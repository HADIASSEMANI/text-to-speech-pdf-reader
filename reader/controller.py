import os
import sys
import time
from bisect import bisect_right
from enum import Enum
from pathlib import Path

from concurrent.futures import ThreadPoolExecutor
from reader.audio_player import AudioPlayer
from reader.cache import create_cache_id, enforce_cache_limit, mark_cache_used
from reader.models import Chapter, Segment
from reader.paths import cache_dir
from reader.tts import KokoroTTS
from reader.progress import ProgressAnchor, save_progress
from reader.models import TextCue



def _lower_worker_priority():
    """Run generation below the GUI thread so playback stays responsive.

    Synthesis is patient work; repainting and cue highlighting are not. Left
    at equal priority the worker takes its full slice and the window stutters
    for as long as a segment is being prepared.
    """
    try:
        if sys.platform == "win32":
            import ctypes

            THREAD_PRIORITY_BELOW_NORMAL = -1

            kernel32 = ctypes.windll.kernel32

            kernel32.SetThreadPriority(
                kernel32.GetCurrentThread(),
                THREAD_PRIORITY_BELOW_NORMAL,
            )
        else:
            os.nice(5)
    except Exception as error:
        print(f"Could not lower generation priority: {error}")


class PlaybackState(str, Enum):
    """The one place playback state is written down.

    Before this existed the same information was spread across a ``running``
    flag, an ``awaiting_audio`` flag and the player's ``is_paused``, and the
    three could disagree: navigation started audio without setting
    ``running``, so the interface showed a paused book that was talking.

    ``PREPARING`` is a playing state that has no audio yet. It is deliberately
    not a separate kind of pause: the listener asked to hear something, so the
    transport reads as playing until they say otherwise.
    """

    STOPPED = "stopped"
    PREPARING = "preparing"
    PLAYING = "playing"
    PAUSED = "paused"
    FINISHED = "finished"


class ReaderController:

    # How often playback position is written to the database while reading.
    # Often enough that a crash costs a sentence, rarely enough that the
    # database is not written on every tick.
    SAVE_INTERVAL_SECONDS = 5.0

    # Step back slightly when resuming a book, so the listener rejoins a
    # sentence already in progress instead of mid-word.
    DEFAULT_RESUME_REWIND = 3.0

    def __init__(
        self,
        segments: list[Segment],
        tts: KokoroTTS,
        book_id: int,
        start_index: int = 0,
        preload_count: int = 2,
        chapters: list[Chapter] | None = None,
        cache_limit_mb: int = 1024,
        start_position: float = 0.0,
        resume_rewind: float | None = None,
    ):
        self.segments = segments
        self.tts = tts
        self.book_id = book_id
        self.start_index = start_index
        self.chapters = chapters if chapters is not None else []
        self.cache_limit_mb = cache_limit_mb

        self.player = AudioPlayer(
            segments,
            start_index=start_index
        )

        self.preload_count = preload_count

        self.futures = {}

        # One worker is safest initially because we're using one
        # Kokoro pipeline/model instance.
        self.executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="tts",
            initializer=_lower_worker_priority,
        )

        self.generating: set[int] = set()
        self.generation_progress: dict[int, int] = {}
        self.generation_errors: dict[int, str] = {}

        # Bumped whenever queued work stops being relevant: a jump, a
        # settings change, closing the book. Results from an older epoch are
        # discarded rather than applied to a segment that has moved on.
        self._epoch = 0

        self.state = PlaybackState.STOPPED

        self.pending_seek: float | None = None

        # A position expressed as a share of the passage rather than in
        # seconds. Used when the audio it refers to does not exist yet at a
        # known length, which is the case right after a speed change.
        self.pending_fraction: float | None = None

        rewind = (
            self.DEFAULT_RESUME_REWIND if resume_rewind is None else resume_rewind
        )

        if start_position > 0:
            self.pending_seek = max(0.0, start_position - rewind)

        self._last_save = time.monotonic()
        self._duration_cache: dict[str, float] = {}

        # Cue lookup state, rebuilt whenever a segment's cues change.
        self._cue_list: list[TextCue] | None = None
        self._cue_starts: list[float] = []
        self._cue_index = 0

    # ------------------------------------------------------------------
    # state
    # ------------------------------------------------------------------

    @property
    def running(self) -> bool:
        """True when the listener has asked to hear the book.

        Kept because it reads well at call sites and because the interface
        binds to it. It is derived from ``state`` rather than stored, so it
        can no longer drift away from what the player is doing.
        """
        return self.state in (
            PlaybackState.PLAYING,
            PlaybackState.PREPARING,
        )

    @property
    def awaiting_audio(self) -> bool:
        return self.state is PlaybackState.PREPARING

    def _set_state(self, state: PlaybackState):
        if state is self.state:
            return

        self.state = state

    # ------------------------------------------------------------------
    # generation
    # ------------------------------------------------------------------

    def ensure_audio(
        self,
        segment: Segment
    ):
        if segment.audio_path is None:
            raise ValueError(
                f"Segment {segment.id} "
                "has no audio path."
            )


        if Path(
            segment.audio_path
        ).exists():

            mark_cache_used(segment.audio_path)

            segment.generated = True

            segment.cues = (
                self.tts.load_cues(
                    segment.audio_path
                )
            )

            self.generation_progress[segment.id] = 100

            return


        segment.cues = (
            self.tts.generate(
                segment.text,
                segment.audio_path,
                on_progress=lambda value: self.generation_progress.__setitem__(
                    segment.id,
                    value,
                ),
            )
        )

        segment.generated = True

    def generate_in_background(
        self,
        segment: Segment
    ):
        if segment.generated:
            return None

        if segment.id in self.generating:
            return self.futures.get(segment.id)

        if segment.audio_path is None:
            return None

        if Path(segment.audio_path).exists():
            segment.generated = True
            segment.cues = self.tts.load_cues(
                segment.audio_path
            )
            self.generation_progress[segment.id] = 100
            return None

        self.generating.add(
            segment.id
        )
        self.generation_progress[segment.id] = 0

        epoch = self._epoch

        future = self.executor.submit(
            self.ensure_audio,
            segment
        )

        self.futures[
            segment.id
        ] = future

        future.add_done_callback(
            lambda future,
            segment=segment,
            epoch=epoch:
            self._generation_finished(
                segment,
                future,
                epoch,
            )
        )

        return future

    def prepare_segment_audio(self, index: int):
        if not 0 <= index < len(self.segments):
            return None

        segment = self.segments[index]

        if segment.audio_path and Path(segment.audio_path).exists():
            self.ensure_audio(segment)
            return None

        segment.generated = False

        return self.generate_in_background(segment)

    def get_generation_progress(self, index: int) -> int:
        if not 0 <= index < len(self.segments):
            return 0

        segment = self.segments[index]

        return self.generation_progress.get(
            segment.id,
            100 if segment.generated else 0,
        )

    def _generation_finished(
        self,
        segment: Segment,
        future,
        epoch: int,
    ):
        self.generating.discard(
            segment.id
        )

        self.futures.pop(
            segment.id,
            None
        )

        if epoch != self._epoch:
            # The book, the voice or the position moved on while this ran.
            # Whatever it produced is still a valid cache entry on disk; it
            # just is not this controller's concern any more.
            return

        try:
            future.result()

        except Exception as error:
            self.generation_errors[segment.id] = str(error)

            print(
                f"Failed generating "
                f"segment {segment.id}: "
                f"{error}"
            )

    def cancel_pending_generation(self):
        """Abandon queued synthesis.

        Work that has not started is cancelled outright. The one segment
        already being synthesized is left to finish on the worker thread: its
        result lands in the cache and is simply ignored. Interrupting it would
        mean tearing down the Kokoro pipeline mid-call.
        """
        self._epoch += 1

        for segment_id, future in list(self.futures.items()):
            if future.cancel():
                self.futures.pop(segment_id, None)
                self.generating.discard(segment_id)
                self.generation_progress.pop(segment_id, None)

    def preload_upcoming(self):
        start = (
            self.player.current_index + 1
        )

        end = (
            start + self.preload_count
        )

        for index in range(
            start,
            min(end, len(self.segments))
        ):
            self.generate_in_background(
                self.segments[index]
            )

    def _segment_ready(self, segment: Segment) -> bool:
        """Report whether a segment can start without synthesizing now.

        Loading cues for an already cached file is cheap and happens here;
        synthesis never does, because this runs on the GUI thread.

        A segment can arrive already marked generated: ``create_segments``
        sets the flag for any passage whose audio is already in the cache. Its
        cues still have to be read, or the reader plays that passage with no
        highlighting and no way to click into it.
        """
        if segment.generated:
            self._ensure_cues_loaded(segment)

            return True

        if segment.audio_path is None:
            return False

        if segment.id in self.generating:
            return False

        if not Path(segment.audio_path).exists():
            return False

        mark_cache_used(segment.audio_path)

        segment.cues = self.tts.load_cues(segment.audio_path)
        segment.generated = True

        self.generation_progress[segment.id] = 100

        return True

    def _ensure_cues_loaded(self, segment: Segment):
        """Read a cached segment's cue file if it has not been read yet."""
        if segment.cues:
            return

        if not segment.audio_path:
            return

        if not Path(segment.audio_path).exists():
            return

        segment.cues = self.tts.load_cues(segment.audio_path)

    def take_generation_error(self) -> str | None:
        """Return and clear the failure recorded for the current segment."""
        segment = self.get_current_segment()

        if segment is None:
            return None

        return self.generation_errors.pop(segment.id, None)

    def retry_preparation(self):
        """Try the current segment again after a failure."""
        segment = self.get_current_segment()

        if segment is None:
            return

        self.generation_errors.pop(segment.id, None)

        self.play()

    def cancel_preparation(self):
        """Stop waiting for audio and leave the reader where it is."""
        self.cancel_pending_generation()

        self._set_state(PlaybackState.STOPPED)

    # ------------------------------------------------------------------
    # transport
    # ------------------------------------------------------------------

    def play_current(self) -> bool:
        """Start the current segment, or queue its audio and report back.

        This runs on the GUI thread, so it never synthesizes and never waits
        on a future: a cache miss used to freeze the window for the whole of
        the generation. Missing audio is requested in the background instead
        and `tick` retries until it is ready.
        """
        segment = self.segments[
            self.player.current_index
        ]

        if self._segment_ready(segment):
            self.player.play()

            if self.pending_fraction is not None:
                target = self.pending_fraction * self.player.get_duration()

                # A second back, so re-voicing lands just before where the
                # listener was rather than clipping the next word.
                self.player.seek(max(0.0, target - 1.0))

                self.pending_fraction = None
                self.pending_seek = None

            elif self.pending_seek is not None:
                self.player.seek(self.pending_seek)
                self.pending_seek = None

            self._set_state(PlaybackState.PLAYING)

            # While current segment plays,
            # prepare upcoming segments.
            self.preload_upcoming()

            return True

        if segment.id in self.generation_errors:
            # Retrying would resubmit the same failing work on every tick.
            self._set_state(PlaybackState.STOPPED)

            return False

        self.generate_in_background(segment)

        if segment.id in self.generating or segment.generated:
            self._set_state(PlaybackState.PREPARING)

            return False

        # Nothing is generating and nothing can be, so stop rather than spin
        # on a segment that will never become playable.
        self._set_state(PlaybackState.STOPPED)

        return False

    def start(self):
        """Kept for callers that predate ``play``."""
        self.play()

    def play(self):
        if not self.segments:
            return

        if self.state is PlaybackState.PAUSED and self.player.current_segment:
            self.player.resume()
            self._set_state(PlaybackState.PLAYING)
            return

        self.play_current()

    def pause(self):
        if self.state is PlaybackState.PLAYING:
            self.player.pause()

        self._set_state(PlaybackState.PAUSED)

        self.save_position(force=True)

    def toggle_pause(self):
        if self.running:
            self.pause()
        else:
            self.play()

    def stop(self):
        """Stop playback, keeping the reading position."""
        self.save_position(force=True)

        self.player.stop()

        self._set_state(PlaybackState.STOPPED)

    def next(self):
        if (
            self.player.current_index
            >= len(self.segments) - 1
        ):
            self._set_state(PlaybackState.FINISHED)
            self.save_position(force=True)
            return

        self._move_to(self.player.current_index + 1)

    RESTART_THRESHOLD_SECONDS = 3.0

    def previous(self):
        if self.player.get_playback_position() > self.RESTART_THRESHOLD_SECONDS:
            self._move_to(self.player.current_index)
            return

        if self.player.current_index <= 0:
            self._move_to(0)
            return

        self._move_to(self.player.current_index - 1)

    def _move_to(self, index: int, position: float = 0.0):
        """Change segment while keeping the transport doing what it was doing.

        A listener who was reading stays reading; a listener who had paused
        stays paused, on the new passage. Either way the interface and the
        audio agree afterwards, which is the whole point of routing every
        move through here.
        """
        was_running = self.running

        self.player.stop()

        self.player.current_index = index
        self.player.current_segment = None

        self.pending_seek = position if position > 0 else None
        self.pending_fraction = None

        self.save_position(force=True)

        if was_running:
            self.play_current()
        else:
            self._set_state(PlaybackState.PAUSED)

    # ------------------------------------------------------------------
    # seeking
    # ------------------------------------------------------------------

    def _segment_duration(self, index: int) -> float | None:
        """Length of a segment's audio without decoding it.

        Reads the WAV header only. Returns None when the segment has not been
        generated yet, which is the signal to stop walking across segments
        and land at the boundary instead of guessing.
        """
        if not 0 <= index < len(self.segments):
            return None

        path = self.segments[index].audio_path

        if not path:
            return None

        if path in self._duration_cache:
            return self._duration_cache[path]

        if not Path(path).exists():
            return None

        try:
            import soundfile as sf

            duration = sf.info(path).duration
        except Exception as error:
            print(f"Could not read duration for {path}: {error}")
            return None

        self._duration_cache[path] = duration

        return duration

    def seek_to(self, seconds: float):
        self.player.seek(seconds)

        self.save_position(force=True)

    def seek_relative(self, seconds: float):
        """Skip by a number of seconds, crossing segments when it has to.

        The old behaviour clamped inside the current segment, so skipping
        back at the start of a passage did nothing and skipping forward near
        the end lost the remainder. Overflow is carried into the neighbouring
        segments here, using their audio headers for duration so nothing has
        to be decoded to work out where to land.
        """
        if not self.segments:
            return

        target = self.player.get_playback_position() + seconds

        index = self.player.current_index

        if 0.0 <= target <= self.player.get_duration():
            self.player.seek(target)
            self.save_position(force=True)
            return

        if target < 0:
            remaining = -target

            while index > 0:
                index -= 1

                duration = self._segment_duration(index)

                if duration is None:
                    # Unknown length: land at the start of this segment
                    # rather than pretend to know how far into it to go.
                    self._move_to(index)
                    return

                if remaining <= duration:
                    self._move_to(index, duration - remaining)
                    return

                remaining -= duration

            self._move_to(0)
            return

        remaining = target - self.player.get_duration()

        last = len(self.segments) - 1

        while index < last:
            index += 1

            duration = self._segment_duration(index)

            if duration is None:
                self._move_to(index)
                return

            if remaining < duration:
                self._move_to(index, remaining)
                return

            remaining -= duration

        # Ran past the end of the book.
        self._move_to(last)
        self.player.seek(self.player.get_duration())
        self._set_state(PlaybackState.FINISHED)

    def seek_and_play(self, seconds: float):
        """Jump to a position and read from there, whatever the current state.

        Used when the listener picks a spot in the text, which is a request to
        hear it rather than only to move the playhead.
        """
        if self.player.current_segment is None:
            # Remember the target: with audio still generating, playback may
            # only start several ticks from now.
            self.pending_seek = seconds

            self.play_current()

            return

        self.player.seek(seconds)

        if self.state is not PlaybackState.PLAYING:
            self.player.resume()
            self._set_state(PlaybackState.PLAYING)

        self.save_position(force=True)

    # ------------------------------------------------------------------
    # navigation
    # ------------------------------------------------------------------

    def go_to_page(self, page_number: int) -> int | None:
        for index, segment in enumerate(self.segments):
            if segment.page == page_number:
                self._jump_to_index(index)
                return segment.page

        for index, segment in enumerate(self.segments):
            if segment.page > page_number:
                self._jump_to_index(index)
                return segment.page

        return None

    def go_to_chapter(self, chapter_index: int) -> bool:
        if not (0 <= chapter_index < len(self.chapters)):
            return False

        chapter = self.chapters[chapter_index]

        if chapter.segment_index is None:
            return False

        self._jump_to_index(chapter.segment_index)

        return True

    def get_current_chapter_index(self) -> int | None:
        current_index = self.player.current_index

        current_chapter = None

        for index, chapter in enumerate(self.chapters):
            if chapter.segment_index is None:
                continue

            if chapter.segment_index <= current_index:
                current_chapter = index
            else:
                break

        return current_chapter

    def _jump_to_index(self, index: int):
        """Move somewhere the listener chose, and wait for them to press play.

        Deliberately unlike ``_move_to``: a page or chapter jump is an act of
        looking, not of listening, so it never starts audio. Queued synthesis
        for wherever we were is abandoned.
        """
        self.cancel_pending_generation()

        self.player.stop()
        self.player.current_index = index
        self.player.current_segment = None

        self.pending_seek = None
        self.pending_fraction = None

        self._set_state(PlaybackState.STOPPED)

        self.save_position(force=True)

    # ------------------------------------------------------------------
    # narration settings
    # ------------------------------------------------------------------

    def apply_narration_settings(self, voice: str, speed: float) -> bool:
        """Re-voice the open book without losing the listener's place.

        Voice and speed are part of every segment's cache id, so changing
        them means every segment points at different audio. Only the id
        changes here: nothing is synthesized until it is needed, and the
        previous audio stays in the cache, so switching back is a cache hit.

        Position is carried across as a fraction of the passage rather than
        as seconds, because seconds mean something different at a different
        speed.
        """
        if voice == self.tts.voice and abs(speed - self.tts.speed) < 1e-9:
            return False

        was_running = self.running

        duration = self.player.get_duration()

        fraction = (
            self.player.get_playback_position() / duration
            if duration > 0
            else 0.0
        )

        self.cancel_pending_generation()

        self.player.stop()
        self.player.current_segment = None

        self.tts.voice = voice
        self.tts.speed = speed

        for segment in self.segments:
            segment.cache_id = create_cache_id(
                text=segment.text,
                voice=voice,
                speed=speed,
            )

            segment.audio_path = str(cache_dir() / f"{segment.cache_id}.wav")
            segment.generated = Path(segment.audio_path).exists()
            segment.cues = []

        self.generation_progress.clear()
        self.generation_errors.clear()
        self._duration_cache.clear()

        self._cue_list = None
        self._cue_starts = []
        self._cue_index = 0

        self.pending_seek = None
        self.pending_fraction = fraction if fraction > 0 else None

        self.save_position(force=True)

        if was_running:
            self.play_current()
        else:
            self._set_state(PlaybackState.PAUSED)

        return True

    # ------------------------------------------------------------------
    # progress
    # ------------------------------------------------------------------

    def save_position(self, force: bool = False):
        """Write the reading position, with its anchor.

        Called before anything that stops the player, because ``stop()``
        resets the offset to zero: saving afterwards was how the position was
        being lost on the way back to the library.
        """
        now = time.monotonic()

        if not force and now - self._last_save < self.SAVE_INTERVAL_SECONDS:
            return

        self._last_save = now

        segment = self.get_current_segment()

        if segment is None:
            return

        save_progress(
            book_id=self.book_id,
            segment_index=self.player.current_index,
            playback_position=self.player.get_playback_position(),
            anchor=ProgressAnchor.from_segment(segment),
        )

    # ------------------------------------------------------------------
    # tick
    # ------------------------------------------------------------------

    def tick(self):
        if self.state is PlaybackState.PREPARING:
            self.play_current()
            return

        if self.state is not PlaybackState.PLAYING:
            return

        if not self.player.is_playing():
            self.next()
            return

        self.save_position()

    # ------------------------------------------------------------------
    # queries
    # ------------------------------------------------------------------

    def get_current_segment(self) -> Segment | None:
        if not self.segments:
            return None

        return self.segments[
            self.player.current_index
        ]

    def get_current_index(self):
        return self.player.current_index

    def get_current_cue(
        self
    ) -> TextCue | None:
        """Cue covering the playhead, found without walking every cue.

        This is called on every GUI tick, so it starts from the cue it
        returned last — which is nearly always still the right one — and
        falls back to a binary search rather than a scan.
        """
        segment = (
            self.get_current_segment()
        )

        if segment is None:
            return None

        cues = segment.cues

        if not cues:
            self._ensure_cues_loaded(segment)

            cues = segment.cues

            if not cues:
                return None

        if cues is not self._cue_list:
            self._cue_list = cues
            self._cue_starts = [cue.start for cue in cues]
            self._cue_index = 0

        position = self.player.get_playback_position()

        if 0 <= self._cue_index < len(cues):
            cue = cues[self._cue_index]

            if cue.start <= position < cue.end:
                return cue

        index = bisect_right(self._cue_starts, position) - 1

        if index < 0:
            return None

        cue = cues[index]

        if cue.start <= position < cue.end:
            self._cue_index = index
            return cue

        return None

    # ------------------------------------------------------------------
    # shutdown
    # ------------------------------------------------------------------

    def shutdown(self, wait: bool = False):
        """Close the book.

        ``wait`` is false by default so switching books is immediate. The
        audio device is still torn down synchronously here, which is what the
        next AudioPlayer needs; only the in-flight synthesis is left running,
        and it writes its result into the cache atomically. Application exit
        passes ``wait=True`` to let that last file finish.
        """
        current_index = self.player.current_index
        protected_end = current_index + self.preload_count + 1
        protected_paths = [
            segment.audio_path
            for segment in self.segments[current_index:protected_end]
            if segment.audio_path
        ]

        # Before anything stops the player: stopping resets the offset.
        self.save_position(force=True)

        self._set_state(PlaybackState.STOPPED)

        self.cancel_pending_generation()

        self.player.stop()

        # Tear the audio device down first: the next book cannot build an
        # AudioPlayer until this mixer has quit. Synthesis never touches
        # pygame, so it does not have to be joined first.
        self.player.shutdown()

        self.executor.shutdown(wait=wait, cancel_futures=True)

        enforce_cache_limit(
            self.cache_limit_mb * 1024 * 1024,
            protected_audio_paths=protected_paths,
        )

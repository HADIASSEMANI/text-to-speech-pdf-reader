import os
import sys
import time
from bisect import bisect_right
from pathlib import Path

from concurrent.futures import ThreadPoolExecutor
from reader.audio_player import AudioPlayer
from reader.cache import enforce_cache_limit, mark_cache_used
from reader.models import Chapter, Segment
from reader.tts import KokoroTTS
from reader.progress import save_progress
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


class ReaderController:
    def __init__(
        self,
        segments: list[Segment],
        tts: KokoroTTS,
        book_id: int,
        start_index: int = 0,
        preload_count: int = 2,
        chapters: list[Chapter] | None = None,
        cache_limit_mb: int = 1024,
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

        # Set while the current segment has no audio yet. Playback is
        # retried from `tick` instead of blocking whoever asked for it.
        self.awaiting_audio = False
        self.pending_seek: float | None = None

        # Cue lookup state, rebuilt whenever a segment's cues change.
        self._cue_list: list[TextCue] | None = None
        self._cue_starts: list[float] = []
        self._cue_index = 0

        self.running = False

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

        print(
            f"Pre-generating segment "
            f"{segment.id}"
        )

        future = self.executor.submit(
            self.ensure_audio,
            segment
        )

        self.futures[
            segment.id
        ] = future

        future.add_done_callback(
            lambda future,
            segment=segment:
            self._generation_finished(
                segment,
                future
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
        future
    ):
        self.generating.discard(
            segment.id
        )

        self.futures.pop(
            segment.id,
            None
        )

        try:
            future.result()

            print(
                f"Segment {segment.id} ready."
            )

        except Exception as error:
            self.generation_errors[segment.id] = str(error)

            print(
                f"Failed generating "
                f"segment {segment.id}: "
                f"{error}"
            )

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
        """
        if segment.generated:
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

    def take_generation_error(self) -> str | None:
        """Return and clear the failure recorded for the current segment."""
        segment = self.get_current_segment()

        if segment is None:
            return None

        return self.generation_errors.pop(segment.id, None)

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
            self.awaiting_audio = False

            self.player.play()

            if self.pending_seek is not None:
                self.player.seek(self.pending_seek)
                self.pending_seek = None

            # While current segment plays,
            # prepare upcoming segments.
            self.preload_upcoming()

            return True

        if segment.id in self.generation_errors:
            # Retrying would resubmit the same failing work on every tick.
            self.awaiting_audio = False
            self.running = False

            return False

        self.generate_in_background(segment)

        if segment.id in self.generating or segment.generated:
            self.awaiting_audio = True

            return False

        # Nothing is generating and nothing can be, so stop rather than spin
        # on a segment that will never become playable.
        self.awaiting_audio = False
        self.running = False

        return False

    def next(self):

        if (
            self.player.current_index
            >= len(self.segments) - 1
        ):
            print("End of book.")
            self.running = False
            return

        self.player.stop()

        self.player.current_index += 1

        save_progress(
            book_id=self.book_id,
            segment_index=self.player.current_index
        )

        self.play_current()

    def previous(self):

        if self.player.current_index <= 0:
            return

        self.player.stop()

        self.player.current_index -= 1

        save_progress(
            book_id=self.book_id,
            segment_index=self.player.current_index
        )

        self.play_current()

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
        self.player.stop()
        self.player.current_index = index
        self.player.current_segment = None
        self.running = False
        self.awaiting_audio = False
        self.pending_seek = None

        save_progress(
            book_id=self.book_id,
            segment_index=index,
            playback_position=0.0,
        )

    def start(self):
        if not self.segments:
            print("No segments.")
            return

        self.running = True

        self.play_current()

    def tick(self):
        if not self.running:
            return

        if self.awaiting_audio:
            self.play_current()
            return

        if self.player.is_paused:
            return

        if not self.player.is_playing():
            self.next()

    def toggle_pause(self):

        if self.player.current_segment is None:
            self.play_current()
            return

        if self.player.is_paused:
            self.player.resume()
        else:
            self.player.pause()

    def seek_to(self, seconds: float):
        self.player.seek(seconds)

    def seek_relative(self, seconds: float):
        current = self.player.get_playback_position()

        self.player.seek(current + seconds)

    def seek_and_play(self, seconds: float):
        """Jump to a position and read from there, whatever the current state.

        Used when the listener picks a spot in the text, which is a request to
        hear it rather than only to move the playhead.
        """
        if not self.running:
            # Remember the target: with audio still generating, playback may
            # only start several ticks from now.
            self.pending_seek = seconds

            self.start()

            if self.awaiting_audio:
                return

            self.pending_seek = None

        self.player.seek(seconds)

        if self.player.is_paused:
            self.player.resume()

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

    def shutdown(self):

        current_index = self.player.current_index
        protected_end = current_index + self.preload_count + 1
        protected_paths = [
            segment.audio_path
            for segment in self.segments[current_index:protected_end]
            if segment.audio_path
        ]

        save_progress(
            book_id=self.book_id,
            segment_index=self.player.current_index,
            playback_position=self.player.get_playback_position()
        )

        self.running = False
        self.awaiting_audio = False

        self.player.stop()

        self.executor.shutdown(
            wait=True
        )

        self.player.shutdown()

        enforce_cache_limit(
            self.cache_limit_mb * 1024 * 1024,
            protected_audio_paths=protected_paths,
        )

import time
from pathlib import Path

from concurrent.futures import ThreadPoolExecutor
from reader.audio_player import AudioPlayer
from reader.models import Chapter, Segment
from reader.tts import KokoroTTS
from reader.progress import save_progress
from reader.models import TextCue



class ReaderController:
    def __init__(
        self,
        segments: list[Segment],
        tts: KokoroTTS,
        book_id: int,
        start_index: int = 0,
        preload_count: int = 2,
        chapters: list[Chapter] | None = None,
    ):
        self.segments = segments
        self.tts = tts
        self.book_id = book_id
        self.start_index = start_index
        self.chapters = chapters if chapters is not None else []

        self.player = AudioPlayer(
            segments,
            start_index=start_index
        )

        self.preload_count = preload_count

        self.futures = {}

        # One worker is safest initially because we're using one
        # Kokoro pipeline/model instance.
        self.executor = ThreadPoolExecutor(
            max_workers=1
        )

        self.generating: set[int] = set()

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

            segment.generated = True

            segment.cues = (
                self.tts.load_cues(
                    segment.audio_path
                )
            )

            return


        segment.cues = (
            self.tts.generate(
                segment.text,
                segment.audio_path
            )
        )

        segment.generated = True

    def generate_in_background(
        self,
        segment: Segment
    ):
        if segment.generated:
            return

        if segment.id in self.generating:
            return

        if segment.audio_path is None:
            return

        if Path(segment.audio_path).exists():
            segment.generated = True
            segment.cues = self.tts.load_cues(
                segment.audio_path
            )
            return

        self.generating.add(
            segment.id
        )

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

    def play_current(self):
        segment = self.segments[
            self.player.current_index
        ]

        future = self.futures.get(
            segment.id
        )

        if future is not None:
            
            print(
                f"Waiting for segment "
                f"{segment.id} to finish generating..."
            )

            future.result()
        else:

            self.ensure_audio(
                segment
            )

        self.player.play()

        # While current segment plays,
        # prepare upcoming segments.
        self.preload_upcoming()

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
            self.start()

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

        segment = (
            self.get_current_segment()
        )

        if segment is None:
            return None

        if not segment.cues:
            return None

        position = self.player.get_playback_position()

        for cue in segment.cues:

            if (
                cue.start
                <= position
                < cue.end
            ):
                return cue

        return None

    def shutdown(self):

        save_progress(
            book_id=self.book_id,
            segment_index=self.player.current_index,
            playback_position=self.player.get_playback_position()
        )

        self.running = False

        self.player.stop()

        self.executor.shutdown(
            wait=True
        )

        self.player.shutdown()

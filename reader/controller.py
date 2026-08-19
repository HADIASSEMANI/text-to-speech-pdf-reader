from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import time

from reader.audio_player import AudioPlayer
from reader.models import Segment
from reader.tts import KokoroTTS


class ReaderController:
    def __init__(
        self,
        segments: list[Segment],
        tts: KokoroTTS,
        preload_count: int = 2,
    ):
        self.segments = segments
        self.tts = tts

        self.player = AudioPlayer(segments)

        self.preload_count = preload_count

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

        if Path(segment.audio_path).exists():
            segment.generated = True
            return

        self.tts.generate(
            segment.text,
            segment.audio_path
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

        # Current segment must exist before
        # playback starts.
        self.ensure_audio(segment)

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

        self.play_current()

    def previous(self):
        if self.player.current_index <= 0:
            return

        self.player.stop()

        self.player.current_index -= 1

        self.play_current()

    def run(self):
        if not self.segments:
            print("No segments.")
            return

        self.running = True

        self.play_current()

        while self.running:

            # Paused audio should not trigger
            # automatic advancement.
            if self.player.is_paused:
                time.sleep(0.1)
                continue

            # Playback finished.
            if not self.player.is_playing():
                self.next()

            time.sleep(0.1)

    def shutdown(self):
        self.running = False

        self.player.stop()

        self.executor.shutdown(
            wait=True
        )
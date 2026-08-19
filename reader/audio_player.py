import pygame

from reader.models import Segment

class AudioPlayer:
    def __init__(self, segments: list[Segment]):
        pygame.mixer.init()

        self.segments = segments

        self.current_index = 0
        self.current_segment: Segment | None = None

        self.is_paused = False

    def play(self):
        if not self.segments:
            print("No segments available.")
            return

        segment = self.segments[self.current_index]

        if segment.audio_path is None:
            print(
                f"Segment {segment.id} has no audio."
            )
            return

        self.current_segment = segment

        pygame.mixer.music.load(
            segment.audio_path
        )

        pygame.mixer.music.play()

        self.is_paused = False

        print(
            f"Playing segment {segment.id} "
            f"| page {segment.page}"
        )

    def pause(self):
        if self.current_segment is None:
            return

        if self.is_paused:
            return

        pygame.mixer.music.pause()

        self.is_paused = True

        print("Paused")

    def resume(self):
        if not self.is_paused:
            return

        pygame.mixer.music.unpause()

        self.is_paused = False

        print("Resumed")

    def stop(self):
        pygame.mixer.music.stop()

        self.is_paused = False

        print("Stopped")

    def next(self):
        if self.current_index >= len(self.segments) - 1:
            print("Already at final segment.")
            return

        self.stop()

        self.current_index += 1

        self.play()

    def previous(self):
        if self.current_index <= 0:
            print("Already at first segment.")
            return

        self.stop()

        self.current_index -= 1

        self.play()

    def is_playing(self) -> bool:
        return (
            pygame.mixer.music.get_busy()
            and not self.is_paused
        )

    def get_current_segment(self) -> Segment | None:
        return self.current_segment
    
import time

import numpy as np
import pygame
import soundfile as sf

from reader.models import Segment


class AudioPlayer:
    """Sound/Channel based player with exact seeking.

    ``pygame.mixer.music.play(start=...)`` does not seek WAV files
    reliably, so audio is decoded with soundfile and played from an
    arbitrary frame offset through a mixer Channel. Playback position
    is tracked with a monotonic clock rather than ``music.get_pos()``,
    which keeps counting while paused.
    """

    def __init__(
        self,
        segments: list[Segment],
        start_index: int = 0,
    ):
        pygame.mixer.init()

        self.segments = segments
        self.current_index = start_index

        self.current_segment: Segment | None = None

        self.is_paused = False

        self.playback_offset = 0.0

        self._mixer_format: tuple[int, int] | None = None
        self._data = None
        self._samplerate = 0
        self._sound: pygame.mixer.Sound | None = None
        self._channel: pygame.mixer.Channel | None = None
        self._started_at = 0.0

        # Sounds that were stopped but may still be referenced by SDL's mixer
        # thread. Releasing one the instant its channel stops segfaults, so
        # they are held for a few more seeks before being dropped.
        self._retired: list[pygame.mixer.Sound] = []

    # ------------------------------------------------------------------
    # decoding
    # ------------------------------------------------------------------

    def _load(self, path: str) -> bool:
        try:
            data, samplerate = sf.read(
                path,
                dtype="int16",
                always_2d=True,
            )
        except Exception as error:
            print(f"Failed reading {path}: {error}")
            return False

        channels = data.shape[1]

        if self._mixer_format != (samplerate, channels):
            self._silence_current()

            pygame.mixer.quit()

            pygame.mixer.init(
                frequency=samplerate,
                size=-16,
                channels=channels,
            )

            self._mixer_format = (samplerate, channels)

        # The mixer may refuse the requested format and open the device
        # with another one. A raw buffer is interpreted with whatever the
        # device actually uses, so mono data on a stereo device plays at
        # double speed. Match the real format instead of the asked one.
        actual = pygame.mixer.get_init()

        if actual is not None:
            device_rate, _size, device_channels = actual

            data = self._conform(
                data,
                samplerate,
                device_rate,
                device_channels,
            )

            samplerate = device_rate

        self._data = np.ascontiguousarray(data)
        self._samplerate = samplerate

        return True

    @staticmethod
    def _conform(
        data,
        samplerate: int,
        device_rate: int,
        device_channels: int,
    ):
        if device_rate != samplerate and samplerate > 0:
            source_frames = len(data)

            target_frames = int(
                round(source_frames * device_rate / samplerate)
            )

            if target_frames > 0 and source_frames > 1:
                source_positions = np.arange(source_frames)

                target_positions = np.linspace(
                    0,
                    source_frames - 1,
                    target_frames,
                )

                data = np.stack(
                    [
                        np.interp(
                            target_positions,
                            source_positions,
                            data[:, channel].astype(np.float32),
                        )
                        for channel in range(data.shape[1])
                    ],
                    axis=1,
                ).astype(np.int16)

        if data.shape[1] != device_channels:
            if data.shape[1] == 1:
                data = np.repeat(data, device_channels, axis=1)
            else:
                data = data[:, :device_channels]

        return data

    RETIRED_LIMIT = 4

    def _silence_current(self):
        """Stop whatever is sounding before starting new audio.

        Every seek builds a fresh Sound. ``Sound.play()`` picks any free
        channel, so without this the previous clip keeps playing underneath
        and repeated skips stack voice on voice.
        """
        if self._channel is not None:
            self._channel.stop()

        if self._sound is not None:
            self._sound.stop()

            self._retired.append(self._sound)

            while len(self._retired) > self.RETIRED_LIMIT:
                self._retired.pop(0)

        self._channel = None
        self._sound = None

    def _play_from(self, seconds: float):
        if self._data is None or self._samplerate <= 0:
            return

        frame = int(seconds * self._samplerate)

        frame = max(0, min(frame, len(self._data)))

        self._silence_current()

        if frame >= len(self._data):
            # Seeking to (or past) the end leaves nothing to play, and handing
            # SDL a zero-length buffer crashes the process. Park at the end
            # instead; the controller sees idle playback and advances.
            self.playback_offset = self.get_duration()
            self._started_at = time.monotonic()
            self.is_paused = False

            return

        sound = pygame.mixer.Sound(buffer=self._data[frame:].tobytes())

        # Always play on the same reserved channel. Channel.play() replaces
        # what that channel is doing, so narration can never overlap itself.
        channel = pygame.mixer.Channel(0)
        channel.play(sound)

        self._sound = sound
        self._channel = channel

        self.playback_offset = frame / self._samplerate
        self._started_at = time.monotonic()
        self.is_paused = False

    # ------------------------------------------------------------------
    # transport
    # ------------------------------------------------------------------

    def play(self):
        if not self.segments:
            print("No segments available.")
            return

        segment = self.segments[self.current_index]

        if segment.audio_path is None:
            print(f"Segment {segment.id} has no audio.")
            return

        if not self._load(segment.audio_path):
            return

        self.current_segment = segment

        self._play_from(0.0)

        print(f"Playing segment {segment.id} " f"| page {segment.page}")

    def pause(self):
        if self.current_segment is None:
            return

        if self.is_paused:
            return

        # Freeze the elapsed time before the clock stops being read.
        self.playback_offset = self.get_playback_position()

        if self._channel is not None:
            self._channel.pause()

        self.is_paused = True

        print("Paused")

    def resume(self):
        if not self.is_paused:
            return

        if self._channel is not None:
            self._channel.unpause()

        self._started_at = time.monotonic()

        self.is_paused = False

        print("Resumed")

    def stop(self):
        self._silence_current()

        self.playback_offset = 0.0
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

    # ------------------------------------------------------------------
    # seeking
    # ------------------------------------------------------------------

    def get_duration(self) -> float:
        if self._data is None or self._samplerate <= 0:
            return 0.0

        return len(self._data) / self._samplerate

    def seek(self, seconds: float):
        if self.current_segment is None:
            return

        duration = self.get_duration()

        if duration <= 0:
            return

        seconds = max(0.0, min(seconds, duration))

        was_paused = self.is_paused

        self._play_from(seconds)

        if was_paused:
            if self._channel is not None:
                self._channel.pause()

            self.is_paused = True

    # ------------------------------------------------------------------
    # state
    # ------------------------------------------------------------------

    def is_playing(self) -> bool:
        if self._channel is None:
            return False

        return self._channel.get_busy() and not self.is_paused

    def get_current_segment(self) -> Segment | None:
        return self.current_segment

    def get_playback_position(self) -> float:
        if self._channel is None:
            # No channel means stopped (offset 0) or parked at the end of the
            # segment after seeking past it. Either way the offset is truth.
            return self.playback_offset

        if self.is_paused:
            return self.playback_offset

        elapsed = time.monotonic() - self._started_at

        position = self.playback_offset + elapsed

        duration = self.get_duration()

        if duration > 0:
            position = min(position, duration)

        return position

    def shutdown(self):
        self._silence_current()

        self._data = None
        self._mixer_format = None

        pygame.mixer.quit()

        self.current_segment = None
        self.is_paused = False
        self.playback_offset = 0.0

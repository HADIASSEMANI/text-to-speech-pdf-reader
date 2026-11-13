from PySide6.QtCore import QSettings


class AppSettings:
    ORGANIZATION = "BookTTS"
    APPLICATION = "BookTTSReader"

    # Matches the narration speed the reader has always used. Changing this
    # changes every cache id, because speed is part of the cache key.
    DEFAULT_VOICE = "af_heart"
    DEFAULT_SPEED = 0.85
    DEFAULT_CACHE_LIMIT_MB = 1024
    DEFAULT_TEXT_SIZE = 18
    MIN_TEXT_SIZE = 14
    MAX_TEXT_SIZE = 32

    def __init__(self):
        self.settings = QSettings(self.ORGANIZATION, self.APPLICATION)

    @classmethod
    def clamp_text_size(cls, value) -> int:
        try:
            size = int(value)
        except (TypeError, ValueError, OverflowError):
            size = cls.DEFAULT_TEXT_SIZE
        return max(cls.MIN_TEXT_SIZE, min(cls.MAX_TEXT_SIZE, size))

    def get_text_size(self) -> int:
        return self.clamp_text_size(
            self.settings.value("reader/text_size", self.DEFAULT_TEXT_SIZE)
        )

    def set_text_size(self, size: int):
        self.settings.setValue("reader/text_size", self.clamp_text_size(size))

    # -------------------------
    # Voice
    # -------------------------

    def get_voice(self) -> str:
        return self.settings.value("tts/voice", self.DEFAULT_VOICE, type=str)

    def set_voice(self, voice: str):
        self.settings.setValue("tts/voice", voice)

    # -------------------------
    # TTS speed
    # -------------------------

    def get_speed(self) -> float:
        return self.settings.value("tts/speed", self.DEFAULT_SPEED, type=float)

    def set_speed(self, speed: float):
        self.settings.setValue("tts/speed", speed)

    # -------------------------
    # Generated audio cache
    # -------------------------

    def get_cache_limit_mb(self) -> int:
        return self.settings.value(
            "cache/max_size_mb",
            self.DEFAULT_CACHE_LIMIT_MB,
            type=int,
        )

    def set_cache_limit_mb(self, size_mb: int):
        self.settings.setValue("cache/max_size_mb", max(256, int(size_mb)))

    # -------------------------
    # Narration content options
    # -------------------------

    def get_read_footnotes(self) -> bool:
        return self.settings.value("narration/read_footnotes", False, type=bool)

    def set_read_footnotes(self, value: bool):
        self.settings.setValue("narration/read_footnotes", value)

    def get_read_captions(self) -> bool:
        return self.settings.value("narration/read_captions", False, type=bool)

    def set_read_captions(self, value: bool):
        self.settings.setValue("narration/read_captions", value)

    def get_read_sidebars(self) -> bool:
        return self.settings.value("narration/read_sidebars", False, type=bool)

    def set_read_sidebars(self, value: bool):
        self.settings.setValue("narration/read_sidebars", value)

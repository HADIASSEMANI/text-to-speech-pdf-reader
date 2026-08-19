from PySide6.QtCore import QSettings


class AppSettings:
    ORGANIZATION = "BookTTS"
    APPLICATION = "BookTTSReader"

    # Matches the narration speed the reader has always used. Changing this
    # changes every cache id, because speed is part of the cache key.
    DEFAULT_VOICE = "af_heart"
    DEFAULT_SPEED = 0.85

    def __init__(self):
        self.settings = QSettings(self.ORGANIZATION, self.APPLICATION)

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

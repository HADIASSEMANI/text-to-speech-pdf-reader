from pathlib import Path

import soundfile as sf
from kokoro import KPipeline


class KokoroTTS:

    SAMPLE_RATE = 24000

    def __init__(
        self,
        voice: str = "af_heart",
        speed: float = 1.0,
        lang_code: str = "a",
    ):
        self.voice = voice
        self.speed = speed

        self.pipeline = KPipeline(
            lang_code=lang_code,
            repo_id="hexgrad/Kokoro-82M"
        )

    def generate(
        self,
        text: str,
        output_path: str
    ) -> str:

        output = Path(output_path)

        output.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        generator = self.pipeline(
            text,
            voice=self.voice,
            speed=self.speed,
        )

        audio_parts = []

        for _, _, audio in generator:
            audio_parts.append(audio)

        if not audio_parts:
            raise RuntimeError(
                "Kokoro returned no audio."
            )

        if len(audio_parts) == 1:
            final_audio = audio_parts[0]

        else:
            import numpy as np

            final_audio = np.concatenate(
                audio_parts
            )

        sf.write(
            output,
            final_audio,
            self.SAMPLE_RATE
        )

        return str(output)
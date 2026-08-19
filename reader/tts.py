import json
import os
import warnings
import soundfile as sf
import numpy as np

from pathlib import Path
from kokoro import KPipeline

import torch
from reader.models import TextCue
from reader.paths import cache_dir


CACHE_DIR = cache_dir()

# Kokoro synthesizes on the reader's background worker. Left at its default,
# torch claims every core, the GUI thread loses its slice, and the whole app
# stutters for as long as the next segment is being prepared. Two cores are
# reserved: one for the interface, one for playback.
_TTS_THREADS = max(1, (os.cpu_count() or 3) - 2)

torch.set_num_threads(_TTS_THREADS)

try:
    torch.set_num_interop_threads(1)
except RuntimeError:
    # Torch only accepts this before its inter-op pool starts. If something
    # already started it, the intra-op cap above still does the real work.
    pass

warnings.filterwarnings(
    "ignore",
    message="dropout option adds dropout after all but last recurrent layer",
    category=UserWarning,
)

warnings.filterwarnings(
    "ignore",
    message="`torch.nn.utils.weight_norm` is deprecated",
    category=FutureWarning,
)

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
        output_path: str,
        on_progress=None,
    ) -> list[TextCue]:

        output = Path(
            output_path
        )

        output.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        audio_parts = []
        cues = []
        current_time = 0.0
        processed_characters = 0
        total_characters = max(len(text), 1)

        if on_progress is not None:
            on_progress(0)

        generator = self.pipeline(
            text,
            voice=self.voice,
            speed=self.speed,
        )


        for graphemes, phonemes, audio in generator:

            duration = (
                len(audio)
                / self.SAMPLE_RATE
            )

            cue = TextCue(
                text=graphemes,
                start=current_time,
                end=current_time + duration
            )

            cues.append(cue)

            audio_parts.append(
                audio
            )

            current_time += duration

            processed_characters += len(graphemes)

            if on_progress is not None:
                on_progress(
                    min(
                        int(processed_characters / total_characters * 95),
                        95,
                    )
                )
        
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

        self._save_cues(
            output,
            cues
        )

        if on_progress is not None:
            on_progress(100)


        return cues

    def is_cache_empty() -> bool:
        CACHE_DIR.mkdir(
            parents=True,
            exist_ok=True
        )

        return not any(
            CACHE_DIR.iterdir()
        )

    def _save_cues(
        self,
        output: Path,
        cues: list[TextCue]
    ):
        cue_path = output.with_suffix(
            ".json"
        )

        data = [
            {
                "text": cue.text,
                "start": cue.start,
                "end": cue.end
            }
            for cue in cues
        ]

        cue_path.write_text(
            json.dumps(
                data,
                indent=2
            ),
            encoding="utf-8"
        )

    def load_cues(
        self,
        audio_path: str
    ) -> list[TextCue]:

        cue_path = Path(
            audio_path
        ).with_suffix(
            ".json"
        )

        if not cue_path.exists():
            return []

        data = json.loads(
            cue_path.read_text(
                encoding="utf-8"
            )
        )

        return [
            TextCue(
                text=item["text"],
                start=item["start"],
                end=item["end"]
            )
            for item in data
        ]

import json
import os
import warnings
import soundfile as sf
import numpy as np

from pathlib import Path
from huggingface_hub import hf_hub_download
from kokoro import KModel, KPipeline

import torch
from reader.models import TextCue
from reader.paths import cache_dir


KOKORO_REPO_ID = "hexgrad/Kokoro-82M"
KOKORO_REVISION = "f3ff3571791e39611d31c381e3a41a3af07b4987"
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

        config_path = hf_hub_download(
            repo_id=KOKORO_REPO_ID,
            filename="config.json",
            revision=KOKORO_REVISION,
        )
        model_path = hf_hub_download(
            repo_id=KOKORO_REPO_ID,
            filename=KModel.MODEL_NAMES[KOKORO_REPO_ID],
            revision=KOKORO_REVISION,
        )
        device = "cuda" if torch.cuda.is_available() else "cpu"
        model = KModel(
            repo_id=KOKORO_REPO_ID,
            config=config_path,
            model=model_path,
        ).to(device).eval()

        self.pipeline = KPipeline(
            lang_code=lang_code,
            repo_id=KOKORO_REPO_ID,
            model=model,
        )

    def _resolve_voice(self, voice: str) -> str:
        resolved = []
        for part in voice.split(","):
            part = part.strip()
            if part.endswith(".pt"):
                resolved.append(part)
            else:
                resolved.append(
                    hf_hub_download(
                        repo_id=KOKORO_REPO_ID,
                        filename=f"voices/{part}.pt",
                        revision=KOKORO_REVISION,
                    )
                )
        return ",".join(resolved)

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

        voice_path = self._resolve_voice(self.voice)
        generator = self.pipeline(
            text,
            voice=voice_path,
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

        # Write through a temporary name and rename into place. Synthesis
        # can outlive the book it was started for, and a process that exits
        # mid-write would otherwise leave a truncated WAV in the cache that
        # every later read of that passage would fail on.
        self._write_atomically(
            output,
            lambda target: sf.write(
                target,
                final_audio,
                self.SAMPLE_RATE,
            ),
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

    @staticmethod
    def _write_atomically(target: Path, write):
        # The extension has to survive: soundfile picks its format from it,
        # so a plain ".part" suffix makes every write fail.
        temporary = target.with_name(
            f"{target.stem}.part{target.suffix}"
        )

        try:
            write(temporary)

            os.replace(temporary, target)

        except BaseException:
            temporary.unlink(missing_ok=True)

            raise

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

        self._write_atomically(
            cue_path,
            lambda target: target.write_text(
                json.dumps(
                    data,
                    indent=2
                ),
                encoding="utf-8"
            ),
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

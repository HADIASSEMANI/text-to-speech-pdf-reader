import hashlib
from pathlib import Path

from reader.paths import cache_dir

CACHE_DIR = cache_dir()


def create_cache_id(text: str, voice: str, speed: float = 1.0) -> str:

    content = f"{voice}:{speed}:{text}"

    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def clear_cache(segments, current_index: int) -> int:
    """Delete audio and cue files for segments already read.

    Only segments strictly before ``current_index`` are removed, so upcoming
    and preloaded narration survives. Cache files are named by cache id, and
    identical text shares one file, so a file is kept when any segment from
    the current position onward still points at it.
    """
    if not segments:
        return 0

    current_index = max(0, min(current_index, len(segments)))

    still_needed = {
        segment.audio_path
        for segment in segments[current_index:]
        if segment.audio_path
    }

    removed = 0

    for segment in segments[:current_index]:
        audio_path = segment.audio_path

        if not audio_path or audio_path in still_needed:
            continue

        audio_file = Path(audio_path)

        for path in (audio_file, audio_file.with_suffix(".json")):
            try:
                path.unlink()
            except FileNotFoundError:
                continue
            except OSError as error:
                print(f"Could not remove {path}: {error}")
                continue

            if path == audio_file:
                removed += 1

        # The audio no longer exists, so let it be regenerated if the reader
        # comes back to this segment.
        segment.generated = False
        segment.cues = []

    if removed:
        print(f"Removed {removed} played segment(s) from the audio cache.")

    return removed

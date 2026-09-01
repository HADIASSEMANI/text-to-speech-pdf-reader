import re
from pathlib import Path

from reader.paths import pasted_text_dir


_WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{number}" for number in range(1, 10)),
    *(f"LPT{number}" for number in range(1, 10)),
}


def _suggest_title(text: str) -> str:
    first_line = next(
        (line.strip() for line in text.splitlines() if line.strip()),
        "Pasted text",
    )

    return first_line[:80]


def _safe_file_stem(title: str) -> str:
    stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", title)
    stem = re.sub(r"\s+", " ", stem).strip(" .")
    stem = stem[:80].rstrip(" .") or "Pasted text"

    if stem.upper() in _WINDOWS_RESERVED_NAMES:
        stem += " text"

    return stem


def save_pasted_text(
    text: str,
    title: str = "",
    directory: Path | None = None,
) -> str:
    """Save pasted narration as a durable text source and return its path.

    Keeping pasted content as an app-managed file lets it use the normal
    library, progress, segmentation, and cache code without a parallel reader
    implementation.
    """
    if not text or not text.strip():
        raise ValueError("Paste some text before opening the reader.")

    display_title = title.strip() or _suggest_title(text)
    stem = _safe_file_stem(display_title)
    target_dir = directory or pasted_text_dir()
    target_dir.mkdir(parents=True, exist_ok=True)

    path = target_dir / f"{stem}.txt"
    suffix = 2

    while path.exists():
        path = target_dir / f"{stem} ({suffix}).txt"
        suffix += 1

    path.write_text(text, encoding="utf-8")

    return str(path)


def extract_text(path: str) -> list[dict]:
    """Read a UTF-8 plain-text source as one reflowable narration page."""
    text = Path(path).read_text(encoding="utf-8-sig")

    return [{"page": 1, "text": text}] if text.strip() else []

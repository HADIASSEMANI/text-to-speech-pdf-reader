import hashlib
from dataclasses import dataclass
from pathlib import Path

from reader.paths import cache_dir

CACHE_DIR = cache_dir()


@dataclass(frozen=True)
class CacheCleanupResult:
    removed_entries: int
    removed_bytes: int
    remaining_bytes: int


def create_cache_id(text: str, voice: str, speed: float = 1.0) -> str:

    content = f"{voice}:{speed}:{text}"

    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def mark_cache_used(audio_path: str):
    """Refresh an entry's timestamp so size cleanup behaves like LRU."""
    audio_file = Path(audio_path)

    for path in (audio_file, audio_file.with_suffix(".json")):
        try:
            if path.exists():
                path.touch()
        except OSError as error:
            print(f"Could not update cache timestamp for {path}: {error}")


def enforce_cache_limit(
    max_bytes: int,
    protected_audio_paths=(),
) -> CacheCleanupResult:
    """Remove least-recently-used generated audio until under ``max_bytes``.

    WAV files and their cue JSON files are treated as one entry. Protected
    entries are never removed, even when they alone exceed the configured
    limit.
    """
    max_bytes = max(0, int(max_bytes))
    protected_stems = {
        Path(path).stem
        for path in protected_audio_paths
        if path
    }

    entries = {}

    try:
        candidates = list(CACHE_DIR.iterdir())
    except FileNotFoundError:
        return CacheCleanupResult(0, 0, 0)
    except OSError as error:
        print(f"Could not inspect audio cache: {error}")
        return CacheCleanupResult(0, 0, 0)

    for path in candidates:
        if not path.is_file() or path.suffix.lower() not in {".wav", ".json"}:
            continue

        try:
            stat = path.stat()
        except OSError as error:
            print(f"Could not inspect cache file {path}: {error}")
            continue

        entry = entries.setdefault(
            path.stem,
            {"paths": [], "size": 0, "last_used": 0.0},
        )
        entry["paths"].append(path)
        entry["size"] += stat.st_size
        entry["last_used"] = max(entry["last_used"], stat.st_mtime)

    total_bytes = sum(entry["size"] for entry in entries.values())
    removed_entries = 0
    removed_bytes = 0

    if total_bytes <= max_bytes:
        return CacheCleanupResult(0, 0, total_bytes)

    oldest_first = sorted(
        entries.items(),
        key=lambda item: item[1]["last_used"],
    )

    for stem, entry in oldest_first:
        if total_bytes <= max_bytes:
            break

        if stem in protected_stems:
            continue

        entry_removed = 0
        audio_file = next(
            (
                path
                for path in entry["paths"]
                if path.suffix.lower() == ".wav"
            ),
            None,
        )

        # Keep the cue data when Windows still has the WAV locked. That way
        # a failed cleanup attempt cannot leave playable audio without its
        # highlighting metadata.
        if audio_file is not None:
            size = 0

            try:
                size = audio_file.stat().st_size
                audio_file.unlink()
            except FileNotFoundError:
                pass
            except OSError as error:
                print(f"Could not remove cache file {audio_file}: {error}")
                continue

            entry_removed += size

        for path in entry["paths"]:
            if path == audio_file:
                continue

            try:
                size = path.stat().st_size
                path.unlink()
            except FileNotFoundError:
                continue
            except OSError as error:
                print(f"Could not remove cache file {path}: {error}")
                continue

            entry_removed += size

        if entry_removed:
            removed_entries += 1
            removed_bytes += entry_removed
            total_bytes -= entry_removed

    if removed_entries:
        freed_mb = removed_bytes / (1024 * 1024)
        print(
            f"Removed {removed_entries} old audio cache entry/entries "
            f"and freed {freed_mb:.1f} MB."
        )

    return CacheCleanupResult(
        removed_entries,
        removed_bytes,
        total_bytes,
    )


def clear_all_cache() -> CacheCleanupResult:
    """Delete every generated WAV and cue file in the cache directory.

    Used by development builds on application exit so a run never inherits
    audio from an earlier one. Packaged builds keep their cache; see
    ``is_frozen`` in ``reader.paths``. Call this only once playback has shut
    down, or the player may still hold a file open.
    """
    removed_entries = 0
    removed_bytes = 0
    remaining_bytes = 0

    try:
        candidates = list(CACHE_DIR.iterdir())
    except FileNotFoundError:
        return CacheCleanupResult(0, 0, 0)
    except OSError as error:
        print(f"Could not inspect audio cache: {error}")
        return CacheCleanupResult(0, 0, 0)

    for path in candidates:
        if not path.is_file() or path.suffix.lower() not in {".wav", ".json"}:
            continue

        try:
            size = path.stat().st_size
            path.unlink()
        except FileNotFoundError:
            continue
        except OSError as error:
            # A file still held open survives the purge rather than failing
            # the shutdown. The next run reuses it, which is harmless.
            print(f"Could not remove cache file {path}: {error}")

            try:
                remaining_bytes += path.stat().st_size
            except OSError:
                pass

            continue

        removed_bytes += size

        if path.suffix.lower() == ".wav":
            removed_entries += 1

    if removed_entries or removed_bytes:
        freed_mb = removed_bytes / (1024 * 1024)
        print(
            f"Development build: cleared {removed_entries} cached segment(s) "
            f"and freed {freed_mb:.1f} MB."
        )

    return CacheCleanupResult(
        removed_entries,
        removed_bytes,
        remaining_bytes,
    )


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

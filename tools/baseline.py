"""Record how the reader narrates the fixture passages, today.

Two independent baselines:

``--text``   what the pipeline decides to say and where it breaks. Cheap,
             deterministic, and committed as goldens so later changes show up
             as a reviewable diff.

``--audio``  what Kokoro actually produces: generation speed, clip length,
             cue granularity, and the silence already present at each
             boundary. Written outside version control, because the point of
             comparison is listening to it.

Usage (from the repository root)::

    .venv/bin/python -m tools.baseline --text
    .venv/bin/python -m tools.baseline --text --update-golden
    .venv/bin/python -m tools.baseline --audio --speed 0.85
    .venv/bin/python -m tools.baseline --audio --passage headings lists
"""

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

from tools.passages import ALL_PASSAGES, Passage, get_passage
from tools.pipeline_dump import (
    build_pdf,
    pdf_pipeline_dump,
    text_pipeline_dump,
)

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent

GOLDEN_DIR = REPOSITORY_ROOT / "tests" / "fixtures" / "golden"
BASELINE_DIR = REPOSITORY_ROOT / "baseline"

# Anything quieter than this counts as silence when measuring the pauses
# Kokoro already produces. Chosen well below speech level and above the
# noise floor of the model's output.
SILENCE_FLOOR_DB = -45.0

# Shorter dips are within a normal word boundary and are not pauses.
MIN_GAP_SECONDS = 0.15


def selected_passages(names: list[str] | None) -> tuple[Passage, ...]:
    if not names:
        return ALL_PASSAGES

    return tuple(get_passage(name) for name in names)


# ----------------------------------------------------------------------
# text baseline
# ----------------------------------------------------------------------


def build_text_baseline(
    passages: tuple[Passage, ...],
    voice: str,
    speed: float,
    include_pdf: bool = True,
) -> dict:
    import tempfile

    results = {}

    for passage in passages:
        entry = {"text": text_pipeline_dump(passage, voice=voice, speed=speed)}

        if include_pdf:
            with tempfile.TemporaryDirectory() as directory:
                pdf_path = build_pdf(passage, Path(directory) / f"{passage.name}.pdf")

                entry["pdf"] = pdf_pipeline_dump(
                    passage,
                    pdf_path,
                    voice=voice,
                    speed=speed,
                )

        results[passage.name] = entry

    return results


def golden_path(passage_name: str) -> Path:
    return GOLDEN_DIR / f"{passage_name}.json"


def write_golden(name: str, entry: dict):
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)

    golden_path(name).write_text(
        json.dumps(entry, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def report_text_baseline(results: dict):
    print(f"{'passage':<20} {'segs':>5} {'pages':>18} {'faithful':>9}  notes")
    print("-" * 86)

    for name, entry in results.items():
        text = entry["text"]

        notes = []

        if not text["text_is_faithful"]:
            notes.append("TEXT CHANGED")

        pdf = entry.get("pdf")

        if pdf is not None:
            if pdf["segment_count"] != text["segment_count"]:
                notes.append(
                    f"pdf segs={pdf['segment_count']}"
                )

            if pdf["coverage"] < 0.99:
                notes.append(f"pdf coverage={pdf['coverage']:.1%}")

        print(
            f"{name:<20} "
            f"{text['segment_count']:>5} "
            f"{str(text['pages_covered']):>18} "
            f"{str(text['text_is_faithful']):>9}  "
            + ", ".join(notes)
        )


# ----------------------------------------------------------------------
# audio baseline
# ----------------------------------------------------------------------


def measure_silence(audio, samplerate: int) -> dict:
    """Locate the silence Kokoro already produces in a generated clip.

    Phase 4 adds pauses at paragraph boundaries. Adding them blind doubles
    whatever the model emitted on its own, so the existing silence is
    measured first.
    """
    import numpy as np

    samples = np.asarray(audio, dtype=np.float32).reshape(len(audio), -1)

    mono = samples.mean(axis=1)

    frame = max(1, int(samplerate * 0.01))

    usable = (len(mono) // frame) * frame

    if usable == 0:
        return {"leading": 0.0, "trailing": 0.0, "gaps": []}

    frames = mono[:usable].reshape(-1, frame)

    rms = np.sqrt(np.mean(np.square(frames), axis=1))

    peak = float(rms.max())

    if peak <= 0:
        return {"leading": 0.0, "trailing": 0.0, "gaps": []}

    floor = peak * (10 ** (SILENCE_FLOOR_DB / 20))

    loud = rms > floor

    if not loud.any():
        return {
            "leading": round(usable / samplerate, 3),
            "trailing": 0.0,
            "gaps": [],
        }

    indices = np.flatnonzero(loud)

    first, last = int(indices[0]), int(indices[-1])

    gaps = []

    run_start = None

    for position in range(first, last + 1):
        if not loud[position]:
            if run_start is None:
                run_start = position
            continue

        if run_start is not None:
            duration = (position - run_start) * frame / samplerate

            if duration >= MIN_GAP_SECONDS:
                gaps.append(
                    {
                        "at": round(run_start * frame / samplerate, 3),
                        "seconds": round(duration, 3),
                    }
                )

            run_start = None

    return {
        "leading": round(first * frame / samplerate, 3),
        "trailing": round((len(frames) - 1 - last) * frame / samplerate, 3),
        "gaps": gaps,
    }


def build_audio_baseline(
    passages: tuple[Passage, ...],
    voice: str,
    speed: float,
    output_dir: Path,
) -> dict:
    import numpy as np
    import soundfile as sf

    from reader.segmenter import create_segments
    from reader.tts import KokoroTTS
    from tools.pipeline_dump import passage_pages

    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Loading Kokoro (voice={voice}, speed={speed})...")

    load_started = time.perf_counter()

    tts = KokoroTTS(voice=voice, speed=speed)

    model_load_seconds = round(time.perf_counter() - load_started, 2)

    print(f"Model ready in {model_load_seconds}s\n")

    results = {
        "recorded": datetime.now().isoformat(timespec="seconds"),
        "voice": voice,
        "speed": speed,
        "model_load_seconds": model_load_seconds,
        "passages": {},
    }

    for passage in passages:
        segments = create_segments(
            passage_pages(passage),
            voice=voice,
            speed=speed,
        )

        entries = []

        for index, segment in enumerate(segments):
            target = output_dir / f"{passage.name}-{index:02d}.wav"

            started = time.perf_counter()

            cues = tts.generate(segment.text, str(target))

            generation_seconds = round(time.perf_counter() - started, 3)

            audio, samplerate = sf.read(target, dtype="float32", always_2d=True)

            audio_seconds = round(len(audio) / samplerate, 3)

            silence = measure_silence(audio, samplerate)

            cue_durations = [round(cue.end - cue.start, 3) for cue in cues]

            entry = {
                "index": index,
                "page": segment.page,
                "chars": len(segment.text),
                "audio_seconds": audio_seconds,
                "generation_seconds": generation_seconds,
                "realtime_factor": (
                    round(audio_seconds / generation_seconds, 2)
                    if generation_seconds
                    else None
                ),
                "cue_count": len(cues),
                "chars_per_cue": (
                    round(len(segment.text) / len(cues), 1) if cues else None
                ),
                "longest_cue_seconds": max(cue_durations) if cue_durations else 0.0,
                "silence": silence,
                "wav": target.name,
            }

            entries.append(entry)

            print(
                f"  {passage.name:<18} seg {index} "
                f"{entry['chars']:>5} chars  "
                f"{audio_seconds:>6.2f}s audio  "
                f"{generation_seconds:>6.2f}s gen  "
                f"{entry['realtime_factor']}x  "
                f"{len(cues)} cues  "
                f"lead {silence['leading']:.2f}s "
                f"tail {silence['trailing']:.2f}s "
                f"gaps {len(silence['gaps'])}"
            )

        results["passages"][passage.name] = {
            "guards": passage.guards,
            "segments": entries,
        }

    return results


def summarize_audio(results: dict):
    entries = [
        entry
        for passage in results["passages"].values()
        for entry in passage["segments"]
    ]

    if not entries:
        return

    total_audio = sum(entry["audio_seconds"] for entry in entries)
    total_generation = sum(entry["generation_seconds"] for entry in entries)

    gap_durations = [
        gap["seconds"]
        for entry in entries
        for gap in entry["silence"]["gaps"]
    ]

    print("\n" + "-" * 70)
    print(f"Clips                : {len(entries)}")
    print(f"Audio                : {total_audio:.1f}s")
    print(f"Generation           : {total_generation:.1f}s")
    print(
        f"Realtime factor      : "
        f"{total_audio / total_generation:.1f}x"
        if total_generation
        else "Realtime factor      : n/a"
    )
    print(
        f"Cues per clip        : "
        f"{sum(entry['cue_count'] for entry in entries) / len(entries):.1f}"
    )
    print(
        f"Longest cue          : "
        f"{max(entry['longest_cue_seconds'] for entry in entries):.2f}s"
    )
    print(
        f"Internal pauses      : {len(gap_durations)}"
        + (
            f"  (median {sorted(gap_durations)[len(gap_durations) // 2]:.2f}s,"
            f" max {max(gap_durations):.2f}s)"
            if gap_durations
            else ""
        )
    )
    print(
        f"Leading silence      : "
        f"{sum(e['silence']['leading'] for e in entries) / len(entries):.3f}s avg"
    )
    print(
        f"Trailing silence     : "
        f"{sum(e['silence']['trailing'] for e in entries) / len(entries):.3f}s avg"
    )


# ----------------------------------------------------------------------


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument("--text", action="store_true", help="run the text baseline")
    parser.add_argument("--audio", action="store_true", help="synthesize and measure")
    parser.add_argument(
        "--update-golden",
        action="store_true",
        help="rewrite the committed text goldens",
    )
    parser.add_argument("--passage", nargs="*", help="limit to these passages")
    parser.add_argument("--voice", default="af_heart")
    parser.add_argument("--speed", type=float, default=0.85)
    parser.add_argument("--no-pdf", action="store_true", help="skip the PDF round trip")
    parser.add_argument(
        "--out",
        default=None,
        help="audio baseline directory (default: baseline/<voice>-<speed>)",
    )

    arguments = parser.parse_args(argv)

    if not arguments.text and not arguments.audio:
        arguments.text = True

    passages = selected_passages(arguments.passage)

    if arguments.text:
        results = build_text_baseline(
            passages,
            voice=arguments.voice,
            speed=arguments.speed,
            include_pdf=not arguments.no_pdf,
        )

        report_text_baseline(results)

        if arguments.update_golden:
            for name, entry in results.items():
                write_golden(name, entry)

            print(f"\nWrote {len(results)} goldens to {GOLDEN_DIR}")

    if arguments.audio:
        output_dir = (
            Path(arguments.out)
            if arguments.out
            else BASELINE_DIR / f"{arguments.voice}-{arguments.speed}"
        )

        results = build_audio_baseline(
            passages,
            voice=arguments.voice,
            speed=arguments.speed,
            output_dir=output_dir,
        )

        (output_dir / "baseline.json").write_text(
            json.dumps(results, indent=2),
            encoding="utf-8",
        )

        summarize_audio(results)

        print(f"\nWrote {output_dir / 'baseline.json'}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

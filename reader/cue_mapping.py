"""Map speech cues to the displayed document, using Qt's UTF-16 positions."""

import re


def _normalized(text):
    # Kokoro normalizes whitespace, including typography spaces in MathML.
    # Retain source positions so matching never changes the displayed text.
    chars, positions = [], []
    for match in re.finditer(r"\S+|\s+", text):
        value = match.group()
        if value.isspace():
            chars.append(" ")
            positions.append(match.start())
        else:
            chars.extend(value)
            positions.extend(range(match.start(), match.end()))
    return "".join(chars), positions


def map_cues(segment):
    spoken = segment.spoken_text or segment.text
    normalized, positions = _normalized(spoken)
    spans = segment.speech_spans or [(0, len(spoken), 0, len(segment.text))]
    # Python counts astral characters once; Qt selections count two units.
    utf16 = [0]
    for character in segment.text:
        utf16.append(utf16[-1] + (2 if ord(character) > 0xFFFF else 1))
    offsets, cursor = [], 0
    for cue in segment.cues:
        needle = _normalized(cue.text)[0].strip()
        if not needle:
            continue
        start = normalized.find(needle, cursor)
        if start < 0:
            continue
        end = start + len(needle)
        speech_start, speech_end = positions[start], positions[end - 1] + 1
        ranges = []
        for ss, se, ds, de in spans:
            left, right = max(ss, speech_start), min(se, speech_end)
            if left >= right:
                continue
            if spoken[ss:se] == segment.text[ds:de]:
                ranges.append((ds + left - ss, ds + right - ss))
            else:
                # A verbalized equation maps to its full displayed block.
                ranges.append((ds, de))
        if ranges:
            offsets.append((cue, utf16[ranges[0][0]], utf16[ranges[-1][1]]))
        cursor = end
    return offsets

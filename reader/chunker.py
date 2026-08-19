def chunk_text(
    text: str,
    max_chars: int = 1500,
    min_chars: int = 200,
) -> list[str]:

    paragraphs = text.split("\n\n")

    chunks = []
    current = ""

    for paragraph in paragraphs:
        paragraph = paragraph.strip()

        if not paragraph:
            continue

        # A single PDF paragraph can be longer than max_chars. Split it at
        # word boundaries so one Kokoro request cannot become unexpectedly
        # large.
        if len(paragraph) > max_chars:
            words = paragraph.split()

            if current:
                chunks.append(current.strip())
                current = ""

            part = ""
            for word in words:
                candidate = f"{part} {word}".strip()

                if part and len(candidate) > max_chars:
                    chunks.append(part)
                    part = word
                else:
                    part = candidate

            if part:
                chunks.append(part)

            continue

        if len(current) + len(paragraph) + 2 > max_chars:

            if current:
                chunks.append(current.strip())

            current = paragraph

        else:
            if current:
                current += "\n\n"

            current += paragraph

    if current:
        chunks.append(current.strip())

    # Avoid creating a standalone audio segment for a short trailing or
    # single-paragraph fragment. Prefer the previous chunk when it fits;
    # otherwise append the fragment to the following chunk.
    merged = []

    for chunk in chunks:
        if (
            merged
            and len(chunk) < min_chars
            and len(merged[-1]) + len(chunk) + 2 <= max_chars
        ):
            merged[-1] += "\n\n" + chunk
        else:
            merged.append(chunk)

    index = 0
    while index < len(merged) - 1:
        if (
            len(merged[index]) < min_chars
            and len(merged[index]) + len(merged[index + 1]) + 2 <= max_chars
        ):
            merged[index + 1] = merged[index] + "\n\n" + merged[index + 1]
            del merged[index]
        else:
            index += 1

    return merged

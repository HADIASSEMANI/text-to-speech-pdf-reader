def chunk_text(
    text: str,
    max_chars: int = 1500
) -> list[str]:

    paragraphs = text.split("\n\n")

    chunks = []
    current = ""

    for paragraph in paragraphs:
        paragraph = paragraph.strip()

        if not paragraph:
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

    return chunks
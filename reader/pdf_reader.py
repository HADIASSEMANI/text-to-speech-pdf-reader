import pymupdf as fitz
from reader.models import TextBlock


def extract_blocks(pdf_path: str) -> list[list[TextBlock]]:

    document = fitz.open(pdf_path)

    pages: list[list[TextBlock]] = []

    for page_number, page in enumerate(document):

        page_width = page.rect.width
        page_height = page.rect.height

        data = page.get_text("dict", sort=True)

        page_blocks: list[TextBlock] = []

        for block in data["blocks"]:

            # Ignore image blocks
            if block.get("type") != 0:
                continue

            lines = block.get("lines", [])

            text_parts = []
            font_sizes = []

            for line in lines:

                for span in line.get("spans", []):

                    text = span.get("text", "")

                    if text.strip():
                        text_parts.append(text)

                    size = span.get("size")

                    if size:
                        font_sizes.append(size)

            text = " ".join(text_parts).strip()

            if not text:
                continue

            x0, y0, x1, y1 = block["bbox"]

            average_font_size = sum(font_sizes) / len(font_sizes) if font_sizes else 0

            page_blocks.append(
                TextBlock(
                    page=page_number + 1,
                    text=text,
                    x0=x0,
                    y0=y0,
                    x1=x1,
                    y1=y1,
                    font_size=average_font_size,
                    page_width=page_width,
                    page_height=page_height,
                )
            )

        pages.append(page_blocks)

    document.close()

    return pages

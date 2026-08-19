import pymupdf as fitz

def extract_pages(pdf_path: "../pdfs/introduction_to_the_new_mainframe.pdf") -> list[str]:
    document = fitz.open(pdf_path)

    return [
        {
            "page": page.number + 1,
            "text": page.get_text()
        }
        for page_number, page in enumerate(document)
    ]
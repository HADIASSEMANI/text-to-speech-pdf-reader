import re

def clean_text(text: str) -> str:
     # Collapse excessive spaces
    text = re.sub(r"[ \t]+", " ", text)

    # Collapse excessive newlines
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Join some line-break artifacts
    text = re.sub(r"(?<![.!?:])\n(?=[a-z])", " ", text)
    
    return text.strip()
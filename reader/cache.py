import hashlib


def create_cache_id(
    text: str,
    voice: str,
    speed: float = 1.0
) -> str:

    content = f"{voice}:{speed}:{text}"

    return hashlib.sha256(
        content.encode("utf-8")
    ).hexdigest()[:16]
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from reader.database import get_connection


@dataclass
class ProgressAnchor:
    """Where the listener was, described by what was being read.

    A segment index is only meaningful while a book segments the same way,
    and the cache id additionally encodes voice and speed. Recording all
    three means a saved position survives a settings change or a change to
    how the book is chunked, instead of silently landing somewhere else.
    """

    cache_id: str | None = None
    page: int | None = None
    text: str | None = None

    # Identifier of the first source block in the passage, when the format
    # provides one. EPUB does; a rendered PDF does not.
    source_id: str | None = None

    # Enough of the passage to identify it again, short enough to store.
    EXCERPT_CHARS = 160

    @classmethod
    def from_segment(cls, segment) -> "ProgressAnchor":
        source_ids = getattr(segment, "source_ids", None) or []

        return cls(
            cache_id=segment.cache_id,
            page=segment.page,
            text=" ".join(segment.text.split())[: cls.EXCERPT_CHARS],
            source_id=source_ids[0] if source_ids else None,
        )


@dataclass
class BookProgress:
    id: int
    path: str
    title: str
    current_segment: int
    playback_position: float
    last_opened: str | None = None
    is_new: bool = False
    anchor: ProgressAnchor = field(default_factory=ProgressAnchor)


def get_or_create_book(
    pdf_path: str
) -> BookProgress:

    resolved_path = str(
        Path(pdf_path).resolve()
    )

    title = Path(
        pdf_path
    ).stem

    now = datetime.now().isoformat(timespec="seconds")

    with get_connection() as connection:

        row = connection.execute(
            """
            SELECT *
            FROM books
            WHERE path = ?
            """,
            (resolved_path,)
        ).fetchone()

        if row is None:

            cursor = connection.execute(
                """
                INSERT INTO books (
                    path,
                    title,
                    last_opened
                )
                VALUES (?, ?, ?)
                """,
                (
                    resolved_path,
                    title,
                    now,
                )
            )

            connection.commit()

            return BookProgress(
                id=cursor.lastrowid,
                path=resolved_path,
                title=title,
                current_segment=0,
                playback_position=0.0,
                last_opened=now,
                is_new=True,
            )

        connection.execute(
            """
            UPDATE books
            SET last_opened = ?
            WHERE id = ?
            """,
            (now, row["id"]),
        )
        connection.commit()

        return BookProgress(
            id=row["id"],
            path=row["path"],
            title=row["title"],
            current_segment=row[
                "current_segment"
            ],
            playback_position=row[
                "playback_position"
            ],
            last_opened=now,
            is_new=False,
            anchor=_read_anchor(row),
        )


def get_recent_books(limit: int = 10) -> list[BookProgress]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT
                id,
                path,
                title,
                current_segment,
                playback_position,
                last_opened
            FROM books
            ORDER BY last_opened DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    return [
        BookProgress(
            id=row["id"],
            path=row["path"],
            title=row["title"],
            current_segment=row["current_segment"],
            playback_position=row["playback_position"],
            last_opened=row["last_opened"],
        )
        for row in rows
    ]

def _read_anchor(row) -> ProgressAnchor:
    keys = row.keys()

    return ProgressAnchor(
        cache_id=row["anchor_cache_id"] if "anchor_cache_id" in keys else None,
        page=row["anchor_page"] if "anchor_page" in keys else None,
        text=row["anchor_text"] if "anchor_text" in keys else None,
        source_id=(
            row["anchor_source_id"] if "anchor_source_id" in keys else None
        ),
    )


def save_progress(
    book_id: int,
    segment_index: int,
    playback_position: float = 0.0,
    anchor: ProgressAnchor | None = None,
):
    """Record where the listener is.

    The anchor is written alongside the index whenever the caller knows the
    segment. Callers that only have an index still work; they just leave the
    previous anchor in place rather than clearing it, because a stale anchor
    is more useful than none when segmentation later changes.
    """

    with get_connection() as connection:

        if anchor is None:
            connection.execute(
                """
                UPDATE books

                SET
                    current_segment = ?,
                    playback_position = ?,
                    last_opened = CURRENT_TIMESTAMP

                WHERE id = ?
                """,
                (
                    segment_index,
                    playback_position,
                    book_id
                )
            )

        else:
            connection.execute(
                """
                UPDATE books

                SET
                    current_segment = ?,
                    playback_position = ?,
                    anchor_cache_id = ?,
                    anchor_page = ?,
                    anchor_text = ?,
                    anchor_source_id = ?,
                    last_opened = CURRENT_TIMESTAMP

                WHERE id = ?
                """,
                (
                    segment_index,
                    playback_position,
                    anchor.cache_id,
                    anchor.page,
                    anchor.text,
                    anchor.source_id,
                    book_id
                )
            )

        connection.commit()


def resolve_resume_point(
    progress: BookProgress,
    segments: list,
) -> tuple[int, float]:
    """Find where to start reading, and from how many seconds in.

    Tried in order of how much each source of truth actually guarantees:

    1. A segment with the same cache id is the same text at the same voice
       and speed, so its saved second offset is still valid.
    2. A source identifier points at the block in the document it came from,
       which no change to chunking can move.
    3. Matching the recorded excerpt finds the passage after the book has
       been resegmented or the narration settings changed. The offset within
       it no longer means anything, so reading restarts at the passage.
    4. The recorded page is a coarser version of the same idea.
    5. The stored index is the last resort, and only when it is in range.
    """
    if not segments:
        return 0, 0.0

    anchor = progress.anchor

    if anchor.cache_id:
        for index, segment in enumerate(segments):
            if segment.cache_id == anchor.cache_id:
                return index, max(0.0, progress.playback_position)

    # A source identifier survives re-extraction and re-chunking, so it is
    # tried before matching on the text itself.
    if anchor.source_id:
        for index, segment in enumerate(segments):
            if anchor.source_id in getattr(segment, "source_ids", ()):
                return index, 0.0

    if anchor.text:
        excerpt = " ".join(anchor.text.split())

        for index, segment in enumerate(segments):
            if excerpt and excerpt in " ".join(segment.text.split()):
                return index, 0.0

    if anchor.page:
        for index, segment in enumerate(segments):
            if segment.page >= anchor.page:
                return index, 0.0

    index = progress.current_segment

    if 0 <= index < len(segments):
        return index, 0.0

    return 0, 0.0


def remove_book(path: str):
    """Drop a book whose file no longer exists from the library."""
    resolved_path = str(Path(path).resolve())

    with get_connection() as connection:
        connection.execute(
            """
            DELETE FROM books
            WHERE path = ? OR path = ?
            """,
            (resolved_path, path),
        )

        connection.commit()

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from reader.database import get_connection


@dataclass
class BookProgress:
    id: int
    path: str
    title: str
    current_segment: int
    playback_position: float
    last_opened: str | None = None
    is_new: bool = False


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

def save_progress(
    book_id: int,
    segment_index: int,
    playback_position: float = 0.0
):

    with get_connection() as connection:

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

        connection.commit()


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

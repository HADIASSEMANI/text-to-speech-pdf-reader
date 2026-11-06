import sqlite3

from reader.paths import database_path


DATABASE_PATH = database_path()


def get_connection() -> sqlite3.Connection:
    DATABASE_PATH.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    connection = sqlite3.connect(
        DATABASE_PATH
    )

    connection.row_factory = sqlite3.Row

    return connection


# Ordered schema steps, applied once each and tracked in PRAGMA user_version.
#
# The library database is user data that outlives any release, so it is
# migrated rather than recreated. Append new steps; never edit a step that
# has shipped, because databases in the field have already run it.
MIGRATIONS: list[list[str]] = [
    # 1 - original schema
    [
        """
        CREATE TABLE IF NOT EXISTS books (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            path TEXT NOT NULL UNIQUE,
            title TEXT NOT NULL,

            current_segment INTEGER NOT NULL DEFAULT 0,

            playback_position REAL NOT NULL DEFAULT 0,

            last_opened TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
    ],
    # 2 - resume anchors
    #
    # A saved segment index only means something while the book segments the
    # same way. Chunking changes, and so do voice and speed, which are part
    # of a segment's cache id. These columns let a saved position be found
    # again by what was being read rather than by where it happened to fall.
    [
        "ALTER TABLE books ADD COLUMN anchor_cache_id TEXT",
        "ALTER TABLE books ADD COLUMN anchor_page INTEGER",
        "ALTER TABLE books ADD COLUMN anchor_text TEXT",
    ],
    # 3 - source anchors
    #
    # Structured extraction gives every block a stable identifier from the
    # document it came from. That outlives any change to chunking, so it is
    # the most durable thing a saved position can point at.
    [
        "ALTER TABLE books ADD COLUMN anchor_source_id TEXT",
    ],
]


def _column_names(connection: sqlite3.Connection, table: str) -> set[str]:
    return {
        row["name"]
        for row in connection.execute(f"PRAGMA table_info({table})")
    }


def initialize_database():
    with get_connection() as connection:
        version = connection.execute("PRAGMA user_version").fetchone()[0]

        # Databases created before migrations existed report version 0 but
        # already have the original table. Detect that and adopt version 1
        # so the first real migration is not skipped or repeated.
        if version == 0 and _column_names(connection, "books"):
            version = 1

        for step, statements in enumerate(MIGRATIONS, start=1):
            if step <= version:
                continue

            for statement in statements:
                connection.execute(statement)

            version = step

        connection.execute(f"PRAGMA user_version = {version}")

        connection.commit()

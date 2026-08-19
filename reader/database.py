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


def initialize_database():
    with get_connection() as connection:

        connection.execute("""
            CREATE TABLE IF NOT EXISTS books (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                path TEXT NOT NULL UNIQUE,
                title TEXT NOT NULL,

                current_segment INTEGER NOT NULL DEFAULT 0,

                playback_position REAL NOT NULL DEFAULT 0,

                last_opened TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        connection.commit()
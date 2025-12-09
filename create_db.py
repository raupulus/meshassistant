from pathlib import Path
import sqlite3

# Archivo de base de datos SQLite (en el raíz del proyecto)
DATABASE_FILE = Path(__file__).resolve().parent / "database.sql"


def _execute_schema(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()

    # Usamos comillas dobles para columnas con palabras reservadas ("from", "to")
    cur.executescript(
        """
        PRAGMA journal_mode=WAL;
        PRAGMA synchronous=NORMAL;

        CREATE TABLE IF NOT EXISTS chistes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            "from" TEXT,
            content TEXT NOT NULL,
            need_approve INTEGER NOT NULL DEFAULT 0,
            need_upload INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS traces (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            "from" TEXT NOT NULL,
            "to" TEXT NOT NULL,
            data_raw TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS pings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            "from" TEXT NOT NULL,
            "to" TEXT NOT NULL,
            data_raw TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            start_at TEXT NULL,
            end_at TEXT NULL,
            period TEXT NOT NULL,
            content TEXT NOT NULL,
            send_at TEXT NULL
        );

        CREATE TABLE IF NOT EXISTS agenda (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            node_id TEXT NOT NULL,
            content TEXT NOT NULL,
            moment TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_agenda_node_moment ON agenda(node_id, moment);
        """
    )
    conn.commit()


def ensure_database() -> Path:
    """Crea la base de datos si no existe y devuelve la ruta al archivo."""
    if not DATABASE_FILE.exists():
        DATABASE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(DATABASE_FILE) as conn:
            _execute_schema(conn)

    return DATABASE_FILE


if __name__ == "__main__":
    path = ensure_database()
    print(f"Base de datos lista en: {path}")

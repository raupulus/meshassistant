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
            from_name TEXT,
            hops INTEGER,
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

        -- Nodo: persistencia de nodos de la red
        CREATE TABLE IF NOT EXISTS nodes (
            node_id TEXT PRIMARY KEY,
            name TEXT,
            num INTEGER,
            short_name TEXT,
            mac_addr TEXT,
            hw_model INTEGER,
            is_favorite INTEGER,
            snr REAL,
            rssi REAL,
            public_key TEXT,
            hops INTEGER,
            hop_start INTEGER,
            uptime INTEGER,
            via_mqtt INTEGER,
            last_heard INTEGER,
            updated_at TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_nodes_short_name ON nodes(short_name);
        CREATE INDEX IF NOT EXISTS idx_nodes_num ON nodes(num);
        """
    )
    conn.commit()

    # Idempotent migration: ensure new columns exist in existing databases
    def _has_column(table: str, column: str) -> bool:
        cur2 = conn.execute(f'PRAGMA table_info({table})')
        cols = [r[1] for r in cur2.fetchall()]  # r[1] is name
        return column in cols

    # Ensure columns in pings: from_name (TEXT), hops (INTEGER)
    if not _has_column('pings', 'from_name'):
        conn.execute('ALTER TABLE pings ADD COLUMN from_name TEXT')
    if not _has_column('pings', 'hops'):
        conn.execute('ALTER TABLE pings ADD COLUMN hops INTEGER')
    conn.commit()


def ensure_database() -> Path:
    """Asegura que la BD existe y aplica el esquema (idempotente)."""
    if not DATABASE_FILE.exists():
        DATABASE_FILE.parent.mkdir(parents=True, exist_ok=True)
        # Crear archivo vacío primero
        with sqlite3.connect(DATABASE_FILE):
            pass

    # Siempre aplicar esquema para asegurar tablas nuevas
    with sqlite3.connect(DATABASE_FILE) as conn:
        _execute_schema(conn)

    return DATABASE_FILE


if __name__ == "__main__":
    path = ensure_database()
    print(f"Base de datos lista en: {path}")

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
            need_upload INTEGER NOT NULL DEFAULT 0,
            chiste_id INTEGER NULL
        );

        CREATE TABLE IF NOT EXISTS traces (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            "from" TEXT NULL,
            "to" TEXT NOT NULL,
            data_raw TEXT NULL,
            status TEXT NULL,        -- 'pending' | 'done' | 'error'
            created_at TEXT NULL,    -- en cola
            updated_at TEXT NULL,
            hops INTEGER NULL,
            hops_back INTEGER NULL,
            -- Enriquecimiento de trace: destino y hasta 7 saltos
            to_name TEXT NULL,
            to_name_short TEXT NULL,
            hop1_id TEXT NULL, hop1_name TEXT NULL, hop1_name_short TEXT NULL, hop1_snr REAL NULL, hop1_rssi REAL NULL,
            hop2_id TEXT NULL, hop2_name TEXT NULL, hop2_name_short TEXT NULL, hop2_snr REAL NULL, hop2_rssi REAL NULL,
            hop3_id TEXT NULL, hop3_name TEXT NULL, hop3_name_short TEXT NULL, hop3_snr REAL NULL, hop3_rssi REAL NULL,
            hop4_id TEXT NULL, hop4_name TEXT NULL, hop4_name_short TEXT NULL, hop4_snr REAL NULL, hop4_rssi REAL NULL,
            hop5_id TEXT NULL, hop5_name TEXT NULL, hop5_name_short TEXT NULL, hop5_snr REAL NULL, hop5_rssi REAL NULL,
            hop6_id TEXT NULL, hop6_name TEXT NULL, hop6_name_short TEXT NULL, hop6_snr REAL NULL, hop6_rssi REAL NULL,
            hop7_id TEXT NULL, hop7_name TEXT NULL, hop7_name_short TEXT NULL, hop7_snr REAL NULL, hop7_rssi REAL NULL,
            -- Hops de regreso (hasta 7)
            hop_return1_id TEXT NULL, hop_return1_name TEXT NULL, hop_return1_name_short TEXT NULL, hop_return1_snr REAL NULL, hop_return1_rssi REAL NULL,
            hop_return2_id TEXT NULL, hop_return2_name TEXT NULL, hop_return2_name_short TEXT NULL, hop_return2_snr REAL NULL, hop_return2_rssi REAL NULL,
            hop_return3_id TEXT NULL, hop_return3_name TEXT NULL, hop_return3_name_short TEXT NULL, hop_return3_snr REAL NULL, hop_return3_rssi REAL NULL,
            hop_return4_id TEXT NULL, hop_return4_name TEXT NULL, hop_return4_name_short TEXT NULL, hop_return4_snr REAL NULL, hop_return4_rssi REAL NULL,
            hop_return5_id TEXT NULL, hop_return5_name TEXT NULL, hop_return5_name_short TEXT NULL, hop_return5_snr REAL NULL, hop_return5_rssi REAL NULL,
            hop_return6_id TEXT NULL, hop_return6_name TEXT NULL, hop_return6_name_short TEXT NULL, hop_return6_snr REAL NULL, hop_return6_rssi REAL NULL,
            hop_return7_id TEXT NULL, hop_return7_name TEXT NULL, hop_return7_name_short TEXT NULL, hop_return7_snr REAL NULL, hop_return7_rssi REAL NULL
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

        -- Control de tareas periódicas
        CREATE TABLE IF NOT EXISTS tasks_control (
            name TEXT PRIMARY KEY,
            last_run_at TEXT,
            extra TEXT
        );

        -- Tablas antiguas de control de traces eliminadas del esquema
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

    # Ensure new column in chistes: chiste_id
    if not _has_column('chistes', 'chiste_id'):
        conn.execute('ALTER TABLE chistes ADD COLUMN chiste_id INTEGER NULL')
        conn.commit()

    # Create indexes if not exist
    cur.execute('CREATE INDEX IF NOT EXISTS idx_chistes_need_upload ON chistes(need_upload)')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_chistes_need_approve ON chistes(need_approve)')
    cur.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_chistes_chiste_id ON chistes(chiste_id)')
    # Índices para optimizar cola y consultas de traces
    cur.execute('CREATE INDEX IF NOT EXISTS idx_traces_status_created ON traces(status, created_at)')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_traces_to_updated ON traces("to", updated_at)')
    conn.commit()

    # Migración idempotente para adaptar la tabla traces existente
    # - Añadir columnas status, created_at, updated_at si faltan
    # - Permitir NULL en "from" y data_raw (si antes eran NOT NULL -> rebuild)
    info_rows = conn.execute('PRAGMA table_info(traces)').fetchall()
    colnames = [r[1] for r in info_rows]

    needs_rebuild = False
    if 'status' not in colnames or 'created_at' not in colnames or 'updated_at' not in colnames:
        needs_rebuild = True
    else:
        cols = {r[1]: r for r in info_rows}
        # r[3] -> notnull flag (1 si NOT NULL)
        if ('from' in cols and cols['from'][3] == 1) or ('data_raw' in cols and cols['data_raw'][3] == 1):
            needs_rebuild = True

    if needs_rebuild:
        cur.executescript(
            """
            BEGIN TRANSACTION;
            CREATE TABLE IF NOT EXISTS traces_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                "from" TEXT NULL,
                "to" TEXT NOT NULL,
                data_raw TEXT NULL,
                status TEXT NULL,
                created_at TEXT NULL,
                updated_at TEXT NULL,
                hops INTEGER NULL,
                hops_back INTEGER NULL,
                to_name TEXT NULL,
                to_name_short TEXT NULL,
                hop1_id TEXT NULL, hop1_name TEXT NULL, hop1_name_short TEXT NULL, hop1_snr REAL NULL, hop1_rssi REAL NULL,
                hop2_id TEXT NULL, hop2_name TEXT NULL, hop2_name_short TEXT NULL, hop2_snr REAL NULL, hop2_rssi REAL NULL,
                hop3_id TEXT NULL, hop3_name TEXT NULL, hop3_name_short TEXT NULL, hop3_snr REAL NULL, hop3_rssi REAL NULL,
                hop4_id TEXT NULL, hop4_name TEXT NULL, hop4_name_short TEXT NULL, hop4_snr REAL NULL, hop4_rssi REAL NULL,
                hop5_id TEXT NULL, hop5_name TEXT NULL, hop5_name_short TEXT NULL, hop5_snr REAL NULL, hop5_rssi REAL NULL,
                hop6_id TEXT NULL, hop6_name TEXT NULL, hop6_name_short TEXT NULL, hop6_snr REAL NULL, hop6_rssi REAL NULL,
                hop7_id TEXT NULL, hop7_name TEXT NULL, hop7_name_short TEXT NULL, hop7_snr REAL NULL, hop7_rssi REAL NULL,
                hop_return1_id TEXT NULL, hop_return1_name TEXT NULL, hop_return1_name_short TEXT NULL, hop_return1_snr REAL NULL, hop_return1_rssi REAL NULL,
                hop_return2_id TEXT NULL, hop_return2_name TEXT NULL, hop_return2_name_short TEXT NULL, hop_return2_snr REAL NULL, hop_return2_rssi REAL NULL,
                hop_return3_id TEXT NULL, hop_return3_name TEXT NULL, hop_return3_name_short TEXT NULL, hop_return3_snr REAL NULL, hop_return3_rssi REAL NULL,
                hop_return4_id TEXT NULL, hop_return4_name TEXT NULL, hop_return4_name_short TEXT NULL, hop_return4_snr REAL NULL, hop_return4_rssi REAL NULL,
                hop_return5_id TEXT NULL, hop_return5_name TEXT NULL, hop_return5_name_short TEXT NULL, hop_return5_snr REAL NULL, hop_return5_rssi REAL NULL,
                hop_return6_id TEXT NULL, hop_return6_name TEXT NULL, hop_return6_name_short TEXT NULL, hop_return6_snr REAL NULL, hop_return6_rssi REAL NULL,
                hop_return7_id TEXT NULL, hop_return7_name TEXT NULL, hop_return7_name_short TEXT NULL, hop_return7_snr REAL NULL, hop_return7_rssi REAL NULL
            );
            INSERT INTO traces_new (id, "from", "to", data_raw)
            SELECT id, "from", "to", data_raw FROM traces;
            DROP TABLE traces;
            ALTER TABLE traces_new RENAME TO traces;
            COMMIT;
            """
        )
        cur.execute('CREATE INDEX IF NOT EXISTS idx_traces_status_created ON traces(status, created_at)')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_traces_to_updated ON traces("to", updated_at)')
        conn.commit()

    # Asegurar columnas de enriquecimiento en traces (idempotente, para BDs existentes sin rebuild)
    enrichment_cols = [
        'hops', 'hops_back', 'to_name', 'to_name_short',
    ] + [
        f'hop{i}_id' for i in range(1, 8)
    ] + [
        f'hop{i}_name' for i in range(1, 8)
    ] + [
        f'hop{i}_name_short' for i in range(1, 8)
    ] + [
        f'hop{i}_snr' for i in range(1, 8)
    ] + [
        f'hop{i}_rssi' for i in range(1, 8)
    ] + [
        f'hop_return{i}_id' for i in range(1, 8)
    ] + [
        f'hop_return{i}_name' for i in range(1, 8)
    ] + [
        f'hop_return{i}_name_short' for i in range(1, 8)
    ] + [
        f'hop_return{i}_snr' for i in range(1, 8)
    ] + [
        f'hop_return{i}_rssi' for i in range(1, 8)
    ]

    for col in enrichment_cols:
        if not _has_column('traces', col):
            # Tipos según sufijo
            if col.endswith('_snr') or col.endswith('_rssi'):
                conn.execute(f'ALTER TABLE traces ADD COLUMN {col} REAL NULL')
            else:
                conn.execute(f'ALTER TABLE traces ADD COLUMN {col} TEXT NULL')
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

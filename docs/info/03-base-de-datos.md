# 03 · Base de datos (SQLite)

## Motor y fichero

- **Motor:** SQLite (módulo `sqlite3` de la stdlib). **No** PostgreSQL.
- **Fichero:** `database.sql` en la raíz del proyecto (definido en `create_db.py`,
  `DATABASE_FILE`). Genera además `database.sql-wal` y `database.sql-shm`.
- **Modo:** `PRAGMA journal_mode=WAL` y `PRAGMA synchronous=NORMAL` (mejor
  concurrencia lectura/escritura entre `main.py` y `cron_tasks.py`).
- **Conexión:** `Database._connect()` usa `row_factory = sqlite3.Row` (acceso por
  nombre de columna).

`database.sql*` están en `.gitignore`: **no se versionan**.

## Creación y migración

`create_db.py::ensure_database()` crea el fichero si no existe y aplica el esquema
con `CREATE TABLE IF NOT EXISTS`. Además realiza **migraciones idempotentes**:

- Comprueba columnas con `PRAGMA table_info(<tabla>)` antes de hacer `ALTER TABLE`.
- Reconstruye `traces` (patrón *table rebuild*) si faltan columnas clave
  (`status`, `created_at`, `updated_at`) o si `"from"`/`data_raw` eran `NOT NULL`.
- Crea índices con `CREATE INDEX IF NOT EXISTS`.

`main.py` llama a `ensure_database()` al arrancar; también puede ejecutarse a mano:
`python3 create_db.py`.

## Tablas

### `nodes` — nodos de la malla
| Columna | Tipo | Notas |
|---|---|---|
| `node_id` | TEXT PK | ID Meshtastic (`!xxxxxxxx`). |
| `name`, `short_name` | TEXT | Nombre largo/corto. |
| `num` | INTEGER | Número de nodo. |
| `mac_addr` | TEXT | MAC. |
| `hw_model` | INTEGER | Modelo de hardware. |
| `is_favorite` | INTEGER | 0/1. |
| `snr`, `rssi` | REAL | Calidad de señal. |
| `public_key` | TEXT | Clave pública. |
| `hops`, `hop_start` | INTEGER | Saltos. |
| `uptime` | INTEGER | Uptime reportado. |
| `via_mqtt` | INTEGER | 0/1 (si llega por MQTT). |
| `last_heard` | INTEGER | Último contacto. |
| `updated_at` | TEXT | ISO 8601. |

Índices: `idx_nodes_short_name`, `idx_nodes_num`.

### `pings` — histórico de pings
| Columna | Tipo | Notas |
|---|---|---|
| `id` | INTEGER PK | |
| `"from"` | TEXT | Nodo origen (entre comillas, palabra reservada). |
| `"to"` | TEXT | Destino. |
| `from_name` | TEXT | Nombre del origen. |
| `hops` | INTEGER | Saltos. |
| `data_raw` | TEXT | JSON con metadatos del ping. |

### `traces` — cola y resultado de traceroutes
Hace de **cola** (`status='pending'`) y de **resultado** a la vez.

| Columna | Tipo | Notas |
|---|---|---|
| `id` | INTEGER PK | |
| `"from"` | TEXT NULL | `local` tras procesar. |
| `"to"` | TEXT | Nodo destino del trace. |
| `data_raw` | TEXT NULL | Texto completo del trace (o mensaje de error). |
| `status` | TEXT | `pending` \| `done` \| `error`. |
| `created_at` | TEXT | Encolado. |
| `updated_at` | TEXT | Procesado. |
| `hops`, `hops_back` | INTEGER | Nº de saltos ida/vuelta. |
| `to_name`, `to_name_short` | TEXT | Nombres del destino. |
| `hop1_*` … `hop7_*` | TEXT/REAL | Hasta 7 saltos de ida: `id`, `name`, `name_short`, `snr`, `rssi`. |
| `hop_return1_*` … `hop_return7_*` | TEXT/REAL | Hasta 7 saltos de vuelta. |

Índices: `idx_traces_status_created`, `idx_traces_to_updated`.

### `chistes`
| Columna | Tipo | Notas |
|---|---|---|
| `id` | INTEGER PK | |
| `"from"` | TEXT | Autor/origen. |
| `content` | TEXT NOT NULL | Texto del chiste. |
| `need_approve` | INTEGER | 0/1 — pendiente de aprobación. |
| `need_upload` | INTEGER | 0/1 — pendiente de subir a la API. |
| `chiste_id` | INTEGER NULL | ID en la API externa (único). |

Índices: `idx_chistes_need_upload`, `idx_chistes_need_approve`,
`idx_chistes_chiste_id` (UNIQUE).

### `aemet` — histórico de alertas
| Columna | Tipo | Notas |
|---|---|---|
| `id` | INTEGER PK | |
| `province` | TEXT | Provincia/CCAA. |
| `data_raw` | TEXT NOT NULL | Mensaje breve (ES) extraído del CAP. |
| `message` | TEXT NULL | Texto a publicar (ES). |
| `data_hash` | TEXT UNIQUE | SHA-256 para deduplicar. |
| `created_at` | TEXT | |
| `published` | INTEGER | 0/1. |
| `published_at` | TEXT NULL | |

### `agenda` — avisos programados por nodo
| Columna | Tipo | Notas |
|---|---|---|
| `id` | INTEGER PK | |
| `node_id` | TEXT NOT NULL | Nodo destinatario. |
| `content` | TEXT NOT NULL | Mensaje. |
| `moment` | TEXT NOT NULL | Momento (ISO 8601). |

Índice: `idx_agenda_node_moment`.

### `queue` — cola de publicaciones programadas (parcial)
| Columna | Tipo | Notas |
|---|---|---|
| `id` | INTEGER PK | |
| `start_at`, `end_at` | TEXT NULL | Ventana. |
| `period` | TEXT NOT NULL | Periodicidad. |
| `content` | TEXT NOT NULL | Mensaje. |
| `send_at` | TEXT NULL | Próximo envío. |

> `Database.get_next_in_queue()` es todavía un **TODO**.

### `tasks_control` — control de tareas periódicas
| Columna | Tipo | Notas |
|---|---|---|
| `name` | TEXT PK | Identificador de la tarea (p. ej. `chiste_download`, `aemet_fetch`, `aemet_publish_ch_6`). |
| `last_run_at` | TEXT | Última ejecución (ISO). |
| `extra` | TEXT | Libre. |

### `commands_sent` — log de comandos recibidos
| Columna | Tipo | Notas |
|---|---|---|
| `id` | INTEGER PK | |
| `node_id` | TEXT | Nodo que envía. |
| `command` | TEXT | Comando sin prefijo. |
| `parameters` | TEXT NULL | Reservado. |
| `message` | TEXT | Texto posterior al comando. |
| `created_at` | TEXT | |

## Palabras reservadas

`from` y `to` son palabras reservadas de SQL. En todas las queries van **entre
comillas dobles**: `"from"`, `"to"`. Mantener esta convención al añadir queries.

## Acceso

Todo el acceso a datos está centralizado en `Models/Database.py`. Ver
[06-modelo-database.md](06-modelo-database.md) para la API.

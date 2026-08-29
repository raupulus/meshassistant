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
| `role` | INTEGER | Rol oficial Meshtastic (`2=ROUTER`, `4=REPEATER`, `9=ROUTER_LATE`). |
| `is_favorite` | INTEGER | 0/1. |
| `snr`, `rssi` | REAL | Calidad de señal. |
| `public_key` | TEXT | Clave pública. |
| `hops`, `hop_start` | INTEGER | Saltos. |
| `uptime` | INTEGER | Uptime reportado. |
| `via_mqtt` | INTEGER | 0/1 (si llega por MQTT). |
| `battery` | INTEGER NULL | Nivel de batería reportado (0-100%). |
| `voltage` | REAL NULL | Voltaje de batería (V). |
| `last_heard` | INTEGER | Último contacto (epoch). |
| `traces_detected` | INTEGER | Contador de traceroutes emitidos y detectados en la malla por este nodo. |
| `created_at` | TEXT | Fecha y hora en que fue descubierto por primera vez. |
| `updated_at` | TEXT | ISO 8601 de última actualización. |

Índices: `idx_nodes_short_name`, `idx_nodes_num`, `idx_nodes_role`.

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

### `aemet_weather` — predicción de texto provincial / municipal
| Columna | Tipo | Notas |
|---|---|---|
| `id` | INTEGER PK | |
| `scope` | TEXT | `province` \| `city`. |
| `province` | TEXT NULL | Nombre de provincia. |
| `province_code` | TEXT NULL | Código INE de 2 dígitos. |
| `city` | TEXT NULL | Nombre de municipio. |
| `city_code` | TEXT NULL | Código INE de 5 dígitos. |
| `day` | TEXT | `hoy` \| `manana`. |
| `content` | TEXT NOT NULL | Texto listo para responder. |
| `data_raw` | TEXT NULL | Texto original completo. |
| `created_at` | TEXT | ISO 8601. |

### `aemet_forecast_daily` — predicción estructurada multi-día (7 días)
| Columna | Tipo | Notas |
|---|---|---|
| `id` | INTEGER PK | |
| `city_code` | TEXT NOT NULL | Código INE de 5 dígitos. |
| `city_name` | TEXT NOT NULL | Nombre del municipio (ej. Chipiona). |
| `province` | TEXT NOT NULL | Provincia. |
| `data_json` | TEXT NOT NULL | JSON estructurado oficial de AEMET a 7 días. |
| `summary_3d` | TEXT NULL | Resumen pre-renderizado para 3 días. |
| `summary_7d` | TEXT NULL | Resumen pre-renderizado para 7 días. |
| `created_at` | TEXT | ISO 8601. |

### `aemet_forecast_hourly` — predicción estructurada horaria (24-48 h)
| Columna | Tipo | Notas |
|---|---|---|
| `id` | INTEGER PK | |
| `city_code` | TEXT NOT NULL | Código INE de 5 dígitos. |
| `city_name` | TEXT NOT NULL | Nombre del municipio. |
| `province` | TEXT NOT NULL | Provincia. |
| `data_json` | TEXT NOT NULL | JSON horario oficial de AEMET. |
| `summary_24h` | TEXT NULL | Resumen pre-renderizado para 12-24 horas. |
| `created_at` | TEXT | ISO 8601. |

### `aemet_maritime` — boletín meteorológico costero
| Columna | Tipo | Notas |
|---|---|---|
| `id` | INTEGER PK | |
| `costa_code` | TEXT NOT NULL | Código de costa (ej. `42` para Andalucía Occidental / Cádiz). |
| `costa_name` | TEXT NOT NULL | Nombre de la zona costera. |
| `data_json` | TEXT NOT NULL | JSON oficial del boletín costero con subzonas. |
| `summary` | TEXT NOT NULL | Resumen formateado para LoRa (ej. Guadalquivir a Roche). |
| `created_at` | TEXT | ISO 8601. |

### `aemet_observation` — mediciones físicas de estaciones meteorológicas
| Columna | Tipo | Notas |
|---|---|---|
| `id` | INTEGER PK | |
| `station_id` | TEXT NOT NULL | Código indicativo de estación (ej. `5972X` Cádiz / San Fernando). |
| `station_name` | TEXT NOT NULL | Nombre descriptivo de la estación. |
| `data_json` | TEXT NOT NULL | JSON con las últimas observaciones horarias. |
| `summary` | TEXT NOT NULL | Resumen en formato LoRa (temp, viento, rachas, HR, presión). |
| `created_at` | TEXT | ISO 8601. |

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
| `created_at` | TEXT | ISO 8601. |

Índice: `idx_commands_sent_created ON commands_sent(created_at, node_id)`.

### `outbox` — cola de mensajes y peticiones salientes por radio
Permite a procesos externos (como la API WebSocket del Gateway) encolar mensajes y solicitudes de radio (`__REQ_NODEINFO__`, mensajes de chat, etc.) de forma no bloqueante para que `main.py` los transmita por UART.

| Columna | Tipo | Notas |
|---|---|---|
| `id` | INTEGER PK | |
| `text` | TEXT NOT NULL | Texto del mensaje o comando reservado. |
| `dest` | TEXT | Destino (`^all` o `!xxxxxxxx`). |
| `channel` | INTEGER | Canal de transmisión (0-7). |
| `status` | TEXT | `pending` \| `sent` \| `error`. |
| `created_at` | TEXT | Momento de encolado. |
| `sent_at` | TEXT NULL | Momento de transmisión. |

Índice: `idx_outbox_status_created ON outbox(status, created_at)`.

### `auto_reported_nodes` — nodos auto-reportados por mala praxis (vigilancia)
Registra incidencias de nodos que saturan o dañan la red LoRa (saltos excesivos iniciales ≥6, telemetrías frecuentes <30m, spam de comandos). Permite que un mismo nodo tenga múltiples motivos de incidencia.

| Columna | Tipo | Notas |
|---|---|---|
| `id` | INTEGER PK | Identificador único del auto-reporte. |
| `node_id` | TEXT NOT NULL | ID del nodo (`!xxxxxxxx`). |
| `short_name` | TEXT NULL | Alias corto del nodo. |
| `name` | TEXT NULL | Nombre largo del nodo. |
| `reason_code` | TEXT NOT NULL | Código (`EXCESSIVE_HOPS`, `FAST_TELEMETRY`, `FAST_POSITION`, `FAST_NODEINFO`, `FAST_ENVIRONMENTAL`, `EXCESSIVE_TRACES`, `COMMAND_SPAM`). |
| `reason_desc` | TEXT NOT NULL | Descripción en lenguaje natural en español. |
| `event_count` | INTEGER | Número de reincidencias detectadas (por defecto 1). |
| `first_detected_at` | TEXT | Fecha y hora de la primera infracción (ISO 8601). |
| `last_detected_at` | TEXT | Fecha y hora de la última infracción (ISO 8601). |
| `last_details` | TEXT NULL | Metadatos JSON (intervalo medido, saltos, etc.). |
| `is_ignored_bot` | INTEGER | 1 si el bot lo ignora completamente en memoria y BD. |
| `is_blocked_fw` | INTEGER | 1 si se solicitó bloqueo en firmware/radio. |
| `updated_at` | TEXT | Fecha de última actualización. |

Restricción: `UNIQUE(node_id, reason_code)`.
Índices: `idx_auto_reported_node ON auto_reported_nodes(node_id)`, `idx_auto_reported_last ON auto_reported_nodes(last_detected_at DESC)`.

### `blocked_nodes` — lista negra de nodos bloqueados
Gestiona bloqueos automáticos (por saturación) o manuales permanentes.

| Columna | Tipo | Notas |
|---|---|---|
| `id` | INTEGER PK | |
| `node_id` | TEXT UNIQUE | Nodo bloqueado. |
| `node_name` | TEXT NULL | Nombre del nodo. |
| `block_type` | TEXT | `auto` \| `manual`. |
| `reason` | TEXT NULL | Motivo del bloqueo. |
| `created_at` | TEXT | Momento del bloqueo. |
| `expires_at` | TEXT NULL | Fecha de expiración (NULL = permanente). |
| `active` | INTEGER | 1 = activo, 0 = inactivo. |

### `abuse_logs` — auditoría de bloqueos y saturación
Histórico de disparos del sistema anti-abuso.

| Columna | Tipo | Notas |
|---|---|---|
| `id` | INTEGER PK | |
| `node_id` | TEXT NOT NULL | Nodo infractor. |
| `command` | TEXT NULL | Comando intentado. |
| `action_taken` | TEXT NOT NULL | `autoban_15m`, `autoban_24h`, `manual_block`, `dropped`. |
| `reason` | TEXT NULL | Motivo detallado. |
| `created_at` | TEXT | Momento del evento. |

## Palabras reservadas

`from` y `to` son palabras reservadas de SQL. En todas las queries van **entre
comillas dobles**: `"from"`, `"to"`. Mantener esta convención al añadir queries.

## Acceso

Todo el acceso a datos está centralizado en `Models/Database.py`. Ver
[06-modelo-database.md](06-modelo-database.md) para la API.

## Política de retención y mantenimiento

La base de datos SQLite ocupa muy poco espacio en disco (~8 MB con miles de registros).
Con el almacenamiento habitual en las Raspberry Pi (tarjetas SD de 64-128 GB), el bot puede
mantener años de datos continuos sin problemas de espacio.

- **Datos históricos válidos:** Se conservan **siempre** de forma indefinida (`pings` respondidos,
  `commands_sent`, `traces` exitosos y archivados, y telemetría de `nodes`). Son fundamentales
  para diagnóstico de cobertura, comparativas de SNR en el tiempo y trazabilidad de la malla.
- **Datos fallidos:** Si en el futuro se requiere liberar espacio, la única purga admisible es
  sobre registros de intentos fallidos sin utilidad técnica (p. ej. `traces` con `status = 'error'`
  antiguos). No se eliminan datos de interacciones válidas.

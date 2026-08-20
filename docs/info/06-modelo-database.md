# 06 · Modelo Database (`Models/Database.py`)

Centraliza **todo** el acceso a SQLite. No se escribe SQL fuera de este módulo.

```python
db = Database()                 # usa ensure_database() para localizar el fichero
db = Database(db_path="...")    # ruta explícita (tests)
```

- `_connect()` abre conexión con `row_factory = sqlite3.Row`.
- Cada método abre/cierra su conexión con `with self._connect() as conn:`.

## API por dominio

### Chistes
| Método | Descripción |
|---|---|
| `get_random_chiste(approved_only=True)` | Chiste aleatorio (aprobado o no). |
| `save_chiste(from_, content, need_upload=False, need_approve=False, chiste_id=None)` | Inserta y devuelve id. |
| `get_chistes_to_upload(limit=100)` | Chistes con `need_upload=1`. |
| `mark_chistes_uploaded(ids)` | Marca como subidos. |
| `get_last_downloaded_chiste_id()` | `MAX(chiste_id)` descargado. |
| `bulk_insert_api_chistes(items)` | Inserta lote desde API (dedup por `chiste_id`). → `(insertados, ignorados)`. |

### Traces
| Método | Descripción |
|---|---|
| `save_trace(from_, to, data_raw)` | Inserta un trace ya resuelto (`done`). |
| `enqueue_trace(node_id)` | Encola (`pending`); si ya hay uno pendiente, devuelve su id. |
| `get_next_pending_trace()` | Pendiente más antiguo o `None`. |
| `mark_trace_done(trace_id, ok, payload, from_='local')` | Marca `done`/`error` con payload. |
| `mark_trace_done_with_route(trace_id, ok, *, text, to_name, to_name_short, hops, return_hops, from_='local')` | Marca y guarda hasta 7 saltos ida/vuelta con SNR y nombres. |
| `get_last_trace_updated_at()` | `MAX(updated_at)` (para throttle global). |
| `get_latest_trace_snr(identifier, base_identifiers=None)` | Obtiene el SNR real del enlace exterior hacia/desde el router y la base (`RAU0`). |
| `get_next_node_to_trace(*, hops_limit, reload_hours, router_reload_hours, router_max_hops, retry_hours, router_identifiers)` | Selecciona el próximo nodo candidato dando **prioridad 1 a routers cercanos (hops <= 2, cada 6h)** y prioridad 2 a clientes normales/routers lejanos (72h). |

### Pings
| Método | Descripción |
|---|---|
| `save_ping(from_id, to_id, data_raw, *, from_name=None, hops=None)` | Guarda un ping con saltos efectivos y datos crudos. |

### Agenda
| Método | Descripción |
|---|---|
| `get_agenda(node_id)` | Items de agenda del nodo, ordenados por `moment`. |
| `add_agenda(node_id, content, moment=None)` | Inserta (acepta `datetime` o ISO). |

### Nodos y Routers
| Método | Descripción |
|---|---|
| `get_node(node_id)` | Devuelve la fila como dict o `None`. |
| `get_node_by_identifier(identifier)` | Busca un nodo por `node_id`, `short_name` o `name`. |
| `get_router_nodes(configured_identifiers=None, max_hops=2)` | Devuelve routers configurados y auto-detectados por rol (`ROUTER`/`ROUTER_LATE`/`REPEATER`) filtrados por `max_hops`. |
| `create_node_if_not_exists(node_id, data=None)` | `INSERT OR IGNORE` + update opcional. |
| `update_node(node_id, data)` | Update con lista blanca de columnas (`role`, `hops`, `snr`, etc.); castea `is_favorite`/`via_mqtt` a 0/1; actualiza `updated_at`. |

### Control de tareas
| Método | Descripción |
|---|---|
| `get_task_last_run(name)` | `last_run_at` de una tarea. |
| `set_task_run(name, when=None, extra=None)` | UPSERT de la marca. |

### AEMET
| Método | Descripción |
|---|---|
| `aemet_insert_alert(province, data_raw, message=None)` | Inserta dedup por hash; `None` si duplicada. |
| `aemet_bulk_insert(province, items)` | Parsea CAP y guarda lote. → `(insertadas, ignoradas)`. |
| `aemet_get_next_unpublished()` | Próxima alerta `published=0`. |
| `aemet_mark_published(alert_id)` | Marca publicada con timestamp. |
| `aemet_fix_legacy_rows(limit=500)` | Migra filas antiguas que guardaron XML crudo. |
| `_parse_cap_es(xml_text)` *(static)* | Extrae texto ES de un XML CAP 1.2. |

### Log de comandos
| Método | Descripción |
|---|---|
| `log_command(*, node_id, command, message=None, parameters=None)` | Inserta en `commands_sent`. |

### Cola (pendiente)
| Método | Descripción |
|---|---|
| `get_next_in_queue()` | **TODO** — estrategia de extracción por definir. |

## Convenciones

- `"from"` y `"to"` siempre entre comillas dobles.
- Fechas en ISO 8601 (`datetime.now().isoformat(timespec='seconds')`).
- Texto saneado con `sanitize_text` antes de almacenar (AEMET).
- Para añadir una query nueva: **método en este modelo**, nunca SQL suelto en
  comandos/cron. Si toca el esquema, actualiza también `create_db.py` y
  [03-base-de-datos.md](03-base-de-datos.md).

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
| `get_next_pending_trace(router_identifiers=None)` | Obtiene el trace pendiente más prioritario (routers primero, luego cronológico) o `None`. |
| `cleanup_stale_pending_traces(max_age_minutes=15)` | Expira trazas que lleven más de 15 minutos en estado pending sin procesar. |
| `mark_trace_done(trace_id, ok, payload, from_='local')` | Marca `done`/`error` con payload. |
| `mark_trace_done_with_route(trace_id, ok, *, text, to_name, to_name_short, hops, return_hops, from_='local')` | Marca y guarda hasta 7 saltos ida/vuelta con SNR y nombres. |
| `get_latest_trace_snr(identifier, base_identifiers=None)` | Obtiene el primer SNR exterior hacia/desde el router y la base (`RAU0`). |
| `get_latest_trace_route_info(identifier, base_identifiers=None)` | Obtiene la información completa de la ruta exterior (saltos reales desde la base, lista de SNRs tramo a tramo, repetidores intermedios y texto formateado, ej. `9.0dB, 9.2dB`). |
| `get_next_node_to_trace(*, hops_limit, reload_hours, router_reload_hours, router_max_hops, router_retry_short_hours, router_max_retries, router_retry_long_hours, retry_hours, router_start_hour, router_identifiers)` | Selecciona el próximo candidato con **prioridad 1 a routers cercanos (hops <= 2, cada 24h tras éxito a partir de las 06:00 AM, reintentos cada 1h hasta 5 veces y 24h tras 5 fallos)** y prioridad 2 a clientes normales (cada 5 días / 120h tras éxito, 24h tras fallo, y descarte definitivo tras 5 fallos consecutivos hasta nueva actividad). |
| `is_router_node(node_id, router_identifiers)` | Comprueba si un `node_id` es router/repetidor por rol o lista configurada. |

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
| `get_router_nodes(configured_identifiers=None, max_hops=2, require_successful_trace_for_auto=True)` | Devuelve routers configurados siempre, y auto-detectados por rol (`ROUTER`/`ROUTER_LATE`/`REPEATER`) solo si han respondido con éxito un traceroute previo. |
| `create_node_if_not_exists(node_id, data=None)` | `INSERT OR IGNORE` + update opcional. |
| `update_node(node_id, data)` | Update con lista blanca de columnas (`role`, `hops`, `snr`, etc.); castea `is_favorite`/`via_mqtt` a 0/1; actualiza `updated_at`. |
| `increment_node_traces_detected(node_id)` | Incrementa en 1 el contador de traceroutes emitidos y detectados para este nodo. |

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
| `aemet_weather_insert(scope, content, province, province_code, city, city_code, day, data_raw)` | Inserta texto provincial o municipal (`day='hoy'|'manana'`). |
| `aemet_weather_get_latest(scope=None, province_code=None, province=None, day=None)` | Devuelve la última predicción en texto filtrada por provincia y día con fallback. |
| `aemet_forecast_daily_insert(city_code, city_name, province, data_json, summary_3d, summary_7d)` | Inserta predicción estructurada a 7 días. |
| `aemet_forecast_daily_get_latest(city_code=None)` | Devuelve la última predicción multi-día estructurada. |
| `aemet_forecast_daily_get_all_latest()` | Devuelve la última predicción multi-día para cada una de las ubicaciones registradas en BD. |
| `aemet_forecast_hourly_insert(city_code, city_name, province, data_json, summary_24h)` | Inserta predicción estructurada horaria. |
| `aemet_forecast_hourly_get_latest(city_code=None)` | Devuelve la última predicción horaria estructurada. |
| `aemet_maritime_insert(costa_code, costa_name, data_json, summary)` | Inserta boletín costero oficial. |
| `aemet_maritime_get_latest(costa_code=None)` | Devuelve el último boletín marítimo costero. |
| `aemet_observation_insert(station_id, station_name, data_json, summary)` | Inserta mediciones físicas de estación meteorológica. |
| `aemet_observation_get_latest(station_id=None)` | Devuelve la última observación meteorológica física. |

### Encuestas y Votaciones
| Método | Descripción |
|---|---|
| `encuesta_create(*, owner_node_id, question, options, days=7, starts_at=None, ends_at=None)` | Crea una encuesta comunitaria con duración por días o fechas exactas. |
| `encuesta_get(encuesta_id)` | Devuelve los metadatos y opciones de una encuesta. |
| `encuesta_list_active(limit=10)` | Devuelve las encuestas vigentes activas. |
| `encuesta_list_all(limit=100)` | Devuelve todas las encuestas ordenadas con las activas más recientes primero. |
| `encuesta_vote(encuesta_id, node_id, option_index)` | Registra o rectifica el voto atómico de un nodo. |
| `encuesta_results(encuesta_id)` | Calcula los totales y porcentajes de votos por opción. |
| `encuesta_close(encuesta_id, owner_node_id=None)` | Cierra anticipadamente la votación. |
| `encuesta_delete(encuesta_id, owner_node_id=None)` | Elimina la encuesta y sus votos. |

### Log y Auditoría de Comandos
| Método | Descripción |
|---|---|
| `log_command(*, node_id, command, message=None, parameters=None)` | Inserta en `commands_sent` tras validar comando y nodo. |
| `get_commands_audit(limit=100, offset=0, hours=24, node_id=None, command=None)` | Devuelve logs paginados con filtrado temporal. |
| `get_top_command_users(limit=20, hours=24)` | Ranking de usuarios más activos en el periodo. |
| `get_commands_audit_summary(hours=24)` | Resumen numérico: total comandos, nodos únicos, top comando y top usuario. |

### Outbox (Cola Asíncrona Saliente)
| Método | Descripción |
|---|---|
| `enqueue_outbox(text, dest='^all', channel=0)` | Encola un mensaje para que `main.py` lo envíe (deduplica si está pendiente). |
| `get_next_pending_outbox()` | Obtiene el siguiente mensaje pendiente de envío. |
| `mark_outbox_sent(outbox_id, ok=True)` | Marca el mensaje como enviado (`sent`) o con error (`error`). |

### Traceroutes y Rutas
| Método | Descripción |
|---|---|
| `get_latest_trace_route_info(identifier, base_identifiers=['RAU0'])` | Devuelve saltos exteriores, lista de repetidores intermedios (`intermediates`) y SNR exterior de la ruta. |
| `get_recent_traces(limit=15)` | Devuelve los últimos traceroutes con saltos estructurados. |

### Seguridad, Anti-Abuso y Vigilancia
| Método | Descripción |
|---|---|
| `record_auto_reported_node(node_id, reason_code, reason_desc, details=None, short_name=None, name=None)` | Inserta o actualiza una incidencia por infracción consolidando por `(node_id, reason_code)` e incrementando `event_count`. |
| `get_auto_reported_nodes(limit=100, offset=0, reason_code=None)` | Lista los nodos auto-reportados con filtrado opcional por tipo de infracción. |
| `count_auto_reported_nodes()` | Devuelve el total de incidencias de auto-reportes registradas. |
| `set_node_bot_ignored(node_id, is_ignored=True)` | Marca/desmarca si un nodo debe ser ignorado por completo en memoria y base de datos. |
| `get_ignored_node_ids()` | Devuelve el conjunto `set[str]` de identificadores de nodos ignorados. |
| `set_node_fw_blocked(node_id, is_blocked=True)` | Marca el nodo para bloqueo a nivel de firmware/radio. |
| `is_node_blocked(node_id)` | Comprueba si un nodo está bloqueado en la lista negra (manual o auto activo). |
| `block_node(...)` / `unblock_node(...)` | Bloquea o reactiva un nodo en la lista negra. |
| `log_abuse(...)` / `get_abuse_logs(...)` | Registra y consulta la auditoría de saturación de comandos. |

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

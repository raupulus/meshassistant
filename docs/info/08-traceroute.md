# 08 · Traceroute (traces)

Funcionalidad para **mapear la topología** de la malla ejecutando traceroutes
periódicos. Usa la tabla `traces` como **cola y resultado** a la vez. Requiere
`ENABLE_TRACES=True`.

## Flujo completo

```
cron_tasks.send_trace()                      main.py loop()
  │                                            │
  ├─ ¿ENABLE_TRACES?                           │
  ├─ throttle global TRACES_INTERVAL           │
  ├─ get_next_node_to_trace(...)               │
  └─ enqueue_trace(node_id)  ──►  traces(status='pending')
                                               │
                              get_next_pending_trace() ◄─┘
                                               │
                              SerialInterface.traceroute(node_id)
                                               │
                              resolver nombres de saltos (get_node)
                                               │
                              mark_trace_done_with_route(...) ──► status done/error
```

## Lado cron — `cron_tasks.send_trace()`

1. Si `ENABLE_TRACES` es `False`, no hace nada.
2. **Throttle global:** si `now - get_last_trace_updated_at() < TRACES_INTERVAL`
   minutos, omite.
3. Selecciona candidato con `Database.get_next_node_to_trace(hops_limit, reload_hours, retry_hours)`.
4. `enqueue_trace(node_id)` inserta `status='pending'` (o reutiliza el pendiente
   existente). **No abre el serie.**

### Selección de candidato — `get_next_node_to_trace`

Query con CTEs que elige un `node_id` que cumpla **todo**:
- `COALESCE(via_mqtt,0)=0` (no MQTT).
- `hops IS NULL` o `hops <= hops_limit`.
- Sin traces `pending`.
- Ventana cumplida: último `done` hace ≥ `reload_hours`, o último `error` hace ≥
  `retry_hours`, o sin traces previos.
Ordena por `nodes.updated_at DESC` y toma 1.

## Lado principal — `main.loop()`

1. `get_next_pending_trace()` → toma el pendiente más antiguo.
2. `SerialInterface.traceroute(node_id)` → `{text, forward[], backward[]}`.
3. Resuelve hasta 7 saltos de ida y 7 de vuelta, enriqueciendo cada uno con
   `name`/`name_short`/`rssi` desde `Database.get_node`.
4. `mark_trace_done_with_route(...)` guarda `status='done'`, `data_raw=text`,
   `to_name`, los `hopN_*` y `hop_returnN_*`, y `hops`/`hops_back` (conteos).
5. Si algo falla, guarda `status='error'` con el texto del error en `data_raw`.

## Parámetros (env.py)

| Variable | Efecto |
|---|---|
| `ENABLE_TRACES` | Interruptor maestro. |
| `TRACES_HOPS` | Máximo de saltos del candidato. |
| `TRACES_INTERVAL` (min) | Throttle global entre traces. |
| `TRACES_RELOAD_INTERVAL` (h) | Re-trazar nodo tras éxito. |
| `TRACES_RETRY_INTERVAL` (h) | Reintentar nodo tras error. |

## Diseño: por qué la cola es la propia tabla

Versiones anteriores tenían tablas auxiliares de "peticiones de trace"; se
eliminaron. Ahora la misma fila de `traces` representa la **petición** (`pending`) y,
tras procesarse, el **resultado** (`done`/`error`). Esto simplifica el modelo y evita
que el cron toque el serie. Ver [01-arquitectura.md](01-arquitectura.md).

## Notas

- El parseo de saltos depende del **texto** que imprime `meshtastic` durante el
  trace (capturado por redirección de stdout). Si cambias de versión, verifícalo.
- `mark_trace_done_with_route` calcula `hops_count = len(hops) - 1` (excluye el
  extremo) — un único salto efectivo cuenta como 0.

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
3. Selecciona candidato con `Database.get_next_node_to_trace(hops_limit, reload_hours, router_reload_hours, router_max_hops, retry_hours, router_identifiers)`:
   - **Prioridad 1 (Routers cercanos):** Los routers configurados (`ROUTER_NODES`) y aquellos con rol oficial (`ROUTER`/`ROUTER_LATE`/`REPEATER`) que estén a `hops <= ROUTER_MAX_HOPS` (def. 2) se trazan cada **6 horas** (`ROUTER_TRACE_INTERVAL_HOURS=6`).
   - **Prioridad 2 (Clientes normales y routers lejanos):** Si los routers cercanos están al día, se trazan nodos ordinarios y routers lejanos que cumplan `hops <= hops_limit` y ventana de `reload_hours` (72 h).
4. `enqueue_trace(node_id)` inserta `status='pending'` (o reutiliza el pendiente
   existente). **No abre el serie.**

### Selección de candidato — `get_next_node_to_trace`

Query en dos fases con CTEs:
1. Comprueba si algún **router cercano (`hops <= router_max_hops`)** cumple `lp.last_updated IS NULL` o `done ≥ router_reload_hours` (6h) o `error ≥ retry_hours` (24h).
2. Si no hay routers cercanos pendientes, comprueba los **clientes ordinarios y routers más lejanos** cumpliendo `done ≥ reload_hours` (72h) y `hops <= hops_limit`.
3. Excluye siempre nodos MQTT (`via_mqtt=1`) y nodos con traces `pending`.

## Lado principal — `main.loop()`

1. `get_next_pending_trace()` → toma el pendiente más antiguo.
2. `SerialInterface.traceroute(node_id)` → `{text, forward[], backward[]}` invocando `sendTraceRoute(dest=node_id, hopLimit=3, channelIndex=0)`.
3. Resuelve hasta 7 saltos de ida y 7 de vuelta, enriqueciendo cada uno con
   `name`/`name_short`/`snr`/`rssi` desde `Database.get_node`.
4. `mark_trace_done_with_route(...)` guarda `status='done'`, `data_raw=text`,
   `to_name`, los `hopN_*` y `hop_returnN_*`, y `hops`/`hops_back` (conteos).
5. Si algo falla, guarda `status='error'` con el texto del error en `data_raw`.

## Uso del SNR de Traceroute en `/routers`

El comando `/routers` utiliza `Database.get_latest_trace_snr(node_id)` para obtener el **SNR medido en el enlace exterior real entre `RAU0` y el router** (en el salto `RAU0 <-> Router`), en lugar de mostrar el SNR del salto local interior `RAU0 -> Bot`. Si el nodo es repetido y aún no dispone de traza previa, se omite el SNR para evitar mostrar la señal distorsionada del enlace local.

## Parámetros (env.py)

| Variable | Efecto |
|---|---|
| `ENABLE_TRACES` | Interruptor maestro. |
| `TRACES_HOPS` | Máximo de saltos del candidato general. |
| `TRACES_INTERVAL` (min) | Throttle global entre traces (def. 5 min). |
| `TRACES_RELOAD_INTERVAL` (h) | Re-trazar nodo cliente tras éxito (def. 72 h). |
| `ROUTER_TRACE_INTERVAL_HOURS` (h) | Re-trazar router prioritario tras éxito (def. 6 h). |
| `ROUTER_MAX_HOPS` | Límite de saltos para routers prioritarios y el informe de `/routers` (def. 2). |
| `TRACES_RETRY_INTERVAL` (h) | Reintentar nodo tras error (def. 24 h). |

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

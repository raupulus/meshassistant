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
3. Selecciona candidato con `Database.get_next_node_to_trace(...)`:
   - **Compensación de Nodo Base (+1 salto):** Dado que el bot está cableado por UART a la base (`RAU0`), se añade +1 a los límites de saltos (`hops <= ROUTER_MAX_HOPS + 1` y `hops <= TRACES_HOPS + 1`) para cubrir con exactitud los saltos exteriores reales deseados.
   - **Filtro de Inactividad y Alejamiento (7 días):** Descarta automáticamente nodos que lleven más de 7 días sin ser escuchados cerca (`last_heard < now - 7d` o `hops > hops_limit + 1`). Esto evita insistir en nodos turistas o repetidores caídos.
   - **Prioridad 1 (Routers cercanos):** Los routers configurados (`ROUTER_NODES`) y aquellos con rol oficial (`ROUTER`/`ROUTER_LATE`/`REPEATER`) que estén a `hops <= ROUTER_MAX_HOPS + 1` (def. 2+1=3 brutos).
     * **Ventana Horaria:** Se ejecutan preferentemente a partir de las **05:00 AM** (`ROUTER_TRACE_START_HOUR=5`), cuando la malla está en calma.
     * **Éxito previo (`status='done'`):** Se traza **1 vez al día** (cada **24 horas**, `ROUTER_TRACE_INTERVAL_HOURS=24`).
     * **Fallo puntual (`status='error'`, < 5 fallos consecutivos):** Se reintenta cada **1 hora** (`ROUTER_RETRY_SHORT_HOURS=1`).
     * **Fallo persistente ($\ge$ 5 fallos consecutivos):** Se penaliza con **24 horas** de enfriamiento (`ROUTER_RETRY_LONG_HOURS=24`) para no saturar la red.
   - **Prioridad 2 (Clientes normales y routers lejanos):** Si los routers cercanos están al día, se trazan nodos ordinarios y routers lejanos que cumplan `hops <= hops_limit + 1`, activos en los últimos 7 días, y ventana de `reload_hours` (72 h tras éxito, 24 h tras error).
4. `enqueue_trace(node_id)` inserta `status='pending'` (o reutiliza el pendiente existente). **No abre el serie.**

### Sondeo Matinal de Batería de Routers — `cron_tasks.request_router_telemetry()`
A partir de las **07:00 AM** (`ROUTER_TELEMETRY_START_HOUR=7`), el cron solicita 1 vez al día la telemetría de batería/voltaje a todos los routers cercanos ($\le 2$ saltos exteriores):
- Encola en `outbox` una petición reservada `__REQ_TELEMETRY__` por cada router.
- `main.py` despacha estas solicitudes espaciadamente hacia la radio con `interface.request_telemetry(dest)`.
- Las respuestas recibidas por LoRa actualizan automáticamente `nodes.battery`, `nodes.voltage` y el dashboard.

## Lado principal — `main.loop()`

1. `get_next_pending_trace(router_identifiers)` → toma el pendiente dando **prioridad a routers**.
2. `SerialInterface.traceroute(node_id)` → `{text, forward[], backward[]}` invocando `sendTraceRoute(dest=node_id, hopLimit=3, channelIndex=0)` con timeout máximo tajante de **60 segundos** (1 minuto exacto desde el envío).
3. Resuelve hasta 7 saltos de ida y 7 de vuelta, enriqueciendo cada uno con
   `name`/`name_short`/`snr`/`rssi` desde `Database.get_node`.
4. `mark_trace_done_with_route(...)` guarda `status='done'`, `data_raw=text`,
   `to_name`, los `hopN_*` y `hop_returnN_*`, y `hops`/`hops_back` (conteos).
5. Si algo falla o expira el minuto, guarda `status='error'` con el texto del error en `data_raw`.

## Uso del SNR y Saltos de Traceroute en `/routers`

El comando `/routers` utiliza `Database.get_latest_trace_route_info(node_id)` para obtener el desglose completo del enlace exterior:
* **Saltos reales exteriores:** Determina cuántos repetidores intermedios hay entre la base (`RAU0`) y el nodo destino (0 saltos = enlace directo con `RAU0`, 1 salto = 1 repetidor intermedio, etc.).
* **SNRs tramo a tramo:** Muestra el SNR medido en cada salto exterior. Por ejemplo, en una ruta `Bot -> RAU0 -> herc -> CO14`, descarta el enlace local `Bot <-> RAU0` y muestra `(9.0dB, 9.2dB)` correspondientes a los tramos `RAU0 <-> herc` y `herc <-> CO14`.
* Si el nodo es repetido y aún no dispone de traza previa exitosa, se omite el SNR para evitar mostrar la señal distorsionada del enlace local.

## Parámetros (env.py)

| Variable | Efecto |
|---|---|
| `ENABLE_TRACES` | Interruptor maestro. |
| `TRACES_HOPS` | Saltos exteriores deseados del candidato general (se compensa con +1 base). |
| `TRACES_INTERVAL` (min) | Throttle global entre traces (def. 5 min). |
| `TRACES_MAX_INACTIVE_DAYS` (d) | Días sin señales cercanas para descartar un nodo de la cola automática (def. 7 d). |
| `TRACES_RELOAD_INTERVAL` (h) | Re-trazar nodo cliente tras éxito (def. 72 h). |
| `ROUTER_TRACE_INTERVAL_HOURS` (h) | Re-trazar router prioritario tras éxito (def. 24 h / 1 vez al día). |
| `ROUTER_TRACE_START_HOUR` | Hora de inicio preferente para trazas diarias a routers (def. 5 AM). |
| `ROUTER_TELEMETRY_START_HOUR` | Hora para solicitar telemetría matinal a routers (def. 7 AM). |
| `ROUTER_RETRY_SHORT_HOURS` (h) | Reintento rápido ante fallo puntual de un router (def. 1 h). |
| `ROUTER_MAX_RETRIES` | Límite de reintentos rápidos (1h) antes de penalizar (def. 5). |
| `ROUTER_RETRY_LONG_HOURS` (h) | Enfriamiento largo tras 5 fallos consecutivos (def. 24 h). |
| `ROUTER_MAX_HOPS` | Límite de saltos exteriores para routers prioritarios (def. 2). |
| `ROUTERS_MAX_PARTS` | Límite máximo de mensajes para la respuesta de `/routers` (def. 5). |
| `TRACES_RETRY_INTERVAL` (h) | Reintentar nodo cliente general tras error (def. 24 h). |

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

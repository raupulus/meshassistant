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
2. Si ya hay una traza pendiente (`status='pending'`, como las lanzadas **manualmente desde la Web UI**), se respeta y no se encola otra para no duplicar.
3. Selecciona candidato con `Database.get_next_node_to_trace(...)`:
   - **Compensación de Nodo Base (+1 salto):** Dado que el bot está cableado por UART a la base (`RAU0`), se añade +1 a los límites de saltos (`hops <= ROUTER_MAX_HOPS + 1` y `hops <= TRACES_HOPS + 1`) para cubrir con exactitud los saltos exteriores reales deseados.
   - **Filtro de Inactividad y Alejamiento (7 días):** Descarta automáticamente nodos que lleven más de 7 días sin ser escuchados cerca (`last_heard < now - 7d` o `hops > hops_limit + 1`). Esto evita insistir en nodos turistas o repetidores caídos.
   - **Prioridad 1 (Routers cercanos):** Los routers configurados (`ROUTER_NODES`) y aquellos con rol oficial (`ROUTER`/`ROUTER_LATE`/`REPEATER`) que estén a `hops <= ROUTER_MAX_HOPS + 1` (def. 2+1=3 brutos).
     * **Ventana Horaria:** Se ejecutan preferentemente a partir de las **06:00 AM** (`ROUTER_TRACE_START_HOUR=6`), cuando la malla está en calma.
     * **Intervalo rápido entre routers:** **40 segundos** (`ROUTER_TRACE_INTERVAL_SECONDS=40`) para despachar la auditoría matinal completa rápidamente antes del inicio del tráfico diurno.
     * **Éxito previo (`status='done'`):** Se traza **1 vez al día** (cada **24 horas**, `ROUTER_TRACE_INTERVAL_HOURS=24`).
     * **Fallo puntual (`status='error'`, < 5 fallos consecutivos):** Se reintenta cada **1 hora** (`ROUTER_RETRY_SHORT_HOURS=1`).
     * **Fallo persistente ($\ge$ 5 fallos consecutivos):** Se penaliza con **24 horas** de enfriamiento (`ROUTER_RETRY_LONG_HOURS=24`) para no saturar la red.
   - **Prioridad 2 (Clientes normales y routers lejanos):**
     * **Cadencia tras éxito:** Se trazan **1 vez cada 5 días** (cada **120 horas**, `TRACES_RELOAD_INTERVAL=120`).
     * **Reintento tras fallo:** Se espera **24 horas** (`TRACES_RETRY_INTERVAL=24`).
     * **Descarte por 5 fallos consecutivos:** Si un nodo normal acumula $\ge 5$ errores consecutivos sin responder, se descarta definitivamente de la cola y no se le vuelve a trazar hasta que el bot reciba un nuevo paquete o telemetría del nodo que actualice su `last_heard` posterior al último error.
4. **Throttle dinámico por franja horaria:**
   - **Routers:** Cooldown de **40 segundos** entre trazas.
   - **Clientes diurnos (08:00 a 23:00):** Cooldown de **60 minutos** (**1 trace por hora**).
   - **Clientes nocturnos (23:00 a 08:00):** Cooldown de **5 minutos**.
5. `enqueue_trace(node_id)` inserta `status='pending'` (o reutiliza el pendiente existente). **No abre el serie.**

### Sondeo Matinal de Batería de Routers — `cron_tasks.request_router_telemetry()`
A partir de las **07:00 AM** (`ROUTER_TELEMETRY_START_HOUR=7`), el cron solicita 1 vez al día la telemetría de batería/voltaje a todos los routers cercanos ($\le 2$ saltos exteriores):
- Encola en `outbox` una petición reservada `__REQ_TELEMETRY__` por cada router.
- `main.py` despacha estas solicitudes espaciadamente hacia la radio con `interface.request_telemetry(dest)`.
- Las respuestas recibidas por LoRa actualizan automáticamente `nodes.battery`, `nodes.voltage` y el dashboard.

## Lado principal — `main.loop()`

1. `get_next_pending_trace(router_identifiers)` → toma el pendiente de inmediato (tanto automáticos como manuales desde la Web UI) dando **prioridad a routers**.
2. **Timeout dinámico de Radio LoRa:**
   - Durante el día (**08:00 a 23:00**): Timeout reducido a **30 segundos** (`TRACES_TIMEOUT_PEAK=30.0`) para no retener la radio en horarios de alta actividad.
   - Durante la noche (**23:00 a 08:00**): Timeout estándar de **60 segundos** (`TRACES_TIMEOUT_OFFPEAK=60.0`).
3. `SerialInterface.traceroute(node_id, timeout=...)` → `{text, forward[], backward[]}` invocando `sendTraceRoute(dest=node_id, hopLimit=3, channelIndex=0)`.
4. Resuelve hasta 7 saltos de ida y 7 de vuelta, enriqueciendo cada uno con
   `name`/`name_short`/`snr`/`rssi` desde `Database.get_node`.
5. `mark_trace_done_with_route(...)` guarda `status='done'`, `data_raw=text`,
   `to_name`, los `hopN_*` y `hop_returnN_*`, y `hops`/`hops_back` (conteos).
6. Si algo falla o expira el timeout, guarda `status='error'` con el texto del error en `data_raw`.

## Uso del SNR y Saltos de Traceroute en `/routers`

El comando `/routers` utiliza `Database.get_latest_trace_route_info(node_id)` para obtener el desglose completo del enlace exterior:
* **Saltos reales exteriores:** Determina cuántos repetidores intermedios hay entre la base (`RAU0`) y el nodo destino (0 saltos = enlace directo con `RAU0`, 1 salto = 1 repetidor intermedio, etc.).
* **SNRs tramo a tramo:** Muestra el SNR medido en cada salto exterior. Por ejemplo, en una ruta `Bot -> RAU0 -> herc -> CO14`, descarta el enlace local `Bot <-> RAU0` y muestra `(9.0dB, 9.2dB)` correspondientes a los tramos `RAU0 <-> herc` y `herc <-> CO14`.
* Si el nodo es repetido y aún no dispone de traza previa exitosa, se omite el SNR para evitar mostrar la señal distorsionada del enlace local.

## Parámetros (env.py)

| Variable | Efecto |
|---|---|
| `ENABLE_TRACES` | Interruptor maestro para trazas automáticas. |
| `TRACES_HOPS` | Saltos exteriores deseados del candidato general (se compensa con +1 base). |
| `TRACES_RELOAD_INTERVAL` (h) | Re-trazar nodo cliente tras éxito (def. 120 h = 5 días). |
| `TRACES_RETRY_INTERVAL` (h) | Reintentar nodo cliente general tras error (def. 24 h). |
| `TRACES_PEAK_START_HOUR` | Inicio de franja diurna de alta concurrencia (def. 8 AM). |
| `TRACES_PEAK_END_HOUR` | Fin de franja diurna de alta concurrencia (def. 23 PM). |
| `TRACES_INTERVAL_PEAK` (min) | Cooldown diurno entre trazas a clientes (def. 60 min = 1 por hora). |
| `TRACES_INTERVAL_OFFPEAK` (min) | Cooldown nocturno entre trazas a clientes (def. 5 min). |
| `TRACES_TIMEOUT_PEAK` (s) | Timeout de traceroute de radio durante el día (def. 30 s). |
| `TRACES_TIMEOUT_OFFPEAK` (s) | Timeout de traceroute de radio durante la noche (def. 60 s). |
| `ROUTER_TRACE_START_HOUR` | Hora de inicio preferente para trazas diarias a routers (def. 6 AM). |
| `ROUTER_TRACE_INTERVAL_HOURS` (h) | Re-trazar router prioritario tras éxito (def. 24 h / 1 vez al día). |
| `ROUTER_TRACE_INTERVAL_SECONDS` (s) | Intervalo entre trazas a routers en la rutina matinal (def. 40 s). |
| `ROUTER_TELEMETRY_START_HOUR` | Hora para solicitar telemetría matinal a routers (def. 7 AM). |
| `ROUTER_RETRY_SHORT_HOURS` (h) | Reintento rápido ante fallo puntual de un router (def. 1 h). |
| `ROUTER_MAX_RETRIES` | Límite de reintentos rápidos (1h) antes de penalizar (def. 5). |
| `ROUTER_RETRY_LONG_HOURS` (h) | Enfriamiento largo tras 5 fallos consecutivos (def. 24 h). |
| `ROUTER_MAX_HOPS` | Límite de saltos exteriores para routers prioritarios (def. 2). |
| `TRACES_MAX_INACTIVE_DAYS` (d) | Días sin señales cercanas para descartar un nodo de la cola automática (def. 7 d). |
| `ROUTERS_MAX_PARTS` | Límite máximo de mensajes para la respuesta de `/routers` (def. 5). |

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

# 04 · Interfaz serial (`Models/SerialInterface.py`)

Envoltura sobre la librería `meshtastic` que gestiona la comunicación por **UART**
con el nodo. Es el único componente que abre el puerto serie.

## Construcción

```python
SerialInterface(serial_port)   # serial_port = env.SERIAL_DEVICE_PATH
```

Atributos de clase relevantes:
- `node_dict` — caché en memoria de `Node` indexada por `node_id`.
- `command_dict` — referencia a `data.commands_dict`.

## Conexión y eventos

`connect()` abre `serial_interface.SerialInterface(devPath=...)` y se suscribe a
tópicos de `pubsub`:

| Tópico | Handler | Uso |
|---|---|---|
| `meshtastic.connection.established` | `on_connection` | Al conectar, carga nodos (`get_nodes`). |
| `meshtastic.receive.text` | `on_receive_text` | **Núcleo:** procesa texto y dispara comandos. |
| `meshtastic.receive.nodeinfo` | `on_receive_nodeinfo` | (placeholder). |
| `meshtastic.node.updated` | `on_node_update` | Actualización de nodo. |
| `meshtastic.receive.user` | `on_receive_user` | Actualiza metadatos del nodo emisor. |
| `meshtastic.receive.data` | `on_receive_data` | Telemetría (batería, métricas y sensores INA), vigilancia y emisión en tiempo real. |
| `meshtastic.connection.lost` | `on_connection_lost` | Reconexión. |
| `meshtastic.connection.closed` | `on_connection_closed` | Cierre. |

## Reconexión y Watchdog de Recepción Serie (UART)

El bot está diseñado para conectarse a un nodo por UART de hardware (`/dev/serial0` en Raspberry Pi). A diferencia de un puerto USB, el puerto UART físico no se desconecta a nivel de kernel si el microcontrolador (Pico W / ESP32) sufre un desincronismo o bloqueo en su flujo de lectura. Para evitar que el bot quede en un estado "sordo" silencioso, se implementa una arquitectura de doble protección:

1. **Reconexión Reactiva (`on_connection_lost` / `on_connection_closed`):**
   - El hilo de Meshtastic marca `self._needs_reconnect = True` de forma atómica y no bloqueante.
   - La reconexión efectiva la ejecuta el hilo principal en `main.py` mediante `interface.reconnect_if_needed()`, cerrando la interfaz, aplicando una pausa de 2 segundos para liberar buffers del SO y reabriendo el puerto.

2. **Watchdog Activo de Recepción (`check_watchdog()`):**
   - **Monitoreo del hilo lector (`_rxThread`):** Verifica que el hilo en segundo plano de la librería `meshtastic` siga vivo. Si muere silenciosamente, solicita reconexión inmediata.
   - **Inactividad de recepción (RX Silence Timeout):** Registra mediante `self._touch_rx()` la marca temporal de cualquier paquete o evento entrante (`on_receive_text`, `on_receive_data`, `on_node_update`, etc.). Si transcurren más de `SERIAL_WATCHDOG_TIMEOUT_MINUTES` (por defecto 20 min) sin ningún paquete entrante en la malla, fuerza un reinicio limpio del puerto serie.
   - **Detección por fallos de trazas repetidos:** Si fallan `SERIAL_WATCHDOG_MAX_TRACE_TIMEOUTS` (por defecto 5) trazas consecutivas por `TimeoutError` y además no ha habido tráfico RX en los últimos 5 minutos, se diagnostica desincronismo del canal serie y se fuerza una reconexión preventiva.
   - **Notificación IPC en tiempo real:** Si el watchdog actúa, emite los eventos `watchdog_alert` y actualiza `system_status` (indicando `watchdog_triggered=True` y la causa) para visibilidad en el panel web.

Parámetros configurables en `env.py`:
- `SERIAL_WATCHDOG_ENABLED` (bool, def. `True`): Activa o desactiva la vigilancia.
- `SERIAL_WATCHDOG_TIMEOUT_MINUTES` (int/float, def. `20`): Minutos máximos de inactividad RX antes de reconectar (0 para deshabilitar).
- `SERIAL_WATCHDOG_MAX_TRACE_TIMEOUTS` (int, def. `5`): Traces consecutivos fallidos por timeout antes de reconectar (0 para deshabilitar).

## Envío de mensajes

```python
send(msg, dest=None, channel=0, reply_id=None)  # broadcast (^all) o directo con in-reply-to
send_direct(msg, node_id)                      # atajo a directo
send_to_channel(msg, channel=0)                # atajo a canal/broadcast
reply_to_message(msg, metadata)                # responde citando el mensaje original (replyId)
```

- `dest=None` o `"^all"` → broadcast en `channel`.
- `dest=int|str` → mensaje directo (`destinationId`).
- `reply_id` → ID del paquete original para citar la respuesta nativamente en la app de Meshtastic (`replyId`).
- `reply_to_message` decide directo vs. canal leyendo `metadata['is_direct']`, `metadata['channel']` y propaga `metadata['reply_id']`.
- Devuelve `bool` (éxito/fallo) y nunca lanza: errores capturados y logueados.

> Límite Meshtastic: **~200 caracteres** por mensaje. Trocea textos largos con `split_messages()`.

## Solicitud de telemetría y métricas — `request_telemetry`

```python
request_telemetry(destination_id, channel_index=0, telemetry_type="device_metrics")
```

Permite solicitar telemetría bajo demanda a cualquier nodo o router de la red por radio LoRa:
- `telemetry_type="device_metrics"`: Solicita métricas estándar de dispositivo (nivel de batería, voltaje interno, uptime).
- `telemetry_type="power_metrics"`: Solicita métricas de potencia y corriente a nodos equipados con sensores INA (INA219 / INA3221).
- **Asíncrono y no bloqueante**: Construye el protobuf `telemetry_pb2.Telemetry` y utiliza `self.interface.sendData(..., portNum=TELEMETRY_APP, wantResponse=True)` evitando deliberadamente el método síncrono `waitForTelemetry()` de Meshtastic. El proceso principal `main.py` no se congela y la respuesta entrante se procesa de forma natural en `on_receive_data`.

## Recepción de texto — `on_receive_text`

1. Extrae `text`, `fromId`, `toId`, `to` y el `id` del paquete original.
2. **Inspección de Vigilancia (`MeshWatcher`):**
   - Si el nodo emisor está en la lista de **ignorados en el bot**, descarta inmediatamente el paquete (0 CPU, 0 escrituras, 0 radio).
   - Comprueba si el paquete nació con saltos excesivos (`hopStart >= 6`) y lo auto-reporta si procede.
3. Determina `is_direct` (`toId != '^all'` y `to != 0xFFFFFFFF`).
4. Obtiene/crea el `Node` emisor en `node_dict` y actualiza sus metadatos
   (snr, rssi, hop_limit, hop_start, via_mqtt) y telemetría en base de datos.
5. Emite el evento en tiempo real `message_rx` a la pasarela WebSocket / Gateway.
6. `functions.search_command(msg)` → busca un comando registrado.
7. **Filtro de saltos (Hops):** Si el mensaje es por RF (`via_mqtt=False`), calcula los saltos
   del emisor (`hopStart - hopLimit`). Si superan `local_hop_limit + 1` (donde `local_hop_limit`
   se lee dinámicamente del firmware local), se omite la ejecución de la respuesta para ahorrar
   ancho de banda en la malla, registrándolo en el log.
8. Si procede (`is_direct` o `in_group`), invoca `command_dict[cmd]['callback'](...)` y
   registra el comando en `commands_sent`.

## Recepción de datos y telemetría — `on_receive_data`

Maneja los paquetes de datos que circulan por la malla Meshtastic (`meshtastic.receive.data`):

1. **Vigilancia e Inspección (`MeshWatcher`):**
   - Comprueba si el nodo emisor está en la lista de ignorados para descartar el paquete.
   - Detecta si el paquete es de traceroute (`TRACEROUTE_APP` o `ROUTING_APP`) e incrementa la tasa de actividad y detección de trazas del nodo.
2. **Extracción y Decodificación de Telemetría:**
   - **Métricas de dispositivo (`deviceMetrics`):** Nivel de batería (`batteryLevel`), voltaje (`voltage`), tiempo de actividad (`uptimeSeconds`), ocupación del canal (`channelUtilization`) y del aire (`airUtilTx`).
   - **Métricas de potencia / Sensores INA (`powerMetrics` / `power_metrics`):** Captura lecturas de sensores de corriente/tensión externos (ej. INA219, INA3221 de hasta 3 canales) vía `ch1Voltage`, `ch2Voltage`, `ch3Voltage` o `voltage`.
   - **Métricas ambientales (`environmentMetrics`):** Voltaje adicional o lecturas climáticas si están presentes.
3. **Persistencia en Base de Datos:**
   - Si el nodo emisor está identificado, actualiza en `nodes` los campos de batería, voltaje, tiempo de actividad y los voltajes `power_ina1`, `power_ina2`, `power_ina3` mediante `Database.update_node`.
4. **Emisión en Tiempo Real (Gateway):**
   - Emite el evento IPC/WebSocket `device_telemetry` con todos los datos extraídos (incluyendo `power_ina1/2/3`) para su visualización reactiva e inmediata en el panel web.

## Carga de nodos — `get_nodes`

Recorre `interface.nodes` y crea/actualiza un `Node` por cada uno, persistiéndolos
en BD a través del propio modelo `Node`.

## Traceroute — `traceroute(node_id, timeout=10.0)`

Ejecuta un TraceRoute real y **captura la salida textual** que imprime la librería
(redirigiendo `stdout`/`stderr`). Está escrito de forma **defensiva**: prueba varias
firmas de `sendTraceRoute` en orden hasta que una funcione (compatibilidad entre
versiones de `meshtastic`). Luego parsea el texto:

- Líneas tras `Route traced towards destination:` → saltos de **ida**.
- Líneas tras `Route traced back to us:` → saltos de **vuelta**.

Devuelve:

```python
{ 'text': str, 'forward': [{'id','snr'}...], 'backward': [{'id','snr'}...] }
```

`main.py` enriquece esos saltos con nombres desde BD y los guarda con
`Database.mark_trace_done_with_route`. Ver [08-traceroute.md](08-traceroute.md).

## Notas / gotchas

- **Hardware y Potencia TX del Nodo:** El nodo de radio es una **Raspberry Pi Pico W** acoplada a un módulo **HT-RA62** (SX1262). La potencia máxima física real que puede entregar el hardware en emisión es de **21–22 dBm** (~160 mW). Aunque por software se configure un valor superior como `lora.tx_power = 27`, el módulo recortará la emisión física a su límite real de 21–22 dBm.
- Si actualizas `meshtastic`, **prueba un traceroute real**: el parseo depende del
  texto que imprime la librería.
- Hay algunos `print` heredados en handlers; el logging "oficial" es `log_p`.

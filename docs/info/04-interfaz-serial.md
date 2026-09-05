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

## Reconexión

`on_connection_lost` espera, cierra la interfaz y reintenta `connect()` en bucle
mientras el dispositivo exista (`os.path.exists(self.serial_port)`), con esperas
entre intentos. Esto da **tolerancia a reinicios** del nodo.

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

- Si actualizas `meshtastic`, **prueba un traceroute real**: el parseo depende del
  texto que imprime la librería.
- Hay algunos `print` heredados en handlers; el logging "oficial" es `log_p`.

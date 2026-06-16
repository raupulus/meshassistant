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
| `meshtastic.receive.data` | `on_receive_data` | (debug). |
| `meshtastic.connection.lost` | `on_connection_lost` | Reconexión. |
| `meshtastic.connection.closed` | `on_connection_closed` | Cierre. |

## Reconexión

`on_connection_lost` espera, cierra la interfaz y reintenta `connect()` en bucle
mientras el dispositivo exista (`os.path.exists(self.serial_port)`), con esperas
entre intentos. Esto da **tolerancia a reinicios** del nodo.

## Envío de mensajes

```python
send(msg, dest=None, channel=0)     # broadcast (^all) o directo según dest
send_direct(msg, node_id)           # atajo a directo
send_to_channel(msg, channel=0)     # atajo a canal/broadcast
reply_to_message(msg, metadata)     # responde según el mensaje original
```

- `dest=None` o `"^all"` → broadcast en `channel`.
- `dest=int|str` → mensaje directo (`destinationId`).
- `reply_to_message` decide directo vs. canal leyendo `metadata['is_direct']` y
  `metadata['channel']`.
- Devuelve `bool` (éxito/fallo) y nunca lanza: errores capturados y logueados.

> Límite Meshtastic: **~200 caracteres** por mensaje. Trocea textos largos.

## Recepción de texto — `on_receive_text`

1. Extrae `text`, `fromId`, `toId`, `to`.
2. Determina `is_direct` (`toId != '^all'` y `to != 0xFFFFFFFF`).
3. Obtiene/crea el `Node` emisor en `node_dict` y actualiza sus metadatos
   (snr, rssi, hop_limit, hop_start, via_mqtt).
4. Construye `metadata` (ver contrato en [07-comandos.md](07-comandos.md)).
5. `functions.search_command(msg)` → si hay comando válido y procede
   (`is_direct` o `in_group`), invoca `command_dict[cmd]['callback'](...)`.

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

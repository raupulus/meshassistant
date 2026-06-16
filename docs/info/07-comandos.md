# 07 · Comandos

## Registro de comandos (`data.py`)

Los comandos se declaran en `commands_dict`. Cada entrada:

```python
"ping": {
    "callback": ping_callback,   # función importada de Commands/
    "in_group": True,            # ¿responde en canal? Si False, solo en directo
    "usage": "/ping o !ping",
    "info": "Devuelve información de como detecta el nodo que hace ping"
}
```

## Detección (`functions.search_command`)

- El mensaje debe empezar por `/` o `!`.
- Se toma la primera palabra, se quita el prefijo y se pasa a minúsculas.
- Si está en `commands_dict`, devuelve `(comando, args)`; si no, `(None, [])`.

## Dispatch (`SerialInterface.on_receive_text`)

```
comando válido?
  └─ sí → ¿es directo?  o  ¿commands_dict[cmd]['in_group'] es True?
            └─ sí → callback(interface, args, msg, metadata)
            └─ no → se ignora (no responde en canal)
```

## Contrato del callback

```python
def <nombre>_callback(interface, args, msg, metadata):
    ...
    interface.reply_to_message(respuesta, metadata)
```

`metadata` contiene:

| Clave | Descripción |
|---|---|
| `node_from` | dict del nodo emisor (`id`, `name`, `short_name`, `snr`, `rssi`, `hops`, `via_mqtt`…). |
| `node_to` | `{ id, num }` del destino. |
| `channel` | índice de canal. |
| `is_direct` | bool. |
| `rx_snr`, `rx_rssi` | señal de recepción. |
| `via_mqtt` | bool. |

Todo callback **registra el comando** con `Database().log_command(...)` (en
`try/except` para no romper la respuesta).

## Comandos actuales

| Comando | Fichero | `in_group` | Estado | Notas |
|---|---|---|---|---|
| `/help [cmd]` | `Commands/help.py` | No | ✅ | Lista comandos o muestra `info` de uno. |
| `/about` | `Commands/about.py` | No | ✅ | Texto fijo del proyecto. |
| `/ping` | `Commands/ping.py` | Sí | ✅ | Guarda ping en BD; responde saltos o "via MQTT". |
| `/chiste [add\|help …]` | `Commands/chiste.py` | Sí | ✅ | Aleatorio, alta (`need_approve`+`need_upload`) o ayuda. |
| `/maremoto` | `Commands/maremoto.py` | Sí | ✅ | Años/meses/días desde 1/11/1755. |
| `/weather` | `Commands/weather.py` | No | 🟡 | Texto fijo; pendiente fuente real. |
| `/uptime` | `Commands/uptime.py` | No | 🟡 | Responde `N/D`. |
| `/ia` | `Commands/ia.py` | Sí | 🟡 | "funcionalidad en desarrollo". |

## Añadir un comando nuevo

1. `Commands/<nombre>.py`:
   ```python
   def <nombre>_callback(interface, args, msg, metadata):
       interface.reply_to_message("respuesta", metadata)
       try:
           from Models.Database import Database
           node_id = (metadata or {}).get('node_from', {}).get('id')
           Database().log_command(node_id=node_id, command='<nombre>',
                                   message=' '.join(args) if args else None)
       except Exception:
           pass
   ```
2. En `data.py`: `from Commands.<nombre> import <nombre>_callback` y añadir entrada
   en `commands_dict` (`callback`, `in_group`, `usage`, `info`).
3. Respetar el límite de ~200 caracteres por respuesta (trocear si hace falta).
4. Documentar en `README.md` y aquí.

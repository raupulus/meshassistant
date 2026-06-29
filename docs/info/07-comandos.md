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
| `/help [cmd]` | `Commands/help.py` | No | ✅ | Lista comandos (omite alias `hidden`) o muestra `info` de uno. |
| `/about` | `Commands/about.py` | No | ✅ | Texto fijo del proyecto. |
| `/ping` | `Commands/ping.py` | Sí | ✅ | Guarda ping en BD; responde saltos o "via MQTT". |
| `/chiste [add\|help …]` | `Commands/chiste.py` | Sí | ✅ | Aleatorio, alta (`need_approve`+`need_upload`) o ayuda. |
| `/maremoto` | `Commands/maremoto.py` | Sí | ✅ | Años/meses/días desde 1/11/1755. |
| `/weather` | `Commands/weather.py` | No | ✅ | Tiempo actual desde BD (`aemet_weather`, cron AEMET). |
| `/tiempo` | (alias → `weather.py`) | Sí | ✅ | Mismo callback que `/weather`, pero accesible en canal. |
| `/prevision` | `Commands/prevision.py` | Sí | ✅ | Previsión multi-día municipal. BD-first + fallback en vivo. |
| `/avisos` | `Commands/avisos.py` | Sí | ✅ | Últimas alertas AEMET (tabla `aemet`), ventana 48 h. |
| `/marea` | `Commands/marea.py` | Sí | ✅ | Extremos de marea desde `tides`; fallback en vivo/estimación. |
| `/sol` | `Commands/sol.py` | Sí | ✅ | Orto/ocaso/duración (offline, `Models/Astro.py`). |
| `/luna` | `Commands/luna.py` | Sí | ✅ | Fase e iluminación (offline, `Models/Astro.py`). |
| `/nodos` | `Commands/nodos.py` | Sí | ✅ | Total/RF/MQTT/activos 24h desde `nodes`. |
| `/snr` | `Commands/snr.py` | Sí | ✅ | SNR del nodo pasarela + media RF. |
| `/stats` | `Commands/stats.py` | Sí | ✅ | Comandos, pings, nodos, encuestas y uptime. |
| `/encuesta …` | `Commands/encuesta.py` | Sí | ✅ | Encuestas comunitarias (subcomandos abajo). |
| `/dado [NdM]` | `Commands/dado.py` | Sí | ✅ | 1d6 por defecto; admite `N` caras o `NdM`. |
| `/bola8` (`/8ball`) | `Commands/bola8.py` | Sí | ✅ | Bola 8 mágica; `8ball` es alias `hidden`. |
| `/uptime` | `Commands/uptime.py` | No | 🟡 | Responde `N/D`. |
| `/ia` | `Commands/ia.py` | Sí | 🟡 | "funcionalidad en desarrollo". |

## Referencia de los comandos nuevos

### Información de la malla

- **`/nodos`** — Resumen: `Nodos: 42 (38 RF, 4 MQTT). Activos 24h: 12.` Lee la
  tabla `nodes` (persistente). "RF" = nodos no recibidos por MQTT; "activos" usa
  `last_heard` (epoch) en las últimas 24 h.
- **`/snr`** — Calidad de señal. Muestra primero el SNR del **nodo pasarela**
  (azotea) identificado por su nombre corto en `MESH_GATEWAY_SHORT_NAME`
  (def. `RAU0`) y luego la **media de SNR** del resto de nodos RF (excluye MQTT).
  Ej.: `SNR RAU0: 8.5 dB (1 hops). Media malla RF: 6.2 dB (38 nodos).`
- **`/stats`** — `Comandos: 12 hoy / 540 total. top /ping (210). pings 188.
  nodos 42 (38 RF/4 MQTT). encuestas activas 1. encendido 3d 4h 12m.`

### Meteorología y mar (AEMET / Open-Meteo, offline-first)

- **`/weather`** y **`/tiempo`** — Tiempo actual. Sirven el último registro de
  `aemet_weather` (scope `province`/`city`) descargado por el cron. `/tiempo` es
  un alias accesible en canal (`in_group=True`).
- **`/prevision`** — Previsión municipal de varios días (`AEMET_FORECAST_DAYS`).
  Estrategia: (1) lee `aemet_weather` scope `forecast`; (2) si falta o tiene
  >12 h, descarga en vivo de AEMET y cachea; (3) último recurso, el texto de
  `/weather`. La descarga en vivo se limita a una vez cada
  `ONDEMAND_REFRESH_MIN` min (def. 10) y con timeout bajo (4 s), para no
  bloquear el hilo de recepción en cada uso.
- **`/avisos`** — Últimas alertas AEMET de la provincia desde la tabla `aemet`
  (las descarga el cron). No hace peticiones en vivo.
- **`/marea`** — Próximas pleamares/bajamares de la ubicación (`LOCATION_*`).
  Estrategia: (1) lee la última fila de `tides` (cron); (2) si no hay 2 extremos
  futuros, calcula on-demand. Fuente real → WorldTides (`TIDES_API_KEY`) u
  Open-Meteo Marine; sin Internet → **estimación astronómica** marcada `~`. La
  consulta de red on-demand se limita a una vez cada `ONDEMAND_REFRESH_MIN` min
  (def. 10) y con timeout bajo (4 s); entre medias se usa la estimación offline.

### Astronomía (100% offline, `Models/Astro.py`)

- **`/sol`** — `Sol Chipiona: orto 07:10, ocaso 21:49, día 14h39m.` Algoritmo
  solar NOAA; usa `LOCATION_LAT/LON/TZ`.
- **`/luna`** — `Luna: Gibosa creciente, 78% iluminada (creciente). Llena: 12/07.
  Nueva: 26/07.` Edad lunar respecto al mes sinódico.

### Juegos

- **`/dado`** — `/dado` (1d6), `/dado 20` (un d20), `/dado 2d6` (suma + desglose).
  Límites: 1-10 dados, 2-1000 caras.
- **`/bola8`** (alias `/8ball`) — Respuesta aleatoria de "bola 8 mágica" (sí/no).

### `/encuesta` — Encuestas comunitarias

Persistencia en `encuestas` (+ `encuesta_votos`). Reglas:

- Cada **nodo dueño** puede tener **una sola encuesta activa** a la vez.
- **Cualquier nodo** puede votar cualquier encuesta; el voto se guarda por
  `node_id` y **se puede cambiar** (vuelve a votar otra opción y se actualiza).
- **Duración**: entre **1 y 30 días** (7 por defecto). Al pasar `ends_at` la
  encuesta se **cierra automáticamente** (de forma perezosa, al consultarla).
- **Solo el dueño** puede **cerrar** o **borrar** su encuesta. Ver resultados es
  público.

Subcomandos:

| Sintaxis | Quién | Efecto |
|---|---|---|
| `/encuesta` o `/encuesta lista` | todos | Lista encuestas activas con su `#id`. |
| `/encuesta nueva ¿Pregunta? \| op1 \| op2 [\| …] [dias=N]` | todos | Crea encuesta (2-6 opciones; `dias` 1-30, def. 7). |
| `/encuesta voto <id> <nº>` | todos | Vota/cambia el voto a la opción `nº` (1-based). |
| `/encuesta ver <id>` | todos | Resultados y porcentajes. |
| `/encuesta cerrar <id>` | dueño | Finaliza la encuesta y muestra resultados. |
| `/encuesta borrar <id>` | dueño | Elimina la encuesta y sus votos. |
| `/encuesta ayuda` | todos | Muestra la ayuda de uso. |

Ejemplo de creación: `/encuesta nueva ¿Quedada el sábado? | Sí | No | Tal vez dias=5`
→ `Encuesta #5 creada (5 día(s)): … Vota con /encuesta voto 5 <nº>.`

> El token `dias=N` (o `dias:N`) puede ir en cualquier punto del texto: se extrae
> antes de separar la pregunta y las opciones por `|`.

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

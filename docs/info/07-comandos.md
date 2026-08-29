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
            └─ sí → ¿via_mqtt?  o  ¿hops <= local_hop_limit + 1?
                      └─ sí → callback(interface, args, msg, metadata)
                      └─ no → se omite respuesta (ahorro de AirTime en la malla)
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

| Comando | Fichero | `in_group` | Estado | Sintaxis y Opciones |
|---|---|---|---|---|
| `/help [cmd]` | `Commands/help.py` | No | ✅ | Lista todos los comandos o detalla el uso y opciones de `/help <cmd>`. |
| `/about` | `Commands/about.py` | No | ✅ | Información fija del proyecto, hardware y autor. |
| `/ping` (`/test`) | `Commands/ping.py` | Sí | ✅ | Comprueba conectividad, saltos, RSSI y SNR. |
| `/weather` (`/tiempo`) | `Commands/weather.py` | Sí | ✅ | `/tiempo` (día completo), `/tiempo real` (estación física) o `/tiempo <provincia>`. |
| `/prevision` | `Commands/prevision.py` | Sí | ✅ | `/prevision` (3 días), `/prevision mañana`, `/prevision <1-7> dias` o `/prevision <1-12> horas`. |
| `/marea` | `Commands/marea.py` | Sí | ✅ | `/marea` (pleamares y bajamares del día) o `/marea mar` / `/marea costa` (boletín costero Cádiz). |
| `/avisos` | `Commands/avisos.py` | Sí | ✅ | Alertas oficiales activas para la provincia con color (*Amarillo/Naranja/Rojo*), fenómeno y vigencia. |
| `/sol` | `Commands/sol.py` | Sí | ✅ | Orto, ocaso y duración solar del día (offline). |
| `/luna` | `Commands/luna.py` | Sí | ✅ | Fase lunar actual, porcentaje iluminado y próximas fases (offline). |
| `/boletin [tipo]` | `Commands/boletin.py` | Sí | ✅ | `/boletin [matinal\|vespertino]` (resumen sol, luna, tiempo provincial, mareas y avisos). |
| `/nodos` | `Commands/nodos.py` | Sí | ✅ | Conteo de nodos descubiertos (total, RF, MQTT y activos 24h). |
| `/snr` | `Commands/snr.py` | Sí | ✅ | SNR del nodo pasarela y media de la malla RF. |
| `/routers` (`/repetidores`) | `Commands/routers.py` | Sí | ✅ | Estado de routers/repetidores (actividad, tramos SNR y saltos). |
| `/estado` (`/status`, `/salud`) | `Commands/estado.py` | Sí | ✅ | Telemetría y salud de la Raspberry Pi y nodo (temperatura, RAM, CPU, disco). |
| `/chiste [add]` | `Commands/chiste.py` | Sí | ✅ | `/chiste` (aleatorio) o `/chiste add <texto>` (proponer chiste). |
| `/encuesta …` | `Commands/encuesta.py` | Sí | ✅ | Encuestas comunitarias (`/encuesta nueva`, `voto`, `ver`, `lista`, `cerrar`). |
| `/ia [pregunta]` | `Commands/ia.py` | Sí | ✅ | Asistente de IA mínima para consultas de emergencia (cola RAG). |
| `/dado [NdM]` | `Commands/dado.py` | Sí | ✅ | Tirada de dados (1d6 por defecto, N caras o formato NdM). |
| `/bola8` (`/8ball`) | `Commands/bola8.py` | Sí | ✅ | Bola 8 mágica para preguntas de sí/no. |
| `/maremoto` | `Commands/maremoto.py` | Sí | ✅ | Tiempo transcurrido desde el maremoto de 1755 en Chipiona. |
| `/uptime` | `Commands/uptime.py` | No | ✅ | Tiempo en funcionamiento continuo del bot. |

---

## Detalle de Comandos Meteorológicos y Marítimos

### `/tiempo` (alias `/weather`)
* **Uso estándar:** `/tiempo` o `/weather`
  * Devuelve la predicción meteorológica completa para el **día actual** (texto oficial de AEMET para la jornada + resumen de temperaturas mín/máx, cielo y lluvia).
* **Medición física en vivo:** `/tiempo real` o `/tiempo ahora`
  * Muestra la última medición registrada por la estación meteorológica física de AEMET más cercana (Cádiz / Rota): temperatura real, velocidad del viento, racha máxima, humedad relativa y presión barométrica.
* **Otras provincias:** `/tiempo <provincia>`
  * Permite consultar el pronóstico de cualquier provincia de Andalucía (ej: `/tiempo sevilla`, `/tiempo malaga`).

### `/prevision`
* **Por defecto (3 días):** `/prevision`
  * Muestra la previsión resumida para los próximos **3 días** (temperaturas mín/máx, estado del cielo y probabilidad de lluvia).
* **Mañana:** `/prevision mañana`
  * Devuelve el pronóstico específico para el día siguiente con temperaturas, cielo, probabilidad de lluvia, viento y radiación UV.
* **Multi-día:** `/prevision <1-7> dias` (ej: `/prevision 4 dias`, `/prevision 7 dias`)
  * Devuelve la previsión para el número de días indicado (acotado automáticamente entre 1 y 7 días).
* **Horaria / Subdiaria:** `/prevision <1-12> horas` (ej: `/prevision 6 horas`, `/prevision 12h`)
  * Devuelve la evolución cronológica por tramos horarios a partir de la hora actual (temperatura, cielo y lluvia).

### `/marea`
* **Mareas del día:** `/marea`
  * Devuelve las pleamares y bajamares del día actual con sus horas y alturas (m) para la costa local.
* **Boletín costero:** `/marea mar` o `/marea costa`
  * Devuelve el boletín marítimo costero oficial de AEMET (Costa 42 - Andalucía Occidental / Cádiz): dirección y fuerza del viento (escala Beaufort), estado de la mar (*Marejadilla/Marejada*), mar de fondo (m) y visibilidad.

### `/avisos`
* **Alertas meteorológicas oficiales:** `/avisos`
  * Consulta las alertas vigentes emitidas por Meteoalerta / CAP para la provincia, indicando nivel de gravedad (*Amarillo, Naranja, Rojo*), fenómeno meteorológico y hora de expiración.


## Referencia de los comandos nuevos

### Información de la malla

- **`/nodos`** — Resumen: `Nodos: 42 (38 RF, 4 MQTT). Activos 24h: 12.` Lee la
  tabla `nodes` (persistente). "RF" = nodos no recibidos por MQTT; "activos" usa
  `last_heard` (epoch) en las últimas 24 h.
- **`/snr`** — Calidad de señal. Muestra primero el SNR del **nodo pasarela**
  (azotea) identificado por su nombre corto en `MESH_GATEWAY_SHORT_NAME`
  (def. `RAU0`) y luego la **media de SNR** del resto de nodos RF (excluye MQTT).
  Ej.: `SNR RAU0: 8.5 dB (1 hops). Media malla RF: 6.2 dB (38 nodos).`
- **`/routers`** (alias **`/repetidores`**) — Informa del estado de los nodos routers/repetidores
  cercanos (máximo `ROUTER_MAX_HOPS` saltos, por defecto 2) configurados en `ROUTER_NODES` de `env.py`
  o con rol oficial `ROUTER`/`ROUTER_LATE`/`REPEATER`.
  * **Tiempo:** Transcurrido desde el último contacto (`last_heard`/`updated_at`), ej. `26m`, `2h`. Si supera 24h, los configurados se marcan `[CA12 | offline]` y los auto-detectados se omiten.
  * **Saltos:** Calculados a partir del traceroute exterior desde la base `RAU0` (0 hops = directo, 1 hop = 1 repetidor intermedio, etc.).
  * **SNR:** Si existe un traceroute previo (`status='done'`), muestra los SNRs reales medidos en cada tramo del enlace exterior (ej. directo `(5.2dB)` o con salto intermedio `(9.0dB, 9.2dB)`). Si el enlace es directo con el bot/base, muestra la señal directa. Si vino repetido y aún no hay traceroute, omite el SNR para no falsear datos.
  * **Límite de mensajes:** Ampliado hasta 5 mensajes (`ROUTERS_MAX_PARTS = 5`).
  * Formato: `Routers: [RAU0: 2m - 0 hops(12.5dB)], [CA13: 26m - 0 hops(5.2dB)], [CO14: 2h - 1 hop(9.0dB, 9.2dB)], [CA03: 21h - 1 hop], [CA04 | offline]`
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

### Asistente de Emergencias IA (RAG en Raspberry Pi 5)

- **`/ia <pregunta>`** o **`!ia <pregunta>`** — Consulta al asistente RAG de emergencias.
  - **Cola Secuencial FIFO:** El bot procesa 1 sola inferencia a la vez hacia la API de la Pi 5. Si llegan peticiones simultáneas, se encolan automáticamente en un hilo independiente sin bloquear la recepción de la radio Meshtastic.
  - **Memoria por Nodo:** Cada emisor (`from_id`) mantiene su propio contexto conversacional multi-turno durante 1 hora.
  - **`/ia reset`** (o `/ia nueva`) — Limpia el historial de la conversación para ese nodo en el servidor.
  - **Mensajes LoRa:** Las respuestas vienen limitadas a $\le 230$ bytes UTF-8 por mensaje (máximo 3 partes) y se transmiten con pausas defensivas de 2.5s entre partes.
  - **Tolerancia a Fallos:** Si la API no responde o da timeout, responde por radio: `"Servidor IA de @raupulus no disponible en este momento."`

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

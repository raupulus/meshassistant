# 09 · AEMET (alertas meteorológicas)

Descarga avisos meteorológicos de **AEMET OpenData** (formato CAP), los guarda en BD
y los **publica en canales Meshtastic** dentro de una ventana horaria. Solo se activa
si `AEMET_API_KEY` tiene valor.

## Componentes

- **`Models/Aemet.py`** — cliente HTTP + reglas de publicación (ventana horaria,
  periodo por canal).
- **`cron_tasks.py`** — descarga (`check_aemet`, `fetch_aemet_alerts_archive`,
  `fetch_aemet_alerts_for_province`).
- **`Models/Database.py`** — almacenamiento, dedup y parseo CAP (`aemet_*`,
  `_parse_cap_es`).
- **`main.py`** — publicación en la malla.

## Descarga (cron) — `check_aemet()`

1. Cooldown: máximo **1 vez/hora** (`tasks_control['aemet_fetch']`).
2. Si no hay `AEMET_API_KEY`, no consulta.
3. One-shot `_aemet_fix_legacy_once()` (migra filas antiguas con XML crudo).
4. Vía principal: **archivo por rango temporal** `fetch_aemet_alerts_archive` —
   descarga un `tar.gz` con XMLs CAP de hoy/mañana y **filtra por provincia/CCAA**.
5. Fallback: `fetch_aemet_alerts_for_province` (endpoints `ultimoelaborado` por
   `/provincia/{códigoINE}` o `/area/{NOMBRE}`, con mapas nombre→código).
6. `Database.aemet_bulk_insert(province, texts)` parsea y guarda.

> El flujo OpenData es de **dos pasos**: el primer GET devuelve un JSON con un campo
> `datos` (URL); el segundo GET a esa URL trae el documento real (XML o tar.gz).

## Parseo CAP — `Database._parse_cap_es`

Extrae el bloque `<info>` en español de un XML **CAP 1.2** y compone dos textos:

- `data_raw` (alert_text): breve — `headline` + descripción.
- `message` (publish_text): completo — evento + nivel, área, ventana temporal,
  probabilidad, descripción, instrucción y URL de aemet.es.

Campos leídos: `event`, `headline`, `description`, `instruction`, `onset`,
`expires`, `senderName`, `web`, `areaDesc` y parámetros (`nivel`, `probabilidad`,
`fenomeno`). Las respuestas JSON de error de AEMET (`estado != 200`) se descartan.

## Almacenamiento y dedup

- `aemet_insert_alert` calcula `data_hash = SHA-256(message|data_raw)` y usa la
  restricción `UNIQUE` para **evitar duplicados**.
- Textos saneados con `sanitize_text` antes de guardar (nunca se almacena XML crudo).

## Publicación (main.py loop)

Solo si hay `AEMET_API_KEY` y la hora está dentro de la ventana
(`Aemet.is_within_hour_window`, admite cruce de medianoche):

1. `aemet_get_next_unpublished()` — siguiente alerta `published=0`.
2. Para cada canal de `AEMET_CHANNELS`, comprueba el **periodo por canal** mirando
   `tasks_control['aemet_publish_ch_<canal>']` vs. `period_to_minutes(AEMET_PERIOD)`.
3. Construye el mensaje respetando **~200 caracteres**: 1 mensaje si cabe, o **2
   partes** (`AEMET 1/2:` / `AEMET 2/2:`) con enlace a aemet.es en la segunda, con 5 s
   entre partes.
4. Envía con `interface.send(msg, dest='^all', channel=ch)`.
5. Marca el periodo por canal (`set_task_run`) y, si se envió a algún canal, marca la
   alerta como publicada (`aemet_mark_published`).

## Periodicidad — `Aemet.period_to_minutes`

| `AEMET_PERIOD` | Minutos |
|---|---|
| `Hour` | 60 |
| `Three_hour` | 180 |
| `Six_hour` | 360 |
| `Twelve_hour` | 720 |
| `Day` | 1440 |

## Clima / predicción (`/weather`)

Independiente de los avisos CAP. Descarga la **predicción meteorológica** y la
guarda como histórico en la tabla `aemet_weather`, para que el comando `/weather`
la sirva **offline** desde BD (sin llamar a la API en tiempo de comando).

- **Cadencia de descarga**: según `AEMET_PERIOD` (mismo helper
  `period_to_minutes`), no fija. Tarea cron `weather_aemet()` (control en
  `tasks_control['aemet_weather_fetch']`). Solo si hay `AEMET_API_KEY`.
- **Fuente principal — provincia (texto general)**:
  `GET /prediccion/provincia/hoy/{códigoINE2}` (flujo OpenData de 2 pasos →
  devuelve **texto plano** de toda la provincia). Código resuelto desde
  `AEMET_PROVINCE` (`Aemet.province_code`). Se le retira la cabecera burocrática
  (agencia, "DÍA … HORA OFICIAL", "VÁLIDA PARA …") y se queda solo con el
  pronóstico, sin fechas ni etiquetas. Conexión con reintento SSL `verify=False`
  (el certificado de AEMET falla en muchos sistemas).
- **Fallback — municipio**: si la provincia no devuelve datos,
  `GET /prediccion/especifica/municipio/diaria/{códigoINE5}` (JSON) formateado a
  un texto breve (temperaturas, estado del cielo, prob. de lluvia). El municipio
  se define con `AEMET_CITY` (display) y `AEMET_CITY_CODE` (INE 5 dígitos, p.ej.
  Chipiona = `11015`); si falta el código se intenta resolver por nombre.
- **Comando `/weather`**: lee el último registro de `aemet_weather` y responde
  troceando el texto en **1–2 mensajes de ~200 caracteres** (límite Meshtastic).

### Variables de entorno (clima)

| Variable | Ejemplo | Descripción |
|---|---|---|
| `AEMET_PROVINCE` | `Cadiz` | Provincia (nombre o código INE 2 dígitos) |
| `AEMET_CITY` | `Chipiona` | Municipio de fallback (nombre para mostrar) |
| `AEMET_CITY_CODE` | `11015` | Código INE de 5 dígitos del municipio (`''` = autodetectar) |
| `AEMET_PERIOD` | `Hour` | Cadencia de descarga del clima y de publicación de avisos |

## Notas

- La provincia puede ser nombre (`Cádiz`) o, para Galicia, una CCAA con mapa a sus
  provincias. Para otras CCAA habría que ampliar los mapas en `cron_tasks.py`.
- `Aemet` usa la cabecera `api_key`; los timeouts son cortos (5–20 s) y hay
  reintentos.

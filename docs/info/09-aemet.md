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

1. Cooldown: según `AEMET_PERIOD` (`tasks_control['aemet_fetch']`).
2. Si no hay `AEMET_API_KEY`, no consulta.
3. One-shot `_aemet_fix_legacy_once()` (migra filas antiguas con XML crudo).
4. Vía principal: **área C.A. EMMA** `fetch_aemet_alerts_for_province` —
   descarga el archivo TAR de la Comunidad Autónoma (`.../ultimoelaborado/area/{ccaa_code}`,
   p. ej. `61` para Andalucía / Cádiz) de forma instantánea (<0.2s), desempaqueta
   los XMLs en memoria y filtra por geocode EMMA (`6111xx` para Cádiz) y comarcas.
   Fallback a `area/esp` si falla el área específica.
5. Fallback secundario: `fetch_aemet_alerts_archive` (rango temporal de 2 días).
6. `Database.aemet_bulk_insert(province, texts)` parsea y guarda (descartando `nivel verde`).

> El flujo OpenData es de **dos pasos**: el primer GET devuelve un JSON con un campo
> `datos` (URL); el segundo GET a esa URL trae el contenedor real (archivo TAR con los XMLs CAP).

## Parseo CAP — `Database._parse_cap_es`

Extrae el bloque `<info>` en español de un XML **CAP 1.2** y compone dos textos:

- `data_raw` (alert_text): breve — `headline` + descripción.
- `message` (publish_text): completo — evento + nivel, área, ventana temporal,
  probabilidad, descripción, instrucción y URL de aemet.es.

Campos leídos: `event`, `headline`, `description`, `instruction`, `onset`,
`expires`, `senderName`, `web`, `areaDesc` y parámetros (`nivel`, `probabilidad`,
`fenomeno`). Las respuestas JSON de error de AEMET (`estado != 200`) y los
avisos rutinarios de **`nivel verde` (sin riesgo)** se descartan automáticamente.

## Almacenamiento y dedup

- `aemet_insert_alert` calcula `data_hash = SHA-256(message|data_raw)` y usa la
  restricción `UNIQUE` para **evitar duplicados**.
- Textos saneados con `sanitize_text` antes de guardar (nunca se almacena XML crudo).

## Publicación (main.py loop)

Solo si hay `AEMET_API_KEY` y la hora está dentro de la ventana
(`Aemet.is_within_hour_window`, admite cruce de medianoche):

1. **Cadencia entre emisiones (`AEMET_PERIOD`):** Para cada canal en `AEMET_CHANNELS`, comprueba `tasks_control['aemet_publish_ch_<canal>']` contra el periodo configurado (`Hour`, `Three_hour`, `Six_hour`, `Day`).
2. **Deduplicación diaria de alertas idénticas:** Al procesar la cola de alertas pendientes, si una alerta contiene el mismo fenómeno meteorológico (`data_raw`) que ya fue publicado hoy en esa provincia/canal (`aemet_is_same_alert_published_today`), se marca como procesada automáticamente sin re-emitir duplicados por la radio.
3. **Emisión de alertas diferentes:** Todas las alertas de fenómenos, zonas o niveles distintos (ej. lluvia en Grazalema y viento en Litoral, o escalado a naranja) **se emiten íntegramente**, respetando la cadencia de `AEMET_PERIOD` entre emisiones para no saturar la malla.
4. **Formato multi-mensaje LoRa:** Se construyen mensajes respetando el estándar Meshtastic de **hasta ~200 bytes por paquete** (hasta 3 partes con cabecera `AEMET i/n:` y pausa de 2.5s entre partes).
5. Tras completar la emisión a los canales configurados, marca la alerta como publicada (`aemet_mark_published`) y registra la marca de tiempo por canal (`set_task_run`).

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

### Variables de entorno (clima y marítimo)

| Variable | Ejemplo | Descripción |
|---|---|---|
| `AEMET_PROVINCE` | `Cadiz` | Provincia (nombre o código INE 2 dígitos). |
| `AEMET_CITY` | `Chipiona` | Municipio de fallback (nombre para mostrar). |
| `AEMET_CITY_CODE` | `11016` | Código INE de 5 dígitos del municipio (`''` = autodetectar). |
| `AEMET_PERIOD` | `Hour` | Cadencia de descarga del clima y de publicación de avisos. |
| `AEMET_EXPIRY_WARNING_DAYS` | `10` | Días antes de la caducidad del JWT para emitir alerta. |
| `AEMET_EXPIRY_WARNING_CHANNELS` | `['raupulus']` | Canales donde avisar de la caducidad de la clave. |
| `AEMET_MARITIME_COAST_CODE` | `'42'` | Código de costa AEMET (42 = Andalucía Occidental / Cádiz). |
| `AEMET_OBSERVATION_STATION` | `'5972X'` | Código de estación meteorológica física de observación. |

---

## 8. Módulos y Comandos Extendidos de AEMET

### 8.1. Control de Caducidad de API Key (JWT)
* La API Key de AEMET OpenData es un token JWT que caduca a los 100 días.
* `Models/Aemet.py::check_api_key_expiry()` decodifica el payload en base64 de forma offline para obtener la fecha exacta de expiración.
* La tarea cron `check_aemet_key_expiry()` envía un aviso diario por los canales configurados cuando quedan $\le 10$ días para expirar o si ya caducó.

### 8.2. Predicción Multi-día y Horaria (`/prevision`)
* Descargada cada 3 horas (`weather_forecast_aemet`) en `aemet_forecast_daily` y `aemet_forecast_hourly`.
* Soporta: `/prevision` (3 días), `/prevision mañana`, `/prevision <1-7> dias` y `/prevision <1-12> horas`.

### 8.3. Boletín Marítimo Costero (`/marea mar`)
* Descargado a las **12:05 y 20:05** (5 min tras la emisión oficial) con **3 reintentos** cada 10 min en caso de error.
* Extrae viento (Beaufort), estado de la mar, mar de fondo y visibilidad de la subzona gaditana (*Del Guadalquivir al Cabo Roche*).

### 8.4. Medición Física en Tiempo Real (`/tiempo real`)
* Descarga horaria de la estación física configurada (`5972X` Cádiz / San Fernando o `5960X` Rota).
* Muestra temperatura real, velocidad del viento, racha máxima, humedad relativa y presión barométrica.

---

## Notas

- La provincia puede ser nombre (`Cádiz`) o código INE (`11`).
- `Aemet` usa la cabecera `api_key`; los timeouts son cortos (5–20 s) con reintentos y monitorización de cuota con `Remaining-request-endpoint`.


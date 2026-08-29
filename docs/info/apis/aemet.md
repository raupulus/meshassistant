# Integración de AEMET OpenData en MeshAssistant

Este documento describe **cómo esta aplicación consume e integra la API de AEMET OpenData**, sus modelos, tareas cron, esquemas en base de datos y comandos asociados.

> Para la documentación oficial externa de AEMET (especificaciones de endpoints, parámetros y limitaciones de terceros), consultar `docs/apis/aemet/`.

---

## 1. Arquitectura de Integración

La comunicación con AEMET OpenData se rige por los siguientes principios:

1. **Desacoplamiento Serie/Red:** Las peticiones HTTP a AEMET se realizan de forma asíncrona y periódica en `cron_tasks.py`. `main.py` y los comandos de la radio leen prioritariamente desde **SQLite** (`database.sql`) para responder con latencia cero a la malla Meshtastic.
2. **Patrón OpenData Two-Step:** Todas las consultas a la API de AEMET constan de 2 pasos (`Models/Aemet.py`):
   - Paso 1: `GET <path>?api_key=<key>` → devuelve `{ estado: 200, datos: "<url_documento>" }`.
   - Paso 2: `GET <url_documento>` → descarga el JSON/XML real.
3. **Control de Cuota:** Se monitoriza la cabecera `Remaining-request-endpoint` en cada llamada para registrar el volumen restante de peticiones en el endpoint consultado.

---

## 2. Monitorización y Expiración de la API Key

* **Formato del Token:** La clave de AEMET es un **JSON Web Token (JWT)** con validez real de **100 días**.
* **Decodificación Offline:** En `Models/Aemet.py` (`parse_jwt_payload` y `check_api_key_expiry`), se extrae el timestamp `exp` del payload base64url sin librerías externas.
* **Alerta Preventiva en Cron (`cron_tasks.check_aemet_key_expiry`):**
  - Se ejecuta diariamente.
  - Cuando faltan $\le 10$ días para la expiración (o si ya caducó / responde 401), genera **un único mensaje diario** encolado en `outbox` hacia los canales configurados (`AEMET_EXPIRY_WARNING_CHANNELS = ['raupulus']` o canal 6).
  - Texto: `⚠️ [AEMET] Tu API Key caduca en X días (YYYY-MM-DD). Renuévala en opendata.aemet.es.`

---

## 3. Estrategia de Descarga y Cron

| Tarea Cron | Función en `cron_tasks.py` | Cadencia y Horarios | Tablas SQLite |
|---|---|---|---|
| **Avisos CAP** | `check_aemet()` | Según `AEMET_PERIOD` (def. 1-3 h) | `aemet` |
| **Tiempo Hoy/Mañana** | `weather_aemet()` | Según `AEMET_PERIOD` (def. 1-3 h) | `aemet_weather` |
| **Predicción Multi-día & Horaria** | `weather_forecast_aemet()` | Cada 3 horas (`180 min`) | `aemet_forecast_daily`, `aemet_forecast_hourly` |
| **Boletín Marítimo Costero** | `maritime_aemet()` | **12:05 y 20:05** (5 min tras emisión) con **3 reintentos** cada 10 min en caso de error (`:15`, `:25`, `:35`) | `aemet_maritime` |
| **Observación Física Estación** | `observation_aemet()` | Cada 60 minutos | `aemet_observation` |

---

## 4. Esquema de Base de Datos

Las tablas dedicadas a AEMET en SQLite son:

* `aemet`: Histórico de avisos meteorológicos CAP procesados.
* `aemet_weather`: Textos oficiales provincial y municipal para hoy y mañana (`day='hoy'|'manana'`).
* `aemet_forecast_daily`: Predicción estructurada a 7 días (temperaturas, probabilidad de lluvia, viento, UV).
* `aemet_forecast_hourly`: Predicción estructurada horaria para las próximas 24-48 horas.
* `aemet_maritime`: Boletines costeros oficiales de Andalucía Occidental / Costa de Cádiz (Costa 42).
* `aemet_observation`: Mediciones físicas reales de estaciones de observación (Cádiz 5972X, Rota 5960X).

---

## 5. Comandos de la Malla

* `/tiempo` (`/weather`): Devuelve la predicción completa del día actual. Con `/tiempo real` devuelve la estación física.
* `/prevision`: Previsión flexible (`/prevision` 3 días, `/prevision mañana`, `/prevision <1-7> dias`, `/prevision <1-12> horas`).
* `/marea`: Pleamares y bajamares del día actual. Con `/marea mar` o `/marea costa` muestra el boletín costero de Cádiz.
* `/avisos`: Avisos meteorológicos vigentes con indicación de nivel (*Amarillo/Naranja/Rojo*), fenómeno y hora de finalización.

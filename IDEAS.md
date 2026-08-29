# Ideas e Implementaciones Futuras

Registro detallado de propuestas, arquitectura y especificaciones funcionales para futuras mejoras del proyecto **meshassistant**. Cada sección describe el módulo con el nivel de detalle necesario para su posterior evaluación, ajuste o desarrollo.

---

## Índice de propuestas

1. [Módulo 01 · Previsión meteorológica: Migración a Meteo Rota](#módulo-01--previsión-meteorológica-migración-a-meteo-rota)
2. [Módulo 02 · Previsión meteorológica extendida (2–3 días)](#módulo-02--previsión-meteorológica-extendida-23-días)
3. [Módulo 03 · Boletín diario automático en canal público](#módulo-03--boletín-diario-automático-en-canal-público)
4. [Módulo 04 · Mensajes programables desde la Web (Cola de difusión)](#módulo-04--mensajes-programables-desde-la-web-cola-de-difusión)
5. [Módulo 05 · Telemetría y salud de la Raspberry Pi / Bot](#módulo-05--telemetría-y-salud-de-la-raspberry-pi--bot)
6. [Módulo 06 · Control de saturación, anti-abuso y bloqueos con gestión Web](#módulo-06--control-de-saturación-anti-abuso-y-bloqueos-con-gestión-web)

---

## Módulo 01 · Previsión meteorológica: Migración a Meteo Rota

### 1. Objetivo y Necesidad
Sustituir el origen de datos de predicción meteorológica actual (AEMET OpenData) por **Meteo Rota** (estación/servicio meteorológico local de referencia en la comarca Rota-Chipiona). 
- AEMET a menudo entrega textos provinciales genéricos poco precisos para la costa local y con redacciones extensas difíciles de adaptar a LoRa.
- Meteo Rota ofrece predicciones hiperlocales, redactadas de forma más clara, directa y estructurada para la zona.

### 2. Componentes involucrados
- **`Models/MeteoRota.py`**: Cliente de descarga y parseo (vía web scraping / API / RSS según disponibilidad) con extracción limpia de temperatura, viento, probabilidad de precipitación y estado del cielo.
- **`cron_tasks.py`**: Tarea periódica (`weather_meteorota()`) que descarga la predicción según la cadencia configurada y la guarda en BD.
- **`Models/Database.py`**: Métodos para guardar y obtener la última predicción almacenada (`save_weather_prediction`, `get_latest_weather_prediction`).
- **`Commands/weather.py` / `Commands/prevision.py`**: Comandos que leen de la BD local y devuelven la respuesta formateada en modo 100% offline.

### 3. Flujo de datos
```
Internet ──► [cron_tasks.py] ──► [Models/MeteoRota.py] ──► [SQLite: aemet_weather / meteo_weather]
                                                                     │
Malla LoRa (/weather) ◄── [Commands/weather.py] ◄────────────────────┘ (Lectura offline)
```

### 4. Formato de salida y límites LoRa
- **Límite:** 1 solo paquete LoRa (~160–180 bytes) para `/weather`.
- **Estructura ejemplo:**
  ```text
  🌦️ Meteo Rota (Chipiona/Rota)
  Hoy: Soleado con intervalos nubosos.
  🌡️ 16°C / 23°C | 💨 Viento: SO 15-25 km/h
  🌧️ Lluvia: 10%
  ```

### 5. Configuración (`env.py`)
- `WEATHER_PROVIDER = "meteorota"` (o selector `"aemet" | "meteorota"`).
- `WEATHER_FETCH_INTERVAL_HOURS = 3` (horas entre descargas en cron).

### 6. Consideraciones y Casos borde
- Si la web de Meteo Rota no responde o cambia su estructura HTML, fallback automático a los datos en caché de SQLite. Si llevan más de 24h obsoletos, opcionalmente recurrir a AEMET/Open-Meteo como respaldo.

---

## Módulo 02 · Previsión meteorológica extendida (2–3 días)

### 1. Objetivo y Necesidad
Permitir a los usuarios de la malla consultar una previsión a corto plazo (hoy, mañana y pasado mañana) mediante un comando dedicado (o ampliando `/prevision`), especialmente útil para actividades al aire libre, navegación o emergencias sin conexión a Internet.

### 2. Componentes involucrados
- **`Models/MeteoRota.py` (o fallback Open-Meteo/AEMET)**: Parser que extraiga la previsión desglosada por días (temperaturas mín/máx, estado del cielo, probabilidad de lluvia y viento).
- **`Models/Database.py`**: Almacenamiento estructurado del pronóstico multijornada en SQLite.
- **`Commands/prevision.py`**: Lógica de formateo ultra-condensado y particionado.

### 3. Formato de salida y límites LoRa
Para no saturar la malla, la previsión a 3 días debe ajustarse estrictamente a **1 o máximo 2 mensajes LoRa**, empleando iconografía y abreviaturas claras.

- **Estructura ejemplo (1 mensaje ~180 bytes):**
  ```text
  📅 Previsión 3 días (Rota/Chipiona):
  • Hoy: ☀️ 16/23°C · V:SO 15km/h · 0%
  • Mañ: ⛅ 15/22°C · V:O 20km/h · 20%
  • Dom: 🌧️ 14/19°C · V:NO 35km/h · 85%
  ```

### 4. Configuración (`env.py`)
- `FORECAST_DAYS = 3` (número de días a proyectar).
- `FORECAST_MAX_PARTS = 2` (máximo número de paquetes LoRa para la respuesta).

---

## Módulo 03 · Boletín diario automático en canal público

### 1. Objetivo y Necesidad
Publicar automáticamente 1 o 2 veces al día (por ejemplo, matinal a las 08:00 y vespertino a las 20:00) un parte resumen de la jornada en los canales públicos configurados, proporcionando valor continuo a la comunidad de la malla sin requerir que nadie invoque comandos.

### 2. Componentes involucrados
- **`cron_tasks.py` / `main.py` (bucle `loop()`)**: Detección de la ventana horaria de publicación y control de ejecución mediante `tasks_control` para garantizar que se emite exactamente una vez por ventana.
- **`Models/Bulletin.py`**: Generador que agrega datos locales existentes:
  - Tiempo y previsión del día (`Models/MeteoRota.py`).
  - Próximas pleamares y bajamares del día (`Commands/marea.py` / `tides`).
  - Orto y ocaso solar (`Commands/sol.py`).
  - Alertas activas si las hubiera (`aemet`).
- **`SerialInterface.py`**: Envío de los paquetes broadcast a los canales seleccionados respetando pausas de 2.5s entre partes.

### 3. Formato de salida y límites LoRa
El boletín se diseñará en **2 partes (máximo 3)** claramente diferenciadas:
- **Parte 1 (Meteo + Sol):**
  ```text
  📢 [Boletín Matinal] ☀️ Chipiona
  Sol: 07:45 - 21:15 (13h 30m)
  Tiempo: Soleado, 17°C a 24°C, Viento O 15km/h. Sin lluvia.
  ```
- **Parte 2 (Mareas + Avisos):**
  ```text
  🌊 Mareas:
  • Pleamar: 04:12 (3.1m) | 16:35 (3.0m)
  • Bajamar: 10:20 (0.8m) | 22:45 (0.9m)
  ⚠️ Avisos: Sin alertas activas.
  ```

### 4. Configuración (`env.py`)
- `BULLETIN_ENABLED = True`
- `BULLETIN_CHANNELS = [0, 6]` (índices de canal donde emitir).
- `BULLETIN_HOURS = ["08:00", "20:30"]` (horarios programados).

---

## Módulo 04 · Mensajes programables desde la Web (Cola de difusión)

### 1. Objetivo y Necesidad
Permitir a los administradores programar anuncios, avisos informativos, balizas o mensajes comunitarios recurrentes directamente desde el dashboard web local, sin tocar ficheros de configuración ni reiniciar servicios.

### 2. Componentes involucrados
- **Base de datos (`scheduled_messages` / `queue`)**:
  - `id`: Identificador único.
  - `message`: Texto a transmitir (saneado y validado en longitud).
  - `channels`: Canales destino (lista JSON `[0, 2]`, canal único `3` o `"all"` para broadcast total).
  - `period_type`: Tipo de cadencia (`"hours"`, `"days"`, `"once"`).
  - `period_value`: Intervalo numérico (ej. cada `6` horas, cada `2` días).
  - `start_at`: Fecha y hora de inicio.
  - `last_sent_at`: Marca temporal del último envío.
  - `next_run_at`: Siguiente momento programado de disparo.
  - `enabled`: Booleano (1 = activo, 0 = pausado).
- **`Services/Gateway.py` (API REST / WebSocket)**:
  - Endpoints `GET /api/scheduled_messages`, `POST /api/scheduled_messages` (crear), `PUT /api/scheduled_messages/<id>` (editar/pausar), `DELETE /api/scheduled_messages/<id>`.
- **Panel Web (`web/index.html`, `web/app.js`)**:
  - Pestaña "Programación de Mensajes".
  - Formulario con caja de texto, contador dinámico de caracteres y advertencia de corte de 200 bytes.
  - Selector de canales: 8 casillas de verificación (Canal 0 al 7) + casilla "Todos".
  - Selector de frecuencia: "Una sola vez", "Cada X horas", "Cada X días".
  - Tabla de mensajes programados con interruptor de activar/desactivar y botón de eliminar.
- **`main.py` (`loop()`)**:
  - Consulta periódica (cada 30s) de mensajes vencidos (`next_run_at <= NOW() AND enabled = 1`).
  - Envío por `SerialInterface.send_to_channel()` y cálculo automático del siguiente `next_run_at`.

### 3. Consideraciones de seguridad y malla
- Restringir la longitud máxima a 3 partes LoRa (~500 bytes) y alertar en la interfaz web.
- Pausa obligatoria entre mensajes para no saturar el canal.

---

## Módulo 05 · Telemetría y salud de la Raspberry Pi / Bot

### 1. Objetivo y Necesidad
Supervisar el estado físico y operativo del bot (hardware de la Raspberry Pi y conexión con el nodo LoRa) de forma remota a través de la propia malla mediante un comando (`/estado` o ampliando `/stats`) y desde el panel web.

### 2. Métricas a recolectar (locales del bot, sin saturar la red)
- **Temperatura de la CPU**: Lectura de `/sys/class/thermal/thermal_zone0/temp` (en °C).
- **Carga de CPU**: Promedio de carga de 1 min / 5 min (`os.getloadavg()`).
- **Memoria RAM**: Uso actual y disponible (`psutil` o parseo directo de `/proc/meminfo` para evitar dependencias).
- **Almacenamiento**: Espacio libre en `/` para la base de datos SQLite (`shutil.disk_usage`).
- **Uptime**: Tiempo en servicio del sistema operativo y del proceso `main.py`.
- **Estado del puerto serie**: Conexión UART activa (`OK` / `Reconectando`), tasa de paquetes erróneos o colas pendientes.

### 3. Formato de salida y límites LoRa
- **Límite:** 1 solo mensaje LoRa condensado (~150 bytes).
- **Estructura ejemplo:**
  ```text
  🖥️ Bot RPi Zero 2W (RAU0):
  🌡️ 44.8°C | ⚡ Load: 0.18 | 🧠 RAM: 145/480 MB
  💾 Disco: 22.4 GB libre | ⏱️ Up: 12d 4h
  📻 UART: /dev/ttyAMA0 (OK)
  ```

### 4. Integración en el Panel Web
- Visualización de tarjetas de estado en tiempo real en la cabecera del dashboard web con actualización periódica por WebSocket.

---

## Módulo 06 · Control de saturación, anti-abuso y bloqueos con gestión Web

### 1. Objetivo y Necesidad
Proteger la malla LoRa frente a bucles de mensajes, flooding o nodos que envíen ráfagas masivas de comandos al bot, incorporando tanto detección/bloqueo automático temporal como una interfaz web para bloqueos manuales permanentes y consulta de auditoría.

### 2. Componentes involucrados
- **Base de datos (`blocked_nodes`, `commands_sent`)**:
  - Tabla `blocked_nodes`:
    - `node_id`: ID del nodo (`!1234abcd`).
    - `node_name`: Nombre o apodo conocido.
    - `block_type`: `"auto"` o `"manual"`.
    - `reason`: Motivo (ej. *"Exceso de comandos: 10 en 60s"*, *"Bloqueo administrativo"*).
    - `created_at`: Fecha/hora del bloqueo.
    - `expires_at`: Fecha/hora de expiración (`NULL` si es permanente).
    - `active`: 1 (bloqueado) / 0 (levantado).
- **Motor de detección de abusos (`Models/AntiAbuse.py` o en `SerialInterface.py`)**:
  - Al recibir un comando, comprueba la lista negra en memoria/BD. Si el nodo está bloqueado, se descarta silenciosamente.
  - Ventana deslizante: Si un nodo emite más de `MAX_COMMANDS_PER_MINUTE` (ej. 6 comandos en 60s):
    1. Primer nivel: Silencio durante 15 minutos (auto-ban temporal).
    2. Reincidencia (>3 bloqueos en 24h): Auto-ban de 24 horas.
- **Gestión desde el Panel Web (`web/index.html`, `web/app.js`)**:
  - Pestaña "Seguridad y Bloqueos".
  - **Formulario de bloqueo manual:** Campo para introducir ID de nodo/nombre, motivo y tipo (Temporal / Permanente).
  - **Tabla de bloqueos activos:** Listado con tipo (automático/manual), motivo, expiración y botón de acción directa "Desbloquear".
  - **Registro de actividad sospechosa / auditoría:** Historial de disparos del limitador de velocidad.

### 3. Configuración (`env.py`)
- `RATE_LIMIT_ENABLED = True`
- `RATE_LIMIT_MAX_PER_MINUTE = 5`
- `RATE_LIMIT_BAN_MINUTES = 15`
- `RATE_LIMIT_NOTIFY_USER = False` (si es `False`, descarta en silencio para no generar tráfico LoRa adicional).

---

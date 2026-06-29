# meshassistant

`meshassistant` es un **asistente/bot para redes [Meshtastic](https://meshtastic.org/)**
(malla LoRa) pensado para ejecutarse de forma desatendida (modo *daemon*) en una
**Raspberry Pi Zero W / Zero 2 W**. El bot se comunica por **puerto serie (UART)**
con un nodo Meshtastic, gestiona ese nodo por completo y responde a comandos y
mensajes (directos o de canal) recibidos por la malla.

La idea es que cualquier usuario de la malla pueda preguntarle por mensaje privado
o por canal y el asistente responda con información útil, incluso **sin conexión a
Internet** (asistente *offline*). Las operaciones se apoyan en una base de datos
**SQLite local** que actúa como cola y almacén persistente, lo que hace al sistema
**tolerante a desconexiones del nodo, caídas del puerto serie o reinicios**.

> **Nota sobre el almacenamiento:** el proyecto usa **SQLite** (fichero
> `database.sql` en modo WAL), no PostgreSQL. SQLite encaja mejor en una Raspberry
> Pi Zero (sin servicio de BD que mantener) y permite que aplicaciones externas
> escriban en las mismas tablas para encolar mensajes/avisos.

---

## Índice

- [Objetivo y funcionalidades](#objetivo-y-funcionalidades)
- [Estado actual](#estado-actual)
- [Arquitectura](#arquitectura)
- [Hardware y conexión serie](#hardware-y-conexión-serie)
- [Requisitos e instalación](#requisitos-e-instalación)
- [Configuración (`env.py`)](#configuración-envpy)
- [Comandos disponibles](#comandos-disponibles)
- [Base de datos](#base-de-datos)
- [Ejecución del proceso principal](#ejecución-del-proceso-principal)
- [Ejecución con cron](#ejecución-con-cron-solo-linux)
- [Variables de entorno para AEMET](#variables-de-entorno-para-aemet)
- [Variables de entorno para Traces](#variables-de-entorno-para-traces)
- [Estructura del proyecto](#estructura-del-proyecto)
- [Documentación técnica](#documentación-técnica)
- [Roadmap / TODO](#roadmap--todo)

---

## Objetivo y funcionalidades

Las funcionalidades previstas (algunas ya implementadas, otras en curso) son:

- **Canal público** con información relevante para todos los usuarios, resumida
  varias veces al día (mañana/tarde/noche). Por ejemplo, alertas de agua, incendio
  o tormenta.
- **Canal privado** para gestionar IoT, avisos de eventos, *watchdogs*, etc.
- **Petición de tiempo** por mensaje directo (tiempo real y previsión).
- **Avisos programados** (agendar que el bot te avise un día/hora con un mensaje).
- **Micro-IA** por mensaje directo: un modelo de IA muy pequeño con respuestas
  breves para preguntas comunes.
- **Comandos** accesibles con prefijo `/` o `!`:
  - `/help` — ayuda general; `/help <comando>` muestra detalle de un comando.
  - `/about` — información sobre el proyecto.
  - `/ping` — responde con `pong` e información de cómo se recibe el nodo (saltos,
    SNR, vía MQTT…).
  - `/uptime` — tiempo encendido.
  - `/chiste` — devuelve un chiste de la comunidad (y permite añadir el tuyo).
  - `/weather` — tiempo en la provincia de Cádiz.
  - `/maremoto` — días desde el último maremoto en Chipiona (1/11/1755).
  - `/ia` — respuesta de la micro-IA.
- **Publicación automática de alertas AEMET** en canales configurados.
- **Traceroute programado** de nodos de la malla para mapear la topología.

---

## Estado actual

| Funcionalidad | Estado | Notas |
|---|---|---|
| Conexión serie con el nodo Meshtastic | ✅ Funcional | Reconexión automática ante caídas |
| Recepción de mensajes (directo / canal) y dispatch de comandos | ✅ Funcional | Vía `pubsub` de meshtastic |
| Persistencia en SQLite (nodos, pings, comandos, traces, chistes, AEMET) | ✅ Funcional | Esquema autogestionado e idempotente |
| `/help`, `/about`, `/maremoto` | ✅ Funcional | Respuesta completa |
| `/ping` | ✅ Funcional | Guarda el ping en BD y responde con saltos/MQTT |
| `/chiste` | ✅ Funcional | Lectura/alta en BD + sincronización con API externa |
| AEMET (descarga, parseo CAP, publicación por canal) | ✅ Funcional | Solo si hay `AEMET_API_KEY` |
| Traceroute encolado por cron y ejecutado por el proceso principal | ✅ Funcional | Solo si `ENABLE_TRACES=True` |
| `/weather` | 🟡 Placeholder | Responde texto fijo; pendiente integrar fuente real |
| `/uptime` | 🟡 Placeholder | Responde `N/D`; pendiente calcular uptime |
| `/ia` | 🟡 Placeholder | Responde "en desarrollo"; pendiente integrar micro-IA |
| Agenda de avisos programados (tabla `agenda`) | 🟡 Parcial | Modelo de datos listo; falta envío programado |
| Cola de publicaciones (tabla `queue`) | 🟡 Parcial | Tabla creada; `get_next_in_queue()` es un TODO |

---

## Arquitectura

El sistema se compone de **dos procesos** que cooperan a través de la base de datos
SQLite, evitando que ambos abran el puerto serie a la vez:

1. **Proceso principal — `main.py`** (servicio de larga duración):
   - Abre y **mantiene** el puerto serie con el nodo Meshtastic.
   - Se suscribe a los eventos de la malla (`pubsub`) y procesa los mensajes
     entrantes; si son comandos, ejecuta su *callback*.
   - En su bucle `loop()` consume tareas encoladas en la BD: ejecuta los
     **traceroutes** pendientes y **publica las alertas AEMET** dentro de la
     ventana horaria configurada.
   - Es el **único** que habla con el puerto serie.

2. **Tareas periódicas — `cron_tasks.py`** (se lanza cada minuto desde `cron`):
   - Sube/descarga chistes contra una API externa.
   - **Encola** traceroutes en la tabla `traces` (no abre el serie).
   - Descarga avisos AEMET y los guarda en BD.

Esta separación es clave: como el puerto serie solo lo puede abrir un proceso, el
cron **nunca** ejecuta acciones de radio directamente, sino que **deja trabajo en
cola** en SQLite para que `main.py` lo realice de forma segura.

```
        Nodo Meshtastic (LoRa)
                 │  UART (serie)
                 ▼
   ┌─────────────────────────────┐        ┌──────────────────────────┐
   │   main.py  (loop, daemon)   │        │  cron_tasks.py (cada min) │
   │  - SerialInterface          │        │  - chistes up/down        │
   │  - dispatch de comandos     │        │  - encola traces          │
   │  - ejecuta traces pendientes│        │  - descarga AEMET         │
   │  - publica alertas AEMET    │        └──────────────┬───────────┘
   └──────────────┬──────────────┘                       │
                  │           SQLite (database.sql, WAL)  │
                  └───────────────────►◄──────────────────┘
                         cola + persistencia compartida
```

Capas principales del código:

- **`Models/SerialInterface.py`** — envoltura sobre la librería `meshtastic`:
  conexión, reconexión, envío (directo / canal / broadcast), suscripción a eventos
  y `traceroute`.
- **`Models/Database.py`** — acceso a SQLite (chistes, traces, pings, nodos,
  agenda, AEMET, control de tareas y log de comandos).
- **`Models/Node.py`** — representación de un nodo de la malla, con persistencia
  automática en BD.
- **`Models/Aemet.py`** / **`Models/Api.py`** — clientes HTTP (AEMET y API genérica
  de chistes).
- **`Commands/`** — un fichero por comando; cada uno expone un *callback*.
- **`data.py`** — registro de comandos (`commands_dict`) y canales (`channels`).
- **`functions.py`** — utilidades (`log_p`, `search_command`, `sanitize_text`).
- **`create_db.py`** — creación y migración idempotente del esquema SQLite.

---

## Hardware y conexión serie

- **Servidor / bot:** Raspberry Pi Zero W o **Zero 2 W**, ejecutando este proyecto.
- **Nodo de malla:** un nodo Meshtastic conectado a la Pi por **UART**.

Conexión por los pines UART de la Raspberry Pi (GPIO):

- **GPIO 14 (TX, pin físico 8)** → RX del nodo.
- **GPIO 15 (RX, pin físico 10)** → TX del nodo.
- **GND común** entre ambos dispositivos.

En la Raspberry Pi hay que habilitar el puerto serie por hardware y **liberar la
consola serie** (`raspi-config` → *Interface Options* → *Serial Port*: login shell
*No*, hardware *Yes*).

**Importante en Pi Zero 2 W:** por defecto el Bluetooth ocupa el UART completo
(PL011) y GPIO 14/15 quedan en el mini UART, que es inestable porque su baudrate
depende del reloj de la CPU. Para usar el PL011 (estable) hay que añadir
`dtoverlay=disable-bt` en `/boot/firmware/config.txt` y deshabilitar el servicio
`hciuart`. Con eso activo, el dispositivo serie es `/dev/ttyAMA0`. Ver detalle
completo en [`docs/info/13-instalacion-despliegue.md`](docs/info/13-instalacion-despliegue.md).

```python
# env.py — valor correcto para Pi Zero 2 W con dtoverlay=disable-bt
SERIAL_DEVICE_PATH = "/dev/ttyAMA0"
```

> Si se conecta el nodo por USB (durante desarrollo en un PC), `SERIAL_DEVICE_PATH`
> apuntará a algo como `/dev/ttyUSB0` (Linux) o `/dev/cu.usbserial-XXXX` (macOS).

---

## Requisitos e instalación

- Python 3.11+ (validado con 3.14).
- Acceso al puerto serie del sistema.
- Dependencias en `requirements.txt`: `meshtastic`, `pypubsub`, `requests`.

**En Raspberry Pi** usa el script de instalación automática (ver sección
[Despliegue en producción](#despliegue-en-producción-raspberry-pi)).

**En desarrollo / macOS / Linux:**

```bash
# 1. Clonar el repositorio
git clone https://github.com/raupulus/meshassistant.git && cd meshassistant

# 2. Crear y activar el entorno virtual
python3 -m venv .venv
source .venv/bin/activate

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Crear el fichero de configuración a partir del ejemplo
cp env.example.py env.py
#   …y editar env.py con tus valores (SERIAL_DEVICE_PATH, etc.)

# 5. (Opcional) Crear/migrar la base de datos manualmente
python3 create_db.py     # main.py también la crea al arrancar
```

---

## Configuración (`env.py`)

La configuración vive en `env.py` (se copia desde `env.example.py`). **Este fichero
está excluido del repositorio** porque puede contener claves de API.

| Variable | Tipo | Descripción |
|---|---|---|
| `DEBUG` | bool | Activa el logging detallado (`log_p`). |
| `SERIAL_DEVICE_PATH` | str | Ruta del dispositivo serie del nodo Meshtastic. |
| `ENABLE_TRACES` | bool | Habilita el encolado de traceroutes desde el cron. |
| `TRACES_HOPS` | int | Máximo de saltos para elegir nodos a trazar (`hops <=`). |
| `TRACES_INTERVAL` | int (min) | Intervalo global mínimo entre traces. |
| `TRACES_RETRY_INTERVAL` | int (h) | Espera para reintentar un trace tras error. |
| `TRACES_RELOAD_INTERVAL` | int (h) | Espera para volver a trazar un nodo tras éxito. |
| `CHISTES_API_ENABLED` | bool | Activa la sincronización de chistes con API externa. |
| `CHISTES_API_KEY` | str | *Bearer token* de la API de chistes. |
| `CHISTES_URL_UPLOAD` | str | Endpoint para subir chistes. |
| `CHISTES_URL_DOWNLOAD` | str | Endpoint para descargar chistes. |
| `AEMET_API_KEY` | str | Clave de AEMET OpenData. Si está vacía, AEMET no se usa. |
| `AEMET_CHANNELS` | list[int] | Canales donde publicar alertas (p. ej. `[6]`). |
| `AEMET_PROVINCE` | str | Provincia/CCAA vigilada y para la predicción (nombre `Cádiz` o código INE 2 dígitos). |
| `AEMET_CITY` | str | Municipio de fallback para el clima si no hay predicción provincial (p. ej. `Chipiona`). |
| `AEMET_CITY_CODE` | str | Código INE de 5 dígitos del municipio (p. ej. `11015`); `''` para autodetectar por nombre. |
| `AEMET_PERIOD` | str | Cadencia de descarga del clima y periodicidad mínima de publicación por canal (`Hour`, `Three_hour`, `Six_hour`, `Twelve_hour`, `Day`). |
| `AEMET_HOUR_MIN` | int (0-23) | Hora mínima a partir de la cual publicar. |
| `AEMET_HOUR_MAX` | int (0-23) | Hora máxima hasta la cual publicar. |

---

## Comandos disponibles

Los comandos se invocan con prefijo `/` o `!` (p. ej. `/ping` o `!ping`). Cada
comando declara en `data.py` si responde también **en grupo/canal** (`in_group`) o
**solo en mensajes directos**.

| Comando | En grupo | Descripción | Estado |
|---|---|---|---|
| `/help [cmd]` | No | Ayuda general o detalle de un comando | ✅ |
| `/about` | No | Información del proyecto | ✅ |
| `/ping` | Sí | Devuelve saltos/SNR/MQTT y guarda el ping | ✅ |
| `/chiste [add …]` | Sí | Chiste aleatorio o alta de uno nuevo | ✅ |
| `/maremoto` | Sí | Tiempo desde el último maremoto en Chipiona | ✅ |
| `/weather` | No | Tiempo actual de la zona (datos AEMET, desde BD) | ✅ |
| `/tiempo` | Sí | Alias de `/weather`, usable en canal | ✅ |
| `/prevision` | Sí | Previsión de varios días (AEMET); BD + en vivo si hace falta | ✅ |
| `/avisos` | Sí | Últimos avisos AEMET de la provincia (desde BD) | ✅ |
| `/marea` | Sí | Próximas pleamares/bajamares (offline, con estimación de respaldo) | ✅ |
| `/sol` | Sí | Orto, ocaso y duración del día (cálculo offline) | ✅ |
| `/luna` | Sí | Fase lunar e iluminación (cálculo offline) | ✅ |
| `/nodos` | Sí | Total de nodos: RF, MQTT y activos 24h | ✅ |
| `/snr` | Sí | Señal del nodo pasarela (RAU0) y media de la malla RF | ✅ |
| `/stats` | Sí | Estadísticas del bot (comandos, pings, nodos, uptime) | ✅ |
| `/encuesta …` | Sí | Encuestas comunitarias (crear, votar, ver, cerrar) | ✅ |
| `/dado [NdM]` | Sí | Tira dados (1d6 por defecto) | ✅ |
| `/bola8` (`/8ball`) | Sí | Bola 8 mágica (sí/no, diversión) | ✅ |
| `/uptime` | No | Tiempo encendido | 🟡 Placeholder |
| `/ia` | Sí | Respuesta de la micro-IA | 🟡 Placeholder |

Origen de los datos:

- `/weather`, `/tiempo`, `/prevision` y `/avisos` usan **AEMET** (requiere `AEMET_API_KEY`). El cron descarga y guarda en BD; los comandos sirven **offline** desde ahí. `/prevision` intenta además una descarga en vivo si el dato de BD está obsoleto (>12 h).
- `/marea` usa **Open-Meteo Marine** (gratis, sin clave) o **WorldTides** (si configuras `TIDES_API_KEY`) vía cron→BD. Si no hay dato ni Internet, hace una **estimación astronómica** offline (se marca con `~`).
- `/sol` y `/luna` se calculan **100% offline** desde la ubicación configurada (`LOCATION_*`; por defecto Chipiona).
- `/nodos`, `/snr` y `/stats` leen la BD local (`nodes`, `pings`, `commands_sent`, `encuestas`).

Todos los comandos quedan registrados en la tabla `commands_sent`, lo que permite
detectar abusos y, en el futuro, bloquear nodos.

Cómo se añade un comando nuevo: crear `Commands/<nombre>.py` con una función
`<nombre>_callback(interface, args, msg, metadata)`, importarla y registrarla en
`commands_dict` dentro de `data.py`. Ver
[`docs/info/07-comandos.md`](docs/info/07-comandos.md).

---

## Base de datos

SQLite (`database.sql`, modo WAL) creada y migrada de forma **idempotente** por
`create_db.py` (`ensure_database()`), que `main.py` invoca al arrancar. Tablas:

- `nodes` — nodos de la malla (nombre, SNR, RSSI, saltos, MQTT…).
- `pings` — histórico de pings recibidos.
- `traces` — cola **y** resultado de traceroutes (estado `pending`/`done`/`error`,
  hasta 7 saltos de ida y 7 de vuelta).
- `chistes` — chistes locales y sincronizados con la API externa.
- `aemet` — histórico de alertas AEMET con marca `published`.
- `aemet_weather` — histórico de clima/previsión (scopes `province`/`city`/`forecast`).
- `tides` — predicción de mareas descargada (servida offline por `/marea`).
- `encuestas` / `encuesta_votos` — encuestas comunitarias y sus votos.
- `agenda` — avisos programados por nodo (modelo listo).
- `queue` — cola de publicaciones programadas (parcial).
- `tasks_control` — marcas de última ejecución de tareas periódicas.
- `commands_sent` — log de comandos recibidos.

Detalle completo del esquema en
[`docs/info/03-base-de-datos.md`](docs/info/03-base-de-datos.md).

---

## Despliegue en producción (Raspberry Pi)

### Instalación automática

El script `install.sh` automatiza todo el proceso con un solo comando:

```bash
curl -sSL https://raw.githubusercontent.com/raupulus/meshassistant/main/install.sh | bash
```

O si ya tienes el repo clonado:

```bash
bash install.sh
```

El script clona/actualiza el repo en `/home/pi/meshbotassistant`, crea el entorno
virtual, instala dependencias, genera `env.py` si no existe, migra la BD, instala
el servicio systemd y configura el cron automáticamente. Para **actualizar**
el bot en el futuro basta con volver a ejecutar el mismo comando.

Tras la instalación, edita `env.py` (al menos `SERIAL_DEVICE_PATH`) y arranca:

```bash
nano /home/pi/meshbotassistant/env.py
sudo systemctl start meshbotassistant
```

### Gestión del servicio

```bash
sudo systemctl status  meshbotassistant   # estado
sudo systemctl restart meshbotassistant   # reiniciar
journalctl -u meshbotassistant -f         # logs en tiempo real
```

El servicio usa `Restart=always` con 30 s de espera entre reinicios. Los errores
de conexión al nodo (puerto serie caído, nodo apagado o ocupado) los gestiona el
propio bot esperando y reintentando; `Restart=always` cubre caídas inesperadas del
proceso.

### Ejecución del proceso principal (manual / desarrollo)

```bash
source .venv/bin/activate
python3 main.py
```

`main.py` asegura la base de datos, abre el puerto serie, queda a la escucha de
mensajes y, en bucle, procesa traces pendientes y publica alertas AEMET. Se detiene
con `Ctrl+C`.

---

## Ejecución con cron (solo Linux)

Para tareas periódicas (subir/descargar chistes, encolar traceroutes y revisar
AEMET) se proporciona el script `cron_tasks.py`. Se ejecuta cada minuto desde
`cron`. El proceso principal `main.py` mantiene el puerto serie abierto; por
eso el cron no realiza el traceroute directamente, sino que **encola** un registro
en la tabla `traces` con `status='pending'` para que `main.py` lo ejecute de forma
segura.

El script `install.sh` instala la entrada de cron automáticamente. Para revisarla:

```bash
crontab -l
```

Entrada manual si prefieres configurarlo tú mismo:

```cron
* * * * * cd /home/pi/meshbotassistant && .venv/bin/python cron_tasks.py >> /home/pi/meshbotassistant/cron.log 2>&1
```

Notas sobre traceroute:

- `cron_tasks.py` encola el trace insertando en `traces` una fila mínima:
  `to=<node_id>`, `status='pending'`, `created_at=NOW()`.
- `main.py` en su bucle (`loop()`) busca el trace pendiente más antiguo y lo ejecuta
  con la conexión serie abierta. Al terminar, actualiza esa misma fila con
  `status='done'|'error'`, `from='local'`, `data_raw=<texto>` y `updated_at=NOW()`.
- Límite global configurable: como máximo un trace cada `TRACES_INTERVAL` minutos,
  calculado mirando el `updated_at` del último trace procesado.
- Ventanas por nodo configurables:
  - Tras éxito (`status='done'`): repetir pasado `TRACES_RELOAD_INTERVAL` horas.
  - Tras error (`status='error'`): reintentar pasado `TRACES_RETRY_INTERVAL` horas.
  - Solo se consideran nodos con `via_mqtt=0` y con `hops <= TRACES_HOPS`.

Esto evita conflictos por el puerto serie ya que solo el proceso principal lo abre
y lo mantiene.

---

## Variables de entorno para AEMET

Estas variables se configuran en `env.py` (puedes copiar desde `env.example.py`). La
integración solo se activa si `AEMET_API_KEY` tiene un valor.

- `AEMET_API_KEY`: Clave de API de AEMET (OpenData). Si está vacía, no se consulta la
  API ni se publican avisos.
- `AEMET_CHANNELS`: Lista de canales Meshtastic donde publicar alertas. Ejemplo:
  `[6]`. Los nombres de canales se definen en `data.py`.
- `AEMET_PROVINCE`: Provincia para la que se vigilan alertas y se descarga la
  predicción general. Puede ser el nombre (p. ej. `Cádiz`) o el código INE de 2
  dígitos (Cádiz = `11`).
- `AEMET_CITY`: Municipio usado como *fallback* del clima (comando `/weather`)
  cuando la API no devuelve predicción provincial. Por defecto `Chipiona`.
- `AEMET_CITY_CODE`: Código INE de 5 dígitos del municipio de `AEMET_CITY`
  (Chipiona = `11015`). Si se deja vacío (`''`) se intenta resolver por nombre.
- `AEMET_PERIOD`: Cadencia de descarga del clima (tarea `weather_aemet`) y
  periodicidad mínima entre publicaciones de avisos por canal. Valores
  admitidos: `Hour`, `Three_hour`, `Six_hour`, `Twelve_hour`, `Day` (insensible a
  mayúsculas). Se traduce a 60, 180, 360, 720 y 1440 minutos respectivamente.
- `AEMET_HOUR_MIN`: Hora mínima (0-23) a partir de la cual se puede empezar a
  publicar alertas (respetando `AEMET_PERIOD`).
- `AEMET_HOUR_MAX`: Hora máxima (0-23) hasta la cual se puede empezar a publicar
  alertas (respetando `AEMET_PERIOD`).

Flujo de AEMET:

- `cron_tasks.py` (cada hora): si hay `AEMET_API_KEY`, consulta OpenData de AEMET
  (avisos CAP para la provincia indicada) y guarda cualquier novedad en la tabla
  `aemet` (evitando duplicados por hash).
- `main.py` (bucle): si hay API key y la hora actual está entre `AEMET_HOUR_MIN` y
  `AEMET_HOUR_MAX`, toma la próxima alerta no publicada y la envía a los canales de
  `AEMET_CHANNELS`, respetando `AEMET_PERIOD` por canal. Tras publicar, marca la
  alerta como publicada.

Clima / predicción (comando `/weather`):

- `cron_tasks.py` → `weather_aemet()` descarga la predicción cada `AEMET_PERIOD`
  (no fija): primero el texto general de la provincia
  (`/prediccion/provincia/hoy/{códigoINE}`) y, si falla, la del municipio
  `AEMET_CITY` (`/prediccion/especifica/municipio/diaria/{códigoINE5}`).
- Se guarda como histórico en la tabla `aemet_weather`. El comando `/weather` lee
  el último registro y responde **offline** desde BD, troceado en 1-2 mensajes.

Notas:

- La tabla `aemet` actúa como histórico con un indicador `published` para evitar
  repeticiones.
- Los mensajes se trocean para respetar el límite de **~200 caracteres** de
  Meshtastic (hasta 2 partes, con enlace a `aemet.es` en la segunda).
- La periodicidad por canal se controla con la tabla `tasks_control` (marcas
  `aemet_publish_ch_<canal>`).

---

## Variables de entorno para Traces

Configúralas en `env.py` (consulta `env.example.py`):

- `ENABLE_TRACES` (bool): Si es `False`, el cron no encola traceroutes (deshabilitado
  por completo). Por defecto `False` en el ejemplo.
- `TRACES_HOPS` (int): Máximo de saltos permitidos para seleccionar nodos candidatos
  (se usa `hops <= TRACES_HOPS`). Por defecto `2`.
- `TRACES_INTERVAL` (int, minutos): Intervalo global mínimo entre traces (de
  distintos nodos). Por defecto `5`.
- `TRACES_RETRY_INTERVAL` (int, horas): Tiempo de espera para reintentar un trace
  tras un fallo (`status='error'`). Por defecto `24` (1 día).
- `TRACES_RELOAD_INTERVAL` (int, horas): Tiempo de espera para volver a trazar un
  nodo tras un éxito (`status='done'`). Por defecto `168` (7 días).

Cómo funciona con estas variables:

- El cron (`cron_tasks.send_trace`) respeta `ENABLE_TRACES` y el `TRACES_INTERVAL`
  global mirando el `updated_at` del último trace realizado.
- La selección de candidatos lee los parámetros y solo elige nodos que cumplen
  `via_mqtt=0` y `hops <= TRACES_HOPS` y cuyas ventanas por nodo hayan expirado.
- El proceso principal toma el `pending` más antiguo de la tabla `traces` y lo
  ejecuta.

---

## Estructura del proyecto

```
meshassistant/
├── main.py                 # Proceso principal (daemon): serie + dispatch + loop
├── cron_tasks.py           # Tareas periódicas (cron cada minuto)
├── create_db.py            # Creación/migración idempotente del esquema SQLite
├── data.py                 # Registro de comandos y canales
├── functions.py            # Utilidades (log_p, search_command, sanitize_text)
├── env.example.py          # Plantilla de configuración (copiar a env.py)
├── requirements.txt        # Dependencias Python
├── test.py                 # Script de ejemplo/prueba de recepción por UART
├── Commands/               # Un módulo por comando (callbacks)
│   ├── help.py  about.py  ping.py  chiste.py
│   ├── ia.py    uptime.py weather.py  maremoto.py
├── Models/                 # Modelos de dominio
│   ├── SerialInterface.py  # Envoltura de meshtastic (serie, eventos, envío)
│   ├── Database.py         # Acceso a SQLite
│   ├── Node.py             # Nodo de la malla con persistencia
│   ├── Aemet.py            # Cliente AEMET + reglas de publicación
│   └── Api.py              # Cliente HTTP genérico (chistes)
├── Crons/                  # (reservado) tareas futuras
├── Services/               # (reservado) servicios futuros
└── docs/info/              # Documentación técnica por módulo
```

> Nota: cada comando vive en `Commands/<nombre>.py` y se registra en `data.py`. Si
> renombras un fichero de comando, actualiza también su import en `data.py`.

---

## Documentación técnica

La documentación detallada por módulo está en
[`docs/info/`](docs/info/00-indice.md):

- `00-indice.md` — índice de la documentación.
- `01-arquitectura.md` — procesos, flujo y decisiones de diseño.
- `02-configuracion.md` — variables de `env.py`.
- `03-base-de-datos.md` — esquema completo de SQLite.
- `04-interfaz-serial.md` — `SerialInterface` (serie, eventos, envío, reconexión).
- `05-nodos.md` — modelo `Node` y persistencia.
- `06-modelo-database.md` — API del modelo `Database`.
- `07-comandos.md` — sistema de comandos y cómo añadir uno.
- `08-traceroute.md` — encolado y ejecución de traces.
- `09-aemet.md` — descarga, parseo CAP y publicación de alertas.
- `10-chistes.md` — sincronización y almacenamiento de chistes.
- `11-cron.md` — tareas periódicas.
- `12-api-http.md` — cliente HTTP genérico.
- `13-instalacion-despliegue.md` — instalación, hardware y despliegue.
- `14-roadmap.md` — funcionalidades pendientes.

---

## Roadmap / TODO

- [x] Base de datos SQLite con pings, nodos, traces, chistes, AEMET y comandos.
- [x] Tablas para alertas/avisos con canal de destino (alimentables desde otras apps).
- [x] Tabla de comandos recibidos (`commands_sent`) para detectar abusos.
- [ ] Implementar `/weather` con fuente real (tiempo actual + previsión).
- [ ] Implementar `/uptime` real (tiempo de servicio del bot/nodo).
- [ ] Integrar la micro-IA para `/ia`.
- [ ] Envío de avisos programados (consumir la tabla `agenda`).
- [ ] Resumen del canal público 3 veces al día.
- [ ] Bloqueo de nodos que abusan de comandos (con advertencia previa).
- [ ] Consumo de la cola `queue` (`get_next_in_queue()`).

# AGENTS.md

Guía para agentes de IA (y personas) que trabajen en **meshassistant**. Resume qué
es el proyecto, cómo está organizado, sus convenciones y las reglas que **hay que
respetar** al modificar el código.

> Idioma del proyecto: **español**. Código, comentarios, mensajes de log y de la
> malla se escriben en español. Mantén esa convención.

---

## 1. Qué es el proyecto

Bot/asistente para una red **Meshtastic** (malla LoRa) que corre como *daemon* en
una **Raspberry Pi Zero W / Zero 2 W**. Habla por **puerto serie (UART)** con un
nodo Meshtastic, responde comandos y mensajes de la malla, publica alertas (AEMET)
y mantiene un histórico en **SQLite**. Está diseñado para ser **tolerante a
desconexiones**: el trabajo se encola en la base de datos y se procesa cuando el
serie está disponible.

Visión funcional completa: ver `README.md`. Detalle por módulo: ver `docs/info/`.

---

## 2. Stack y runtime

- **Lenguaje:** Python 3.11+ (validado con 3.14).
- **Base de datos:** SQLite (`database.sql`, modo WAL). **No** es PostgreSQL.
- **Dependencias** (`requirements.txt`):
  - `meshtastic` — API/CLI para hablar con el nodo por serie.
  - `pypubsub` — bus de eventos (`from pubsub import pub`) que usa meshtastic.
  - `requests` — cliente HTTP (AEMET y API de chistes).
- **Sin framework web.** Son dos scripts ejecutables (`main.py`, `cron_tasks.py`).

---

## 3. Estructura del repositorio

```
main.py            Proceso principal (daemon): abre serie, escucha, ejecuta el loop.
cron_tasks.py      Tareas periódicas (cron cada minuto): chistes, encola traces, AEMET.
create_db.py       Crea/migra el esquema SQLite (idempotente). ensure_database().
data.py            commands_dict (registro de comandos) y channels (mapa de canales).
functions.py       Utilidades: log_p, search_command, sanitize_text.
env.example.py     Plantilla de configuración. Se copia a env.py (NO versionado).
requirements.txt   Dependencias.
tests/             Tests y scripts de prueba (test.py, test_aemet_*.py). No forman parte del bot.

Commands/          Un fichero por comando. Cada uno expone <cmd>_callback(...).
  help.py about.py ping.py chiste.py ia.py uptime.py weather.py maremoto.py

Models/
  SerialInterface.py  Envoltura de meshtastic: connect/reconnect, send, eventos, traceroute.
  Database.py         Acceso a SQLite (todas las queries).
  Node.py             Nodo de la malla, con carga/persistencia automática en BD.
  Aemet.py            Cliente AEMET + reglas de publicación (ventana horaria, periodo).
  Api.py              Cliente HTTP genérico con reintentos (chistes).

Crons/  Services/     Reservados para futuro (vacíos).
docs/info/            Documentación técnica por módulo.
```

> Cada comando es `Commands/<nombre>.py` con un callback `<nombre>_callback` y se
> registra en `data.py`. Si renombras un fichero de comando, actualiza su import en
> `data.py`.

---

## 4. Arquitectura y flujo (lo que NO se ve en un solo fichero)

Dos procesos cooperan **solo a través de SQLite**. El puerto serie lo abre **un
único proceso** (`main.py`). Esta es la decisión de diseño más importante:

- `cron_tasks.py` **nunca** abre el serie ni hace acciones de radio. Si necesita una
  acción de radio (p. ej. un traceroute), **inserta una fila en cola** en la tabla
  `traces` con `status='pending'`.
- `main.py`, en su `loop()`, recoge ese trabajo pendiente y lo ejecuta con el serie
  abierto, actualizando la misma fila con el resultado (`done`/`error`).

Mismo patrón para AEMET: el cron descarga y guarda alertas; `main.py` las publica
respetando ventana horaria y periodicidad por canal.

**Regla de oro:** si añades una acción que use el puerto serie, hazla en `main.py`
(o encólala en BD para que la haga `main.py`). Nunca desde el cron.

### Recepción de mensajes
`SerialInterface.connect()` se suscribe a tópicos de `pubsub`
(`meshtastic.receive.text`, `…nodeinfo`, `…user`, `connection.lost`, etc.). Al
llegar texto, `on_receive_text` construye `metadata`, detecta si es directo o de
canal, busca comando con `search_command` y, si procede, llama al callback.

### Contrato de un comando
Cada callback tiene la firma:

```python
def <nombre>_callback(interface, args, msg, metadata):
    ...
    interface.reply_to_message(respuesta, metadata)
```

- `interface`: instancia de `SerialInterface` (usa `reply_to_message`, `send`, …).
- `args`: lista de argumentos tras el comando.
- `msg`: texto completo recibido.
- `metadata`: dict con `node_from`, `node_to`, `channel`, `is_direct`, `rx_snr`,
  `rx_rssi`, `via_mqtt`.

Tras responder, el callback **registra el comando** en `commands_sent` vía
`Database().log_command(...)`.

---

## 5. Cómo añadir un comando nuevo

1. Crear `Commands/<nombre>.py` con `def <nombre>_callback(interface, args, msg, metadata):`.
2. Responder con `interface.reply_to_message(texto, metadata)`.
3. Registrar el comando en `commands_sent` (copiar el bloque `try/except` de otro
   comando).
4. En `data.py`: importar el callback y añadir una entrada a `commands_dict` con
   `callback`, `in_group` (¿responde en canal o solo en directo?), `usage` e `info`.
5. Documentarlo en `README.md` (tabla de comandos) y en `docs/info/07-comandos.md`.

Respetar las reglas de longitud de mensaje (ver sección 5.1).

### 5.1. Longitud de los mensajes (OBLIGATORIO)

Meshtastic limita cada mensaje a ~**200 caracteres**. Un texto más largo se corta
y la información se pierde (es lo que pasaba con `/weather`). Reglas:

- **Máximo 200 caracteres por mensaje.** Usa la constante `MESH_MAX_LEN`.
- **Máximo 3 mensajes por respuesta** de un comando básico. Usa `MESH_MAX_PARTS`.
  Si el contenido no cabe en 3 partes, se trunca con `…` en la última (preferible a
  reventar el límite o a inundar la malla).
- **No trocees a mano.** Usa `split_messages(texto)` de `functions.py`, que corta por
  palabras y añade `…` si hace falta. Las alertas AEMET de `main.py` y `/weather`
  ya lo usan; sigue ese patrón.
- Entre parte y parte, espera unos segundos (`sleep(5)`) para no saturar la malla,
  pero **nunca tras la última**.

---

## 6. Base de datos: convenciones

- Todo acceso a BD pasa por `Models/Database.py`. **No** escribas SQL suelto en
  comandos ni en el cron; añade un método al modelo `Database`.
- El esquema se define y migra en `create_db.py`. Las migraciones son
  **idempotentes** (comprobar columnas con `PRAGMA table_info` antes de `ALTER`).
  Si añades una columna, hazlo también ahí siguiendo ese patrón.
- `"from"` y `"to"` son palabras reservadas de SQL: van **siempre entre comillas
  dobles** en las queries.
- Fechas: se guardan como texto ISO 8601 (`datetime.now().isoformat(timespec=...)`).
- Tabla `traces`: hace de **cola y de resultado** a la vez (no hay tabla auxiliar).
  `status` ∈ `pending|done|error`.
- `tasks_control`: marca la última ejecución de tareas periódicas (`name`,
  `last_run_at`). Úsala para *throttling* (`_should_run`, `get_task_last_run`,
  `set_task_run`).

Esquema completo: `docs/info/03-base-de-datos.md`.

---

## 7. Convenciones de código

- **Logging:** usa `functions.log_p(mensaje, level=...)`. Solo imprime si
  `env.DEBUG` es `True`. No metas `print()` nuevos para depurar producción (hay
  algunos `print` heredados; no añadas más).
- **Robustez:** el bot debe seguir vivo pase lo que pase. El `loop()` y los accesos
  a BD/serie usan `try/except` amplios para **no romper el proceso**. Mantén ese
  estilo defensivo en código que corra dentro del loop o en callbacks.
- **Configuración:** se lee de `env.py` con `getattr(env, 'NOMBRE', defecto)` para
  tolerar variables ausentes. Sigue ese patrón al leer nuevas variables.
- **Saneado de texto:** todo texto que vaya a BD o a la malla pasa por
  `sanitize_text` (normaliza Unicode, quita control chars, colapsa espacios).
- **Tipos:** hay anotaciones de tipo y `from __future__ import annotations` en los
  módulos nuevos. Mantenlo.
- **Sin estado global mutable** más allá de `SerialInterface.node_dict` y los
  singletons de configuración.

---

## 8. Ejecución y pruebas

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp env.example.py env.py          # editar valores
python3 create_db.py              # opcional; main.py también la crea
python3 main.py                   # proceso principal (necesita serie real)
python3 cron_tasks.py             # una pasada de tareas periódicas
```

- No hay suite de tests automatizada. `tests/test.py` es solo un ejemplo de recepción.
- Para validar cambios sin hardware: `create_db.py` y la lógica de `Database` se
  pueden ejercitar sin nodo. La parte de serie requiere un nodo Meshtastic conectado
  (o un puerto serie simulado).
- Comprueba que el código compila: `python3 -m py_compile $(git ls-files '*.py')`.

---

## 9. Qué NO hacer

- ❌ No abrir el puerto serie desde `cron_tasks.py` ni desde callbacks: encola en BD.
- ❌ No versionar secretos ni datos locales. Están en `.gitignore`: `env.py`,
  `database.sql*`, `.venv`, `.junie`, `.idea`. **Nunca** los añadas al repo.
- ❌ No introducir PostgreSQL ni otro motor: el proyecto es SQLite por diseño (RPi
  Zero, sin servicio que mantener).
- ❌ No superar ~200 caracteres por mensaje a la malla.
- ❌ No renombrar un fichero de `Commands/` sin actualizar su import en `data.py`.
- ❌ No bloquear el `loop()` con esperas largas; usa colas/estado en BD.

---

## 10. Dependencias y versiones

`requirements.txt` declara versiones mínimas. Validado con (entorno actual):

| Paquete | Mínimo en requirements | Probado | Última publicada |
|---|---|---|---|
| meshtastic | `>=2.7.5` | 2.7.5 | 2.7.8 |
| pypubsub | `>=4.0.3` | 4.0.3 | 4.0.3 |
| requests | `>=2.32.0` | 2.32.5 | 2.34.x |

`SerialInterface.traceroute()` está escrito de forma **defensiva** (prueba varias
firmas de `sendTraceRoute`) precisamente para sobrevivir a cambios de API entre
versiones de `meshtastic`. Si actualizas la librería, prueba un traceroute real.

---

## 11. Punteros rápidos

- Añadir comando → §5 y `docs/info/07-comandos.md`.
- Tocar el esquema → `create_db.py` + `docs/info/03-base-de-datos.md`.
- Lógica de radio/serie → `Models/SerialInterface.py` + `docs/info/04-interfaz-serial.md`.
- AEMET → `Models/Aemet.py`, `cron_tasks.py`, `main.py` + `docs/info/09-aemet.md`.
- Traces → `cron_tasks.send_trace`, `main.loop`, `Database` + `docs/info/08-traceroute.md`.

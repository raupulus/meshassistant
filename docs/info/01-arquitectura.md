# 01 · Arquitectura

## Visión general

`meshassistant` está formado por **dos procesos** que se coordinan exclusivamente a
través de una base de datos **SQLite** compartida. Ninguno llama al otro
directamente; el acoplamiento es la base de datos.

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

## Proceso principal — `main.py`

Servicio de larga duración. Responsabilidades:

1. `ensure_database()` — crea/migra el esquema SQLite al arrancar.
2. `SerialInterface.connect()` — abre el puerto serie y se suscribe a los eventos
   de `pubsub`.
3. Bucle infinito `loop()` que cada ~5 s:
   - **Procesa el trace pendiente más antiguo** (`get_next_pending_trace`): ejecuta
     el traceroute por serie, parsea hasta 7 saltos de ida y 7 de vuelta, y guarda
     el resultado en la misma fila (`mark_trace_done_with_route`).
   - **Publica la siguiente alerta AEMET** sin publicar, si hay `AEMET_API_KEY` y la
     hora está dentro de la ventana, respetando el periodo por canal.
4. Recepción de mensajes: dirigida por eventos (`on_receive_text`), no por *polling*.

Es el **único proceso** que abre el puerto serie.

## Tareas periódicas — `cron_tasks.py`

Pensado para ejecutarse **cada minuto desde cron**. En cada pasada (`run_all`):

- `chiste_upload()` — sube chistes pendientes (cooldown 5 min).
- `chiste_download()` — descarga chistes nuevos (cooldown 10 min).
- `send_trace()` — selecciona un nodo candidato y **encola** un trace en la tabla
  `traces` (no abre el serie). Respeta `ENABLE_TRACES` y los intervalos.
- `check_aemet()` — descarga avisos CAP de AEMET (cooldown 60 min) y los guarda.

El *throttling* se apoya en la tabla `tasks_control`.

## Por qué dos procesos

El puerto serie del nodo Meshtastic **solo puede abrirlo un proceso**. Si el cron
intentara hacer radio mientras `main.py` tiene el serie abierto, habría conflicto.
Solución: el cron deja trabajo **en cola** (filas en SQLite) y `main.py` lo ejecuta
cuando puede. Esto también aporta **tolerancia a fallos**: si el nodo se desconecta
o se reinicia, el trabajo permanece encolado y se procesa al reconectar.

## Tolerancia a fallos

- **Reconexión serie:** `on_connection_lost` cierra y reintenta `connect()` en bucle
  mientras exista el dispositivo (`os.path.exists(serial_port)`).
- **Errores aislados:** el `loop()` envuelve cada bloque (traces, AEMET) en
  `try/except` para que un fallo puntual no tire el proceso.
- **BD como verdad persistente:** pings, nodos, traces, alertas y comandos quedan en
  SQLite aunque el serie esté caído.

## Diagrama de flujo de un comando

```
Mensaje de la malla
  → pubsub "meshtastic.receive.text"
  → SerialInterface.on_receive_text
  → construye metadata (directo/canal, snr, rssi, via_mqtt)
  → functions.search_command(msg)
  → ¿comando válido?  → sí → ¿in_group o es directo? → callback(...)
                               → interface.reply_to_message(...)
                               → Database.log_command(...)
```

Ver también: [04-interfaz-serial.md](04-interfaz-serial.md),
[07-comandos.md](07-comandos.md), [08-traceroute.md](08-traceroute.md),
[09-aemet.md](09-aemet.md).

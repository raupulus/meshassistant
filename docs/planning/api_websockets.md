# Planificación y Análisis: Pasarela WiFi en Tiempo Real (WebSockets / IPC) para Meshassistant

> **Archivo de referencia y prompt maestro** para la futura implementación de la pasarela de control y monitoreo en tiempo real vía WiFi, orientada a microcontroladores (**Raspberry Pi Pico W / Pico 2 W**) y aplicaciones locales (móviles, escritorio, web).

---

## 1. Contexto y Objetivos

### 1.1. Situación Actual
- **Hardware base:** Raspberry Pi Zero 2 W (Quad-Core Cortex-A53 @ 1.0 GHz, 512 MB RAM, WiFi 2.4 GHz) conectada por UART/serie a un nodo Meshtastic LoRa.
- **Arquitectura actual:** Daemon principal (`main.py`) con control exclusivo del puerto serie + tareas periódicas (`cron_tasks.py`) coordinadas mediante base de datos SQLite en modo WAL.
- **Comportamiento del bot:** Máxima estabilidad y prioridad para la recepción y emisión de paquetes de radio Meshtastic (LoRa).

### 1.2. Qué se desea conseguir
1. Disponer de un canal de comunicación agnóstico vía **WiFi (WebSockets / API)** en la Raspberry Pi Zero 2 W.
2. Permitir que cualquier cliente (microcontroladores ligeros como Pico W, dashboards web, apps móviles o scripts de automatización) pueda:
   - Recibir en **tiempo real (push)** todo lo que ocurre en la malla LoRa.
   - Consultar el **estado global** (nodos, routers, histórico de pings/traces, estadísticas, telemetría).
   - **Enviar acciones y órdenes al bot/nodo** de forma segura y sin riesgo para la radio.
3. Establecer un **Contrato Formal de API / WebSocket** inmutable y versionado que sirva de especificación estricta tanto para el servidor como para el desarrollo de proyectos clientes externos.

---

## 2. Configuración de Red, Puerto y Servicio del Sistema

### 2.1. Puerto y Host de Red
- **Puerto por defecto:** **`8680`** (Referencia mnemotécnica a la banda LoRa europea de 868 MHz; no colisiona con puertos habituales como 80, 443, 8080, 8000, 3000 o 5000).
- **Host por defecto:** `0.0.0.0` (Escucha en la interfaz WiFi local de la Raspberry Pi Zero 2 W).
- **Configuración en `env.py`:**
  - `GATEWAY_WS_HOST = getattr(env, 'GATEWAY_WS_HOST', '0.0.0.0')`
  - `GATEWAY_WS_PORT = getattr(env, 'GATEWAY_WS_PORT', 8680)`
  - `GATEWAY_API_TOKEN = getattr(env, 'GATEWAY_API_TOKEN', None)` (Opcional, autenticación en handshake).

### 2.2. Servicio Independiente en `systemd`
El servidor WebSocket correrá como un servicio de sistema (`meshassistant-gateway.service`) separado de `main.py`:
- Si el servicio WebSocket se reinicia o falla, `systemd` lo recupera automáticamente (`Restart=always`) sin afectar en ningún momento a `main.py` ni al puerto serie UART.

---

## 3. Análisis de Viabilidad y Costes de Hardware

### 3.1. Capacidad del Servidor (Raspberry Pi Zero 2 W)
- **Carga de CPU:** El tráfico de radio LoRa oscila habitualmente entre 0.1 y 2 paquetes por segundo. Emitir un datagrama JSON no bloqueante por Unix Domain Socket toma ~0.045 ms por paquete (menos del 0.01% de uso de CPU en `main.py`).
- **Arquitectura Quad-Core:** La CPU de 4 núcleos permite que el servidor WebSocket (`Services/Gateway.py`) corra de forma aislada en un hilo/núcleo independiente sin competir con el bucle UART del bot.
- **Consumo de Memoria:** El proceso del WebSocket consume ~15–20 MB de RAM en reposo (disponibles > 300 MB en el sistema).
- **Tráfico de Red:** ~0.15–0.5 KB/s en WiFi local.

### 3.2. Capacidad de Clientes Ligeros (Raspberry Pi Pico W / Pico 2 W)
- Payloads JSON planos, compactos y con claves directas para garantizar un parseo rápido en MicroPython o C/C++ sin problemas de memoria RAM (264 KB en Pico W).

---

## 4. Catálogo Completo de Entradas y Salidas del WebSocket

### 4.1. Salidas (Eventos Push emitidos por el Bot hacia los Clientes)

Todos los eventos siguen un esquema unificado y compacto:
```json
{
  "event": "<nombre_evento>",
  "ts": "2026-08-21T20:00:00",
  "data": { ... }
}
```

1. **`message_rx`:** Mensaje de texto recibido en canal o privado.
   - `data`: `{ "from": "!12345678", "from_name": "rau5", "to": "^all", "channel": 0, "text": "Hola", "snr": 7.2, "rssi": -70, "hops": 1, "via_mqtt": false }`
2. **`local_node_info`:** Información y configuración del nodo local de radio conectado al bot.
   - `data`: `{ "my_node_id": "!63ca1feb", "name": "Raupulus Bot", "short_name": "rauB", "firmware": "2.5.6", "region": "EU_868" }`
3. **`node_discovered` / `node_updated`:** Alta o actualización de metadatos de un nodo.
   - `data`: `{ "id": "!12345678", "name": "Raupulus", "short_name": "rau5", "hw_model": 79, "role": 1, "snr": 8.0, "last_heard": 1755800000 }`
4. **`device_telemetry`:** Telemetría de batería, voltaje y uptime de un nodo.
   - `data`: `{ "id": "!12345678", "battery": 95, "voltage": 4.12, "uptime_seconds": 12450 }`
5. **`channel_metrics`:** Utilización de canal y tiempo en el aire de la frecuencia LoRa.
   - `data`: `{ "channel_util": 4.25, "air_util_tx": 0.18 }`
6. **`trace_completed`:** Resultado estructurado de un traceroute.
   - `data`: `{ "trace_id": 12, "to": "!12345678", "to_name": "Raupulus", "hops_forward": [...], "hops_backward": [...] }`
7. **`router_status`:** Salud y conectividad de repetidores clave (`ROUTER_NODES`).
   - `data`: `{ "routers": [ {"id": "!11111111", "name": "RPT-Norte", "status": "online", "snr": 9.5, "last_seen_sec": 120} ] }`
8. **`message_ack`:** Confirmación de entrega o estado de envío de un mensaje por radio.
   - `data`: `{ "req_id": "msg_001", "dest": "!12345678", "status": "delivered", "hops": 1, "snr": 8.5 }`
9. **`poll_created` / `poll_closed`:** Notificación de encuestas comunitarias activas o cerradas.
   - `data`: `{ "poll_id": 1, "owner": "!12345678", "question": "¿Quedada LoRa?", "options": ["Sí", "No"], "ends_at": "..." }`
10. **`traffic_stats` / `traffic_anomaly`:** Estadísticas de tráfico y detección de flood/spam.
    - `data`: `{ "total_pkts_min": 14, "top_senders": [{"id": "!12345678", "pkts": 9}], "alert": null }`
11. **`position_rx`:** Telemetría de coordenadas GPS de nodos.
    - `data`: `{ "id": "!12345678", "lat": 36.5297, "lon": -6.2926, "alt": 15 }`
12. **`system_status` (Heartbeat):** Estado del bot y del enlace serie.
    - `data`: `{ "uart_connected": true, "bot_uptime": 86400, "clients_connected": 2, "pending_traces": 0 }`
13. **`aemet_alert`:** Avisos meteorológicos oficiales.
    - `data`: `{ "level": "amarillo", "province": "Cadiz", "message": "Viento fuerte en litoral" }`

### 4.2. Entradas (Acciones que cualquier Cliente puede enviar al WebSocket)

Estructura de petición estándar:
```json
{
  "action": "<nombre_accion>",
  "req_id": "opcional_correlacion",
  "params": { ... }
}
```

1. **`send_message`:** Envía un mensaje a la malla (canal o privado).
   - `params`: `{ "text": "Mensaje", "dest": "^all", "channel": 0 }`
2. **`request_trace`:** Encola un traceroute hacia un nodo destino.
   - `params`: `{ "dest": "!12345678" }`
3. **`request_nodeinfo`:** Solicita al nodo local enviar petición NodeInfo a un nodo remoto.
   - `params`: `{ "dest": "!12345678" }`
4. **`get_snapshot`:** Solicita el estado actual completo al conectar.
   - `params`: `{ "include": ["nodes", "routers", "recent_messages", "traffic_stats", "system_status", "local_node"] }`
5. **`get_polls`:** Consulta la lista de encuestas activas y recuento de votos.
   - `params`: `{}`
6. **`vote_poll`:** Emite el voto a una opción de una encuesta activa.
   - `params`: `{ "poll_id": 1, "option_index": 0 }`
7. **`get_weather`:** Obtiene la predicción meteorológica descargada en BD (offline).
   - `params`: `{}`
8. **`get_tides`:** Obtiene la predicción de mareas descargada en BD (offline).
   - `params`: `{}`
9. **`set_node_favorite`:** Marca o desmarca un nodo como favorito en la base de datos.
   - `params`: `{ "node_id": "!12345678", "is_favorite": true }`
10. **`restart_serial`:** Solicita al daemon reiniciar el enlace serie UART (diagnóstico/recuperación).
    - `params`: `{}`

---

## 5. Decisiones Arquitectónicas Adoptadas

```
                                ARQUITECTURA PROPUESTA
                                
   ┌─────────────────────────────────────────────────────────────────────────────┐
   │                         RASPBERRY PI ZERO 2 W                               │
   │                                                                             │
   │   ┌────────────────────────┐                  ┌─────────────────────────┐   │
   │   │  main.py (Daemon UART) │                  │  Gateway.py (Daemon)    │   │
   │   │  - Dueño único serie   │                  │  - Servidor WebSocket   │   │
   │   │  - Procesa radio LoRa  │                  │  - Puerto 8680          │   │
   │   │  - Despacha comandos   │                  │  - Ring Buffer en RAM   │   │
   │   └──────────┬─────────────┘                  └────────────┬────────────┘   │
   │              │ (Push en < 0.05ms)                          │                │
   │              ├──────────────────────┬──────────────────────┤                │
   │              ▼                      │                      ▼                │
   │       [ Unix Socket DGRAM ]         │             [ Clientes Conectados ]   │
   │      (/tmp/mesh_events.sock)        │                      │                │
   │      (Solo Memoria RAM)             ▼                      │ (WiFi :8680)   │
   │                           ┌──────────────────┐             │                │
   │                           │  SQLite (WAL)    │             │                │
   │                           │  (database.sql)  │             │                │
   │                           │  - Persistencia  │             │                │
   │                           │  - Cola acciones │             │                │
   │                           └──────────────────┘             │                │
   └────────────────────────────────────────────────────────────┼────────────────┘
                                                                │
                                            ┌───────────────────┴───────────────────┐
                                            ▼                                       ▼
                                ┌──────────────────────┐                ┌───────────────────────┐
                                │ Raspberry Pi Pico W  │                │ Apps Móvil / Web / PC │
                                │ (MicroPython / C++)  │                │ (Dashboard agnóstico) │
                                └──────────────────────┘                └───────────────────────┘
```

1. **Aislamiento absoluto:** `Gateway.py` corre como servicio independiente (`meshassistant-gateway.service`). Si cae la red WiFi o un cliente falla, el bot de radio (`main.py`) ni se entera.
2. **Cero escrituras para mensajes ordinarios:** Los mensajes de chat viajan puramente en memoria a través del socket Unix DGRAM, con un *ring buffer* en RAM en el servidor WS (últimos 20) para alimentar a clientes recién conectados.
3. **Persistencia limpia:** SQLite WAL se reserva para nodos, pings, traces completados y cola de acciones entrantes.
4. **Documentación desacoplada y Contrato de API:** Todo el módulo se documenta en el directorio dedicado `docs/info/gateway/`, incluyendo el **Contrato Formal de API**.

---

## 6. Documentación Dedicada y Contrato Formal

Estructura de archivos técnicos que se crearán para el módulo:
- `docs/info/gateway/00-indice.md`: Visión global y arquitectura.
- `docs/info/gateway/01-arquitectura-ipc.md`: Diseño del Unix Domain Socket y desacoplamiento de procesos.
- **`docs/info/gateway/02-contrato-api-websocket.md`:** **Documento de Contrato Formal (Inmutable/Versionado).** Especifica con exactitud los esquemas JSON de eventos, acciones, campos obligatorios, tipos de datos, códigos de error y directivas de compatibilidad hacia atrás. Este archivo está diseñado para ser copiado directamente a proyectos de clientes externos como especificación técnica garantizada.
- `docs/info/gateway/03-guia-cliente-micropython.md`: Guía de consumo desde MicroPython (manejo de sockets, payloads y reconexión).
- `docs/info/gateway/04-servicio-systemd.md`: Guía de despliegue y archivo `.service` para systemd.

---

## 7. Prompt Maestro para Futura Implementación

Copia y utiliza el siguiente prompt cuando desees iniciar el desarrollo de este módulo:

```markdown
Actúa como ingeniero senior de software embebido y Python. Vamos a implementar la pasarela WiFi en tiempo real (WebSockets + IPC) para meshassistant siguiendo el diseño y directrices de `docs/planning/next_info.md`.

### Reglas estrictas a respetar:
1. El bot de radio (`main.py` y `Models/SerialInterface.py`) tiene máxima prioridad y nunca debe bloquearse ni degradarse por operaciones de red.
2. `main.py` es el ÚNICO proceso que abre el puerto serie UART.
3. Toda la comunicación en tiempo real del bot hacia la pasarela se realiza mediante Unix Domain Sockets DGRAM no bloqueantes (`/tmp/meshassistant_events.sock`).
4. SQLite (modo WAL) se utiliza para persistencia histórica estructural (nodos, pings, traces completados) y cola de acciones. NO se guardan mensajes de chat ordinarios en SQLite (solo viajan en RAM por socket).
5. Crear y formalizar el Contrato de API en `docs/info/gateway/02-contrato-api-websocket.md` como especificación estricta e inmutable para proyectos clientes.
6. El servicio WebSocket escuchará por defecto en el puerto 8680 (configurable en `env.py`) y dispondrá de su archivo de servicio systemd.
7. Código y comentarios en español conforme a las reglas del repositorio.

### Tareas a ejecutar:
1. **Emisor de eventos IPC en `Models/EventBroadcaster.py`:** Módulo ligero para enviar datagramas JSON sin bloqueo desde los callbacks de `SerialInterface.py` y `main.py`.
2. **Servidor de Pasarela `Services/Gateway.py`:** Proceso asíncrono (`asyncio` / `websockets`) que:
   - Escucha en el puerto `8680` (o `GATEWAY_WS_PORT`).
   - Escucha datagramas del Unix Socket y los retransmite a los clientes WebSocket conectados.
   - Mantiene un buffer circular en RAM (últimos 20 mensajes) para clientes recién conectados.
   - Responde a solicitudes de snapshot inicial y telemetría leyendo de SQLite y memoria.
   - Recibe comandos y acciones de los clientes (`send_message`, `request_trace`, `request_nodeinfo`, `get_polls`, `vote_poll`, `get_weather`, `get_tides`, `set_node_favorite`, `restart_serial`) y los procesa de forma segura.
3. **Integración en `main.py` y `Models/SerialInterface.py`:** Emitir eventos para `message_rx`, `local_node_info`, `node_discovered`, `node_updated`, `device_telemetry`, `channel_metrics`, `position_rx`, `trace_completed` y `system_status`.
4. **Contrato Formal y Documentación en `docs/info/gateway/`:**
   - Crear `00-indice.md`, `01-arquitectura-ipc.md`, `02-contrato-api-websocket.md` (Contrato estricto), `03-guia-cliente-micropython.md` y `04-servicio-systemd.md`.
5. **Cliente de prueba para MicroPython / Pico W (`clients/pico_w_sample.py`):** Script de ejemplo agnóstico que conecta vía WiFi y procesa los eventos.
```

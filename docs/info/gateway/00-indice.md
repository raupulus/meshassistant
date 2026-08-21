# 00 · Índice de la Pasarela Gateway (WiFi / WebSockets / IPC)

La **Pasarela Gateway** de `meshassistant` es un servicio desacoplado y en tiempo real que expone los eventos y el estado de la red Meshtastic a través de **WiFi mediante WebSockets** en el puerto **`8680`**.

Está diseñada para permitir que microcontroladores ligeros (**Raspberry Pi Pico W / Pico 2 W** con pantalla), paneles web, aplicaciones móviles o sistemas domóticos (Home Assistant) puedan monitorear e interactuar con la malla LoRa de forma 100% segura y sin interferir en el daemon principal de radio (`main.py`).

---

## Estructura de la Documentación

1. [**01 · Arquitectura e IPC**](01-arquitectura-ipc.md): Desacoplamiento de procesos, Unix Domain Sockets DGRAM, rendimiento y aislamiento de fallos.
2. [**02 · Contrato Formal de API / WebSocket**](02-contrato-api-websocket.md): **Especificación estricta e inmutable** de todos los eventos JSON emitidos y acciones recibidas. *Documento exportable a repositorios de clientes externos.*
3. [**03 · Guía de Cliente MicroPython**](03-guia-cliente-micropython.md): Ejemplos de conexión, consumo de eventos y manejo de reconexiones en Raspberry Pi Pico W.
4. [**04 · Servicio Systemd**](04-servicio-systemd.md): Configuración y despliegue del servicio `meshassistant-gateway.service`.

---

## Resumen Rápido de Configuración (`env.py`)

| Variable | Tipo | Defecto | Descripción |
|---|---|---|---|
| `GATEWAY_WS_HOST` | `str` | `"0.0.0.0"` | Dirección IP de escucha del servidor WebSocket. |
| `GATEWAY_WS_PORT` | `int` | `8680` | Puerto TCP de escucha (referencia a 868 MHz). |
| `GATEWAY_EVENTS_SOCKET` | `str` | `"/tmp/meshassistant_events.sock"` | Ruta del socket Unix DGRAM para IPC. |
| `GATEWAY_API_TOKEN` | `str` | `None` | Token de autenticación opcional en handshake. |

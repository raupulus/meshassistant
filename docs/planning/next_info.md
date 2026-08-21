# Planificación y Análisis: Mini Dashboard Web Integrado para Meshassistant

> **Archivo de referencia y prompt maestro** para la implementación de un mini dashboard web ligero (HTML5 + CSS local autocontenido + JS Vanilla) servido directamente en el puerto **`8680`** por la pasarela `Services/Gateway.py`.

---

## 1. Contexto y Objetivos

### 1.1. Situación Actual
- La pasarela [`Services/Gateway.py`](../../Services/Gateway.py) está desplegada y activa en el puerto `8680`, funcionando como servidor WebSocket puro (`ws://<ip>:8680`).
- Actualmente, para consultar la información se requiere un cliente WebSocket programático (como el script `clients/pico_w_sample.py` o un microcontrolador Pico W).

### 1.2. Qué se desea conseguir
1. Permitir que cualquier usuario en la red local pueda abrir su navegador web (móvil, tablet o PC) y acceder a **`http://<ip_raspberry>:8680`** para visualizar y gestionar el bot en tiempo real.
2. Servir los archivos web estáticos **directamente desde `Services/Gateway.py`** en el mismo puerto `8680`, sin necesidad de instalar ni configurar servidores web externos (`lighttpd`, `nginx` o `apache`).
3. **100% Offline (Cero Dependencias de Internet / Sin CDNs externas):** Todos los recursos (HTML, CSS, JS, iconos SVG inline y fuentes de sistema) residirán localmente en el directorio `web/` para funcionar en redes aisladas o sin acceso a Internet.
4. Crear un **dashboard SPA (Single Page Application)** ultra ligero, sin dependencias pesadas ni frameworks de compilación (Node.js/npm), utilizando únicamente:
   - **HTML5 semántico**
   - **CSS autocontenido local** (diseño moderno con tema oscuro, responsive y utilidades visuales)
   - **JavaScript Vanilla** (manejo nativo de WebSocket, reconexión automática y renderizado dinámico del DOM)
5. Estructurar la documentación técnica del módulo en un directorio propio e independiente: **`docs/info/web/`**.

---

## 2. Análisis de Viabilidad y Costes de Hardware

| Aspecto | Evaluación | Justificación Técnica |
|---|---|---|
| **CPU (RPi Zero 2W)** | **~0% (Inapreciable)** | Servir los 3 archivos estáticos (HTML, JS y CSS) al cargar la página toma **menos de 2 ms**. El procesamiento de renderizado visual corre en la CPU/GPU del navegador del cliente (móvil/PC), no en la Raspberry Pi. |
| **Memoria RAM** | **0 MB extra** | Se integra en el mismo proceso `meshbotassistant-gateway.service`, que ya consume apenas ~15–20 MB. |
| **Concurrencia (1–3 clientes)** | **Óptima** | El tráfico de actualización en vivo es el mismo flujo WebSocket ligero (< 0.15 KB/s) ya probado. |
| **Aislamiento del Bot** | **Garantizado** | `main.py` sigue operando de forma 100% aislada con su puerto serie UART y su socket Unix IPC. |

---

## 3. Arquitectura del Servidor Web Integrado

```
                              PUERTO UNIFICADO :8680 (100% OFFLINE)
                              
Navegador Web (Móvil / PC en LAN)
    │
    ├─ 1. HTTP GET http://172.18.1.110:8680 ──────► Gateway.py sirve web/index.html (200 OK)
    │                                                   ├─ web/app.js (Local, JS Vanilla)
    │                                                   └─ web/style.css (Local, Autocontenido)
    │
    └─ 2. WebSocket ws://172.18.1.110:8680 ───────► Handshake WebSocket (101 Switching Protocols)
                                                        └─ Streaming push y envío de acciones
```

### 3.1. Manejador HTTP en `Services/Gateway.py`
Se implementa el hook `process_request` nativo de `websockets.serve`:
- Si la petición entrante es un `GET` HTTP estándar (`/`, `/app.js`, `/style.css`), lee el archivo correspondiente del directorio `web/` y devuelve una respuesta HTTP con el `Content-Type` adecuado (`text/html; charset=utf-8`, `application/javascript`, `text/css`) y cabeceras de caché.
- Si la petición contiene la cabecera `Upgrade: websocket`, se delega al manejador de WebSocket `_ws_handler`.

---

## 4. Diseño y Funcionalidades del Mini Dashboard

### 4.1. Estructura de Ficheros (Directorio `web/`)
```
web/
├── index.html       # Estructura del dashboard, layouts, navegación y modales
├── app.js           # Lógica WebSocket, gestión de estado y renderizado dinámico
└── style.css        # CSS autocontenido (tema oscuro, badges, flex/grid y tipografía de sistema)
```

### 4.2. Módulos y Pestañas del Dashboard

1. **Barra de Estado Superior (Header):**
   - Indicador de estado del enlace serie UART (Punto Verde / Rojo).
   - Indicador de estado de la conexión WebSocket local (Conectado / Reconectando).
   - Identidad del nodo local de la Raspberry Pi (`short_name`, `id`, `batería`).
   - Barra de ocupación del espectro LoRa (`channelUtilization` % y `airUtilTx` %).
   - Uptime del bot.

2. **Pestaña 1 · Live Chat (Mensajes en Tiempo Real):**
   - Feed de mensajes con desplazamiento automático.
   - Badges visuales por canal (Canal 0 público, directos privados, etc.).
   - Metadatos por mensaje: Remitente (nombre largo + corto), SNR (dB), RSSI (dBm), saltos y flag MQTT.
   - Formulario inferior para componer y enviar mensajes a la malla (selección de canal o destinatario privado).

3. **Pestaña 2 · Routers y Repetidores:**
   - Tarjetas de estado para los repetidores configurados en `ROUTER_NODES`.
   - Estado en tiempo real (`Online`/`Offline`), tiempo transcurrido desde el último paquete y SNR medio.
   - Botón directo para solicitar un traceroute de diagnóstico hacia el repetidor.

4. **Pestaña 3 · Nodos Descubiertos:**
   - Buscador interactivo en tiempo real por nombre corto, nombre largo o ID hexadecimal.
   - Tabla con: Nombre, ID, Rol (`CLIENT`, `ROUTER`, `REPEATER`), Modelo de hardware, SNR, Batería y botón para marcar como favorito.

5. **Pestaña 4 · Traceroutes y Topología:**
   - Visor gráfico y textual de los últimos traceroutes realizados.
   - Diagrama lineal de saltos con SNR tramo a tramo (ida y vuelta).

6. **Pestaña 5 · Encuestas y Meteorología:**
   - Visualización de encuestas comunitarias activas con barras de porcentaje de votos.
   - Botones para emitir voto directo desde el navegador.
   - Tarjeta con la última predicción meteorológica descargada de AEMET.

---

## 5. Documentación Dedicada (`docs/info/web/`)

La documentación de este módulo se organizará en su propio directorio:
- **`docs/info/web/00-indice.md`:** Visión general, acceso y configuración.
- **`docs/info/web/01-arquitectura-servidor-http.md`:** Funcionamiento del servidor de estáticos integrado en `Gateway.py`.
- **`docs/info/web/02-componentes-y-pestanas.md`:** Guía detallada de cada panel interactivo del frontend.
- **`docs/info/web/03-guia-offline-estilos.md`:** Especificación de CSS/JS autocontenido y diseño 100% offline.

---

## 6. Prompt Maestro para Futura Implementación

Copia y utiliza el siguiente prompt cuando desees iniciar el desarrollo de este módulo:

```markdown
Actúa como ingeniero senior full-stack (Python + Frontend ligero). Vamos a implementar el mini dashboard web integrado para meshassistant siguiendo la planificación de `docs/planning/next_info.md`.

### Reglas estrictas a respetar:
1. El dashboard debe ser 100% OFFLINE (cero dependencias de Internet, sin CDNs externas). Todo el CSS, JS e iconos deben residir localmente en `web/`.
2. Servirse directamente desde `Services/Gateway.py` en el puerto 8680 mediante el manejador HTTP nativo de `websockets`, sin instalar servidores web externos.
3. El frontend debe ser SPA ligero en `web/` con HTML5, CSS autocontenido y JavaScript Vanilla (sin Node.js ni bundlers).
4. Todo el flujo de datos en tiempo real debe comunicarse con el WebSocket local mediante el Contrato Formal definido en `docs/info/gateway/02-contrato-api-websocket.md`.
5. El bot de radio (`main.py`) y la prioridad del puerto serie UART no deben verse afectados en absoluto.
6. Crear la suite de documentación dedicada en `docs/info/web/` y mantener `AGENTS.md` y `docs/info/00-indice.md` actualizados.
7. Código y comentarios en español conforme a las reglas del repositorio.

### Tareas a ejecutar:
1. **Soporte HTTP Estático en `Services/Gateway.py`:** Implementar el callback `process_request` para servir los archivos del directorio `web/` (`index.html`, `app.js`, `style.css`) con Content-Type y cabeceras correctas.
2. **Estructura HTML en `web/index.html`:** Layout responsive, barra de estado superior, navegación por pestañas (Chat, Routers, Nodos, Traces, Encuestas/Tiempo) y modales.
3. **Lógica Frontend en `web/app.js`:**
   - Conexión y reconexión automática WebSocket a `ws://<host>:8680`.
   - Procesamiento de eventos en tiempo real (`message_rx`, `device_telemetry`, `channel_metrics`, `node_updated`, `trace_completed`, `system_status`, `router_status`, `poll_created`).
   - Envío de acciones (`get_snapshot`, `send_message`, `request_trace`, `vote_poll`, `set_node_favorite`).
4. **Estilos Locales en `web/style.css`:** CSS moderno y autocontenido (tema oscuro, animaciones de pulso para estado, barras de progreso y tipografía de sistema).
5. **Tests automatizados en `tests/test_gateway_http.py`:** Validar que `Services/Gateway.py` responde correctamente con HTTP 200 y los ficheros estáticos a peticiones GET de navegadores.
6. **Documentación Completa en `docs/info/web/`:** (Índice, arquitectura servidor HTTP, componentes y guía offline).
```

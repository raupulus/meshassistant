# Módulo Web: Mini Dashboard Integrado 100% Offline

El módulo web proporciona una interfaz gráfica moderna, ligera y completamente autocontenida (Single Page Application) que se sirve directamente desde la pasarela `Services/Gateway.py` en el puerto **`8680`**.

Está pensado para monitorizar y operar el bot de Meshtastic desde cualquier navegador en la red local (móvil, tablet o PC) entrando en **`http://<ip_raspberry>:8680`**.

---

## 1. Características Principales

- **Cero servidores web externos:** No requiere `lighttpd`, `nginx` ni `apache`. El servidor HTTP está integrado en `Services/Gateway.py` mediante el hook `process_request` de `websockets`.
- **100% Offline (Zero CDNs):** No depende de Internet. Todo el CSS, JS, fuentes del sistema e iconos vectoriales SVG inline residen en la carpeta `web/`.
- **Tiempo Real:** Se conecta mediante WebSocket bidireccional contra el mismo puerto para recibir eventos push y enviar acciones a la malla.
- **Responsive:** Adaptable para smartphones, tablets y pantallas de escritorio.

---

## 2. Índice de Documentación

| # | Documento | Contenido |
|---|---|---|
| 01 | [Arquitectura del Servidor HTTP](01-arquitectura-servidor-http.md) | Hook HTTP nativo, resolución segura de estáticos y prevención de path traversal. |
| 02 | [Componentes y Pestañas](02-componentes-y-pestanas.md) | Detalle de las 5 pestañas: Chat en vivo, Routers, Nodos, Traceroutes y Encuestas/Clima. |
| 03 | [Guía Offline y Estilos](03-guia-offline-estilos.md) | Estructura de `style.css` y `app.js`, diseño responsive y utilidades. |

---

## 3. Acceso Rápido

- URL Local en la Raspberry Pi: `http://172.18.1.110:8680` (o `http://localhost:8680` si se accede en local).
- Puerto configurado: `GATEWAY_WS_PORT = 8680` en `env.py`.

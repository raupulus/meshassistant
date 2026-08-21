# 01 · Arquitectura del Servidor HTTP Integrado

## 1. Funcionamiento del Hook `process_request`

Para evitar procesos adicionales y mantener el consumo de RAM al mínimo en la Raspberry Pi Zero 2W, `Services/Gateway.py` utiliza el parámetro `process_request` del servidor asíncrono `websockets`:

```
                             PUERTO UNIFICADO TCP 8680
                                        │
             ┌──────────────────────────┴──────────────────────────┐
             ▼                                                     ▼
      [ Petición HTTP GET ]                                 [ WebSocket Upgrade ]
     (GET /, /app.js, /style.css)                          (Upgrade: websocket)
             │                                                     │
             ▼                                                     ▼
   _process_http_request()                                    _ws_handler()
   - Lee archivo de web/                                  - Handshake RFC 6455
   - Retorna Response(200, Content-Type)                  - Streaming push de eventos
```

---

## 2. Resolución de Archivos y Seguridad

1. **Ruta Raíz (`/`):** Peticiones a `/` o vacías se resuelven automáticamente a `/index.html`.
2. **Prevención de Directory Traversal:** Se valida mediante `os.path.abspath` que la ruta solicitada permanezca estrictamente dentro del directorio base `web/`. Cualquier intento con `../` se responde inmediatamente con `404 Not Found`.
3. **MIME Types Soportados:**
   - `.html` ➔ `text/html; charset=utf-8`
   - `.js` ➔ `application/javascript; charset=utf-8`
   - `.css` ➔ `text/css; charset=utf-8`
   - `.svg` ➔ `image/svg+xml`
   - `.json` ➔ `application/json; charset=utf-8`
   - `.png` ➔ `image/png`
   - `.ico` ➔ `image/x-icon`
4. **Cabeceras de Control de Caché:** Se envían cabeceras `Cache-Control: no-cache, no-store, must-revalidate` para asegurar que los navegadores móviles carguen siempre la última versión de la SPA.

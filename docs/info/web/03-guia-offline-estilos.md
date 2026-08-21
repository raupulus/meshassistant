# 03 · Guía Offline y Estilos CSS Autocontenidos

## 1. Principio de Cero Dependencias de Internet

En situaciones de emergencia o despliegues en campo (montaña, repetidores aislados o cortes de fibra), el bot opera en una red Wi-Fi local sin acceso a Internet.

Por este motivo, la interfaz web cumple estrictamente:
- **Sin CDNs externas:** No se emplean URLs externas (`cdn.tailwindcss.com`, `fonts.googleapis.com`, `cdnjs.cloudflare.com`...).
- **Iconografía Vectorial Inline:** Todos los iconos están integrados como elementos `<svg>` directos en el HTML.
- **Tipografía Nativa del Sistema Operativo:** Se utilizan las pilas tipográficas del sistema cliente (`system-ui, -apple-system, Segoe UI, Roboto...`).

---

## 2. Variables de Diseño (`web/style.css`)

El archivo `web/style.css` organiza la paleta visual mediante variables CSS nativas:

```css
:root {
  --bg-main: #0f172a;       /* slate-900 */
  --bg-card: #1e293b;       /* slate-800 */
  --bg-card-hover: #334155; /* slate-700 */
  --text-main: #f8fafc;     /* slate-50 */
  --text-muted: #94a3b8;    /* slate-400 */
  --primary: #38bdf8;       /* sky-400 */
  --success: #34d399;       /* emerald-400 */
  --danger: #f87171;        /* red-400 */
}
```

---

## 3. Resiliencia de la Conexión en `web/app.js`

- **Reconexión Automática:** Si la conexión WebSocket se interrumpe (reinicio del servicio o corte WiFi momentáneo), `app.js` ejecuta un temporizador cada 3 segundos hasta restablecer el canal.
- **Auto-recuperación de Estado:** Tras reconectar, solicita automáticamente un `get_snapshot` para sincronizar los mensajes perdidos y el estado más reciente de la radio.

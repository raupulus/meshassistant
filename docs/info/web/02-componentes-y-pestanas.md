# 02 · Componentes y Pestañas del Dashboard

La aplicación web está estructurada como una SPA (Single Page Application) reactiva en tiempo real con las siguientes secciones:

---

## 1. Barra de Estado Superior (Header)

- **Indicador UART:** LED verde cuando el bot tiene el puerto serie (`/dev/serial0`) conectado; rojo si la radio está desconectada.
- **Indicador WebSocket:** LED verde cuando el navegador mantiene el socket activo con el Gateway.
- **Nodo Local:** Nombre corto, nombre largo e ID hexadecimal (`!xxxxxxxx`) de la estación base conectada por serie.
- **Utilización del Espectro LoRa:** Porcentaje real de ocupación del canal (`Ch Util`) y tiempo de transmisión al aire (`Air Tx`) transmitidos por el nodo.

---

## 2. Pestaña 1 · Live Chat (Mensajería en Tiempo Real)

- **Feed con Scroll Dinámico y Cero Duplicados:** Muestra mensajes en tiempo real con metadatos completos:
  - Badge de canal configurado (Canal 0, Canal 1…), Privado directo o MQTT.
  - Identificación del remitente (nombre, alias corto o ID hexadecimal si carece de alias).
  - Métricas de recepción: SNR (Directo vs Último Salto) y saltos de radio.
- **Filtros Dinámicos por Canal:** Chips generados automáticamente para filtrar por canal o mensajes privados.
- **Formulario de Composición:** Selector de destino (canales públicos o nodos favoritos) y envío asíncrono no bloqueante vía cola `outbox`.

---

## 3. Pestaña 2 · Routers y Repetidores

- **Criterio de Inclusión y Monitorización:**
  - **Routers configurados manualmente (`env.ROUTER_NODES`):** Se muestran y vigilan **siempre** (tanto si están online como offline, hayan respondido o no).
  - **Routers auto-detectados (`role=ROUTER/REPEATER`):** Solo se incluyen si **han respondido con éxito un traceroute** en algún momento (`traces.status = 'done'`), evitando nodos fantasma que llegaron por rebote casual sin cobertura real.
- **Ordenación Jerárquica:**
  1. Repetidores `ONLINE` arriba y `OFFLINE` abajo.
  2. Enlaces directos ordenados por mejor SNR exterior; seguidos de los nodos con saltos ordenados por menor número de repetidores intermedios.
- **Ruta Intermedia y Calidad:**
  - **Directo a Base (RAU0):** Indicador verde con el SNR exterior del enlace.
  - **Vía Repetidores:** Indicador azul con la ruta completa y nombres legibles (`RAU0 ➔ CO01 ➔ CO04`).
- **Telemetría de Batería:** Nivel de carga (`⚡ 100%`) y voltaje (`4.18V`) cuando está disponible.
- **Acción Rápida:** Botón *"📍 Lanzar Traceroute"* con protección anti-doble clic.

---

## 4. Pestaña 3 · Nodos de la Red

- **Buscador en Vivo y Filtros de Cabecera:**
  - **Texto:** Búsqueda instantánea por nombre, alias o ID hexadecimal.
  - **Rol:** Selector de roles completo (`CLIENT`, `CLIENT_BASE`, `ROUTER`, `REPEATER`, `ROUTER_CLIENT`, `TRACKER`, `TAK_TRACKER`, `SENSOR`, `CLIENT_MUTE`, `CLIENT_HIDDEN`, `LOST_FOUND`).
  - **Preservación de Batería en Vivo:** Las actualizaciones reactivas de nodo (`node_updated`) preservan la última telemetría de batería y voltaje conocida, evitando que paquetes sin métricas borren temporalmente el estado en la tabla.
  - **Última Señal (Tiempo):** Selector desplegable junto al de roles para filtrar por ventanas de actividad o inactividad:
    - `Última señal: Todos` (sin límite temporal).
    - `Vistos hoy (≤ 24h)`: Nodos que han emitido en las últimas 24 horas.
    - `Vistos ≤ 1 semana`: Nodos activos en los últimos 7 días.
    - `Vistos ≤ 1 mes`: Nodos activos en los últimos 30 días.
    - `Apagados > 1 día`: Nodos sin señal hace más de 24 horas (ordena por defecto los más antiguos arriba).
    - `Apagados > 1 semana`: Nodos inactivos durante más de 7 días.
    - `Apagados > 1 mes`: Nodos desaparecidos hace más de 30 días.
- **Filtros Rápidos:**
  - `Todos`: Censo íntegro de la red.
  - `Con Batería 🔋`: Muestra exclusivamente los nodos con telemetría de batería/voltaje reportada, activando por defecto la ordenación ascendente para identificar nodos con batería baja (ideal para monitorizar repetidores solares en días nublados).
  - `Solo RF`: Excluye tráfico que llega por pasarelas MQTT.
  - `Favoritos ⭐`: Nodos destacados persistidos en SQLite.
- **Paginación Ágil:** Selector de 50, 100, 250 por página o "Ver todos", manteniendo el censo completo en memoria.
- **Ordenación Multidimensional Inteligente:** Posibilidad de ordenar por favoritos, rol, nombre, alias, saltos, batería, SNR, última señal o primera vez visto, manteniendo siempre los nodos con dato real arriba y los nulos al final.
- **Detalle de Columnas:**
  - **Primera Vez:** Fecha en que el nodo fue descubierto por primera vez (`DD/MM/YYYY`).
  - **Última Señal:** Formateo dinámico (`HH:MM:SS` para hoy / `DD/MM HH:MM` para días previos).
  - **Acciones:** Botón **`Trace`** (lanzar traceroute) y botón **`ℹ️ Info`** (solicitar NodeInfo por radio LoRa bajo demanda).

---

## 5. Pestaña 4 · Traceroutes

- **Visualizador de Saltos:** Representación gráfica de la ruta de ida (`Bot ➔ RPT1 (8.5dB) ➔ Destino`).
- **Control de Trazas Fallidas:** Muestra claramente el aviso `⚠️ Sin respuesta del nodo destino (Timeout / Sin cobertura)` en caso de expiración.
- **Formulario Manual:** Permite encolar un traceroute a cualquier ID o nombre corto de la red.

---

## 6. Pestaña 5 · Auditoría y Estadísticas de Comandos

- **Filtros de Período:** Selección instantánea entre **`Última hora`** (1h), **`Últimas 24h`** (por defecto), **`Últimos 7 días`** (168h) e **`Histórico Total`**.
- **Tarjetas de Resumen:** Total de comandos, nodos únicos, comando más solicitado y usuario más activo.
- **Ranking Top 20 de Nodos:** Lista de los 20 usuarios con mayor volumen de peticiones en el período, avisos de alto uso y fecha completa de última interacción.
- **Registro Cronológico Paginado:** Historial de comandos cargado en bloques de 100 con controles `◀ Anterior` / `Siguiente ▶` y buscador de texto en tiempo real.

---

## 7. Pestaña 6 · Encuestas & Clima

- **Encuestas Comunitarias:** Muestra encuestas activas, porcentaje de votos y desglose de opciones.
- **Meteorología Oficial AEMET:** Visualización de la última predicción meteorológica descargada por el bot para la provincia configurada.

---

## 8. Pestaña 7 · Mensajes Programados

- **Gestión de Automatizaciones:** Programación de difusiones periódicas o diferidas (boletines, recordatorios).
- **Control de Estado:** Activación/desactivación instantánea, edición y eliminación.

---

## 9. Pestaña 8 · Seguridad & Vigilancia de Malla

- **Nodos Auto-reportados por Mala Praxis:** Tabla en tiempo real con incidencias detectadas por `MeshWatcher`:
  - Infracción con badge e icono (`🔀 Saltos Excesivos ≥6`, `⚡ Telemetría Rápida <30m`, `📍 GPS Rápido <30m`, `👥 NodeInfo Rápido <30m`, `🌡️ Clima Rápido <30m`, `🛑 Spam Comandos`).
  - Contador de reincidencias y fecha relativa de última detección.
  - Botón **`🚫 Ignorar en Bot` / `✅ Atender`**: Descarta todo paquete del nodo en memoria sin procesar ni responder.
  - Botón **`🔒 Bloquear Radio` / `🔓 Desbloquear`**: Marca para exclusión en firmware.
  - Selector de filtro por tipo de infracción.
- **Lista Negra de Bloqueos:** Histórico y bloqueos manuales activos con tiempo de expiración.
- **Auditoría Anti-Abuso:** Registro detallado de disparos automáticos del limitador de tasa de comandos.

## 10. Pestaña 9 · Guía de Comandos

- **Catálogo Interactivo Clasificado:**
  - Agrupación temática: *🌦️ Meteorología, Marítimo y Naturaleza*, *📻 Red Meshtastic y Repetidores*, *🤖 Asistente de IA y Comunidad*, *⚙️ Sistema y Telemetría*.
  - **Buscador en Tiempo Real:** Filtra al instante por nombre de comando, alias, descripción o ejemplos.
  - **Badges de Ámbito:** Distinción visual clara entre comandos públicos (`📢 Canal y Privado`) y comandos restringidos (`💬 Solo Privado (DM)`).
  - **Prueba Rápida & Copia al Portapapeles:** Al hacer clic en un comando o ejemplo, se inserta automáticamente en el campo de texto del chat o se copia al portapapeles.

---

## 11. Navegación y Diseño Adaptativo

- **Barra Lateral Izquierda:**
  - **Pantallas > 900px:** Barra fija de `120px` de ancho con icono y texto en salto de línea natural (`overflow-wrap: break-word`).
  - **Pantallas ≤ 900px:** Modo compacto automático de `58px` con solo iconos visibles y badges flotantes.



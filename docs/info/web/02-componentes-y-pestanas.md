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
- **Telemetría de Batería y Sensores INA:** Nivel de carga (`⚡ 100%`) y voltaje (`4.18V`), o mediciones externas de potencia con sensor INA (`🔌 3.7/4.1/3.5`) cuando el router está alimentado por USB o monitorizado externamente.
- **Carga de Canal y Transmisión (`Carga (Ch/Tx)`):** Ocupación instantánea del canal (`chutil %`) y tiempo de emisión al aire (`tx %`) reportados por el repetidor.
- **Actividad de Telemetría y Traces:** Conteo ligero acumulado de telemetrías recibidas (`📊 X telems.`) y traceroutes detectados (`📍 Y traces`).
- **Avisos de Red:** Fila regular situada bajo *Última señal:* que indica `0 avisos` (en color atenuado) o `⚠️ X avisos` (en rojo con tooltip explicativo de la infracción) si el router está registrado en `auto_reported_nodes`.
- **Acciones Rápidas (Alineadas al footer con `.card-actions`):**
  - Botón **`🔋 Batería`**: Solicita por radio LoRa la telemetría de batería y voltaje actualizada al router.
  - Botón **`🔌 PWR`**: Si el router cuenta con sensor INA, solicita de forma directa la telemetría de potencia/batería externa.
  - Botón **`📍 Trace`**: Encola un traceroute hacia el router con protección anti-doble clic y estado temporal de espera (`⏳ Trace...`).

---

## 4. Pestaña 3 · Vigilancia (Favoritos y Vigilados)

Sección dedicada a la agrupación, seguimiento estrecho y diagnóstico rápido de nodos seleccionados por el operador de la estación:
- **Subpestañas de Navegación:**
  - **`⭐ Favoritos`:** Nodos marcados como favoritos (`is_favorite = 1`). Se sincronizan automáticamente desde la estrella `★` de la tabla de nodos sin necesidad de añadirlos manualmente ni poder borrarlos salvo quitando el favorito.
  - **`👁️ Vigilados`:** Nodos en seguimiento activo (`is_watched = 1`) marcados explícitamente mediante el botón `👁️` al inicio de la tabla de nodos o desde la propia tarjeta.
- **Formato de Tarjetas Idéntico a Routers:**
  - Estado `ONLINE` / `OFFLINE` y enlace de ruta / calidad SNR.
  - Telemetría de batería y sensores INA (`🔌 PWR`).
  - Métricas de saturación instantánea `Carga (Ch/Tx)`.
  - Actividad recogida (`📊 telemetrías` y `📍 traces detectados`).
  - Fila de avisos de red (`0 avisos` o `⚠️ X avisos`).
- **Acciones Directas en Tarjeta (Alineadas al footer):**
  - Fila 1: `🔋 Batería` y `🔌 PWR` (o `🔋 Batería` y `📍 Trace` si no tiene INA).
  - Fila 2: `📍 Trace` y botón de gestión rápida: **`★ Quitar`** en subpestaña Favoritos y **`👁️ Quitar`** en subpestaña Vigilados.

---

## 5. Pestaña 4 · Nodos de la Red

- **Buscador en Vivo y Filtros de Cabecera:**
  - **Texto:** Búsqueda instantánea por nombre, alias o ID hexadecimal.
  - **Rol:** Selector de roles completo (`CLIENT`, `CLIENT_BASE`, `ROUTER`, `REPEATER`, `ROUTER_CLIENT`, `TRACKER`, `TAK_TRACKER`, `SENSOR`, `CLIENT_MUTE`, `CLIENT_HIDDEN`, `LOST_FOUND`).
  - **Preservación de Batería en Vivo:** Las actualizaciones reactivas de nodo (`node_updated`) preservan la última telemetría de batería y voltaje conocida, evitando que paquetes sin métricas borren temporalmente el estado en la tabla.
  - **Soporte de Sensores de Potencia INA (INA219/INA3221):** Si el nodo cuenta con mediciones de sensor INA, en lugar de mostrar `⚡ 100%` por estar conectado a USB, se muestra el icono `🔌` junto con los canales de voltaje disponibles (ej. `🔌 3.7/4.1/3.5`).
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
  - `Con Batería 🔋`: Muestra exclusivamente los nodos con telemetría de batería/voltaje o medición INA reportada.
  - `Con Traceroutes 📍`: Filtra de inmediato los nodos con emisión de traceroutes (`traces_detected > 0`).
  - `Solo RF`: Excluye tráfico que llega por pasarelas MQTT.
  - `Favoritos ⭐`: Nodos destacados persistidos en SQLite.
  - `Vigilados 👁️`: Nodos marcados activamente para seguimiento en la pestaña Vigilancia.
- **Paginación Ágil:** Selector de 50, 100, 250 por página o "Ver todos", manteniendo el censo completo en memoria.
- **Ordenación Multidimensional Inteligente:** Posibilidad de ordenar por favoritos (`⭐`), vigilados (`👁️`), rol, nombre, alias, saltos, batería, carga (`Carga (Ch/Tx)`), SNR, Traceroutes detectados, última señal o primera vez visto.
- **Detalle de Columnas:**
  - **Favoritos (`⭐`) y Vigilados (`👁️`):** Columnas fijas al inicio de la tabla (35px) con botones interactivos toggle para marcar/desmarcar con un solo clic.
  - **Carga (Ch/Tx):** Ocupación instantánea del canal en porcentaje (`chutil %`) y tiempo empleado en el aire transmitiendo (`tx %`).
  - **Traces:** Contador de paquetes de traceroute emitidos por ese nodo (`📍 X`).
  - **Primera Vez:** Fecha en que el nodo fue descubierto por primera vez (`DD/MM/YYYY`).
  - **Última Señal:** Formateo dinámico (`HH:MM:SS` para hoy / `DD/MM HH:MM` para días previos).
  - **Acciones (Iconos compactos):**
    - Botón **`🔋`**: Solicita por radio LoRa la telemetría de batería y voltaje del nodo bajo demanda.
    - Botón **`🔌`**: Presente en nodos con sensor INA para solicitar actualización de potencia externa por LoRa.
    - Botón **`📍`**: Lanza y encola un traceroute hacia el nodo.
    - Botón **`ℹ️`**: Solicita NodeInfo por radio LoRa bajo demanda.

---

## 6. Pestaña 5 · Traceroutes

- **Visualizador de Saltos:** Representación gráfica de la ruta de ida (`Bot ➔ RPT1 (8.5dB) ➔ Destino`).
- **Control de Trazas Fallidas:** Muestra claramente el aviso `⚠️ Sin respuesta del nodo destino (Timeout / Sin cobertura)` en caso de expiración.
- **Formulario Manual:** Permite encolar un traceroute a cualquier ID o nombre corto de la red.

---

## 7. Pestaña 6 · Encuestas Comunitarias

- **Formulario de Creación:**
  - Pregunta y hasta 5 opciones dinámicas con botón `+ Añadir Opción`.
  - Duración configurable: por días (1 a 365 días) o fechas exactas de inicio y fin (`datetime-local`).
  - Selección de canales para anuncio inicial en la malla LoRa.
- **Histórico y Encuestas Vigentes:**
  - Filtro por estado: `Todas`, `🟢 Activas` y `⚪ Cerradas`.
  - Tarjetas con badge de estado (`🟢 Vigente hasta DD/MM HH:MM`), autor (`Nodo` o `Web / Administrador`), barras de porcentaje y conteo exacto de votos.
  - **Botonera por Encuesta:**
    - **`📢 Recordatorio`**: Abre modal para difundir de inmediato o programar periódicamente (cada 6h, 12h, diario, semanal) un recordatorio en uno o varios canales con el comando exacto de voto (`/encuesta votar <id> <opción>`).
    - **`🔒 Cerrar`**: Cierre anticipado de la encuesta para impedir más votos.
    - **`🗑️ Borrar`**: Eliminación permanente de la encuesta y sus votos asociados.
- **Chuleta de Comandos LoRa RF:** Resumen interactivo para memorizar los comandos de consulta (`/encuesta`, `/encuesta ver <id>`, `/encuesta votar <id> <opción>`, `/encuesta crear`, `/encuesta cerrar <id>`).

---

## 8. Pestaña 7 · Meteorología, Mar y Astronomía

- **Widgets Visuales Superiores:**
  - 🌊 **Mareas:** Pleamares y bajamares del día con hora, nivel en metros, coeficiente y fuente oficial (IHM / Estación).
  - 🌙 **Ciclo Lunar (100% Offline):** Nombre de la fase lunar, porcentaje de iluminación, tendencia (creciente/menguante) y fechas de próxima luna llena y luna nueva.
  - ☀️ **Sol y Luz Diurna (NOAA):** Hora exacta de orto (amanecer), ocaso (atardecer) y duración efectiva del día solar.
  - 🚨 **Vigilancia Maremoto:** Tiempo transcurrido (años, meses y días) desde el maremoto de Cádiz y Chipiona de 1755 y estado de alerta sísmica marítima.
- **Predicción en Próximas Horas (24 Horas):** Carrusel horizontal con intervalos horarios, iconos de estado del cielo (`☀️`, `⛅`, `🌧️`, `⛈️`), temperatura (°C), probabilidad de lluvia (%) y viento.
- **Tablas Multi-Ubicación de Días Futuros:** Tarjetas dedicadas por cada municipio registrado en la base de datos (Cádiz, Sevilla, Huelva...), con tabla comparativa de 7 días (Día, Fecha, Cielo, Temp. Mín/Máx, Lluvia %, Viento) y texto oficial descriptivo de la AEMET.
- **Avisos y Alertas AEMET Vigentes:** Alertas meteorológicas oficiales activas con nivel de severidad y descripción.

---

## 9. Pestaña 8 · Mensajes Programados

- **Gestión de Automatizaciones:** Programación de difusiones periódicas o diferidas (boletines, recordatorios de encuestas).
- **Control de Estado:** Activación/desactivación instantánea, edición y eliminación.

---

## 10. Pestaña 9 · Seguridad & Vigilancia de Malla

- **Nodos Auto-reportados por Mala Praxis:** Tabla en tiempo real con incidencias detectadas por `MeshWatcher`:
  - Infracción con badge e icono (`🔀 Saltos Excesivos ≥6`, `⚡ Telemetría Rápida <30m`, `📍 GPS Rápido <30m`, `👥 NodeInfo Rápido <30m`, `🌡️ Clima Rápido <30m`, `📍 Exceso Traceroutes`, `🛑 Spam Comandos`).
  - Contador de reincidencias y fecha relativa de última detección.
  - **Filtro Persistente por Infracción:** Selector desplegable por motivo de reporte que mantiene el filtrado tanto en peticiones activas como en snapshots globales en segundo plano, evitando que la lista se mezcle o resetee.
  - **Ordenación Reactiva Estable:** Ordenable por Infracción, Nodo, Veces y Última Detección sin perder el orden ni el foco durante las actualizaciones periódicas.
  - Botón **`🚫 Ignorar en Bot` / `✅ Atender`**: Descarta todo paquete del nodo en memoria sin procesar ni responder.
  - Botón **`🔒 Bloquear Radio` / `🔓 Desbloquear`**: Marca para exclusión en firmware.
- **Lista Negra de Bloqueos:** Histórico y bloqueos manuales activos con tiempo de expiración.
- **Auditoría Anti-Abuso:** Registro detallado de disparos automáticos del limitador de tasa de comandos.

---

## 11. Pestaña 10 · Auditoría y Estadísticas de Comandos

- **Filtros de Período:** Selección instantánea entre **`Última hora`** (1h), **`Últimas 24h`** (por defecto), **`Últimos 7 días`** (168h) e **`Histórico Total`**.
- **Tarjetas de Resumen:** Total de comandos, nodos únicos, comando más solicitado y usuario más activo.
- **Ranking Top 20 de Nodos:** Lista de los 20 usuarios con mayor volumen de peticiones en el período, avisos de alto uso y fecha completa de última interacción.
- **Registro Cronológico Paginado:** Historial de comandos cargado en bloques de 100 con controles `◀ Anterior` / `Siguiente ▶` y buscador de texto en tiempo real.

---

## 12. Pestaña 11 · Guía de Comandos

- **Catálogo Interactivo Clasificado:**
  - Agrupación temática: *🌦️ Meteorología, Marítimo y Naturaleza*, *📻 Red Meshtastic y Repetidores*, *🤖 Asistente de IA y Comunidad*, *⚙️ Sistema y Telemetría*.
  - **Buscador en Tiempo Real:** Filtra al instante por nombre de comando, alias, descripción o ejemplos.
  - **Badges de Ámbito:** Distinción visual clara entre comandos públicos (`📢 Canal y Privado`) y comandos restringidos (`💬 Solo Privado (DM)`).
  - **Prueba Rápida & Copia al Portapapeles:** Al hacer clic en un comando o ejemplo, se inserta automáticamente en el campo de texto del chat o se copia al portapapeles.

---

## 13. Navegación y Diseño Adaptativo

- **Barra Lateral Izquierda:**
  - **Pantallas > 900px:** Barra fija de `120px` de ancho con icono y texto en salto de línea natural (`overflow-wrap: break-word`).
  - **Pantallas ≤ 900px:** Modo compacto automático de `58px` con solo iconos visibles y badges flotantes.

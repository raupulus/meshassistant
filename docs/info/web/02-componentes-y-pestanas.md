# 02 · Componentes y Pestañas del Dashboard

La aplicación web está estructurada como una SPA (Single Page Application) con las siguientes secciones:

---

## 1. Barra de Estado Superior (Header)

- **Indicador UART:** LED verde cuando el bot tiene el puerto serie (`/dev/serial0`) conectado; rojo si la radio está desconectada.
- **Indicador WebSocket:** LED verde cuando el navegador mantiene el socket activo con el Gateway.
- **Nodo Local:** Nombre corto y número de nodo de la estación base conectada por serie.
- **Utilización del Espectro LoRa:** Porcentaje de ocupación del canal (`Ch Util`) y tiempo de emisión de la radio (`Air Tx`).

---

## 2. Pestaña 1 · Live Chat (Mensajería en Tiempo Real)

- **Feed con Scroll Dinámico:** Muestra mensajes según entran por la malla en tiempo real con metadatos:
  - Badge de canal (Canal 0 público, Privado directo o MQTT).
  - Remitente (nombre largo + ID corto).
  - Métricas de recepción: SNR en dB, RSSI en dBm y saltos de radio.
- **Filtros Rápidos:** Permite alternar entre "Todos", "Canal 0" y "Directos".
- **Formulario de Composición:** Selector de canal/nodo de destino, contador de caracteres (máx 200) y botón de envío directo a la cola LoRa.

---

## 3. Pestaña 2 · Routers y Repetidores

- **Tarjetas de Estado:** Lista los repetidores configurados en `ROUTER_NODES` indicando:
  - Estado `ONLINE` (verde) / `OFFLINE` (rojo).
  - SNR medio de enlace.
  - Minutos transcurridos desde el último paquete recibido.
- **Acción Rápida:** Botón *"📍 Lanzar Traceroute"* para evaluar la ruta hacia el repetidor seleccionado.

---

## 4. Pestaña 3 · Nodos de la Red

- **Buscador en Vivo:** Filtra instantáneamente por ID hexadecimal, nombre o alias corto.
- **Filtros de Lista:** Alternar entre "Todos", "Solo RF" (sin MQTT) y "Favoritos ⭐".
- **Tabla de Detalles:** Nombre, Rol (`CLIENT`, `ROUTER`, `REPEATER`), SNR, Saltos y nivel de batería.
- **Marcador de Favoritos:** Botón de estrella para persistir favoritos en la base de datos SQLite.

---

## 5. Pestaña 4 · Traceroutes

- **Visualizador de Saltos:** Representación gráfica de la ruta de ida (`Bot ➔ RPT1 (8.5dB) ➔ Destino`).
- **Formulario Manual:** Permite encolar un traceroute a cualquier ID o nombre corto de la red.

---

## 6. Pestaña 5 · Encuestas & Clima

- **Encuestas Comunitarias:** Muestra encuestas activas, porcentaje de votos y botones para votar directamente desde la interfaz web.
- **Meteorología Oficial AEMET:** Visualización de la última predicción descargada para la provincia configurada.

# 18. Captura Selectiva de Tráfico LoRa (Packet Sniffer)

Este documento describe la arquitectura, reglas y funcionamiento de la **Captura Selectiva de Tráfico LoRa (Packet Sniffer)** en Meshassistant. Permite inspeccionar tramas de radio específicas en tiempo real, almacenando metadatos completos y volcados de payload íntegro (cifrado o descifrado) de manera dirigida sin saturar el almacenamiento de la Raspberry Pi con tráfico broadcast general.

---

## 1. Motivación y Casos de Uso

En una red de malla Meshtastic con decenas o cientos de nodos, el tráfico continuo de radio genera un volumen elevado de paquetes broadcast (anuncios periódicos de nodos, telemetrías y texto público). Aunque existen herramientas para capturar todo el tráfico de la red, para la operativa diaria y diagnóstico de incidencias se necesita **ir al grano de forma productiva**:

1. **Diagnóstico de Nodos Concretos:** Auditar el tráfico originado o destinado a un nodo o router particular (comportamiento de retransmisión, confirmaciones ACK, saltos efectivos).
2. **Supervisión de Tráfico Administrativo (Admin PKI):** Monitorizar tramas de administración remota basadas en claves públicas (intercambiadas en canal 0 como unicast directo).
3. **Inspección de Cargas Cifradas:** Almacenar el payload binario crudo (`BLOB`) y hexadecimal para su posterior análisis forense o validación de cifrado.
4. **Verificación de Enrutamiento:** Capturar `next_hop`, `relay_node`, `want_ack`, `hop_start`, `hop_limit` y número real de saltos recorridos.

---

## 2. Flujo de Captura y Arquitectura

El motor de captura está centralizado en [`Models/PacketSniffer.py`](file:///Users/fryntiz/git/meshassistant/Models/PacketSniffer.py) y se integra en la primera línea de recepción de paquetes de datos (`on_receive_data`) en [`Models/SerialInterface.py`](file:///Users/fryntiz/git/meshassistant/Models/SerialInterface.py):

```
                     ┌───────────────────────────────────────────────┐
                     │          Paquete UART Meshtastic              │
                     └───────────────────────┬───────────────────────┘
                                             │
                                             ▼
                          ┌─────────────────────────────────────┐
                          │   PacketSniffer.inspect_packet()    │
                          │   (Deduplicación por packet.id)     │
                          │   (Filtro en RAM en microsegundos)  │
                          └──────────────────┬──────────────────┘
                                             │
                       ┌─────────────────────┴─────────────────────┐
                       │ (Cumple reglas activas)                   │ (No coincide)
                       ▼                                           ▼
         ┌───────────────────────────┐                    [ Continuar flujo normal ]
         │  insert_captured_packet() │                    (MeshWatcher, Descarte,
         │  (SQLite: captured_packets)│                     Telemetría, etc.)
         └─────────────┬─────────────┘
                       │
                       ▼
         ┌───────────────────────────┐
         │  broadcast_event(IPC)     │ ──► [ Gateway WebSocket :8680 ] ──► [ Mini Dashboard Web ]
         │  ("packet_captured")      │                                       (Actualización en vivo)
         └───────────────────────────┘
```

> **Orden de Ejecución:** `PacketSniffer.inspect_packet()` se invoca **antes** de los descartes por lista negra o nodos ignorados (`is_node_discarded`). Esto asegura que si un nodo ha sido marcado como conflictivo o ignorado para el bot, su tráfico aún pueda ser capturado e inspeccionado por el operador.

---

## 3. Criterios de Captura y Validación de Reglas

Las reglas se gestionan desde la tabla `capture_rules` y son evaluadas en memoria con una caché invalidada automáticamente ante cualquier cambio:

| Criterio | Descripción | Restricciones / Reglas |
|---|---|---|
| **Destino (`to`)** | Nodo destinatario (`!xxxxxxxx` o `^all`). | Puede ser `NULL` solo si `from` está definido. |
| **Origen (`from`)** | Nodo emisor (`!xxxxxxxx`). | Puede ser `NULL` solo si `to` está definido. |
| **Canal (`channel_filter`)** | `'all'` \| `'admin_pki'` \| `'0'`, `'1'`, etc. | Permite aislar canales específicos o tráfico administrativo. |
| **Solo Cifrado (`only_encrypted`)** | Booleano (`1`/`0`). | Si está activo, ignora paquetes con texto plano o sin carga cifrada. |
| **Modo de Guardado (`save_payload_mode`)** | `'full_encrypted'` \| `'text_if_available'`. | Almacena BLOB/Hex completo o solo texto plano. |

### Regla Condicional Obligatoria: Admin Remota (PKI)
Si se selecciona el canal **Admin Remota (`admin_pki`)**:
1. Se identifica técnicamente como cualquier paquete que circule por el **canal 0** con un **destino unicast directo** (`to != ^all` y `to != 0xFFFFFFFF`).
2. El modo de guardado se fija de forma **inquebrantable a payload completo cifrado (`full_encrypted`)**, tanto en la base de datos como en la interfaz web, ya que las tramas administrativas PKI viajan cifradas con claves asimétricas de los nodos y no pueden descifrarse en texto plano por terceros.

---

## 4. Almacenamiento en Base de Datos

Cada paquete capturado se descompone celda por celda en la tabla `captured_packets`:

- **Identidades:** `from_num`, `from_id`, `from_name`, `to_num`, `to_id`, `to_name`.
- **Canal y Modo:** `channel`, `channel_name`, `is_encrypted`, `is_admin_pki`.
- **Topología y Radio:** `next_hop`, `relay_node`, `want_ack`, `hop_limit`, `hop_start`, `hops`, `rx_snr`, `rx_rssi`.
- **Carga Útil:** `payload_raw` (`BLOB`), `payload_hex` (`TEXT`), `payload_text` (`TEXT`), `payload_size` (`INTEGER`), `portnum` (`TEXT`).
- **Asociación:** `rule_id` de la regla que disparó la captura.

---

## 5. Interfaz de Usuario y Pasarela Web

1. **Pestaña "Cap." (Icono `📷`):**
   - Situada en el menú lateral bajo "Comandos".
   - Formulario colapsable para crear/editar criterios con autocompletado de nodos conocidos vía `datalist`.
   - Listado visual de reglas activas con botones para pausar (`⏸️`), reanudar (`▶️`) o eliminar (`🗑️`).
2. **Acceso Rápido desde Nodos y Routers:**
   - Botón **`📷`** en cada fila de la tabla de Nodos.
   - Botón **`📷 Cap.`** en cada tarjeta de Routers.
   - Ambos preconfiguran el destino en el formulario de captura y abren la pestaña de forma inmediata.
3. **Visor de Tráfico en Tiempo Real:**
   - Recepción reactiva por WebSocket con animación y alertas toast.
   - Filtros por búsqueda de texto y tipo de paquete (*Admin PKI*, *Cifrados*, *Plano*).
   - Modal de inspección completa con volcado hexadecimal estilo Wireshark (`Hex Dump`) y botón para copiar al portapapeles.
   - Botón para vaciar el historial capturado con diálogo de confirmación.

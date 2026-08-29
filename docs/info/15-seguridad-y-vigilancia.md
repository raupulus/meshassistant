# 15. Seguridad, Anti-Abuso y Vigilancia de Malla

Este documento describe la arquitectura, componentes y funcionamiento del **Sistema de Vigilancia de Malla** y el **Control Anti-Abuso** de Meshassistant. Su objetivo es proteger la red LoRa comunitaria frente a saturación, nodos mal configurados o comportamientos maliciosos, operando de forma ultra-eficiente en hardware limitado (Raspberry Pi Zero W / Zero 2 W).

---

## 1. Visión General y Objetivos

En redes Meshtastic comunitarias (especialmente con cientos de nodos en el espectro), la saturación de AirTime suele provenir de:
1. **Nodos con exceso de saltos (`hop_limit: 7`):** Propagan paquetes innecesariamente a cientos de kilómetros sobrecargando repetidores lejanos.
2. **Telemetrías hiperactivas (< 30 minutos):** Nodos emitiendo batería, GPS o mediciones ambientales en ciclos de pocos segundos o minutos.
3. **Spam o bucles de comandos:** Intentos de saturar el bot con ráfagas continuas de peticiones.

Meshassistant implementa un doble nivel de protección:
- **`MeshWatcher` (Vigilancia pasiva en RAM):** Detecta infracciones de tráfico en tiempo real y auto-reporta a los nodos infractores en base de datos.
- **`AntiAbuseManager` (Control de tasa de comandos):** Aplica límites de frecuencia y auto-bloqueos temporales ante ráfagas de comandos.
- **Lista Negra y Nodos Ignorados:** Permite descartar silenciosamente en la primera línea de código cualquier tráfico de un nodo infractor.

```
                  ┌───────────────────────────────────────────────┐
                  │          Paquete UART Meshtastic              │
                  └───────────────────────┬───────────────────────┘
                                          │
                                          ▼
                         ┌─────────────────────────────────┐
                         │  ¿Nodo en lista de ignorados?   │ ──(SÍ)──► [ DESCARTAR SILENCIOSAMENTE ]
                         │     (MeshWatcher.is_ignored)    │           (0 escrituras, 0 CPU, 0 radio)
                         └────────────────┬────────────────┘
                                          │ (NO)
                                          ▼
                      ┌───────────────────────────────────────┐
                      │    Inspección en RAM (MeshWatcher)    │
                      │  - ¿hopStart >= 6?                    │
                      │  - ¿Delta telemetría < 1800s (30m)?   │
                      └───────────────────┬───────────────────┘
                                          │
                        ┌─────────────────┴─────────────────┐
                        │ (Infracción detectada)            │ (Tráfico normal)
                        ▼                                   ▼
          ┌───────────────────────────┐         ┌───────────────────────────┐
          │  auto_reported_nodes (BD) │         │  Solo actualiza TS en RAM │
          │  (Incrementa event_count) │         │  (0 escrituras en disco)  │
          └───────────────────────────┘         └───────────────────────────┘
```

---

## 2. Sistema de Vigilancia (`MeshWatcher`)

El módulo [`Models/MeshWatcher.py`](file:///Users/fryntiz/git/meshassistant/Models/MeshWatcher.py) opera en memoria con coste computacional casi nulo (~250 KB de RAM para 1.700 nodos).

### 2.1. Infracciones Monitorizadas

| Infracción | Código | Umbral | Descripción |
|---|---|---|---|
| **Exceso de Saltos Iniciales** | `EXCESSIVE_HOPS` | `hopStart >= 6` o `hopLimit >= 6` | El paquete fue originado deliberadamente para inundar la red a 6 o 7 saltos. |
| **Telemetría de Batería Rápida** | `FAST_TELEMETRY` | `TELEMETRY_APP` < 30 min | Emisión repetida de métricas de batería/voltaje. |
| **Posición GPS Rápida** | `FAST_POSITION` | `POSITION_APP` < 30 min | Emisión de coordenadas en ciclos cortos. |
| **NodeInfo Rápido** | `FAST_NODEINFO` | `NODEINFO_APP` < 30 min | Difusión repetitiva de información de usuario/nodo. |
| **Sensores Ambientales Rápidos** | `FAST_ENVIRONMENTAL` | `ENVIRONMENTAL_MEASUREMENT_APP` < 30 min | Estación climática emitiendo en intervalos agresivos. |
| **Spam de Comandos** | `COMMAND_SPAM` | ≥ 10 peticiones / minuto | Ráfaga de comandos hacia el bot. |

### 2.2. Filtro Antirrebote y Exclusión del Nodo Local
- **Exclusión del Nodo Propio:** El nodo local conectado por UART (`Raupulus PicoBot 2` / ID local) emite telemetría constante por diseño hacia el host serie. Queda **estrictamente excluido** de cualquier regla de vigilancia o bloqueo.
- **Filtro Antirrebote (< 15 segundos):** Los paquetes repetidos o disparados en ráfagas casi simultáneas por UART (< 15s) se descartan como duplicados del mismo evento, evitando falsos positivos de "0s".
- **Medición de Intervalos Reales:** Cuando un nodo emite telemetría legítima en menos de 30 minutos, se calcula el tiempo transcurrido exacto y se presenta de forma limpia: `Telemetría recibida en 45s`, `Posición GPS recibida en 5m 20s`, `NodeInfo recibido en 12m`.

### 2.3. Agrupación por Motivo en Base de Datos

La tabla `auto_reported_nodes` utiliza la restricción `UNIQUE(node_id, reason_code)`:
- Un mismo nodo físico puede registrar **dos incidencias separadas** si comete dos infracciones distintas (por ejemplo, una por saltos excesivos y otra por telemetría rápida).
- Si el nodo reincide en la misma infracción, se incrementa `event_count`, se actualiza la fecha `last_detected_at` y se guarda el último intervalo o dato medido en `last_details` (JSON).

---

## 3. Control Anti-Abuso (`AntiAbuseManager`)

El módulo [`Models/AntiAbuse.py`](file:///Users/fryntiz/git/meshassistant/Models/AntiAbuse.py) gestiona una ventana deslizante de 60 segundos por nodo:

1. **Límite de velocidad:** Configurable vía `env.RATE_LIMIT_MAX_PER_MINUTE` (por defecto 10 comandos/minuto).
2. **Auto-bloqueo escalonado:**
   - **Primer exceso:** Bloqueo temporal de 15 minutos (`autoban_15m`).
   - **Reincidencias (≥ 2 bloqueos en 24h):** Bloqueo ampliado de 24 horas (`autoban_24h`).
3. **Auditoría:** Cada disparo se registra en la tabla `abuse_logs` y se emite un evento IPC en tiempo real a la interfaz web (`node_blocked`).

---

## 4. Acciones de Administración (Dashboard Web)

En la pestaña **🛡️ Seguridad** del Dashboard Web se dispone de control directo sobre los nodos infractores:

### A) `🚫 Ignorar en Bot` / `✅ Atender`
- Marca `is_ignored_bot = 1` en base de datos y añade el `node_id` al conjunto `_ignored_nodes` en memoria.
- **Efecto:** El bot descarta cualquier paquete entrante del nodo en la primera línea de ejecución:
  - No almacena sus datos ni telemetrías en SQLite.
  - No gasta CPU parseando sus payloads.
  - No responde a ninguno de sus comandos (silencio de radio para evitar tráfico LoRa).

### B) `🔒 Bloquear en Radio (Firmware)` / `🔓 Desbloquear`
- Registra `is_blocked_fw = 1` y permite enviar a la radio Meshtastic por serie la orden de exclusión a nivel de firmware.

### C) `🛡️ Bloqueo Manual Administrativo`
- Formulario para bloquear un nodo por ID o nombre con duración configurable (1 hora, 24 horas, 7 días o Permanente).

---

## 5. API y Eventos WebSocket

La pasarela WiFi (`Services/Gateway.py`) expone las siguientes acciones:

- **`get_auto_reported_nodes`**: `{ limit: 100, offset: 0, reason_code: "EXCESSIVE_HOPS" | null }` -> `{ auto_reported_nodes: [...], total: N }`
- **`set_node_bot_ignored`**: `{ node_id: "!xxxxxxxx", is_ignored: true | false }` -> `{ success: true }`
- **`set_node_fw_blocked`**: `{ node_id: "!xxxxxxxx", is_blocked: true | false }` -> `{ success: true }`
- **Eventos en tiempo real:**
  - `auto_report_event`: Emitido al detectar una nueva infracción de vigilancia.
  - `node_ignore_toggled`: Emitido al cambiar el estado de ignorado de un nodo.
  - `node_blocked`: Emitido ante disparos del sistema anti-abuso.

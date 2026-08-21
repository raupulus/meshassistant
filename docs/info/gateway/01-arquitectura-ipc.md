# 01 · Arquitectura e IPC de la Pasarela

## 1. Principio de Aislamiento y Prioridad de Radio

El principio fundamental del diseño de `meshassistant` es que **el bot de radio tiene máxima prioridad**:
- `main.py` es el **único proceso** que interactúa con el nodo Meshtastic por el puerto serie UART.
- Si el servidor WebSocket se congela, si la red WiFi local se satura, o si un cliente (Pico W / App) se desconecta abruptamente, **el bot de radio jamás se bloquea**.

```
                                ARQUITECTURA DEL SISTEMA
                                
   ┌─────────────────────────────────────────────────────────────────────────────┐
   │                         RASPBERRY PI ZERO 2 W                               │
   │                                                                             │
   │   ┌────────────────────────┐                  ┌─────────────────────────┐   │
   │   │  main.py (Daemon UART) │                  │  Gateway.py (Daemon)    │   │
   │   │  - Dueño único serie   │                  │  - Servidor WebSocket   │   │
   │   │  - Procesa radio LoRa  │                  │  - Puerto 8680          │   │
   │   │  - Despacha comandos   │                  │  - Ring Buffer en RAM   │   │
   │   └──────────┬─────────────┘                  └────────────┬────────────┘   │
   │              │ (Push en < 0.05ms)                          │                │
   │              ├──────────────────────┬──────────────────────┤                │
   │              ▼                      │                      ▼                │
   │       [ Unix Socket DGRAM ]         │             [ Clientes Conectados ]   │
   │      (/tmp/mesh_events.sock)        │                      │                │
   │      (Solo Memoria RAM)             ▼                      │ (WiFi :8680)   │
   │                           ┌──────────────────┐             │                │
   │                           │  SQLite (WAL)    │             │                │
   │                           │  (database.sql)  │             │                │
   │                           │  - Persistencia  │             │                │
   │                           │  - Cola acciones │             │                │
   │                           └──────────────────┘             │                │
   └────────────────────────────────────────────────────────────┼────────────────┘
                                                                │
                                            ┌───────────────────┴───────────────────┐
                                            ▼                                       ▼
                                ┌──────────────────────┐                ┌───────────────────────┐
                                │ Raspberry Pi Pico W  │                │ Apps Móvil / Web / PC │
                                │ (MicroPython / C++)  │                │ (Dashboard agnóstico) │
                                └──────────────────────┘                └───────────────────────┘
```

---

## 2. Canal de Tiempo Real: Unix Domain Socket DGRAM

La comunicación interna entre `main.py` y `Services/Gateway.py` se realiza a través de un **Unix Domain Socket tipo DGRAM** (`/tmp/meshassistant_events.sock`):

1. **Latencia Sub-milisegundo (< 0.05 ms):** La llamada `sock.sendto(..., socket.MSG_DONTWAIT)` deposita el datagrama en el buffer del kernel de Linux en memoria RAM sin bloquear el hilo de ejecución de Python.
2. **Descarte Silencioso (Fire and Forget):** Si el servidor `Gateway.py` está apagado o no escucha, la emisión falla de inmediato de forma no bloqueante (`try/except: pass`) sin afectar a la recepción serie.
3. **Cero Desgaste de Almacenamiento (SD):** Los mensajes de chat y eventos en vivo viajan puramente en memoria volátil; no se realizan escrituras en SQLite para el tráfico ordinario.

---

## 3. Manejo de Estado y Persistencia (SQLite en modo WAL)

- **Lecturas Concurrentes sin Bloqueos:** `Gateway.py` lee directamente de SQLite en modo WAL (`PRAGMA journal_mode=WAL; PRAGMA busy_timeout=10000;`) para generar snapshots de estado iniciales (lista de nodos, histórico de traces y repetidores).
- **Encolamiento Seguro de Acciones:** Cuando un cliente solicita una acción de radio (p. ej. forzar un traceroute), `Gateway.py` inserta la petición en la tabla `traces` con estado `pending`. `main.py` procesa la cola de forma ordenada respetando las pausas de emisión LoRa (`sleep(2.5)`).

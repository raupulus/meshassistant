# 02 · Contrato Formal de API / WebSocket

> **Versión de la Especificación:** `1.0.0`  
> **Estado:** Vigente / Inmutable (SemVer)  
> **Puerto por defecto:** `8680`  
> **Protocolo:** WebSocket sobre TCP (`ws://<host>:8680`)  
> **Codificación:** UTF-8 / JSON plano

Este documento define el **contrato formal y estricto** de comunicación entre el servidor `meshassistant-gateway` y cualquier cliente externo (Raspberry Pi Pico W, aplicaciones móviles, paneles web o sistemas domóticos). 

Cualquier cambio futuro debe preservar la compatibilidad hacia atrás o incrementar la versión mayor de la API. Este documento puede copiarse directamente en proyectos de clientes como especificación técnica garantizada.

---

## 1. Convenciones y Estructura Global

### 1.1. Eventos Push (Servidor ➔ Cliente)
Todos los eventos emitidos de forma reactiva por el servidor tienen la siguiente estructura estándar:

```json
{
  "event": "<nombre_evento>",
  "ts": "YYYY-MM-DDTHH:MM:SS",
  "data": { ... }
}
```

### 1.2. Peticiones de Acción (Cliente ➔ Servidor)
Todas las solicitudes emitidas por los clientes deben seguir el esquema:

```json
{
  "action": "<nombre_accion>",
  "req_id": "identificador_opcional_para_correlacion",
  "params": { ... }
}
```

### 1.3. Respuestas a Acciones (Servidor ➔ Cliente)
El servidor siempre responde a una acción con el siguiente formato unificado:

```json
{
  "type": "response",
  "action": "<nombre_accion>",
  "req_id": "identificador_opcional_para_correlacion",
  "success": true,
  "data": { ... },
  "error": null
}
```
Si `success` es `false`, `data` será `null` y `error` contendrá una cadena de texto describiendo el motivo del fallo.

---

## 2. Catálogo de Eventos de Salida (Push)

### 2.1. `welcome` (Mensaje de Bienvenida en Conexión)
Emitido inmediatamente tras aceptar el handshake WebSocket.
```json
{
  "event": "welcome",
  "ts": "2026-08-21T20:00:00",
  "data": {
    "version": "1.0",
    "server": "meshassistant-gateway",
    "local_node": {
      "my_node_id": "!63ca1feb",
      "my_num": 1674190827,
      "name": "Raupulus Bot",
      "short_name": "rauB",
      "region": "EU_868"
    },
    "system_status": {
      "uart_connected": true,
      "serial_port": "/dev/ttyUSB0"
    }
  }
}
```

### 2.2. `message_rx` (Mensaje de Texto Recibido)
Emitido en tiempo real cuando llega un mensaje por radio (canal o privado).
```json
{
  "event": "message_rx",
  "ts": "2026-08-21T20:01:15",
  "data": {
    "from": "!12345678",
    "from_name": "Raupulus",
    "from_short_name": "rau5",
    "to": "^all",
    "channel": 0,
    "text": "Hola a toda la malla",
    "snr": 8.25,
    "rssi": -68,
    "hops": 1,
    "is_direct": false,
    "via_mqtt": false
  }
}
```

### 2.3. `local_node_info` (Identidad del Nodo Local)
```json
{
  "event": "local_node_info",
  "ts": "2026-08-21T20:00:00",
  "data": {
    "my_node_id": "!63ca1feb",
    "my_num": 1674190827,
    "name": "Raupulus Bot",
    "short_name": "rauB",
    "hw_model": 79,
    "region": "EU_868"
  }
}
```

### 2.4. `node_updated` / `node_discovered` (Metadatos de Nodo)
```json
{
  "event": "node_updated",
  "ts": "2026-08-21T20:02:10",
  "data": {
    "id": "!12345678",
    "num": 305419896,
    "name": "Estación Sur",
    "short_name": "SUR1",
    "mac_addr": "ab:cd:ef:12",
    "hw_model": 79,
    "role": 1,
    "snr": 7.5,
    "rssi": -72,
    "hops": 1
  }
}
```

### 2.5. `device_telemetry` (Batería y Energía de Nodo)
```json
{
  "event": "device_telemetry",
  "ts": "2026-08-21T20:05:00",
  "data": {
    "id": "!12345678",
    "battery": 94,
    "voltage": 4.15,
    "channel_util": 3.8,
    "air_util_tx": 0.12,
    "uptime_seconds": 36000
  }
}
```

### 2.6. `channel_metrics` (Salud y Ocupación del Espectro LoRa)
```json
{
  "event": "channel_metrics",
  "ts": "2026-08-21T20:05:00",
  "data": {
    "channel_util": 4.25,
    "air_util_tx": 0.18
  }
}
```

### 2.7. `trace_completed` (Resultado de Traceroute)
```json
{
  "event": "trace_completed",
  "ts": "2026-08-21T20:06:30",
  "data": {
    "trace_id": 45,
    "to": "!12345678",
    "to_name": "Repetidor Sierra",
    "to_name_short": "RPT1",
    "success": true,
    "hops_forward": [
      { "id": "!11111111", "name": "RPT-Intermedio", "snr": 9.2, "rssi": -65 },
      { "id": "!12345678", "name": "Repetidor Sierra", "snr": 4.5, "rssi": -85 }
    ],
    "hops_backward": [
      { "id": "!11111111", "name": "RPT-Intermedio", "snr": 8.0, "rssi": -70 }
    ],
    "raw_text": "Route traced towards destination: ..."
  }
}
```

### 2.8. `router_status` (Estado de Repetidores Clave)
```json
{
  "event": "router_status",
  "ts": "2026-08-21T20:10:00",
  "data": {
    "routers": [
      {
        "id": "!12345678",
        "name": "RPT-Sierra",
        "status": "online",
        "snr": 8.5,
        "last_seen_sec": 45
      }
    ]
  }
}
```

### 2.9. `message_ack` (Confirmación de Entrega de Mensaje Directo)
```json
{
  "event": "message_ack",
  "ts": "2026-08-21T20:08:12",
  "data": {
    "dest": "!12345678",
    "status": "delivered",
    "error_reason": "NONE"
  }
}
```

### 2.10. `position_rx` (Telemetría de Posición GPS)
```json
{
  "event": "position_rx",
  "ts": "2026-08-21T20:12:00",
  "data": {
    "id": "!12345678",
    "lat": 36.5297,
    "lon": -6.2926,
    "alt": 25,
    "time": 1755800000
  }
}
```

### 2.11. `system_status` (Heartbeat Periódico del Bot)
```json
{
  "event": "system_status",
  "ts": "2026-08-21T20:15:00",
  "data": {
    "uart_connected": true,
    "serial_port": "/dev/ttyUSB0",
    "nodes_in_memory": 48
  }
}
```

### 2.12. `aemet_alert` (Aviso Meteorológico Oficial)
```json
{
  "event": "aemet_alert",
  "ts": "2026-08-21T20:20:00",
  "data": {
    "level": "amarillo",
    "province": "Cadiz",
    "message": "Aviso amarillo por viento de Levante costero."
  }
}
```

---

## 3. Catálogo de Acciones de Entrada (Cliente ➔ Servidor)

### 3.1. `get_snapshot` (Estado Completo de la Red)
- **Petición:**
```json
{
  "action": "get_snapshot",
  "req_id": "snap_01",
  "params": {
    "include": ["nodes", "routers", "recent_messages", "stats", "system_status", "local_node", "channel_metrics"]
  }
}
```
- **Respuesta:**
```json
{
  "type": "response",
  "action": "get_snapshot",
  "req_id": "snap_01",
  "success": true,
  "data": {
    "recent_messages": [ ... ],
    "system_status": { ... },
    "local_node": { ... },
    "nodes": { "total": 45, "rf": 40, "mqtt": 5, "active": 18 },
    "routers": [ ... ],
    "stats": { "cmd_total": 120, "pings_total": 85 }
  },
  "error": null
}
```

### 3.2. `request_trace` (Lanzar Traceroute)
- **Petición:**
```json
{
  "action": "request_trace",
  "req_id": "tr_01",
  "params": {
    "dest": "!12345678"
  }
}
```
- **Respuesta:**
```json
{
  "type": "response",
  "action": "request_trace",
  "req_id": "tr_01",
  "success": true,
  "data": {
    "trace_id": 46,
    "status": "queued"
  },
  "error": null
}
```

### 3.3. `send_message` (Enviar Mensaje a la Malla)
- **Petición:**
```json
{
  "action": "send_message",
  "req_id": "msg_01",
  "params": {
    "text": "Hola desde cliente WiFi",
    "dest": "^all",
    "channel": 0
  }
}
```
- **Respuesta:**
```json
{
  "type": "response",
  "action": "send_message",
  "req_id": "msg_01",
  "success": true,
  "data": {
    "queued": true,
    "dest": "^all",
    "channel": 0
  },
  "error": null
### 3.4. `request_telemetry` (Solicitar Batería y Métricas a un Nodo/Router)
- **Petición:**
```json
{
  "action": "request_telemetry",
  "req_id": "tel_01",
  "params": {
    "node_id": "!12345678"
  }
}
```
- **Respuesta:**
```json
{
  "type": "response",
  "action": "request_telemetry",
  "req_id": "tel_01",
  "success": true,
  "data": {
    "queued": true,
    "outbox_id": 89,
    "node_id": "!12345678"
  },
  "error": null
}
```

### 3.5. `get_polls` (Consultar Encuestas Comunitarias)
- **Petición:**
```json
{
  "action": "get_polls",
  "req_id": "pl_01"
}
```
- **Respuesta:**
```json
{
  "type": "response",
  "action": "get_polls",
  "req_id": "pl_01",
  "success": true,
  "data": {
    "polls": [
      {
        "id": 1,
        "owner_node_id": "!12345678",
        "question": "¿Cambio de frecuencia?",
        "options": ["Sí", "No"],
        "counts": [5, 2],
        "total_votes": 7,
        "status": "active"
      }
    ]
  },
  "error": null
}
```

### 3.5. `vote_poll` (Votar en Encuesta)
- **Petición:**
```json
{
  "action": "vote_poll",
  "req_id": "vt_01",
  "params": {
    "poll_id": 1,
    "option_index": 0,
    "node_id": "mi_nodo_o_cliente"
  }
}
```
- **Respuesta:**
```json
{
  "type": "response",
  "action": "vote_poll",
  "req_id": "vt_01",
  "success": true,
  "data": {
    "status": "new"
  },
  "error": null
}
```

### 3.6. `get_weather` / `get_tides` (Feeds Meteorológicos y Mareas)
- **Petición:**
```json
{
  "action": "get_weather",
  "req_id": "wt_01"
}
```
- **Respuesta:**
```json
{
  "type": "response",
  "action": "get_weather",
  "req_id": "wt_01",
  "success": true,
  "data": {
    "province": "Cadiz",
    "content": "Cielos despejados, máxima 24ºC...",
    "created_at": "2026-08-21T18:00:00"
  },
  "error": null
}
```

### 3.7. `set_node_favorite` (Marcar/Desmarcar Nodo Favorito)
- **Petición:**
```json
{
  "action": "set_node_favorite",
  "req_id": "fav_01",
  "params": {
    "node_id": "!12345678",
    "is_favorite": true
  }
}
```
- **Respuesta:**
```json
{
  "type": "response",
  "action": "set_node_favorite",
  "req_id": "fav_01",
  "success": true,
  "data": {
    "node_id": "!12345678",
    "is_favorite": true
  },
  "error": null
}
```

### 3.8. `request_node_info` (Solicitar Metadatos de un Nodo por Radio LoRa)
- **Petición:**
```json
{
  "action": "request_node_info",
  "req_id": "ni_01",
  "params": {
    "node_id": "!1309e02c"
  }
}
```
- **Respuesta:**
```json
{
  "type": "response",
  "action": "request_node_info",
  "req_id": "ni_01",
  "success": true,
  "data": {
    "node_id": "!1309e02c",
    "status": "queued",
    "outbox_id": 48
  },
  "error": null
}
```

### 3.9. `get_commands_audit` (Estadísticas y Auditoría de Comandos)
- **Petición:**
```json
{
  "action": "get_commands_audit",
  "req_id": "aud_01",
  "params": {
    "hours": 24,
    "limit": 100,
    "offset": 0
  }
}
```
- **Respuesta:**
```json
{
  "type": "response",
  "action": "get_commands_audit",
  "req_id": "aud_01",
  "success": true,
  "data": {
    "period_hours": 24,
    "summary": {
      "total": 35,
      "unique_nodes": 12,
      "top_command": "ping",
      "top_command_count": 18,
      "top_user": "Raupulus",
      "top_user_count": 9
    },
    "ranking": [
      {
        "node_id": "!1309e02c",
        "name": "Raupulus",
        "short_name": "Rau5",
        "count": 9,
        "last_command": "ping",
        "last_command_at": "2026-08-22T02:15:00"
      }
    ],
    "recent_logs": [ ... ]
  },
  "error": null
}
```

### 3.10. `get_auto_reported_nodes` (Consulta de Nodos Auto-reportados)
- **Petición:**
```json
{
  "action": "get_auto_reported_nodes",
  "req_id": "ar_01",
  "params": {
    "limit": 100,
    "offset": 0,
    "reason_code": "EXCESSIVE_HOPS"
  }
}
```
- **Respuesta:**
```json
{
  "type": "response",
  "action": "get_auto_reported_nodes",
  "req_id": "ar_01",
  "success": true,
  "data": {
    "auto_reported_nodes": [
      {
        "id": 1,
        "node_id": "!1234abcd",
        "short_name": "BAD1",
        "name": "Nodo Inundador",
        "reason_code": "EXCESSIVE_HOPS",
        "reason_desc": "Configurado con 7 saltos iniciales (máx recomendado 3-5)",
        "event_count": 5,
        "first_detected_at": "2026-08-29T09:00:00",
        "last_detected_at": "2026-08-29T10:30:00",
        "last_details": "{\"configured_hops\": 7}",
        "is_ignored_bot": 0,
        "is_blocked_fw": 0
      }
    ],
    "total": 1
  },
  "error": null
}
```

### 3.11. `set_node_bot_ignored` (Ignorar o Reactivar Nodo en Bot)
- **Petición:**
```json
{
  "action": "set_node_bot_ignored",
  "req_id": "ign_01",
  "params": {
    "node_id": "!1234abcd",
    "is_ignored": true
  }
}
```
- **Respuesta:**
```json
{
  "type": "response",
  "action": "set_node_bot_ignored",
  "req_id": "ign_01",
  "success": true,
  "data": {
    "node_id": "!1234abcd",
    "is_ignored": true,
    "success": true
  },
  "error": null
}
```

### 3.12. `set_node_fw_blocked` (Bloquear o Desbloquear en Radio)
- **Petición:**
```json
{
  "action": "set_node_fw_blocked",
  "req_id": "fwb_01",
  "params": {
    "node_id": "!1234abcd",
    "is_blocked": true
  }
}
```
- **Respuesta:**
```json
{
  "type": "response",
  "action": "set_node_fw_blocked",
  "req_id": "fwb_01",
  "success": true,
  "data": {
    "node_id": "!1234abcd",
    "is_blocked": true,
    "success": true
  },
  "error": null
}
```


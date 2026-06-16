# 14 · Roadmap y funcionalidades pendientes

Estado de las piezas a medio implementar. Leyenda: ✅ funcional · 🟡 parcial/placeholder
· ⛔ no implementado.

## Comandos placeholder

| Comando | Estado | Comportamiento actual | Pendiente |
|---|---|---|---|
| `/weather` | 🟡 | Responde `Tiempo real: ???; Predicción: ???` | Integrar fuente real (AEMET predicción u otra) para Cádiz. |
| `/uptime` | 🟡 | Responde `Uptime: N/D` | Calcular uptime del bot y/o del nodo. |
| `/ia` | 🟡 | Responde `IA: funcionalidad en desarrollo` | Integrar micro-IA con respuestas breves. |

## Modelos de datos listos, lógica pendiente

| Funcionalidad | Estado | Detalle |
|---|---|---|
| Agenda de avisos (`agenda`) | 🟡 | Tabla y métodos `get_agenda`/`add_agenda` listos. Falta el **envío programado** desde `main.loop()` cuando llega `moment`. |
| Cola de publicaciones (`queue`) | 🟡 | Tabla creada. `Database.get_next_in_queue()` es un **TODO** (estrategia por definir: `send_at`/`period`). |
| Canal público resumido 3×/día | ⛔ | Idea de README; sin implementar. |
| Bloqueo de nodos abusivos | ⛔ | `commands_sent` ya registra todo; falta la política de límites + advertencia + bloqueo. |

## Modelo `Node`

| Método | Estado | Pendiente |
|---|---|---|
| `update_positions()` | ⛔ | Persistir posición/última señal (`lastHeard`, GPS). |
| `update_metrics()` | ⛔ | Métricas de dispositivo: batería, voltaje, utilización de canal, airUtilTx, uptime. |

## Directorios reservados

- `Crons/` y `Services/` están **vacíos**, reservados para reorganizar tareas y
  servicios en el futuro. Hoy toda la lógica de cron vive en `cron_tasks.py`.

## Ideas adicionales (del README original)

- Canal privado para gestionar IoT, avisos de eventos y *watchdogs*.
- Resúmenes automáticos de alertas (agua, incendio, tormenta) en horario
  mañana/tarde/noche.

## Deuda técnica menor

- Unificar los `print` heredados de depuración bajo `functions.log_p`.
- Añadir una suite de tests (hoy solo existe `test.py` como ejemplo de recepción).

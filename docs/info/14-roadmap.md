# 14 · Roadmap y funcionalidades pendientes

Estado de las piezas a medio implementar. Leyenda: ✅ funcional · 🟡 parcial/placeholder
· ⛔ no implementado.

## Mejoras planificadas

Mejoras solicitadas, pendientes de implementar. Leyenda de prioridad orientativa.

| Mejora | Estado | Detalle |
|---|---|---|
| SNR en `/ping` | ⛔ | Añadir el SNR de recepción a la respuesta de `/ping`. El dato ya está disponible en `metadata['rx_snr']` (y en `node_from.snr`), poblado en `SerialInterface.on_receive_text`. Falta incluirlo en el texto de respuesta de [`Commands/ping.py`](../../Commands/ping.py), junto a los *hops* y la calidad ya mostrados. Contemplar el caso `via_mqtt` (sin SNR RF) y cuando el valor sea `None`. |
| Nodo base configurable (restar salto) | ⛔ | El despliegue habitual en Meshtastic usa un nodo **exterior en azotea** y otro **interior** (donde corre el bot). Los `/ping` que entran reenviados por el nodo principal de azotea llegan con **un salto de más**. Añadir variable en `env.py` (p. ej. `BASE_NODE_ID`, id del nodo pasarela de azotea) para **restar 1 hop** al conteo cuando el mensaje entra a través de ese nodo, de modo que el usuario vea los saltos reales de su nodo hasta la azotea. Documentar la variable en [`02-configuracion.md`](02-configuracion.md) y `env.example.py`. |
| Comando de estado de *routers* | ⛔ | Nuevo comando que informe de los **routers** de la malla y su estado (p. ej. visto/última señal/*hops*). La lista de routers a vigilar se define como **lista en `env.py`** (ids de nodo). Reutilizar la info de `node_dict`/BD para el estado. Registrar el comando en `data.py` y crear `Commands/<nombre>.py`; documentarlo en [`07-comandos.md`](07-comandos.md). |
| Previsión a varios días | ⛔ | Ampliar la previsión meteorológica a **varios días (3 aprox.)**. Existe ya `/prevision` (AEMET, BD + en vivo); concretar si esta mejora es evolución de ese comando o uno nuevo, y respetar el límite de mensajes de la malla (`MESH_MAX_LEN`/`MESH_MAX_PARTS`) troceando la salida. |

## Comandos placeholder

| Comando | Estado | Comportamiento actual | Pendiente |
|---|---|---|---|
| `/ia` | 🟡 | Responde `IA: funcionalidad en desarrollo` | Integrar micro-IA con respuestas breves. |

> `/weather` (y su alias `/tiempo`) ya es ✅ funcional: lee la última predicción
> AEMET de la BD (`aemet_weather`) y trocea la respuesta a `MESH_MAX_LEN`.
> `/uptime` ya es ✅ funcional: responde `Encendido desde hace …` con
> `functions.format_uptime()`.

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

## Bugs conocidos

- **🔴 `on_connection_lost` bloquea el hilo `publishing` (latencia de minutos).**
  [`SerialInterface.on_connection_lost`](../../Models/SerialInterface.py) ejecuta un
  bucle de reconexión bloqueante (`sleep` + `while not self.interface` + `connect()`)
  **sobre el mismo hilo `publishing` que Meshtastic usa para repartir por `pubsub`
  los mensajes recibidos** (`meshtastic.receive.text`). Al caerse el nodo, el handler
  entra en ese bucle (a veces sin salir: si `connect()` lanza excepción, `self.interface`
  sigue `None`), y crea una `SerialInterface` nueva en cada vuelta. Efectos observados
  en la Pi: el hilo `publishing` atascado en el bucle, cientos de hilos creados
  (`Thread-4xx`) y decenas de fds a la BD. Mientras dura, los mensajes entrantes no se
  entregan → **responde con minutos de retraso y solo a algunas cosas**; solo un
  reinicio del proceso/Pi lo limpia. Diagnóstico confirmado en vivo con `py-spy`.
  **Fix propuesto:** `on_connection_lost` solo debe marcar una bandera y retornar de
  inmediato (sin `sleep` ni bucle); la reconexión ordenada (con `pub.unsubscribe` de
  los handlers y cierre completo del interfaz viejo antes de crear el nuevo) debe
  hacerse desde `main.loop()`, que corre en su propio hilo. Añadir además
  `pub.unsubscribe` antes de re-suscribir en `connect()`.

## Deuda técnica menor

- Unificar los `print` heredados de depuración bajo `functions.log_p`.
- Añadir una suite de tests (hoy solo existe `test.py` como ejemplo de recepción).

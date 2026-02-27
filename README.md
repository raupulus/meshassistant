# meshassistant

Este proyecto trata de crear un asistente virtual para redes lorawan gestionando
información a modo conversación directa.

La idea es que puedas preguntarle por mensaje privado y que el asistente te
responda con esa información.

Las ideas de funcionalidades son:

- Un canal público independiente, con información relevante para todos los 
  usuarios resumiendo estos mensajes 3 veces al día (mañana/tarde/noche). 
  Por ejemplo si hay alertas de agua, incendio, tormenta
- Un canal privado para gestionar IOT, avisos de eventos, watchdogs etc.
- A través de mensaje directo pedir tiempo (dará tiempo real y previsión)
- Gestionar avisos programados (agendar que te avise un día/hora con un mensaje)
- Preguntas por mensaje directo usando micro-ia, una modelo de IA muy 
  pequeño con respuestas breves para preguntas comunes.
- Comando "/help"
- Comando "/about"
- Comando "/ping" (Responde con "pong" y toda la info como saltos snr...)
- Comando "/uptime" (Tiempo encendido)
- Comando "/chiste" (Responde con un chiste de la comunidad)
- Comando "/weather" (Tiempo en la provincia de Cádiz)
- Comando "/maremoto" (Días desde el último maremoto en Chipiona)

También puedes usar "/help comando" indicando un "comando" de los anteriores
para ver más información sobre ese comando.

El Hardware para comenzar es una Raspberry Pi Zero 2w como servidor y una
raspberry pi pico 2w como cliente mediante la red Meshtastic.

La rasbperry pi pico conecta a la red mediante lorawan y reenvía los mensajes
a la raspberry pi zero por UART, igualmente los recibe.


## TODO

- Crear base de datos sqlite y los datos de los ping que me hagan al nodo
- Crear tablas para mensajes o avisos que se publicarán y el canal/grupo al 
  que van destinados. Con idea de añadirlos a la base de datos desde otras 
  aplicaciones.
- Crear tabla para almacenar los comandos recibidos. Si alguien abusa de los 
  comandos, se puede bloquear el nodo enviando antes una advertencia.  

## Ejecución con cron (solo Linux)

Para tareas periódicas (subir/descargar chistes, encolar traceroutes y revisar AEMET) se proporciona el script `cron_tasks.py`. La idea es ejecutarlo cada minuto desde `cron` en Linux. El proceso principal `main.py` mantiene el puerto serie abierto; por eso, el cron no realiza el traceroute directamente, sino que encola un registro en la propia tabla `traces` con `status='pending'` para que `main.py` lo ejecute de forma segura cuando corresponda.

Pasos recomendados en un despliegue Linux:

1. Crear y activar el entorno virtual (si no existe):
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

Puedes probar el cron como un comando manualmente en bucle para probar que funciona:

```bash
while true; do .venv/bin/python cron_tasks.py && sleep 60; done
```


2. Configurar `env.py` con los valores adecuados (por ejemplo `SERIAL_DEVICE_PATH`, URLs y API keys).

3. Añadir una entrada al `crontab` del sistema para ejecutar las tareas cada minuto:
   ```cron
   * * * * * cd /ruta/a/meshassistant && . venv/bin/activate && python3 cron_tasks.py >> cron.log 2>&1
   ```

Notas sobre traceroute (sin tablas auxiliares):
- `cron_tasks.py` encola el trace insertando en `traces` una fila con campos mínimos: `to=<node_id>`, `status='pending'`, `created_at=NOW()`.
- `main.py` en su bucle (`loop()`) busca el trace pendiente más antiguo y lo ejecuta con la conexión serial abierta. Al terminar, actualiza esa misma fila con `status='done'|'error'`, `from='local'`, `data_raw=<JSON>` y `updated_at=NOW()`.
- Límite global configurable: como máximo un trace cada `TRACES_INTERVAL` minutos, calculado mirando el `updated_at` del último trace procesado.
- Ventanas por nodo configurables:
  - Tras éxito (`status='done'`): repetir pasado `TRACES_RELOAD_INTERVAL` horas.
  - Tras error (`status='error'`): reintentar pasado `TRACES_RETRY_INTERVAL` horas.
  - Solo se consideran nodos con `via_mqtt=0` y con `hops <= TRACES_HOPS`.

Esto evita conflictos por el puerto serie ya que solo el proceso principal lo abre y lo mantiene.


## Variables de entorno para AEMET

Estas variables se configuran en `env.py` (puedes copiar desde `env.example.py`). La integración solo se activa si `AEMET_API_KEY` tiene un valor.

- `AEMET_API_KEY`: Clave de API de AEMET (OpenData). Si está vacía, no se consulta la API ni se publican avisos.
- `AEMET_CHANNELS`: Lista de canales Meshtastic donde publicar alertas. Ejemplo: `[6]`. Los nombres de canales se definen en `data.py`.
- `AEMET_PROVINCE`: Provincia para la que se vigilan alertas. Puede ser el nombre (p. ej. `Cádiz`) o el código que acepte el endpoint de AEMET utilizado.
- `AEMET_PERIOD`: Periodicidad mínima entre publicaciones por canal. Valores admitidos: `Hour`, `Three_hour`, `Six_hour`, `Twelve_hour`, `Day` (insensible a mayúsculas). Se traduce a 60, 180, 360, 720 y 1440 minutos respectivamente.
- `AEMET_HOUR_MIN`: Hora mínima (0-23) del día a partir de la cual se puede empezar a publicar alertas (respetando `AEMET_PERIOD`).
- `AEMET_HOUR_MAX`: Hora máxima (0-23) del día hasta la cual se puede empezar a publicar alertas (respetando `AEMET_PERIOD`).

Flujo de AEMET:
- `cron_tasks.py` (cada hora): si hay `AEMET_API_KEY`, consulta OpenData de AEMET (últimos avisos CAP para la provincia indicada si es posible), y guarda cualquier novedad en la tabla `aemet` (evitando duplicados).
- `main.py` (bucle): si hay API key y la hora actual está entre `AEMET_HOUR_MIN` y `AEMET_HOUR_MAX`, toma la próxima alerta no publicada y la envía a los canales definidos en `AEMET_CHANNELS`, respetando `AEMET_PERIOD` por canal. Tras publicar, marca la alerta como publicada en BD.

Notas:
- La tabla `aemet` actúa como histórico con un indicador `published` para evitar repeticiones.
- La periodicidad por canal se controla con la tabla `tasks_control` (marcas `aemet_publish_ch_<canal>`).


## Variables de entorno para Traces

Configúralas en `env.py` (consulta `env.example.py`):

- `ENABLE_TRACES` (bool): Si es `False`, el cron no encola traceroutes (deshabilitado por completo). Por defecto `False` en el ejemplo.
- `TRACES_HOPS` (int): Máximo de saltos permitidos para seleccionar nodos candidatos (se usa `hops <= TRACES_HOPS`). Por defecto `2`.
- `TRACES_INTERVAL` (int, minutos): Intervalo global mínimo entre traces (de distintos nodos). Por defecto `5`.
- `TRACES_RETRY_INTERVAL` (int, horas): Tiempo de espera para reintentar un trace tras un fallo (`status='error'`). Por defecto `24` (1 día).
- `TRACES_RELOAD_INTERVAL` (int, horas): Tiempo de espera para volver a trazar un nodo tras un éxito (`status='done'`). Por defecto `168` (7 días).

Cómo funciona con estas variables:
- El cron (`cron_tasks.send_trace`) respeta `ENABLE_TRACES` y el `TRACES_INTERVAL` global mirando el `updated_at` del último trace realizado.
- La selección de candidatos lee los parámetros y solo elige nodos que cumplen `via_mqtt=0` y `hops <= TRACES_HOPS` y cuyas ventanas por nodo hayan expirado (`TRACES_RETRY_INTERVAL` o `TRACES_RELOAD_INTERVAL`).
- El proceso principal no cambia: simplemente toma el `pending` más antiguo de la tabla `traces` y lo ejecuta.


## Activar el entorno virtual

### En Linux/macOS:
```shell script
source .venv/bin/activate
```

## Desactivar el entorno virtual

Cuando termines de trabajar, para desactivar el entorno virtual:

```shell script
deactivate
```


## Verificar que estás en el entorno virtual

Una vez activado, deberías ver el nombre del entorno virtual `(venv)` al principio de tu línea de comandos:

```shell script
(venv) usuario@maquina:~/proyecto$
```


## Crear el entorno virtual (si aún no existe)

Si aún no has creado el entorno virtual, puedes hacerlo con:

```shell script
python3 -m venv venv
```


O usando virtualenv directamente:

```shell script
virtualenv venv
```


## Instalar paquetes en el entorno virtual

Una vez activado el entorno virtual, puedes instalar paquetes con pip:

```shell script
pip install nombre_del_paquete
```

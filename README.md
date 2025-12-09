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

- Detectar hops y snr desde ping
- Crear base de datos sqlite y los datos de los ping que me hagan al nodo
- Crear tablas para mensajes o avisos que se publicarán y el canal/grupo al 
  que van destinados. Con idea de añadirlos a la base de datos desde otras 
  aplicaciones.


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

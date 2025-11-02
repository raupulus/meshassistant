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
- Comando "/chiste"

El Hardware para comenzar es una Raspberry Pi Zero 2w como servidor y una
raspberry pi pico 2w como cliente mediante la red Meshtastic.

La rasbperry pi pico conecta a la red mediante lorawan y reenvía los mensajes
a la raspberry pi zero por UART, igualmente los recibe.


## TODO

- Crear archivo de métodos auxiliares


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

from Commands.help import help_callback
from Commands.about import about_callback
from Commands.chiste import chiste_callback
from Commands.ia import ia_callback
from Commands.maremoto import maremoto_callback
from Commands.ping import ping_callback
from Commands.uptime import uptime_callback
from Commands.weahter import weather_callback

from datetime import date


commands_dict = {
    "help": {
        "callback": help_callback,
        "in_group": False,
        "usage": "/help o !help",
        "info": "Muestra este mensaje de ayuda"
    },
    "about": {
        "callback": about_callback,
        "in_group": False,
        "usage": "/about o !about",
        "info": "Muestra información sobre el proyecto"
    },
    "ping": {
        "callback": ping_callback,
        "in_group": True,
        "usage": "/ping o !ping",
        "info": "Devuelve información de como detecta el nodo que hace ping"
    },
    "weather": {
        "callback": weather_callback,
        "in_group": False,
        "usage": "/weather o !weather",
        "info": "Muestra información climatológica relevante"
    },
    "chiste": {
        "callback": chiste_callback,
        "in_group": True,
        "usage": "/chiste o !chiste",
        "info": "Proyecto de chistes de comunidad, más información en: https://jaja.raupulus.dev"
    },
    "ia": {
        "callback": ia_callback,
        "in_group": True,
        "usage": "/ia o !ia",
        "info": "Responde con una respuesta de una IA mínima"
    },
    "uptime": {
        "callback": uptime_callback,
        "in_group": False,
        "usage": "/uptime o !uptime",
        "info": "Responde el tiempo que ha estado conectado al nodo"
    },
    "maremoto": {
        "callback": maremoto_callback,
        "in_group": True,
        "usage": "/maremoto o !maremoto",
        "info": "Devuelve el tiempo que ha pasado desde el último maremoto en Chipiona"
    },
}

channels = {
    0: {
        "name": "General",
    },
    1: {
        "name": "Iberia",
    },
    2: {
        "name": "Andalucia"
    },
    3: {
        "name": "Cadiz"
    },
    4: {
        "name": "Chipiona"
    },
    5: {
        "name": "TEST"
    },
    6: {
        "name": "raupulus"
    },
    7: {
        "name": "Frikidevs"
    }
}

last_maremoto_date = date(1755, 11, 1)
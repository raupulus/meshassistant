from Commands.help import help_callback
from Commands.about import about_callback
from Commands.chiste import chiste_callback
from Commands.ia import ia_callback
from Commands.maremoto import maremoto_callback
from Commands.ping import ping_callback
from Commands.uptime import uptime_callback
from Commands.weather import weather_callback
from Commands.nodos import nodos_callback
from Commands.snr import snr_callback
from Commands.marea import marea_callback
from Commands.sol import sol_callback
from Commands.luna import luna_callback
from Commands.avisos import avisos_callback
from Commands.prevision import prevision_callback
from Commands.stats import stats_callback
from Commands.encuesta import encuesta_callback
from Commands.dado import dado_callback
from Commands.bola8 import bola8_callback

from datetime import date


commands_dict = {
    "help": {
        "callback": help_callback,
        "in_group": False,
        "usage": "/help o !help",
        "info": "Lista los comandos. Usa !help <comando> para el detalle"
    },
    "about": {
        "callback": about_callback,
        "in_group": False,
        "usage": "/about o !about",
        "info": "Información sobre el proyecto y su autor"
    },
    "ping": {
        "callback": ping_callback,
        "in_group": True,
        "usage": "/ping o !ping",
        "info": "Confirma recepción e indica saltos y calidad de señal"
    },
    "weather": {
        "callback": weather_callback,
        "in_group": True,
        "usage": "/weather o !weather",
        "info": "Predicción meteorológica de la zona (datos AEMET)"
    },
    "chiste": {
        "callback": chiste_callback,
        "in_group": True,
        "usage": "/chiste o !chiste",
        "info": "Cuenta un chiste. Añade el tuyo con !chiste add <texto>"
    },
    "ia": {
        "callback": ia_callback,
        "in_group": True,
        "usage": "/ia o !ia",
        "info": "Respuesta breve generada por una IA mínima"
    },
    "uptime": {
        "callback": uptime_callback,
        "in_group": False,
        "usage": "/uptime o !uptime",
        "info": "Tiempo que lleva encendido el bot"
    },
    "maremoto": {
        "callback": maremoto_callback,
        "in_group": True,
        "usage": "/maremoto o !maremoto",
        "info": "Tiempo desde el último maremoto en Chipiona (1755)"
    },
    "tiempo": {
        # Alias accesible de /weather (misma fuente AEMET, pero usable en canal).
        "callback": weather_callback,
        "in_group": True,
        "usage": "/tiempo o !tiempo",
        "info": "Tiempo actual de la zona (alias de /weather, datos AEMET)"
    },
    "prevision": {
        "callback": prevision_callback,
        "in_group": True,
        "usage": "/prevision o !prevision",
        "info": "Previsión de varios días del municipio (AEMET). BD + en vivo si hace falta"
    },
    "avisos": {
        "callback": avisos_callback,
        "in_group": True,
        "usage": "/avisos o !avisos",
        "info": "Últimos avisos meteorológicos de AEMET para la provincia"
    },
    "marea": {
        "callback": marea_callback,
        "in_group": True,
        "usage": "/marea o !marea",
        "info": "Próximas pleamares y bajamares (Chipiona). Offline con estimación de respaldo"
    },
    "sol": {
        "callback": sol_callback,
        "in_group": True,
        "usage": "/sol o !sol",
        "info": "Orto, ocaso y duración del día (cálculo offline)"
    },
    "luna": {
        "callback": luna_callback,
        "in_group": True,
        "usage": "/luna o !luna",
        "info": "Fase lunar e iluminación actual (cálculo offline)"
    },
    "nodos": {
        "callback": nodos_callback,
        "in_group": True,
        "usage": "/nodos o !nodos",
        "info": "Resumen de nodos conocidos: total, RF, MQTT y activos 24h"
    },
    "snr": {
        "callback": snr_callback,
        "in_group": True,
        "usage": "/snr o !snr",
        "info": "Señal del nodo pasarela (RAU0) y media de SNR de la malla RF"
    },
    "stats": {
        "callback": stats_callback,
        "in_group": True,
        "usage": "/stats o !stats",
        "info": "Estadísticas del bot: comandos, pings, nodos, encuestas y uptime"
    },
    "encuesta": {
        "callback": encuesta_callback,
        "in_group": True,
        "usage": "/encuesta [nueva|voto|ver|lista|cerrar|borrar|ayuda] …",
        "info": "Encuestas comunitarias. 1 activa por nodo; vota cualquiera. Ver /encuesta ayuda"
    },
    "dado": {
        "callback": dado_callback,
        "in_group": True,
        "usage": "/dado, /dado 20 o /dado 2d6",
        "info": "Tira dados. Por defecto 1d6; admite N caras o formato NdM"
    },
    "bola8": {
        "callback": bola8_callback,
        "in_group": True,
        "usage": "/bola8 o /8ball <pregunta>",
        "info": "La bola 8 mágica responde a tu pregunta de sí/no (diversión)"
    },
    "8ball": {
        # Alias de /bola8 (oculto en la lista de /help para no duplicar).
        "callback": bola8_callback,
        "in_group": True,
        "hidden": True,
        "usage": "/8ball o /bola8 <pregunta>",
        "info": "Alias de /bola8: la bola 8 mágica responde sí/no"
    },
}

channels = {
    0: {
        "name": "SFNarrow",
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
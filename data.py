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
from Commands.routers import routers_callback
from Commands.estado import estado_callback
from Commands.boletin import boletin_callback

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
    "test": {
        "callback": ping_callback,
        "in_group": True,
        "usage": "/test o !test",
        "info": "Confirma recepción e indica saltos y calidad de señal (alias de /ping)"
    },
    "weather": {
        "callback": weather_callback,
        "in_group": True,
        "usage": "/weather, /tiempo, /tiempo real o /tiempo <provincia>",
        "info": "Predicción del día actual. /tiempo real para datos de estación física"
    },
    "chiste": {
        "callback": chiste_callback,
        "in_group": True,
        "usage": "/chiste o /chiste add <texto>",
        "info": "Cuenta un chiste. Añade el tuyo con /chiste add <texto>"
    },
    "ia": {
        "callback": ia_callback,
        "in_group": True,
        "usage": "/ia <pregunta> o /ia reset",
        "info": "Respuesta breve generada por una IA mínima"
    },
    "uptime": {
        "callback": uptime_callback,
        "in_group": False,
        "usage": "/uptime",
        "info": "Tiempo que lleva encendido el bot"
    },
    "maremoto": {
        "callback": maremoto_callback,
        "in_group": True,
        "usage": "/maremoto",
        "info": "Tiempo transcurrido desde el maremoto de 1755 en Chipiona"
    },
    "tiempo": {
        "callback": weather_callback,
        "in_group": True,
        "usage": "/tiempo, /tiempo real o /tiempo <provincia>",
        "info": "Predicción del día actual. /tiempo real para datos de estación física"
    },
    "prevision": {
        "callback": prevision_callback,
        "in_group": True,
        "usage": "/prevision, /prevision mañana, /prevision <1-7> dias o /prevision <1-12> horas",
        "info": "Previsión meteorológica (3 días por defecto, mañana, N días o N horas)"
    },
    "avisos": {
        "callback": avisos_callback,
        "in_group": True,
        "usage": "/avisos",
        "info": "Avisos meteorológicos oficiales activos para la provincia con color y vigencia"
    },
    "marea": {
        "callback": marea_callback,
        "in_group": True,
        "usage": "/marea o /marea mar (o costa)",
        "info": "Pleamares y bajamares del día actual. /marea mar para boletín marítimo costero"
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
    "boletin": {
        "callback": boletin_callback,
        "in_group": True,
        "usage": "/boletin [matinal|vespertino]",
        "info": "Resumen diario: sol, tiempo, mareas y alertas. Uso: /boletin [matinal|vespertino]"
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
    "routers": {
        "callback": routers_callback,
        "in_group": True,
        "usage": "/routers o !routers",
        "info": "Estado de los routers/repetidores clave de la malla (actividad, SNR y saltos)"
    },
    "repetidores": {
        # Alias de /routers (oculto en la lista de /help para no duplicar).
        "callback": routers_callback,
        "in_group": True,
        "hidden": True,
        "usage": "/repetidores o /routers",
        "info": "Alias de /routers: estado de los routers y repetidores de la malla"
    },
    "estado": {
        "callback": estado_callback,
        "in_group": True,
        "usage": "/estado, /salud o /bot",
        "info": "Telemetría y salud del bot/RPi (solo DM o canal #bots)"
    },
    "salud": {
        "callback": estado_callback,
        "in_group": True,
        "hidden": True,
        "usage": "/salud o /estado",
        "info": "Alias de /estado: salud y telemetría de la Raspberry Pi"
    },
    "bot": {
        "callback": estado_callback,
        "in_group": True,
        "hidden": True,
        "usage": "/bot o /estado",
        "info": "Alias de /estado: telemetría del nodo y la Raspberry Pi"
    },
    "status": {
        "callback": estado_callback,
        "in_group": True,
        "hidden": True,
        "usage": "/status o /estado",
        "info": "Alias de /estado: salud y telemetría del nodo y la Raspberry Pi"
    },
    "telemetria": {
        "callback": estado_callback,
        "in_group": True,
        "hidden": True,
        "usage": "/telemetria o /estado",
        "info": "Alias de /estado: telemetría de hardware de la Raspberry Pi"
    },
    "boletín": {
        "callback": boletin_callback,
        "in_group": True,
        "hidden": True,
        "usage": "/boletín [matinal|vespertino]",
        "info": "Alias con tilde de /boletin"
    },
    "previsión": {
        "callback": prevision_callback,
        "in_group": True,
        "hidden": True,
        "usage": "/previsión [mañana|N días|N horas]",
        "info": "Alias con tilde de /prevision"
    },
    "telemetría": {
        "callback": estado_callback,
        "in_group": True,
        "hidden": True,
        "usage": "/telemetría",
        "info": "Alias con tilde de /telemetria"
    },
    "estación": {
        "callback": weather_callback,
        "in_group": True,
        "hidden": True,
        "usage": "/estación",
        "info": "Alias de /tiempo real para datos de estación meteorológica"
    },
    "estacion": {
        "callback": weather_callback,
        "in_group": True,
        "hidden": True,
        "usage": "/estacion",
        "info": "Alias de /tiempo real para datos de estación meteorológica"
    },
    "información": {
        "callback": about_callback,
        "in_group": False,
        "hidden": True,
        "usage": "/información",
        "info": "Alias con tilde de /about"
    },
    "informacion": {
        "callback": about_callback,
        "in_group": False,
        "hidden": True,
        "usage": "/informacion",
        "info": "Alias de /about"
    },
}

channels = {
    0: {
        "name": "SFNarrow",
    },
    1: {
        "name": "Andalucia",
    },
    2: {
        "name": "Cadiz",
    },
    3: {
        "name": "Chipiona",
    },
    4: {
        "name": "bots",
    },
    5: {
        "name": "sos",
    },
    6: {
        "name": "raupulus",
    },
    7: {
        "name": "Frikidevs",
    }
}

last_maremoto_date = date(1755, 11, 1)
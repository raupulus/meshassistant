
DEBUG = False

## Interfaz serial
SERIAL_DEVICE_PATH = '/dev/cu.usbserial-212110'

## Traces (Una vez a la semana cada nodo para nodos con máximo 2 saltos)
TRACES_ENABLE = False
TRACES_HOPS = 2 # Hops máximos permitidos para traces
TRACES_INTERVAL = 5 # Intervalo en minutos entre cada trace (de distintos nodos)
TRACES_RETRY_INTERVAL = 24 # Al fallar, espera estas horas antes de volver a intentarlo
TRACES_RELOAD_INTERVAL = 24 * 7 # Horas para actualizar de nuevo el traceroute hacia el nodo

## Api para Chistes, habilitado solo si tiene API key
CHISTES_API_KEY = ''
CHISTES_URL_UPLOAD = 'https://tuweb/chiste/add'
CHISTES_URL_DOWNLOAD = 'https://tuweb/chiste/get'

## Aemet, habilitado solo si tiene API key
AEMET_API_KEY = ''
AEMET_CHANNELS = [6]
AEMET_PROVINCE = 'Cádiz' # Poner igual que en AEMET
AEMET_PERIOD = 'Day' # Hour, Three_hour, Six_hour, Day
AEMET_HOUR_MIN = 8
AEMET_HOUR_MAX = 22
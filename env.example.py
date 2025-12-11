
DEBUG = False

## Interfaz serial
SERIAL_DEVICE_PATH = '/dev/cu.usbserial-212110'

## Traces (configurables por variables de entorno)
ENABLE_TRACES = False              # Si es False, el cron no encola traces
TRACES_HOPS = 2                    # Hops máximos permitidos para traces (<=)
TRACES_INTERVAL = 5                # Intervalo en minutos entre traces (global)
TRACES_RETRY_INTERVAL = 24         # Horas para reintentar tras un fallo
TRACES_RELOAD_INTERVAL = 24 * 7    # Horas para repetir tras un éxito (una semana por defecto)

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
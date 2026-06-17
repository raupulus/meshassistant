
DEBUG = False

## Interfaz serial
SERIAL_DEVICE_PATH = '/dev/cu.usbserial-212110'

## Traces (configurables por variables de entorno)
ENABLE_TRACES = False              # Si es False, el cron no encola traces
TRACES_HOPS = 2                    # Hops máximos permitidos para traces (<=)
TRACES_INTERVAL = 15                # Intervalo en minutos entre traces (global)
TRACES_RETRY_INTERVAL = 24         # Horas para reintentar tras un fallo
TRACES_RELOAD_INTERVAL = 24 * 7    # Horas para repetir tras un éxito (una semana por defecto)

## Api para Chistes, habilitado solo si tiene API key
CHISTES_API_ENABLED = False
CHISTES_API_KEY = ''
CHISTES_URL_UPLOAD = 'https://tuweb/chiste/add'
CHISTES_URL_DOWNLOAD = 'https://tuweb/chiste/get'

## Aemet, habilitado solo si tiene API key
AEMET_API_KEY = ''
AEMET_CHANNELS = [6]
AEMET_PROVINCE = 'Cadiz' # Provincia para la predicción/avisos (nombre o código INE 2 dígitos)
AEMET_CITY = 'Chipiona' # Municipio de fallback si no hay predicción provincial
AEMET_CITY_CODE = '11016' # Código INE (5 dígitos) del municipio; '' para autodetectar por nombre
AEMET_PERIOD = 'Day' # Cadencia de descarga del clima y publicación: Hour, Three_hour, Six_hour, Day
AEMET_HOUR_MIN = 8
AEMET_HOUR_MAX = 22
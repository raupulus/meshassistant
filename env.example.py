
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
CHISTES_EXCLUDE_GROUPS = [3]

## Aemet, habilitado solo si tiene API key
AEMET_API_KEY = ''
AEMET_CHANNELS = [6]
AEMET_PROVINCE = 'Cadiz' # Provincia para la predicción/avisos (nombre o código INE 2 dígitos)
AEMET_CITY = 'Chipiona' # Municipio de fallback si no hay predicción provincial
AEMET_CITY_CODE = '11016' # Código INE (5 dígitos) del municipio; '' para autodetectar por nombre
AEMET_PERIOD = 'Day' # Cadencia de descarga del clima y publicación: Hour, Three_hour, Six_hour, Day
AEMET_HOUR_MIN = 8
AEMET_HOUR_MAX = 22
AEMET_FORECAST_DAYS = 4 # Días de previsión municipal a descargar para /prevision (1-7)

## Comandos con fallback en vivo (/marea, /prevision): cada cuántos minutos como
## mucho se permite una petición a Internet desde el propio comando. Evita
## bloquear el hilo de recepción en cada uso; entre medias se sirve lo que haya
## en BD o, para mareas, la estimación offline.
ONDEMAND_REFRESH_MIN = 10

## Ubicación geográfica (para /sol, /luna y /marea). Por defecto: Chipiona
LOCATION_NAME = 'Chipiona'
LOCATION_LAT = 36.7361
LOCATION_LON = -6.4358
LOCATION_TZ = 'Europe/Madrid'  # zona horaria IANA (gestiona el horario de verano)

## Nodo pasarela propio (azotea) por el que el bot sale a la malla.
## /snr muestra la señal de este nodo (nombre corto) como referencia principal.
MESH_GATEWAY_SHORT_NAME = 'RAU0'

## Mareas (/marea)
## Fuente de descarga vía cron: si TIDES_API_KEY está vacío se usa Open-Meteo
## Marine (gratis, sin key). Si no hay Internet, el comando estima con la Luna.
TIDES_API_KEY = ''        # Opcional: clave de WorldTides (https://www.worldtides.info)
TIDES_PERIOD_MIN = 360    # Cadencia de descarga de mareas en minutos (6 h por defecto)
TIDES_DAYS = 2            # Días de predicción de marea a descargar
TIDES_HWI_MIN = 60        # Solo para la estimación offline: intervalo de establecimiento
                          # del puerto (lunitidal interval) en minutos. Aprox. Cádiz.
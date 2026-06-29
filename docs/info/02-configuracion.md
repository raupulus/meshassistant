# 02 · Configuración (`env.py`)

La configuración del proyecto vive en `env.py`, que se crea copiando
`env.example.py`. **`env.py` no se versiona** (está en `.gitignore`) porque puede
contener claves de API.

```bash
cp env.example.py env.py
# editar env.py
```

El código lee las variables con `getattr(env, 'NOMBRE', valor_por_defecto)`, de modo
que las variables ausentes no rompen la ejecución.

## Variables

### General

| Variable | Tipo | Defecto ejemplo | Descripción |
|---|---|---|---|
| `DEBUG` | bool | `False` | Activa el logging de `functions.log_p`. Con `False` no se imprime nada (salvo `print` heredados). |
| `SERIAL_DEVICE_PATH` | str | `/dev/cu.usbserial-212110` | Ruta del dispositivo serie del nodo. En la Pi suele ser `/dev/serial0`. |

### Traces

| Variable | Tipo | Defecto | Descripción |
|---|---|---|---|
| `ENABLE_TRACES` | bool | `False` | Si es `False`, el cron no encola traceroutes. |
| `TRACES_HOPS` | int | `2` | Máximo de saltos para elegir nodos (`hops <= TRACES_HOPS`). |
| `TRACES_INTERVAL` | int (min) | `5` | Intervalo global mínimo entre traces. |
| `TRACES_RETRY_INTERVAL` | int (h) | `24` | Espera para reintentar un trace tras `error`. |
| `TRACES_RELOAD_INTERVAL` | int (h) | `168` | Espera para volver a trazar un nodo tras `done`. |

### Chistes

| Variable | Tipo | Descripción |
|---|---|---|
| `CHISTES_API_ENABLED` | bool | Activa la sincronización con la API externa. |
| `CHISTES_API_KEY` | str | *Bearer token* para la API de chistes. |
| `CHISTES_URL_UPLOAD` | str | Endpoint POST para subir chistes. |
| `CHISTES_URL_DOWNLOAD` | str | Endpoint GET para descargar chistes. |

### AEMET

| Variable | Tipo | Descripción |
|---|---|---|
| `AEMET_API_KEY` | str | Clave de AEMET OpenData. **Si está vacía, AEMET no se usa.** |
| `AEMET_CHANNELS` | list[int] | Canales donde publicar alertas (p. ej. `[6]`). |
| `AEMET_PROVINCE` | str | Provincia o CCAA vigilada (p. ej. `Cádiz`, `Galicia`). |
| `AEMET_PERIOD` | str | Periodicidad mínima por canal: `Hour`, `Three_hour`, `Six_hour`, `Twelve_hour`, `Day`. |
| `AEMET_HOUR_MIN` | int (0-23) | Hora mínima a partir de la cual publicar. |
| `AEMET_HOUR_MAX` | int (0-23) | Hora máxima hasta la cual publicar. |

> `AEMET_PERIOD` se traduce a minutos en `Aemet.period_to_minutes`: 60, 180, 360,
> 720 y 1440 respectivamente. La ventana horaria admite cruzar medianoche (si
> `HOUR_MIN > HOUR_MAX`).

## Canales (`data.py`)

Los nombres de los canales Meshtastic se definen en `data.py` (`channels`), no en
`env.py`. `AEMET_CHANNELS` referencia los índices de ese mapa. Mapa actual:

```
0 SFNarrow · 1 Iberia · 2 Andalucia · 3 Cadiz · 4 Chipiona
5 TEST · 6 raupulus · 7 Frikidevs
```

## Buenas prácticas

- No comitear `env.py`. Si necesitas documentar una variable nueva, hazlo en
  `env.example.py` con un valor de ejemplo seguro (vacío para secretos).
- Al leer una variable nueva en el código, usa siempre `getattr(env, 'X', defecto)`.

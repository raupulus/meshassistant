# 12 · API HTTP (`Models/Api.py`)

Cliente HTTP genérico y minimalista, basado en `requests`, usado para la **API de
chistes**. (AEMET tiene su propio cliente en `Models/Aemet.py`, con la misma
filosofía pero cabecera `api_key`.)

## Características

- **Timeout fijo:** 5 s.
- **Reintentos:** 2 (configurable en el constructor).
- **Autenticación opcional:** Bearer token (`set_apikey`).
- Devuelve JSON parseado; si no hay contenido, `None`. Si se agotan los reintentos,
  relanza la última excepción.

## API

```python
api = Api(timeout=5.0, retries=2)
api.set_apikey("TOKEN")                 # añade Authorization: Bearer TOKEN
api.upload(url, data)                   # POST con cuerpo JSON
api.download(url, params)               # GET con query params
```

### Cabeceras

```http
Accept: application/json
Content-Type: application/json
Authorization: Bearer <api_key>   # solo si set_apikey()
```

### Métodos

| Método | Verbo | Notas |
|---|---|---|
| `upload(url, data)` | POST | Serializa `data` a JSON en el cuerpo. |
| `download(url, params)` | GET | Pasa `params` como query string. |
| `_request(method, url, data)` | — | Núcleo con reintentos para POST/PUT/etc. |

## Uso en el proyecto

- `cron_tasks.chiste_upload` → `api.upload(CHISTES_URL_UPLOAD, {nick,title,content})`.
- `cron_tasks.chiste_download` → `api.download(CHISTES_URL_DOWNLOAD, {limit, after_id})`.

## Diferencias con `Models/Aemet.py`

| | `Api` | `Aemet` |
|---|---|---|
| Auth | `Authorization: Bearer` | cabecera `api_key` |
| Uso | API de chistes | AEMET OpenData |
| Descarga | `GET` con `params` | flujo de 2 pasos (JSON `datos` → documento) |
| Timeout | 5 s | 5 s (20 s para el tar.gz de archivo) |

## Notas

- Cliente síncrono y de un solo uso por petición; no mantiene sesión (`requests`
  directo). Suficiente para el volumen del proyecto.
- Para endpoints nuevos, reutiliza `Api` si la auth es Bearer; si no, valora un
  cliente específico como `Aemet`.

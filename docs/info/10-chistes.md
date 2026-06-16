# 10 · Chistes

Sistema de chistes de comunidad: los usuarios añaden chistes por la malla
(`!chiste add ...`), se almacenan localmente y se **sincronizan con una API externa**
(proyecto <https://jaja.raupulus.dev>).

## Componentes

- **`Commands/chiste.py`** — comando `/chiste` (lectura, alta, ayuda).
- **`Models/Database.py`** — almacenamiento (`get_random_chiste`, `save_chiste`,
  `get_chistes_to_upload`, `mark_chistes_uploaded`, `get_last_downloaded_chiste_id`,
  `bulk_insert_api_chistes`).
- **`cron_tasks.py`** — `chiste_upload()` / `chiste_download()`.
- **`Models/Api.py`** — cliente HTTP (Bearer token).

## Comando `/chiste`

| Uso | Efecto |
|---|---|
| `/chiste` | Devuelve un chiste aleatorio **aprobado** (`need_approve=0`). |
| `/chiste add <texto>` | Guarda el chiste con `need_approve=1` y `need_upload=1`. |
| `/chiste help` (o `info`/`ayuda`) | Muestra el texto de ayuda. |

El alta toma el autor de `node_from.short_name`/`name`. Responde confirmando que
queda **pendiente de aprobación**.

## Modelo de datos (tabla `chistes`)

- `content` — texto.
- `need_approve` — 0/1: si requiere aprobación antes de mostrarse.
- `need_upload` — 0/1: si está pendiente de subir a la API.
- `chiste_id` — id en la API externa (UNIQUE; permite dedup en descargas).
- `"from"` — autor.

## Sincronización (cron)

### `chiste_upload()` — cooldown 5 min
- Lee `CHISTES_URL_UPLOAD` y `CHISTES_API_KEY`.
- Toma hasta 5 chistes con `need_upload=1` y los sube (`Api.upload`) con payload
  `{nick, title, content}`.
- Marca los subidos con `mark_chistes_uploaded`.

### `chiste_download()` — cooldown 10 min
- Lee `CHISTES_URL_DOWNLOAD`.
- Pide chistes nuevos con `after_id = get_last_downloaded_chiste_id()` (paginación
  incremental, `limit=25`).
- `bulk_insert_api_chistes` inserta con `INSERT OR IGNORE` (dedup por `chiste_id`),
  `need_approve=0` y `need_upload=0`. Devuelve `(insertados, ignorados)`.

## Aprobación

Los chistes añadidos desde la malla entran con `need_approve=1` y **no** se muestran
en `/chiste` hasta aprobarse. Los descargados de la API entran aprobados
(`need_approve=0`). El flujo de aprobación se gestiona en el lado de la API externa.

## Notas

- La API usa autenticación **Bearer** (`Api.set_apikey` → `Authorization: Bearer …`).
- `Api` tiene timeout 5 s y 2 reintentos. Ver [12-api-http.md](12-api-http.md).

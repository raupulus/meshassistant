# 11 · Cron (tareas periódicas)

`cron_tasks.py` agrupa las tareas que deben ejecutarse de forma periódica. Está
pensado para lanzarse **cada minuto desde `cron`**. Nunca abre el puerto serie.

## Punto de entrada — `run_all()`

```python
run_all():
    chiste_upload()     # cooldown 5 min
    chiste_download()   # cooldown 10 min
    send_trace()        # encola trace (si ENABLE_TRACES)
    check_aemet()       # cooldown 60 min
```

Cada tarea controla su propia frecuencia, por lo que ejecutar el script cada minuto
es seguro: la mayoría de pasadas no hacen nada (respetan el cooldown).

## Throttling — `tasks_control`

El control de frecuencia se basa en la tabla `tasks_control`:

- `_should_run(db, name, min_interval_minutes)` compara `now` con
  `get_task_last_run(name)`.
- Al terminar, la tarea llama `set_task_run(name)` para sellar la última ejecución.

Marcas usadas: `chiste_upload`, `chiste_download`, `aemet_fetch`,
`aemet_fix_legacy_done`, y `aemet_publish_ch_<canal>` (esta última la marca
`main.py` al publicar).

## Tareas

| Tarea | Cooldown | Qué hace | Detalle |
|---|---|---|---|
| `chiste_upload` | 5 min | Sube chistes `need_upload=1`. | [10-chistes.md](10-chistes.md) |
| `chiste_download` | 10 min | Descarga chistes nuevos. | [10-chistes.md](10-chistes.md) |
| `send_trace` | `TRACES_INTERVAL` | Encola un traceroute. | [08-traceroute.md](08-traceroute.md) |
| `check_aemet` | 60 min | Descarga y guarda alertas AEMET. | [09-aemet.md](09-aemet.md) |

## Instalación en crontab

```cron
* * * * * cd /ruta/a/meshassistant && . .venv/bin/activate && python3 cron_tasks.py >> cron.log 2>&1
```

Prueba manual en bucle (sin cron):

```bash
while true; do .venv/bin/python cron_tasks.py && sleep 60; done
```

## Reparto de responsabilidades cron vs. main

| Acción | Cron | main.py |
|---|---|---|
| Descargar AEMET | ✅ | |
| Publicar AEMET en la malla | | ✅ |
| Seleccionar/encolar trace | ✅ | |
| Ejecutar trace (serie) | | ✅ |
| Subir/descargar chistes | ✅ | |
| Responder comandos | | ✅ |

Regla: **todo lo que toca el serie ocurre en `main.py`**; el cron solo prepara datos
y encola trabajo. Ver [01-arquitectura.md](01-arquitectura.md).

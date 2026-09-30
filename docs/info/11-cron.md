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

El control de frecuencia se basa en la tabla `tasks_control` (`name`, `last_run_at`, `extra`):

- `_should_run(db, name, min_interval_minutes)` compara `now` con `get_task_last_run(name)`.
- Al terminar, la tarea llama `set_task_run(name, extra=...)` para sellar la última ejecución.
- **Regla de oro sobre nombres canónicos:** Está estrictamente prohibido generar claves dinámicas con fechas en `name` (ej. `maritime_attempt_YYYYMMDD_HH` o `aemet_key_warn_YYYYMMDD`) porque acumulan filas indefinidamente y ensucian el monitor. En su lugar, el nombre de la tarea es siempre canónico y fijo, almacenando el identificador de slot o fecha en la columna `extra`.

Marcas canónicas usadas:
- `send_trace`: Encolado de trazas periódicas a routers y clientes.
- `router_telemetry_request`: Petición diaria de telemetría a routers matinales.
- `aemet_fetch`: Descarga de avisos CAP de AEMET.
- `aemet_weather_fetch`: Predicción meteorológica diaria para `/weather`.
- `aemet_forecast_fetch`: Predicción municipal horaria y 7 días.
- `aemet_observation_fetch`: Descarga de estación meteorológica física.
- `maritime_aemet_success`: Último boletín costero exitoso (`extra=slot_id`).
- `maritime_aemet_attempt`: Último intento de boletín costero (`extra=slot_id`).
- `aemet_key_expiry_check`: Chequeo diario del token JWT de AEMET.
- `aemet_key_expiry_warn`: Último aviso emitido por radio ante caducidad (`extra=YYYY-MM-DD`).
- `tides_fetch`: Descarga de extremos de marea para `/marea`.
- `marea_ondemand`: Petición bajo demanda de mareas.
- `chiste_upload`, `chiste_download`: Sincronización de chistes.
- `encuestas_expire`: Expiración de encuestas.
- `aemet_publish_ch_<canal>`: Publicación de alertas por canal (registrado por `main.py`).

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

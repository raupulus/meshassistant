# scripts/

Tareas de mantenimiento que se ejecutan **fuera del bot** (bash, contra la base
de datos o el sistema). No forman parte del flujo normal de `main.py` ni del
cron; son utilidades puntuales para el operador.

> Recomendación general: ejecuta estos scripts con el bot detenido para evitar
> bloqueos de SQLite (la BD usa modo WAL).

---

## reset_traces.sh

Reinicia el ciclo de **traceroute** para todos los nodos **sin perder el
histórico** de traces ya realizados.

### ¿Cuándo usarlo?

Normalmente los traces se hacen una vez por semana por nodo
(`TRACES_RELOAD_INTERVAL` en `env.py`). Si cambias de preset para hacer pruebas
y quieres que se vuelva a tracear todo desde cero conservando lo anterior, este
script es la forma rápida de hacerlo.

### ¿Cómo funciona?

El planificador `get_next_node_to_trace()` (en `Models/Database.py`) decide qué
nodo tracear mirando **solo** los traces con `status IN ('done','error')`. Por
cada nodo toma el `MAX(updated_at)` de su último trace procesado y aplica las
ventanas de tiempo:

- último `done`  → re-tracea si pasaron ≥ `TRACES_RELOAD_INTERVAL` horas
- último `error` → reintenta si pasaron ≥ `TRACES_RETRY_INTERVAL` horas
- sin trace previo → elegible de inmediato

El script cambia el `status` de los traces actuales `done`/`error` a
**`archived`**. Como ese valor queda fuera del conjunto que mira el
planificador, cada nodo pasa a tratarse como "sin trace previo" y vuelve a ser
candidato ya. **Las filas no se borran**: `data_raw`, `hops`, `updated_at`,
etc. siguen ahí como histórico.

El cron sigue cogiendo **un nodo por ejecución** respetando el cooldown global
`TRACES_INTERVAL`, así que el re-trazado se reparte en el tiempo solo (no hay
avalancha).

### Uso

```bash
# Reset normal (crea un backup de la BD antes de tocar nada)
./scripts/reset_traces.sh

# Ver qué haría sin modificar nada
./scripts/reset_traces.sh --dry-run

# Sin crear backup
./scripts/reset_traces.sh --no-backup

# Apuntar a otra ruta de BD
./scripts/reset_traces.sh --db /ruta/a/database.sql

# Ayuda
./scripts/reset_traces.sh --help
```

La primera vez, dale permisos de ejecución:

```bash
chmod +x scripts/reset_traces.sh
```

### Salida de ejemplo

```
BD:                 /.../meshassistant/database.sql
Traces a archivar:  410  (status 'done'/'error')
Backup creado:      /.../meshassistant/database.sql.bak_20260621_101500
Hecho. Traces archivados ahora: 410. Pendientes done/error: 0.
Cada nodo volverá a tracearse en el próximo ciclo del cron.
```

### Reversión

Para volver al estado anterior tienes dos vías:

1. **Restaurar el backup** generado por el script (recomendado, conserva la
   distinción original `done`/`error`):

   ```bash
   cp database.sql.bak_AAAAMMDD_HHMMSS database.sql
   ```

2. **Revertir el status** (rápido, pero todos los archivados vuelven como
   `done`, perdiendo la marca de los que fueron `error`):

   ```bash
   sqlite3 database.sql "UPDATE traces SET status='done' WHERE status='archived';"
   ```

### Notas

- `get_last_trace_updated_at()` (cooldown global) usa `MAX(updated_at)` sin
  filtrar por status, así que el **primer** trace tras el reset puede esperar
  hasta `TRACES_INTERVAL` minutos. Es el comportamiento esperado.
- Ningún comando del bot muestra el histórico filtrando por `status='done'`;
  solo el planificador usa el `status`. Archivar no oculta nada al usuario.

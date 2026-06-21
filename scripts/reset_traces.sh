#!/usr/bin/env bash
#
# reset_traces.sh
# -----------------------------------------------------------------------------
# Reinicia el ciclo de traceroute para TODOS los nodos sin perder el histórico.
#
# Contexto:
#   El planificador (Models/Database.py -> get_next_node_to_trace) decide qué
#   nodo tracear mirando SOLO los traces con status IN ('done','error'):
#   por cada nodo usa el MAX(updated_at) de su último trace procesado y aplica
#   las ventanas TRACES_RELOAD_INTERVAL (éxito) y TRACES_RETRY_INTERVAL (error).
#   Si un nodo no tiene ningún trace en ese conjunto, es elegible de inmediato.
#
# Qué hace este script:
#   Cambia el status de los traces actuales 'done'/'error' a 'archived'. Así el
#   planificador deja de contarlos y vuelve a tracear cada nodo desde cero,
#   PERO las filas (data_raw, hops, timestamps...) se conservan como histórico.
#   El planificador sigue cogiendo un nodo por ejecución con el cooldown global
#   TRACES_INTERVAL, así que el re-trazado se reparte en el tiempo solo.
#
# Uso:
#   ./scripts/reset_traces.sh            # ejecuta el reset (crea backup antes)
#   ./scripts/reset_traces.sh --dry-run  # solo muestra qué haría, no modifica
#   ./scripts/reset_traces.sh --no-backup
#   ./scripts/reset_traces.sh --db /ruta/a/database.sql
#   ./scripts/reset_traces.sh -h | --help
#
# Recomendación: ejecútalo con el bot detenido para evitar bloqueos de SQLite.
# -----------------------------------------------------------------------------

set -euo pipefail

# --- Localizar la raíz del proyecto y la BD ---------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
DB="${PROJECT_ROOT}/database.sql"

DRY_RUN=0
DO_BACKUP=1

# --- Parseo de argumentos ----------------------------------------------------
usage() {
    sed -n '2,40p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
    exit 0
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run)   DRY_RUN=1; shift ;;
        --no-backup) DO_BACKUP=0; shift ;;
        --db)        DB="${2:?--db requiere una ruta}"; shift 2 ;;
        -h|--help)   usage ;;
        *) echo "Argumento desconocido: $1" >&2; echo "Usa --help" >&2; exit 1 ;;
    esac
done

# --- Comprobaciones previas --------------------------------------------------
command -v sqlite3 >/dev/null 2>&1 || {
    echo "ERROR: 'sqlite3' no está instalado." >&2; exit 1;
}
[[ -f "$DB" ]] || { echo "ERROR: no se encuentra la BD: $DB" >&2; exit 1; }

# --- Conteo antes ------------------------------------------------------------
before="$(sqlite3 "$DB" \
    "SELECT COUNT(*) FROM traces WHERE status IN ('done','error');")"

echo "BD:                 $DB"
echo "Traces a archivar:  $before  (status 'done'/'error')"

if [[ "$before" -eq 0 ]]; then
    echo "No hay traces que archivar. Nada que hacer."
    exit 0
fi

# --- Dry-run -----------------------------------------------------------------
if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "[dry-run] No se modifica nada. Se archivarían $before traces."
    exit 0
fi

# --- Backup ------------------------------------------------------------------
if [[ "$DO_BACKUP" -eq 1 ]]; then
    ts="$(date +%Y%m%d_%H%M%S)"
    backup="${DB}.bak_${ts}"
    cp "$DB" "$backup"
    echo "Backup creado:      $backup"
fi

# --- Reset (transacción) -----------------------------------------------------
sqlite3 "$DB" <<'SQL'
BEGIN;
UPDATE traces SET status = 'archived' WHERE status IN ('done','error');
COMMIT;
SQL

after="$(sqlite3 "$DB" \
    "SELECT COUNT(*) FROM traces WHERE status IN ('done','error');")"
archived="$(sqlite3 "$DB" \
    "SELECT COUNT(*) FROM traces WHERE status = 'archived';")"

echo "Hecho. Traces archivados ahora: $archived. Pendientes done/error: $after."
echo "Cada nodo volverá a tracearse en el próximo ciclo del cron."

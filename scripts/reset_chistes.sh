#!/usr/bin/env bash
#
# reset_chistes.sh
# -----------------------------------------------------------------------------
# Vacía POR COMPLETO la tabla `chistes` de la base de datos, sin tocar el resto.
#
# Contexto:
#   Algunos chistes para adultos se colaban y eran difíciles de identificar
#   uno a uno. La API ya se ha corregido para no volver a enviarlos, así que
#   la forma más limpia de partir de cero es vaciar la tabla `chistes`.
#
# Qué hace este script:
#   Borra TODAS las filas de la tabla `chistes` (DELETE FROM chistes) dentro de
#   una transacción y reinicia su contador AUTOINCREMENT. NO toca ninguna otra
#   tabla (traces, pings, commands_sent, aemet, etc.). Crea un backup de la BD
#   antes de modificar nada.
#
# Uso:
#   ./scripts/reset_chistes.sh            # ejecuta el vaciado (crea backup antes)
#   ./scripts/reset_chistes.sh --dry-run  # solo muestra qué haría, no modifica
#   ./scripts/reset_chistes.sh --no-backup
#   ./scripts/reset_chistes.sh --db /ruta/a/database.sql
#   ./scripts/reset_chistes.sh -h | --help
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
    sed -n '2,30p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
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
before="$(sqlite3 "$DB" "SELECT COUNT(*) FROM chistes;")"

echo "BD:                 $DB"
echo "Chistes a borrar:   $before"

if [[ "$before" -eq 0 ]]; then
    echo "La tabla 'chistes' ya está vacía. Nada que hacer."
    exit 0
fi

# --- Dry-run -----------------------------------------------------------------
if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "[dry-run] No se modifica nada. Se borrarían $before chistes."
    exit 0
fi

# --- Backup ------------------------------------------------------------------
if [[ "$DO_BACKUP" -eq 1 ]]; then
    ts="$(date +%Y%m%d_%H%M%S)"
    backup="${DB}.bak_${ts}"
    cp "$DB" "$backup"
    echo "Backup creado:      $backup"
fi

# --- Vaciado (transacción) ---------------------------------------------------
sqlite3 "$DB" <<'SQL'
BEGIN;
DELETE FROM chistes;
DELETE FROM sqlite_sequence WHERE name = 'chistes';
COMMIT;
VACUUM;
SQL

after="$(sqlite3 "$DB" "SELECT COUNT(*) FROM chistes;")"

echo "Hecho. Chistes restantes: $after."

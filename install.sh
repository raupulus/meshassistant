#!/usr/bin/env bash
# =============================================================================
# install.sh — Instalación y actualización de meshbotassistant
#
# Uso (instalación desde cero):
#   curl -sSL https://raw.githubusercontent.com/raupulus/meshassistant/main/install.sh | bash
#
# Uso (si ya tienes el repo clonado):
#   bash install.sh
#
# Qué hace este script:
#   1. Clona el repositorio en /home/pi/meshbotassistant (o lo actualiza con
#      git pull si ya existe).
#   2. Crea/actualiza el entorno virtual (.venv) e instala las dependencias.
#   3. Crea env.py a partir de env.example.py si no existe todavía.
#   4. Crea/migra la base de datos SQLite.
#   5. Instala el servicio systemd y lo habilita para que arranque con el sistema.
#   6. Instala la entrada de cron para cron_tasks.py (cada minuto).
#
# Requisitos previos:
#   - Raspberry Pi OS (Bullseye / Bookworm) con Python 3.11+.
#   - Usuario pi con permisos sudo.
#   - Puerto serie habilitado en raspi-config y usuario en el grupo dialout:
#       sudo usermod -aG dialout pi   (requiere re-login)
# =============================================================================

set -euo pipefail

# ─── Configuración ────────────────────────────────────────────────────────────
REPO_URL="https://github.com/raupulus/meshassistant.git"
INSTALL_DIR="/home/pi/meshbotassistant"
SERVICE_NAME="meshbotassistant"
SERVICE_SRC="Services/${SERVICE_NAME}.service"
SERVICE_DEST="/etc/systemd/system/${SERVICE_NAME}.service"
CRON_MARKER="meshbotassistant-cron"
CRON_CMD="* * * * * cd ${INSTALL_DIR} && .venv/bin/python cron_tasks.py >> ${INSTALL_DIR}/cron.log 2>&1"

# ─── Colores ──────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()    { echo -e "${GREEN}[INFO]${NC} $*"; }
warning() { echo -e "${YELLOW}[WARN]${NC} $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*" >&2; exit 1; }

# ─── Comprobaciones previas ───────────────────────────────────────────────────
command -v python3 >/dev/null 2>&1 || error "Python 3 no encontrado. Instala con: sudo apt install python3 python3-venv"
command -v git     >/dev/null 2>&1 || error "Git no encontrado. Instala con: sudo apt install git"
# sqlite3 (CLI) no lo necesita el bot (Python trae su propio módulo), pero sí los
# scripts de mantenimiento de scripts/ (p. ej. reset_traces.sh) y los backups.
command -v sqlite3 >/dev/null 2>&1 || warning "sqlite3 (CLI) no encontrado. Necesario para scripts/ y backups: sudo apt install sqlite3"

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
PYTHON_MAJOR=$(echo "$PYTHON_VERSION" | cut -d. -f1)
PYTHON_MINOR=$(echo "$PYTHON_VERSION" | cut -d. -f2)

if [ "$PYTHON_MAJOR" -lt 3 ] || { [ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 11 ]; }; then
    error "Se requiere Python 3.11+. Versión detectada: ${PYTHON_VERSION}"
fi

info "Python ${PYTHON_VERSION} detectado. OK."

# ─── 1. Clonar o actualizar el repositorio ───────────────────────────────────
if [ -d "${INSTALL_DIR}/.git" ]; then
    info "Repositorio existente en ${INSTALL_DIR}. Actualizando..."
    git -C "${INSTALL_DIR}" pull --ff-only
else
    info "Clonando repositorio en ${INSTALL_DIR}..."
    git clone "${REPO_URL}" "${INSTALL_DIR}"
fi

cd "${INSTALL_DIR}"

# ─── 2. Entorno virtual y dependencias ───────────────────────────────────────
info "Creando/actualizando entorno virtual..."
python3 -m venv .venv

info "Instalando dependencias..."
.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet -r requirements.txt

# ─── 3. Configuración (env.py) ───────────────────────────────────────────────
if [ ! -f env.py ]; then
    info "Creando env.py a partir de env.example.py..."
    cp env.example.py env.py
    warning "Edita ${INSTALL_DIR}/env.py antes de iniciar el bot (SERIAL_DEVICE_PATH, claves, etc.)."
else
    info "env.py ya existe. Se mantiene sin cambios."
fi

# ─── 4. Base de datos ─────────────────────────────────────────────────────────
info "Inicializando/migrando la base de datos..."
.venv/bin/python create_db.py

# ─── 5. Servicio systemd ─────────────────────────────────────────────────────
if [ ! -f "${SERVICE_SRC}" ]; then
    error "No se encontró ${SERVICE_SRC}. Asegúrate de que el repositorio está completo."
fi

info "Instalando servicio systemd (${SERVICE_NAME})..."
sudo cp "${SERVICE_SRC}" "${SERVICE_DEST}"
sudo systemctl daemon-reload
sudo systemctl enable "${SERVICE_NAME}"

# No arrancar si env.py acaba de crearse (pendiente de configurar)
if grep -q "SERIAL_DEVICE_PATH" env.py 2>/dev/null && ! grep -q '"/dev/' env.py 2>/dev/null; then
    warning "env.py parece sin configurar. El servicio se arrancará manualmente tras configurarlo."
    warning "Cuando esté listo: sudo systemctl start ${SERVICE_NAME}"
else
    sudo systemctl restart "${SERVICE_NAME}"
    info "Servicio ${SERVICE_NAME} iniciado."
fi

# ─── 6. Cron para cron_tasks.py ──────────────────────────────────────────────
info "Configurando cron para cron_tasks.py..."

# Eliminar entrada anterior si existe (evitar duplicados)
(crontab -l 2>/dev/null | grep -v "${CRON_MARKER}") | crontab - || true

# Añadir la nueva entrada con el marcador
(crontab -l 2>/dev/null; echo "${CRON_CMD} # ${CRON_MARKER}") | crontab -

info "Cron instalado. Verificar con: crontab -l"

# ─── Resumen ──────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}══════════════════════════════════════════════${NC}"
echo -e "${GREEN}  meshbotassistant instalado correctamente     ${NC}"
echo -e "${GREEN}══════════════════════════════════════════════${NC}"
echo ""
echo "  Directorio:  ${INSTALL_DIR}"
echo "  Servicio:    ${SERVICE_NAME} (systemd)"
echo "  Cron:        cada minuto → cron_tasks.py"
echo ""
echo "  Comandos útiles:"
echo "    sudo systemctl status ${SERVICE_NAME}    # estado del servicio"
echo "    sudo systemctl restart ${SERVICE_NAME}   # reiniciar"
echo "    journalctl -u ${SERVICE_NAME} -f         # logs en tiempo real"
echo "    crontab -l                               # ver cron instalado"
echo ""
echo "  Si es la primera instalación, edita env.py y luego:"
echo "    sudo systemctl start ${SERVICE_NAME}"
echo ""

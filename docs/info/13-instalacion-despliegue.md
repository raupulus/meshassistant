# 13 · Instalación y despliegue

## Hardware

- **Servidor / bot:** Raspberry Pi Zero W o **Zero 2 W**.
- **Nodo de malla:** un nodo Meshtastic conectado por **UART** a la Pi.

### Conexión serie (GPIO)

| Pi (GPIO) | Pin físico | Nodo |
|---|---|---|
| GPIO 14 — **TX** | 8 | RX |
| GPIO 15 — **RX** | 10 | TX |
| GND | 6 (u otro) | GND |

Cruzar TX↔RX y compartir GND. Niveles **3.3 V** (no conectar a 5 V).

### Habilitar el puerto serie en la Pi

`sudo raspi-config` → *Interface Options* → *Serial Port*:
- *Would you like a login shell over serial?* → **No**.
- *Would you like the serial port hardware enabled?* → **Yes**.

Reiniciar. El puerto suele quedar como `/dev/serial0` (alias de `/dev/ttyAMA0` o
`/dev/ttyS0` según modelo). Configúralo en `SERIAL_DEVICE_PATH` (`env.py`).

> Asegúrate de que el usuario pertenece al grupo `dialout` para acceder al serie:
> `sudo usermod -aG dialout $USER` (re-login).

## Instalación del software

```bash
git clone <repo> meshassistant && cd meshassistant
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp env.example.py env.py     # editar valores (serial, AEMET, chistes, traces)
python3 create_db.py          # opcional; main.py también la crea
```

## Ejecución

```bash
# Proceso principal (daemon)
python3 main.py

# Tareas periódicas (una pasada)
python3 cron_tasks.py
```

## Despliegue en producción

### 1. Proceso principal con `systemd`

`/etc/systemd/system/meshassistant.service`:

```ini
[Unit]
Description=meshassistant (bot Meshtastic)
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/meshassistant
ExecStart=/home/pi/meshassistant/.venv/bin/python main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now meshassistant
journalctl -u meshassistant -f
```

### 2. Tareas periódicas con `cron`

```cron
* * * * * cd /home/pi/meshassistant && . .venv/bin/activate && python3 cron_tasks.py >> /home/pi/meshassistant/cron.log 2>&1
```

## Ficheros que NO se versionan (y por qué)

| Ruta | Motivo |
|---|---|
| `env.py` | Configuración con posibles claves de API. |
| `database.sql`, `database.sql-shm`, `database.sql-wal` | Datos locales / runtime SQLite. |
| `.venv/` | Entorno virtual local. |
| `.junie/`, `.idea/` | Configuración de IDE/herramientas. |
| `__pycache__/`, `*.pyc` | Artefactos de compilación. |

Todos están en `.gitignore`.

## Mantenimiento

- **Logs:** activa `DEBUG=True` en `env.py` para ver el detalle (`log_p`). El cron
  escribe en `cron.log`; `main.py` (systemd) en `journalctl`.
- **Base de datos:** copia en caliente posible gracias a WAL; para backup consistente
  usa `sqlite3 database.sql ".backup backup.sql"`.
- **Actualizar dependencias:** ver [requisitos](../../requirements.txt) y la nota de
  compatibilidad de `meshtastic` en [04-interfaz-serial.md](04-interfaz-serial.md).

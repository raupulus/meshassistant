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

```bash
sudo raspi-config
# → Interface Options → Serial Port
#   "Would you like a login shell over serial?" → No
#   "Would you like the serial port hardware enabled?" → Yes
```

Reiniciar. El puerto suele quedar como `/dev/serial0` (alias de `/dev/ttyAMA0` o
`/dev/ttyS0` según modelo). Configúralo en `SERIAL_DEVICE_PATH` dentro de `env.py`.

Añadir el usuario al grupo `dialout` para acceder al puerto serie sin sudo:

```bash
sudo usermod -aG dialout pi   # requiere cerrar sesión y volver a entrar
```

> **Conexión USB (desarrollo):** si conectas el nodo por USB desde un PC,
> `SERIAL_DEVICE_PATH` apuntará a `/dev/ttyUSB0` (Linux) o
> `/dev/cu.usbserial-XXXX` (macOS).

---

## Instalación automática (recomendada)

El script `install.sh` automatiza **todo el proceso** de instalación y también
sirve para actualizar el bot en el futuro. Solo se necesita un comando:

```bash
curl -sSL https://raw.githubusercontent.com/raupulus/meshassistant/main/install.sh | bash
```

O, si ya tienes el repositorio clonado:

```bash
bash install.sh
```

### Qué hace el script

1. Clona el repositorio en `/home/pi/meshbotassistant` (o ejecuta `git pull` si
   ya existe).
2. Crea/actualiza el entorno virtual `.venv` e instala las dependencias de
   `requirements.txt`.
3. Crea `env.py` a partir de `env.example.py` si no existe todavía.
4. Inicializa/migra la base de datos SQLite (`create_db.py`).
5. Copia `Services/meshbotassistant.service` a `/etc/systemd/system/` y habilita
   el servicio para que arranque automáticamente con el sistema.
6. Instala la entrada de `cron` para `cron_tasks.py` (cada minuto), evitando
   duplicados en instalaciones sucesivas.

### Tras la instalación

Si es la primera vez, edita `env.py` con los valores correctos antes de arrancar:

```bash
nano /home/pi/meshbotassistant/env.py
```

Variables mínimas obligatorias:

| Variable | Ejemplo | Descripción |
|---|---|---|
| `SERIAL_DEVICE_PATH` | `"/dev/serial0"` | Puerto serie del nodo Meshtastic |
| `DEBUG` | `False` | Activa logging detallado |

Luego arranca el servicio:

```bash
sudo systemctl start meshbotassistant
```

---

## Instalación manual paso a paso

Si prefieres hacerlo tú mismo sin el script:

```bash
# 1. Clonar el repositorio
git clone https://github.com/raupulus/meshassistant.git /home/pi/meshbotassistant
cd /home/pi/meshbotassistant

# 2. Crear el entorno virtual e instalar dependencias
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 3. Configuración
cp env.example.py env.py
nano env.py   # ajustar SERIAL_DEVICE_PATH y demás variables

# 4. Base de datos
.venv/bin/python create_db.py

# 5. Servicio systemd
sudo cp Services/meshbotassistant.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable meshbotassistant
sudo systemctl start meshbotassistant

# 6. Cron para tareas periódicas
crontab -e
# Añadir la siguiente línea:
# * * * * * cd /home/pi/meshbotassistant && .venv/bin/python cron_tasks.py >> /home/pi/meshbotassistant/cron.log 2>&1
```

---

## Servicio systemd — detalles

El archivo de servicio se encuentra en `Services/meshbotassistant.service` y se
instala en `/etc/systemd/system/meshbotassistant.service`.

```ini
[Unit]
Description=meshbotassistant — Bot Meshtastic para Raspberry Pi
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=pi
Group=dialout
WorkingDirectory=/home/pi/meshbotassistant
ExecStart=/home/pi/meshbotassistant/.venv/bin/python main.py
Restart=always
RestartSec=30
TimeoutStartSec=60
TimeoutStopSec=15
StandardOutput=journal
StandardError=journal
SyslogIdentifier=meshbotassistant

[Install]
WantedBy=multi-user.target
```

### Parámetros clave

| Parámetro | Valor | Por qué |
|---|---|---|
| `After=network-online.target` | — | Garantiza que la interfaz de red existe antes de arrancar |
| `Group=dialout` | — | Acceso al puerto serie sin sudo |
| `Restart=always` | — | Reinicia el proceso si muere por cualquier causa |
| `RestartSec=30` | 30 s | Evita bucle de reinicios rápidos ante fallos continuos |
| `TimeoutStopSec=15` | 15 s | Tiempo de gracia para parada limpia antes de SIGKILL |
| `StandardOutput=journal` | — | Logs accesibles con `journalctl` |

### Tolerancia a errores de conexión

El bot gestiona internamente los errores de conexión al nodo (puerto serie caído,
nodo apagado, ocupado…): espera y reintenta cada minuto sin salir del proceso.
`Restart=always` complementa este comportamiento cubriendo los casos en que el
proceso muere inesperadamente (excepción no capturada, OOM, señal externa, etc.).

### Comandos de gestión habituales

```bash
# Estado del servicio
sudo systemctl status meshbotassistant

# Iniciar / detener / reiniciar
sudo systemctl start   meshbotassistant
sudo systemctl stop    meshbotassistant
sudo systemctl restart meshbotassistant

# Logs en tiempo real
journalctl -u meshbotassistant -f

# Últimas 100 líneas de log
journalctl -u meshbotassistant -n 100

# Habilitar / deshabilitar arranque automático
sudo systemctl enable  meshbotassistant
sudo systemctl disable meshbotassistant

# Recargar el archivo .service tras modificarlo
sudo systemctl daemon-reload && sudo systemctl restart meshbotassistant
```

---

## Tareas periódicas con cron

`cron_tasks.py` se encarga de sincronizar chistes, encolar traceroutes y descargar
alertas AEMET. Se ejecuta cada minuto desde `cron`; **nunca** abre el puerto serie
(solo encola trabajo en SQLite para que `main.py` lo realice).

Entrada de crontab instalada por `install.sh`:

```cron
* * * * * cd /home/pi/meshbotassistant && .venv/bin/python cron_tasks.py >> /home/pi/meshbotassistant/cron.log 2>&1
```

Ver el cron activo:

```bash
crontab -l
```

Rotar o limpiar el log del cron:

```bash
> /home/pi/meshbotassistant/cron.log   # vaciar sin borrar el fichero
```

---

## Actualización del bot

Con el script, actualizar a la última versión es un solo comando:

```bash
bash /home/pi/meshbotassistant/install.sh
```

El script hace `git pull`, reinstala dependencias si cambiaron, migra la BD y
reinicia el servicio automáticamente. `env.py` y `database.sql` no se tocan.

---

## Ficheros que no se versionan

| Ruta | Motivo |
|---|---|
| `env.py` | Configuración local con posibles claves de API |
| `database.sql`, `database.sql-shm`, `database.sql-wal` | Datos runtime de SQLite |
| `.venv/` | Entorno virtual local |
| `cron.log` | Log de ejecuciones del cron |
| `__pycache__/`, `*.pyc` | Artefactos de compilación |

Todos están en `.gitignore`.

---

## Mantenimiento

- **Logs del bot:** `journalctl -u meshbotassistant -f`
- **Logs del cron:** `tail -f /home/pi/meshbotassistant/cron.log`
- **Logging detallado:** activar `DEBUG=True` en `env.py` y reiniciar el servicio.
- **Backup de la BD:**

```bash
sqlite3 /home/pi/meshbotassistant/database.sql ".backup /home/pi/backup.sql"
```

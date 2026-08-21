# 04 · Servicio Systemd para la Pasarela Gateway

Para garantizar que el servidor WebSocket se ejecute en segundo plano y se reinicie automáticamente tras caídas o reinicios de la Raspberry Pi Zero 2 W, se despliega como una unidad de servicio independiente en **systemd**.

---

## 1. Archivo de Servicio (`meshassistant-gateway.service`)

Crear el archivo en `/etc/systemd/system/meshassistant-gateway.service`:

```ini
[Unit]
Description=Meshassistant WebSocket Gateway Service
After=network.target
Wants=network-online.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/meshassistant
ExecStart=/home/pi/meshassistant/.venv/bin/python3 Services/Gateway.py
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

> **Nota:** Ajustar `User` y las rutas de `WorkingDirectory` y `.venv` según el usuario y directorio real de despliegue en la Raspberry Pi.

---

## 2. Comandos de Activación y Control

```bash
# Recargar systemd tras crear o editar el servicio
sudo systemctl daemon-reload

# Habilitar el servicio para arranque automático
sudo systemctl enable meshassistant-gateway.service

# Iniciar el servicio
sudo systemctl start meshassistant-gateway.service

# Comprobar estado
sudo systemctl status meshassistant-gateway.service

# Ver logs en vivo
journalctl -u meshassistant-gateway.service -f
```

#!/bin/bash
# Network watchdog for Raspberry Pi
# Pings the gateway and restarts NetworkManager if the connection is dead

GATEWAY="172.18.0.1"
LOG_PREFIX="WiFi-Watchdog:"

# Ping gateway with 3 packets, max wait 10 seconds
ping -c 3 -W 10 $GATEWAY > /dev/null 2>&1

if [ $? -ne 0 ]; then
    logger "$LOG_PREFIX Ping to gateway $GATEWAY failed. Restarting NetworkManager..."
    systemctl restart NetworkManager
    
    # Wait a bit for connection to establish
    sleep 15
    
    # Try again
    ping -c 3 -W 10 $GATEWAY > /dev/null 2>&1
    if [ $? -ne 0 ]; then
        logger "$LOG_PREFIX Ping still failing after NM restart. Reloading brcmfmac driver..."
        modprobe -r brcmfmac
        sleep 2
        modprobe brcmfmac
    else
        logger "$LOG_PREFIX Network recovered successfully after NM restart."
    fi
fi

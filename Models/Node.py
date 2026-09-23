from Models.Database import Database


class Node:

    name = 'Desconocido'
    num = 'Desconocido'
    short_name = 'N/A'
    mac_addr = 'Desconocido'
    hw_model = 'Desconocido'
    role = None
    is_favorite = False
    is_watched = False
    telemetry_count = 0
    traces_detected = 0
    snr = None
    rssi = None
    public_key = None
    hops = None
    hop_start = None
    uptime = None
    via_mqtt = False
    battery = None
    voltage = None
    power_ina1 = None
    power_ina2 = None
    power_ina3 = None
    channel_util = None
    air_util_tx = None
    last_heard = None


    def __init__(self, id):
        self.id = id
        self.updated = False

        from functions import is_node_discarded
        if is_node_discarded(node_id=self.id):
            return

        # Cargar desde BD si existe o crearlo
        try:
            db = Database()
            row = db.get_node(self.id)
            if row:
                self.name = row.get('name', self.name)
                self.num = row.get('num', self.num)
                self.short_name = row.get('short_name', self.short_name)
                self.mac_addr = row.get('mac_addr', self.mac_addr)
                self.hw_model = row.get('hw_model', self.hw_model)
                self.role = row.get('role', self.role)
                self.is_favorite = bool(row.get('is_favorite')) if row.get('is_favorite') is not None else self.is_favorite
                self.is_watched = bool(row.get('is_watched')) if row.get('is_watched') is not None else self.is_watched
                self.snr = row.get('snr', self.snr)
                self.rssi = row.get('rssi', self.rssi)
                self.public_key = row.get('public_key', self.public_key)
                self.hops = row.get('hops', self.hops)
                self.hop_start = row.get('hop_start', self.hop_start)
                self.uptime = row.get('uptime', self.uptime)
                self.via_mqtt = bool(row.get('via_mqtt')) if row.get('via_mqtt') is not None else self.via_mqtt
                self.battery = row.get('battery', self.battery)
                self.voltage = row.get('voltage', self.voltage)
                self.power_ina1 = row.get('power_ina1', self.power_ina1)
                self.power_ina2 = row.get('power_ina2', self.power_ina2)
                self.power_ina3 = row.get('power_ina3', self.power_ina3)
                self.channel_util = row.get('channel_util', self.channel_util)
                self.air_util_tx = row.get('air_util_tx', self.air_util_tx)
                self.traces_detected = int(row.get('traces_detected')) if row.get('traces_detected') is not None else 0
                self.telemetry_count = int(row.get('telemetry_count')) if row.get('telemetry_count') is not None else 0
                self.last_heard = row.get('last_heard', self.last_heard)
            else:
                db.create_node_if_not_exists(self.id)
        except Exception:
            # Si la BD no está lista o hay error, continuar en memoria
            pass

    def update_metadata(self, node_info):
        self.name = node_info.get('name', self.name)
        self.num = node_info.get('num', self.num)
        self.short_name = node_info.get('short_name', self.short_name)
        self.mac_addr = node_info.get('mac_addr', self.mac_addr)
        self.hw_model = node_info.get('hw_model', self.hw_model)
        self.role = node_info.get('role', self.role)
        # is_favorite es una preferencia de usuario/dashboard.
        # Los paquetes de radio nunca deben desmarcar un favorito existente.
        # Solo se actualiza si viene explícitamente como True (ej. importación inicial desde la radio).
        if node_info.get('is_favorite') is True or node_info.get('isFavorite') is True:
            self.is_favorite = True
        if node_info.get('is_watched') is not None:
            self.is_watched = bool(node_info.get('is_watched'))
        if node_info.get('telemetry_count') is not None:
            try:
                self.telemetry_count = int(node_info.get('telemetry_count'))
            except Exception:
                pass
        if node_info.get('traces_detected') is not None:
            try:
                self.traces_detected = int(node_info.get('traces_detected'))
            except Exception:
                pass
        self.uptime = node_info.get('uptime', self.uptime)
        self.via_mqtt = node_info.get('via_mqtt', self.via_mqtt)
        
        # Telemetría de batería si está presente
        dev_m = node_info.get('deviceMetrics') or node_info.get('device_metrics') or {}
        if isinstance(dev_m, dict):
            if dev_m.get('batteryLevel') is not None:
                self.battery = dev_m.get('batteryLevel')
            if dev_m.get('voltage') is not None:
                self.voltage = dev_m.get('voltage')
            if dev_m.get('uptimeSeconds') is not None:
                self.uptime = dev_m.get('uptimeSeconds')
            ch_u = dev_m.get('channelUtilization') if dev_m.get('channelUtilization') is not None else dev_m.get('channel_utilization')
            if ch_u is None:
                ch_u = dev_m.get('channel_util')
            if ch_u is not None:
                try:
                    self.channel_util = round(float(ch_u), 2)
                except Exception:
                    pass
            a_tx = dev_m.get('airUtilTx') if dev_m.get('airUtilTx') is not None else dev_m.get('air_util_tx')
            if a_tx is not None:
                try:
                    self.air_util_tx = round(float(a_tx), 2)
                except Exception:
                    pass
        
        if node_info.get('battery') is not None:
            self.battery = node_info.get('battery')
        if node_info.get('batteryLevel') is not None:
            self.battery = node_info.get('batteryLevel')
        if node_info.get('voltage') is not None:
            self.voltage = node_info.get('voltage')
        if node_info.get('channel_util') is not None:
            try:
                self.channel_util = round(float(node_info.get('channel_util')), 2)
            except Exception:
                pass
        if node_info.get('air_util_tx') is not None:
            try:
                self.air_util_tx = round(float(node_info.get('air_util_tx')), 2)
            except Exception:
                pass

        # Telemetría de potencia / sensores INA externos
        power_m = node_info.get('powerMetrics') or node_info.get('power_metrics') or {}
        if isinstance(power_m, dict):
            ina1_v = power_m.get('ch1Voltage') if power_m.get('ch1Voltage') is not None else power_m.get('ch1_voltage')
            if ina1_v is None:
                ina1_v = power_m.get('voltage')
            if ina1_v is not None:
                self.power_ina1 = ina1_v
            ina2_v = power_m.get('ch2Voltage') if power_m.get('ch2Voltage') is not None else power_m.get('ch2_voltage')
            if ina2_v is not None:
                self.power_ina2 = ina2_v
            ina3_v = power_m.get('ch3Voltage') if power_m.get('ch3Voltage') is not None else power_m.get('ch3_voltage')
            if ina3_v is not None:
                self.power_ina3 = ina3_v

        if node_info.get('power_ina1') is not None:
            self.power_ina1 = node_info.get('power_ina1')
        if node_info.get('power_ina2') is not None:
            self.power_ina2 = node_info.get('power_ina2')
        if node_info.get('power_ina3') is not None:
            self.power_ina3 = node_info.get('power_ina3')

        self.snr = node_info.get('snr', self.snr)
        self.rssi = node_info.get('rssi', self.rssi)

        hops_start = node_info.get('hop_start', None)
        hops_limit = node_info.get('hop_limit', None)

        if hops_start:
            self.hop_start = hops_start

        if hops_start and hops_limit:
            self.hops = hops_start - hops_limit

        self.updated = True

        from functions import is_node_discarded
        if is_node_discarded(node_id=self.id, short_name=self.short_name, name=self.name):
            return

        # Persistir en BD
        try:
            db = Database()
            db.create_node_if_not_exists(self.id)
            db_update = {
                "name": self.name,
                "num": self.num,
                "short_name": self.short_name,
                "mac_addr": self.mac_addr,
                "hw_model": self.hw_model,
                "role": self.role,
                "snr": self.snr,
                "rssi": self.rssi,
                "public_key": self.public_key,
                "hops": self.hops,
                "hop_start": self.hop_start,
                "uptime": self.uptime,
                "via_mqtt": self.via_mqtt,
                "battery": self.battery,
                "voltage": self.voltage,
                "last_heard": self.last_heard,
            }
            if self.power_ina1 is not None:
                db_update["power_ina1"] = self.power_ina1
            if self.power_ina2 is not None:
                db_update["power_ina2"] = self.power_ina2
            if self.power_ina3 is not None:
                db_update["power_ina3"] = self.power_ina3
            if self.channel_util is not None:
                db_update["channel_util"] = self.channel_util
            if self.air_util_tx is not None:
                db_update["air_util_tx"] = self.air_util_tx
            if node_info.get('is_favorite') is True or node_info.get('isFavorite') is True:
                db_update["is_favorite"] = 1
            if node_info.get('is_watched') is not None:
                db_update["is_watched"] = 1 if self.is_watched else 0
            if node_info.get('telemetry_count') is not None:
                db_update["telemetry_count"] = self.telemetry_count
            db.update_node(self.id, db_update)
        except Exception:
            # En caso de error al guardar, continuar sin interrumpir
            pass

    def update_positions(self):
        pass

    def update_metrics(self):
        pass

    def get_metadata(self):
        return {
            "id": self.id,
            "name": self.name,
            "num": self.num,
            "short_name": self.short_name,
            "mac_addr": self.mac_addr,
            "hw_model": self.hw_model,
            "is_favorite": self.is_favorite,
            "is_watched": self.is_watched,
            "public_key": self.public_key,
            "snr": self.snr,
            "rssi": self.rssi,
            "hops": self.hops,
            "hop_start": self.hop_start,
            "uptime": self.uptime,
            "via_mqtt": self.via_mqtt,
            "battery": self.battery,
            "voltage": self.voltage,
            "power_ina1": self.power_ina1,
            "power_ina2": self.power_ina2,
            "power_ina3": self.power_ina3,
            "channel_util": self.channel_util,
            "air_util_tx": self.air_util_tx,
            "traces_detected": self.traces_detected,
            "telemetry_count": self.telemetry_count,
            "last_heard": self.last_heard,
        }

    def refresh_from_db(self):
        try:
            db = Database()
            row = db.get_node(self.id)
            if row:
                fav = row.get('is_favorite')
                if fav is not None:
                    self.is_favorite = bool(fav)
                wat = row.get('is_watched')
                if wat is not None:
                    self.is_watched = bool(wat)
                self.update_metadata({
                    "name": row.get('name', None),
                    "num": row.get('num', None),
                    "short_name": row.get('short_name', None),
                    "mac_addr": row.get('mac_addr', None),
                    "hw_model": row.get('hw_model', None),
                    "is_favorite": self.is_favorite,
                    "is_watched": self.is_watched,
                    "snr": row.get('snr', None),
                    "rssi": row.get('rssi', None),
                    "public_key": row.get('public_key', None),
                    "hops": row.get('hops', None),
                    "hop_start": row.get('hop_start', None),
                    "uptime": row.get('uptime', None),
                    "via_mqtt": bool(row.get('via_mqtt')) if row.get('via_mqtt') is not None else None,
                    "battery": row.get('battery', None),
                    "voltage": row.get('voltage', None),
                    "power_ina1": row.get('power_ina1', None),
                    "power_ina2": row.get('power_ina2', None),
                    "power_ina3": row.get('power_ina3', None),
                    "channel_util": row.get('channel_util', None),
                    "air_util_tx": row.get('air_util_tx', None),
                    "traces_detected": row.get('traces_detected', 0),
                    "telemetry_count": row.get('telemetry_count', 0),
                    "last_heard": row.get('last_heard', None),
                })
        except Exception:
            pass
        except Exception:
            pass

from Models.Database import Database


class Node:

    name = 'Desconocido'
    num = 'Desconocido'
    short_name = 'N/A'
    mac_addr = 'Desconocido'
    hw_model = 'Desconocido'
    is_favorite = False
    snr = None
    rssi = None
    public_key = None
    hops = None
    hop_start = None
    uptime = None
    via_mqtt = False
    last_heard = None


    def __init__(self, id):
        self.id = id
        self.updated = False

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
                self.is_favorite = bool(row.get('is_favorite')) if row.get('is_favorite') is not None else self.is_favorite
                self.snr = row.get('snr', self.snr)
                self.rssi = row.get('rssi', self.rssi)
                self.public_key = row.get('public_key', self.public_key)
                self.hops = row.get('hops', self.hops)
                self.hop_start = row.get('hop_start', self.hop_start)
                self.uptime = row.get('uptime', self.uptime)
                self.via_mqtt = bool(row.get('via_mqtt')) if row.get('via_mqtt') is not None else self.via_mqtt
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
        self.is_favorite = node_info.get('is_favorite', self.is_favorite)
        self.uptime = node_info.get('uptime', self.uptime)
        self.via_mqtt = node_info.get('via_mqtt', self.via_mqtt)

        # self.public_key = node_info.get('public_key', 0)

        self.snr = node_info.get('snr', self.snr)
        self.rssi = node_info.get('rssi', self.rssi)

        hops_start = node_info.get('hop_start', None)
        hops_limit = node_info.get('hop_limit', None)

        if hops_start:
            self.hop_start = hops_start

        if hops_start and hops_limit:
            self.hops = hops_start - hops_limit

        self.updated = True

        # Persistir en BD
        try:
            db = Database()
            db.create_node_if_not_exists(self.id)
            db.update_node(self.id, {
                "name": self.name,
                "num": self.num,
                "short_name": self.short_name,
                "mac_addr": self.mac_addr,
                "hw_model": self.hw_model,
                "is_favorite": self.is_favorite,
                "snr": self.snr,
                "rssi": self.rssi,
                "public_key": self.public_key,
                "hops": self.hops,
                "hop_start": self.hop_start,
                "uptime": self.uptime,
                "via_mqtt": self.via_mqtt,
                "last_heard": self.last_heard,
            })
        except Exception:
            # En caso de error al guardar, continuar sin interrumpir
            pass

    def update_positions(self):
        # al cargar nodos:
        #{'num': 1674190827, 'user': {'id': '!63ca1feb', 'longName': 'Raupulus PicoBot', 'shortName': 'rau5', 'macaddr': 'KT9jyh/r', 'hwModel': 79, 'role': 'CLIENT_MUTE'}, 'position': {'time': 1762114855}, 'lastHeard': 1762114855, 'deviceMetrics': {'batteryLevel': 101, 'voltage': 4.348, 'channelUtilization': 5.636667, 'airUtilTx': 0.18047222, 'uptimeSeconds': 245}, 'isFavorite': True}

        #self.last_heard = node_info.get('last_heard', self.last_heard)
        #
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
            "public_key": self.public_key,
            "snr": self.snr,
            "rssi": self.rssi,
            "hops": self.hops,
            "hop_start": self.hop_start,
            "uptime": self.uptime,
            "via_mqtt": self.via_mqtt,
            "last_heard": self.last_heard,
        }

    def refresh_from_db(self):
        try:
            db = Database()
            row = db.get_node(self.id)
            if row:
                self.update_metadata({
                    "name": row.get('name', None),
                    "num": row.get('num', None),
                    "short_name": row.get('short_name', None),
                    "mac_addr": row.get('mac_addr', None),
                    "hw_model": row.get('hw_model', None),
                    "is_favorite": bool(row.get('is_favorite')) if row.get('is_favorite') is not None else None,
                    "snr": row.get('snr', None),
                    "rssi": row.get('rssi', None),
                    "public_key": row.get('public_key', None),
                    "hops": row.get('hops', None),
                    "hop_start": row.get('hop_start', None),
                    "uptime": row.get('uptime', None),
                    "via_mqtt": bool(row.get('via_mqtt')) if row.get('via_mqtt') is not None else None,
                    "last_heard": row.get('last_heard', None),
                })
        except Exception:
            pass

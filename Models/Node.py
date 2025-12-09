




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

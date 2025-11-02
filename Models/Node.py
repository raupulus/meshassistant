




class Node:

    name = None
    short_name = None
    mac_addr = None
    hw_model = None
    is_favorite = None
    snr = None
    rssi = None
    public_key = None


    def __init__(self, id):
        self.id = id
        self.updated = False

    def update_metadata(self, node_info):
        user = node_info.get('user', { })

        self.name = user.get('longName', 'Desconocido')
        self.short_name = user.get('shortName', 'N/A')
        self.mac_addr = user.get('macAddr', 'Desconocido')
        self.hw_model = user.get('hwModel', 'Desconocido')
        self.is_favorite = user.get('isFavorite', False)
        # self.public_key = node_info.get('public_key', 0)
        # self.snr = node_info.get('snr', 0)
        # self.rssi = node_info.get('rssi', 0)

        self.updated = True

    def get_metadata(self):
        return {
            "id": self.id,
            "name": self.name,
            "short_name": self.short_name,
            "mac_addr": self.mac_addr,
            "hw_model": self.hw_model,
            "is_favorite": self.is_favorite,
            "public_key": self.public_key,
            "snr": self.snr,
            "rssi": self.rssi,
        }

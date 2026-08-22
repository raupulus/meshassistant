# 05 · Nodos (`Models/Node.py`)

Representa un nodo de la malla Meshtastic con **carga y persistencia automática** en
la tabla `nodes`.

## Ciclo de vida

```python
node = Node(id)            # carga desde BD si existe; si no, lo crea
node.update_metadata({...})# fusiona metadatos y persiste
node.get_metadata()        # dict con el estado actual
node.refresh_from_db()     # recarga desde BD
```

### Constructor `__init__(id)`

- Intenta `Database().get_node(id)`. Si existe, vuelca los campos al objeto.
- Si no existe, `create_node_if_not_exists(id)`.
- Todo dentro de `try/except`: si la BD no está lista, el nodo sigue **en memoria**
  sin romper el flujo.

### `update_metadata(node_info)`

- Fusiona los campos presentes en `node_info` sobre los actuales (los ausentes se
  conservan).
- Calcula `hops = hop_start - hop_limit` cuando ambos están disponibles.
- Persiste vía `Database.create_node_if_not_exists` + `Database.update_node`
  (también con `try/except` defensivo).

## Campos

`id`, `name`, `num`, `short_name`, `mac_addr`, `hw_model`, `role`, `is_favorite`, `snr`,
`rssi`, `public_key`, `hops`, `hop_start`, `uptime`, `via_mqtt`, `battery`, `voltage`, `last_heard`, `created_at`, `updated_at`.

Valores por defecto: `name='Desconocido'`, `short_name='N/A'`, `via_mqtt=False`,
señales en `None`.

## Quién crea/actualiza nodos

- `SerialInterface.get_nodes()` — al conectar, carga toda la lista del nodo local.
- `SerialInterface.on_receive_user()` — al recibir info de usuario de un nodo.
- `SerialInterface.on_receive_text()` — al recibir un mensaje (actualiza señal, saltos, `via_mqtt`, etc.).
- `SerialInterface.on_receive_data()` / `on_node_update()` — al recibir paquetes de telemetría (`deviceMetrics`), persistiendo nivel de batería, voltaje y uptime.
- `SerialInterface.request_node_info(destination_id)` — solicita a un nodo por radio LoRa que emita sus metadatos (`NODEINFO_APP`).

## Relación con traces

Los nombres y la señal de cada salto de un traceroute se resuelven consultando esta
tabla (`Database.get_node`) en `main.py` al enriquecer el resultado. Solo se eligen
para trazar nodos con `via_mqtt=0` y `hops <= TRACES_HOPS`.

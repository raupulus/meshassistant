from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional

from create_db import ensure_database


class Database:
    """Modelo simple para interactuar con la base de datos SQLite."""

    def __init__(self, db_path: Optional[str] = None) -> None:
        self.db_path = str(db_path) if db_path else str(ensure_database())

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # ---------- CHISTES ----------
    def get_random_chiste(self, approved_only: bool = True) -> Optional[Dict[str, Any]]:
        """Devuelve un chiste aleatorio o None si no hay.

        Si approved_only es True, solo devuelve chistes con need_approve = 0.
        """
        with self._connect() as conn:
            if approved_only:
                cur = conn.execute(
                    'SELECT id, "from", content, need_upload FROM chistes WHERE need_approve = 0 ORDER BY RANDOM() LIMIT 1'
                )
            else:
                cur = conn.execute(
                    'SELECT id, "from", content, need_upload, need_approve FROM chistes ORDER BY RANDOM() LIMIT 1'
                )
            row = cur.fetchone()
            if not row:
                return None
            return dict(row)

    def save_chiste(
        self,
        from_: Optional[str],
        content: str,
        need_upload: bool = False,
        need_approve: bool = False,
    ) -> int:
        """Guarda un chiste y devuelve el id insertado.

        Parámetros:
        - from_: origen del chiste (opcional)
        - content: contenido del chiste
        - need_upload: si necesita subirse a un origen externo (por defecto False)
        - need_approve: si requiere aprobación antes de mostrarse (por defecto False)
        """
        with self._connect() as conn:
            cur = conn.execute(
                'INSERT INTO chistes ("from", content, need_upload, need_approve) VALUES (?, ?, ?, ?)',
                (from_, content, 1 if need_upload else 0, 1 if need_approve else 0),
            )
            conn.commit()
            return int(cur.lastrowid)

    # ---------- TRACES ----------
    def save_trace(self, from_: str, to: str, data_raw: str) -> int:
        """Guarda un trace y devuelve el id insertado."""
        with self._connect() as conn:
            cur = conn.execute(
                'INSERT INTO traces ("from", "to", data_raw) VALUES (?, ?, ?)',
                (from_, to, data_raw),
            )
            conn.commit()
            return int(cur.lastrowid)

    # ---------- PINGS ----------
    def save_ping(
        self,
        from_id: str,
        to_id: str,
        data_raw: str,
        *,
        from_name: str | None = None,
        hops: int | None = None,
    ) -> int:
        """Guarda un ping en la tabla pings y devuelve el id insertado.

        - from_id se guarda en la columna "from" (id del nodo origen)
        - from_name se guarda en la columna from_name (nombre del nodo origen)
        - to_id se guarda en la columna "to"
        - hops se guarda en la columna hops
        - data_raw debe ser un string (p.ej., JSON) con los datos crudos
        """
        with self._connect() as conn:
            cur = conn.execute(
                'INSERT INTO pings ("from", "to", from_name, hops, data_raw) VALUES (?, ?, ?, ?, ?)',
                (from_id, to_id, from_name, hops, data_raw),
            )
            conn.commit()
            return int(cur.lastrowid)

    # ---------- QUEUE ----------
    def get_next_in_queue(self) -> Optional[Dict[str, Any]]:
        """TODO: Obtener el siguiente elemento de la cola (queue).
        Estrategia pendiente de definir (p.ej., por send_at, period, etc.).
        """
        # TODO: Implementar lógica de extracción de la cola según reglas de negocio
        return None

    # ---------- AGENDA ----------
    def get_agenda(self, node_id: str) -> List[Dict[str, Any]]:
        """Devuelve todos los elementos de la agenda para un node_id."""
        with self._connect() as conn:
            cur = conn.execute(
                'SELECT id, node_id, content, moment FROM agenda WHERE node_id = ? ORDER BY moment ASC',
                (node_id,),
            )
            return [dict(row) for row in cur.fetchall()]

    def add_agenda(self, node_id: str, content: str, moment: Optional[Any] = None) -> int:
        """Añade un elemento a la agenda y devuelve el id.

        - moment puede ser None, un datetime, o una cadena ISO 8601.
        Si es None, se usará el momento actual (UTC local según sistema).
        """
        if moment is None:
            moment_str = datetime.now().isoformat(timespec="seconds")
        elif isinstance(moment, datetime):
            moment_str = moment.isoformat(timespec="seconds")
        else:
            moment_str = str(moment)

        with self._connect() as conn:
            cur = conn.execute(
                'INSERT INTO agenda (node_id, content, moment) VALUES (?, ?, ?)',
                (node_id, content, moment_str),
            )
            conn.commit()
            return int(cur.lastrowid)

    # ---------- NODES ----------
    def get_node(self, node_id: str) -> Optional[Dict[str, Any]]:
        """Obtiene un nodo por su node_id."""
        with self._connect() as conn:
            cur = conn.execute(
                """
                SELECT node_id, name, num, short_name, mac_addr, hw_model, is_favorite,
                       snr, rssi, public_key, hops, hop_start, uptime, via_mqtt,
                       last_heard, updated_at
                FROM nodes
                WHERE node_id = ?
                """,
                (node_id,),
            )
            row = cur.fetchone()
            return dict(row) if row else None

    def create_node_if_not_exists(self, node_id: str, data: Optional[Dict[str, Any]] = None) -> None:
        """Crea un nodo si no existe. Ignora si ya existe."""
        now = datetime.now().isoformat(timespec="seconds")
        with self._connect() as conn:
            conn.execute(
                'INSERT OR IGNORE INTO nodes (node_id, updated_at) VALUES (?, ?)',
                (node_id, now),
            )
            conn.commit()

        # Si se pasa data, realizar una actualización inicial
        if data:
            self.update_node(node_id, data)

    def update_node(self, node_id: str, data: Dict[str, Any]) -> None:
        """Actualiza un nodo por node_id con las claves proporcionadas en data."""
        if not data:
            return

        allowed = {
            "name",
            "num",
            "short_name",
            "mac_addr",
            "hw_model",
            "is_favorite",
            "snr",
            "rssi",
            "public_key",
            "hops",
            "hop_start",
            "uptime",
            "via_mqtt",
            "last_heard",
        }

        # Filtrar y preparar valores
        fields: List[str] = []
        values: List[Any] = []

        for k, v in data.items():
            if k not in allowed:
                continue
            if k in ("is_favorite", "via_mqtt") and v is not None:
                v = 1 if bool(v) else 0
            fields.append(f"{k} = ?")
            values.append(v)

        if not fields:
            return

        values.append(datetime.now().isoformat(timespec="seconds"))
        values.append(node_id)

        set_clause = ", ".join(fields + ["updated_at = ?"])  # siempre actualizar updated_at

        with self._connect() as conn:
            conn.execute(
                f"UPDATE nodes SET {set_clause} WHERE node_id = ?",
                tuple(values),
            )
            conn.commit()

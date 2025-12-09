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

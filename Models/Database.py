from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional, Iterable, Tuple

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
        chiste_id: Optional[int] = None,
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
                'INSERT INTO chistes ("from", content, need_upload, need_approve, chiste_id) VALUES (?, ?, ?, ?, ?)',
                (from_, content, 1 if need_upload else 0, 1 if need_approve else 0, chiste_id),
            )
            conn.commit()
            return int(cur.lastrowid)

    def get_chistes_to_upload(self, limit: int = 100) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            cur = conn.execute(
                'SELECT id, "from", content FROM chistes WHERE need_upload = 1 LIMIT ?',
                (limit,),
            )
            return [dict(r) for r in cur.fetchall()]

    def mark_chistes_uploaded(self, ids: Iterable[int]) -> None:
        ids = list(ids)
        if not ids:
            return
        placeholders = ",".join(["?"] * len(ids))
        with self._connect() as conn:
            conn.execute(f'UPDATE chistes SET need_upload = 0 WHERE id IN ({placeholders})', tuple(ids))
            conn.commit()

    def get_last_downloaded_chiste_id(self) -> Optional[int]:
        with self._connect() as conn:
            cur = conn.execute('SELECT MAX(chiste_id) as last_id FROM chistes WHERE chiste_id IS NOT NULL')
            row = cur.fetchone()
            return int(row[0]) if row and row[0] is not None else None

    def bulk_insert_api_chistes(self, items: Iterable[Dict[str, Any]]) -> Tuple[int, int]:
        """Inserta chistes descargados de la API.

        Cada item debe tener: id (-> chiste_id) y content.
        Flags need_approve y need_upload se guardan en 0.
        Devuelve (insertados, ignorados).
        """
        inserted = 0
        ignored = 0
        with self._connect() as conn:
            for it in items:
                api_id = it.get('id')
                content = it.get('content')
                if content is None:
                    continue
                try:
                    conn.execute(
                        'INSERT OR IGNORE INTO chistes ("from", content, need_upload, need_approve, chiste_id) VALUES (?, ?, 0, 0, ?)',
                        (None, content, api_id),
                    )
                    if conn.total_changes > 0:
                        inserted += 1
                    else:
                        ignored += 1
                except sqlite3.IntegrityError:
                    ignored += 1
            conn.commit()
        return inserted, ignored

    # ---------- TRACES ----------
    def save_trace(self, from_: str, to: str, data_raw: str) -> int:
        """Guarda un trace clásico (registro completo) y devuelve el id insertado."""
        with self._connect() as conn:
            now = datetime.now().isoformat(timespec='seconds')
            cur = conn.execute(
                'INSERT INTO traces ("from", "to", data_raw, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)',
                (from_, to, data_raw, 'done', now, now),
            )
            conn.commit()
            return int(cur.lastrowid)

    def enqueue_trace(self, node_id: str) -> int:
        """Encola un trace para un node_id en la propia tabla `traces`.

        Inserta un registro con "to"=node_id, status='pending', created_at=ahora,
        y deja NULL los campos "from", data_raw, updated_at.

        Si ya existe un pendiente para ese nodo, devuelve su id sin crear otro.
        """
        now = datetime.now().isoformat(timespec='seconds')
        with self._connect() as conn:
            cur = conn.execute(
                'SELECT id FROM traces WHERE "to" = ? AND status = "pending" ORDER BY created_at ASC LIMIT 1',
                (node_id,),
            )
            row = cur.fetchone()
            if row:
                return int(row['id'])
            cur2 = conn.execute(
                'INSERT INTO traces ("to", status, created_at) VALUES (?, "pending", ?)',
                (node_id, now),
            )
            conn.commit()
            return int(cur2.lastrowid)

    def get_next_pending_trace(self) -> Optional[Dict[str, Any]]:
        """Obtiene el trace pendiente más antiguo (status='pending') o None."""
        with self._connect() as conn:
            cur = conn.execute(
                'SELECT id, "to", created_at FROM traces WHERE status = "pending" ORDER BY created_at ASC LIMIT 1'
            )
            row = cur.fetchone()
            return dict(row) if row else None

    def mark_trace_done(self, trace_id: int, ok: bool, payload: str, from_: str = 'local') -> None:
        """Marca un trace pendiente como procesado, guardando resultado y sellando updated_at.

        - ok=True -> status='done'
        - ok=False -> status='error'
        - payload debe ser string (ej. JSON)
        """
        when_str = datetime.now().isoformat(timespec='seconds')
        status = 'done' if ok else 'error'
        with self._connect() as conn:
            conn.execute(
                'UPDATE traces SET status = ?, data_raw = ?, "from" = ?, updated_at = ? WHERE id = ?',
                (status, payload, from_, when_str, trace_id),
            )
            conn.commit()

    def mark_trace_done_with_route(
        self,
        trace_id: int,
        ok: bool,
        *,
        text: str,
        to_name: Optional[str] = None,
        to_name_short: Optional[str] = None,
        hops: Optional[List[Dict[str, Any]]] = None,
        return_hops: Optional[List[Dict[str, Any]]] = None,
        from_: str = 'local',
    ) -> None:
        """Marca un trace pendiente como procesado y guarda campos enriquecidos.

        - text: cadena completa del trace (se almacena en data_raw)
        - to_name / to_name_short: nombres del destino (si disponibles)
        - hops: lista de hasta 7 dicts con claves: id, name, name_short, snr, rssi (ida)
        - return_hops: lista de hasta 7 dicts (regreso) con las mismas claves
        """
        when_str = datetime.now().isoformat(timespec='seconds')
        status = 'done' if ok else 'error'
        hops = hops or []
        return_hops = return_hops or []

        # Preparar columnas y valores
        set_cols: List[str] = [
            'status = ?',
            'data_raw = ?',
            '"from" = ?',
            'updated_at = ?',
            'hops = ?',
            'hops_back = ?',
            'to_name = ?',
            'to_name_short = ?',
        ]
        # Cálculo de número de saltos: contamos nodos en la lista y restamos 1 para excluir el destino/origen final
        hops_count = max(len(hops) - 1, 0) if hops else 0
        hops_back_count = max(len(return_hops) - 1, 0) if return_hops else 0
        values: List[Any] = [status, text, from_, when_str, hops_count, hops_back_count, to_name, to_name_short]

        # Rellenar hop1..hop7
        for i in range(1, 8):
            item = hops[i - 1] if i - 1 < len(hops) else None
            for suffix in ('id', 'name', 'name_short', 'snr', 'rssi'):
                set_cols.append(f'hop{i}_{suffix} = ?')
                if item:
                    values.append(item.get(suffix))
                else:
                    values.append(None)

        # Rellenar hop_return1..hop_return7
        for i in range(1, 8):
            item = return_hops[i - 1] if i - 1 < len(return_hops) else None
            for suffix in ('id', 'name', 'name_short', 'snr', 'rssi'):
                set_cols.append(f'hop_return{i}_{suffix} = ?')
                if item:
                    values.append(item.get(suffix))
                else:
                    values.append(None)

        values.append(trace_id)

        sql = f'UPDATE traces SET {", ".join(set_cols)} WHERE id = ?'
        with self._connect() as conn:
            conn.execute(sql, tuple(values))
            conn.commit()

    def get_last_trace_updated_at(self) -> Optional[str]:
        """Devuelve el timestamp (ISO) del último trace procesado (updated_at no NULL)."""
        with self._connect() as conn:
            cur = conn.execute('SELECT MAX(updated_at) AS last FROM traces WHERE updated_at IS NOT NULL')
            row = cur.fetchone()
            return row['last'] if row and row['last'] else None

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

    # ---------- TASKS CONTROL ----------
    def get_task_last_run(self, name: str) -> Optional[str]:
        with self._connect() as conn:
            cur = conn.execute('SELECT last_run_at FROM tasks_control WHERE name = ?', (name,))
            row = cur.fetchone()
            return row['last_run_at'] if row and row['last_run_at'] else None

    def set_task_run(self, name: str, when: Optional[datetime] = None, extra: Optional[str] = None) -> None:
        when_str = (when or datetime.now()).isoformat(timespec='seconds')
        with self._connect() as conn:
            conn.execute(
                (
                    """
                    INSERT INTO tasks_control (name, last_run_at, extra) VALUES (?, ?, ?)
                    ON CONFLICT(name) DO UPDATE SET last_run_at = excluded.last_run_at, extra = excluded.extra
                    """
                ),
                (name, when_str, extra),
            )
            conn.commit()

    # ---------- NODE TRACE CONTROL ----------
    def get_next_node_to_trace(self, min_days: int = 7) -> Optional[str]:
        """Devuelve el próximo node_id candidato (2 hops, no MQTT), sin pendientes,
        con ventana de reintento según último estado:
          - último status='done' => ≥7 días
          - último status='error' => ≥1 día
        Si no hay trazas previas: elegible.
        """
        with self._connect() as conn:
            cur = conn.execute(
                '''
                WITH last_processed AS (
                    SELECT "to" AS node_id, MAX(updated_at) AS last_updated
                    FROM traces
                    WHERE updated_at IS NOT NULL AND status IN ('done','error')
                    GROUP BY "to"
                ), last_status AS (
                    SELECT t."to" AS node_id, t.status AS last_status, t.updated_at AS last_updated
                    FROM traces t
                    WHERE t.updated_at IS NOT NULL AND t.status IN ('done','error')
                    AND t.updated_at = (
                        SELECT MAX(t2.updated_at) FROM traces t2
                        WHERE t2."to" = t."to" AND t2.updated_at IS NOT NULL AND t2.status IN ('done','error')
                    )
                ), pend AS (
                    SELECT "to" AS node_id, COUNT(*) AS pendings
                    FROM traces
                    WHERE status = 'pending'
                    GROUP BY "to"
                )
                SELECT n.node_id
                FROM nodes n
                LEFT JOIN last_processed lp ON lp.node_id = n.node_id
                LEFT JOIN last_status ls ON ls.node_id = n.node_id
                LEFT JOIN pend p ON p.node_id = n.node_id
                WHERE COALESCE(n.via_mqtt, 0) = 0
                  AND n.hops = 2
                  AND COALESCE(p.pendings, 0) = 0
                  AND (
                        lp.last_updated IS NULL
                     OR (
                          (ls.last_status = 'done'  AND datetime(lp.last_updated) < datetime('now', '-7 days'))
                       OR (ls.last_status = 'error' AND datetime(lp.last_updated) < datetime('now', '-1 days'))
                        )
                  )
                ORDER BY n.updated_at DESC
                LIMIT 1
                '''
            )
            row = cur.fetchone()
            return row['node_id'] if row else None

    # Trace requests: eliminadas en favor de usar la propia tabla `traces` como cola

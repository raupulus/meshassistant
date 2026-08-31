from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Iterable, Tuple
import hashlib
import json

from create_db import ensure_database
from functions import sanitize_text


class Database:
    """Modelo simple para interactuar con la base de datos SQLite."""

    def __init__(self, db_path: Optional[str] = None) -> None:
        self.db_path = str(ensure_database(db_path))

    def _connect(self) -> sqlite3.Connection:
        # timeout: tiempo que el driver espera por un lock antes de lanzar
        # OperationalError. busy_timeout: equivalente a nivel SQLite (ms).
        # Ambos protegen frente a escrituras concurrentes (daemon + cron).
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.execute('PRAGMA busy_timeout = 10000')
        conn.row_factory = sqlite3.Row
        return conn

    # ---------- CHISTES ----------
    def get_random_chiste(self, approved_only: bool = True) -> Optional[Dict[str, Any]]:
        """Devuelve un chiste aleatorio o None si no hay.

        Si approved_only es True, solo devuelve chistes con need_approve = 0.
        """
        with closing(self._connect()) as conn:
            if approved_only:
                cur = conn.execute(
                    'SELECT id, "from", content, need_upload FROM chistes WHERE need_approve = 0 ORDER BY RANDOM() LIMIT 1'
                )
            else:
                cur = conn.execute(
                    'SELECT id, "from", content, need_upload FROM chistes ORDER BY RANDOM() LIMIT 1'
                )
            row = cur.fetchone()
            return dict(row) if row else None

    def save_chiste(
        self,
        from_: Optional[str],
        content: str,
        need_upload: bool = False,
        need_approve: bool = False,
        chiste_id: Optional[int] = None,
    ) -> int:
        """Inserta un nuevo chiste en la base de datos y devuelve su id."""
        with closing(self._connect()) as conn:
            cur = conn.execute(
                (
                    """
                INSERT INTO chistes ("from", content, need_upload, need_approve, chiste_id)
                VALUES (?, ?, ?, ?, ?)
                """
                ),
                (
                    from_,
                    content,
                    1 if need_upload else 0,
                    1 if need_approve else 0,
                    chiste_id,
                ),
            )
            conn.commit()
            return int(cur.lastrowid)

    def get_chistes_to_upload(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Devuelve chistes pendientes de subir a la API externa."""
        with closing(self._connect()) as conn:
            cur = conn.execute(
                'SELECT id, "from", content, chiste_id FROM chistes WHERE need_upload = 1 LIMIT ?',
                (limit,),
            )
            return [dict(row) for row in cur.fetchall()]

    def mark_chistes_uploaded(self, ids: Iterable[int]) -> None:
        """Marca una lista de chistes como ya subidos (need_upload = 0)."""
        ids_list = list(ids)
        if not ids_list:
            return
        placeholders = ','.join(['?'] * len(ids_list))
        with closing(self._connect()) as conn:
            conn.execute(
                f'UPDATE chistes SET need_upload = 0 WHERE id IN ({placeholders})',
                tuple(ids_list),
            )
            conn.commit()

    def get_last_downloaded_chiste_id(self) -> int:
        """Devuelve el máximo chiste_id descargado de la API externa o 0 si no hay ninguno."""
        with closing(self._connect()) as conn:
            cur = conn.execute('SELECT MAX(chiste_id) AS max_id FROM chistes WHERE chiste_id IS NOT NULL')
            row = cur.fetchone()
            return int(row['max_id']) if row and row['max_id'] is not None else 0

    def bulk_insert_api_chistes(self, items: Iterable[Dict[str, Any]]) -> Tuple[int, int]:
        """Inserta un lote de chistes descargados de la API externa ignorando los que ya existan por chiste_id.

        Devuelve una tupla (insertados, ignorados).
        """
        inserted = 0
        ignored = 0
        with closing(self._connect()) as conn:
            for item in items:
                try:
                    chiste_id = item.get('id')
                    content = item.get('content') or item.get('text') or ''
                    from_ = item.get('from') or item.get('author') or 'API'
                    if not content or chiste_id is None:
                        ignored += 1
                        continue
                    conn.execute(
                        (
                            """
                        INSERT INTO chistes ("from", content, need_upload, need_approve, chiste_id)
                        VALUES (?, ?, 0, 0, ?)
                        ON CONFLICT(chiste_id) DO NOTHING
                        """
                        ),
                        (from_, content, chiste_id),
                    )
                    inserted += 1
                except sqlite3.IntegrityError:
                    ignored += 1
                except Exception:
                    ignored += 1
            conn.commit()
        return inserted, ignored

    # ---------- TRACES (COLA Y RESULTADOS) ----------
    def save_trace(self, from_: Optional[str], to: str, data_raw: Optional[str]) -> int:
        """Inserta un trace directamente como completado ('done')."""
        now = datetime.now().isoformat(timespec='seconds')
        with closing(self._connect()) as conn:
            cur = conn.execute(
                'INSERT INTO traces ("from", "to", data_raw, status, created_at, updated_at) VALUES (?, ?, ?, "done", ?, ?)',
                (from_, to, data_raw, now, now),
            )
            conn.commit()
            return int(cur.lastrowid)

    def enqueue_trace(self, node_id: str) -> int:
        """Encola una petición de traceroute para el nodo indicado."""
        now = datetime.now().isoformat(timespec='seconds')
        with closing(self._connect()) as conn:
            cur = conn.execute(
                'SELECT id FROM traces WHERE "to" = ? AND status = "pending" ORDER BY id ASC LIMIT 1',
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

    def get_next_pending_trace(self, router_identifiers: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
        """Obtiene el trace pendiente más prioritario (routers primero, luego por created_at ASC)."""
        router_idents = [str(r).upper() for r in (router_identifiers or [])]
        with closing(self._connect()) as conn:
            query = """
                SELECT t.id, t."to", t.created_at
                FROM traces t
                LEFT JOIN nodes n ON n.node_id = t."to"
                WHERE t.status = "pending"
                ORDER BY
                    CASE
                        WHEN n.role IN (2, 4, 9)
                          OR UPPER(COALESCE(n.role, '')) IN ('ROUTER', 'ROUTER_LATE', 'REPEATER')
                          OR UPPER(COALESCE(n.short_name, '')) IN ({ro_placeholders})
                          OR UPPER(COALESCE(t."to", '')) IN ({ro_placeholders})
                        THEN 0 ELSE 1
                    END,
                    t.created_at ASC
                LIMIT 1
            """.format(
                ro_placeholders=','.join(['?'] * len(router_idents)) if router_idents else "''"
            )
            params = tuple(router_idents * 2) if router_idents else ()
            cur = conn.execute(query, params)
            row = cur.fetchone()
            return dict(row) if row else None

    def cleanup_stale_pending_traces(self, max_age_minutes: int = 15) -> int:
        """Marca como error trazas que lleven más de max_age_minutes en estado pending sin procesar."""
        with closing(self._connect()) as conn:
            cur = conn.execute(
                """
                UPDATE traces
                SET status = 'error',
                    data_raw = 'Timeout: cola pendiente expirada',
                    updated_at = datetime('now', 'localtime')
                WHERE status = 'pending'
                  AND strftime('%s', 'now', 'localtime') - strftime('%s', created_at) >= ?
                """,
                (int(max_age_minutes) * 60,),
            )
            conn.commit()
            return cur.rowcount

    def mark_trace_done(self, trace_id: int, ok: bool, payload: str, from_: str = 'local') -> None:
        """Marca un trace pendiente como procesado, guardando resultado y sellando updated_at.

        - ok=True -> status='done'
        - ok=False -> status='error'
        - payload debe ser string (ej. JSON)
        """
        when_str = datetime.now().isoformat(timespec='seconds')
        status = 'done' if ok else 'error'
        with closing(self._connect()) as conn:
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
        with closing(self._connect()) as conn:
            conn.execute(sql, tuple(values))
            conn.commit()

    def get_last_trace_updated_at(self) -> Optional[str]:
        """Devuelve el timestamp (ISO) del último trace procesado (updated_at no NULL)."""
        with closing(self._connect()) as conn:
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
        with closing(self._connect()) as conn:
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
        with closing(self._connect()) as conn:
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

        with closing(self._connect()) as conn:
            cur = conn.execute(
                'INSERT INTO agenda (node_id, content, moment) VALUES (?, ?, ?)',
                (node_id, content, moment_str),
            )
            conn.commit()
            return int(cur.lastrowid)

    # ---------- NODES ----------
    def get_node(self, node_id: str) -> Optional[Dict[str, Any]]:
        """Obtiene un nodo por su node_id."""
        with closing(self._connect()) as conn:
            cur = conn.execute(
                """
                SELECT node_id, name, num, short_name, mac_addr, hw_model, role, is_favorite,
                       snr, rssi, public_key, hops, hop_start, uptime, via_mqtt,
                       battery, voltage, last_heard, traces_detected, updated_at
                FROM nodes
                WHERE node_id = ?
                """,
                (node_id,),
            )
            row = cur.fetchone()
            return dict(row) if row else None

    def get_node_by_identifier(self, identifier: str) -> Optional[Dict[str, Any]]:
        """Busca un nodo por node_id, nombre corto o nombre largo (case-insensitive)."""
        if not identifier:
            return None
        with closing(self._connect()) as conn:
            cur = conn.execute(
                """
                SELECT node_id, name, num, short_name, mac_addr, hw_model, role, is_favorite,
                       snr, rssi, public_key, hops, hop_start, uptime, via_mqtt,
                       battery, voltage, last_heard, traces_detected, updated_at
                FROM nodes
                WHERE UPPER(node_id) = UPPER(?)
                   OR UPPER(short_name) = UPPER(?)
                   OR UPPER(name) = UPPER(?)
                ORDER BY updated_at DESC LIMIT 1
                """,
                (identifier, identifier, identifier),
            )
            row = cur.fetchone()
            return dict(row) if row else None

    def get_router_nodes(
        self,
        configured_identifiers: Optional[List[str]] = None,
        max_hops: Optional[int] = 2,
        require_successful_trace_for_auto: bool = True,
    ) -> List[Dict[str, Any]]:
        """Obtiene nodos routers explícitos (configurados) y auto-detectados por role.

        - Los configurados explícitamente en configured_identifiers se devuelven SIEMPRE.
        - Los auto-detectados por role (ROUTER, ROUTER_LATE, REPEATER) solo se devuelven
          si han respondido con éxito a un traceroute en algún momento (status = 'done')
          cuando require_successful_trace_for_auto es True.
        """
        found_nodes: List[Dict[str, Any]] = []
        seen_ids = set()

        # 1. Buscar los configurados explícitamente (se vigilan y devuelven siempre)
        if configured_identifiers:
            for ident in configured_identifiers:
                node = self.get_node_by_identifier(ident)
                if node:
                    nid = node.get('node_id')
                    if nid and nid not in seen_ids:
                        seen_ids.add(nid)
                        found_nodes.append(node)
                else:
                    # Nodo configurado pero no registrado aún
                    found_nodes.append({'identifier': ident, 'offline': True})

        # 2. Auto-detectar nodos con role ROUTER, ROUTER_LATE o REPEATER
        with closing(self._connect()) as conn:
            query = """
                SELECT node_id, name, num, short_name, mac_addr, hw_model, role, is_favorite,
                       snr, rssi, public_key, hops, hop_start, uptime, via_mqtt, battery, voltage,
                       last_heard, created_at, updated_at
                FROM nodes
                WHERE (
                    role IN (2, 4, 9)
                 OR UPPER(COALESCE(role, '')) IN ('ROUTER', 'ROUTER_LATE', 'REPEATER')
                )
                AND COALESCE(via_mqtt, 0) = 0
            """
            params: List[Any] = []

            if require_successful_trace_for_auto:
                query += """
                AND EXISTS (
                    SELECT 1 FROM traces t
                    WHERE (t."to" = nodes.node_id OR UPPER(COALESCE(t.to_name_short, '')) = UPPER(nodes.short_name) OR UPPER(COALESCE(t.to_name, '')) = UPPER(nodes.name))
                      AND t.status = 'done'
                )
                """

            if max_hops is not None:
                query += " AND (hops IS NULL OR hops <= ?)"
                params.append(int(max_hops))

            query += " ORDER BY updated_at DESC LIMIT 30"

            cur = conn.execute(query, tuple(params))
            for row in cur.fetchall():
                node_dict = dict(row)
                nid = node_dict.get('node_id')
                if nid and nid not in seen_ids:
                    seen_ids.add(nid)
                    found_nodes.append(node_dict)

        return found_nodes

    def create_node_if_not_exists(self, node_id: str, data: Optional[Dict[str, Any]] = None) -> None:
        """Crea un nodo si no existe. Ignora si ya existe o si el ID es inválido."""
        if not node_id or str(node_id).strip() in ("", "None", "null", "Desconocido", "none"):
            return
        clean_id = str(node_id).strip()
        now = datetime.now().isoformat(timespec="seconds")
        with closing(self._connect()) as conn:
            conn.execute(
                'INSERT OR IGNORE INTO nodes (node_id, created_at, updated_at) VALUES (?, ?, ?)',
                (clean_id, now, now),
            )
            conn.commit()

        # Si se pasa data, realizar una actualización inicial
        if data:
            self.update_node(clean_id, data)

    def update_node(self, node_id: str, data: Dict[str, Any]) -> None:
        """Actualiza un nodo por node_id con las claves proporcionadas en data."""
        if not node_id or str(node_id).strip() in ("", "None", "null", "Desconocido", "none") or not data:
            return
        clean_id = str(node_id).strip()

        allowed = {
            "name",
            "num",
            "short_name",
            "mac_addr",
            "hw_model",
            "role",
            "is_favorite",
            "snr",
            "rssi",
            "public_key",
            "hops",
            "hop_start",
            "uptime",
            "via_mqtt",
            "battery",
            "voltage",
            "last_heard",
            "traces_detected",
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
        values.append(clean_id)

        set_clause = ", ".join(fields + ["updated_at = ?"])  # siempre actualizar updated_at

        with closing(self._connect()) as conn:
            conn.execute(
                f"UPDATE nodes SET {set_clause} WHERE node_id = ?",
                tuple(values),
            )
            conn.commit()

    def increment_node_traces_detected(self, node_id: str) -> int:
        """Incrementa en 1 el contador de traceroutes emitidos y detectados por este nodo."""
        if not node_id or str(node_id).strip() in ("", "None", "null", "Desconocido", "none"):
            return 0
        clean_id = str(node_id).strip()
        self.create_node_if_not_exists(clean_id)
        when_str = datetime.now().isoformat(timespec="seconds")
        with closing(self._connect()) as conn:
            conn.execute(
                "UPDATE nodes SET traces_detected = COALESCE(traces_detected, 0) + 1, updated_at = ? WHERE node_id = ?",
                (when_str, clean_id),
            )
            conn.commit()
            cur = conn.execute("SELECT traces_detected FROM nodes WHERE node_id = ?", (clean_id,))
            row = cur.fetchone()
            return int(row["traces_detected"]) if row and row["traces_detected"] is not None else 1

    # ---------- TASKS CONTROL ----------
    def get_task_last_run(self, name: str) -> Optional[str]:
        with closing(self._connect()) as conn:
            cur = conn.execute('SELECT last_run_at FROM tasks_control WHERE name = ?', (name,))
            row = cur.fetchone()
            return row['last_run_at'] if row and row['last_run_at'] else None

    def set_task_run(self, name: str, when: Optional[datetime] = None, extra: Optional[str] = None) -> None:
        when_str = (when or datetime.now()).isoformat(timespec='seconds')
        with closing(self._connect()) as conn:
            conn.execute(
                (
                    """
                INSERT INTO tasks_control (name, last_run_at, extra)
                VALUES (?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    last_run_at = excluded.last_run_at,
                    extra = excluded.extra
                """
                ),
                (name, when_str, extra),
            )
            conn.commit()

    def get_latest_trace_route_info(
        self,
        identifier: str,
        base_identifiers: Optional[List[str]] = None,
    ) -> Optional[dict]:
        """Obtiene información detallada de la ruta del último trace exitoso hacia identifier.

        Retorna un dict con:
        - 'hops': saltos exteriores entre la base y el destino (0 para directo, 1 para 1 repetidor intermedio, etc.)
        - 'snrs': lista de floats con el SNR de cada tramo exterior (desde la base hacia el destino)
        - 'intermediates': lista de identificadores/nombres de repetidores intermedios
        - 'snr_text': cadena formateada, ej. '5.2dB' o '9.0dB, 9.3dB'
        """
        if not identifier:
            return None
        import re

        with closing(self._connect()) as conn:
            cur = conn.execute(
                """
                SELECT * FROM traces
                WHERE ("to" = ? OR UPPER(COALESCE(to_name_short, '')) = UPPER(?) OR UPPER(COALESCE(to_name, '')) = UPPER(?))
                  AND status = 'done'
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (identifier, identifier, identifier),
            )
            row = cur.fetchone()
            if not row:
                return None

            row_dict = dict(row)
            data_raw = row_dict.get("data_raw") or ""

            base_set = {str(b).upper() for b in (base_identifiers or ["RAU0"])}
            bot_set = {"LOCAL", "!BOT", "BOT", ""}

            def parse_part(part: str):
                m = re.search(r"(!?[0-9a-fA-F]{6,8}|![0-9a-fA-F]+)", part)
                node = m.group(1) if m else ""
                if node and not node.startswith("!"):
                    node = "!" + node
                m2 = re.search(r"\(([-+]?\d+(?:\.\d+)?)\s*dB\)", part)
                snr = float(m2.group(1)) if m2 else None
                return node.upper(), snr

            lines = [l.strip() for l in data_raw.splitlines() if l.strip()]

            # Intento 1: Ruta de vuelta (Route traced back to us)
            ret_line = None
            for i, l in enumerate(lines):
                if l.lower().startswith("route traced back to us"):
                    if i + 1 < len(lines):
                        ret_line = lines[i + 1]
                    break

            if ret_line:
                parts = [p.strip() for p in ret_line.split("-->")]
                parsed = [parse_part(p) for p in parts]
                if len(parsed) >= 2:
                    # El último elemento es siempre nuestro nodo local receptor (Bot)
                    clean_path = parsed[:-1]
                    reversed_path = clean_path[::-1]
                    def resolve_names(n_list):
                        out_names = []
                        for n_id in n_list:
                            nr = conn.execute("SELECT short_name, name FROM nodes WHERE UPPER(node_id) = UPPER(?) OR UPPER(short_name) = UPPER(?) LIMIT 1", (n_id, n_id)).fetchone()
                            if nr and nr["short_name"]:
                                out_names.append(nr["short_name"])
                            elif nr and nr["name"]:
                                out_names.append(nr["name"])
                            else:
                                out_names.append(n_id)
                        return out_names

                    snrs = [item[1] for item in reversed_path if item[1] is not None]
                    intermediate_nodes = resolve_names([item[0] for item in reversed_path[1:-1]])
                    hops = len(intermediate_nodes)
                    snr_text = ", ".join(f"{s:.1f}dB" for s in snrs) if snrs else None
                    return {
                        "hops": hops,
                        "snrs": snrs,
                        "intermediates": intermediate_nodes,
                        "snr_text": snr_text,
                    }

            # Intento 2: Ruta de ida (Route traced towards destination)
            fwd_line = None
            for i, l in enumerate(lines):
                if l.lower().startswith("route traced towards destination"):
                    if i + 1 < len(lines):
                        fwd_line = lines[i + 1]
                    break

            if fwd_line:
                parts = [p.strip() for p in fwd_line.split("-->")]
                parsed = [parse_part(p) for p in parts]
                if len(parsed) >= 2:
                    # El primer elemento es siempre nuestro nodo local emisor (Bot)
                    # parsed[1] es la base/antena
                    clean_path = parsed[1:]
                    # Tramo exterior: desde la base hasta el destino
                    snrs = [item[1] for item in clean_path[1:] if item[1] is not None]
                    intermediate_nodes = resolve_names([item[0] for item in clean_path[1:-1]])
                    hops = len(intermediate_nodes)
                    snr_text = ", ".join(f"{s:.1f}dB" for s in snrs) if snrs else None
                    return {
                        "hops": hops,
                        "snrs": snrs,
                        "intermediates": intermediate_nodes,
                        "snr_text": snr_text,
                    }

            # Fallback: columnas estructuradas de BD
            hops_count = row_dict.get("hops") or 0
            hops_back_count = row_dict.get("hops_back") or 0

            if row_dict.get("hop_return1_snr") is not None:
                ret1_id = (row_dict.get("hop_return1_id") or "").upper()
                ret1_short = (row_dict.get("hop_return1_name_short") or "").upper()
                if ret1_id not in bot_set and ret1_short not in bot_set:
                    val = row_dict.get("hop_return1_snr")
                    return {"hops": max(0, hops_back_count - 1), "snrs": [val], "intermediates": [], "snr_text": f"{val:.1f}dB"}
                elif hops_back_count <= 1:
                    val = row_dict.get("hop_return1_snr")
                    return {"hops": 0, "snrs": [val], "intermediates": [], "snr_text": f"{val:.1f}dB"}

            if row_dict.get("hop2_snr") is not None:
                val = row_dict.get("hop2_snr")
                return {"hops": max(0, hops_count - 1), "snrs": [val], "intermediates": [], "snr_text": f"{val:.1f}dB"}

            if hops_count <= 1 and row_dict.get("hop1_snr") is not None:
                hop1_id = (row_dict.get("hop1_id") or "").upper()
                hop1_short = (row_dict.get("hop1_name_short") or "").upper()
                if hop1_id not in base_set and hop1_short not in base_set:
                    val = row_dict.get("hop1_snr")
                    return {"hops": 0, "snrs": [val], "intermediates": [], "snr_text": f"{val:.1f}dB"}

            return None

    def get_latest_trace_snr(self, identifier: str, base_identifiers: Optional[List[str]] = None) -> Optional[float]:
        """Obtiene el SNR del enlace exterior con la base (o directo) desde el último trace exitoso."""
        info = self.get_latest_trace_route_info(identifier, base_identifiers)
        if info and info.get("snrs"):
            return info["snrs"][0]
        return None

    # ---------- NODE TRACE CONTROL ----------
    def get_next_node_to_trace(
        self,
        *,
        hops_limit: int = 2,
        reload_hours: int = 120,
        router_reload_hours: int = 24,
        router_max_hops: int = 2,
        router_retry_short_hours: int = 1,
        router_max_retries: int = 5,
        router_retry_long_hours: int = 24,
        retry_hours: int = 24,
        max_inactive_days: int = 7,
        router_start_hour: int = 6,
        router_identifiers: Optional[List[str]] = None,
    ) -> Optional[str]:
        """Devuelve el próximo node_id candidato para traceroute.

        Compensación de saltos: Se añade +1 salto al límite configurado para contemplar
        el salto local Bot <-> RAU0 (ej. hops_limit=2 equivale a <=3 saltos brutos desde el bot).

        Filtro de actividad: Descarta nodos sin señales recientes (>7 días) o que se hayan alejado.

        Prioridad 1: Nodos routers cercanos (en router_identifiers o con role ROUTER/ROUTER_LATE/REPEATER)
                    con hops <= router_max_hops + 1 (<=3 brutos).
                    - Se ejecutan preferentemente a partir de router_start_hour (06:00 AM).
                    - Éxito previo ('done'): re-trazar cada router_reload_hours (24h).
                    - Fallo previo ('error') con < router_max_retries (5): reintentar cada router_retry_short_hours (1h).
                    - Fallo previo ('error') con >= router_max_retries (5): enfriamiento de router_retry_long_hours (24h).
        Prioridad 2: Nodos normales y routers más lejanos (hops <= hops_limit + 1, no MQTT, activos en 7 días)
                    - Éxito previo: cada reload_hours (120h = 5 días).
                    - Fallo puntual: reintento tras retry_hours (24h).
                    - Tras 5 fallos consecutivos sin respuesta, se descarta definitivamente hasta recibir un update en 'nodes'.
        """
        router_idents = [str(r) for r in (router_identifiers or [])]
        eff_router_hops = int(router_max_hops) + 1
        eff_hops_limit = int(hops_limit) + 1
        inactive_sec = int(max_inactive_days) * 86400
        current_hour = datetime.now().hour
        router_routine_allowed = (current_hour >= int(router_start_hour))

        with closing(self._connect()) as conn:
            # 1. Comprobar primero si algún ROUTER CERCANO (<= router_max_hops + 1) necesita traceroute (prioridad 1)
            query_routers = '''
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
                ), consecutive_errors AS (
                    SELECT t1."to" AS node_id, COUNT(*) AS err_count
                    FROM traces t1
                    WHERE t1.status = 'error'
                      AND t1.id > COALESCE(
                          (SELECT MAX(t2.id) FROM traces t2 WHERE t2."to" = t1."to" AND t2.status = 'done'),
                          0
                      )
                    GROUP BY t1."to"
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
                LEFT JOIN consecutive_errors ce ON ce.node_id = n.node_id
                LEFT JOIN pend p ON p.node_id = n.node_id
                WHERE COALESCE(n.via_mqtt, 0) = 0
                  AND (n.hops IS NULL OR n.hops <= ?)
                  AND (
                      (n.last_heard IS NOT NULL AND strftime('%s','now','localtime') - n.last_heard <= ?)
                   OR (n.last_heard IS NULL AND strftime('%s','now','localtime') - strftime('%s', n.updated_at) <= ?)
                  )
                  AND COALESCE(p.pendings, 0) = 0
                  AND (
                      n.role IN (2, 4, 9)
                   OR UPPER(COALESCE(n.role, '')) IN ('ROUTER', 'ROUTER_LATE', 'REPEATER')
                   OR UPPER(COALESCE(n.short_name, '')) IN ({ro_placeholders})
                   OR UPPER(COALESCE(n.node_id, '')) IN ({ro_placeholders})
                  )
                  AND (
                        (lp.last_updated IS NULL AND ? = 1)
                     OR (ls.last_status = 'done' AND ? = 1 AND strftime('%s','now','localtime') - strftime('%s', lp.last_updated) >= ?)
                     OR (ls.last_status = 'error' AND COALESCE(ce.err_count, 0) < ?  AND strftime('%s','now','localtime') - strftime('%s', lp.last_updated) >= ?)
                     OR (ls.last_status = 'error' AND COALESCE(ce.err_count, 0) >= ? AND strftime('%s','now','localtime') - strftime('%s', lp.last_updated) >= ?)
                  )
                ORDER BY lp.last_updated ASC, n.updated_at DESC
                LIMIT 1
            '''.format(
                ro_placeholders=','.join(['?'] * len(router_idents)) if router_idents else "''"
            )

            allow_flag = 1 if router_routine_allowed else 0
            params_routers = tuple(
                [eff_router_hops, inactive_sec, inactive_sec] + [r.upper() for r in router_idents] * 2 + [
                    allow_flag,
                    allow_flag,
                    int(router_reload_hours) * 3600,
                    int(router_max_retries),
                    int(router_retry_short_hours) * 3600,
                    int(router_max_retries),
                    int(router_retry_long_hours) * 3600,
                ]
            ) if router_idents else (
                eff_router_hops,
                inactive_sec,
                inactive_sec,
                allow_flag,
                allow_flag,
                int(router_reload_hours) * 3600,
                int(router_max_retries),
                int(router_retry_short_hours) * 3600,
                int(router_max_retries),
                int(router_retry_long_hours) * 3600,
            )

            cur = conn.execute(query_routers, params_routers)
            row = cur.fetchone()
            if row:
                return row['node_id']

            # 2. Si ningún router cercano necesita trace, seleccionar nodo normal o router lejano cumpliendo reload_hours (120h = 5 días) y activo en 7 días
            query_clients = '''
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
                ), consecutive_errors AS (
                    SELECT t1."to" AS node_id, COUNT(*) AS err_count, MAX(t1.updated_at) AS last_err_time
                    FROM traces t1
                    WHERE t1.status = 'error'
                      AND t1.id > COALESCE(
                          (SELECT MAX(t2.id) FROM traces t2 WHERE t2."to" = t1."to" AND t2.status = 'done'),
                          0
                      )
                    GROUP BY t1."to"
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
                LEFT JOIN consecutive_errors ce ON ce.node_id = n.node_id
                LEFT JOIN pend p ON p.node_id = n.node_id
                WHERE COALESCE(n.via_mqtt, 0) = 0
                  AND (n.hops IS NULL OR n.hops <= ?)
                  AND (
                      (n.last_heard IS NOT NULL AND strftime('%s','now','localtime') - n.last_heard <= ?)
                   OR (n.last_heard IS NULL AND strftime('%s','now','localtime') - strftime('%s', n.updated_at) <= ?)
                  )
                  AND COALESCE(p.pendings, 0) = 0
                  AND NOT (
                      (
                          n.role IN (2, 4, 9)
                       OR UPPER(COALESCE(n.role, '')) IN ('ROUTER', 'ROUTER_LATE', 'REPEATER')
                       OR UPPER(COALESCE(n.short_name, '')) IN ({ro_placeholders})
                       OR UPPER(COALESCE(n.node_id, '')) IN ({ro_placeholders})
                      )
                      AND (n.hops IS NULL OR n.hops <= ?)
                  )
                  AND (
                      COALESCE(ce.err_count, 0) < 5
                   OR (
                       (n.last_heard IS NOT NULL AND n.last_heard > strftime('%s', ce.last_err_time))
                    OR (strftime('%s', n.updated_at) > strftime('%s', ce.last_err_time))
                   )
                  )
                  AND (
                        lp.last_updated IS NULL
                     OR (
                          (ls.last_status = 'done'  AND strftime('%s','now','localtime') - strftime('%s', lp.last_updated) >= ?)
                       OR (ls.last_status = 'error' AND strftime('%s','now','localtime') - strftime('%s', lp.last_updated) >= ?)
                        )
                  )
                ORDER BY n.updated_at DESC
                LIMIT 1
            '''.format(
                ro_placeholders=','.join(['?'] * len(router_idents)) if router_idents else "''"
            )

            params_clients = tuple(
                [eff_hops_limit, inactive_sec, inactive_sec] + [r.upper() for r in router_idents] * 2 + [
                    eff_router_hops,
                    int(reload_hours) * 3600,
                    int(retry_hours) * 3600,
                ]
            ) if router_idents else (
                eff_hops_limit,
                inactive_sec,
                inactive_sec,
                eff_router_hops,
                int(reload_hours) * 3600,
                int(retry_hours) * 3600,
            )

            cur = conn.execute(query_clients, params_clients)
            row = cur.fetchone()
            return row['node_id'] if row else None

    def is_router_node(self, node_id: str, router_identifiers: Optional[List[str]] = None) -> bool:
        """Determina si un nodo es un router/repetidor de la red."""
        if not node_id:
            return False
        router_idents = [str(r).upper() for r in (router_identifiers or [])]
        node = self.get_node(node_id)
        if not node:
            return str(node_id).upper() in router_idents

        role = node.get('role')
        if role in (2, 4, 9) or str(role).upper() in ('ROUTER', 'ROUTER_LATE', 'REPEATER'):
            return True

        s_name = str(node.get('short_name') or '').upper()
        n_id = str(node.get('node_id') or '').upper()
        return s_name in router_idents or n_id in router_idents

    # ---------- AEMET ALERTS ----------
    def _hash_text(self, text: str) -> str:
        return hashlib.sha256(text.encode('utf-8')).hexdigest()

    def aemet_insert_alert(self, province: Optional[str], data_raw: str, message: Optional[str] = None) -> Optional[int]:
        """Inserta una alerta AEMET si no existe (deduplicada por hash). Devuelve id o None si ya existía.

        data_raw: texto del "mensaje de alerta" (ES) extraído del XML (no el XML completo).
        message: texto a publicar (ES) ya preparado para mostrarse.
        """
        # Sanitizar ambos campos y calcular hash sobre el mensaje prioritariamente
        data_raw_s = sanitize_text(data_raw)
        message_s = sanitize_text(message) if message is not None else None
        basis = message_s if (message_s and len(message_s) > 0) else data_raw_s
        if not basis:
            return None
        h = self._hash_text(basis)
        now = datetime.now().isoformat(timespec='seconds')
        with closing(self._connect()) as conn:
            try:
                cur = conn.execute(
                    'INSERT INTO aemet (province, data_raw, message, data_hash, created_at, published) VALUES (?, ?, ?, ?, ?, 0)',
                    (province, data_raw_s, message_s, h, now),
                )
                conn.commit()
                return int(cur.lastrowid)
            except sqlite3.IntegrityError:
                # Duplicada por hash
                return None

    def aemet_bulk_insert(self, province: Optional[str], items: Iterable[Any]) -> Tuple[int, int]:
        """Inserta múltiples alertas.

        - items suelen ser cadenas XML CAP (texto). También se ignoran JSON de error.
        - Extrae el bloque ES y guarda:
          - data_raw: mensaje de alerta (ES) breve (headline + descripción)
          - message: texto a publicar (ES) más completo
        Devuelve (insertadas, ignoradas).
        """
        inserted = 0
        ignored = 0
        for it in items:
            # 1) Filtrar respuestas JSON de error de AEMET (p.ej., {"estado":404,...})
            try:
                import json as _json
                candidate_dict = None
                if isinstance(it, str):
                    s = (it or '').strip()
                    if s.startswith('{') and s.endswith('}'):
                        try:
                            candidate_dict = _json.loads(s)
                        except Exception:
                            candidate_dict = None
                    else:
                        candidate_dict = None
                elif isinstance(it, dict):
                    candidate_dict = it
                else:
                    candidate_dict = None

                if isinstance(candidate_dict, dict):
                    estado = candidate_dict.get('estado')
                    if estado is not None and int(str(estado)) != 200:
                        ignored += 1
                        continue
            except Exception:
                pass

            # 2) Obtener XML como texto
            if isinstance(it, str):
                xml_text = it
            else:
                try:
                    xml_text = _json.dumps(it, ensure_ascii=False)
                except Exception:
                    xml_text = str(it)

            # 3) Parsear ES y construir mensajes; si falla, ignorar (nunca almacenar XML)
            alert_text, publish_text = self._parse_cap_es(xml_text)
            if not alert_text and not publish_text:
                ignored += 1
                continue

            # Sanitizar textos y validar que no contengan marcas XML
            alert_text_s = sanitize_text(alert_text or '')
            publish_text_s = sanitize_text(publish_text or alert_text_s)
            if not alert_text_s and not publish_text_s:
                ignored += 1
                continue

            if self.aemet_insert_alert(province, alert_text_s, publish_text_s) is not None:
                inserted += 1
            else:
                ignored += 1
        return inserted, ignored

    @staticmethod
    def _parse_cap_es(xml_text: str) -> Tuple[Optional[str], Optional[str]]:
        """Extrae información en español del XML CAP y construye dos textos:
        - alert_text: mensaje breve (headline + descripción) para almacenar en data_raw
        - publish_text: texto para publicar (evento, nivel, área, horarios, descripción, url)
        Devuelve (alert_text, publish_text). Si falla, devuelve (None, None).
        """
        try:
            import xml.etree.ElementTree as ET
            from datetime import datetime

            # Manejo de espacios de nombres CAP 1.2
            ns = {'cap': 'urn:oasis:names:tc:emergency:cap:1.2'}
            root = ET.fromstring(xml_text)

            # Buscar bloque <info> con idioma español
            infos = root.findall('cap:info', ns)
            info_es = None
            for info in infos:
                lang = (info.findtext('cap:language', default='', namespaces=ns) or '').lower()
                if lang.startswith('es'):
                    info_es = info
                    break
            if info_es is None:
                info_es = infos[0] if infos else None
            if info_es is None:
                return None, None

            # Campos clave
            event = (info_es.findtext('cap:event', default='', namespaces=ns) or '').strip()
            headline = (info_es.findtext('cap:headline', default='', namespaces=ns) or '').strip()
            description = (info_es.findtext('cap:description', default='', namespaces=ns) or '').strip()
            instruction = (info_es.findtext('cap:instruction', default='', namespaces=ns) or '').strip()
            onset = (info_es.findtext('cap:onset', default='', namespaces=ns) or '').strip()
            expires = (info_es.findtext('cap:expires', default='', namespaces=ns) or '').strip()
            sender_name = (info_es.findtext('cap:senderName', default='', namespaces=ns) or '').strip()
            web = (info_es.findtext('cap:web', default='', namespaces=ns) or '').strip()

            # Área
            area_el = info_es.find('cap:area', ns)
            area = ''
            if area_el is not None:
                area = (area_el.findtext('cap:areaDesc', default='', namespaces=ns) or '').strip()

            # Parámetros AEMET
            nivel = ''
            prob = ''
            fenomeno = ''
            for par in info_es.findall('cap:parameter', ns):
                vname = (par.findtext('cap:valueName', default='', namespaces=ns) or '').strip()
                v = (par.findtext('cap:value', default='', namespaces=ns) or '').strip()
                vn = vname.lower()
                if 'nivel' in vn:
                    nivel = v
                elif 'probabilidad' in vn:
                    prob = v
                elif 'fenomeno' in vn or 'fenómeno' in vn:
                    fenomeno = v

            # Descartar avisos de nivel verde (sin riesgo meteorológico / baseline de AEMET)
            if nivel.lower() == 'verde' or 'nivel verde' in event.lower() or 'nivel verde' in headline.lower():
                return None, None

            # Componer textos
            parts_short: list[str] = []
            if headline:
                parts_short.append(headline)
            else:
                base = event
                if nivel:
                    base = f"{event} de nivel {nivel}" if event else f"Nivel {nivel}"
                if area:
                    base = f"{base}. {area}" if base else area
                parts_short.append(base)
            if description:
                parts_short.append(description)
            alert_text = ' '.join(' '.join(parts_short).split())

            # Fecha/hora: mantener tal cual (CAP incluye zona); opcionalmente formatear HH:MM
            def _fmt_time(t: str) -> str:
                try:
                    # Admite formatos con offset o 'Z' o '+01:00'
                    # Tomamos solo fecha y hora local textual
                    return t.replace('T', ' ').replace('Z', '+00:00')
                except Exception:
                    return t

            parts_pub: list[str] = []
            if event:
                if nivel:
                    parts_pub.append(f"{event} (nivel {nivel})")
                else:
                    parts_pub.append(event)
            elif headline:
                parts_pub.append(headline)
            if area:
                parts_pub.append(area)
            # Ventana temporal
            if onset or expires:
                if onset and expires:
                    parts_pub.append(f"De { _fmt_time(onset) } a { _fmt_time(expires) }")
                elif onset:
                    parts_pub.append(f"Desde { _fmt_time(onset) }")
                elif expires:
                    parts_pub.append(f"Hasta { _fmt_time(expires) }")
            if prob:
                parts_pub.append(f"Prob.: {prob}")
            if description:
                parts_pub.append(description)
            if instruction:
                parts_pub.append(instruction)
            if web and 'aemet' in web.lower():
                parts_pub.append(web)

            publish_text = ' '.join(' '.join(parts_pub).split())
            return alert_text, publish_text
        except Exception:
            return None, None

    def aemet_get_next_unpublished(self) -> Optional[Dict[str, Any]]:
        with closing(self._connect()) as conn:
            cur = conn.execute(
                'SELECT id, province, data_raw, message, created_at FROM aemet WHERE published = 0 ORDER BY created_at ASC LIMIT 1'
            )
            row = cur.fetchone()
            return dict(row) if row else None

    def aemet_mark_published(self, alert_id: int) -> None:
        now = datetime.now().isoformat(timespec='seconds')
        with closing(self._connect()) as conn:
            conn.execute('UPDATE aemet SET published = 1, published_at = ? WHERE id = ?', (now, alert_id))
            conn.commit()

    # ---------- AEMET LEGACY FIX ----------
    def aemet_fix_legacy_rows(self, limit: int = 500) -> Tuple[int, int, int]:
        """Convierte filas antiguas que almacenaron XML crudo a texto en español.

        Busca filas donde data_raw o message parecen contener XML ('<' al inicio o '<?xml').
        Intenta parsear y actualizar data_raw/message con texto saneado y recomputa data_hash.
        Si al actualizar se produce colisión de hash con otra fila existente, elimina la fila actual (duplicado).

        Devuelve (procesadas, actualizadas, eliminadas).
        """
        processed = 0
        updated = 0
        deleted = 0
        with closing(self._connect()) as conn:
            rows = conn.execute(
                """
                SELECT id, province, data_raw, message
                FROM aemet
                WHERE (data_raw LIKE '<%' OR data_raw LIKE '<?xml%' OR (message IS NOT NULL AND message LIKE '<%'))
                ORDER BY id ASC
                LIMIT ?
                """,
                (int(limit),),
            ).fetchall()

            for r in rows:
                processed += 1
                rid = int(r['id'])
                xml_candidate = r['data_raw'] or r['message'] or ''
                alert_text, publish_text = self._parse_cap_es(xml_candidate)
                if not alert_text and not publish_text:
                    # No se pudo parsear; intentar eliminar marcas XML básicas y continuar
                    import re
                    txt = re.sub(r'<[^>]+>', ' ', xml_candidate)
                    txt = sanitize_text(txt)
                    if not txt:
                        continue
                    alert_s = txt
                    pub_s = txt
                else:
                    alert_s = sanitize_text(alert_text or '')
                    pub_s = sanitize_text(publish_text or alert_s)

                if not alert_s and not pub_s:
                    continue

                basis = pub_s if pub_s else alert_s
                new_hash = self._hash_text(basis)

                try:
                    conn.execute(
                        'UPDATE aemet SET data_raw = ?, message = ?, data_hash = ? WHERE id = ?',
                        (alert_s, pub_s, new_hash, rid),
                    )
                    conn.commit()
                    updated += 1
                except sqlite3.IntegrityError:
                    # Duplicado tras normalizar: eliminar esta fila
                    conn.execute('DELETE FROM aemet WHERE id = ?', (rid,))
                    conn.commit()
                    deleted += 1

        return processed, updated, deleted

    # ---------- AEMET WEATHER (clima histórico) ----------
    def aemet_weather_insert(
        self,
        *,
        scope: str,
        content: str,
        province: Optional[str] = None,
        province_code: Optional[str] = None,
        city: Optional[str] = None,
        city_code: Optional[str] = None,
        day: str = 'hoy',
        data_raw: Optional[str] = None,
    ) -> Optional[int]:
        """Inserta un registro de clima descargado (histórico). Devuelve id o None.

        - scope: 'province' (texto general de provincia) o 'city' (municipio).
        - content: texto ya saneado y listo para mostrar por el comando /weather.
        """
        content_s = sanitize_text(content)
        if not content_s:
            return None
        now = datetime.now().isoformat(timespec='seconds')
        with closing(self._connect()) as conn:
            cur = conn.execute(
                'INSERT INTO aemet_weather (scope, province, province_code, city, city_code, day, content, data_raw, created_at) '
                'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
                (scope, province, province_code, city, city_code, day, content_s, data_raw, now),
            )
            conn.commit()
            return int(cur.lastrowid)

    def aemet_weather_get_latest(
        self,
        scope: Optional[str] = None,
        province_code: Optional[str] = None,
        province: Optional[str] = None,
        day: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Devuelve el último registro de clima descargado o None.

        Si se indica `scope` ('province' | 'city' | 'forecast'), filtra por él.
        Si se indica `province_code` o `province`, filtra por esa provincia.
        Si se indica `day` ('hoy' | 'manana'), filtra por ese día.
        Sin scope, devuelve el más reciente independientemente del tipo, pero
        excluye los de previsión multi-día ('forecast') para no mezclarlos con
        el tiempo actual de /weather.
        """
        with closing(self._connect()) as conn:
            query = "SELECT id, scope, province, province_code, city, city_code, day, content, created_at FROM aemet_weather WHERE "
            params = []
            conditions = []

            if scope:
                conditions.append("scope = ?")
                params.append(scope)
            else:
                conditions.append("scope != 'forecast'")

            if province_code:
                conditions.append("province_code = ?")
                params.append(str(province_code))
            elif province:
                conditions.append("(province LIKE ? OR province_code = ?)")
                params.extend([f"%{province}%", str(province)])

            if day:
                conditions.append("day = ?")
                params.append(str(day))

            query += " AND ".join(conditions) + " ORDER BY created_at DESC, id DESC LIMIT 1"

            cur = conn.execute(query, tuple(params))
            row = cur.fetchone()
            if row:
                return dict(row)

            # Fallback si no había para ese día específico pero sí para esa provincia
            if day and (province_code or province):
                query_fallback = "SELECT id, scope, province, province_code, city, city_code, day, content, created_at FROM aemet_weather WHERE "
                f_params = []
                f_conds = ["scope != 'forecast'"]
                if province_code:
                    f_conds.append("province_code = ?")
                    f_params.append(str(province_code))
                elif province:
                    f_conds.append("(province LIKE ? OR province_code = ?)")
                    f_params.extend([f"%{province}%", str(province)])
                query_fallback += " AND ".join(f_conds) + " ORDER BY created_at DESC, id DESC LIMIT 1"
                cur = conn.execute(query_fallback, tuple(f_params))
                row = cur.fetchone()
                if row:
                    return dict(row)

            return None

    def aemet_weather_get_all_latest(self) -> List[Dict[str, Any]]:
        """Obtiene los últimos partes meteorológicos de texto por localidad/provincia."""
        with closing(self._connect()) as conn:
            cur = conn.execute(
                """
                SELECT w.id, w.scope, w.province, w.province_code, w.city, w.city_code, w.day, w.content, w.created_at
                FROM aemet_weather w
                INNER JOIN (
                    SELECT COALESCE(city_code, province) AS loc_key, MAX(id) AS max_id
                    FROM aemet_weather
                    GROUP BY COALESCE(city_code, province)
                ) latest ON w.id = latest.max_id
                ORDER BY w.province ASC, w.city ASC
                """
            )
            return [dict(r) for r in cur.fetchall()]

    def aemet_get_recent_alerts(self, limit: int = 3, hours: Optional[int] = 48) -> List[Dict[str, Any]]:
        """Devuelve las alertas AEMET más recientes (para el comando /avisos).

        - limit: número máximo de alertas a devolver.
        - hours: ventana temporal (None = sin límite temporal).
        """
        with closing(self._connect()) as conn:
            if hours is not None:
                threshold = (datetime.now() - timedelta(hours=int(hours))).isoformat(timespec='seconds')
                cur = conn.execute(
                    'SELECT id, province, data_raw, message, created_at FROM aemet '
                    'WHERE created_at >= ? ORDER BY created_at DESC LIMIT ?',
                    (threshold, int(limit)),
                )
            else:
                cur = conn.execute(
                    'SELECT id, province, data_raw, message, created_at FROM aemet '
                    'ORDER BY created_at DESC LIMIT ?',
                    (int(limit),),
                )
            return [dict(r) for r in cur.fetchall()]

    # ---------- AEMET ENRIQUECIDO (DIARIA 7D, HORARIA 24H, MARÍTIMA Y OBSERVACIÓN) ----------
    def aemet_forecast_daily_insert(
        self,
        city_code: str,
        city_name: str,
        province: str,
        data_json: Any,
        summary_3d: Optional[str] = None,
        summary_7d: Optional[str] = None,
    ) -> int:
        """Guarda la predicción multi-día (7 días) de un municipio."""
        payload_str = json.dumps(data_json, ensure_ascii=False) if not isinstance(data_json, str) else data_json
        now_iso = datetime.now().isoformat(timespec='seconds')
        with closing(self._connect()) as conn:
            cur = conn.execute(
                """
                INSERT INTO aemet_forecast_daily (city_code, city_name, province, data_json, summary_3d, summary_7d, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (str(city_code), str(city_name), str(province), payload_str, summary_3d, summary_7d, now_iso),
            )
            conn.commit()
            return int(cur.lastrowid)

    def aemet_forecast_daily_get_latest(self, city_code: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Obtiene la última predicción multi-día."""
        with closing(self._connect()) as conn:
            if city_code:
                cur = conn.execute(
                    "SELECT id, city_code, city_name, province, data_json, summary_3d, summary_7d, created_at "
                    "FROM aemet_forecast_daily WHERE city_code = ? ORDER BY created_at DESC, id DESC LIMIT 1",
                    (str(city_code),),
                )
            else:
                cur = conn.execute(
                    "SELECT id, city_code, city_name, province, data_json, summary_3d, summary_7d, created_at "
                    "FROM aemet_forecast_daily ORDER BY created_at DESC, id DESC LIMIT 1"
                )
            row = cur.fetchone()
            if not row:
                return None
            res = dict(row)
            try:
                res['data'] = json.loads(res.get('data_json') or '{}')
            except Exception:
                res['data'] = {}
            return res

    def aemet_forecast_daily_get_all_latest(self) -> List[Dict[str, Any]]:
        """Obtiene la última predicción multi-día para cada localidad guardada."""
        with closing(self._connect()) as conn:
            cur = conn.execute(
                """
                SELECT f.id, f.city_code, f.city_name, f.province, f.data_json, f.summary_3d, f.summary_7d, f.created_at
                FROM aemet_forecast_daily f
                INNER JOIN (
                    SELECT city_code, MAX(id) AS max_id
                    FROM aemet_forecast_daily
                    GROUP BY city_code
                ) latest ON f.id = latest.max_id
                ORDER BY f.city_name ASC
                """
            )
            results = []
            for row in cur.fetchall():
                res = dict(row)
                try:
                    res['data'] = json.loads(res.get('data_json') or '{}')
                except Exception:
                    res['data'] = {}
                results.append(res)
            return results

    def aemet_forecast_hourly_insert(
        self,
        city_code: str,
        city_name: str,
        province: str,
        data_json: Any,
        summary_24h: Optional[str] = None,
    ) -> int:
        """Guarda la predicción horaria (24-48 horas) de un municipio."""
        payload_str = json.dumps(data_json, ensure_ascii=False) if not isinstance(data_json, str) else data_json
        now_iso = datetime.now().isoformat(timespec='seconds')
        with closing(self._connect()) as conn:
            cur = conn.execute(
                """
                INSERT INTO aemet_forecast_hourly (city_code, city_name, province, data_json, summary_24h, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (str(city_code), str(city_name), str(province), payload_str, summary_24h, now_iso),
            )
            conn.commit()
            return int(cur.lastrowid)

    def aemet_forecast_hourly_get_latest(self, city_code: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Obtiene la última predicción horaria."""
        with closing(self._connect()) as conn:
            if city_code:
                cur = conn.execute(
                    "SELECT id, city_code, city_name, province, data_json, summary_24h, created_at "
                    "FROM aemet_forecast_hourly WHERE city_code = ? ORDER BY created_at DESC, id DESC LIMIT 1",
                    (str(city_code),),
                )
            else:
                cur = conn.execute(
                    "SELECT id, city_code, city_name, province, data_json, summary_24h, created_at "
                    "FROM aemet_forecast_hourly ORDER BY created_at DESC, id DESC LIMIT 1"
                )
            row = cur.fetchone()
            if not row:
                return None
            res = dict(row)
            try:
                res['data'] = json.loads(res.get('data_json') or '{}')
            except Exception:
                res['data'] = {}
            return res

    def aemet_maritime_insert(
        self,
        costa_code: str,
        costa_name: str,
        data_json: Any,
        summary: str,
    ) -> int:
        """Guarda un boletín marítimo costero."""
        payload_str = json.dumps(data_json, ensure_ascii=False) if not isinstance(data_json, str) else data_json
        now_iso = datetime.now().isoformat(timespec='seconds')
        with closing(self._connect()) as conn:
            cur = conn.execute(
                """
                INSERT INTO aemet_maritime (costa_code, costa_name, data_json, summary, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (str(costa_code), str(costa_name), payload_str, str(summary), now_iso),
            )
            conn.commit()
            return int(cur.lastrowid)

    def aemet_maritime_get_latest(self, costa_code: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Obtiene el último boletín marítimo costero."""
        with closing(self._connect()) as conn:
            if costa_code:
                cur = conn.execute(
                    "SELECT id, costa_code, costa_name, data_json, summary, created_at "
                    "FROM aemet_maritime WHERE costa_code = ? ORDER BY created_at DESC, id DESC LIMIT 1",
                    (str(costa_code),),
                )
            else:
                cur = conn.execute(
                    "SELECT id, costa_code, costa_name, data_json, summary, created_at "
                    "FROM aemet_maritime ORDER BY created_at DESC, id DESC LIMIT 1"
                )
            row = cur.fetchone()
            if not row:
                return None
            res = dict(row)
            try:
                res['data'] = json.loads(res.get('data_json') or '{}')
            except Exception:
                res['data'] = {}
            return res

    def aemet_observation_insert(
        self,
        station_id: str,
        station_name: str,
        data_json: Any,
        summary: str,
    ) -> int:
        """Guarda la observación física de una estación meteorológica."""
        payload_str = json.dumps(data_json, ensure_ascii=False) if not isinstance(data_json, str) else data_json
        now_iso = datetime.now().isoformat(timespec='seconds')
        with closing(self._connect()) as conn:
            cur = conn.execute(
                """
                INSERT INTO aemet_observation (station_id, station_name, data_json, summary, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (str(station_id), str(station_name), payload_str, str(summary), now_iso),
            )
            conn.commit()
            return int(cur.lastrowid)

    def aemet_observation_get_latest(self, station_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Obtiene la última observación de estación meteorológica."""
        with closing(self._connect()) as conn:
            if station_id:
                cur = conn.execute(
                    "SELECT id, station_id, station_name, data_json, summary, created_at "
                    "FROM aemet_observation WHERE station_id = ? ORDER BY created_at DESC, id DESC LIMIT 1",
                    (str(station_id),),
                )
            else:
                cur = conn.execute(
                    "SELECT id, station_id, station_name, data_json, summary, created_at "
                    "FROM aemet_observation ORDER BY created_at DESC, id DESC LIMIT 1"
                )
            row = cur.fetchone()
            if not row:
                return None
            res = dict(row)
            try:
                res['data'] = json.loads(res.get('data_json') or '{}')
            except Exception:
                res['data'] = {}
            return res

    # ---------- COMMANDS LOG ----------
    def log_command(
        self,
        *,
        node_id: Optional[str],
        command: Optional[str],
        message: Optional[str] = None,
        parameters: Optional[str] = None,
    ) -> int:
        """Guarda un registro del comando recibido en `commands_sent` y devuelve el id.

        - node_id: id del nodo que envía el comando (puede ser None)
        - command: nombre del comando (sin prefijo / o !), p.ej. 'ping', 'help'
        - message: texto posterior al comando y parámetros
        - parameters: reservado para uso futuro (se almacena tal cual)
        """
        if not command or str(command).strip() in ("", "/", "!", "None", "null"):
            return 0
        clean_node_id = str(node_id).strip() if (node_id and str(node_id).strip() not in ("", "None", "null", "Desconocido")) else None
        clean_cmd = str(command).strip().lstrip("/!").lower()
        when_str = datetime.now().isoformat(timespec='seconds')
        with closing(self._connect()) as conn:
            cur = conn.execute(
                'INSERT INTO commands_sent (node_id, command, parameters, message, created_at) VALUES (?, ?, ?, ?, ?)',
                (clean_node_id, clean_cmd, parameters, message, when_str),
            )
            conn.commit()
            return int(cur.lastrowid)

    # ---------- TIDES (mareas) ----------
    def tides_insert(self, *, location: Optional[str], source: str, approximate: bool,
                     extremes: List[Dict[str, Any]]) -> int:
        """Guarda una predicción de mareas (lista de extremos) como histórico.

        - extremes: lista de dicts con claves time (datetime|str ISO), type, height.
        Se serializa a JSON con las horas en ISO 8601.
        """
        import json
        norm: List[Dict[str, Any]] = []
        for e in extremes or []:
            t = e.get('time')
            t_iso = t.isoformat() if isinstance(t, datetime) else str(t)
            norm.append({'time': t_iso, 'type': e.get('type'), 'height': e.get('height')})
        now = datetime.now().isoformat(timespec='seconds')
        with closing(self._connect()) as conn:
            cur = conn.execute(
                'INSERT INTO tides (location, source, approximate, extremes, created_at) VALUES (?, ?, ?, ?, ?)',
                (location, source, 1 if approximate else 0, json.dumps(norm, ensure_ascii=False), now),
            )
            conn.commit()
            return int(cur.lastrowid)

    def tides_get_latest(self) -> Optional[Dict[str, Any]]:
        """Devuelve la última predicción de mareas (extremos ya parseados) o None."""
        import json
        with closing(self._connect()) as conn:
            cur = conn.execute(
                'SELECT id, location, source, approximate, extremes, created_at '
                'FROM tides ORDER BY created_at DESC, id DESC LIMIT 1'
            )
            row = cur.fetchone()
            if not row:
                return None
            d = dict(row)
            try:
                d['extremes'] = json.loads(d.get('extremes') or '[]')
            except Exception:
                d['extremes'] = []
            d['approximate'] = bool(d.get('approximate'))
            return d

    # ---------- ENCUESTAS ----------
    def encuesta_expire_due(self) -> int:
        """Cierra automáticamente las encuestas activas cuyo ends_at ya pasó.

        Devuelve el número de encuestas cerradas.

        NOTA (punto 2 de la revisión): este método ESCRIBE, por lo que NO debe
        llamarse desde las lecturas (provocaría un UPDATE en cada /encuesta). Se
        invoca solo desde el barrido periódico del cron (run_all). Las lecturas
        calculan el estado efectivo en memoria (ver _row_to_encuesta) sin tocar
        la BD.
        """
        now = datetime.now()
        now_iso = now.isoformat(timespec='seconds')
        with closing(self._connect()) as conn:
            cur = conn.execute(
                "UPDATE encuestas SET status = 'closed', closed_at = ? "
                "WHERE status = 'active' AND ends_at IS NOT NULL AND ends_at <= ?",
                (now_iso, now_iso),
            )
            conn.commit()
            return cur.rowcount or 0

    def encuesta_create(self, *, owner_node_id: str, question: str,
                        options: List[str], days: int = 7,
                        starts_at: Optional[str] = None,
                        ends_at: Optional[str] = None) -> int:
        """Crea una encuesta y devuelve su id. Soporta duración por días o fechas ISO explícitas."""
        import json
        now = datetime.now()
        created_iso = starts_at if starts_at else now.isoformat(timespec='seconds')
        if ends_at:
            ends_iso = ends_at
        else:
            days = max(1, min(365, int(days)))
            ends_iso = (now + timedelta(days=days)).isoformat(timespec='seconds')

        with closing(self._connect()) as conn:
            cur = conn.execute(
                'INSERT INTO encuestas (owner_node_id, question, options, created_at, ends_at, status) '
                "VALUES (?, ?, ?, ?, ?, 'active')",
                (owner_node_id, question, json.dumps(options, ensure_ascii=False),
                 created_iso, ends_iso),
            )
            conn.commit()
            return int(cur.lastrowid)

    def _row_to_encuesta(self, row) -> Dict[str, Any]:
        import json
        d = dict(row)
        try:
            d['options'] = json.loads(d.get('options') or '[]')
        except Exception:
            d['options'] = []
        # Estado EFECTIVO sin persistir: si ya venció ends_at, se presenta como cerrada
        try:
            if d.get('status') == 'active' and d.get('ends_at'):
                if datetime.fromisoformat(d['ends_at']) <= datetime.now():
                    d['status'] = 'closed'
        except Exception:
            pass
        return d

    def encuesta_get(self, encuesta_id: int) -> Optional[Dict[str, Any]]:
        """Devuelve una encuesta por id (con opciones parseadas) o None."""
        with closing(self._connect()) as conn:
            cur = conn.execute(
                'SELECT id, owner_node_id, question, options, created_at, ends_at, status, closed_at '
                'FROM encuestas WHERE id = ?',
                (encuesta_id,),
            )
            row = cur.fetchone()
            return self._row_to_encuesta(row) if row else None

    def encuesta_get_active_by_owner(self, owner_node_id: str) -> Optional[Dict[str, Any]]:
        now = datetime.now().isoformat(timespec='seconds')
        with closing(self._connect()) as conn:
            cur = conn.execute(
                "SELECT id, owner_node_id, question, options, created_at, ends_at, status, closed_at "
                "FROM encuestas WHERE owner_node_id = ? AND status = 'active' "
                "AND (ends_at IS NULL OR ends_at > ?) "
                "ORDER BY created_at DESC LIMIT 1",
                (owner_node_id, now),
            )
            row = cur.fetchone()
            return self._row_to_encuesta(row) if row else None

    def encuesta_list_active(self, limit: int = 10) -> List[Dict[str, Any]]:
        now = datetime.now().isoformat(timespec='seconds')
        with closing(self._connect()) as conn:
            cur = conn.execute(
                "SELECT id, owner_node_id, question, options, created_at, ends_at, status, closed_at "
                "FROM encuestas WHERE status = 'active' AND (ends_at IS NULL OR ends_at > ?) "
                "ORDER BY created_at DESC LIMIT ?",
                (now, int(limit)),
            )
            return [self._row_to_encuesta(r) for r in cur.fetchall()]

    def encuesta_list_all(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Lista todas las encuestas (activas y cerradas) ordenadas con las activas más recientes primero."""
        with closing(self._connect()) as conn:
            cur = conn.execute(
                "SELECT id, owner_node_id, question, options, created_at, ends_at, status, closed_at "
                "FROM encuestas "
                "ORDER BY CASE WHEN status = 'active' THEN 0 ELSE 1 END, created_at DESC LIMIT ?",
                (int(limit),),
            )
            return [self._row_to_encuesta(r) for r in cur.fetchall()]

    def encuesta_close(self, encuesta_id: int, owner_node_id: Optional[str] = None) -> bool:
        """Cierra una encuesta. Si owner_node_id es None o 'admin', cierra sin comprobar dueño."""
        now = datetime.now().isoformat(timespec='seconds')
        with closing(self._connect()) as conn:
            if owner_node_id and owner_node_id not in ('admin', 'gateway', 'web'):
                cur = conn.execute(
                    "UPDATE encuestas SET status = 'closed', closed_at = ? "
                    "WHERE id = ? AND owner_node_id = ? AND status = 'active'",
                    (now, encuesta_id, owner_node_id),
                )
            else:
                cur = conn.execute(
                    "UPDATE encuestas SET status = 'closed', closed_at = ? "
                    "WHERE id = ? AND status = 'active'",
                    (now, encuesta_id),
                )
            conn.commit()
            return (cur.rowcount or 0) > 0

    def encuesta_delete(self, encuesta_id: int, owner_node_id: Optional[str] = None) -> bool:
        """Borra una encuesta y sus votos."""
        with closing(self._connect()) as conn:
            if owner_node_id and owner_node_id not in ('admin', 'gateway', 'web'):
                cur = conn.execute(
                    'DELETE FROM encuestas WHERE id = ? AND owner_node_id = ?',
                    (encuesta_id, owner_node_id),
                )
            else:
                cur = conn.execute(
                    'DELETE FROM encuestas WHERE id = ?',
                    (encuesta_id,),
                )
            if cur.rowcount:
                conn.execute('DELETE FROM encuesta_votos WHERE encuesta_id = ?', (encuesta_id,))
            conn.commit()
            return (cur.rowcount or 0) > 0

    def encuesta_vote(self, encuesta_id: int, node_id: str, option_index: int) -> str:
        """Registra o cambia el voto de un nodo. Devuelve 'new'|'changed'|'same'.

        NOTA (punto 3 de la revisión): la escritura usa un UPSERT atómico
        (INSERT ... ON CONFLICT DO UPDATE) sobre el índice UNIQUE
        (encuesta_id, node_id). El SELECT previo es SOLO para decidir el mensaje
        de respuesta ('new'/'changed'/'same'); aunque haya una escritura
        concurrente entre el SELECT y el UPSERT, este último no lanza
        IntegrityError (a diferencia de un INSERT a secas).

        En la práctica el daemon procesa los mensajes en un único hilo y el cron
        no vota, así que dos votos del MISMO nodo no coinciden en el tiempo; el
        UPSERT se adopta como buena práctica de robustez, no para corregir un
        fallo que se diera hoy.
        """
        now = datetime.now().isoformat(timespec='seconds')
        with closing(self._connect()) as conn:
            cur = conn.execute(
                'SELECT option_index FROM encuesta_votos WHERE encuesta_id = ? AND node_id = ?',
                (encuesta_id, node_id),
            )
            row = cur.fetchone()
            if row is not None and int(row['option_index']) == int(option_index):
                return 'same'

            conn.execute(
                'INSERT INTO encuesta_votos (encuesta_id, node_id, option_index, created_at, updated_at) '
                'VALUES (?, ?, ?, ?, ?) '
                'ON CONFLICT(encuesta_id, node_id) DO UPDATE SET '
                'option_index = excluded.option_index, updated_at = excluded.updated_at',
                (encuesta_id, node_id, option_index, now, now),
            )
            conn.commit()
            return 'new' if row is None else 'changed'

    def encuesta_results(self, encuesta_id: int) -> Dict[str, Any]:
        """Devuelve {counts: [n por opción], total: int}."""
        enc = self.encuesta_get(encuesta_id)
        n_opts = len(enc['options']) if enc else 0
        counts = [0] * n_opts
        with closing(self._connect()) as conn:
            cur = conn.execute(
                'SELECT option_index, COUNT(*) AS c FROM encuesta_votos WHERE encuesta_id = ? GROUP BY option_index',
                (encuesta_id,),
            )
            total = 0
            for r in cur.fetchall():
                idx = int(r['option_index'])
                c = int(r['c'])
                total += c
                if 0 <= idx < n_opts:
                    counts[idx] = c
        return {'counts': counts, 'total': total}

    # ---------- STATS ----------
    def stats_summary(self) -> Dict[str, Any]:
        """Resumen para /stats: comandos (hoy/total), comando top, pings y nodos."""
        today = datetime.now().date().isoformat()
        out: Dict[str, Any] = {}
        with closing(self._connect()) as conn:
            row = conn.execute('SELECT COUNT(*) AS c FROM commands_sent').fetchone()
            out['cmd_total'] = int(row['c']) if row else 0

            row = conn.execute(
                'SELECT COUNT(*) AS c FROM commands_sent WHERE substr(created_at, 1, 10) = ?',
                (today,),
            ).fetchone()
            out['cmd_today'] = int(row['c']) if row else 0

            row = conn.execute(
                'SELECT command, COUNT(*) AS c FROM commands_sent '
                'WHERE command IS NOT NULL GROUP BY command ORDER BY c DESC LIMIT 1'
            ).fetchone()
            out['cmd_top'] = (row['command'], int(row['c'])) if row else (None, 0)

            row = conn.execute('SELECT COUNT(*) AS c FROM pings').fetchone()
            out['pings_total'] = int(row['c']) if row else 0

            row = conn.execute('SELECT COUNT(*) AS c FROM nodes').fetchone()
            out['nodes_total'] = int(row['c']) if row else 0
            row = conn.execute('SELECT COUNT(*) AS c FROM nodes WHERE COALESCE(via_mqtt,0) = 1').fetchone()
            out['nodes_mqtt'] = int(row['c']) if row else 0
            out['nodes_rf'] = out['nodes_total'] - out['nodes_mqtt']

            row = conn.execute('SELECT COUNT(*) AS c FROM encuestas WHERE status = "active"').fetchone()
            out['encuestas_activas'] = int(row['c']) if row else 0
        return out

    def nodes_overview(self, active_hours: int = 24) -> Dict[str, Any]:
        """Resumen de nodos para /nodos: total, RF, MQTT, activos recientes."""
        out: Dict[str, Any] = {}
        with closing(self._connect()) as conn:
            row = conn.execute('SELECT COUNT(*) AS c FROM nodes').fetchone()
            out['total'] = int(row['c']) if row else 0
            row = conn.execute('SELECT COUNT(*) AS c FROM nodes WHERE COALESCE(via_mqtt,0) = 1').fetchone()
            out['mqtt'] = int(row['c']) if row else 0
            out['rf'] = out['total'] - out['mqtt']
            # last_heard es epoch (segundos). Activos en las últimas N horas.
            try:
                threshold = int((datetime.now() - timedelta(hours=active_hours)).timestamp())
                row = conn.execute(
                    'SELECT COUNT(*) AS c FROM nodes WHERE last_heard IS NOT NULL AND last_heard >= ?',
                    (threshold,),
                ).fetchone()
                out['active'] = int(row['c']) if row else 0
            except Exception:
                out['active'] = None
        return out

    def get_node_by_short_name(self, short_name: str) -> Optional[Dict[str, Any]]:
        """Busca un nodo por nombre corto (case-insensitive). Devuelve dict o None."""
        with closing(self._connect()) as conn:
            cur = conn.execute(
                'SELECT node_id, name, short_name, snr, rssi, hops, via_mqtt, last_heard '
                'FROM nodes WHERE UPPER(short_name) = UPPER(?) ORDER BY updated_at DESC LIMIT 1',
                (short_name,),
            )
            row = cur.fetchone()
            return dict(row) if row else None

    def snr_average(self, exclude_mqtt: bool = True) -> Dict[str, Any]:
        """Media de SNR de los nodos con SNR conocido. Devuelve {avg, count}."""
        with closing(self._connect()) as conn:
            sql = 'SELECT AVG(snr) AS avg, COUNT(*) AS c FROM nodes WHERE snr IS NOT NULL'
            if exclude_mqtt:
                sql += ' AND COALESCE(via_mqtt,0) = 0'
            row = conn.execute(sql).fetchone()
            avg = row['avg'] if row and row['avg'] is not None else None
            return {'avg': float(avg) if avg is not None else None, 'count': int(row['c']) if row else 0}

    def get_all_nodes(self, limit: Optional[int] = None, only_rf: bool = False) -> List[Dict[str, Any]]:
        """Devuelve la lista de nodos ordenados por favoritos y actividad reciente."""
        with closing(self._connect()) as conn:
            sql = """
                SELECT node_id AS id, node_id, name, num, short_name, mac_addr, hw_model, role,
                       is_favorite, snr, rssi, hops, uptime, via_mqtt, battery, voltage, last_heard, traces_detected, created_at, updated_at
                FROM nodes
                WHERE node_id IS NOT NULL AND trim(node_id) != '' AND node_id NOT IN ('None', 'null', 'Desconocido')
            """
            params: List[Any] = []
            if only_rf:
                sql += " AND COALESCE(via_mqtt, 0) = 0"
            sql += " ORDER BY is_favorite DESC, COALESCE(last_heard, 0) DESC, updated_at DESC"
            if limit is not None:
                sql += " LIMIT ?"
                params.append(int(limit))
            cur = conn.execute(sql, tuple(params))
            
            roles_map = {
                0: 'CLIENT', 1: 'CLIENT_MUTE', 2: 'ROUTER', 3: 'ROUTER_CLIENT',
                4: 'REPEATER', 5: 'TRACKER', 6: 'SENSOR', 7: 'TAK', 8: 'CLIENT_HIDDEN',
                9: 'LOST_FOUND', 10: 'TAK_TRACKER', 11: 'CLIENT_BASE'
            }
            results = []
            for r in cur.fetchall():
                d = dict(r)
                role_val = d.get('role')
                d['role_name'] = roles_map.get(role_val, 'CLIENT') if isinstance(role_val, int) else (str(role_val) if role_val else 'CLIENT')
                results.append(d)
            return results

    def get_recent_traces(self, limit: int = 15) -> List[Dict[str, Any]]:
        """Devuelve los últimos traceroutes completados con sus saltos estructurados."""
        with closing(self._connect()) as conn:
            cur = conn.execute(
                """
                SELECT id, "from", "to", status, created_at, updated_at, hops, hops_back,
                       to_name, to_name_short, data_raw,
                       hop1_id, hop1_name, hop1_snr,
                       hop2_id, hop2_name, hop2_snr,
                       hop3_id, hop3_name, hop3_snr,
                       hop4_id, hop4_name, hop4_snr,
                       hop5_id, hop5_name, hop5_snr,
                       hop6_id, hop6_name, hop6_snr,
                       hop7_id, hop7_name, hop7_snr
                FROM traces
                WHERE status IN ('done', 'error')
                ORDER BY id DESC
                LIMIT ?
                """,
                (int(limit),),
            )
            rows = cur.fetchall()
            out = []
            for r in rows:
                item = dict(r)
                hops_fwd = []
                for i in range(1, 8):
                    h_id = item.get(f"hop{i}_id")
                    if h_id:
                        hops_fwd.append({
                            "id": h_id,
                            "name": item.get(f"hop{i}_name") or h_id,
                            "snr": item.get(f"hop{i}_snr"),
                        })
                item["hops_forward"] = hops_fwd
                item["success"] = (item.get("status") == "done")
                out.append(item)
            return out

    # ---------- OUTBOX (COLA DE MENSAJES SALIENTES) ----------
    def enqueue_outbox(self, text: str, dest: str = '^all', channel: int = 0) -> int:
        """Encola un mensaje para ser enviado a la malla por el proceso de radio (main.py). Deduplica si ya está pendiente."""
        now_str = datetime.now().isoformat(timespec='seconds')
        with closing(self._connect()) as conn:
            cur = conn.execute(
                "SELECT id FROM outbox WHERE text = ? AND dest = ? AND channel = ? AND status = 'pending' ORDER BY id ASC LIMIT 1",
                (text, str(dest), int(channel)),
            )
            row = cur.fetchone()
            if row:
                return int(row['id'])

            cur2 = conn.execute(
                "INSERT INTO outbox (text, dest, channel, status, created_at) VALUES (?, ?, ?, 'pending', ?)",
                (text, str(dest), int(channel), now_str),
            )
            conn.commit()
            return int(cur2.lastrowid)

    def get_next_pending_outbox(self) -> Optional[Dict[str, Any]]:
        """Obtiene el siguiente mensaje pendiente de envío."""
        with closing(self._connect()) as conn:
            cur = conn.execute(
                "SELECT id, text, dest, channel, created_at FROM outbox WHERE status = 'pending' ORDER BY id ASC LIMIT 1"
            )
            row = cur.fetchone()
            return dict(row) if row else None

    def mark_outbox_sent(self, outbox_id: int, ok: bool = True) -> None:
        """Marca un mensaje saliente como enviado o con error."""
        status = 'sent' if ok else 'error'
        when_str = datetime.now().isoformat(timespec='seconds')
        with closing(self._connect()) as conn:
            conn.execute(
                "UPDATE outbox SET status = ?, sent_at = ? WHERE id = ?",
                (status, when_str, outbox_id),
            )
            conn.commit()

    # ---------- AUDITORÍA DE COMANDOS ----------
    def get_commands_audit(
        self,
        limit: int = 100,
        offset: int = 0,
        hours: Optional[int] = None,
        node_id: Optional[str] = None,
        command: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Historial cronológico detallado de comandos ejecutados con soporte de paginación."""
        with closing(self._connect()) as conn:
            sql = """
                SELECT c.id, c.node_id, c.command, c.message, c.parameters, c.created_at,
                       n.name, n.short_name, n.role, n.via_mqtt, n.snr
                FROM commands_sent c
                LEFT JOIN nodes n ON n.node_id = c.node_id
            """
            conds = []
            params = []
            if hours is not None:
                threshold = (datetime.now() - timedelta(hours=hours)).isoformat(timespec='seconds')
                conds.append("c.created_at >= ?")
                params.append(threshold)
            if node_id:
                conds.append("c.node_id = ?")
                params.append(node_id)
            if command:
                conds.append("c.command = ?")
                params.append(command)
            if conds:
                sql += " WHERE " + " AND ".join(conds)
            sql += " ORDER BY c.id DESC LIMIT ? OFFSET ?"
            params.append(int(limit))
            params.append(int(offset))

            cur = conn.execute(sql, tuple(params))
            return [dict(r) for r in cur.fetchall()]

    def get_top_command_users(self, limit: int = 20, hours: Optional[int] = 24) -> List[Dict[str, Any]]:
        """Ranking de nodos con más comandos ejecutados (Top 20 por defecto)."""
        with closing(self._connect()) as conn:
            sql = """
                SELECT c.node_id, COUNT(*) AS count,
                       MAX(c.created_at) AS last_command_at,
                       (SELECT c2.command FROM commands_sent c2 WHERE c2.node_id = c.node_id ORDER BY c2.id DESC LIMIT 1) AS last_command,
                       n.name, n.short_name, n.role, n.via_mqtt
                FROM commands_sent c
                LEFT JOIN nodes n ON n.node_id = c.node_id
            """
            params = []
            if hours is not None:
                threshold = (datetime.now() - timedelta(hours=hours)).isoformat(timespec='seconds')
                sql += " WHERE c.created_at >= ?"
                params.append(threshold)
            sql += " GROUP BY c.node_id ORDER BY count DESC LIMIT ?"
            params.append(int(limit))

            cur = conn.execute(sql, tuple(params))
            return [dict(r) for r in cur.fetchall()]

    def get_commands_audit_summary(self, hours: Optional[int] = 24) -> Dict[str, Any]:
        """Resumen estadístico de uso de comandos para tarjetas de dashboard."""
        out = {
            "total": 0,
            "unique_nodes": 0,
            "top_command": "N/D",
            "top_command_count": 0,
            "top_user": "N/D",
            "top_user_count": 0,
        }
        with closing(self._connect()) as conn:
            params = []
            where_sql = ""
            if hours is not None:
                threshold = (datetime.now() - timedelta(hours=hours)).isoformat(timespec='seconds')
                where_sql = "WHERE created_at >= ?"
                params.append(threshold)
            
            # Total y nodos únicos
            row = conn.execute(
                f"SELECT COUNT(*) AS total, COUNT(DISTINCT node_id) AS unique_nodes FROM commands_sent {where_sql}",
                tuple(params),
            ).fetchone()
            if row:
                out["total"] = int(row["total"] or 0)
                out["unique_nodes"] = int(row["unique_nodes"] or 0)

            # Comando top
            row = conn.execute(
                f"SELECT command, COUNT(*) AS c FROM commands_sent {where_sql} GROUP BY command ORDER BY c DESC LIMIT 1",
                tuple(params),
            ).fetchone()
            if row:
                out["top_command"] = str(row["command"] or "N/D")
                out["top_command_count"] = int(row["c"] or 0)

            # Nodo top
            where_join = f"WHERE c.created_at >= ?" if hours is not None else ""
            row = conn.execute(
                f"""
                SELECT c.node_id, n.short_name, n.name, COUNT(*) AS cnt
                FROM commands_sent c
                LEFT JOIN nodes n ON n.node_id = c.node_id
                {where_join}
                GROUP BY c.node_id ORDER BY cnt DESC LIMIT 1
                """,
                tuple(params),
            ).fetchone()
            if row:
                disp_name = row["short_name"] or row["name"] or row["node_id"] or "N/D"
                out["top_user"] = str(disp_name)
                out["top_user_count"] = int(row["cnt"] or 0)

        return out

    # ---------- MENSAJES PROGRAMADOS (MÓDULO 04) ----------
    def get_scheduled_messages(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Devuelve todos los mensajes programados."""
        with closing(self._connect()) as conn:
            cur = conn.execute(
                "SELECT id, message, channels, period_type, period_value, start_at, last_sent_at, next_run_at, enabled, created_at "
                "FROM scheduled_messages ORDER BY id DESC LIMIT ?",
                (int(limit),),
            )
            return [dict(r) for r in cur.fetchall()]

    def get_scheduled_message(self, msg_id: int) -> Optional[Dict[str, Any]]:
        """Obtiene un mensaje programado por su ID."""
        with closing(self._connect()) as conn:
            cur = conn.execute(
                "SELECT id, message, channels, period_type, period_value, start_at, last_sent_at, next_run_at, enabled, created_at "
                "FROM scheduled_messages WHERE id = ?",
                (int(msg_id),),
            )
            row = cur.fetchone()
            return dict(row) if row else None

    def create_scheduled_message(
        self,
        message: str,
        channels: str = "all",
        period_type: str = "hours",
        period_value: int = 1,
        start_at: Optional[str] = None,
        enabled: int = 1,
    ) -> int:
        now = datetime.now()
        now_iso = now.isoformat(timespec="seconds")
        
        if not start_at:
            start_iso = now_iso
            next_run_iso = now_iso
        else:
            s_clean = str(start_at).replace("Z", "")
            try:
                if "." in s_clean:
                    s_clean = s_clean.split(".")[0]
                start_dt = datetime.fromisoformat(s_clean)
                start_iso = start_dt.isoformat(timespec="seconds")
                if start_dt <= now:
                    next_run_iso = now_iso
                else:
                    next_run_iso = start_iso
            except Exception:
                start_iso = now_iso
                next_run_iso = now_iso

        with closing(self._connect()) as conn:
            cur = conn.execute(
                """
                INSERT INTO scheduled_messages (
                    message, channels, period_type, period_value, start_at, next_run_at, enabled, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    message.strip(),
                    str(channels),
                    period_type,
                    max(1, int(period_value)),
                    start_iso,
                    next_run_iso,
                    1 if enabled else 0,
                    now_iso,
                ),
            )
            conn.commit()
            return int(cur.lastrowid)

    def update_scheduled_message(self, msg_id: int, data: Dict[str, Any]) -> bool:
        """Actualiza campos de un mensaje programado."""
        data_clean = dict(data)
        if "channels" in data_clean and isinstance(data_clean["channels"], (list, tuple)):
            data_clean["channels"] = json.dumps(data_clean["channels"])
        if "period_value" in data_clean:
            try:
                data_clean["period_value"] = max(1, int(data_clean["period_value"]))
            except Exception:
                pass
        if "message" in data_clean and data_clean["message"]:
            data_clean["message"] = str(data_clean["message"]).strip()

        if "start_at" in data_clean and data_clean["start_at"]:
            s_clean = str(data_clean["start_at"]).replace("Z", "")
            if "." in s_clean:
                s_clean = s_clean.split(".")[0]
            try:
                start_dt = datetime.fromisoformat(s_clean)
                data_clean["start_at"] = start_dt.isoformat(timespec="seconds")
                if "next_run_at" not in data_clean:
                    data_clean["next_run_at"] = data_clean["start_at"]
            except Exception:
                pass

        if "next_run_at" in data_clean and data_clean["next_run_at"]:
            n_clean = str(data_clean["next_run_at"]).replace("Z", "")
            if "." in n_clean:
                n_clean = n_clean.split(".")[0]
            try:
                next_dt = datetime.fromisoformat(n_clean)
                data_clean["next_run_at"] = next_dt.isoformat(timespec="seconds")
            except Exception:
                pass

        allowed = ["message", "channels", "period_type", "period_value", "start_at", "next_run_at", "enabled"]
        updates = []
        params = []
        for k in allowed:
            if k in data_clean:
                updates.append(f"{k} = ?")
                params.append(data_clean[k])
        if not updates:
            return False
        params.append(int(msg_id))
        with closing(self._connect()) as conn:
            cur = conn.execute(
                f"UPDATE scheduled_messages SET {', '.join(updates)} WHERE id = ?",
                tuple(params),
            )
            conn.commit()
            return (cur.rowcount or 0) > 0

    def delete_scheduled_message(self, msg_id: int) -> bool:
        """Elimina un mensaje programado."""
        with closing(self._connect()) as conn:
            cur = conn.execute("DELETE FROM scheduled_messages WHERE id = ?", (int(msg_id),))
            conn.commit()
            return (cur.rowcount or 0) > 0

    def get_pending_scheduled_messages(self) -> List[Dict[str, Any]]:
        """Obtiene mensajes programados activos cuyo next_run_at ya venció."""
        now_iso = datetime.now().isoformat(timespec="seconds")
        with closing(self._connect()) as conn:
            cur = conn.execute(
                """
                SELECT id, message, channels, period_type, period_value, start_at, last_sent_at, next_run_at, enabled, created_at
                FROM scheduled_messages
                WHERE enabled = 1 AND next_run_at IS NOT NULL AND next_run_at <= ?
                ORDER BY next_run_at ASC
                """,
                (now_iso,),
            )
            return [dict(r) for r in cur.fetchall()]

    def mark_scheduled_message_sent(self, msg_id: int, next_run_at: Optional[str] = None) -> None:
        """Actualiza last_sent_at y fija el nuevo next_run_at (o deshabilita si era de un solo uso)."""
        now_iso = datetime.now().isoformat(timespec="seconds")
        with closing(self._connect()) as conn:
            if next_run_at is None:
                # Caso 'once': deshabilitar
                conn.execute(
                    "UPDATE scheduled_messages SET last_sent_at = ?, enabled = 0, next_run_at = NULL WHERE id = ?",
                    (now_iso, int(msg_id)),
                )
            else:
                conn.execute(
                    "UPDATE scheduled_messages SET last_sent_at = ?, next_run_at = ? WHERE id = ?",
                    (now_iso, next_run_at, int(msg_id)),
                )
            conn.commit()

    # ---------- NODOS BLOQUEADOS Y ANTI-ABUSO (MÓDULO 06) ----------
    def get_blocked_nodes(self, active_only: bool = True) -> List[Dict[str, Any]]:
        """Devuelve los nodos bloqueados (con soporte de expiración automática)."""
        now_iso = datetime.now().isoformat(timespec="seconds")
        with closing(self._connect()) as conn:
            sql = "SELECT id, node_id, node_name, block_type, reason, created_at, expires_at, active FROM blocked_nodes"
            if active_only:
                sql += " WHERE active = 1 AND (expires_at IS NULL OR expires_at > ?)"
                sql += " ORDER BY id DESC"
                cur = conn.execute(sql, (now_iso,))
            else:
                sql += " ORDER BY id DESC"
                cur = conn.execute(sql)
            return [dict(r) for r in cur.fetchall()]

    def is_node_blocked(self, node_id: str) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """Comprueba si un nodo está bloqueado actualmente. Devuelve (is_blocked, block_info)."""
        if not node_id:
            return False, None
        now_iso = datetime.now().isoformat(timespec="seconds")
        with closing(self._connect()) as conn:
            cur = conn.execute(
                """
                SELECT id, node_id, node_name, block_type, reason, created_at, expires_at, active
                FROM blocked_nodes
                WHERE node_id = ? AND active = 1 AND (expires_at IS NULL OR expires_at > ?)
                ORDER BY id DESC LIMIT 1
                """,
                (str(node_id), now_iso),
            )
            row = cur.fetchone()
            if row:
                return True, dict(row)
            return False, None

    def block_node(
        self,
        node_id: str,
        node_name: Optional[str] = None,
        block_type: str = "manual",
        reason: Optional[str] = None,
        expires_at: Optional[str] = None,
    ) -> int:
        """Bloquea un nodo (auto o manual). Actualiza o inserta según existencia."""
        now_iso = datetime.now().isoformat(timespec="seconds")
        with closing(self._connect()) as conn:
            cur = conn.execute(
                """
                INSERT INTO blocked_nodes (node_id, node_name, block_type, reason, created_at, expires_at, active)
                VALUES (?, ?, ?, ?, ?, ?, 1)
                ON CONFLICT(node_id) DO UPDATE SET
                    node_name = COALESCE(excluded.node_name, blocked_nodes.node_name),
                    block_type = excluded.block_type,
                    reason = excluded.reason,
                    created_at = excluded.created_at,
                    expires_at = excluded.expires_at,
                    active = 1
                """,
                (str(node_id), node_name, block_type, reason, now_iso, expires_at),
            )
            conn.commit()
            return int(cur.lastrowid or 0)

    def unblock_node(self, node_id: str) -> bool:
        """Desbloquea un nodo marcándolo como inactivo."""
        with closing(self._connect()) as conn:
            cur = conn.execute(
                "UPDATE blocked_nodes SET active = 0 WHERE node_id = ?",
                (str(node_id),),
            )
            conn.commit()
            return (cur.rowcount or 0) > 0

    def log_abuse(self, node_id: str, command: Optional[str], action_taken: str, reason: Optional[str] = None) -> None:
        """Registra un evento de abuso/bloqueo para auditoría."""
        now_iso = datetime.now().isoformat(timespec="seconds")
        with closing(self._connect()) as conn:
            conn.execute(
                "INSERT INTO abuse_logs (node_id, command, action_taken, reason, created_at) VALUES (?, ?, ?, ?, ?)",
                (str(node_id), command, action_taken, reason, now_iso),
            )
            conn.commit()

    def get_abuse_logs(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Devuelve los últimos registros de abusos."""
        with closing(self._connect()) as conn:
            cur = conn.execute(
                """
                SELECT a.id, a.node_id, a.command, a.action_taken, a.reason, a.created_at,
                       n.name, n.short_name
                FROM abuse_logs a
                LEFT JOIN nodes n ON n.node_id = a.node_id
                ORDER BY a.id DESC LIMIT ?
                """,
                (int(limit),),
            )
            return [dict(r) for r in cur.fetchall()]

    # ---------- VIGILANCIA: NODOS AUTO-REPORTADOS (MALA PRAXIS / SATURACIÓN) ----------
    def record_auto_reported_node(
        self,
        node_id: str,
        reason_code: str,
        reason_desc: str,
        details: Optional[Dict[str, Any] | str] = None,
        short_name: Optional[str] = None,
        name: Optional[str] = None,
    ) -> int:
        """Registra o actualiza una incidencia de mala praxis para un nodo.
        
        Si ya existe la combinación (node_id, reason_code), incrementa event_count
        y actualiza last_detected_at y last_details.
        """
        now_iso = datetime.now().isoformat(timespec="seconds")
        details_str = json.dumps(details, ensure_ascii=False) if isinstance(details, dict) else (details or None)

        with closing(self._connect()) as conn:
            # Obtener nombres si no se pasaron
            if not short_name or not name:
                n_row = conn.execute(
                    "SELECT short_name, name FROM nodes WHERE node_id = ? LIMIT 1",
                    (str(node_id),)
                ).fetchone()
                if n_row:
                    short_name = short_name or n_row["short_name"]
                    name = name or n_row["name"]

            cur = conn.execute(
                """
                INSERT INTO auto_reported_nodes (
                    node_id, short_name, name, reason_code, reason_desc,
                    event_count, first_detected_at, last_detected_at,
                    last_details, updated_at
                ) VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?, ?)
                ON CONFLICT(node_id, reason_code) DO UPDATE SET
                    short_name = COALESCE(excluded.short_name, auto_reported_nodes.short_name),
                    name = COALESCE(excluded.name, auto_reported_nodes.name),
                    reason_desc = excluded.reason_desc,
                    event_count = auto_reported_nodes.event_count + 1,
                    last_detected_at = excluded.last_detected_at,
                    last_details = COALESCE(excluded.last_details, auto_reported_nodes.last_details),
                    updated_at = excluded.updated_at
                """,
                (
                    str(node_id), short_name, name, str(reason_code), str(reason_desc),
                    now_iso, now_iso, details_str, now_iso
                )
            )
            conn.commit()
            return int(cur.lastrowid or 0)

    def get_auto_reported_nodes(
        self,
        limit: int = 100,
        offset: int = 0,
        reason_code: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Devuelve el listado de nodos auto-reportados ordenado por última detección."""
        with closing(self._connect()) as conn:
            query = """
                SELECT a.id, a.node_id, a.short_name, a.name, a.reason_code, a.reason_desc,
                       a.event_count, a.first_detected_at, a.last_detected_at, a.last_details,
                       a.is_ignored_bot, a.is_blocked_fw, a.updated_at,
                       n.snr, n.hops, n.via_mqtt, n.last_heard
                FROM auto_reported_nodes a
                LEFT JOIN nodes n ON n.node_id = a.node_id
            """
            params: List[Any] = []
            if reason_code:
                query += " WHERE a.reason_code = ?"
                params.append(str(reason_code))
            query += " ORDER BY a.last_detected_at DESC LIMIT ? OFFSET ?"
            params.extend([int(limit), int(offset)])

            cur = conn.execute(query, tuple(params))
            return [dict(r) for r in cur.fetchall()]

    def count_auto_reported_nodes(self) -> int:
        """Devuelve el total de incidencias de auto-reporte activas."""
        with closing(self._connect()) as conn:
            cur = conn.execute("SELECT COUNT(*) AS c FROM auto_reported_nodes")
            row = cur.fetchone()
            return int(row["c"]) if row else 0

    def set_node_bot_ignored(self, node_id: str, is_ignored: bool = True) -> bool:
        """Marca un nodo para ser ignorado completamente por el bot (no guardar nada ni responder)."""
        now_iso = datetime.now().isoformat(timespec="seconds")
        val = 1 if is_ignored else 0
        with closing(self._connect()) as conn:
            conn.execute(
                "UPDATE auto_reported_nodes SET is_ignored_bot = ?, updated_at = ? WHERE node_id = ?",
                (val, now_iso, str(node_id))
            )
            # Sincronizar también con blocked_nodes si se ignora
            if is_ignored:
                conn.execute(
                    """
                    INSERT INTO blocked_nodes (node_id, block_type, reason, created_at, active)
                    VALUES (?, 'manual', 'Ignorado manualmente en bot desde vigilancia', ?, 1)
                    ON CONFLICT(node_id) DO UPDATE SET active = 1, reason = 'Ignorado manualmente en bot desde vigilancia'
                    """,
                    (str(node_id), now_iso)
                )
            else:
                conn.execute(
                    "UPDATE blocked_nodes SET active = 0 WHERE node_id = ?",
                    (str(node_id),)
                )
            conn.commit()
            return True

    def get_ignored_node_ids(self) -> set[str]:
        """Devuelve el conjunto de todos los node_id ignorados o bloqueados por el bot."""
        with closing(self._connect()) as conn:
            cur = conn.execute(
                """
                SELECT DISTINCT node_id FROM auto_reported_nodes WHERE is_ignored_bot = 1
                UNION
                SELECT DISTINCT node_id FROM blocked_nodes WHERE active = 1
                """
            )
            return {str(r["node_id"]) for r in cur.fetchall() if r["node_id"]}

    def set_node_fw_blocked(self, node_id: str, is_blocked: bool = True) -> bool:
        """Marca en base de datos si el nodo fue bloqueado a nivel de firmware Meshtastic."""
        now_iso = datetime.now().isoformat(timespec="seconds")
        val = 1 if is_blocked else 0
        with closing(self._connect()) as conn:
            cur = conn.execute(
                "UPDATE auto_reported_nodes SET is_blocked_fw = ?, updated_at = ? WHERE node_id = ?",
                (val, now_iso, str(node_id))
            )
            conn.commit()
            return (cur.rowcount or 0) > 0

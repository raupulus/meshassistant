from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Iterable, Tuple
import hashlib

from create_db import ensure_database
from functions import sanitize_text


class Database:
    """Modelo simple para interactuar con la base de datos SQLite."""

    def __init__(self, db_path: Optional[str] = None) -> None:
        self.db_path = str(db_path) if db_path else str(ensure_database())

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
        with closing(self._connect()) as conn:
            cur = conn.execute(
                'INSERT INTO chistes ("from", content, need_upload, need_approve, chiste_id) VALUES (?, ?, ?, ?, ?)',
                (from_, content, 1 if need_upload else 0, 1 if need_approve else 0, chiste_id),
            )
            conn.commit()
            return int(cur.lastrowid)

    def get_chistes_to_upload(self, limit: int = 100) -> List[Dict[str, Any]]:
        with closing(self._connect()) as conn:
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
        with closing(self._connect()) as conn:
            conn.execute(f'UPDATE chistes SET need_upload = 0 WHERE id IN ({placeholders})', tuple(ids))
            conn.commit()

    def get_last_downloaded_chiste_id(self) -> Optional[int]:
        with closing(self._connect()) as conn:
            cur = conn.execute('SELECT MAX(chiste_id) as last_id FROM chistes WHERE chiste_id IS NOT NULL')
            row = cur.fetchone()
            return int(row[0]) if row and row[0] is not None else None

    def bulk_insert_api_chistes(self, items: Iterable[Dict[str, Any]]) -> Tuple[int, int]:
        """Inserta chistes descargados de la API.

        Cada item debe tener: id (-> chiste_id), content y uploaded_by (-> from).
        Flags need_approve y need_upload se guardan en 0.
        Devuelve (insertados, ignorados).
        """
        inserted = 0
        ignored = 0
        with closing(self._connect()) as conn:
            for it in items:
                api_id = it.get('id')
                content = it.get('content')
                uploaded_by = it.get('uploaded_by')
                if content is None:
                    continue
                try:
                    conn.execute(
                        'INSERT OR IGNORE INTO chistes ("from", content, need_upload, need_approve, chiste_id) VALUES (?, ?, 0, 0, ?)',
                        (uploaded_by, content, api_id),
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
        with closing(self._connect()) as conn:
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
        with closing(self._connect()) as conn:
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
        with closing(self._connect()) as conn:
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
        with closing(self._connect()) as conn:
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

        with closing(self._connect()) as conn:
            conn.execute(
                f"UPDATE nodes SET {set_clause} WHERE node_id = ?",
                tuple(values),
            )
            conn.commit()

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
                    INSERT INTO tasks_control (name, last_run_at, extra) VALUES (?, ?, ?)
                    ON CONFLICT(name) DO UPDATE SET last_run_at = excluded.last_run_at, extra = excluded.extra
                    """
                ),
                (name, when_str, extra),
            )
            conn.commit()

    # ---------- NODE TRACE CONTROL ----------
    def get_next_node_to_trace(
        self,
        *,
        hops_limit: int = 2,
        reload_hours: int = 24 * 7,
        retry_hours: int = 24,
    ) -> Optional[str]:
        """Devuelve el próximo node_id candidato cumpliendo:
        - COALESCE(via_mqtt, 0) = 0
        - hops <= hops_limit
        - sin traces pendientes
        - ventanas:
            • último status='done'  → ahora - updated_at ≥ reload_hours
            • último status='error' → ahora - updated_at ≥ retry_hours
          Si no hay trazas previas → elegible.
        """
        with closing(self._connect()) as conn:
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
                  AND (n.hops IS NULL OR n.hops <= ?)
                  AND COALESCE(p.pendings, 0) = 0
                  AND (
                        lp.last_updated IS NULL
                     OR (
                          (ls.last_status = 'done'  AND strftime('%s','now') - strftime('%s', lp.last_updated) >= ?)
                       OR (ls.last_status = 'error' AND strftime('%s','now') - strftime('%s', lp.last_updated) >= ?)
                        )
                  )
                ORDER BY n.updated_at DESC
                LIMIT 1
                '''
                , (
                    int(hops_limit),
                    int(reload_hours) * 3600,
                    int(retry_hours) * 3600,
                )
            )
            row = cur.fetchone()
            return row['node_id'] if row else None

    # Trace requests: eliminadas en favor de usar la propia tabla `traces` como cola

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

    def aemet_weather_get_latest(self, scope: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Devuelve el último registro de clima descargado o None.

        Si se indica `scope` ('province' | 'city' | 'forecast'), filtra por él.
        Sin scope, devuelve el más reciente independientemente del tipo, pero
        excluye los de previsión multi-día ('forecast') para no mezclarlos con
        el tiempo actual de /weather.
        """
        with closing(self._connect()) as conn:
            if scope:
                cur = conn.execute(
                    'SELECT id, scope, province, province_code, city, city_code, day, content, created_at '
                    'FROM aemet_weather WHERE scope = ? ORDER BY created_at DESC, id DESC LIMIT 1',
                    (scope,),
                )
            else:
                cur = conn.execute(
                    'SELECT id, scope, province, province_code, city, city_code, day, content, created_at '
                    "FROM aemet_weather WHERE scope != 'forecast' ORDER BY created_at DESC, id DESC LIMIT 1"
                )
            row = cur.fetchone()
            return dict(row) if row else None

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
        when_str = datetime.now().isoformat(timespec='seconds')
        with closing(self._connect()) as conn:
            cur = conn.execute(
                'INSERT INTO commands_sent (node_id, command, parameters, message, created_at) VALUES (?, ?, ?, ?, ?)',
                (node_id, command, parameters, message, when_str),
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
                        options: List[str], days: int = 7) -> int:
        """Crea una encuesta y devuelve su id. days entre 1 y 30.

        NOTA (punto 5 de la revisión): se usa datetime.now() en hora LOCAL naive,
        igual que el resto del esquema (created_at, tasks_control, etc.). Es una
        decisión consciente de coherencia: pasar solo las encuestas a UTC las
        dejaría inconsistentes con las demás tablas, y el único efecto de un
        cambio de horario (DST) sería un desfase de ±1 h en el cierre de una
        encuesta que dura días, algo irrelevante para este caso de uso.
        """
        import json
        days = max(1, min(30, int(days)))
        now = datetime.now()
        ends = now + timedelta(days=days)
        with closing(self._connect()) as conn:
            cur = conn.execute(
                'INSERT INTO encuestas (owner_node_id, question, options, created_at, ends_at, status) '
                "VALUES (?, ?, ?, ?, ?, 'active')",
                (owner_node_id, question, json.dumps(options, ensure_ascii=False),
                 now.isoformat(timespec='seconds'), ends.isoformat(timespec='seconds')),
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
        # Estado EFECTIVO sin persistir (punto 2 de la revisión): si ya venció
        # ends_at, se presenta como cerrada aunque la BD aún diga 'active'. El
        # cierre real en BD lo hace el cron con encuesta_expire_due(). Así las
        # lecturas no escriben.
        try:
            if d.get('status') == 'active' and d.get('ends_at'):
                if datetime.fromisoformat(d['ends_at']) <= datetime.now():
                    d['status'] = 'closed'
        except Exception:
            pass
        return d

    def encuesta_get(self, encuesta_id: int) -> Optional[Dict[str, Any]]:
        """Devuelve una encuesta por id (con opciones parseadas) o None.

        Calcula el estado efectivo en memoria; no escribe en BD.
        """
        with closing(self._connect()) as conn:
            cur = conn.execute(
                'SELECT id, owner_node_id, question, options, created_at, ends_at, status, closed_at '
                'FROM encuestas WHERE id = ?',
                (encuesta_id,),
            )
            row = cur.fetchone()
            return self._row_to_encuesta(row) if row else None

    def encuesta_get_active_by_owner(self, owner_node_id: str) -> Optional[Dict[str, Any]]:
        # Filtra por ends_at en el propio SELECT (sin escribir): una encuesta
        # vencida pero aún no barrida por el cron NO cuenta como activa.
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
        # Solo activas no vencidas; sin escribir en BD (ver punto 2 revisión).
        now = datetime.now().isoformat(timespec='seconds')
        with closing(self._connect()) as conn:
            cur = conn.execute(
                "SELECT id, owner_node_id, question, options, created_at, ends_at, status, closed_at "
                "FROM encuestas WHERE status = 'active' AND (ends_at IS NULL OR ends_at > ?) "
                "ORDER BY created_at DESC LIMIT ?",
                (now, int(limit)),
            )
            return [self._row_to_encuesta(r) for r in cur.fetchall()]

    def encuesta_close(self, encuesta_id: int, owner_node_id: str) -> bool:
        """Cierra una encuesta. Solo el nodo dueño. Devuelve True si se cerró."""
        now = datetime.now().isoformat(timespec='seconds')
        with closing(self._connect()) as conn:
            cur = conn.execute(
                "UPDATE encuestas SET status = 'closed', closed_at = ? "
                "WHERE id = ? AND owner_node_id = ? AND status = 'active'",
                (now, encuesta_id, owner_node_id),
            )
            conn.commit()
            return (cur.rowcount or 0) > 0

    def encuesta_delete(self, encuesta_id: int, owner_node_id: str) -> bool:
        """Borra una encuesta y sus votos. Solo el nodo dueño.

        NOTA (punto 6 de la revisión): los dos DELETE van en la MISMA transacción
        con un único commit() al final, así que la operación es atómica: si el
        proceso muriera entre medias, ambos se revierten y no quedan votos
        huérfanos. Por eso no se añade FOREIGN KEY ... ON DELETE CASCADE (exigiría
        PRAGMA foreign_keys=ON por conexión y reconstruir la tabla).
        """
        with closing(self._connect()) as conn:
            cur = conn.execute(
                'DELETE FROM encuestas WHERE id = ? AND owner_node_id = ?',
                (encuesta_id, owner_node_id),
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

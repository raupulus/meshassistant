from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional, Iterable, Tuple
import hashlib

from create_db import ensure_database
from functions import sanitize_text


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
        with self._connect() as conn:
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
        with self._connect() as conn:
            cur = conn.execute(
                'SELECT id, province, data_raw, message, created_at FROM aemet WHERE published = 0 ORDER BY created_at ASC LIMIT 1'
            )
            row = cur.fetchone()
            return dict(row) if row else None

    def aemet_mark_published(self, alert_id: int) -> None:
        now = datetime.now().isoformat(timespec='seconds')
        with self._connect() as conn:
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
        with self._connect() as conn:
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

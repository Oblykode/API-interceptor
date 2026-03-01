"""SQLite repository for flow, decision, and event persistence."""

from __future__ import annotations

import asyncio
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from app.domain.models import DecisionStage, FlowRecord


def _to_iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _from_iso(value: str) -> datetime:
    return datetime.fromisoformat(value)


class SQLiteRepository:

    def __init__(self, db_path: str) -> None:
        self._db_path = Path(db_path)
        self._lock = asyncio.Lock()
        self._conn: Optional[sqlite3.Connection] = None
        self._schema_ready = False

    async def init(self) -> None:
        async with self._lock:
            self._require_conn()

    async def close(self) -> None:
        async with self._lock:
            if self._conn is not None:
                conn = self._conn
                self._conn = None
                self._schema_ready = False
                await asyncio.to_thread(conn.close)

    async def upsert_flow(self, flow: FlowRecord) -> None:
        async with self._lock:
            conn = self._require_conn()
            await asyncio.to_thread(
                conn.execute,
                """
                INSERT INTO flows (
                    id, created_at, updated_at, status, request_json, response_json, tags_json, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    updated_at=excluded.updated_at,
                    status=excluded.status,
                    request_json=excluded.request_json,
                    response_json=excluded.response_json,
                    tags_json=excluded.tags_json,
                    metadata_json=excluded.metadata_json
                """,
                (
                    flow.id,
                    _to_iso(flow.created_at),
                    _to_iso(flow.updated_at),
                    flow.status.value,
                    flow.request.model_dump_json(),
                    flow.response.model_dump_json() if flow.response else None,
                    json.dumps(flow.tags),
                    json.dumps(flow.metadata),
                ),
            )
            await asyncio.to_thread(conn.commit)

    async def get_flow(self, flow_id: str) -> Optional[FlowRecord]:
        async with self._lock:
            conn = self._require_conn()
            cursor = await asyncio.to_thread(
                conn.execute,
                """
                SELECT id, created_at, updated_at, status, request_json, response_json, tags_json, metadata_json
                FROM flows
                WHERE id = ?
                """,
                (flow_id,),
            )
            row = await asyncio.to_thread(cursor.fetchone)
            return self._row_to_flow(row) if row else None

    async def list_flows(
        self,
        *,
        limit: int = 100,
        search: Optional[str] = None,
        method: Optional[str] = None,
        status: Optional[str] = None,
        has_response: Optional[bool] = None,
        from_ts: Optional[float] = None,
        to_ts: Optional[float] = None,
    ) -> list[FlowRecord]:
        clauses = ["1=1"]
        params: list[object] = []

        if search:
            clauses.append(
                "(json_extract(request_json, '$.url') LIKE ? OR json_extract(request_json, '$.body_text') LIKE ?)"
            )
            needle = f"%{search}%"
            params.extend([needle, needle])

        if method:
            clauses.append("UPPER(json_extract(request_json, '$.method')) = UPPER(?)")
            params.append(method)

        if status:
            clauses.append("status = ?")
            params.append(status)

        if has_response is True:
            clauses.append("response_json IS NOT NULL")
        elif has_response is False:
            clauses.append("response_json IS NULL")

        if from_ts is not None:
            from_iso = _to_iso(datetime.fromtimestamp(from_ts, tz=timezone.utc))
            clauses.append("updated_at >= ?")
            params.append(from_iso)

        if to_ts is not None:
            to_iso = _to_iso(datetime.fromtimestamp(to_ts, tz=timezone.utc))
            clauses.append("updated_at <= ?")
            params.append(to_iso)

        safe_limit = max(1, min(limit, 1000))
        params.append(safe_limit)

        sql = (
            "SELECT id, created_at, updated_at, status, request_json, response_json, tags_json, metadata_json "
            f"FROM flows WHERE {' AND '.join(clauses)} "
            "ORDER BY updated_at DESC LIMIT ?"
        )

        async with self._lock:
            conn = self._require_conn()
            cursor = await asyncio.to_thread(conn.execute, sql, tuple(params))
            rows = await asyncio.to_thread(cursor.fetchall)
        return [self._row_to_flow(row) for row in rows]

    async def set_decision(self, flow_id: str, stage: DecisionStage, decision: dict) -> None:
        async with self._lock:
            conn = self._require_conn()
            await asyncio.to_thread(
                conn.execute,
                """
                INSERT INTO decisions(flow_id, stage, decision_json, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(flow_id, stage) DO UPDATE SET
                    decision_json=excluded.decision_json,
                    created_at=excluded.created_at
                """,
                (flow_id, stage.value, json.dumps(decision), _to_iso(datetime.now(timezone.utc))),
            )
            await asyncio.to_thread(conn.commit)

    async def take_decision(self, flow_id: str, stage: DecisionStage) -> Optional[dict]:
        async with self._lock:
            conn = self._require_conn()
            cursor = await asyncio.to_thread(
                conn.execute,
                "SELECT decision_json FROM decisions WHERE flow_id = ? AND stage = ?",
                (flow_id, stage.value),
            )
            row = await asyncio.to_thread(cursor.fetchone)
            if row is None:
                return None

            await asyncio.to_thread(
                conn.execute,
                "DELETE FROM decisions WHERE flow_id = ? AND stage = ?",
                (flow_id, stage.value),
            )
            await asyncio.to_thread(conn.commit)
            return json.loads(row["decision_json"])

    async def append_event(self, flow_id: Optional[str], event_type: str, payload: dict) -> int:
        async with self._lock:
            conn = self._require_conn()
            cursor = await asyncio.to_thread(
                conn.execute,
                """
                INSERT INTO events(flow_id, event_type, payload_json, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    flow_id,
                    event_type,
                    json.dumps(payload),
                    _to_iso(datetime.now(timezone.utc)),
                ),
            )
            await asyncio.to_thread(conn.commit)
            return int(cursor.lastrowid)

    async def cleanup_old(self, retention_minutes: int) -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=retention_minutes)
        cutoff_iso = _to_iso(cutoff)
        async with self._lock:
            conn = self._require_conn()
            cursor = await asyncio.to_thread(conn.execute, "DELETE FROM flows WHERE updated_at < ?", (cutoff_iso,))
            deleted = cursor.rowcount if cursor.rowcount is not None else 0
            await asyncio.to_thread(conn.execute, "DELETE FROM decisions WHERE flow_id NOT IN (SELECT id FROM flows)")
            await asyncio.to_thread(
                conn.execute,
                "DELETE FROM events WHERE flow_id IS NOT NULL AND flow_id NOT IN (SELECT id FROM flows)",
            )
            await asyncio.to_thread(conn.commit)
            return int(deleted)

    async def clear_all(self) -> None:
        async with self._lock:
            conn = self._require_conn()
            await asyncio.to_thread(conn.execute, "DELETE FROM decisions")
            await asyncio.to_thread(conn.execute, "DELETE FROM events")
            await asyncio.to_thread(conn.execute, "DELETE FROM flows")
            await asyncio.to_thread(conn.commit)

    async def _execute(self, sql: str) -> None:
        async with self._lock:
            conn = self._require_conn()
            await asyncio.to_thread(conn.execute, sql)
            await asyncio.to_thread(conn.commit)

    async def _executescript(self, sql: str) -> None:
        async with self._lock:
            conn = self._require_conn()
            await asyncio.to_thread(conn.executescript, sql)
            await asyncio.to_thread(conn.commit)

    def _row_to_flow(self, row: sqlite3.Row) -> FlowRecord:
        return FlowRecord(
            id=row["id"],
            request=json.loads(row["request_json"]),
            response=json.loads(row["response_json"]) if row["response_json"] else None,
            status=row["status"],
            created_at=_from_iso(row["created_at"]),
            updated_at=_from_iso(row["updated_at"]),
            tags=json.loads(row["tags_json"]),
            metadata=json.loads(row["metadata_json"]),
        )

    def _require_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._schema_ready = False
        if not self._schema_ready:
            self._bootstrap_schema(self._conn)
            self._schema_ready = True
        return self._conn

    @staticmethod
    def _bootstrap_schema(conn: sqlite3.Connection) -> None:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS flows (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                status TEXT NOT NULL,
                request_json TEXT NOT NULL,
                response_json TEXT,
                tags_json TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS decisions (
                flow_id TEXT NOT NULL,
                stage TEXT NOT NULL,
                decision_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY(flow_id, stage)
            );

            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                flow_id TEXT,
                event_type TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )
        conn.commit()

"""Shared Oracle connection handle — pool or single connection with a lock.

Hybrid retrieve runs bags in parallel; a single async connection cannot multiplex
statements (causes thin-protocol InvalidStateError). Prefer a pool; otherwise
serialize access with a lock.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator


class OracleDb:
    def __init__(self, handle: Any) -> None:
        self._handle = handle
        self._lock = asyncio.Lock()
        # oracledb AsyncConnectionPool has acquire(); AsyncConnection has cursor().
        self._is_pool = hasattr(handle, "acquire") and not hasattr(handle, "cursor")

    @property
    def raw(self) -> Any:
        return self._handle

    @asynccontextmanager
    async def connection(self) -> AsyncIterator[Any]:
        if self._is_pool:
            async with self._handle.acquire() as conn:
                yield conn
        else:
            async with self._lock:
                yield self._handle


async def fetch_all(db: OracleDb, sql: str, binds: list[Any] | None = None) -> list[dict[str, Any]]:
    async with db.connection() as conn:
        cur = conn.cursor()
        try:
            await cur.execute(sql, binds or [])
            rows = await cur.fetchall()
            cols = [d[0].lower() for d in cur.description] if cur.description else []
            return [dict(zip(cols, row, strict=True)) for row in rows]
        finally:
            cur.close()


async def fetch_one(db: OracleDb, sql: str, binds: list[Any] | None = None) -> dict[str, Any] | None:
    rows = await fetch_all(db, sql, binds)
    return rows[0] if rows else None


async def execute(db: OracleDb, sql: str, binds: list[Any] | None = None, *, commit: bool = False) -> None:
    async with db.connection() as conn:
        cur = conn.cursor()
        try:
            await cur.execute(sql, binds or [])
            if commit:
                await conn.commit()
        finally:
            cur.close()


async def oracle_text_available(db: OracleDb) -> bool:
    """True when CTXSYS (Oracle Text) exists — absent on gvenzl *-slim* images."""
    try:
        rows = await fetch_all(
            db,
            "SELECT COUNT(*) AS c FROM all_users WHERE username = 'CTXSYS'",
        )
        return bool(rows and int(rows[0]["c"]) > 0)
    except Exception:
        return False

"""Oracle pagination KV — table/columns from ``DataBindings.pagination_kv``."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from recql.catalog.bindings import PaginationKvBinding
from recql.plugins.base import KvStore
from recql_oracle.db import OracleDb, execute, fetch_all
from recql_oracle.schema import ensure_operational_tables


class OracleKvStore(KvStore):
    def __init__(self, db: Any, *, binding: PaginationKvBinding | None = None) -> None:
        self.db = db if isinstance(db, OracleDb) else OracleDb(db)
        self.binding = binding or PaginationKvBinding()
        self._ensured = False

    async def _ensure(self) -> None:
        if self._ensured:
            return
        await ensure_operational_tables(self.db, kv=self.binding)
        self._ensured = True

    async def load_seen(self, key: str) -> set[str]:
        await self._ensure()
        b = self.binding
        rows = await fetch_all(
            self.db,
            f"""
            SELECT {b.item_id_column} AS item_id FROM {b.from_sql}
            WHERE {b.key_column} = :1 AND {b.expires_at_column} > SYSTIMESTAMP
            """,
            [key],
        )
        return {str(r["item_id"]) for r in rows}

    async def remember(self, key: str, ids: list[str], ttl: int) -> None:
        if not ids:
            return
        await self._ensure()
        b = self.binding
        expires = datetime.now(timezone.utc) + timedelta(seconds=int(ttl))
        for iid in ids:
            await execute(
                self.db,
                f"""
                MERGE INTO {b.from_sql} t
                USING (SELECT :1 AS k, :2 AS iid FROM dual) s
                ON (t.{b.key_column} = s.k AND t.{b.item_id_column} = s.iid)
                WHEN MATCHED THEN UPDATE SET {b.expires_at_column} = :3
                WHEN NOT MATCHED THEN INSERT
                  ({b.key_column}, {b.item_id_column}, {b.expires_at_column})
                  VALUES (:4, :5, :6)
                """,
                [key, iid, expires, key, iid, expires],
                commit=True,
            )

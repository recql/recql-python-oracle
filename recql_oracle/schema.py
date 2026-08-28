"""Oracle operational tables from ``PaginationKvBinding`` (no fixed names)."""

from __future__ import annotations

from typing import Any

from recql.catalog.bindings import PaginationKvBinding
from recql_oracle.db import OracleDb, execute


def pagination_seen_plsql(kv: PaginationKvBinding | None = None) -> str:
    b = kv or PaginationKvBinding()
    return f"""
BEGIN
  EXECUTE IMMEDIATE '
    CREATE TABLE {b.from_sql} (
      {b.key_column} VARCHAR2(512) NOT NULL,
      {b.item_id_column} VARCHAR2(128) NOT NULL,
      {b.expires_at_column} TIMESTAMP WITH TIME ZONE NOT NULL,
      PRIMARY KEY ({b.key_column}, {b.item_id_column})
    )';
EXCEPTION
  WHEN OTHERS THEN
    IF SQLCODE != -955 THEN RAISE; END IF;
END;
"""


ARTIFACT_REGISTRY_PLSQL = """
BEGIN
  EXECUTE IMMEDIATE '
    CREATE TABLE artifact_registry (
      kind VARCHAR2(32) NOT NULL,
      name VARCHAR2(128) NOT NULL,
      version VARCHAR2(64) NOT NULL,
      dims NUMBER,
      config_hash VARCHAR2(64),
      feature_spec JSON,
      created_at TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
      PRIMARY KEY (kind, name, version)
    )';
EXCEPTION
  WHEN OTHERS THEN
    IF SQLCODE != -955 THEN RAISE; END IF;
END;
"""


async def ensure_operational_tables(db: Any, *, kv: PaginationKvBinding | None = None) -> None:
    handle = db if isinstance(db, OracleDb) else OracleDb(db)
    binding = kv or PaginationKvBinding()
    if binding.ensure_table:
        await execute(handle, pagination_seen_plsql(binding), commit=True)
    await execute(handle, ARTIFACT_REGISTRY_PLSQL, commit=True)

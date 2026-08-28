"""Open an Oracle pool + RecQL plugin registry from a DSN."""

from __future__ import annotations

import os
from typing import Any, Awaitable, Callable

from recql.catalog import EngineCatalog
from recql.plugins.base import PluginRegistry


def parse_oracle_dsn(dsn: str) -> tuple[str, str, str]:
    """Parse ``oracle://user:pass@host:1521/service`` into ``(user, password, easy_connect)``."""
    raw = dsn
    if raw.lower().startswith("oracle://"):
        raw = raw[len("oracle://") :]
    if "@" in raw and ":" in raw.split("@", 1)[0]:
        creds, rest = raw.split("@", 1)
        user, password = creds.split(":", 1)
        return user, password, rest
    return (
        os.environ.get("ORACLE_USER", "recql"),
        os.environ.get("ORACLE_PASSWORD", "recql"),
        raw,
    )


async def open_connection(
    dsn: str,
    *,
    catalog: EngineCatalog | None = None,
    min: int = 1,
    max: int = 4,
    **kwargs: Any,
) -> tuple[PluginRegistry, Callable[[], Awaitable[None]]]:
    """Return ``(registry, close)`` for ``oracle://…`` DSNs."""
    import oracledb

    from recql_oracle import open_registry

    user, password, easy = parse_oracle_dsn(dsn)
    # Pool required: hybrid retrieve runs bags in parallel
    pool = oracledb.create_pool_async(
        user=user, password=password, dsn=easy, min=min, max=max
    )
    registry = await open_registry(catalog=catalog, pool=pool, **kwargs)

    async def close() -> None:
        await pool.close()

    return registry, close

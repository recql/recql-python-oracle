"""Oracle 26ai plugin pack — VECTOR_DISTANCE + Oracle Text (or LIKE fallback) + KV.

Configured via engine YAML ``plugins.backend: oracle`` and ``data`` / ``index``
bindings. Application demos: ``examples/generator/oracle/``.

Note: ``gvenzl/oracle-free:*-slim*`` images omit CTXSYS. Lexical search falls
back to substring match unless a full (non-slim) image is used.
"""

from __future__ import annotations

from typing import Any

from recql.plugins.base import PluginRegistry
from recql_oracle import dialect as _dialect  # noqa: F401 — register SQL dialect
from recql_oracle.registry import oracle_registry
from recql_oracle.schema import ensure_operational_tables

__all__ = [
    "ensure_operational_tables",
    "open_registry",
    "oracle_registry",
]


async def open_registry(
    *,
    catalog=None,
    pool=None,
    connection=None,
    plugin_cfg: dict[str, Any] | None = None,
    **kwargs: Any,
) -> PluginRegistry:
    """Entry-point adapter for ``recql.backends`` (called by core factory)."""
    handle = connection or pool
    if handle is None:
        raise ValueError("oracle backend requires connection= or pool=")
    return await oracle_registry(
        handle, catalog=catalog, plugin_cfg=plugin_cfg, **kwargs
    )

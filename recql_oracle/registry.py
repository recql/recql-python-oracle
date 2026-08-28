"""Assemble the Oracle PluginRegistry (retrievers, scorers, filters, KV)."""

from __future__ import annotations

from typing import Any

from recql.catalog.bindings import DataBindings, bindings_from_catalog, default_fixture_bindings
from recql.encode import get_encoder, warm_encoders_for_catalog
from recql.plugins.base import PluginRegistry
from recql.plugins.mock import MockExpressionFilter, MockScorer
from recql.plugins.sql_common import (
    BoundDbExecutor,
    SqlPrebuiltFilter,
    TemplateCandidateIdsRetriever,
    TemplateColumnOrderRetriever,
    TemplateFilterRetriever,
)
from recql_oracle.db import OracleDb, fetch_all, oracle_text_available
from recql_oracle.kv import OracleKvStore
from recql_oracle.pushdown import assert_pushdown_or_raise, supports_prefilter
from recql_oracle.retrievers import OracleSimilarityRetriever, OracleTextSearchRetriever
from recql_oracle.schema import ensure_operational_tables
from recql_oracle.scorer import OracleModelScorer


def _dims_from_catalog(catalog, *, default: int = 8) -> int:
    if catalog is None:
        return default
    embeddings = getattr(catalog, "embeddings", None) or {}
    for preferred in ("content_embedding", "title_embedding"):
        emb = embeddings.get(preferred)
        if emb is not None and getattr(emb, "dims", None):
            return int(emb.dims)
    for emb in embeddings.values():
        if getattr(emb, "dims", None):
            return int(emb.dims)
    return default


async def oracle_registry(
    handle,
    *,
    catalog=None,
    plugin_cfg: dict[str, Any] | None = None,
    dims: int | None = None,
    bindings: DataBindings | None = None,
    warm_models: bool = True,
    **_kwargs: Any,
) -> PluginRegistry:
    cfg = dict(plugin_cfg or {})
    db = handle if isinstance(handle, OracleDb) else OracleDb(handle)
    resolved = bindings or (
        bindings_from_catalog(catalog) if catalog is not None else default_fixture_bindings(backend="oracle")
    )
    if dims is None:
        dims = _dims_from_catalog(catalog, default=8)
    encode_backend = str(cfg.get("encode_backend") or "fake")
    warmed = warm_encoders_for_catalog(catalog, backend=encode_backend, dims=dims)
    encoder = warmed[0] if warmed else get_encoder(backend=encode_backend, dims=dims, warm=True)

    await ensure_operational_tables(db, kv=resolved.pagination_kv)
    use_oracle_text = await oracle_text_available(db)

    ex = BoundDbExecutor(db, fetch_all)
    col = TemplateColumnOrderRetriever(
        ex,
        default_backend="oracle",
        assert_pushdown=assert_pushdown_or_raise,
        supports_prefilter_fn=supports_prefilter,
    )
    filt = TemplateFilterRetriever(
        ex,
        default_backend="oracle",
        assert_pushdown=assert_pushdown_or_raise,
        supports_prefilter_fn=supports_prefilter,
        default_where="1=1",
    )
    ids = TemplateCandidateIdsRetriever(
        ex, default_backend="oracle", supports_prefilter_fn=supports_prefilter
    )
    sim = OracleSimilarityRetriever(db, dims=dims, plugin_cfg=cfg)
    text = OracleTextSearchRetriever(
        db, encoder=encoder, plugin_cfg=cfg, use_oracle_text=use_oracle_text
    )
    model_scorer = OracleModelScorer(db, catalog=catalog, bindings=resolved)

    registry = PluginRegistry(
        retrievers={
            "column_order": col,
            "filter": filt,
            "candidate_ids": ids,
            "candidate_attributes": filt,
            "text_search": text,
            "similarity": sim,
        },
        scorers={"score_ensemble": model_scorer, "passthrough": MockScorer()},
        reorderers={},
        filters={
            "expression": MockExpressionFilter(),
            "prebuilt": SqlPrebuiltFilter(ex, bindings=resolved, default_backend="oracle"),
            "truncate": MockExpressionFilter(),
        },
        kv=OracleKvStore(db, binding=resolved.pagination_kv),
    )
    registry._recql_bindings = resolved  # type: ignore[attr-defined]
    registry._recql_catalog = catalog  # type: ignore[attr-defined]
    registry._recql_encoder = encoder  # type: ignore[attr-defined]
    registry._recql_plugin_cfg = cfg  # type: ignore[attr-defined]
    registry._recql_model_scorer = model_scorer  # type: ignore[attr-defined]
    registry._recql_oracle_text = use_oracle_text  # type: ignore[attr-defined]
    registry._recql_db = db  # type: ignore[attr-defined]
    if warm_models and catalog is not None and catalog.models:
        try:
            await model_scorer.warm()
        except Exception:
            pass
    return registry

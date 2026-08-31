"""Oracle 26ai retrievers — similarity/text stay here; template CRUD in sql_common."""

from __future__ import annotations

import array
from typing import Any

from recql.catalog.bindings import DataBindings
from recql.catalog.query_templates import QueryRenderer
from recql.encode import encode_query
from recql.errors import ExecuteError
from recql.execute.merge import Candidate, RetrieveBag
from recql.language import ast as A
from recql.plugins.base import RetrieveRequest, Retriever
from recql_oracle.db import OracleDb, fetch_all, fetch_one
from recql_oracle.pushdown import assert_pushdown_or_raise, supports_prefilter
from recql.plugins.sql_common import (
    attrs_dict,
    bindings_for_request,
    resolve_param,
)

_attrs = attrs_dict
_resolve_param = resolve_param


def _bindings(req: RetrieveRequest) -> DataBindings:
    return bindings_for_request(req, default_backend="oracle")


def _as_float_vector(value: Any) -> array.array:
    """Normalize Oracle VECTOR / list / array into a float32 array.array for binds."""
    if isinstance(value, array.array):
        if value.typecode == "f":
            return value
        return array.array("f", [float(x) for x in value])
    if hasattr(value, "tolist"):
        return array.array("f", [float(x) for x in value.tolist()])
    return array.array("f", [float(x) for x in value])


def _db(handle: Any) -> OracleDb:
    return handle if isinstance(handle, OracleDb) else OracleDb(handle)


class OracleSimilarityRetriever(Retriever):
    def __init__(
        self,
        db: Any,
        *,
        dims: int = 8,
        plugin_cfg: dict[str, Any] | None = None,
        bindings: DataBindings | None = None,
    ) -> None:
        self.db = _db(db)
        self.dims = dims
        self.plugin_cfg = plugin_cfg or {}
        self.bindings = bindings

    def supports_prefilter(self, expr: A.Expr | str | None) -> bool:
        return supports_prefilter("similarity", expr)

    async def lookup_vector(
        self,
        embedding_ref: str,
        entity_type: str,
        entity_id: str,
        *,
        req: RetrieveRequest | None = None,
    ) -> list[float] | None:
        bindings = self.bindings or (_bindings(req) if req else None)
        if not bindings:
            return None
        renderer = QueryRenderer(bindings)
        emb = bindings.embedding_store_for(str(embedding_ref or "als"), entity_type)
        emb_name = str(embedding_ref) if emb.name_column else None
        lookup_structural, lookup_binds = renderer.embedding_structural(
            emb,
            embedding_name=emb_name,
            entity_type=entity_type if emb.entity_type_column else None,
        )
        sql, args = renderer.render(
            "embedding_lookup",
            structural=lookup_structural,
            binds={"entity_id": str(entity_id), **lookup_binds},
            store=emb,
        )
        row = await fetch_one(self.db, sql, args)
        if row is not None and row.get("embedding") is not None:
            vec = _as_float_vector(row["embedding"])
            return list(vec) if vec is not None else None
        return None

    async def lookup_vectors(
        self,
        embedding_ref: str,
        entity_type: str,
        entity_ids: list[str],
        *,
        req: RetrieveRequest | None = None,
    ) -> dict[str, list[float]]:
        out: dict[str, list[float]] = {}
        for eid in entity_ids:
            v = await self.lookup_vector(embedding_ref, entity_type, eid, req=req)
            if v is not None:
                out[eid] = v
        return out

    async def lookup_interactions(
        self,
        user_id: str,
        limit: int = 10,
        *,
        req: RetrieveRequest | None = None,
    ) -> list[str]:
        bindings = self.bindings or (_bindings(req) if req else None)
        if not bindings:
            return []
        renderer = QueryRenderer(bindings)
        inter = bindings.interactions
        sql, args = renderer.render(
            "interaction_items_for_user",
            structural=renderer.entity_structural(inter),
            binds={"entity_id": str(user_id), "limit": limit},
            entity=inter,
        )
        rows = await fetch_all(self.db, sql, args)
        return [str(r["item_id"]) for r in rows[:limit]]

    async def retrieve(self, req: RetrieveRequest) -> RetrieveBag:
        step = req.step
        name = getattr(step, "name", None) or "similarity"
        limit = int(getattr(step, "limit", 100) or 100)
        where = getattr(step, "where", None)
        if where is not None:
            assert_pushdown_or_raise("similarity", where)
        bindings = self.bindings or _bindings(req)
        renderer = QueryRenderer(bindings)
        items = bindings.entity(req.entity_type)
        emb_ref = getattr(step, "embedding_ref", None) or "als"
        enc = getattr(step, "query_encoder", None)
        etype = getattr(enc, "type", None) if enc is not None else None
        metric = str(self.plugin_cfg.get("vector_distance") or "COSINE").upper()

        qvec = getattr(step, "query_vector", None) or (
            req.params.get("__query_vector__") if req.params else None
        )
        if qvec is None and etype == "vector":
            qvec = getattr(enc, "vector", None)

        if qvec is not None:
            qvec_arr = _as_float_vector(qvec)
        elif etype == "precomputed_user":
            uid = str(_resolve_param(enc.input_user_id, req.params or {}))
            vec = await self.lookup_vector(str(emb_ref), "user", uid, req=req)
            if vec is None:
                return RetrieveBag(name=str(name), candidates=[])
            qvec_arr = _as_float_vector(vec)
        elif etype == "precomputed_item":
            iid = str(_resolve_param(enc.input_item_id, req.params or {}))
            vec = await self.lookup_vector(str(emb_ref), "item", iid, req=req)
            if vec is None:
                return RetrieveBag(name=str(name), candidates=[])
            qvec_arr = _as_float_vector(vec)
        elif etype == "interaction_pooling":
            from recql.encode.pooling import pool_vectors

            uid = str(_resolve_param(enc.input_user_id, req.params or {}))
            trunc = int(getattr(enc, "truncate_interactions", 10) or 10)
            item_ids = await self.lookup_interactions(uid, limit=trunc, req=req)
            if not item_ids:
                return RetrieveBag(name=str(name), candidates=[])
            vecs_map = await self.lookup_vectors(str(emb_ref), "item", item_ids, req=req)
            vec_list = [vecs_map[i] for i in item_ids if i in vecs_map]
            if not vec_list:
                return RetrieveBag(name=str(name), candidates=[])
            p_func = str(getattr(enc, "pooling_function", "mean") or "mean")
            pooled = pool_vectors(vec_list, pooling_function=p_func)
            qvec_arr = _as_float_vector(pooled)
        else:
            raise ExecuteError(f"encoder type {etype} not implemented yet")

        search_emb = bindings.embedding_store_for(str(emb_ref), req.entity_type)
        search_name = str(emb_ref) if search_emb.name_column else None
        search_structural, search_binds = renderer.embedding_structural(
            search_emb,
            embedding_name=search_name,
            entity_type=req.entity_type if search_emb.entity_type_column else None,
        )
        sql, args = renderer.render(
            "embedding_similarity_search",
            structural={
                **renderer.entity_structural(items),
                **search_structural,
                "vector_distance_metric": metric,
            },
            binds={"query_vector": qvec_arr, "limit": limit, **search_binds},
            store=search_emb,
        )
        rows = await fetch_all(self.db, sql, args)
        return RetrieveBag(
            name=str(name),
            candidates=[
                Candidate(
                    id=str(r["entity_id"]),
                    retrieval_score=float(r.get("score") or 0.0),
                    attributes=_attrs(r.get("attrs")),
                )
                for r in rows
            ],
        )


class OracleTextSearchRetriever(Retriever):
    def __init__(
        self,
        db: Any,
        *,
        encoder=None,
        plugin_cfg: dict[str, Any] | None = None,
        use_oracle_text: bool = False,
        bindings: DataBindings | None = None,
    ) -> None:
        self.db = _db(db)
        self.encoder = encoder
        self.plugin_cfg = plugin_cfg or {}
        self.use_oracle_text = use_oracle_text
        self.bindings = bindings

    def supports_prefilter(self, expr: A.Expr | str | None) -> bool:
        return supports_prefilter("text_search", expr)

    async def retrieve(self, req: RetrieveRequest) -> RetrieveBag:
        step = req.step
        name = getattr(step, "name", None) or "text_search"
        limit = int(getattr(step, "limit", 100) or 100)
        where = getattr(step, "where", None)
        if where is not None:
            assert_pushdown_or_raise("text_search", where)
        bindings = self.bindings or _bindings(req)
        renderer = QueryRenderer(bindings)
        items = bindings.entity(req.entity_type)
        q = _resolve_param(getattr(step, "input_text_query", ""), req.params or {})
        mode = step.mode
        mtype = getattr(mode, "type", None) or (
            mode.get("type") if isinstance(mode, dict) else None
        )
        label = int(self.plugin_cfg.get("text_score_label") or 1)

        if mtype == "vector":
            ref = getattr(mode, "text_embedding_ref", None) or (
                mode.get("text_embedding_ref") if isinstance(mode, dict) else None
            )
            ref = ref or "content_embedding"
            emb = bindings.embedding_store_for(str(ref), req.entity_type)
            metric = str(self.plugin_cfg.get("vector_distance") or "COSINE").upper()
            qvec = array.array("f", encode_query(str(q), encoder=self.encoder))
            emb_structural, emb_binds = renderer.embedding_structural(
                emb,
                embedding_name=str(ref) if emb.name_column else None,
                entity_type=req.entity_type if emb.entity_type_column else None,
            )
            sql, args = renderer.render(
                "embedding_vector_search",
                structural={
                    **renderer.entity_structural(items),
                    **emb_structural,
                    "vector_distance_metric": metric,
                },
                binds={"query_vector": qvec, "limit": limit, **emb_binds},
                store=emb,
            )
        elif self.use_oracle_text:
            structural = {
                **renderer.entity_structural(items),
                "text_score_label": label,
            }
            sql, args = renderer.render(
                "lexical_oracle_text",
                structural=structural,
                binds={"query_text": str(q), "limit": limit},
                entity=items,
            )
            if where:
                sql = sql.replace("ORDER BY", f"AND ({where})\nORDER BY", 1)
        else:
            # slim images lack CTXSYS; substring match over search_text CLOB
            structural = {**renderer.entity_structural(items)}
            sql, args = renderer.render(
                "lexical_like_fallback",
                structural=structural,
                binds={"query_text": f"%{str(q)}%", "limit": limit},
                entity=items,
            )
            if where:
                sql = sql.replace("ORDER BY", f"AND ({where})\nORDER BY", 1)

        rows = await fetch_all(self.db, sql, args)
        return RetrieveBag(
            name=str(name),
            candidates=[
                Candidate(
                    id=str(r["entity_id"]),
                    retrieval_score=float(r.get("score") or 0.0),
                    attributes=_attrs(r.get("attrs")),
                )
                for r in rows
            ],
        )



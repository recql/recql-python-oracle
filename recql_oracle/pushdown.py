"""Oracle 26ai prefilter pushdown capability matrix.

Same fail-closed contract as Postgres: each retriever declares which ``where=``
shapes it can enforce in SQL. Matrix is Oracle-plugin-local (not a shared dialect).
"""

from __future__ import annotations

from recql.language import ast as A
from recql.plugins.prefilter import (
    PrefilterShape,
    PushdownCapability,
    assert_pushdown_or_raise as _assert,
    classify_prefilter,
    supports_prefilter as _supports,
)

ORACLE_PUSHDOWN: dict[str, PushdownCapability] = {
    "filter": PushdownCapability(
        "filter",
        frozenset({PrefilterShape.ARBITRARY}),
        "Full SQL WHERE fragment.",
    ),
    "candidate_attributes": PushdownCapability(
        "candidate_attributes",
        frozenset({PrefilterShape.ARBITRARY}),
        "Same as filter retrieve.",
    ),
    "column_order": PushdownCapability(
        "column_order",
        frozenset(
            {
                PrefilterShape.EQUALITY,
                PrefilterShape.IN_LIST,
                PrefilterShape.AND_OR,
            }
        ),
        "Equality / IN / AND-OR only.",
    ),
    "text_search": PushdownCapability(
        "text_search",
        frozenset({PrefilterShape.EQUALITY, PrefilterShape.AND_OR}),
        "Equality conjuncts alongside CONTAINS / VECTOR_DISTANCE.",
    ),
    "similarity": PushdownCapability(
        "similarity",
        frozenset(),
        "No ANN+prefilter pushdown in v1; where= fails closed.",
    ),
    "candidate_ids": PushdownCapability(
        "candidate_ids",
        frozenset(),
        "IDs list is the selection; where= not supported.",
    ),
}


def supports_prefilter(retriever_type: str, expr: A.Expr | str | None) -> bool:
    return _supports(ORACLE_PUSHDOWN, retriever_type, expr)


def assert_pushdown_or_raise(retriever_type: str, expr: A.Expr | str | None) -> None:
    _assert(ORACLE_PUSHDOWN, retriever_type, expr)


__all__ = [
    "ORACLE_PUSHDOWN",
    "PrefilterShape",
    "PushdownCapability",
    "assert_pushdown_or_raise",
    "classify_prefilter",
    "supports_prefilter",
]

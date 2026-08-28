"""Oracle testbed — seeds demo data once, exposes ``recql_testbed``."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from recql.catalog import load_engine_catalog
from recql.testing import RecqlTestbed, SQL_BACKEND_FEATURES
from recql_oracle.connect import open_connection, parse_oracle_dsn

DSN = os.environ.get(
    "RECQL_ORACLE_DSN",
    "oracle://recql:RecqlPass1@127.0.0.1:1522/FREEPDB1",
)


def _resolve_engine() -> Path:
    if os.environ.get("RECQL_ENGINE"):
        return Path(os.environ["RECQL_ENGINE"])
    local = Path(__file__).resolve().parents[1] / "testdata" / "engine.yaml"
    if local.is_file():
        return local
    pytest.skip("engine.yaml not found — set RECQL_ENGINE")


@pytest.fixture(scope="session")
async def recql_testbed():
    try:
        import oracledb
    except ImportError:
        pytest.skip("oracledb missing")

    try:
        from examples.generator.catalog import build_demo_catalog
        from examples.generator.oracle.load import load_catalog
    except ImportError:
        pytest.skip("recql-playground required for seeding")

    user, password, easy = parse_oracle_dsn(DSN)
    try:
        conn = await oracledb.connect_async(user=user, password=password, dsn=easy)
        await conn.close()
    except Exception as e:
        pytest.skip(f"Oracle unavailable — run `make up` ({e})")

    catalog_demo = build_demo_catalog(
        dims=8,
        with_als=True,
        with_lgbm=True,
        max_movies=100,
        max_ratings=4000,
        als_max_users=50,
        als_max_items=150,
        als_steps=5,
    )
    conn = await oracledb.connect_async(user=user, password=password, dsn=easy)
    try:
        await load_catalog(conn, catalog_demo)
    finally:
        await conn.close()

    catalog = load_engine_catalog(_resolve_engine())
    registry, closer = await open_connection(DSN, catalog=catalog)
    bed = RecqlTestbed(
        backend="oracle",
        registry=registry,
        catalog=catalog,
        dims=8,
        popular_rank_column="derived_popular_rank",
        features=SQL_BACKEND_FEATURES,
    )
    yield bed
    await closer()

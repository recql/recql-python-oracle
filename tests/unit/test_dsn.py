"""Oracle-specific helpers (DSN parsing)."""

from __future__ import annotations

from recql_oracle.connect import parse_oracle_dsn


def test_parse_oracle_dsn_full():
    user, password, easy = parse_oracle_dsn(
        "oracle://recql:RecqlPass1@127.0.0.1:1522/FREEPDB1"
    )
    assert user == "recql"
    assert password == "RecqlPass1"
    assert easy == "127.0.0.1:1522/FREEPDB1"


def test_parse_oracle_dsn_bare_falls_back_to_env(monkeypatch):
    monkeypatch.setenv("ORACLE_USER", "u")
    monkeypatch.setenv("ORACLE_PASSWORD", "p")
    user, password, easy = parse_oracle_dsn("dbhost:1521/XEPDB1")
    assert user == "u"
    assert password == "p"
    assert easy == "dbhost:1521/XEPDB1"

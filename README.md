# recql-oracle

Standalone RecQL backend for Oracle 26ai.

## Conformance tests

```bash
# Recommended — DB + pytest in Docker (no local Python required)
make test-conformance-docker

# If Oracle dies with exit 88 / ORA-00600 ksipc (often a half-init volume
# or port clash with another Oracle on 1521):
make reset && make test-conformance-docker
```

Host port defaults to **1522** (`ORACLE_PORT`) so it does not collide with
playground/monorepo Oracle on 1521. Inside Compose the DSN still uses
`oracle:1521`.

Sibling checkouts (override with env):

- `RECQL_CORE_PATH=../recql-python-core`
- `RECQL_PLAYGROUND_PATH=../recql-playground`

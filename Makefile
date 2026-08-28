.DEFAULT_GOAL := help

COMPOSE ?= docker compose
PYTHON ?= $(shell command -v python3 2>/dev/null || command -v python 2>/dev/null || echo python3)
PYTEST ?= $(PYTHON) -m pytest
# Host port 1522 by default (compose maps → container 1521). Avoids clash with
# playground/monorepo Oracle on 1521.
ORACLE_PORT ?= 1522
DSN ?= oracle://recql:RecqlPass1@127.0.0.1:$(ORACLE_PORT)/FREEPDB1

RECQL_CORE_PATH ?= ../recql-python-core
RECQL_PLAYGROUND_PATH ?= ../recql-playground

export ORACLE_PORT
export RECQL_CORE_PATH
export RECQL_PLAYGROUND_PATH

.PHONY: help up down reset logs test test-unit test-conformance test-conformance-docker build-conformance

help: ## Show targets
	@awk 'BEGIN {FS = ":.*## "}; /^[a-zA-Z0-9_-]+:.*## / {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@printf '\nIf Oracle exits with code 88 (ksipc / bad volume):\n'
	@printf '  make reset && make test-conformance-docker\n'
	@printf 'Default host port is $(ORACLE_PORT) (set ORACLE_PORT=… to override).\n'

up: ## Start Oracle Free (first boot can take several minutes)
	$(COMPOSE) up -d oracle
	@echo "waiting for healthy… (host DSN=$(DSN))"
	@for i in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30; do \
	  st=$$($(COMPOSE) ps oracle --format '{{.Health}}' 2>/dev/null || true); \
	  if [ "$$st" = "healthy" ]; then echo "oracle healthy"; exit 0; fi; \
	  if $(COMPOSE) ps -a oracle --format '{{.Status}}' 2>/dev/null | grep -qi exited; then \
	    echo "oracle exited — see: make logs"; \
	    echo "try: make reset && make up"; \
	    exit 1; \
	  fi; \
	  sleep 10; \
	done; \
	echo "timed out waiting for healthy"; exit 1

down: ## Stop containers (keep volumes)
	$(COMPOSE) down

reset: ## Wipe Oracle volume (fixes exit 88 / half-init) and stop
	$(COMPOSE) down -v

logs: ## Tail Oracle container logs
	$(COMPOSE) logs -f oracle

build-conformance: ## Build the conformance runner image
	$(COMPOSE) --profile conformance build conformance

test-unit: ## Backend-specific unit tests (no DB)
	@command -v $(PYTHON) >/dev/null || { echo "No $(PYTHON) on PATH"; exit 127; }
	$(PYTEST) tests/unit -q

test-conformance: ## Shared suite on the host (needs make up + local installs)
	@command -v $(PYTHON) >/dev/null || { echo "No $(PYTHON) on PATH — use: make test-conformance-docker"; exit 127; }
	RECQL_ORACLE_DSN=$(DSN) $(PYTEST) tests/ -q

test-conformance-docker: ## Start Oracle + run suite inside Docker (recommended)
	@# Bring DB up first so a crash is visible before the runner build noise.
	@$(MAKE) up
	$(COMPOSE) --profile conformance run --rm --build conformance

test: test-conformance-docker ## Default: full docker conformance

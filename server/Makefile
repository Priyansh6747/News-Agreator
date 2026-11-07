HOST ?= 127.0.0.1
PORT ?= 8012
LAYA_DEVICE ?= cuda
EVAL_DEVICE ?= cpu
QUERY ?= gold prices
URL ?=

.DEFAULT_GOAL := help

.PHONY: help sync sync-base lock test lint check run demo eval probe-sources probe-clusters probe-enrich demo-brief

help: ## Show the available targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-18s %s\n", $$1, $$2}'

sync: ## Install base + optional Laya dependencies (torch/transformers)
	uv sync --extra laya

sync-base: ## Install only the base server dependencies (no Laya)
	uv sync

lock: ## Refresh uv.lock after dependency changes
	uv lock

test: ## Run the test suite
	uv run pytest -q

lint: ## Run ruff
	uv run ruff check .

check: test lint ## Run tests and lint

run: ## Run dev server: real retrieval + Laya
	NEWS_APP_ENV=dev NEWS_LAYA_DEVICE=$(LAYA_DEVICE) uv run uvicorn main:app --host $(HOST) --port $(PORT)

demo: ## Run the fixture-only demo server
	NEWS_APP_ENV=demo uv run uvicorn main:app --host $(HOST) --port $(PORT)

eval: ## Compare heuristic vs Laya on Docs/eval
	NEWS_LAYA_DEVICE=$(EVAL_DEVICE) uv run python debug/eval_laya.py --engine both --out ../../Docs/eval/laya-report.md

probe-sources: ## Probe live retrieval for a query
	uv run python debug/probe_sources.py "$(QUERY)"

probe-clusters: ## Cluster all live candidates for a query
	uv run python debug/probe_clusters.py "$(QUERY)"

probe-enrich: ## Resolve/fetch/extract one URL (usage: make probe-enrich URL=...)
	@test -n "$(URL)" || (echo "usage: make probe-enrich URL=<url>"; exit 1)
	uv run python debug/probe_enrich.py "$(URL)"

demo-brief: ## Run the fixture pipeline and print a brief
	uv run python debug/demo_brief.py "$(QUERY)"

PYTHON ?= python3.11
VENV := .venv
PY := $(VENV)/bin/python
DBT := $(VENV)/bin/dbt
export DBT_PROFILES_DIR := .
export DBT_TARGET_PATH := warehouse/target
export DBT_LOG_PATH := warehouse/logs
# Snapshots after AS_OF are invisible to the build. The nightly job overrides it to see everything.
AS_OF ?= $(shell cat data/PINNED 2>/dev/null || echo 9999-12-31)
export AS_OF
DBT_VARS := --vars '{as_of: "$(AS_OF)"}'

.PHONY: help setup ingest backfill warehouse fingerprints verify catalog site docs thesis query all clean

help:  ## Show the available commands
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | sed -E 's/:.*## /\t/' | expand -t 12

setup:  ## Create .venv and install the pinned toolchain (needs network, once)
	$(PYTHON) -m venv $(VENV)
	$(PY) -m pip install -q --disable-pip-version-check --only-binary :all: -r requirements.lock
	@echo "Setup complete: $$($(PY) -m pip list --format=freeze | wc -l | tr -d ' ') packages installed"

ingest:  ## Fetch today's data into data/bronze (needs network; keys in .env are optional)
	$(PY) -m ingest run --profile nightly

backfill:  ## Run the long history jobs; safe to stop and restart (needs network)
	$(PY) -m ingest run --profile backfill

warehouse:  ## Rebuild data/warehouse.duckdb and data/gold from committed bronze (no network, no keys)
	rm -f data/warehouse.duckdb data/warehouse.duckdb.wal
	$(DBT) seed --quiet --full-refresh $(DBT_VARS)
	$(DBT) run --quiet $(DBT_VARS)
	$(PY) -m tools.export_gold
	@echo "Warehouse built as of $(AS_OF): see data/warehouse.duckdb and data/gold/"

fingerprints:  ## Record the gold tables' fingerprints after a real data or model change
	$(PY) -m tools.export_gold --write-fingerprints

verify:  ## Check hashes, data tests, reconciliation and fingerprints (no network, no keys)
	$(PY) -m tools.verify

catalog:  ## Regenerate docs/DATA_CATALOG.md, docs/RECONCILIATION.md and the README's expected results
	$(DBT) docs generate --quiet $(DBT_VARS)
	$(PY) -m tools.catalog

site:  ## Rebuild every number and chart on the dashboard from the warehouse, into site/ (no network, no keys)
	$(PY) -m tools.site_data
	$(PY) -m tools.site_catalog
	$(PY) -m tools.site_stamp
	@# The guide is rebuilt with the dashboard. A gold table it has no history line for stops the guide, not the dashboard.
	-$(PY) -m tools.docsite
	@echo "Site built as of $(AS_OF): open site/index.html"

docs:  ## Rebuild the guide to every gold table and field, into site/docs/ (no network, no keys)
	$(PY) -m tools.docsite

thesis:  ## Rewrite THESIS.md from the claim scorecard in the warehouse (no network, no keys)
	$(PY) -m tools.thesis

query:  ## Run SQL against the warehouse: make query SQL="select * from gold.fct_mpc_state"
	@$(PY) -m tools.query "$(SQL)"

all: setup warehouse verify site thesis  ## The judge path: setup, build, check, the dashboard and the thesis

clean:  ## Remove the warehouse and dbt build output (bronze stays)
	rm -f data/warehouse.duckdb data/warehouse.duckdb.wal
	rm -rf warehouse/target warehouse/logs logs

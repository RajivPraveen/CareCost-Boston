#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
.venv/bin/carecost --db data/processed/boston.sqlite ingest config/boston_sources.json --download
if [[ -d data/models/bge-small-en-v1.5 ]]; then
  .venv/bin/python scripts/build_search_index.py
fi
.venv/bin/python scripts/audit_live_prices.py
.venv/bin/python scripts/report_live_data.py

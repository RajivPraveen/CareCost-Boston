.PHONY: setup data refresh demo app test evaluate lint
setup:
	python3.11 -m venv .venv
	.venv/bin/pip install -e '.[dev]'
data:
	.venv/bin/carecost ingest config/boston_sources.json --download
refresh:
	./scripts/refresh.sh
demo:
	.venv/bin/carecost demo
app:
	.venv/bin/streamlit run app.py
test:
	.venv/bin/pytest -q
lint:
	.venv/bin/ruff check .
evaluate:
	.venv/bin/carecost --db data/processed/demo.sqlite evaluate

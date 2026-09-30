"""Prepare local procedure search once after a hospital-data refresh."""

import os
from pathlib import Path

from carecost.repository import load_public_overview
from carecost.search import ProcedureSearch, load_search_catalog

database = os.getenv("CARECOST_DB", "data/processed/boston.sqlite")
model = os.getenv("CARECOST_EMBEDDING_MODEL", "data/models/bge-small-en-v1.5")
stamp = tuple(
    (Path(p).stat().st_mtime_ns, Path(p).stat().st_size)
    for p in [database, database + "-wal"]
    if Path(p).exists()
)
catalog = load_search_catalog(database, stamp)
load_public_overview(database, stamp)
ProcedureSearch(catalog, model_path=model)
print(f"Local search ready for {len(catalog):,} procedure descriptions")

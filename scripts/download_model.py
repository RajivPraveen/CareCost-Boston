"""Explicit one-time public model download. Never reads or sends patient content."""

from pathlib import Path

from sentence_transformers import SentenceTransformer

path = Path("data/models/bge-small-en-v1.5")
model = SentenceTransformer("BAAI/bge-small-en-v1.5", trust_remote_code=False)
model.save(str(path))
print(f"Saved local model to {path.resolve()}")
database = Path("data/processed/boston.sqlite")
if database.exists():
    from carecost.repository import load_public_overview
    from carecost.search import ProcedureSearch, load_search_catalog

    stamp = tuple(
        (item.stat().st_mtime_ns, item.stat().st_size)
        for item in [database, Path(str(database) + "-wal")]
        if item.exists()
    )
    catalog = load_search_catalog(database, stamp)
    load_public_overview(database, stamp)
    ProcedureSearch(catalog, model_path=str(path))
    print(f"Prepared local search index for {len(catalog):,} procedure descriptions")
print("Semantic search is ready when the app starts.")

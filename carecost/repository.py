from __future__ import annotations

import json
import math
import sqlite3
import tempfile
from hashlib import sha256
from pathlib import Path

from carecost.models import Price

SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS hospitals (hospital_id TEXT PRIMARY KEY, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS prices (
  price_id TEXT PRIMARY KEY, hospital_id TEXT NOT NULL, code TEXT NOT NULL,
  code_type TEXT NOT NULL, price_type TEXT NOT NULL, payer TEXT NOT NULL, plan TEXT NOT NULL,
  setting TEXT NOT NULL, billing_class TEXT NOT NULL, modifiers TEXT NOT NULL,
  amount REAL NOT NULL, source_date TEXT NOT NULL, source_sha256 TEXT NOT NULL,
  is_demo INTEGER NOT NULL, payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS price_search ON prices(code, code_type, price_type, hospital_id);
CREATE TABLE IF NOT EXISTS quarantine (
  id INTEGER PRIMARY KEY, run_id TEXT NOT NULL, source_row INTEGER NOT NULL,
  reason TEXT NOT NULL, payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ingestion_runs (
  run_id TEXT PRIMARY KEY, hospital_id TEXT NOT NULL, source_url TEXT NOT NULL,
  sha256 TEXT NOT NULL, accepted INTEGER NOT NULL, rejected INTEGER NOT NULL,
  duplicates INTEGER NOT NULL, finished_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


class Repository:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript(SCHEMA)

    def close(self):
        self.connection.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def hospitals(self):
        return {
            r["hospital_id"]: json.loads(r["payload"])
            for r in self.connection.execute("SELECT * FROM hospitals ORDER BY hospital_id")
        }

    def query(self, **filters) -> list[Price]:
        allowed = {
            "hospital_id",
            "code",
            "code_type",
            "price_type",
            "payer",
            "plan",
            "setting",
            "billing_class",
            "modifiers",
            "is_demo",
        }
        if not set(filters) <= allowed:
            raise ValueError("Unsupported filter")
        sql = "SELECT payload FROM prices"
        if filters:
            sql += " WHERE " + " AND ".join(f"{k} = ?" for k in filters)
        sql += " ORDER BY amount, hospital_id, price_id"
        return [Price.model_validate_json(r[0]) for r in self.connection.execute(sql, list(filters.values()))]

    def for_codes(self, hospital_id, codes):
        codes = sorted(set(codes))
        if not codes:
            return []
        placeholders = ",".join("?" for _ in codes)
        return [
            Price.model_validate_json(r[0])
            for r in self.connection.execute(
                f"SELECT payload FROM prices WHERE hospital_id=? AND code IN ({placeholders})",
                [hospital_id, *codes],
            )
        ]

    def catalog(self):
        rows = self.connection.execute(
            "SELECT code,code_type,MIN(json_extract(payload,'$.description')) description "
            "FROM prices GROUP BY code,code_type ORDER BY code,code_type"
        )
        return [dict(r) for r in rows]

    def statistics(self):
        return dict(
            self.connection.execute(
                "SELECT COUNT(*) prices, COUNT(DISTINCT hospital_id) hospitals, "
                "COUNT(DISTINCT code_type || ':' || code) procedures, MAX(source_date) latest, "
                "COALESCE(SUM(is_demo),0) demo_prices FROM prices"
            ).fetchone()
        )


def load_public_overview(database, snapshot_stamp, index_dir="data/index"):
    """Reuse public hospital counts and locations for an unchanged database snapshot."""
    directory = Path(index_dir)
    cache_key = sha256(
        json.dumps([str(Path(database).resolve()), snapshot_stamp]).encode("utf-8")
    ).hexdigest()[:20]
    cache_file = directory / f"overview-{cache_key}.json"
    if cache_file.exists():
        data = json.loads(cache_file.read_text())
        return data["statistics"], data["hospitals"]
    with Repository(database) as repo:
        statistics, hospitals = repo.statistics(), repo.hospitals()
    directory.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=directory, delete=False) as temporary:
        json.dump({"statistics": statistics, "hospitals": hospitals}, temporary, ensure_ascii=False)
    Path(temporary.name).replace(cache_file)
    return statistics, hospitals


def distance_miles(lat1, lon1, lat2, lon2):
    a, b = math.radians(float(lat1)), math.radians(float(lat2))
    dlat, dlon = b - a, math.radians(float(lon2) - float(lon1))
    v = math.sin(dlat / 2) ** 2 + math.cos(a) * math.cos(b) * math.sin(dlon / 2) ** 2
    return 3958.7613 * 2 * math.asin(min(1, math.sqrt(v)))

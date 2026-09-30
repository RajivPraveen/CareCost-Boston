"""Generate a public-data coverage/variation report from the active Boston snapshot."""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

conn = sqlite3.connect("data/processed/boston.sqlite")
conn.row_factory = sqlite3.Row
systems = sorted(
    {h["hospital"]["health_system"] for h in json.loads(Path("config/boston_sources.json").read_text())}
)
stats = dict(
    conn.execute(
        "SELECT count(*) prices,count(distinct hospital_id) hospitals,count(distinct code_type || code) procedures,max(source_date) published FROM prices"
    ).fetchone()
)
runs = [
    dict(r)
    for r in conn.execute(
        "SELECT hospital_id,source_url,sha256,accepted,rejected,duplicates,finished_at FROM ingestion_runs r WHERE EXISTS (SELECT 1 FROM prices p WHERE p.hospital_id=r.hospital_id AND p.source_sha256=r.sha256)"
    )
]
rows = [
    dict(r)
    for r in conn.execute("""
WITH cash AS (
SELECT hospital_id,code,code_type,setting,billing_class,modifiers,amount,
 json_extract(payload,'$.description') description FROM prices WHERE price_type='cash'
), unique_quotes AS (
SELECT hospital_id,code,code_type,description,setting,billing_class,modifiers,min(amount) amount
FROM cash GROUP BY hospital_id,code,code_type,description,setting,billing_class,modifiers
HAVING count(distinct amount)=1
)
SELECT code,code_type,description,setting,billing_class,modifiers,count(distinct hospital_id) hospitals,
 min(amount) min_cash,max(amount) max_cash,round(max(amount)/min(amount),3) max_min_ratio
FROM unique_quotes GROUP BY code,code_type,description,setting,billing_class,modifiers
HAVING count(distinct hospital_id)>=2 ORDER BY max_min_ratio DESC,code
""")
]
common_codes = {
    "73721",
    "70551",
    "71046",
    "45378",
    "80053",
    "85025",
    "80061",
    "83036",
    "93306",
    "93000",
    "97110",
}
common = [r for r in rows if r["code"] in common_codes and r["setting"] == "both" and not r["modifiers"]]
report = dict(
    generated_at=datetime.now(timezone.utc).isoformat(),
    data=stats,
    scope=f"{stats['hospitals']} Boston-area hospitals across {len(systems)} health systems ({', '.join(systems)}); not a representative Boston market sample.",
    lineage=runs,
    comparable_cash_groups=len(rows),
    largest_observed_ratio=rows[0] if rows else None,
    common_procedures=common,
    method="Group by identical code system, code, exact published description, setting, billing class and modifiers; exclude hospital groups with multiple distinct amounts. Some sources do not identify billing class. Identical wording is not proof of identical inclusions.",
    exclusions=[
        dict(r)
        for r in conn.execute(
            "SELECT reason,count(*) records FROM quarantine GROUP BY reason ORDER BY records DESC LIMIT 12"
        )
    ],
)
Path("evaluations/live-data-report.json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps({k: v for k, v in report.items() if k not in {"lineage", "exclusions"}}, indent=2))

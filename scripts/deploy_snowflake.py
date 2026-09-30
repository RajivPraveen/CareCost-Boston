"""Provision and validate the public CareCost price snapshot in Snowflake."""

import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from carecost.warehouse import bootstrap, connect, load

load_dotenv()
source_db = Path(os.getenv("CARECOST_DB", "data/processed/boston.sqlite"))
if not source_db.exists():
    raise SystemExit(f"No local public price snapshot at {source_db}")
dbt = shutil.which("dbt")
if not dbt:
    raise SystemExit("dbt CLI not found; install the warehouse extra in this environment")
print("Creating/checking CareCost warehouse and schemas…", flush=True)
provisioned = bootstrap()
print("Loading validated public prices; bills are never uploaded…", flush=True)
loaded = load(source_db)
print("Building and testing dbt models…", flush=True)
result = subprocess.run(
    [dbt, "build", "--project-dir", "dbt", "--profiles-dir", "dbt"],
    check=False,
    env=os.environ.copy(),
)
if result.returncode:
    raise SystemExit(f"dbt build failed with exit code {result.returncode}; inspect dbt/logs/dbt.log")
with connect() as conn, conn.cursor() as cur:
    cur.execute(f"SELECT COUNT(*) FROM {provisioned['database']}.{provisioned['raw_schema']}.PRICE_RECORDS")
    raw_count = cur.fetchone()[0]
    cur.execute(f"SELECT COUNT(*) FROM {provisioned['database']}.{provisioned['mart_schema']}.FCT_PRICES")
    mart_count = cur.fetchone()[0]
    cur.execute(f"SELECT COUNT(*) FROM {provisioned['database']}.{provisioned['mart_schema']}.DIM_HOSPITALS")
    hospital_count = cur.fetchone()[0]
summary = {
    "completed_at": datetime.now(timezone.utc).isoformat(),
    "provisioned": provisioned,
    "uploaded_price_rows": loaded["loaded_prices"],
    "warehouse_raw_prices": raw_count,
    "dbt_validated_prices": mart_count,
    "dbt_hospitals": hospital_count,
    "dbt_build_passed": True,
}
if raw_count != loaded["loaded_prices"] or mart_count <= 0 or hospital_count <= 0:
    raise SystemExit(f"Snowflake counts need review: {summary}")
output = Path("data/processed/snowflake-deployment.json")
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(summary, indent=2) + "\n")
print(json.dumps(summary, indent=2))

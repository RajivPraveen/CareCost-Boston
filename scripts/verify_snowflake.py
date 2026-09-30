"""Verify the deployed public-price mart against the local validated snapshot."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from dotenv import load_dotenv

from carecost.repository import Repository
from carecost.warehouse import connect, identifier

load_dotenv()
source_db = Path(os.getenv("CARECOST_DB", "data/processed/boston.sqlite"))
deployment = json.loads(Path("data/processed/snowflake-deployment.json").read_text())
artifact = json.loads(Path("dbt/target/run_results.json").read_text())
results = artifact["results"]
if not results or any(result["status"] not in {"success", "pass"} for result in results):
    raise SystemExit("The latest dbt build did not pass")

with Repository(source_db) as repo:
    sample = repo.connection.execute(
        """SELECT p.price_id,p.hospital_id,p.code,p.price_type,p.amount,p.source_sha256
        FROM prices p JOIN (
          SELECT hospital_id,price_type,MIN(price_id) AS price_id
          FROM prices GROUP BY hospital_id,price_type
        ) s ON p.price_id=s.price_id ORDER BY p.hospital_id,p.price_type"""
    ).fetchall()
    stats = repo.statistics()
    local_count = stats["prices"]
expected = {
    row[0]: (row[1], row[2], row[3], Decimal(str(row[4])).quantize(Decimal("0.01")), row[5]) for row in sample
}

warehouse = identifier(deployment["provisioned"]["warehouse"])
database = identifier(deployment["provisioned"]["database"])
schema = identifier(deployment["provisioned"]["mart_schema"])
with connect() as connection, connection.cursor() as cursor:
    cursor.execute(f"SELECT COUNT(*) FROM {database}.{schema}.FCT_PRICES")
    mart_count = cursor.fetchone()[0]
    cursor.execute(f"SELECT COUNT(*) FROM {database}.{schema}.DIM_HOSPITALS")
    hospital_count = cursor.fetchone()[0]
    placeholders = ",".join(["%s"] * len(expected))
    cursor.execute(
        f"SELECT PRICE_ID,HOSPITAL_ID,CODE,PRICE_TYPE,AMOUNT,SOURCE_SHA256 "
        f"FROM {database}.{schema}.FCT_PRICES WHERE PRICE_ID IN ({placeholders})",
        list(expected),
    )
    found = {
        row[0]: (row[1], row[2], row[3], Decimal(str(row[4])).quantize(Decimal("0.01")), row[5])
        for row in cursor.fetchall()
    }
    cursor.execute(f"SHOW WAREHOUSES LIKE '{warehouse}'")
    columns = [description[0].lower() for description in cursor.description]
    settings = dict(zip(columns, cursor.fetchone()))

if found != expected or mart_count != local_count or hospital_count != stats["hospitals"]:
    raise SystemExit("Snowflake mart differs from the local validated snapshot")

report = {
    "verified_at": datetime.now(timezone.utc).isoformat(),
    "public_prices_local": local_count,
    "public_prices_snowflake": mart_count,
    "hospitals_snowflake": hospital_count,
    "sample_records_matched": len(expected),
    "sample_hospitals": len({row[0] for row in expected.values()}),
    "sample_price_types": sorted({row[2] for row in expected.values()}),
    "dbt_steps_passed": len(results),
    "dbt_warnings_or_errors": 0,
    "warehouse_size": settings["size"],
    "warehouse_auto_suspend_seconds": settings["auto_suspend"],
    "warehouse_auto_resume": settings["auto_resume"],
    "bills_uploaded": False,
}
output = Path("evaluations/snowflake-deployment.json")
output.write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report, indent=2))

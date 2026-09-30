"""Public-data-only Snowflake integration. Bill processing has no path into this module."""

from __future__ import annotations

import json
import os
import re
import uuid
from pathlib import Path

from carecost.models import Price
from carecost.repository import Repository


def identifier(value):
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise ValueError("Snowflake identifiers must be simple unquoted names")
    return value.upper()


def connect(provision=False):
    import snowflake.connector
    from dotenv import load_dotenv

    load_dotenv()
    required = ["SNOWFLAKE_ACCOUNT", "SNOWFLAKE_USER"]
    if not provision:
        required += ["SNOWFLAKE_WAREHOUSE", "SNOWFLAKE_DATABASE", "SNOWFLAKE_SCHEMA"]
    if any(not os.getenv(k) for k in required):
        raise ValueError("Set the Snowflake connection variables from .env.example first")
    authenticator = os.getenv("SNOWFLAKE_AUTHENTICATOR", "snowflake")
    if authenticator not in {"snowflake", "externalbrowser"}:
        raise ValueError("Unsupported Snowflake authenticator; use snowflake or externalbrowser")
    if authenticator == "snowflake" and not os.getenv("SNOWFLAKE_PASSWORD"):
        raise ValueError("Set SNOWFLAKE_PASSWORD or use externalbrowser SSO")
    options = {key.removeprefix("SNOWFLAKE_").lower(): os.environ[key] for key in required}
    options["authenticator"] = authenticator
    if authenticator == "snowflake":
        options["password"] = os.environ["SNOWFLAKE_PASSWORD"]
    if os.getenv("SNOWFLAKE_ROLE"):
        options["role"] = os.environ["SNOWFLAKE_ROLE"]
    return snowflake.connector.connect(**options)


def bootstrap():
    """Create a small, auto-suspending warehouse and public-data schemas."""
    from dotenv import load_dotenv

    load_dotenv()
    warehouse = identifier(os.getenv("SNOWFLAKE_WAREHOUSE", "CARECOST_WH"))
    database = identifier(os.getenv("SNOWFLAKE_DATABASE", "CARECOST"))
    raw = identifier(os.getenv("SNOWFLAKE_SCHEMA", "RAW"))
    mart = identifier(os.getenv("CARECOST_MART_SCHEMA", "ANALYTICS"))
    with connect(provision=True) as conn, conn.cursor() as cur:
        cur.execute(
            f"CREATE WAREHOUSE IF NOT EXISTS {warehouse} "
            "WAREHOUSE_SIZE = XSMALL AUTO_SUSPEND = 60 AUTO_RESUME = TRUE INITIALLY_SUSPENDED = TRUE"
        )
        cur.execute(f"CREATE DATABASE IF NOT EXISTS {database}")
        cur.execute(f"CREATE SCHEMA IF NOT EXISTS {database}.{raw}")
        cur.execute(f"CREATE SCHEMA IF NOT EXISTS {database}.{mart}")
    return {"warehouse": warehouse, "database": database, "raw_schema": raw, "mart_schema": mart}


def load(database):
    """Stage a full local snapshot, then publish it with one transaction.

    Chunked binding avoids keeping the price fact table in a pandas DataFrame.
    Database/schema/warehouse must be provisioned by the operator; no resource creation.
    """
    with Repository(database) as repo, connect() as conn:
        if not repo.statistics()["prices"]:
            raise ValueError("Refusing to replace warehouse prices with an empty snapshot")
        schema = identifier(os.environ["SNOWFLAKE_SCHEMA"])
        with conn.cursor() as cur:
            cur.execute(
                f"CREATE TABLE IF NOT EXISTS {schema}.PRICE_RECORDS (PRICE_ID VARCHAR, PAYLOAD VARIANT)"
            )
            cur.execute(
                f"CREATE TABLE IF NOT EXISTS {schema}.HOSPITAL_RECORDS (HOSPITAL_ID VARCHAR, PAYLOAD VARIANT)"
            )
            cur.execute("CREATE TEMPORARY TABLE CARECOST_PRICE_STAGE (PRICE_ID VARCHAR, PAYLOAD VARCHAR)")
            cur.execute(
                "CREATE TEMPORARY TABLE CARECOST_HOSPITAL_STAGE (HOSPITAL_ID VARCHAR, PAYLOAD VARCHAR)"
            )
            count = 0
            rows = repo.connection.execute("SELECT price_id,payload FROM prices")
            while batch := rows.fetchmany(5000):
                cur.executemany("INSERT INTO CARECOST_PRICE_STAGE VALUES (%s,%s)", [tuple(r) for r in batch])
                count += len(batch)
            cur.executemany(
                "INSERT INTO CARECOST_HOSPITAL_STAGE VALUES (%s,%s)",
                [(k, json.dumps(v)) for k, v in repo.hospitals().items()],
            )
            cur.execute("BEGIN")
            try:
                cur.execute(f"DELETE FROM {schema}.PRICE_RECORDS")
                cur.execute(
                    f"INSERT INTO {schema}.PRICE_RECORDS SELECT PRICE_ID, PARSE_JSON(PAYLOAD) FROM CARECOST_PRICE_STAGE"
                )
                cur.execute(f"DELETE FROM {schema}.HOSPITAL_RECORDS")
                cur.execute(
                    f"INSERT INTO {schema}.HOSPITAL_RECORDS SELECT HOSPITAL_ID, PARSE_JSON(PAYLOAD) FROM CARECOST_HOSPITAL_STAGE"
                )
                cur.execute("COMMIT")
            except Exception:
                cur.execute("ROLLBACK")
                raise
    return {"loaded_prices": count, "next": "Run dbt build before warehouse-export"}


def export(destination):
    """Export a successfully tested dbt mart to a NEW local DB for serving.

    Requires an explicit successful dbt run_results.json artifact from this project.
    The operator must use the same Snowflake environment for dbt and export.
    """
    path = Path(destination)
    if path.exists():
        raise ValueError("Export into a new filename, then set CARECOST_DB after inspecting it")
    artifact_path = Path("dbt/target/run_results.json")
    if not artifact_path.exists():
        raise ValueError("Run dbt build successfully first; run_results.json is required")
    artifact = json.loads(artifact_path.read_text())
    results = artifact.get("results", [])
    if not results or any(r.get("status") not in {"success", "pass"} for r in results):
        raise ValueError("The latest dbt build did not pass all models and tests")
    if not any(r.get("unique_id") == "model.carecost.fct_prices" for r in results):
        raise ValueError("The dbt build artifact must include the price mart")
    staging = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        with Repository(staging) as repo, connect() as conn:
            schema = identifier(os.getenv("CARECOST_MART_SCHEMA", "ANALYTICS"))
            with conn.cursor() as cur, repo.connection:
                cur.execute(f"SELECT HOSPITAL_ID, PAYLOAD FROM {schema}.DIM_HOSPITALS")
                for hid, payload in cur:
                    repo.connection.execute("INSERT INTO hospitals VALUES (?,?)", (hid, payload))
                cur.execute(f"SELECT RAW_PAYLOAD FROM {schema}.FCT_PRICES")
                for (payload,) in cur:
                    p = Price.model_validate_json(payload)
                    repo.connection.execute(
                        "INSERT INTO prices VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (
                            p.price_id,
                            p.hospital_id,
                            p.code,
                            p.code_type,
                            p.price_type,
                            p.payer,
                            p.plan,
                            p.setting,
                            p.billing_class,
                            p.modifiers,
                            float(p.amount),
                            p.source_date.isoformat(),
                            p.source_sha256,
                            int(p.is_demo),
                            p.model_dump_json(),
                        ),
                    )
            repo.connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        staging.replace(path)
    finally:
        staging.unlink(missing_ok=True)
        Path(str(staging) + "-wal").unlink(missing_ok=True)
        Path(str(staging) + "-shm").unlink(missing_ok=True)
    return {"database": str(path)}

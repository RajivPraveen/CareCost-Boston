"""Streaming CMS JSON, CMS tall/wide CSV and canonical flat CSV ingestion.

Only explicit dollar charges for a single CPT/HCPCS service enter the comparison layer.
Percentage/algorithm rates, multiple clinical codes, and unsupported code systems are
quarantined with their source context, never silently interpreted as dollar prices.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
from datetime import date, datetime
from pathlib import Path

import ijson
from pydantic import ValidationError

from carecost.models import Price, stable_id
from carecost.repository import Repository


def normalize_name(value):
    return re.sub(r"\s+", " ", str(value or "").strip()).casefold()


def normalize_payer(payer, plan, aliases):
    # Explicit full-name mappings only: PPO/HMO products must never be fuzzy-merged.
    p, q = normalize_name(payer), normalize_name(plan)
    match = aliases.get(f"{p}|{q}")
    return (match["payer"], match["plan"]) if match else (p, q)


def file_hash(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _clinical_code(codes):
    clinical = {
        (str(c.get("code", "")).strip().upper(), str(c.get("type", "")).strip().upper())
        for c in codes
        if str(c.get("type", "")).strip().upper() in {"CPT", "HCPCS"}
    }
    if len(clinical) != 1:
        raise ValueError("Requires exactly one distinct CPT/HCPCS code; unsupported or bundled codes")
    return next(iter(clinical))


def _charges(base, charges):
    found = False
    for key, kind in [("gross_charge", "gross"), ("discounted_cash", "cash")]:
        if charges.get(key) not in (None, ""):
            found = True
            yield {**base, "price_type": kind, "amount": charges[key], "payer": "", "plan": ""}
    for payer in charges.get("payers_information", []):
        found = True
        row = {
            **base,
            "price_type": "negotiated",
            "payer": payer.get("payer_name", ""),
            "plan": payer.get("plan_name", ""),
            "amount": payer.get("standard_charge_dollar"),
            "notes": json.dumps(payer, default=str),
        }
        method = normalize_name(payer.get("standard_charge_methodology"))
        if method and method != "fee schedule":
            row["_error"] = f"Negotiated rate uses {method}, not a fixed per-service fee schedule"
        if row["amount"] in (None, ""):
            row["_error"] = (
                "Non-dollar negotiated rate: percentage/algorithm/allowed statistic is not a fixed price"
            )
        yield row
    if not found:
        yield {**base, "_error": "No usable charges"}


def json_rows(path, source):
    # Read root metadata without loading a potentially multi-GB array into memory.
    publication = source.get("source_date")
    with open(path, "rb") as stream:
        if stream.read(3) != b"\xef\xbb\xbf":
            stream.seek(0)
        for prefix, event, value in ijson.parse(stream):
            if prefix == "last_updated_on" and event == "string":
                publication = value
                break
    with open(path, "rb") as stream:
        if stream.read(3) != b"\xef\xbb\xbf":
            stream.seek(0)
        count = 0
        for count, item in enumerate(ijson.items(stream, "standard_charge_information.item"), 1):
            try:
                code, code_type = _clinical_code(item.get("code_information", []))
                for charge in item.get("standard_charges", []):
                    modifiers = ",".join(
                        sorted(str(m).strip().upper() for m in charge.get("modifier_code", []))
                    )
                    base = dict(
                        code=code,
                        code_type=code_type,
                        description=item.get("description", ""),
                        setting=charge.get("setting", ""),
                        # BIDMC's published 2026 JSON uses the typo "facillity".
                        billing_class=(
                            "facility"
                            if charge.get("billing_class") == "facillity"
                            else charge.get("billing_class", "unknown")
                        ),
                        modifiers=modifiers,
                        source_row=count,
                        source_date=publication,
                        service_id=stable_id(
                            item.get("description"),
                            item.get("code_information"),
                            item.get("drug_information"),
                        ),
                        notes=charge.get("additional_generic_notes", ""),
                    )
                    if item.get("drug_information"):
                        yield {**base, "_error": "Drug unit conversion requires a dedicated adapter"}
                    else:
                        yield from _charges(base, charge)
                if not item.get("standard_charges"):
                    yield {"source_row": count, "_error": "Missing standard_charges", "raw": item}
            except (ValueError, TypeError, AttributeError) as exc:
                yield {"source_row": count, "_error": str(exc), "raw": item}
        if count == 0:
            raise ValueError("No standard_charge_information items found; use a supported CMS JSON file")


def csv_rows(path, source):
    def header_name(value):
        return "|".join(part.strip().casefold() for part in value.split("|"))

    mapping = {header_name(k): header_name(v) for k, v in source.get("column_map", {}).items()}
    defaults = source.get("defaults", {})
    if not set(defaults) <= {"code_type", "setting", "billing_class", "price_type", "payer", "plan"}:
        raise ValueError(
            "Unsupported adapter default; amounts, codes and descriptions must come from the file"
        )
    with open(path, encoding=source.get("encoding", "utf-8-sig"), newline="") as stream:
        reader = csv.reader(stream)
        metadata = {}
        previous = None
        for line, cells in enumerate(reader, 1):
            headers = [mapping.get(header_name(c), header_name(c)) for c in cells]
            if "description" in headers and ("code" in headers or "code|1" in headers):
                break
            if previous and "last_updated_on" in previous:
                metadata = dict(zip(previous, cells))
            previous = headers
            if line >= 20:
                raise ValueError("Could not find a supported CSV header in the first 20 rows")
        else:
            raise ValueError("Missing CSV header")
        if len(set(headers)) != len(headers):
            raise ValueError("Duplicate CSV headers are ambiguous")
        for row_number, cells in enumerate(reader, line + 1):
            if not any(c.strip() for c in cells):
                continue
            if len(cells) != len(headers):
                yield {"source_row": row_number, "_error": "CSV column count mismatch", "raw": cells}
                continue
            row = {**defaults, **dict(zip(headers, cells))}
            try:
                if "code" in row:
                    # Canonical flat CSV; explicit code system and care setting required.
                    codes = [{"code": row["code"], "type": row.get("code_type", "")}]
                else:
                    codes = [
                        {"code": value, "type": row.get(f"{key}|type", "")}
                        for key, value in row.items()
                        if re.fullmatch(r"code\|\d+", key) and value
                    ]
                code, kind = _clinical_code(codes)
                base = dict(
                    code=code,
                    code_type=kind,
                    description=row["description"],
                    setting=row.get("setting", "").lower(),
                    billing_class=row.get("billing_class", "unknown").lower() or "unknown",
                    modifiers=",".join(
                        sorted(
                            {
                                m.strip()
                                for m in re.split(r"[,|;]", row.get("modifiers", "").upper())
                                if m.strip()
                            }
                        )
                    ),
                    source_row=row_number,
                    source_date=(
                        datetime.strptime(
                            row.get("source_date")
                            or metadata.get("last_updated_on")
                            or source.get("source_date"),
                            source["date_format"],
                        )
                        .date()
                        .isoformat()
                        if source.get("date_format")
                        else row.get("source_date")
                        or metadata.get("last_updated_on")
                        or source.get("source_date")
                    ),
                    service_id=stable_id(row["description"], codes),
                    notes=row.get("additional_generic_notes", ""),
                )
                if row.get("drug_unit_of_measurement") or row.get("drug_type_of_measurement"):
                    yield {**base, "_error": "Drug unit conversion requires a dedicated adapter"}
                    continue
                if "price_type" in row:
                    yield {
                        **base,
                        "price_type": row["price_type"],
                        "payer": row.get("payer", ""),
                        "plan": row.get("plan", ""),
                        "amount": row.get("amount"),
                    }
                    continue
                charges = {
                    "gross_charge": row.get("standard_charge|gross"),
                    "discounted_cash": row.get("standard_charge|discounted_cash"),
                    "payers_information": [],
                }
                if row.get("payer_name"):
                    charges["payers_information"].append(
                        {
                            "payer_name": row["payer_name"],
                            "plan_name": row.get("plan_name", ""),
                            "standard_charge_dollar": row.get("standard_charge|negotiated_dollar"),
                            "standard_charge_percentage": row.get("standard_charge|negotiated_percentage"),
                            "standard_charge_algorithm": row.get("standard_charge|negotiated_algorithm"),
                            "standard_charge_methodology": row.get("standard_charge|methodology"),
                        }
                    )
                wide_payers = set()
                for key in row:
                    parts = key.split("|")
                    if (
                        len(parts) == 4
                        and parts[0] == "standard_charge"
                        and parts[3].startswith("negotiated_")
                    ):
                        wide_payers.add((parts[1], parts[2]))
                for payer, plan in sorted(wide_payers):
                    prefix = f"standard_charge|{payer}|{plan}|"
                    if any(
                        row.get(prefix + suffix)
                        for suffix in ["negotiated_dollar", "negotiated_percentage", "negotiated_algorithm"]
                    ):
                        charges["payers_information"].append(
                            {
                                "payer_name": payer,
                                "plan_name": plan,
                                "standard_charge_dollar": row.get(prefix + "negotiated_dollar"),
                                "standard_charge_percentage": row.get(prefix + "negotiated_percentage"),
                                "standard_charge_algorithm": row.get(prefix + "negotiated_algorithm"),
                            }
                        )
                yield from _charges(base, charges)
            except (ValueError, TypeError, KeyError) as exc:
                yield {"source_row": row_number, "_error": str(exc), "raw": row}


def ingest_file(repo: Repository, path, source, hospital, aliases=None):
    path = Path(path)
    digest = file_hash(path)
    run_id = stable_id(source["hospital_id"], digest, source["url"])
    accepted = rejected = duplicates = 0
    with path.open("rb") as f:
        first = f.read(4096).lstrip(b"\xef\xbb\xbf \r\n\t")[:1]
    rows = json_rows(path, source) if first == b"{" else csv_rows(path, source)
    # Atomic replace: retain the previous snapshot if parsing fails or all rows are rejected.
    with repo.connection:
        repo.connection.execute("DELETE FROM quarantine WHERE run_id=?", (run_id,))
        repo.connection.execute("DELETE FROM prices WHERE hospital_id=?", (source["hospital_id"],))
        for raw in rows:
            row_number = raw.get("source_row", 1)
            try:
                if "_error" in raw:
                    raise ValueError(raw["_error"])
                payer, plan = normalize_payer(raw.get("payer"), raw.get("plan"), aliases or {})
                data = {
                    **raw,
                    "hospital_id": source["hospital_id"],
                    "source_url": source["url"],
                    "source_sha256": digest,
                    "is_demo": bool(source.get("is_demo", False)),
                    "payer": payer,
                    "plan": plan,
                }
                price = Price.model_validate(data)
                if price.source_date > date.today():
                    raise ValueError("Publication date is in the future")
                if price.price_type == "negotiated" and (not payer or not plan):
                    raise ValueError("Negotiated prices require both payer and plan")
                if price.price_type != "negotiated" and (payer or plan):
                    raise ValueError("Cash/gross price cannot carry payer or plan")
                cur = repo.connection.execute(
                    "INSERT OR IGNORE INTO prices VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        price.price_id,
                        price.hospital_id,
                        price.code,
                        price.code_type,
                        price.price_type,
                        price.payer,
                        price.plan,
                        price.setting,
                        price.billing_class,
                        price.modifiers,
                        float(price.amount),
                        price.source_date.isoformat(),
                        digest,
                        int(price.is_demo),
                        price.model_dump_json(),
                    ),
                )
                accepted += cur.rowcount
                duplicates += 1 - cur.rowcount
            except (ValidationError, ValueError) as exc:
                rejected += 1
                repo.connection.execute(
                    "INSERT INTO quarantine(run_id,source_row,reason,payload) VALUES (?,?,?,?)",
                    (run_id, row_number, str(exc), json.dumps(raw, default=str)),
                )
        if not accepted:
            raise ValueError(
                f"No comparable prices accepted ({rejected} rejected); previous snapshot retained"
            )
        repo.connection.execute(
            "INSERT OR REPLACE INTO hospitals VALUES (?,?)", (source["hospital_id"], json.dumps(hospital))
        )
        repo.connection.execute(
            "INSERT OR REPLACE INTO ingestion_runs(run_id,hospital_id,source_url,sha256,accepted,rejected,duplicates) VALUES (?,?,?,?,?,?,?)",
            (run_id, source["hospital_id"], source["url"], digest, accepted, rejected, duplicates),
        )
    return {
        "run_id": run_id,
        "accepted": accepted,
        "quarantined": rejected,
        "duplicates": duplicates,
        "sha256": digest,
    }

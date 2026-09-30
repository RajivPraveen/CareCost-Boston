"""Sample active prices against source CSV/JSON bytes, independent of the ingestion adapter."""

import csv
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import ijson

sources = json.loads(Path("config/boston_sources.json").read_text())
conn = sqlite3.connect("data/processed/boston.sqlite")


def original_records(source, wanted):
    path = Path(source["path"])
    if path.suffix == ".json":
        with path.open("rb") as stream:
            if stream.read(3) != b"\xef\xbb\xbf":
                stream.seek(0)
            return {
                number: item
                for number, item in enumerate(ijson.items(stream, "standard_charge_information.item"), 1)
                if number in wanted
            }
    with path.open(encoding=source.get("encoding", "utf-8-sig"), newline="") as stream:
        reader = csv.reader(stream)
        for line, cells in enumerate(reader, 1):
            if cells and cells[0].strip().casefold() == "description":
                header = cells
                break
        else:
            raise ValueError(f"No CSV header: {path}")
        return {
            number: dict(zip(header, cells))
            for number, cells in enumerate(reader, line + 1)
            if number in wanted
        }


def checks_for(source, record, original, digest):
    common = {
        "source_hash": record["source_sha256"] == digest,
        "source_url": record["source_url"] == source["url"],
        "publication_date": record["source_date"] == source["source_date"],
    }
    if Path(source["path"]).suffix != ".json":
        amount_key = {
            "cash": "standard_charge|discounted_cash",
            "gross": "standard_charge|gross",
            "negotiated": "standard_charge|negotiated_dollar",
        }[record["price_type"]]
        actual_codes = {
            (original.get(f"code|{i}", "").strip(), original.get(f"code|{i}|type", "").strip())
            for i in range(1, 5)
        }
        common.update(
            amount=Decimal(record["amount"])
            == Decimal(original[amount_key]).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            code=(record["code"], record["code_type"]) in actual_codes,
            description=record["description"] == original["description"],
            setting=record["setting"] == original["setting"],
            modifiers=record["modifiers"]
            == ",".join(sorted(filter(None, original.get("modifiers", "").split(",")))),
            billing_class=record["billing_class"] == (original.get("billing_class") or "unknown"),
        )
        if record["price_type"] == "negotiated":
            common["payer"] = record["payer"] == original["payer_name"].casefold().strip()
            common["plan"] = record["plan"] == original["plan_name"].casefold().strip()
        return common
    codes = {(c.get("code"), c.get("type")) for c in original.get("code_information", [])}
    common.update(
        code=(record["code"], record["code_type"]) in codes,
        description=record["description"] == original["description"],
    )

    def matches(charge):
        amount = charge.get(
            {"cash": "discounted_cash", "gross": "gross_charge", "negotiated": "none"}[record["price_type"]]
        )
        payers = charge.get("payers_information", []) if record["price_type"] == "negotiated" else [None]
        for payer in payers:
            value = payer.get("standard_charge_dollar") if payer is not None else amount
            if value is None or Decimal(str(value)).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            ) != Decimal(record["amount"]):
                continue
            if payer is not None and (record["payer"], record["plan"]) != (
                str(payer.get("payer_name", "")).casefold().strip(),
                str(payer.get("plan_name", "")).casefold().strip(),
            ):
                continue
            actual_class = charge.get("billing_class", "unknown")
            if actual_class == "facillity":
                actual_class = "facility"
            if (record["setting"], record["billing_class"], record["modifiers"]) != (
                charge.get("setting"),
                actual_class,
                ",".join(sorted(str(x).strip().upper() for x in charge.get("modifier_code", []))),
            ):
                continue
            return True
        return False

    common["matching_charge"] = any(matches(c) for c in original.get("standard_charges", []))
    return common


audits = []
for source in sources:
    selected = []
    for kind in ["cash", "gross", "negotiated"]:
        selected.extend(
            json.loads(row[0])
            for row in conn.execute(
                "SELECT payload FROM prices WHERE hospital_id=? AND price_type=? ORDER BY price_id LIMIT 10",
                (source["hospital_id"], kind),
            )
        )
    selected.extend(
        json.loads(row[0])
        for row in conn.execute(
            "SELECT payload FROM prices WHERE hospital_id=? AND code='73721' AND price_type='cash' ORDER BY price_id LIMIT 10",
            (source["hospital_id"],),
        )
    )
    if not selected:
        raise SystemExit(f"No active prices to audit for {source['hospital_id']}")
    originals = original_records(source, {r["source_row"] for r in selected})
    with Path(source["path"]).open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    for record in selected:
        original = originals.get(record["source_row"])
        checks = (
            checks_for(source, record, original, digest) if original is not None else {"source_row": False}
        )
        audits.append(
            {
                "hospital_id": record["hospital_id"],
                "code": record["code"],
                "code_type": record["code_type"],
                "description": record["description"],
                "price_type": record["price_type"],
                "amount": record["amount"],
                "source_row": record["source_row"],
                "source_url": record["source_url"],
                "source_sha256": digest,
                "checks": checks,
                "passed": all(checks.values()),
            }
        )

result = {
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "method": "Independent source row comparison: up to 10 per price type per hospital plus knee-MRI cash entries. This is an automated audit, not clinical validation.",
    "sample_size": len(audits),
    "passed": sum(row["passed"] for row in audits),
    "rows": audits,
}
Path("evaluations/live-price-audit.json").write_text(json.dumps(result, indent=2) + "\n")
print({k: v for k, v in result.items() if k != "rows"})
if result["passed"] != len(audits):
    raise SystemExit("Source audit found mismatches")

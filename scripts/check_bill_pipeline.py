"""OCR test text -> local model -> real published price comparison (no patient data)."""

import json
from pathlib import Path

from carecost.bills import check_bill, extract_with_ollama
from carecost.repository import Repository

ocr = json.loads(Path("evaluations/ocr-smoke.json").read_text())
bill = extract_with_ollama(ocr["tests"]["PDF"]["extracted_text"], model="mistral:7b-instruct")
with Repository("data/processed/boston.sqlite") as repo:
    results = check_bill(
        bill.lines,
        repo.for_codes("mgh", [line.code for line in bill.lines]),
        "mgh",
        price_type="gross",
        setting="both",
        billing_class="unknown",
    )
passed = (
    len(results) == 1
    and results[0]["code"] == "73721"
    and results[0]["published_total"] == "3332.00"
    and any(f["type"] == "above_published" for f in results[0]["flags"])
)
output = dict(
    passed=passed,
    note="Fabricated bill from the OCR smoke test compared against the actual MGH published source. No patient bill was used.",
    results=results,
)
Path("evaluations/bill-pipeline-smoke.json").write_text(json.dumps(output, indent=2) + "\n")
print(json.dumps(output, indent=2))
if not passed:
    raise SystemExit("End-to-end bill smoke test did not match expected result")

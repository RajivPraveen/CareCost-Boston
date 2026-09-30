"""Run a synthetic local-Ollama smoke test; never load a patient bill."""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from carecost.bills import extract_with_ollama

parser = argparse.ArgumentParser()
parser.add_argument("--model", default="mistral:7b-instruct")
args = parser.parse_args()
text = (
    "SYNTHETIC BILL - NO PATIENT DATA\nDate 2026-09-01\n"
    "CPT 73721 Knee MRI quantity 1 line total $2400.00\n"
    "CPT 85025 Blood count quantity 1 line total $55.10\n"
    "CPT 85025 Blood count quantity 1 line total $55.10\n"
    "CPT 99999 Unmatched service quantity 1 line total $120.00\n"
)
bill = extract_with_ollama(text, model=args.model)
expected = [
    ("73721", "1", "2400.00"),
    ("85025", "1", "55.10"),
    ("85025", "1", "55.10"),
    ("99999", "1", "120.00"),
]
actual = [(line.code, str(line.quantity), str(line.charge)) for line in bill.lines]
result = dict(
    generated_at=datetime.now(timezone.utc).isoformat(),
    model=args.model,
    fixture="Synthetic four-line bill in scripts/check_local_ai.py",
    expected=expected,
    actual=actual,
    exact_match=actual == expected,
    extracted_bill=bill.model_dump(mode="json"),
    note="One synthetic smoke test reused during development, not an accuracy benchmark; OCR not included. Explicitly labeled codes may be recovered deterministically from source evidence.",
)
Path("evaluations/ollama-smoke.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps(result, indent=2))

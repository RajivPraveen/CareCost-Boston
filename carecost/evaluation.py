from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from carecost.bills import check_bill, extract_structured_text
from carecost.estimator import estimate_cost
from carecost.models import BillLine
from carecost.repository import Repository
from carecost.search import ProcedureSearch


def evaluate(database, output, model_path=None):
    with Repository(database) as repo:
        stats = repo.statistics()
        search = ProcedureSearch(repo.catalog(), model_path=model_path)
        labels = json.loads(Path("evaluations/search_queries.json").read_text())
        details = []
        for label in labels:
            plain = search.search(label["query"], baseline=True)
            ranked = search.search(label["query"])

            def correct(result):
                return bool(
                    result
                    and result[0]["code"] == label["expected_code"]
                    and (result[0]["code_type"] == label["code_type"] or label["expected_code"].isdigit())
                )

            details.append(
                {
                    **label,
                    "baseline_correct": correct(plain),
                    "search_correct": correct(ranked),
                    "predicted": ranked[0]["code"] if ranked else None,
                    "predicted_code_type": ranked[0]["code_type"] if ranked else None,
                    "target_available": any(
                        p["code"] == label["expected_code"]
                        and (p["code_type"] == label["code_type"] or label["expected_code"].isdigit())
                        for p in search.procedures
                    ),
                }
            )
        estimator_cases = [
            (800, 2000, 0, 0.2, None, 800),
            (2000, 2000, 1500, 0.2, None, 800),
            (1000, 2000, 2000, 0.2, None, 200),
            (1000, 0, 0, 0.2, None, 200),
            (500, 1000, 500, 0.2, None, 500),
            (1000, 1000, 1000, 0, None, 0),
            (1000, 1000, 1000, 1, None, 1000),
            (2000, 2000, 1500, 0.2, 600, 600),
            (2000, 2000, 1500, 0.2, 0, 0),
            (0, 1000, 0, 0.2, None, 0),
        ]
        estimator_pass = sum(estimate_cost(*case[:5]).patient_total == case[5] for case in estimator_cases)
        prices = repo.query(price_type="cash")
        bill_metrics = {
            "status": "not_run",
            "reason": "Planted errors are defined for the demo_harbor fixture only",
        }
        if stats["demo_prices"] == stats["prices"] and "demo_harbor" in repo.hospitals():
            bill = extract_structured_text(Path("data/demo/sample_bill.txt").read_text())
            review = check_bill(bill.lines, repo.query(hospital_id="demo_harbor"), "demo_harbor")
            found = {(r["line"], f["type"]) for r in review for f in r["flags"]}
            expected = {(1, "above_published"), (3, "possible_duplicate"), (4, "no_comparable_price")}
            # Independent manually labeled expected fields for the structured fixture.
            extraction_expected = [
                ("73721", "1", "2400.00"),
                ("85025", "1", "55.10"),
                ("85025", "1", "55.10"),
                ("99999", "1", "120.00"),
            ]
            extracted = [(item.code, str(item.quantity), str(item.charge)) for item in bill.lines]
            # A second bill with correct unit quantities and repeated services on different dates.
            clean = [
                BillLine(
                    code="73721",
                    code_type="CPT",
                    description="Knee MRI",
                    quantity=2,
                    charge=3712,
                    service_date="2026-09-01",
                ),
                BillLine(
                    code="85025",
                    code_type="CPT",
                    description="Blood count",
                    quantity=1,
                    charge="55.10",
                    service_date="2026-09-01",
                ),
                BillLine(
                    code="85025",
                    code_type="CPT",
                    description="Blood count",
                    quantity=1,
                    charge="55.10",
                    service_date="2026-09-02",
                ),
            ]
            clean_review = check_bill(clean, repo.query(hospital_id="demo_harbor"), "demo_harbor")
            clean_flags = sum(len(r["flags"]) for r in clean_review)
            bill_metrics = {
                "status": "synthetic_fixture_only",
                "planted_flags": len(expected),
                "detected": len(expected & found),
                "missed": len(expected - found),
                "false_flags": len(found - expected) + clean_flags,
                "clean_control_lines": len(clean),
                "structured_extraction_exact_lines": sum(
                    a == b for a, b in zip(extracted, extraction_expected)
                ),
                "structured_extraction_total_lines": len(extraction_expected),
                "ocr_accuracy": None,
                "ollama_extraction_accuracy": None,
                "note": "Deterministic pipe-delimited extraction evaluated; real scans and LLM extraction have not been benchmarked.",
            }
        groups = {}
        for p in prices:
            if p.price_type == "cash":
                key = (p.code_type, p.code, p.setting, p.billing_class, p.modifiers, p.is_demo, p.description)
                groups.setdefault(key, []).append(p)
        variation = []
        for key, group in groups.items():
            if len({p.hospital_id for p in group}) < 2:
                continue
            amounts = [float(p.amount) for p in group]
            variation.append(
                {
                    "code": key[1],
                    "code_type": key[0],
                    "description": group[0].description,
                    "setting": key[2],
                    "billing_class": key[3],
                    "modifiers": key[4],
                    "is_demo": key[5],
                    "hospital_count": len({p.hospital_id for p in group}),
                    "min_cash": min(amounts),
                    "max_cash": max(amounts),
                    "max_min_ratio": round(max(amounts) / min(amounts), 3),
                }
            )
        non_alias = [d for d in details if not d["overlaps_alias"]]
        result = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "data": stats,
            "search": {
                "queries": len(details),
                "dataset": "100 authored synthetic development queries; 40 are aliases. Not held-out patient research.",
                "mode": "local_embeddings_hybrid" if model_path else "keyword_plus_aliases",
                "top1_accuracy": sum(d["search_correct"] for d in details) / len(details),
                "keyword_top1_accuracy": sum(d["baseline_correct"] for d in details) / len(details),
                "non_alias_queries": len(non_alias),
                "non_alias_top1_accuracy": sum(d["search_correct"] for d in non_alias) / len(non_alias),
                "details": details,
            },
            "estimator": {"hand_calculated_cases": len(estimator_cases), "passed": estimator_pass},
            "bill_checker": bill_metrics,
            "price_variation": sorted(variation, key=lambda r: -r["max_min_ratio"]),
            "user_testing": {"participants": 0, "status": "Not conducted; see docs/user-testing.md"},
        }
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2) + "\n")
    summary = {**result, "search": {k: v for k, v in result["search"].items() if k != "details"}}
    summary["price_variation"] = {
        "procedures_compared": len(variation),
        "maximum_ratio": max((r["max_min_ratio"] for r in variation), default=None),
        "synthetic": bool(stats["demo_prices"]),
    }
    return summary

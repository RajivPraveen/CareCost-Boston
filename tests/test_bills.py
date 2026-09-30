from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from carecost.bills import check_bill, extract_structured_text, extract_with_ollama, read_document
from carecost.models import BillLine


def flags(results):
    return {(r["line"], f["type"]) for r in results for f in r["flags"]}


def line(**kwargs):
    return BillLine.model_validate(
        {
            "code": "73721",
            "code_type": "CPT",
            "description": "Knee MRI",
            "quantity": 1,
            "charge": 1856,
            **kwargs,
        }
    )


def test_planted_sample_errors(repo):
    bill = extract_structured_text(Path("data/demo/sample_bill.txt").read_text())
    found = flags(check_bill(bill.lines, repo.query(), "demo_harbor"))
    assert found == {(1, "above_published"), (3, "possible_duplicate"), (4, "no_comparable_price")}


def test_quantity_and_payment_basis(repo):
    prices = repo.query()
    assert not flags(check_bill([line(quantity=2, charge=3712)], prices, "demo_harbor"))
    assert not flags(check_bill([line(charge=1800)], prices, "demo_harbor"))
    assert (1, "above_published") in flags(
        check_bill([line(charge=700)], prices, "demo_harbor", price_type="cash")
    )


def test_different_dates_not_duplicate(repo):
    result = check_bill(
        [line(service_date="2026-09-01"), line(service_date="2026-09-02")], repo.query(), "demo_harbor"
    )
    assert not flags(result)


def test_date_stale_ambiguous_missing_code_and_modifier(repo):
    prices = repo.query(hospital_id="demo_harbor", code="73721", price_type="gross")
    assert (1, "date_mismatch") in flags(
        check_bill([line(service_date="2025-01-01", charge=9000)], prices, "demo_harbor")
    )
    old = prices[0].model_copy(update={"source_date": date.today() - timedelta(days=500)})
    assert (1, "stale_source") in flags(check_bill([line(charge=9000)], [old], "demo_harbor"))
    variant = prices[0].model_copy(update={"amount": Decimal("1000"), "service_id": "different"})
    assert flags(check_bill([line(charge=9000)], [*prices, variant], "demo_harbor")) == {
        (1, "ambiguous_price")
    }
    assert flags(check_bill([line(code="")], prices, "demo_harbor")) == {(1, "missing_code")}
    assert flags(check_bill([line(modifiers="26")], prices, "demo_harbor")) == {(1, "no_comparable_price")}


def test_insurer_and_hospital_never_fallback(repo):
    result = check_bill([line()], repo.query(), "nonexistent")
    assert flags(result) == {(1, "no_comparable_price")}
    result = check_bill([line()], repo.query(), "demo_harbor", "negotiated", "aetna", "hmo")
    assert flags(result) == {(1, "no_comparable_price")}


def test_ocr_upload_bounds():
    with pytest.raises(ValueError):
        read_document(b"", "bill.txt")
    with pytest.raises(ValueError):
        read_document(b"a" * (10 * 1024 * 1024 + 1), "bill.txt")
    assert read_document(b"test bill", "bill.txt") == "test bill"


def test_ollama_loopback_schema_and_no_redirects(monkeypatch):
    from carecost import bills

    calls = []

    class Response:
        status_code = 200

        def json(self):
            return {
                "message": {
                    "content": '{"lines":[{"description":"MRI","code":"73721","quantity":1,"charge":200,"evidence":"MRI 73721 200"}]}'
                }
            }

    class Session:
        trust_env = True

        def post(self, url, **kwargs):
            if url.endswith("/show"):

                class Metadata:
                    status_code = 200

                    def json(self):
                        return {"model_info": {"general.architecture": "test"}}

                return Metadata()
            calls.append((url, kwargs, self.trust_env))
            return Response()

        def close(self):
            pass

    monkeypatch.setattr(bills.requests, "Session", Session)
    result = extract_with_ollama("MRI 73721 200")
    assert len(result.lines) == 1
    url, kwargs, trust_env = calls[0]
    assert url == "http://127.0.0.1:11434/api/chat"
    assert kwargs["allow_redirects"] is False and trust_env is False
    assert kwargs["json"]["format"]["type"] == "object"
    with pytest.raises(ValueError, match="grounded"):
        extract_with_ollama("Different source text")


def test_cloud_model_names_rejected_before_any_request(monkeypatch):
    from carecost import bills

    def no_network():
        raise AssertionError("Network was contacted")

    monkeypatch.setattr(bills.requests, "Session", no_network)
    with pytest.raises(ValueError, match="locally installed"):
        extract_with_ollama("synthetic", model="some-model:cloud")


def test_remote_model_metadata_blocks_bill_transmission(monkeypatch):
    from carecost import bills

    calls = []

    class Session:
        def post(self, url, **kwargs):
            calls.append(kwargs["json"])
            assert url.endswith("/show")

            class Response:
                status_code = 200

                def json(self):
                    return {"remote_host": "https://example.org", "model_info": {"x": 1}}

            return Response()

        def close(self):
            pass

    monkeypatch.setattr(bills.requests, "Session", Session)
    with pytest.raises(ValueError, match="before sending text"):
        extract_with_ollama("private test content", model="innocent-alias")
    assert calls == [{"model": "innocent-alias"}]


def test_numeric_cpt_matches_hcpcs_level_one_without_changing_source_label(repo):
    price = repo.query(hospital_id="demo_harbor", code="73721", price_type="gross")[0]
    disclosed_as_hcpcs = price.model_copy(update={"code_type": "HCPCS"})
    result = check_bill([line(charge=price.amount)], [disclosed_as_hcpcs], "demo_harbor")
    assert not flags(result)
    assert result[0]["sources"][0]["url"] == price.source_url

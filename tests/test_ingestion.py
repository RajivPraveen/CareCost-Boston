import csv
import json
from datetime import date, timedelta

import pytest

from carecost.ingestion import ingest_file, normalize_payer

SOURCE = {"hospital_id": "test", "url": "https://example.org/prices.csv", "source_date": "2026-01-01"}
HOSPITAL = {"hospital_id": "test", "name": "Test", "latitude": 42, "longitude": -71}


def flat(tmp_path, rows):
    path = tmp_path / "prices.csv"
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0])
        writer.writeheader()
        writer.writerows(rows)
    return path


def base(**kwargs):
    return dict(
        code="00100",
        code_type="CPT",
        description="Test service",
        setting="outpatient",
        price_type="cash",
        amount="100",
        **kwargs,
    )


def test_flat_leading_zeros_quarantine_and_idempotence(repo, tmp_path):
    row = base()
    path = flat(
        tmp_path,
        [row, row, {**row, "amount": "-5"}, {**row, "amount": "NaN"}, {**row, "amount": "999999999"}],
    )
    result = ingest_file(repo, path, SOURCE, HOSPITAL)
    assert result["accepted"] == 1 and result["duplicates"] == 1 and result["quarantined"] == 3
    assert repo.query(hospital_id="test")[0].code == "00100"
    ingest_file(repo, path, SOURCE, HOSPITAL)
    assert len(repo.query(hospital_id="test")) == 1
    assert repo.connection.execute("SELECT count(*) FROM quarantine").fetchone()[0] == 3


def test_failed_refresh_retains_previous_snapshot(repo, tmp_path):
    path = flat(tmp_path, [base()])
    ingest_file(repo, path, SOURCE, HOSPITAL)
    flat(tmp_path, [{**base(), "amount": "-1"}])
    with pytest.raises(ValueError, match="previous snapshot retained"):
        ingest_file(repo, path, SOURCE, HOSPITAL)
    assert str(repo.query(hospital_id="test")[0].amount) == "100.00"


def test_cms_json_explicit_dollars_only(repo, tmp_path):
    path = tmp_path / "cms.json"
    path.write_text(
        json.dumps(
            {
                "last_updated_on": "2026-01-01",
                "standard_charge_information": [
                    {
                        "description": "Knee scan",
                        "code_information": [
                            {"code": "73721", "type": "CPT"},
                            {"code": "12", "type": "LOCAL"},
                        ],
                        "standard_charges": [
                            {
                                "setting": "outpatient",
                                "billing_class": "facility",
                                "discounted_cash": 600,
                                "payers_information": [
                                    {"payer_name": "A", "plan_name": "PPO", "standard_charge_dollar": 800},
                                    {
                                        "payer_name": "B",
                                        "plan_name": "PPO",
                                        "standard_charge_percentage": 50,
                                        "median_amount": 200,
                                    },
                                ],
                            }
                        ],
                    }
                ],
            }
        )
    )
    result = ingest_file(repo, path, SOURCE, HOSPITAL)
    assert result["accepted"] == 2 and result["quarantined"] == 1
    assert sorted(p.amount for p in repo.query(hospital_id="test")) == [600, 800]


@pytest.mark.parametrize("wide", [False, True])
def test_cms_csv_metadata_and_layout(repo, tmp_path, wide):
    path = tmp_path / "cms.csv"
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["hospital_name", "last_updated_on", "version"])
        w.writerow(["Test", "2026-01-02", "3.0.0"])
        header = ["description", "code|1", "code|1|type", "setting", "standard_charge|discounted_cash"]
        row = ["Knee scan", "73721", "CPT", "outpatient", "500"]
        if wide:
            header += ["standard_charge|Aetna|PPO|negotiated_dollar"]
            row += ["700"]
        else:
            header += ["payer_name", "plan_name", "standard_charge|negotiated_dollar"]
            row += ["Aetna", "PPO", "700"]
        w.writerow(header)
        w.writerow(row)
    result = ingest_file(repo, path, SOURCE, HOSPITAL)
    assert result["accepted"] == 2
    assert all(p.source_date.isoformat() == "2026-01-02" for p in repo.query(hospital_id="test"))


def test_future_date_rejected(repo, tmp_path):
    path = flat(tmp_path, [base(source_date=(date.today() + timedelta(days=1)).isoformat())])
    with pytest.raises(ValueError):
        ingest_file(repo, path, SOURCE, HOSPITAL)


def test_payer_mapping_never_fuzzy_merges_products():
    aliases = {"bcbs ma|ppo": {"payer": "BCBS", "plan": "PPO"}}
    assert normalize_payer("BCBS MA", "PPO", aliases) == ("BCBS", "PPO")
    assert normalize_payer("BCBS MA", "HMO", aliases) == ("bcbs ma", "hmo")


def test_context_variants_not_deduplicated(repo, tmp_path):
    a = base()
    b = {**a, "description": "A different bundle"}
    c = {**a, "setting": "inpatient"}
    result = ingest_file(repo, flat(tmp_path, [a, b, c]), SOURCE, HOSPITAL)
    assert result["accepted"] == 3


def test_malformed_trailing_json_rolls_back(repo, tmp_path):
    path = tmp_path / "broken.json"
    path.write_text('{"last_updated_on":"2026-01-01","standard_charge_information":[')
    before = repo.statistics()
    with pytest.raises(Exception):
        ingest_file(repo, path, SOURCE, HOSPITAL)
    assert repo.statistics() == before


def test_explicit_legacy_column_mapping(repo, tmp_path):
    path = tmp_path / "legacy.csv"
    path.write_text("Service Name,CPT Code,Self Pay\nKnee MRI,73721,600\n")
    source = {
        **SOURCE,
        "column_map": {"Service Name": "description", "CPT Code": "code", "Self Pay": "amount"},
        "defaults": {
            "code_type": "CPT",
            "setting": "outpatient",
            "billing_class": "facility",
            "price_type": "cash",
        },
    }
    result = ingest_file(repo, path, source, HOSPITAL)
    assert result["accepted"] == 1
    assert repo.query(hospital_id="test")[0].amount == 600


def test_huge_numeric_values_quarantined(repo, tmp_path):
    row = base()
    result = ingest_file(repo, flat(tmp_path, [row, {**row, "amount": "1e1000"}]), SOURCE, HOSPITAL)
    assert result["accepted"] == 1 and result["quarantined"] == 1


def test_windows1252_hospital_csv(repo, tmp_path):
    path = tmp_path / "windows.csv"
    path.write_bytes(
        "description,code,code_type,setting,price_type,amount\nPatient’s scan,73721,CPT,both,cash,400\n".encode(
            "cp1252"
        )
    )
    result = ingest_file(repo, path, {**SOURCE, "encoding": "cp1252"}, HOSPITAL)
    assert result["accepted"] == 1
    assert repo.query(hospital_id="test")[0].description == "Patient’s scan"


def test_zip_uses_destination_not_member_path(tmp_path):
    import zipfile

    from carecost.cli import extract_price_archive

    archive = tmp_path / "file.zip"
    target = tmp_path / "safe.csv"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("../escape.csv", "code,amount\n73721,400\n")
    extract_price_archive(archive, target)
    assert target.read_text() == "code,amount\n73721,400\n"
    assert not (tmp_path.parent / "escape.csv").exists()


def test_oversized_archive_preserves_previous_file(tmp_path):
    import zipfile

    from carecost.cli import extract_price_archive

    archive = tmp_path / "file.zip"
    target = tmp_path / "safe.csv"
    target.write_text("previous")
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("price.csv", "a" * 100)
    with pytest.raises(ValueError):
        extract_price_archive(archive, target, max_bytes=10)
    assert target.read_text() == "previous"


def test_cms_csv_us_publication_date_and_non_service_rate(repo, tmp_path):
    path = tmp_path / "bmc.csv"
    with path.open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["hospital_name", "last_updated_on", "version"])
        writer.writerow(["Hospital", "03/13/2026", "3.0.0"])
        writer.writerow(
            [
                "description",
                "code|1",
                "code|1|type",
                "setting",
                "standard_charge|gross",
                "standard_charge|discounted_cash",
                "payer_name",
                "plan_name",
                "standard_charge|negotiated_dollar",
                "standard_charge|methodology",
            ]
        )
        writer.writerow(["MRI knee", "73721", "CPT", "both", "500", "300", "Aetna", "PPO", "250", "per diem"])
        writer.writerow(
            ["MRI knee", "73721", "CPT", "both", "500", "300", "Aetna", "PPO", "220", "fee schedule"]
        )
    source = {**SOURCE, "date_format": "%m/%d/%Y"}
    result = ingest_file(repo, path, source, HOSPITAL)
    assert result["accepted"] == 3
    assert result["quarantined"] == 1
    assert result["duplicates"] == 2
    assert {str(p.amount) for p in repo.query(hospital_id="test")} == {"500.00", "300.00", "220.00"}
    assert all(p.source_date.isoformat() == "2026-03-13" for p in repo.query(hospital_id="test"))


def test_cms_json_bom_and_published_billing_class_typo(repo, tmp_path):
    path = tmp_path / "bom.json"
    data = {
        "last_updated_on": "2026-04-01",
        "standard_charge_information": [
            {
                "description": "MRI knee",
                "code_information": [{"code": "73721", "type": "CPT"}],
                "standard_charges": [
                    {"setting": "both", "billing_class": "facillity", "discounted_cash": 600}
                ],
            }
        ],
    }
    path.write_text("\ufeff" + json.dumps(data))
    result = ingest_file(repo, path, SOURCE, HOSPITAL)
    assert result["accepted"] == 1
    assert repo.query(hospital_id="test")[0].billing_class == "facility"

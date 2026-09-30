"""Read-only integration checks against the locally acquired official snapshot.

Skipped in CI without raw public files; these never call a hospital or AI endpoint.
"""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from carecost.mapview import comparison_map, hospital_map_points, map_points
from carecost.repository import Repository, distance_miles

LIVE_DB = Path("data/processed/boston.sqlite")
pytestmark = pytest.mark.skipif(not LIVE_DB.exists(), reason="Download official hospital snapshot first")


def live_app(monkeypatch):
    monkeypatch.setenv("CARECOST_DB", str(LIVE_DB.resolve()))
    monkeypatch.setenv("CARECOST_EMBEDDING_MODEL", "")
    at = AppTest.from_file(Path("app.py").resolve(), default_timeout=40).run()
    return at.text_input(key="service_query").set_value("knee MRI").run()


def test_live_comparison_and_estimate(monkeypatch):
    at = live_app(monkeypatch)
    assert not at.exception
    assert at.metric[0].value == "8"
    assert at.metric[1].value == "$2,075.85"
    assert not any("fictional" in x.value for x in at.warning)
    at.radio(key="navigation_page").set_value("Estimate my cost").run()
    assert not at.exception
    assert any(x.label == "Annual deductible ($)" for x in at.number_input)
    assert int(at.metric[0].value) >= 1


def test_live_bill_review_against_published_gross(monkeypatch):
    at = live_app(monkeypatch)
    at.radio(key="navigation_page").set_value("Check my bill").run()
    next(x for x in at.selectbox if x.label == "Hospital on your bill").select("mgh").run()
    next(x for x in at.radio if x.label == "Input method").set_value("Enter line items manually").run()
    at.text_area(key="bill_manual").set_value(
        "73721 | MRI Lwr Ext Joint W/O Cont | 1 | 3600.00 | 2026-09-01 | CPT |"
    ).run()
    next(x for x in at.button if x.label == "Read my bill").click().run()
    at.checkbox(key="bill_confirm").check().run()
    next(x for x in at.button if x.label == "Check these charges").click().run()
    assert not at.exception
    assert any("$268.00" in x.value for x in at.warning)


def test_live_data_report(monkeypatch):
    at = live_app(monkeypatch)
    at.radio(key="navigation_page").set_value("Data & methodology").run()
    assert not at.exception
    assert at.metric[0].value == "8"
    assert at.metric[2].value == "777059"
    assert any("253 of 253" in x.value for x in at.success)


def test_live_map_has_one_selectable_marker_per_priced_hospital():
    origin = (42.3601, -71.0589)
    with Repository(LIVE_DB) as repo:
        hospitals = repo.hospitals()
        prices = repo.query(code="73721")
    rows = [
        {
            "price": p,
            "hospital": hospitals[p.hospital_id],
            "distance": distance_miles(
                *origin, hospitals[p.hospital_id]["latitude"], hospitals[p.hospital_id]["longitude"]
            ),
            "display": p.amount,
        }
        for p in prices
        if p.price_type == "cash"
        and p.setting in {"outpatient", "both"}
        and p.billing_class in {"facility", "unknown", "both"}
        and not p.modifiers
    ]
    points = map_points(rows)
    assert len(points) == 8
    assert len({p["hospital_id"] for p in points}) == 8
    assert all(p["address"] and p["latitude"] and p["longitude"] for p in points)
    deck = comparison_map(points, origin)
    assert deck.layers[0].id == "hospitals"
    assert deck.layers[0].pickable is True


def test_hospital_map_is_available_without_search(monkeypatch):
    monkeypatch.setenv("CARECOST_DB", str(LIVE_DB.resolve()))
    at = AppTest.from_file(Path("app.py").resolve(), default_timeout=40).run()
    at.radio(key="navigation_page").set_value("Hospital map").run()
    assert not at.exception
    assert any(x.label == "Find a hospital" for x in at.selectbox)
    with Repository(LIVE_DB) as repo:
        hospitals = repo.hospitals()
    points = hospital_map_points(hospitals)
    assert len(points) == 8
    assert all(point["address"] for point in points)
    assert comparison_map(points, focused_hospital="mgh").layers[0].pickable is True

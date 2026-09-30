from pathlib import Path

from streamlit.testing.v1 import AppTest


def app(monkeypatch, demo_db):
    monkeypatch.setenv("CARECOST_DB", str(demo_db))
    monkeypatch.setenv("CARECOST_EMBEDDING_MODEL", "")
    at = AppTest.from_file(Path("app.py").resolve(), default_timeout=20).run()
    return at.text_input(key="service_query").set_value("knee MRI").run()


def test_compare_estimate_and_methodology(monkeypatch, demo_db):
    at = app(monkeypatch, demo_db)
    assert not at.exception
    assert at.title[0].value == "Find care. Know the cost."
    assert at.metric[0].value == "4"
    at.radio(key="navigation_page").set_value("Estimate my cost").run()
    assert not at.exception
    next(x for x in at.selectbox if x.label == "Insurance company").select("aetna").run()
    payment = next(x for x in at.selectbox if x.label == "Your exact plan")
    payment.select(("aetna", "ppo")).run()
    assert not at.exception
    assert any(x.label == "Annual deductible ($)" for x in at.number_input)
    at.radio(key="navigation_page").set_value("Data & methodology").run()
    assert not at.exception


def test_bill_workflow_and_clear(monkeypatch, demo_db):
    at = app(monkeypatch, demo_db)
    at.radio(key="navigation_page").set_value("Check my bill").run()
    assert not at.exception
    # Choose the hospital named on the synthetic fixture.
    next(x for x in at.selectbox if x.label == "Hospital on your bill").select("demo_harbor").run()
    next(x for x in at.button if x.label == "Read my bill").click().run()
    assert not at.exception
    at.checkbox(key="bill_confirm").check().run()
    next(x for x in at.button if x.label == "Check these charges").click().run()
    assert not at.exception
    assert any("3 of 4" in x.value for x in at.subheader)
    next(x for x in at.button if x.label == "Clear bill and review").click().run()
    assert not at.exception
    assert "bill_lines" not in at.session_state


def test_start_with_a_search_and_example_button(monkeypatch, demo_db):
    monkeypatch.setenv("CARECOST_DB", str(demo_db))
    monkeypatch.setenv("CARECOST_EMBEDDING_MODEL", "")
    at = AppTest.from_file(Path("app.py").resolve(), default_timeout=20).run()
    assert not at.exception
    assert at.text_input(key="service_query").value == ""
    assert not at.metric  # No prices presented before the user chooses a service.
    next(x for x in at.button if x.label == "Knee MRI").click().run()
    assert not at.exception
    assert at.text_input(key="service_query").value == "Knee MRI"
    assert at.metric[0].value == "4"

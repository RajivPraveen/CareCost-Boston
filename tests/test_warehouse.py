import sys
from types import ModuleType

import pytest

from carecost.warehouse import export, identifier


@pytest.mark.parametrize("value", ["RAW;DROP TABLE X", "raw.test", 'bad"name', "x y"])
def test_unsafe_identifiers_rejected(value):
    with pytest.raises(ValueError):
        identifier(value)


def test_export_requires_new_destination(tmp_path):
    path = tmp_path / "existing.sqlite"
    path.write_bytes(b"keep this")
    with pytest.raises(ValueError, match="new filename"):
        export(path)
    assert path.read_bytes() == b"keep this"


def test_export_requires_dbt_artifact(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError, match="dbt build"):
        export(tmp_path / "new.sqlite")


def test_bootstrap_uses_small_autosuspending_warehouse(monkeypatch):
    from carecost.warehouse import bootstrap

    executed = []

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def execute(self, sql):
            executed.append(sql)

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def cursor(self):
            return Cursor()

    # Bootstrap SQL can be checked without installing or contacting Snowflake.
    snowflake = ModuleType("snowflake")
    snowflake.__path__ = []
    connector = ModuleType("snowflake.connector")
    connector.connect = lambda **kwargs: Connection()
    snowflake.connector = connector
    dotenv = ModuleType("dotenv")
    dotenv.load_dotenv = lambda: None
    monkeypatch.setitem(sys.modules, "snowflake", snowflake)
    monkeypatch.setitem(sys.modules, "snowflake.connector", connector)
    monkeypatch.setitem(sys.modules, "dotenv", dotenv)
    for name, value in {
        "SNOWFLAKE_ACCOUNT": "example",
        "SNOWFLAKE_USER": "patient_data_builder",
        "SNOWFLAKE_AUTHENTICATOR": "externalbrowser",
        "SNOWFLAKE_WAREHOUSE": "CARECOST_WH",
        "SNOWFLAKE_DATABASE": "CARECOST",
        "SNOWFLAKE_SCHEMA": "RAW",
        "CARECOST_MART_SCHEMA": "ANALYTICS",
    }.items():
        monkeypatch.setenv(name, value)
    result = bootstrap()
    assert result["raw_schema"] == "RAW"
    assert len(executed) == 4
    assert "WAREHOUSE_SIZE = XSMALL" in executed[0]
    assert "AUTO_SUSPEND = 60" in executed[0]
    assert "INITIALLY_SUSPENDED = TRUE" in executed[0]
    assert executed[2] == "CREATE SCHEMA IF NOT EXISTS CARECOST.RAW"

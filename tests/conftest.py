import pytest

from carecost.cli import load_manifest
from carecost.repository import Repository


@pytest.fixture
def demo_db(tmp_path):
    database = tmp_path / "demo.sqlite"
    load_manifest("config/demo_sources.json", database)
    return database


@pytest.fixture
def repo(demo_db):
    with Repository(demo_db) as repository:
        yield repository

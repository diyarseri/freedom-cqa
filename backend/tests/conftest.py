import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

FIXTURES = Path(__file__).resolve().parents[2] / 'fixtures'


def fixture(name):
    return json.loads((FIXTURES / f'{name}.json').read_text(encoding='utf-8'))


@pytest.fixture
def settings(tmp_path):
    return Settings(database_path=str(tmp_path / 'test.sqlite3'))


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as client:
        yield client

import json
from pathlib import Path

import pytest

from leadscout.config import Campaign
from leadscout.db import DB

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixture_text():
    return lambda name: (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture
def fixture_json():
    return lambda name: json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture
def db(tmp_path):
    return DB(tmp_path / "test.db")


@pytest.fixture
def campaign():
    return Campaign(name="test", location="Lahore", country_code="92", categories=["cafe"], service="web_design")

import json
from pathlib import Path

import pytest


@pytest.fixture
def payload():
    return json.loads((Path(__file__).parent / "fixtures/ridepath.json").read_text())

@pytest.fixture
def service_fixtures():
    directory = Path(__file__).parent / "fixtures"
    return {file.stem: json.loads(file.read_text()) for file in directory.glob("*.json")}

@pytest.fixture
def socket_enabled():
    yield

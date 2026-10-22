import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def client(tmp_path):
    """An API client backed by a fresh database and document directory."""
    settings = Settings(data_directory=tmp_path, trafiklab_api_key=None, anthropic_api_key=None)
    with TestClient(create_app(settings)) as test_client:
        yield test_client

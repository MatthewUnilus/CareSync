from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

# The reason a test opens a visit with. A visit carries only a reason until the
# Observation chart lands (ticket 30), and a visit route refuses vitals rather
# than dropping them, so the shared fixture is reason-only. A test that needs a
# different reason overrides ``presenting_complaint`` inline.
VISIT_INTAKE = {
    "presenting_complaint": "Mild headache for a day",
}


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "caresync-test.db"


@pytest.fixture
def settings(db_path: Path) -> Settings:
    return Settings(
        database_url=f"sqlite:///{db_path.as_posix()}",
        session_ttl_seconds=3600,
        seed_demo_users=True,
    )


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as test_client:
        yield test_client


@pytest.fixture
def clinical_client(client: TestClient) -> TestClient:
    """A client with an authenticated Clinical session."""
    response = client.post(
        "/api/auth/login",
        json={"email": "clinical@example.com", "password": "clinical-password"},
    )
    assert response.status_code == 200
    return client


@pytest.fixture
def short_session_client(db_path: Path) -> Iterator[TestClient]:
    settings = Settings(
        database_url=f"sqlite:///{db_path.as_posix()}",
        session_ttl_seconds=1,
        seed_demo_users=True,
    )
    with TestClient(create_app(settings)) as test_client:
        yield test_client

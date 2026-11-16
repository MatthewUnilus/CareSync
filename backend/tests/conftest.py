from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

# Shared intake fixtures. The shipped interim classifier separates these three
# presentations; age is one of its inputs and comes from the Patient, so each
# fixture carries the age the Patient is registered with. Keeping one copy
# means a test can never drift from the presentation another test proves.
LOW_INTAKE = {
    "presenting_complaint": "Mild headache for a day",
    "pain_level": 2,
    "illness_duration_hours": 24,
    "temperature_c": 36.6,
    "heart_rate_bpm": 70,
    "respiratory_rate_bpm": 16,
    "blood_pressure": {"systolic": 116, "diastolic": 72},
    "oxygen_saturation_percent": 99,
    "notes": None,
}

MEDIUM_INTAKE = {
    **LOW_INTAKE,
    "pain_level": 6,
    "presenting_complaint": "Abdominal pain",
    "illness_duration_hours": 12,
    "temperature_c": 36.8,
    "heart_rate_bpm": 80,
    "respiratory_rate_bpm": 18,
    "blood_pressure": {"systolic": 110, "diastolic": 70},
    "oxygen_saturation_percent": 94,
}

HIGH_INTAKE = {
    **LOW_INTAKE,
    "pain_level": 9,
    "presenting_complaint": "Chest pain",
    "illness_duration_hours": 2,
    "temperature_c": 38.4,
    "heart_rate_bpm": 130,
    "respiratory_rate_bpm": 24,
    "blood_pressure": {"systolic": 95, "diastolic": 58},
    "oxygen_saturation_percent": 88,
}

LOW_AGE = 24
MEDIUM_AGE = 80
HIGH_AGE = 78


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "triageassist-test.db"


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

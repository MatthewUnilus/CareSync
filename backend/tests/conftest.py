from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


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
def short_session_client(db_path: Path) -> Iterator[TestClient]:
    settings = Settings(
        database_url=f"sqlite:///{db_path.as_posix()}",
        session_ttl_seconds=1,
        seed_demo_users=True,
    )
    with TestClient(create_app(settings)) as test_client:
        yield test_client

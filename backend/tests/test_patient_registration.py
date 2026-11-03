from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

CLINICAL_CREDENTIALS = {
    "email": "clinical@example.com",
    "password": "clinical-password",
}
ADMINISTRATOR_CREDENTIALS = {
    "email": "administrator@example.com",
    "password": "administrator-password",
}

PATIENT = {
    "full_name": "Ada Lovelace",
    "age": 36,
    "sex": "female",
    "contact_phone": "07700 900123",
    "contact_email": "ada@example.com",
}


def register_patient(client: TestClient, **overrides: Any):
    return client.post(
        "/api/clinical/patients",
        json={**PATIENT, **overrides},
    )


def test_clinical_user_registers_a_patient(clinical_client: TestClient) -> None:
    response = register_patient(clinical_client)

    assert response.status_code == 201
    body = response.json()
    assert body["id"] > 0
    assert body["full_name"] == "Ada Lovelace"
    assert body["age"] == 36
    assert body["sex"] == "female"
    assert body["contact_phone"] == "07700 900123"
    assert body["contact_email"] == "ada@example.com"
    assert body["registered_at"]


def test_registering_the_same_patient_again_reuses_the_record(
    clinical_client: TestClient,
) -> None:
    first = register_patient(clinical_client)
    assert first.status_code == 201

    second = register_patient(clinical_client)

    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]


def test_matching_ignores_name_case_spacing_and_phone_formatting(
    clinical_client: TestClient,
) -> None:
    first = register_patient(
        clinical_client,
        full_name="Ada Lovelace",
        contact_phone="07700 900123",
    )
    assert first.status_code == 201

    second = register_patient(
        clinical_client,
        full_name="  ada   LOVELACE ",
        contact_phone="0770-090 0123",
    )

    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]


def test_two_people_with_the_same_name_stay_separate(
    clinical_client: TestClient,
) -> None:
    first = register_patient(clinical_client, contact_phone="07700 900123")

    second = register_patient(
        clinical_client,
        full_name="Ada Lovelace",
        contact_phone="07700 900999",
        contact_email=None,
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert second.json()["id"] != first.json()["id"]


@pytest.mark.parametrize(
    "overrides",
    [
        {"full_name": "   "},
        {"full_name": ""},
        {"age": -1},
        {"age": 121},
        {"sex": "unknown-sex"},
        {"contact_phone": "n/a"},
        {"contact_email": "not-an-email"},
    ],
)
def test_patient_details_are_validated(
    clinical_client: TestClient, overrides: dict[str, Any]
) -> None:
    response = register_patient(clinical_client, **overrides)

    assert response.status_code == 422


def test_administrator_cannot_register_a_patient(client: TestClient) -> None:
    login = client.post("/api/auth/login", json=ADMINISTRATOR_CREDENTIALS)
    assert login.status_code == 200

    response = register_patient(client)

    assert response.status_code == 403
    assert response.json() == {"detail": "Role not permitted"}


def test_patient_registration_requires_authentication(client: TestClient) -> None:
    response = register_patient(client)

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}


def test_registration_survives_a_new_app_over_the_same_database(db_path) -> None:
    settings = Settings(
        database_url=f"sqlite:///{db_path.as_posix()}",
        session_ttl_seconds=3600,
        seed_demo_users=True,
    )

    with TestClient(create_app(settings)) as first_client:
        first_client.post("/api/auth/login", json=CLINICAL_CREDENTIALS)
        first = register_patient(first_client)

    with TestClient(create_app(settings)) as second_client:
        second_client.post("/api/auth/login", json=CLINICAL_CREDENTIALS)
        second = register_patient(second_client)

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]

"""Patient search and per-Patient history, at the API boundary.

Search is a discovery aid and is deliberately looser than identity resolution:
``app.patients`` documents that a name alone is never enough to *match an
identity* (a returning Patient needs the name *and* the phone number). These
cases assert only what a search may do — match part of a name, or part of a
contact number — and never that search decides who someone is.
"""

from typing import Any

from fastapi.testclient import TestClient

from conftest import LOW_INTAKE

ADMIN_CREDENTIALS = {
    "email": "administrator@example.com",
    "password": "administrator-password",
}

PATIENT = {
    "full_name": "Ada Lovelace",
    "age": 36,
    "sex": "female",
    "contact_phone": "07700 900123",
    "contact_email": None,
}


def register_patient(
    client: TestClient, full_name: str, contact_phone: str, age: int = 36
) -> int:
    response = client.post(
        "/api/clinical/patients",
        json={
            **PATIENT,
            "full_name": full_name,
            "contact_phone": contact_phone,
            "age": age,
        },
    )
    assert response.status_code in (200, 201), response.text
    return response.json()["id"]


def open_encounter(client: TestClient, patient_id: int) -> dict[str, Any]:
    response = client.post(
        "/api/clinical/encounters",
        json={"patient_id": patient_id, "intake": LOW_INTAKE},
    )
    assert response.status_code == 201, response.text
    return response.json()


def search(client: TestClient, query: str, limit: int | None = None) -> list[dict[str, Any]]:
    path = f"/api/clinical/patients?q={query}"
    if limit is not None:
        path += f"&limit={limit}"
    response = client.get(path)
    assert response.status_code == 200, response.text
    return response.json()["patients"]


# --- search by name -------------------------------------------------------


def test_search_matches_a_partial_name(clinical_client: TestClient) -> None:
    register_patient(clinical_client, "Ada Lovelace", "07700 900123")
    register_patient(clinical_client, "Grace Hopper", "07700 900456")

    results = search(clinical_client, "lovel")

    assert [patient["full_name"] for patient in results] == ["Ada Lovelace"]


# --- search by contact number ---------------------------------------------


def test_search_matches_a_contact_number(clinical_client: TestClient) -> None:
    register_patient(clinical_client, "Ada Lovelace", "07700 900123")
    register_patient(clinical_client, "Grace Hopper", "07700 900456")

    # The number is searched loosely: the stored value carries a space the
    # query does not, and the query matches only its last digits.
    results = search(clinical_client, "900123")

    assert [patient["full_name"] for patient in results] == ["Ada Lovelace"]


# --- blank query ----------------------------------------------------------


def test_a_blank_query_returns_nothing(clinical_client: TestClient) -> None:
    register_patient(clinical_client, "Ada Lovelace", "07700 900123")

    assert search(clinical_client, "") == []


def test_a_whitespace_only_query_returns_nothing(
    clinical_client: TestClient,
) -> None:
    register_patient(clinical_client, "Ada Lovelace", "07700 900123")

    assert search(clinical_client, "%20%20") == []


# --- limit ----------------------------------------------------------------


def test_the_result_count_honours_the_limit(clinical_client: TestClient) -> None:
    for index in range(3):
        register_patient(
            clinical_client, f"Test Patient {index}", f"07700 90000{index}"
        )

    assert len(search(clinical_client, "test patient", limit=2)) == 2


# --- role separation ------------------------------------------------------


def test_an_administrator_cannot_search_patients(client: TestClient) -> None:
    login = client.post("/api/auth/login", json=ADMIN_CREDENTIALS)
    assert login.status_code == 200

    response = client.get("/api/clinical/patients?q=ada")

    assert response.status_code == 403
    assert response.json() == {"detail": "Role not permitted"}


def test_an_administrator_cannot_read_patient_history(client: TestClient) -> None:
    login = client.post("/api/auth/login", json=ADMIN_CREDENTIALS)
    assert login.status_code == 200

    response = client.get("/api/clinical/patients/1/encounters")

    assert response.status_code == 403
    assert response.json() == {"detail": "Role not permitted"}


# --- per-Patient history --------------------------------------------------


def test_patient_history_lists_that_patients_encounters(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client, "Ada Lovelace", "07700 900123")
    other_id = register_patient(clinical_client, "Grace Hopper", "07700 900456")
    first = open_encounter(clinical_client, patient_id)
    second = open_encounter(clinical_client, patient_id)
    open_encounter(clinical_client, other_id)

    response = clinical_client.get(f"/api/clinical/patients/{patient_id}/encounters")

    assert response.status_code == 200, response.text
    encounters = response.json()["encounters"]
    assert [encounter["id"] for encounter in encounters] == [first["id"], second["id"]]
    # Each visit carries its Urgency Level and Final Decision.
    assert encounters[0]["assessment"]["final_decision"] in ("High", "Medium", "Low")


def test_an_unknown_patient_id_returns_404(clinical_client: TestClient) -> None:
    response = clinical_client.get("/api/clinical/patients/9999/encounters")

    assert response.status_code == 404
    assert response.json() == {"detail": "Patient not found"}


# --- evaluation-run exclusion --------------------------------------------


def test_evaluation_run_encounters_are_excluded_from_history(
    clinical_client: TestClient,
) -> None:
    patient_id = register_patient(clinical_client, "Ada Lovelace", "07700 900123")
    live = open_encounter(clinical_client, patient_id)

    # Materialise a corpus row for the same Patient, as the evaluation harness
    # does: a real Encounter scored through the engine, marked as scaffolding.
    app = clinical_client.app
    with app.state.session_factory() as session:
        from app.models import Encounter

        corpus = Encounter(
            patient_id=patient_id,
            evaluation_run_id="run-under-test",
            **_intake_columns(LOW_INTAKE),
        )
        session.add(corpus)
        session.commit()

    response = clinical_client.get(f"/api/clinical/patients/{patient_id}/encounters")

    assert response.status_code == 200, response.text
    ids = [encounter["id"] for encounter in response.json()["encounters"]]
    assert ids == [live["id"]]


def _intake_columns(intake: dict[str, Any]) -> dict[str, Any]:
    """Map an intake payload onto the Encounter columns it is stored in."""
    return {
        "presenting_complaint": intake["presenting_complaint"],
        "pain_level": intake["pain_level"],
        "illness_duration_hours": intake["illness_duration_hours"],
        "temperature_c": intake["temperature_c"],
        "heart_rate_bpm": intake["heart_rate_bpm"],
        "systolic_bp": intake["blood_pressure"]["systolic"],
        "diastolic_bp": intake["blood_pressure"]["diastolic"],
        "oxygen_saturation_percent": intake["oxygen_saturation_percent"],
        "notes": intake["notes"],
    }

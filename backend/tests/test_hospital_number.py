"""The hospital number as an identity, at the API boundary.

A ward can hold several inpatients with the same surname and a family phone
number entered for more than one of them, so the hospital number has to be able
to tell them apart. These cases drive the HTTP API and pin the rule ADR 0014
settled: equal numbers mean one Patient, different numbers mean different
Patients, and with neither number present the earlier name-and-phone rule still
holds. They also cover the one deliberate way a number is added after
registration — the attach route — which must never merge two records.
"""

from typing import Any

from fastapi.testclient import TestClient

ADMINISTRATOR_CREDENTIALS = {
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


def register(client: TestClient, **overrides: Any):
    return client.post(
        "/api/clinical/patients",
        json={**PATIENT, **overrides},
    )


def attach(client: TestClient, patient_id: int, hospital_number: str | None):
    return client.post(
        f"/api/clinical/patients/{patient_id}/hospital-number",
        json={"hospital_number": hospital_number},
    )


def history(client: TestClient, patient_id: int) -> dict[str, Any]:
    response = client.get(f"/api/clinical/patients/{patient_id}/encounters")
    assert response.status_code == 200, response.text
    return response.json()["patient"]


def search(client: TestClient, query: str) -> list[dict[str, Any]]:
    response = client.get("/api/clinical/patients", params={"q": query})
    assert response.status_code == 200, response.text
    return response.json()["patients"]


# --- registration carries the number --------------------------------------


def test_the_registration_response_carries_the_hospital_number(
    clinical_client: TestClient,
) -> None:
    numbered = register(clinical_client, hospital_number="MRN 4471")
    unnumbered = register(
        clinical_client, full_name="Grace Hopper", contact_phone="07700 900456"
    )

    assert numbered.status_code == 201, numbered.text
    assert numbered.json()["hospital_number"] == "MRN 4471"
    assert unnumbered.status_code == 201, unnumbered.text
    # The number is optional: a walk-in with none is still registrable.
    assert unnumbered.json()["hospital_number"] is None


def test_a_whitespace_number_is_treated_as_absent(
    clinical_client: TestClient,
) -> None:
    """A blank field reads as "no number", not as a number of blanks."""
    first = register(clinical_client, hospital_number="   ")

    assert first.status_code == 201, first.text
    assert first.json()["hospital_number"] is None

    # Registered with no number, it then obeys the plain name-and-phone rule.
    second = register(clinical_client)

    assert second.status_code == 200, second.text
    assert second.json()["id"] == first.json()["id"]


def test_a_hospital_number_longer_than_the_bound_is_refused(
    clinical_client: TestClient,
) -> None:
    at_bound = register(clinical_client, hospital_number="N" * 64)
    over_bound = register(
        clinical_client,
        full_name="Grace Hopper",
        contact_phone="07700 900456",
        hospital_number="N" * 65,
    )

    assert at_bound.status_code == 201, at_bound.text
    assert at_bound.json()["hospital_number"] == "N" * 64
    assert over_bound.status_code == 422


# --- the identity rule ----------------------------------------------------


def test_two_patients_sharing_name_and_phone_stay_separate_once_numbered(
    clinical_client: TestClient,
) -> None:
    """The ward case the number exists for: same name, same family phone."""
    first = register(clinical_client, hospital_number="MRN 1")
    second = register(clinical_client, hospital_number="MRN 2")

    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert first.json()["id"] != second.json()["id"]


def test_an_equal_number_reuses_the_existing_record(
    clinical_client: TestClient,
) -> None:
    first = register(clinical_client, hospital_number="MRN 1")
    assert first.status_code == 201, first.text

    # Same number, spelled differently case and spacing: it is the same Patient.
    second = register(clinical_client, hospital_number="  mrn   1 ")

    assert second.status_code == 200, second.text
    assert second.json()["id"] == first.json()["id"]


def test_an_equal_number_reuses_the_record_even_under_a_different_name(
    clinical_client: TestClient,
) -> None:
    """The number is the identity, so it wins over a differing name."""
    first = register(clinical_client, hospital_number="MRN 1")
    assert first.status_code == 201, first.text

    second = register(
        clinical_client,
        full_name="Ada Lovelace (nee Byron)",
        contact_phone="07700 900999",
        hospital_number="MRN 1",
    )

    assert second.status_code == 200, second.text
    assert second.json()["id"] == first.json()["id"]


def test_a_patient_with_no_number_still_matches_on_name_and_phone(
    clinical_client: TestClient,
) -> None:
    first = register(clinical_client)
    assert first.status_code == 201, first.text

    second = register(clinical_client, full_name="  ada   LOVELACE ")

    assert second.status_code == 200, second.text
    assert second.json()["id"] == first.json()["id"]


def test_a_no_number_registration_does_not_reuse_a_numbered_record(
    clinical_client: TestClient,
) -> None:
    """Name and phone match only when *neither* side carries a number.

    The numbered record is left alone and a separate unnumbered one is made, so
    a registration that omits the number can never quietly take over a numbered
    Patient who happens to share the name and phone.
    """
    numbered = register(clinical_client, hospital_number="MRN 1")
    assert numbered.status_code == 201, numbered.text

    unnumbered = register(clinical_client)

    assert unnumbered.status_code == 201, unnumbered.text
    assert unnumbered.json()["id"] != numbered.json()["id"]
    assert unnumbered.json()["hospital_number"] is None
    # The numbered record keeps its number rather than being claimed.
    assert (
        history(clinical_client, numbered.json()["id"])["hospital_number"]
        == "MRN 1"
    )


def test_a_supplied_number_never_claims_an_unrelated_unnumbered_record(
    clinical_client: TestClient,
) -> None:
    """A numbered registration is matched on the number alone, not name+phone."""
    unnumbered = register(clinical_client)
    assert unnumbered.status_code == 201, unnumbered.text

    numbered = register(clinical_client, hospital_number="MRN 9")

    assert numbered.status_code == 201, numbered.text
    assert numbered.json()["id"] != unnumbered.json()["id"]
    assert numbered.json()["hospital_number"] == "MRN 9"
    # The earlier, unrelated record is untouched rather than claimed.
    assert history(clinical_client, unnumbered.json()["id"])["hospital_number"] is None


# --- attaching a number to an existing Patient ----------------------------


def test_adding_a_number_to_an_existing_patient_does_not_merge_records(
    clinical_client: TestClient,
) -> None:
    """The explicit attach acts on one chosen record; it merges nothing."""
    unnumbered = register(clinical_client)
    numbered = register(clinical_client, hospital_number="MRN 9")
    assert unnumbered.status_code == 201, unnumbered.text
    assert numbered.status_code == 201, numbered.text
    unnumbered_id = unnumbered.json()["id"]
    numbered_id = numbered.json()["id"]
    assert unnumbered_id != numbered_id

    attached = attach(clinical_client, unnumbered_id, "MRN 8")

    assert attached.status_code == 200, attached.text
    assert attached.json()["id"] == unnumbered_id
    assert attached.json()["hospital_number"] == "MRN 8"
    # Each record keeps its own number; neither absorbed the other.
    assert history(clinical_client, unnumbered_id)["hospital_number"] == "MRN 8"
    assert history(clinical_client, numbered_id)["hospital_number"] == "MRN 9"


def test_attaching_a_number_already_held_is_refused(
    clinical_client: TestClient,
) -> None:
    holder = register(clinical_client, hospital_number="MRN 1")
    other = register(
        clinical_client, full_name="Grace Hopper", contact_phone="07700 900456"
    )
    holder_id = holder.json()["id"]
    other_id = other.json()["id"]

    response = attach(clinical_client, other_id, "MRN 1")

    assert response.status_code == 409, response.text
    assert response.json() == {
        "detail": "Hospital number already belongs to another patient"
    }
    # The refused attach changed neither record.
    assert history(clinical_client, other_id)["hospital_number"] is None
    assert history(clinical_client, holder_id)["hospital_number"] == "MRN 1"


def test_attaching_to_a_patient_that_already_has_a_number_is_refused(
    clinical_client: TestClient,
) -> None:
    patient = register(clinical_client, hospital_number="MRN 1")
    assert patient.status_code == 201, patient.text

    response = attach(clinical_client, patient.json()["id"], "MRN 2")

    assert response.status_code == 409, response.text
    assert response.json() == {"detail": "Patient already has a hospital number"}
    assert history(clinical_client, patient.json()["id"])["hospital_number"] == "MRN 1"


def test_attaching_a_blank_number_is_refused(clinical_client: TestClient) -> None:
    patient = register(clinical_client)
    assert patient.status_code == 201, patient.text
    patient_id = patient.json()["id"]

    for blank in ("", "   "):
        response = attach(clinical_client, patient_id, blank)
        assert response.status_code == 422, response.text
        assert response.json() == {"detail": "hospital_number is required"}

    assert history(clinical_client, patient_id)["hospital_number"] is None


def test_attaching_to_an_unknown_patient_is_not_found(
    clinical_client: TestClient,
) -> None:
    response = attach(clinical_client, 999999, "MRN 1")

    assert response.status_code == 404
    assert response.json() == {"detail": "Patient not found"}


def test_attaching_a_number_leaves_one_attributable_audit_entry(
    clinical_client: TestClient,
) -> None:
    patient = register(clinical_client)
    assert patient.status_code == 201, patient.text
    patient_id = patient.json()["id"]
    assert attach(clinical_client, patient_id, "MRN 1").status_code == 200

    login = clinical_client.post("/api/auth/login", json=ADMINISTRATOR_CREDENTIALS)
    assert login.status_code == 200
    entries = clinical_client.get("/api/administrator/audit-log").json()["entries"]

    attached = [
        entry
        for entry in entries
        if entry["action"] == "attach_hospital_number"
    ]
    assert len(attached) == 1
    entry = attached[0]
    assert entry["action_label"] == "Hospital number attached"
    assert entry["patient_id"] == patient_id
    assert entry["encounter_id"] is None
    assert entry["actor"]["display_name"] == "Clinical Demo User"


def test_an_administrator_cannot_attach_a_hospital_number(
    client: TestClient,
) -> None:
    client.post(
        "/api/auth/login",
        json={"email": "clinical@example.com", "password": "clinical-password"},
    )
    patient_id = register(client).json()["id"]

    login = client.post("/api/auth/login", json=ADMINISTRATOR_CREDENTIALS)
    assert login.status_code == 200

    response = attach(client, patient_id, "MRN 1")

    assert response.status_code == 403
    assert response.json() == {"detail": "Role not permitted"}


def test_attaching_requires_authentication(client: TestClient) -> None:
    response = attach(client, 1, "MRN 1")

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}


# --- search ---------------------------------------------------------------


def test_search_matches_the_hospital_number(clinical_client: TestClient) -> None:
    register(clinical_client, hospital_number="MRN 4471")
    register(
        clinical_client,
        full_name="Grace Hopper",
        contact_phone="07700 900456",
        hospital_number="MRN 8899",
    )

    assert [p["full_name"] for p in search(clinical_client, "4471")] == [
        "Ada Lovelace"
    ]
    # Normalised like the stored key: case does not matter.
    assert [p["full_name"] for p in search(clinical_client, "mrn 8899")] == [
        "Grace Hopper"
    ]

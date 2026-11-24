from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient

from test_investigations import admit, discharge, record_investigation, register_patient


def login_laboratory(client: TestClient) -> TestClient:
    lab = TestClient(client.app)
    assert lab.post("/api/auth/login", json={
        "email": "laboratory@example.com", "password": "laboratory-password",
    }).status_code == 200
    return lab


def test_laboratory_returns_a_result_after_discharge(clinical_client: TestClient):
    ward = clinical_client
    lab = login_laboratory(ward)
    admission = admit(ward, register_patient(ward))
    investigation = record_investigation(ward, admission).json()["id"]
    path = f"/api/ward/investigations/{investigation}"
    lab_path = f"/api/laboratory/investigations/{investigation}"

    assert ward.get("/api/laboratory/investigations").status_code == 403
    assert lab.get("/api/laboratory/investigations").json()["incoming"] == []
    other_patient = register_patient(ward, full_name="Ada Lovelace Smith")
    other_admission = admit(ward, other_patient, bed="9")
    assert record_investigation(ward, other_admission).status_code == 201
    assert lab.post(f"{lab_path}/receive").status_code == 404
    assert ward.post(f"{path}/send").status_code == 409
    assert ward.post(f"{path}/sample-taken").status_code == 200
    assert ward.post(f"{path}/send").status_code == 200
    assert ward.post(f"{path}/send").status_code == 409
    assert ward.post(f"/api/ward/admissions/{admission}/move", json={
        "ward": "Ward B", "bed": "8",
    }).status_code == 200
    incoming = lab.get("/api/laboratory/investigations").json()["incoming"]
    assert [row["id"] for row in incoming] == [investigation]
    assert incoming[0]["patient"] == {"full_name": "Ada Lovelace", "hospital_number": None}
    assert incoming[0]["ward"] == "Ward A"
    assert incoming[0]["lab_sent_at"].endswith("Z")
    assert lab.get("/api/clinical/patients", params={"q": "Ada"}).status_code == 403
    assert lab.post(f"{lab_path}/result", json={"result_note": "A result"}).status_code == 409
    assert lab.post(f"{lab_path}/receive").status_code == 200
    assert lab.post(f"{lab_path}/receive").status_code == 409
    assert ward.post(f"{path}/result", json={"result_note": "Bypass"}).status_code == 409
    assert discharge(ward, admission).status_code == 200

    assert lab.post(f"{lab_path}/result", json={"result_note": " "}).status_code == 422
    response = lab.post(f"{lab_path}/result", json={"result_note": "A result"})
    assert response.status_code == 200, response.text
    assert response.json()["result_available_at"].endswith("Z")
    assert response.json()["lab_received_at"].endswith("Z")
    assert lab.post(f"{lab_path}/result", json={"result_note": "Overwrite"}).status_code == 409
    late = ward.get("/api/ward/investigations/late-results").json()["investigations"]
    assert [(row["id"], row["admission_id"], row["result_note"]) for row in late] == [
        (investigation, admission, "A result"),
    ]
    assert late[0]["result_published_by"]["display_name"] == "Laboratory Demo User"
    assert lab.post(f"{path}/review").status_code == 403
    assert ward.post(f"{path}/review").json()["state"] == "reviewed"
    assert ward.get("/api/ward/investigations/late-results").json()["investigations"] == []


def test_concurrent_publication_returns_one_result_to_the_open_ward(clinical_client: TestClient):
    ward = clinical_client
    lab_sessions = [login_laboratory(ward), login_laboratory(ward)]
    admin = TestClient(ward.app)
    assert admin.post("/api/auth/login", json={
        "email": "administrator@example.com", "password": "administrator-password",
    }).status_code == 200
    admission = admit(ward, register_patient(ward))
    request = record_investigation(ward, admission).json()
    path = f"/api/ward/investigations/{request['id']}"
    lab_path = f"/api/laboratory/investigations/{request['id']}"
    assert admin.get("/api/laboratory/investigations").status_code == 403
    assert lab_sessions[0].get("/api/clinical/access").status_code == 403
    assert lab_sessions[0].get("/api/administrator/access").status_code == 403
    assert ward.post(f"{path}/sample-taken").status_code == 200
    assert ward.post(f"{path}/send").status_code == 200
    assert lab_sessions[0].post(f"{lab_path}/receive").status_code == 200

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(
            lambda session: session.post(f"{lab_path}/result", json={"result_note": "Report text"}),
            lab_sessions,
        ))
    assert sorted(response.status_code for response in responses) == [200, 409]
    worklist = lab_sessions[0].get("/api/laboratory/investigations").json()
    assert worklist["incoming"] == worklist["acknowledged"] == []
    assert [row["id"] for row in worklist["published"]] == [request["id"]]
    awaiting = ward.get("/api/ward/investigations/awaiting-review").json()["investigations"]
    assert [(row["id"], row["result_note"]) for row in awaiting] == [(request["id"], "Report text")]
    assert ward.post(f"{path}/review").status_code == 200
    log = admin.get("/api/administrator/audit-log").json()
    actions = [row["action"] for row in log["entries"]]
    for action in (
        "send_investigation_to_lab", "acknowledge_lab_investigation",
        "publish_lab_result", "review_investigation",
    ):
        assert actions.count(action) == 1

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.audit import record_audit_entry
from app.audit_actions import AuditAction
from app.departures import encounter_status, end_encounter, ensure_open
from app.deps import DbSession, require_role
from app.intake import apply_visit_reason
from app.models import (
    Admission,
    Encounter,
    Observation,
    Patient,
    Role,
    StudyTaskRun,
    User,
)
from app.observations import (
    observation_response,
    observation_response_for,
    stage_observation,
)
from app.patients import (
    find_or_create_patient,
    normalise_hospital_number,
    search_patients as patient_search,
)
from app.schemas import (
    EncounterCreateRequest,
    EncounterListResponse,
    EncounterResponse,
    HospitalNumberRequest,
    IntakePayload,
    ObservationPayload,
    ObservationResponse,
    PatientHistoryResponse,
    PatientObservationsResponse,
    PatientRegistrationRequest,
    PatientResponse,
    PatientSearchResponse,
    StudyTaskRunAbandonRequest,
    StudyTaskRunCreateRequest,
    StudyTaskRunEndRequest,
    StudyTaskRunListResponse,
    StudyTaskRunResponse,
    VisitReasonPayload,
)
from app.timeutils import utc_now

router = APIRouter(prefix="/api/clinical", tags=["clinical"])

ClinicalUser = Annotated[User, Depends(require_role(Role.clinical))]

DEFAULT_LIMIT = 20
MAX_LIMIT = 100

#: Refusals for charting against a closed subject. Ticket 31 owns the discharge
#: route; the stay is closed in the data layer here by a set ``discharged_at``,
#: the same open/ended pattern ``departures.ensure_open`` applies to a visit.
ENDED_VISIT_CHART_DETAIL = (
    "An Encounter that has already ended cannot take new Observations"
)
DISCHARGED_ADMISSION_CHART_DETAIL = (
    "A discharged Admission cannot take new Observations"
)


@router.get("/access")
def clinical_access(user: ClinicalUser) -> dict[str, str]:
    return {
        "role": Role.clinical.value,
        "message": "Clinical access granted",
    }


@router.post(
    "/patients",
    response_model=PatientResponse,
    status_code=status.HTTP_201_CREATED,
)
def register_patient(
    payload: PatientRegistrationRequest,
    response: Response,
    db: DbSession,
    user: ClinicalUser,
) -> Patient:
    """Register a Patient, or reuse the existing record for the same person.

    ``201 Created`` when a new Patient is registered, ``200 OK`` when an
    existing record is reused.

    The route commits, so the Patient row and its audit entry land in one
    transaction. ``find_or_create_patient`` no longer commits internally for
    exactly this reason: a re-registration reuses a record, so it is not a
    mutation and writes no audit entry.
    """
    patient, created = find_or_create_patient(
        db,
        full_name=payload.full_name,
        age=payload.age,
        sex=payload.sex,
        contact_phone=payload.contact_phone,
        contact_email=payload.contact_email,
        hospital_number=payload.hospital_number,
    )
    if not created:
        response.status_code = status.HTTP_200_OK
    else:
        record_audit_entry(
            db,
            actor=user,
            action=AuditAction.register_patient,
            patient=patient,
        )
    db.commit()
    return patient


@router.post(
    "/patients/{patient_id}/hospital-number",
    response_model=PatientResponse,
)
def attach_hospital_number(
    patient_id: int,
    payload: HospitalNumberRequest,
    db: DbSession,
    user: ClinicalUser,
) -> Patient:
    """Attach a hospital number to an existing Patient that carries none.

    Registration never lets a supplied number claim an unrelated name-and-phone
    record, so giving a number to an already-registered Patient is a separate,
    explicit act on one *chosen* record. The route refuses a blank number
    (``422``) and any attempt to set a number the Patient already holds or that
    belongs to another Patient (``409``), so it can never merge two records or
    silently reassign a number. The change and its audit entry commit together.
    """
    patient = db.get(Patient, patient_id)
    if patient is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient not found",
        )

    if payload.hospital_number is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="hospital_number is required",
        )
    hospital_number_key = normalise_hospital_number(payload.hospital_number)

    holder = db.scalar(
        select(Patient).where(
            Patient.hospital_number_key == hospital_number_key,
            Patient.id != patient.id,
        )
    )
    if holder is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Hospital number already belongs to another patient",
        )

    if patient.hospital_number_key is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Patient already has a hospital number",
        )

    patient.hospital_number = payload.hospital_number
    patient.hospital_number_key = hospital_number_key
    record_audit_entry(
        db,
        actor=user,
        action=AuditAction.attach_hospital_number,
        patient=patient,
    )
    try:
        db.commit()
    except IntegrityError:
        # A concurrent attach claimed the number between the lookup and the
        # commit; the unique index caught it, so report the conflict rather than
        # letting the failure surface as a 500.
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Hospital number already belongs to another patient",
        ) from None
    return patient


@router.post(
    "/encounters",
    response_model=EncounterResponse,
    status_code=status.HTTP_201_CREATED,
)
def open_encounter(
    payload: EncounterCreateRequest,
    db: DbSession,
    user: ClinicalUser,
) -> EncounterResponse:
    patient = db.get(Patient, payload.patient_id)
    if patient is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient not found",
        )

    encounter = Encounter(patient_id=patient.id)
    apply_visit_reason(encounter, payload.intake)
    db.add(encounter)
    db.flush()
    record_audit_entry(
        db,
        actor=user,
        action=AuditAction.open_encounter,
        patient=patient,
        encounter=encounter,
    )
    # A full intake carries the first set of vitals as well as the reason. Those
    # readings become the visit's first Observation, in this same transaction;
    # they are never written onto the Encounter. The open entry above already
    # covers this transaction, so the first Observation is not logged a second
    # time: opening a visit writes exactly one audit entry (documented boundary).
    if isinstance(payload.intake, IntakePayload):
        stage_observation(
            db,
            actor=user,
            payload=payload.intake,
            patient=patient,
            encounter=encounter,
        )
    db.commit()
    return _encounter_response(encounter)


@router.get("/patients", response_model=PatientSearchResponse)
def search_patients(
    db: DbSession,
    user: ClinicalUser,
    q: Annotated[str, Query()] = "",
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
) -> PatientSearchResponse:
    """Find Patients by a fragment of their name, contact number or hospital number.

    This is not identity resolution. ``app.patients`` matches an identity on the
    hospital number when one is present, and otherwise on the whole name
    together with the whole phone; a search matches part of a name, a contact
    number or a hospital number and returns candidates for a human to choose
    between. A blank query returns nothing, so the route is never a bulk export.
    """
    patients = patient_search(db, query=q, limit=limit)
    return PatientSearchResponse(
        patients=[PatientResponse.model_validate(patient) for patient in patients]
    )


@router.get(
    "/patients/{patient_id}/encounters",
    response_model=PatientHistoryResponse,
)
def get_patient_history(
    patient_id: int,
    db: DbSession,
    user: ClinicalUser,
) -> PatientHistoryResponse:
    """One Patient's Encounters over time, oldest first.

    Every visit is rendered through the same helper the rest of the API uses. An
    unknown Patient is a 404, consistent with the encounter lookup.
    """
    patient = db.get(Patient, patient_id)
    if patient is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient not found",
        )

    encounters = db.scalars(
        select(Encounter)
        .where(Encounter.patient_id == patient.id)
        .order_by(Encounter.arrived_at, Encounter.id)
    ).all()
    return PatientHistoryResponse(
        patient=PatientResponse.model_validate(patient),
        encounters=[_encounter_response(encounter) for encounter in encounters],
    )


@router.get("/encounters", response_model=EncounterListResponse)
def list_recent_encounters(
    db: DbSession,
    user: ClinicalUser,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
) -> EncounterListResponse:
    """Encounters most recently opened first, for reviewing a saved intake."""
    encounters = db.scalars(
        select(Encounter)
        .order_by(Encounter.arrived_at.desc(), Encounter.id.desc())
        .limit(limit)
    ).all()
    return EncounterListResponse(
        encounters=[_encounter_response(encounter) for encounter in encounters]
    )


@router.get("/encounters/{encounter_id}", response_model=EncounterResponse)
def get_encounter(
    encounter_id: int,
    db: DbSession,
    user: ClinicalUser,
) -> EncounterResponse:
    return _encounter_response(_get_encounter(db, encounter_id))


@router.post(
    "/encounters/{encounter_id}/observations",
    response_model=ObservationResponse,
    status_code=status.HTTP_201_CREATED,
)
def chart_encounter_observation(
    encounter_id: int,
    payload: ObservationPayload,
    db: DbSession,
    user: ClinicalUser,
) -> ObservationResponse:
    """Chart a set of vitals against a visit, appending one Observation.

    The set and its audit entry commit together. An unknown Encounter is a 404;
    a visit that has already ended takes no new sets (``409``), and a refused
    request writes neither an Observation nor an audit entry. Reading the visit's
    chart is unaffected, so an ended visit keeps its history.
    """
    encounter = _get_encounter(db, encounter_id)
    ensure_open(encounter, ENDED_VISIT_CHART_DETAIL)
    observation = stage_observation(
        db,
        actor=user,
        payload=payload,
        patient=encounter.patient,
        encounter=encounter,
    )
    db.flush()
    record_audit_entry(
        db,
        actor=user,
        action=AuditAction.chart_observation,
        patient=encounter.patient,
        encounter=encounter,
    )
    db.commit()
    return observation_response(db, observation)


@router.post(
    "/admissions/{admission_id}/observations",
    response_model=ObservationResponse,
    status_code=status.HTTP_201_CREATED,
)
def chart_admission_observation(
    admission_id: int,
    payload: ObservationPayload,
    db: DbSession,
    user: ClinicalUser,
) -> ObservationResponse:
    """Chart a set of vitals against a stay, appending one Observation.

    The set and its audit entry commit together. An unknown Admission is a 404;
    a discharged stay takes no new sets (``409``), and a refused request writes
    neither an Observation nor an audit entry. Reading the stay's chart is
    unaffected, so a discharged stay keeps its history.
    """
    admission = db.get(Admission, admission_id)
    if admission is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Admission not found",
        )
    if admission.discharged_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=DISCHARGED_ADMISSION_CHART_DETAIL,
        )
    observation = stage_observation(
        db,
        actor=user,
        payload=payload,
        patient=admission.patient,
        admission=admission,
    )
    db.flush()
    record_audit_entry(
        db,
        actor=user,
        action=AuditAction.chart_observation,
        patient=admission.patient,
        # A set charted on the ward is attributed to the stay it belongs to, so a
        # stay's history reads in one place alongside its admissions and moves.
        admission=admission,
    )
    db.commit()
    return observation_response(db, observation)


@router.get(
    "/patients/{patient_id}/observations",
    response_model=PatientObservationsResponse,
)
def get_patient_observations(
    patient_id: int,
    db: DbSession,
    user: ClinicalUser,
) -> PatientObservationsResponse:
    """One Patient's Observation chart, newest first.

    Every reading is returned beside the value taken before it, so the chart
    shows the direction of travel. An unknown Patient is a 404; an empty chart
    is an empty list, not a row of zeros.
    """
    patient = db.get(Patient, patient_id)
    if patient is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient not found",
        )

    observations = db.scalars(
        select(Observation)
        .where(Observation.patient_id == patient.id)
        .order_by(Observation.taken_at, Observation.id)
    ).all()

    responses: list[ObservationResponse] = []
    previous: Observation | None = None
    for observation in observations:
        responses.append(observation_response_for(observation, previous))
        previous = observation
    responses.reverse()
    return PatientObservationsResponse(observations=responses)


@router.put("/encounters/{encounter_id}/intake", response_model=EncounterResponse)
def correct_visit_reason(
    encounter_id: int,
    payload: VisitReasonPayload,
    db: DbSession,
    user: ClinicalUser,
) -> EncounterResponse:
    """Replace the reason for the visit on an Encounter.

    The reason is not frozen by anything, so this route always succeeds for a
    known Encounter. Vitals in the body are refused (``422``), not dropped.
    """
    encounter = _get_encounter(db, encounter_id)
    apply_visit_reason(encounter, payload)
    record_audit_entry(
        db,
        actor=user,
        action=AuditAction.correct_visit_reason,
        patient=encounter.patient,
        encounter=encounter,
    )
    db.commit()
    return _encounter_response(encounter)


@router.post("/encounters/{encounter_id}/end", response_model=EncounterResponse)
def end_visit(
    encounter_id: int,
    db: DbSession,
    user: ClinicalUser,
) -> EncounterResponse:
    """End a visit, recording the end instant now.

    Manual only: the instant is the server's clock at the moment of the request,
    never a value the caller supplies. A visit that has already ended is refused
    with ``409``; an unknown Encounter is a ``404``. The end and its single audit
    entry land in one transaction.
    """
    encounter = _get_encounter(db, encounter_id)
    end_encounter(db, encounter)
    record_audit_entry(
        db,
        actor=user,
        action=AuditAction.end_encounter,
        patient=encounter.patient,
        encounter=encounter,
    )
    db.commit()
    return _encounter_response(encounter)


def _get_encounter(db: Session, encounter_id: int) -> Encounter:
    encounter = db.get(Encounter, encounter_id)
    if encounter is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Encounter not found",
        )
    return encounter


def _encounter_response(encounter: Encounter) -> EncounterResponse:
    return EncounterResponse(
        id=encounter.id,
        arrived_at=encounter.arrived_at,
        ended_at=encounter.ended_at,
        status=encounter_status(encounter),
        patient=PatientResponse.model_validate(encounter.patient),
        reason_for_visit=encounter.reason_for_visit,
    )


# =============================================================================
# Study Instrumentation (ticket 40)
#
# A timed study task run, behind a setting that is off in normal ward use. The
# run carries an anonymised participant identifier and a task label, never the
# nurse's identity, and never joins to a Patient. Begin, end and abandon are
# explicit actions, so a run is deliberate rather than inferred from activity,
# and an abandoned run is recorded as abandoned rather than as a very long one.
# =============================================================================


def _require_instrumentation(request: Request) -> None:
    """Refuse the study routes when the instrumentation is switched off."""
    if not request.app.state.settings.study_instrumentation_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Study instrumentation is not enabled",
        )


def _get_study_run(db: Session, run_id: int) -> StudyTaskRun:
    run = db.get(StudyTaskRun, run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Study task run not found",
        )
    return run


def _ensure_owned_and_open(run: StudyTaskRun, participant_id: str) -> None:
    """A run is only ended or abandoned by its own participant, and only once."""
    if run.participant_id != participant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Participant id does not match the run",
        )
    if run.ended_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Run already ended",
        )


@router.post(
    "/study-task-runs",
    response_model=StudyTaskRunResponse,
    status_code=status.HTTP_201_CREATED,
)
def start_study_task_run(
    payload: StudyTaskRunCreateRequest,
    request: Request,
    db: DbSession,
    user: ClinicalUser,
) -> StudyTaskRunResponse:
    """Begin a timed study task run and record its start instant."""
    _require_instrumentation(request)
    run = StudyTaskRun(
        task_label=payload.task_label,
        participant_id=payload.participant_id,
        started_at=utc_now(),
        status="running",
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return StudyTaskRunResponse.model_validate(run)


@router.patch(
    "/study-task-runs/{run_id}/end",
    response_model=StudyTaskRunResponse,
)
def end_study_task_run(
    run_id: int,
    payload: StudyTaskRunEndRequest,
    request: Request,
    db: DbSession,
    user: ClinicalUser,
) -> StudyTaskRunResponse:
    """End a run, recording its end instant. Only its own participant may."""
    _require_instrumentation(request)
    run = _get_study_run(db, run_id)
    _ensure_owned_and_open(run, payload.participant_id)
    run.ended_at = utc_now()
    run.status = "completed"
    db.commit()
    db.refresh(run)
    return StudyTaskRunResponse.model_validate(run)


@router.patch(
    "/study-task-runs/{run_id}/abandon",
    response_model=StudyTaskRunResponse,
)
def abandon_study_task_run(
    run_id: int,
    payload: StudyTaskRunAbandonRequest,
    request: Request,
    db: DbSession,
    user: ClinicalUser,
) -> StudyTaskRunResponse:
    """Mark a run abandoned rather than recording a very long duration."""
    _require_instrumentation(request)
    run = _get_study_run(db, run_id)
    _ensure_owned_and_open(run, payload.participant_id)
    run.ended_at = utc_now()
    run.status = "abandoned"
    db.commit()
    db.refresh(run)
    return StudyTaskRunResponse.model_validate(run)


@router.get(
    "/study-task-runs",
    response_model=StudyTaskRunListResponse,
)
def list_study_task_runs(
    request: Request,
    db: DbSession,
    user: ClinicalUser,
) -> StudyTaskRunListResponse:
    """List every study task run, oldest first, for the write-up's export."""
    _require_instrumentation(request)
    runs = db.scalars(
        select(StudyTaskRun).order_by(StudyTaskRun.started_at)
    ).all()
    return StudyTaskRunListResponse(
        runs=[StudyTaskRunResponse.model_validate(run) for run in runs]
    )

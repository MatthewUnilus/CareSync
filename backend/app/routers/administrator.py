from typing import Annotated

from fastapi import APIRouter, Depends

from app.deps import DbSession, require_role
from app.models import Role, User
from app.queue import administrator_queue
from app.schemas import AdministratorQueueEntryResponse, AdministratorQueueResponse
from app.timeutils import utc_now

router = APIRouter(prefix="/api/administrator", tags=["administrator"])

AdministratorUser = Annotated[User, Depends(require_role(Role.administrator))]


@router.get("/access")
def administrator_access(user: AdministratorUser) -> dict[str, str]:
    return {
        "role": Role.administrator.value,
        "message": "Administrator access granted",
    }


@router.get("/queue", response_model=AdministratorQueueResponse)
def get_administrator_queue(
    db: DbSession,
    user: AdministratorUser,
) -> AdministratorQueueResponse:
    """The awaiting Queue as a dense, read-only table.

    Reports will mount here as further Administrator-only read routes; neither
    this route nor the dashboard offers any clinical action.
    """
    now = utc_now()
    return AdministratorQueueResponse(
        as_of=now,
        entries=[
            AdministratorQueueEntryResponse(
                encounter_id=row.encounter_id,
                arrived_at=row.arrived_at,
                waiting_seconds=row.waiting_seconds,
                urgency_level=row.urgency_level,
                patient_name=row.patient_name,
                presenting_complaint=row.presenting_complaint,
                machine_recommendation=row.machine_recommendation,
                final_decision=row.final_decision,
                final_decision_differs=row.final_decision_differs,
            )
            for row in administrator_queue(db, now)
        ],
    )

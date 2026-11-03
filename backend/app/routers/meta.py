from fastapi import APIRouter

from app.models import ROLE_LABELS, Role
from app.schemas import RoleDescriptor, RolesResponse

router = APIRouter(prefix="/api", tags=["meta"])


@router.get("/roles", response_model=RolesResponse)
def list_roles() -> RolesResponse:
    return RolesResponse(
        roles=[
            RoleDescriptor(value=role, label=ROLE_LABELS[role])
            for role in Role
        ]
    )

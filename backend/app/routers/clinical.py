from typing import Annotated

from fastapi import APIRouter, Depends

from app.deps import require_role
from app.models import Role, User

router = APIRouter(prefix="/api/clinical", tags=["clinical"])


@router.get("/access")
def clinical_access(
    user: Annotated[User, Depends(require_role(Role.clinical))],
) -> dict[str, str]:
    return {
        "role": Role.clinical.value,
        "message": "Clinical access granted",
    }

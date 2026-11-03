from typing import Annotated

from fastapi import APIRouter, Depends

from app.deps import require_role
from app.models import Role, User

router = APIRouter(prefix="/api/administrator", tags=["administrator"])


@router.get("/access")
def administrator_access(
    user: Annotated[User, Depends(require_role(Role.administrator))],
) -> dict[str, str]:
    return {
        "role": Role.administrator.value,
        "message": "Administrator access granted",
    }

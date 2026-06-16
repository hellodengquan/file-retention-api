from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth import get_current_active_user, RoleChecker
from app.database import get_db
from app import crud
from app.models import User
from app.schemas import AuditLogResponse, PaginatedResponse
from typing import List

router = APIRouter(prefix="/audit-logs", tags=["审计日志"])
role_admin = RoleChecker(["admin"])


@router.get("", response_model=PaginatedResponse[AuditLogResponse], dependencies=[Depends(role_admin)])
def list_audit_logs(
    skip: int = 0,
    limit: int = 100,
    user_id: Optional[int] = None,
    action: Optional[str] = None,
    resource_type: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    logs = crud.list_audit_logs(
        db, skip=skip, limit=limit,
        user_id=user_id, action=action, resource_type=resource_type
    )
    total = crud.count_audit_logs(
        db, user_id=user_id, action=action, resource_type=resource_type
    )
    return {"total": total, "skip": skip, "limit": limit, "items": logs}

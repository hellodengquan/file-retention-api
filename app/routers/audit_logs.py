from typing import Optional
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth import get_current_active_user_checked, RoleChecker
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
    username: Optional[str] = None,
    action: Optional[str] = None,
    resource_type: Optional[str] = None,
    resource_id: Optional[int] = None,
    start_time: Optional[datetime] = Query(default=None, description="开始时间 (ISO格式)"),
    end_time: Optional[datetime] = Query(default=None, description="结束时间 (ISO格式)"),
    ip_address: Optional[str] = None,
    keyword: Optional[str] = Query(default=None, description="关键词模糊搜索 (动作、详情、用户名、资源类型)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user_checked)
):
    logs = crud.list_audit_logs(
        db, skip=skip, limit=limit,
        user_id=user_id, username=username,
        action=action, resource_type=resource_type,
        resource_id=resource_id,
        start_time=start_time, end_time=end_time,
        ip_address=ip_address, keyword=keyword
    )
    total = crud.count_audit_logs(
        db,
        user_id=user_id, username=username,
        action=action, resource_type=resource_type,
        resource_id=resource_id,
        start_time=start_time, end_time=end_time,
        ip_address=ip_address, keyword=keyword
    )
    return {"total": total, "skip": skip, "limit": limit, "items": logs}


@router.get("/stats/actions", dependencies=[Depends(role_admin)])
def get_audit_actions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user_checked)
):
    from app.models import AuditLog
    from sqlalchemy import func
    results = db.query(
        AuditLog.action,
        func.count(AuditLog.id).label("count")
    ).group_by(AuditLog.action).all()
    return [{"action": r.action, "count": r.count} for r in results]

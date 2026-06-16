from typing import Optional
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.auth import get_current_active_user_checked, RoleChecker
from app.database import get_db
from app import crud
from app.models import User, AuditLog
from app.schemas import AuditLogResponse, PaginatedResponse, AuditStatsResponse
from typing import List

router = APIRouter(prefix="/audit-logs", tags=["审计日志"])
role_admin = RoleChecker(["admin"])
role_admin_manager = RoleChecker(["admin", "manager"])


@router.get("", response_model=PaginatedResponse[AuditLogResponse])
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
    filter_user_id = None
    if current_user.role == "operator":
        filter_user_id = current_user.id
    elif current_user.role == "manager" and user_id is None:
        pass
    elif user_id:
        filter_user_id = user_id

    if current_user.role == "operator":
        user_id = filter_user_id

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


@router.get("/stats/actions", dependencies=[Depends(role_admin_manager)])
def get_audit_actions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user_checked)
):
    query = db.query(AuditLog)
    if current_user.role == "operator":
        query = query.filter(AuditLog.user_id == current_user.id)
    results = query.with_entities(
        AuditLog.action,
        func.count(AuditLog.id).label("count")
    ).group_by(AuditLog.action).all()
    return [{"action": r.action, "count": r.count} for r in results]


@router.get("/stats/dashboard", response_model=AuditStatsResponse, dependencies=[Depends(role_admin_manager)])
def get_audit_dashboard(
    days: int = Query(default=7, description="统计最近N天"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user_checked)
):
    base_query = db.query(AuditLog)
    if current_user.role == "operator":
        base_query = base_query.filter(AuditLog.user_id == current_user.id)

    total_logs = base_query.count()

    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_logs = base_query.filter(AuditLog.timestamp >= today_start).count()

    action_stats = base_query.with_entities(
        AuditLog.action,
        func.count(AuditLog.id).label("count")
    ).group_by(AuditLog.action).order_by(func.count(AuditLog.id).desc()).limit(10).all()
    action_stats = [{"action": r.action, "count": r.count} for r in action_stats]

    resource_type_stats = base_query.with_entities(
        AuditLog.resource_type,
        func.count(AuditLog.id).label("count")
    ).filter(AuditLog.resource_type.isnot(None)).group_by(AuditLog.resource_type).all()
    resource_type_stats = [{"resource_type": r.resource_type, "count": r.count} for r in resource_type_stats]

    user_stats = base_query.with_entities(
        AuditLog.username,
        func.count(AuditLog.id).label("count")
    ).filter(AuditLog.username.isnot(None)).group_by(AuditLog.username).order_by(func.count(AuditLog.id).desc()).limit(10).all()
    user_stats = [{"username": r.username, "count": r.count} for r in user_stats]

    daily_stats = []
    for i in range(days - 1, -1, -1):
        day_start = (datetime.utcnow() - timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        count = base_query.filter(
            AuditLog.timestamp >= day_start,
            AuditLog.timestamp < day_end
        ).count()
        daily_stats.append({
            "date": day_start.strftime("%Y-%m-%d"),
            "count": count
        })

    return {
        "total_logs": total_logs,
        "today_logs": today_logs,
        "action_stats": action_stats,
        "resource_type_stats": resource_type_stats,
        "user_stats": user_stats,
        "daily_stats": daily_stats
    }

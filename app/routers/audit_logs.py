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


def _mask_log_details(details: Optional[str]) -> Optional[str]:
    if not details:
        return details
    sensitive_keywords = ["密码", "password", "token", "secret", "密钥", "凭证"]
    masked = details
    for kw in sensitive_keywords:
        if kw.lower() in masked.lower():
            masked = masked[:30] + "..." + "[已脱敏]" if len(masked) > 30 else "[已脱敏]"
            break
    return masked


def _filter_logs_by_permission(logs, user: User):
    if user.role == "admin":
        return logs
    filtered = []
    for log in logs:
        log_dict = {
            "id": log.id,
            "timestamp": log.timestamp,
            "user_id": log.user_id,
            "username": log.username,
            "action": log.action,
            "resource_type": log.resource_type,
            "resource_id": log.resource_id,
            "details": _mask_log_details(log.details) if user.role == "operator" else log.details,
            "ip_address": log.ip_address if user.role == "admin" else (
                ".".join(log.ip_address.split(".")[:2]) + ".*.*" if log.ip_address and "." in log.ip_address else log.ip_address
            ) if user.role == "manager" else "[已脱敏]"
        }
        filtered.append(log_dict)
    return filtered


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
        user_id = current_user.id

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

    filtered_logs = _filter_logs_by_permission(logs, current_user)
    return {"total": total, "skip": skip, "limit": limit, "items": filtered_logs}


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


@router.get("/stats/dashboard", response_model=AuditStatsResponse)
def get_audit_dashboard(
    days: int = Query(default=7, description="统计最近N天"),
    granularity: str = Query(default="day", description="聚合粒度: hour/day/week"),
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

    if current_user.role == "admin":
        user_stats = base_query.with_entities(
            AuditLog.username,
            func.count(AuditLog.id).label("count")
        ).filter(AuditLog.username.isnot(None)).group_by(AuditLog.username).order_by(func.count(AuditLog.id).desc()).limit(10).all()
        user_stats = [{"username": r.username, "count": r.count} for r in user_stats]
    elif current_user.role == "manager":
        user_stats = base_query.with_entities(
            AuditLog.username,
            func.count(AuditLog.id).label("count")
        ).filter(AuditLog.username.isnot(None)).group_by(AuditLog.username).order_by(func.count(AuditLog.id).desc()).limit(5).all()
        user_stats = [{"username": r.username, "count": r.count} for r in user_stats]
    else:
        user_stats = [{"username": current_user.username, "count": total_logs}]

    daily_stats = []
    now = datetime.utcnow()

    if granularity == "hour":
        hours = min(days * 24, 168)
        for i in range(hours - 1, -1, -1):
            hour_start = (now - timedelta(hours=i)).replace(minute=0, second=0, microsecond=0)
            hour_end = hour_start + timedelta(hours=1)
            count = base_query.filter(
                AuditLog.timestamp >= hour_start,
                AuditLog.timestamp < hour_end
            ).count()
            daily_stats.append({
                "date": hour_start.strftime("%Y-%m-%d %H:00"),
                "count": count
            })
    elif granularity == "week":
        weeks = min((days // 7) + 1, 12)
        for i in range(weeks - 1, -1, -1):
            week_start = (now - timedelta(weeks=i)).replace(hour=0, minute=0, second=0, microsecond=0)
            week_start = week_start - timedelta(days=week_start.weekday())
            week_end = week_start + timedelta(weeks=1)
            count = base_query.filter(
                AuditLog.timestamp >= week_start,
                AuditLog.timestamp < week_end
            ).count()
            daily_stats.append({
                "date": week_start.strftime("%Y-%m-%d"),
                "count": count
            })
    else:
        for i in range(days - 1, -1, -1):
            day_start = (now - timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0)
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

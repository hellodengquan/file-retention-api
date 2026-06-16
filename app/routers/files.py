from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.auth import (
    get_current_active_user_checked, RoleChecker, log_audit, get_client_ip
)
from app.database import get_db
from app import crud
from app.models import User
from app.schemas import (
    FileRecordCreate, FileRecordUpdate, FileRecordResponse, PaginatedResponse,
    FileRestoreRequest, BatchRematchRequest, BatchRematchResult
)
from typing import List

router = APIRouter(prefix="/files", tags=["文件记录"])
role_admin = RoleChecker(["admin"])
role_admin_manager = RoleChecker(["admin", "manager"])


@router.post("", response_model=FileRecordResponse)
def create_file(
    file_in: FileRecordCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user_checked)
):
    file = crud.create_file(db, file_in, current_user.id)
    ip = get_client_ip(request)
    log_audit(
        db, current_user, "create_file", "file", file.id,
        f"创建文件记录: {file.file_name}, 类别: {file.business_category}", ip
    )
    return file


@router.get("", response_model=PaginatedResponse[FileRecordResponse])
def list_files(
    skip: int = 0,
    limit: int = 100,
    business_category: Optional[str] = None,
    status: Optional[str] = None,
    created_by: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user_checked)
):
    if current_user.role == "operator":
        created_by = current_user.id
    files = crud.list_files(
        db, skip=skip, limit=limit,
        business_category=business_category,
        status=status, created_by=created_by
    )
    total = crud.count_files(
        db, business_category=business_category,
        status=status, created_by=created_by
    )
    return {"total": total, "skip": skip, "limit": limit, "items": files}


@router.get("/{file_id}", response_model=FileRecordResponse)
def get_file(
    file_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user_checked)
):
    file = crud.get_file(db, file_id)
    if not file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="文件不存在"
        )
    if current_user.role == "operator" and file.created_by != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="权限不足"
        )
    return file


@router.put("/{file_id}", response_model=FileRecordResponse)
def update_file(
    file_id: int,
    file_in: FileRecordUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user_checked)
):
    file = crud.get_file(db, file_id)
    if not file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="文件不存在"
        )
    if current_user.role == "operator" and file.created_by != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="权限不足"
        )
    if (file_in.status or file_in.business_category) and current_user.role == "operator":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权修改文件状态或业务类别"
        )
    updated_file = crud.update_file(db, file_id, file_in)
    ip = get_client_ip(request)
    log_details = f"更新文件记录: {file.file_name}"
    if file_in.business_category:
        log_details += f", 业务类别变更为: {file_in.business_category}"
    if file_in.status:
        log_details += f", 状态变更为: {file_in.status}"
    log_audit(
        db, current_user, "update_file", "file", file_id, log_details, ip
    )
    return updated_file


@router.post("/{file_id}/restore", response_model=FileRecordResponse)
def restore_archived_file(
    file_id: int,
    restore_req: FileRestoreRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user_checked)
):
    file = crud.get_file(db, file_id)
    if not file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="文件不存在"
        )
    if file.status not in ("archived", "expired"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="只有已归档或已过期的文件才能恢复"
        )
    if current_user.role == "operator" and file.created_by != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="权限不足"
        )
    can_restore, msg = crud.can_restore_file(db, file_id)
    if not can_restore:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=msg
        )
    restored = crud.restore_file(db, file_id)
    ip = get_client_ip(request)
    reason = restore_req.reason or "未填写原因"
    log_audit(
        db, current_user, "restore_file", "file", file_id,
        f"恢复文件: {file.file_name}, 原因: {reason}", ip
    )
    return restored


@router.delete("/{file_id}", dependencies=[Depends(role_admin)])
def delete_file(
    file_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user_checked)
):
    file = crud.get_file(db, file_id)
    if not file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="文件不存在"
        )
    crud.delete_file(db, file_id)
    ip = get_client_ip(request)
    log_audit(
        db, current_user, "delete_file", "file", file_id,
        f"删除文件记录: {file.file_name}", ip
    )
    return {"message": "文件记录删除成功"}


@router.post("/batch-rematch", response_model=BatchRematchResult, dependencies=[Depends(role_admin)])
def batch_rematch_policies(
    rematch_req: BatchRematchRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user_checked)
):
    total, matched, updated = crud.batch_rematch_policies(
        db, business_category=rematch_req.business_category,
        dry_run=rematch_req.dry_run
    )
    ip = get_client_ip(request)
    log_audit(
        db, current_user, "batch_rematch_policies", "policy", None,
        f"批量策略重匹配: 类别={rematch_req.business_category or '全部'}, "
        f"总数={total}, 匹配={matched}, 更新={updated}, dry_run={rematch_req.dry_run}",
        ip
    )
    return {
        "total": total,
        "matched": matched,
        "updated": updated,
        "dry_run": rematch_req.dry_run
    }

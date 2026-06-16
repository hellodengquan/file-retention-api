from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session

from app.auth import get_current_active_user, RoleChecker, log_audit, get_client_ip
from app.database import get_db
from app import crud
from app.models import User
from app.schemas import (
    ExtensionRequestCreate, ExtensionRequestDecision, ExtensionRequestResponse, PaginatedResponse
)
from typing import List

router = APIRouter(prefix="/extensions", tags=["延期审批"])
role_admin_manager = RoleChecker(["admin", "manager"])


@router.post("", response_model=ExtensionRequestResponse)
def create_extension_request(
    request_in: ExtensionRequestCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    file = crud.get_file(db, request_in.file_id)
    if not file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="文件不存在"
        )
    if current_user.role == "operator" and file.created_by != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权为他人文件申请延期"
        )
    ext_request = crud.create_extension_request(db, request_in, current_user.id)
    ip = get_client_ip(request)
    log_audit(
        db, current_user, "create_extension_request", "extension", ext_request.id,
        f"申请文件延期: 文件ID={request_in.file_id}, 延期天数={request_in.requested_days}", ip
    )
    return ext_request


@router.get("", response_model=PaginatedResponse[ExtensionRequestResponse])
def list_extension_requests(
    skip: int = 0,
    limit: int = 100,
    status: Optional[str] = None,
    requester_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    if current_user.role == "operator":
        requester_id = current_user.id
    requests = crud.list_extension_requests(
        db, skip=skip, limit=limit, status=status, requester_id=requester_id
    )
    total = crud.count_extension_requests(db, status=status, requester_id=requester_id)
    return {"total": total, "skip": skip, "limit": limit, "items": requests}


@router.get("/{request_id}", response_model=ExtensionRequestResponse)
def get_extension_request(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    ext_request = crud.get_extension_request(db, request_id)
    if not ext_request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="审批请求不存在"
        )
    if current_user.role == "operator" and ext_request.requester_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="权限不足"
        )
    return ext_request


@router.post("/{request_id}/decide", response_model=ExtensionRequestResponse, dependencies=[Depends(role_admin_manager)])
def decide_extension_request(
    request_id: int,
    decision: ExtensionRequestDecision,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    ext_request = crud.get_extension_request(db, request_id)
    if not ext_request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="审批请求不存在"
        )
    if ext_request.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该请求已处理"
        )
    updated = crud.decide_extension_request(
        db, request_id, decision.status, current_user.id, decision.approval_notes
    )
    ip = get_client_ip(request)
    log_audit(
        db, current_user, f"decide_extension_{decision.status}", "extension", request_id,
        f"审批延期请求: 文件ID={ext_request.file_id}, 结果={decision.status}", ip
    )
    return updated

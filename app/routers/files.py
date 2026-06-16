from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session

from app.auth import get_current_active_user, RoleChecker, log_audit, get_client_ip
from app.database import get_db
from app import crud
from app.models import User
from app.schemas import (
    FileRecordCreate, FileRecordUpdate, FileRecordResponse, PaginatedResponse
)
from typing import List

router = APIRouter(prefix="/files", tags=["文件记录"])
role_admin = RoleChecker(["admin"])


@router.post("", response_model=FileRecordResponse)
def create_file(
    file_in: FileRecordCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
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
    current_user: User = Depends(get_current_active_user)
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
    current_user: User = Depends(get_current_active_user)
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
    current_user: User = Depends(get_current_active_user)
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
    if file_in.status and current_user.role == "operator":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权修改文件状态"
        )
    updated_file = crud.update_file(db, file_id, file_in)
    ip = get_client_ip(request)
    log_audit(
        db, current_user, "update_file", "file", file_id,
        f"更新文件记录: {file.file_name}", ip
    )
    return updated_file


@router.delete("/{file_id}", dependencies=[Depends(role_admin)])
def delete_file(
    file_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
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

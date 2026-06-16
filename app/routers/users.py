from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session

from app.auth import get_current_active_user, RoleChecker, log_audit, get_client_ip
from app.database import get_db
from app import crud
from app.models import User
from app.schemas import (
    UserCreate, UserUpdate, UserResponse, PaginatedResponse
)
from typing import List

router = APIRouter(prefix="/users", tags=["用户管理"])
role_admin = RoleChecker(["admin"])


@router.post("", response_model=UserResponse, dependencies=[Depends(role_admin)])
def create_user(
    user_in: UserCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    if crud.get_user_by_username(db, user_in.username):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="用户名已存在"
        )
    user = crud.create_user(db, user_in)
    ip = get_client_ip(request)
    log_audit(db, current_user, "create_user", "user", user.id, f"创建用户: {user.username}", ip)
    return user


@router.get("", response_model=PaginatedResponse[UserResponse])
def list_users(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    if current_user.role != "admin":
        limit = min(limit, 10)
    users = crud.list_users(db, skip=skip, limit=limit)
    total = crud.count_users(db)
    return {"total": total, "skip": skip, "limit": limit, "items": users}


@router.get("/{user_id}", response_model=UserResponse)
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    if current_user.role != "admin" and current_user.id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="权限不足"
        )
    user = crud.get_user(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在"
        )
    return user


@router.put("/{user_id}", response_model=UserResponse)
def update_user(
    user_id: int,
    user_in: UserUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    if current_user.role != "admin" and current_user.id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="权限不足"
        )
    if current_user.role != "admin" and (user_in.role or user_in.is_active is not None):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权修改角色或激活状态"
        )
    user = crud.update_user(db, user_id, user_in)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在"
        )
    ip = get_client_ip(request)
    log_audit(db, current_user, "update_user", "user", user_id, f"更新用户信息: {user.username}", ip)
    return user


@router.delete("/{user_id}", dependencies=[Depends(role_admin)])
def delete_user(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    if current_user.id == user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="不能删除自己"
        )
    user = crud.get_user(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在"
        )
    crud.delete_user(db, user_id)
    ip = get_client_ip(request)
    log_audit(db, current_user, "delete_user", "user", user_id, f"删除用户: {user.username}", ip)
    return {"message": "用户删除成功"}

from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session

from app.auth import get_current_active_user_checked, RoleChecker, log_audit, get_client_ip
from app.database import get_db
from app import crud
from app.models import User
from app.schemas import (
    UserCreate, UserUpdate, UserResponse, PaginatedResponse, ForceResetPassword
)
from typing import Optional, List

router = APIRouter(prefix="/users", tags=["用户管理"])
role_admin = RoleChecker(["admin"])


@router.post("", response_model=UserResponse, dependencies=[Depends(role_admin)])
def create_user(
    user_in: UserCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user_checked)
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
    current_user: User = Depends(get_current_active_user_checked)
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
    current_user: User = Depends(get_current_active_user_checked)
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
    current_user: User = Depends(get_current_active_user_checked)
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


@router.post("/{user_id}/reset-password", dependencies=[Depends(role_admin)])
def force_reset_password(
    user_id: int,
    reset_in: ForceResetPassword,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user_checked)
):
    user = crud.get_user(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在"
        )
    crud.update_user_password(db, user_id, reset_in.new_password, clear_must_change=False)
    crud.set_must_change_password(db, user_id, must_change=True)
    ip = get_client_ip(request)
    log_audit(
        db, current_user, "force_reset_password", "user", user_id,
        f"管理员强制重置用户密码: {user.username}, 需首次登录修改", ip
    )
    return {"message": "密码已重置，该用户下次登录时必须修改密码"}


@router.delete("/{user_id}/force-change-password", dependencies=[Depends(role_admin)])
def force_user_change_password(
    user_id: int,
    must_change: bool = True,
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user_checked)
):
    user = crud.get_user(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在"
        )
    crud.set_must_change_password(db, user_id, must_change=must_change)
    ip = get_client_ip(request)
    action = "启用" if must_change else "取消"
    log_audit(
        db, current_user, "set_must_change_password", "user", user_id,
        f"{action}用户 {user.username} 的强制改密标记", ip
    )
    return {"message": f"已设置用户 {user.username} 的强制改密标记为 {must_change}"}


@router.delete("/{user_id}", dependencies=[Depends(role_admin)])
def delete_user(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user_checked)
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

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.auth import (
    authenticate_user, create_access_token, get_current_active_user, verify_password,
    log_audit, get_client_ip
)
from app.config import settings
from app.database import get_db
from app.crud import update_user_password
from app.models import User
from app.schemas import Token, PasswordChange, UserResponse, TokenWithPasswordChange

router = APIRouter(prefix="/auth", tags=["认证"])


@router.post("/login", response_model=TokenWithPasswordChange)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    request: Request = None,
    db: Session = Depends(get_db)
):
    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    if request:
        ip = get_client_ip(request)
        log_audit(
            db, user, "login", "auth", None,
            f"用户登录成功", ip
        )
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "must_change_password": user.must_change_password
    }


@router.get("/me", response_model=UserResponse)
def read_current_user(
    current_user: User = Depends(get_current_active_user)
):
    return current_user


@router.post("/change-password")
def change_password(
    password_data: PasswordChange,
    request: Request,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    if not verify_password(password_data.old_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="原密码错误"
        )
    if password_data.old_password == password_data.new_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="新密码不能与原密码相同"
        )
    update_user_password(db, current_user.id, password_data.new_password, clear_must_change=True)
    ip = get_client_ip(request)
    log_audit(
        db, current_user, "change_password", "auth", None,
        "用户修改密码成功", ip
    )
    return {"message": "密码修改成功"}

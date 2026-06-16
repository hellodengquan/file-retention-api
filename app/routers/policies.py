from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session

from app.auth import get_current_active_user, RoleChecker, log_audit, get_client_ip
from app.database import get_db
from app import crud
from app.models import User
from app.schemas import (
    RetentionPolicyCreate, RetentionPolicyUpdate, RetentionPolicyResponse, PaginatedResponse
)
from typing import List

router = APIRouter(prefix="/policies", tags=["保留策略"])
role_admin_manager = RoleChecker(["admin", "manager"])


@router.post("", response_model=RetentionPolicyResponse, dependencies=[Depends(role_admin_manager)])
def create_policy(
    policy_in: RetentionPolicyCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    if crud.get_policy_by_category(db, policy_in.business_category):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该业务类别的策略已存在"
        )
    policy = crud.create_policy(db, policy_in, current_user.id)
    ip = get_client_ip(request)
    log_audit(
        db, current_user, "create_policy", "policy", policy.id,
        f"创建保留策略: {policy.business_category}, 保留期: {policy.retention_days}天", ip
    )
    return policy


@router.get("", response_model=PaginatedResponse[RetentionPolicyResponse])
def list_policies(
    skip: int = 0,
    limit: int = 100,
    is_active: Optional[bool] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    policies = crud.list_policies(db, skip=skip, limit=limit, is_active=is_active)
    total = crud.count_policies(db, is_active=is_active)
    return {"total": total, "skip": skip, "limit": limit, "items": policies}


@router.get("/{policy_id}", response_model=RetentionPolicyResponse)
def get_policy(
    policy_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    policy = crud.get_policy(db, policy_id)
    if not policy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="策略不存在"
        )
    return policy


@router.get("/category/{business_category}", response_model=RetentionPolicyResponse)
def get_policy_by_category(
    business_category: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    policy = crud.get_policy_by_category(db, business_category)
    if not policy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="该业务类别无有效策略"
        )
    return policy


@router.put("/{policy_id}", response_model=RetentionPolicyResponse, dependencies=[Depends(role_admin_manager)])
def update_policy(
    policy_id: int,
    policy_in: RetentionPolicyUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    policy = crud.update_policy(db, policy_id, policy_in)
    if not policy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="策略不存在"
        )
    ip = get_client_ip(request)
    log_audit(
        db, current_user, "update_policy", "policy", policy_id,
        f"更新保留策略: {policy.business_category}", ip
    )
    return policy


@router.delete("/{policy_id}", dependencies=[Depends(role_admin_manager)])
def delete_policy(
    policy_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    policy = crud.get_policy(db, policy_id)
    if not policy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="策略不存在"
        )
    crud.delete_policy(db, policy_id)
    ip = get_client_ip(request)
    log_audit(
        db, current_user, "delete_policy", "policy", policy_id,
        f"删除保留策略: {policy.business_category}", ip
    )
    return {"message": "策略删除成功"}

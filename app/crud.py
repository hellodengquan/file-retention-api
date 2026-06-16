from datetime import datetime, timedelta
from typing import Optional, List, Tuple

from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func

from app.auth import get_password_hash
from app.config import settings
from app.models import (
    User, RetentionPolicy, FileRecord, ExtensionRequest, AuditLog
)
from app.schemas import (
    UserCreate, UserUpdate, RetentionPolicyCreate, RetentionPolicyUpdate,
    FileRecordCreate, FileRecordUpdate, ExtensionRequestCreate
)


def create_user(db: Session, user_in: UserCreate) -> User:
    db_user = User(
        username=user_in.username,
        hashed_password=get_password_hash(user_in.password),
        full_name=user_in.full_name,
        email=user_in.email,
        role=user_in.role,
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


def get_user(db: Session, user_id: int) -> Optional[User]:
    return db.query(User).filter(User.id == user_id).first()


def get_user_by_username(db: Session, username: str) -> Optional[User]:
    return db.query(User).filter(User.username == username).first()


def list_users(db: Session, skip: int = 0, limit: int = 100) -> List[User]:
    return db.query(User).offset(skip).limit(limit).all()


def count_users(db: Session) -> int:
    return db.query(User).count()


def update_user(db: Session, user_id: int, user_in: UserUpdate) -> Optional[User]:
    db_user = get_user(db, user_id)
    if not db_user:
        return None
    update_data = user_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_user, field, value)
    db.commit()
    db.refresh(db_user)
    return db_user


def update_user_password(db: Session, user_id: int, new_password: str, clear_must_change: bool = True) -> Optional[User]:
    db_user = get_user(db, user_id)
    if not db_user:
        return None
    db_user.hashed_password = get_password_hash(new_password)
    if clear_must_change:
        db_user.must_change_password = False
    db_user.token_version = db_user.token_version + 1 if db_user.token_version else 2
    db.commit()
    db.refresh(db_user)
    return db_user


def set_must_change_password(db: Session, user_id: int, must_change: bool = True) -> Optional[User]:
    db_user = get_user(db, user_id)
    if not db_user:
        return None
    db_user.must_change_password = must_change
    db.commit()
    db.refresh(db_user)
    return db_user


def revoke_user_tokens(db: Session, user_id: int) -> Optional[User]:
    db_user = get_user(db, user_id)
    if not db_user:
        return None
    db_user.token_version = (db_user.token_version or 1) + 1
    db.commit()
    db.refresh(db_user)
    return db_user


def delete_user(db: Session, user_id: int) -> bool:
    db_user = get_user(db, user_id)
    if not db_user:
        return False
    db.delete(db_user)
    db.commit()
    return True


def create_policy(db: Session, policy_in: RetentionPolicyCreate, created_by: int) -> RetentionPolicy:
    db_policy = RetentionPolicy(
        **policy_in.model_dump(),
        created_by=created_by
    )
    db.add(db_policy)
    db.commit()
    db.refresh(db_policy)
    return db_policy


def get_policy(db: Session, policy_id: int) -> Optional[RetentionPolicy]:
    return db.query(RetentionPolicy).filter(RetentionPolicy.id == policy_id).first()


def get_policy_by_category(db: Session, business_category: str) -> Optional[RetentionPolicy]:
    return db.query(RetentionPolicy).filter(
        RetentionPolicy.business_category == business_category,
        RetentionPolicy.is_active == True
    ).first()


def list_policies(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    is_active: Optional[bool] = None
) -> List[RetentionPolicy]:
    query = db.query(RetentionPolicy)
    if is_active is not None:
        query = query.filter(RetentionPolicy.is_active == is_active)
    return query.offset(skip).limit(limit).all()


def count_policies(db: Session, is_active: Optional[bool] = None) -> int:
    query = db.query(RetentionPolicy)
    if is_active is not None:
        query = query.filter(RetentionPolicy.is_active == is_active)
    return query.count()


def update_policy(db: Session, policy_id: int, policy_in: RetentionPolicyUpdate) -> Optional[RetentionPolicy]:
    db_policy = get_policy(db, policy_id)
    if not db_policy:
        return None
    update_data = policy_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_policy, field, value)
    db_policy.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(db_policy)
    return db_policy


def delete_policy(db: Session, policy_id: int) -> bool:
    db_policy = get_policy(db, policy_id)
    if not db_policy:
        return False
    db.delete(db_policy)
    db.commit()
    return True


def calculate_expiry_date(db: Session, business_category: str, upload_date: datetime) -> Optional[datetime]:
    policy = get_policy_by_category(db, business_category)
    if policy:
        return upload_date + timedelta(days=policy.retention_days)
    return None


def create_file(db: Session, file_in: FileRecordCreate, created_by: int) -> FileRecord:
    upload_date = datetime.utcnow()
    expiry_date = calculate_expiry_date(db, file_in.business_category, upload_date)
    policy = get_policy_by_category(db, file_in.business_category)

    db_file = FileRecord(
        **file_in.model_dump(),
        upload_date=upload_date,
        expiry_date=expiry_date,
        policy_id=policy.id if policy else None,
        created_by=created_by,
        status="active"
    )
    db.add(db_file)
    db.commit()
    db.refresh(db_file)
    return db_file


def get_file(db: Session, file_id: int) -> Optional[FileRecord]:
    return db.query(FileRecord).filter(FileRecord.id == file_id).first()


def list_files(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    business_category: Optional[str] = None,
    status: Optional[str] = None,
    created_by: Optional[int] = None
) -> List[FileRecord]:
    query = db.query(FileRecord)
    if business_category:
        query = query.filter(FileRecord.business_category == business_category)
    if status:
        query = query.filter(FileRecord.status == status)
    if created_by:
        query = query.filter(FileRecord.created_by == created_by)
    return query.order_by(FileRecord.upload_date.desc()).offset(skip).limit(limit).all()


def count_files(
    db: Session,
    business_category: Optional[str] = None,
    status: Optional[str] = None,
    created_by: Optional[int] = None
) -> int:
    query = db.query(FileRecord)
    if business_category:
        query = query.filter(FileRecord.business_category == business_category)
    if status:
        query = query.filter(FileRecord.status == status)
    if created_by:
        query = query.filter(FileRecord.created_by == created_by)
    return query.count()


def update_file(db: Session, file_id: int, file_in: FileRecordUpdate) -> Optional[FileRecord]:
    db_file = get_file(db, file_id)
    if not db_file:
        return None
    update_data = file_in.model_dump(exclude_unset=True)

    old_category = db_file.business_category
    for field, value in update_data.items():
        setattr(db_file, field, value)

    if "business_category" in update_data and update_data["business_category"] != old_category:
        policy = get_policy_by_category(db, db_file.business_category)
        db_file.policy_id = policy.id if policy else None
        if policy:
            base_expiry = db_file.upload_date + timedelta(days=policy.retention_days)
            if db_file.last_extended_at and db_file.expiry_date:
                original_expiry = (db_file.upload_date + timedelta(days=getattr(db_file.policy, 'retention_days', 0) if db_file.policy else 0))
                extension_days = (db_file.expiry_date - original_expiry).days
                if extension_days > 0:
                    base_expiry = base_expiry + timedelta(days=extension_days)
            db_file.expiry_date = base_expiry

    if "status" in update_data:
        if update_data["status"] == "archived":
            db_file.archived_at = datetime.utcnow()
        elif update_data["status"] == "active":
            db_file.archived_at = None

    db.commit()
    db.refresh(db_file)
    return db_file


def can_restore_file(db: Session, file_id: int) -> Tuple[bool, str]:
    db_file = get_file(db, file_id)
    if not db_file:
        return False, "文件不存在"
    if db_file.status not in ("archived", "expired"):
        return False, "只有已归档或已过期的文件才能恢复"
    if db_file.archived_at:
        window_days = settings.ARCHIVE_RESTORE_WINDOW_DAYS
        if datetime.utcnow() - db_file.archived_at > timedelta(days=window_days):
            return False, f"已超过归档恢复时间窗口（{window_days}天），无法恢复"
    return True, ""


def restore_file(db: Session, file_id: int) -> Optional[FileRecord]:
    db_file = get_file(db, file_id)
    if not db_file:
        return None
    if db_file.status not in ("archived", "expired"):
        return None
    db_file.status = "active"
    db_file.archived_at = None
    db.commit()
    db.refresh(db_file)
    return db_file


def extend_file_expiry(db: Session, file_id: int, days: int) -> Optional[FileRecord]:
    db_file = get_file(db, file_id)
    if not db_file:
        return None
    if db_file.expiry_date:
        db_file.expiry_date = db_file.expiry_date + timedelta(days=days)
    else:
        db_file.expiry_date = datetime.utcnow() + timedelta(days=days)
    db_file.last_extended_at = datetime.utcnow()
    db.commit()
    db.refresh(db_file)
    return db_file


def delete_file(db: Session, file_id: int) -> bool:
    db_file = get_file(db, file_id)
    if not db_file:
        return False
    db.delete(db_file)
    db.commit()
    return True


def get_expired_files(db: Session) -> List[FileRecord]:
    now = datetime.utcnow()
    return db.query(FileRecord).filter(
        FileRecord.expiry_date <= now,
        FileRecord.status == "active"
    ).all()


def batch_rematch_policies(
    db: Session,
    business_category: Optional[str] = None,
    dry_run: bool = False
) -> Tuple[int, int, int, List[dict]]:
    query = db.query(FileRecord).filter(FileRecord.status == "active")
    if business_category:
        query = query.filter(FileRecord.business_category == business_category)
    
    total_files = query.count()
    matched_count = 0
    updated_count = 0
    changes = []
    
    for file_record in query.all():
        policy = get_policy_by_category(db, file_record.business_category)
        if policy:
            matched_count += 1
            new_expiry = file_record.upload_date + timedelta(days=policy.retention_days)
            old_expiry = file_record.expiry_date
            old_policy_id = file_record.policy_id
            
            if file_record.last_extended_at and file_record.expiry_date:
                original_expiry = file_record.upload_date + timedelta(
                    days=getattr(file_record.policy, 'retention_days', 0) if file_record.policy else 0
                )
                extension_days = (file_record.expiry_date - original_expiry).days
                if extension_days > 0:
                    new_expiry = new_expiry + timedelta(days=extension_days)
            
            if file_record.expiry_date != new_expiry or file_record.policy_id != policy.id:
                updated_count += 1
                changes.append({
                    "file_id": file_record.id,
                    "file_name": file_record.file_name,
                    "business_category": file_record.business_category,
                    "old_policy_id": old_policy_id,
                    "new_policy_id": policy.id,
                    "old_expiry_date": old_expiry.isoformat() if old_expiry else None,
                    "new_expiry_date": new_expiry.isoformat() if new_expiry else None,
                })
                if not dry_run:
                    file_record.policy_id = policy.id
                    file_record.expiry_date = new_expiry
    
    if not dry_run:
        db.commit()
    
    return total_files, matched_count, updated_count, changes


def create_extension_request(
    db: Session,
    request_in: ExtensionRequestCreate,
    requester_id: int
) -> ExtensionRequest:
    db_request = ExtensionRequest(
        file_id=request_in.file_id,
        requester_id=requester_id,
        requested_days=request_in.requested_days,
        reason=request_in.reason,
        status="pending"
    )
    db.add(db_request)
    db.commit()
    db.refresh(db_request)
    return db_request


def get_extension_request(db: Session, request_id: int) -> Optional[ExtensionRequest]:
    return db.query(ExtensionRequest).filter(ExtensionRequest.id == request_id).first()


def list_extension_requests(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    status: Optional[str] = None,
    requester_id: Optional[int] = None
) -> List[ExtensionRequest]:
    query = db.query(ExtensionRequest)
    if status:
        query = query.filter(ExtensionRequest.status == status)
    if requester_id:
        query = query.filter(ExtensionRequest.requester_id == requester_id)
    return query.order_by(ExtensionRequest.requested_at.desc()).offset(skip).limit(limit).all()


def count_extension_requests(
    db: Session,
    status: Optional[str] = None,
    requester_id: Optional[int] = None
) -> int:
    query = db.query(ExtensionRequest)
    if status:
        query = query.filter(ExtensionRequest.status == status)
    if requester_id:
        query = query.filter(ExtensionRequest.requester_id == requester_id)
    return query.count()


def decide_extension_request(
    db: Session,
    request_id: int,
    status: str,
    approver_id: int,
    approval_notes: Optional[str] = None
) -> Optional[ExtensionRequest]:
    db_request = get_extension_request(db, request_id)
    if not db_request:
        return None
    db_request.status = status
    db_request.approver_id = approver_id
    db_request.approval_notes = approval_notes
    db_request.decided_at = datetime.utcnow()

    if status == "approved":
        extend_file_expiry(db, db_request.file_id, db_request.requested_days)

    db.commit()
    db.refresh(db_request)
    return db_request


def cancel_extension_request(
    db: Session,
    request_id: int,
    canceller_id: int,
    cancel_reason: Optional[str] = None
) -> Optional[ExtensionRequest]:
    db_request = get_extension_request(db, request_id)
    if not db_request:
        return None
    if db_request.status != "pending":
        return None
    db_request.status = "cancelled"
    db_request.approver_id = canceller_id
    db_request.approval_notes = cancel_reason or "申请人取消"
    db_request.decided_at = datetime.utcnow()
    db.commit()
    db.refresh(db_request)
    return db_request


def list_audit_logs(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    user_id: Optional[int] = None,
    username: Optional[str] = None,
    action: Optional[str] = None,
    resource_type: Optional[str] = None,
    resource_id: Optional[int] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    ip_address: Optional[str] = None,
    keyword: Optional[str] = None
) -> List[AuditLog]:
    query = db.query(AuditLog)
    if user_id:
        query = query.filter(AuditLog.user_id == user_id)
    if username:
        query = query.filter(AuditLog.username == username)
    if action:
        query = query.filter(AuditLog.action == action)
    if resource_type:
        query = query.filter(AuditLog.resource_type == resource_type)
    if resource_id:
        query = query.filter(AuditLog.resource_id == resource_id)
    if start_time:
        query = query.filter(AuditLog.timestamp >= start_time)
    if end_time:
        query = query.filter(AuditLog.timestamp <= end_time)
    if ip_address:
        query = query.filter(AuditLog.ip_address.like(f"%{ip_address}%"))
    if keyword:
        keyword_pattern = f"%{keyword}%"
        query = query.filter(
            or_(
                AuditLog.action.like(keyword_pattern),
                AuditLog.details.like(keyword_pattern),
                AuditLog.username.like(keyword_pattern),
                AuditLog.resource_type.like(keyword_pattern)
            )
        )
    return query.order_by(AuditLog.timestamp.desc()).offset(skip).limit(limit).all()


def count_audit_logs(
    db: Session,
    user_id: Optional[int] = None,
    username: Optional[str] = None,
    action: Optional[str] = None,
    resource_type: Optional[str] = None,
    resource_id: Optional[int] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    ip_address: Optional[str] = None,
    keyword: Optional[str] = None
) -> int:
    query = db.query(AuditLog)
    if user_id:
        query = query.filter(AuditLog.user_id == user_id)
    if username:
        query = query.filter(AuditLog.username == username)
    if action:
        query = query.filter(AuditLog.action == action)
    if resource_type:
        query = query.filter(AuditLog.resource_type == resource_type)
    if resource_id:
        query = query.filter(AuditLog.resource_id == resource_id)
    if start_time:
        query = query.filter(AuditLog.timestamp >= start_time)
    if end_time:
        query = query.filter(AuditLog.timestamp <= end_time)
    if ip_address:
        query = query.filter(AuditLog.ip_address.like(f"%{ip_address}%"))
    if keyword:
        keyword_pattern = f"%{keyword}%"
        query = query.filter(
            or_(
                AuditLog.action.like(keyword_pattern),
                AuditLog.details.like(keyword_pattern),
                AuditLog.username.like(keyword_pattern),
                AuditLog.resource_type.like(keyword_pattern)
            )
        )
    return query.count()

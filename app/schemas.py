from datetime import datetime
from typing import Optional, List, Generic, TypeVar

from pydantic import BaseModel, EmailStr, Field

T = TypeVar("T")


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    username: Optional[str] = None


class UserBase(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    full_name: Optional[str] = None
    email: Optional[EmailStr] = None
    role: str = Field(default="operator", pattern="^(admin|manager|operator)$")


class UserCreate(UserBase):
    password: str = Field(..., min_length=6)


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[EmailStr] = None
    role: Optional[str] = Field(default=None, pattern="^(admin|manager|operator)$")
    is_active: Optional[bool] = None


class UserInDB(UserBase):
    id: int
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class UserResponse(UserBase):
    id: int
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class RetentionPolicyBase(BaseModel):
    business_category: str = Field(..., max_length=100)
    description: Optional[str] = None
    retention_days: int = Field(..., gt=0)
    action_on_expiry: str = Field(default="archive", pattern="^(archive|delete)$")
    is_active: Optional[bool] = True


class RetentionPolicyCreate(RetentionPolicyBase):
    pass


class RetentionPolicyUpdate(BaseModel):
    description: Optional[str] = None
    retention_days: Optional[int] = Field(default=None, gt=0)
    action_on_expiry: Optional[str] = Field(default=None, pattern="^(archive|delete)$")
    is_active: Optional[bool] = None


class RetentionPolicyInDB(RetentionPolicyBase):
    id: int
    created_by: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class RetentionPolicyResponse(RetentionPolicyBase):
    id: int
    created_by: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class FileRecordBase(BaseModel):
    file_name: str = Field(..., max_length=255)
    file_path: str = Field(..., max_length=500)
    file_size: Optional[int] = None
    business_category: str = Field(..., max_length=100)
    notes: Optional[str] = None


class FileRecordCreate(FileRecordBase):
    pass


class FileRecordUpdate(BaseModel):
    file_name: Optional[str] = None
    file_path: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[str] = Field(default=None, pattern="^(active|archived|deleted|expired)$")


class FileRecordInDB(FileRecordBase):
    id: int
    upload_date: datetime
    expiry_date: Optional[datetime] = None
    status: str
    policy_id: Optional[int] = None
    created_by: int
    last_extended_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class FileRecordResponse(FileRecordBase):
    id: int
    upload_date: datetime
    expiry_date: Optional[datetime] = None
    status: str
    policy_id: Optional[int] = None
    created_by: int
    last_extended_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ExtensionRequestBase(BaseModel):
    file_id: int
    requested_days: int = Field(..., gt=0, le=3650)
    reason: Optional[str] = None


class ExtensionRequestCreate(ExtensionRequestBase):
    pass


class ExtensionRequestDecision(BaseModel):
    status: str = Field(..., pattern="^(approved|rejected)$")
    approval_notes: Optional[str] = None


class ExtensionRequestInDB(ExtensionRequestBase):
    id: int
    requester_id: int
    approver_id: Optional[int] = None
    status: str
    approval_notes: Optional[str] = None
    requested_at: datetime
    decided_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ExtensionRequestResponse(ExtensionRequestBase):
    id: int
    requester_id: int
    approver_id: Optional[int] = None
    status: str
    approval_notes: Optional[str] = None
    requested_at: datetime
    decided_at: Optional[datetime] = None
    requester: Optional[UserResponse] = None
    approver: Optional[UserResponse] = None
    file: Optional[FileRecordResponse] = None

    class Config:
        from_attributes = True


class AuditLogBase(BaseModel):
    action: str
    resource_type: Optional[str] = None
    resource_id: Optional[int] = None
    details: Optional[str] = None


class AuditLogResponse(AuditLogBase):
    id: int
    timestamp: datetime
    user_id: Optional[int] = None
    username: Optional[str] = None
    ip_address: Optional[str] = None

    class Config:
        from_attributes = True


class PaginatedResponse(BaseModel, Generic[T]):
    total: int
    skip: int
    limit: int
    items: List[T]


class PasswordChange(BaseModel):
    old_password: str
    new_password: str = Field(..., min_length=6)

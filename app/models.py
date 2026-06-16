from datetime import datetime

from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey, Text, Boolean
)
from sqlalchemy.orm import relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(100))
    email = Column(String(100))
    role = Column(String(20), nullable=False, default="operator")
    is_active = Column(Boolean, default=True)
    must_change_password = Column(Boolean, default=False)
    token_version = Column(Integer, default=1)
    created_at = Column(DateTime, default=datetime.utcnow)

    extension_requests = relationship("ExtensionRequest", foreign_keys="ExtensionRequest.requester_id", back_populates="requester")
    extension_approvals = relationship("ExtensionRequest", foreign_keys="ExtensionRequest.approver_id", back_populates="approver")


class RetentionPolicy(Base):
    __tablename__ = "retention_policies"

    id = Column(Integer, primary_key=True, index=True)
    business_category = Column(String(100), unique=True, index=True, nullable=False)
    description = Column(Text)
    retention_days = Column(Integer, nullable=False)
    action_on_expiry = Column(String(20), nullable=False, default="archive")
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active = Column(Boolean, default=True)

    files = relationship("FileRecord", back_populates="policy")


class FileRecord(Base):
    __tablename__ = "file_records"

    id = Column(Integer, primary_key=True, index=True)
    file_name = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)
    file_size = Column(Integer)
    business_category = Column(String(100), nullable=False, index=True)
    upload_date = Column(DateTime, default=datetime.utcnow, index=True)
    expiry_date = Column(DateTime, index=True)
    status = Column(String(20), nullable=False, default="active")
    policy_id = Column(Integer, ForeignKey("retention_policies.id"))
    created_by = Column(Integer, ForeignKey("users.id"))
    last_extended_at = Column(DateTime)
    archived_at = Column(DateTime)
    notes = Column(Text)

    policy = relationship("RetentionPolicy", back_populates="files")
    extension_requests = relationship("ExtensionRequest", back_populates="file")


class ExtensionRequest(Base):
    __tablename__ = "extension_requests"

    id = Column(Integer, primary_key=True, index=True)
    file_id = Column(Integer, ForeignKey("file_records.id"), nullable=False)
    requester_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    approver_id = Column(Integer, ForeignKey("users.id"))
    requested_days = Column(Integer, nullable=False)
    reason = Column(Text)
    status = Column(String(20), nullable=False, default="pending")
    approval_notes = Column(Text)
    requested_at = Column(DateTime, default=datetime.utcnow)
    decided_at = Column(DateTime)

    file = relationship("FileRecord", back_populates="extension_requests")
    requester = relationship("User", foreign_keys=[requester_id], back_populates="extension_requests")
    approver = relationship("User", foreign_keys=[approver_id], back_populates="extension_approvals")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    username = Column(String(50))
    action = Column(String(50), nullable=False, index=True)
    resource_type = Column(String(50), index=True)
    resource_id = Column(Integer)
    details = Column(Text)
    ip_address = Column(String(50))

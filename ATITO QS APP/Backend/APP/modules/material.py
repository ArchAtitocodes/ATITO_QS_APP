# backend/app/models/material.py
"""Materials catalog with dynamic pricing"""

from sqlalchemy import Column, String, DateTime, Float, Text, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from datetime import datetime
import uuid
from app.database import Base


class Material(Base):
    __tablename__ = "materials"
    __table_args__ = (
        Index('idx_material_code', 'material_code'),
        Index('idx_material_category', 'category'),
        {"extend_existing": True}
    )
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Material identification
    material_code = Column(String(50), unique=True, nullable=False)
    description = Column(Text, nullable=False)
    category = Column(String(100), nullable=False)
    sub_category = Column(String(100), nullable=True)
    
    # Pricing
    unit = Column(String(20), nullable=False)
    unit_price = Column(Float, nullable=False)
    currency = Column(String(10), default="KES")
    
    # Source tracking
    price_sources = Column(JSONB, default=list)  # List of scraped sources with prices
    last_scraped = Column(DateTime, nullable=True)
    price_confidence = Column(Float, default=1.0)
    
    # County-specific pricing adjustments
    county_factors = Column(JSONB, default=dict)
    
    # Material specifications
    specifications = Column(JSONB, default=dict)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f"<Material {self.material_code}: {self.description}>"


# backend/app/models/expense.py
"""Expense tracking for budget management"""

from sqlalchemy import Column, String, DateTime, ForeignKey, Float, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
from app.database import Base


class Expense(Base):
    __tablename__ = "expenses"
    __table_args__ = {"extend_existing": True}
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    # Expense details
    expense_date = Column(DateTime, nullable=False, default=datetime.utcnow)
    category = Column(String(100), nullable=False)  # Materials, Labor, Equipment, etc.
    item_description = Column(Text, nullable=False)
    supplier = Column(String(255), nullable=True)
    
    # Financial details
    quantity = Column(Float, nullable=True)
    unit = Column(String(20), nullable=True)
    unit_price = Column(Float, nullable=True)
    total_amount = Column(Float, nullable=False)
    
    # Documentation
    receipt_url = Column(String(500), nullable=True)
    remarks = Column(Text, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    project = relationship("Project", back_populates="expenses")
    user = relationship("User", back_populates="expenses")
    
    def __repr__(self):
        return f"<Expense {self.item_description}: {self.total_amount}>"


# backend/app/models/sitelog.py
"""Daily site progress logs with offline support"""

from sqlalchemy import Column, String, DateTime, ForeignKey, Float, Text, Boolean
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
from app.database import Base


class SiteLog(Base):
    __tablename__ = "site_logs"
    __table_args__ = {"extend_existing": True}
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    # Log details
    log_date = Column(DateTime, nullable=False, default=datetime.utcnow)
    log_text = Column(Text, nullable=False)
    
    # Site conditions
    weather_conditions = Column(String(100), nullable=True)
    workforce_count = Column(Integer, nullable=True)
    equipment_used = Column(JSONB, default=list)
    
    # Progress tracking
    activities_completed = Column(JSONB, default=list)
    issues_encountered = Column(Text, nullable=True)
    
    # Geolocation
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    
    # Media attachments
    photo_urls = Column(JSONB, default=list)  # List of photo URLs
    
    # Sync status (for offline-first functionality)
    is_synced = Column(Boolean, default=True)
    sync_attempted_at = Column(DateTime, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    project = relationship("Project", back_populates="site_logs")
    user = relationship("User", back_populates="site_logs")
    
    def __repr__(self):
        return f"<SiteLog {self.log_date}: Project {self.project_id}>"


# backend/app/models/comment.py
"""Threaded comments for collaboration"""

from sqlalchemy import Column, String, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
from app.database import Base


class Comment(Base):
    __tablename__ = "comments"
    __table_args__ = {"extend_existing": True}
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    # Comment can be attached to either BOQ or BBS item
    boq_item_id = Column(UUID(as_uuid=True), ForeignKey("boq_items.id", ondelete="CASCADE"), nullable=True)
    bbs_item_id = Column(UUID(as_uuid=True), ForeignKey("bbs_items.id", ondelete="CASCADE"), nullable=True)
    
    # Threading support
    parent_comment_id = Column(UUID(as_uuid=True), ForeignKey("comments.id", ondelete="CASCADE"), nullable=True)
    
    # Comment content
    comment_text = Column(Text, nullable=False)
    
    # Status
    is_resolved = Column(Boolean, default=False)
    resolved_at = Column(DateTime, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="comments")
    boq_item = relationship("BOQItem", back_populates="comments")
    bbs_item = relationship("BBSItem", back_populates="comments")
    
    # Self-referential relationship for threading
    replies = relationship("Comment", backref="parent", remote_side=[id])
    
    def __repr__(self):
        return f"<Comment by User {self.user_id}>"


# backend/app/models/audit.py
"""Comprehensive audit logging"""

from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
from app.database import Base


class AuditLog(Base):
    __tablename__ = "audit_log"
    __table_args__ = (
        Index('idx_audit_user', 'user_id'),
        Index('idx_audit_action', 'action_type'),
        Index('idx_audit_timestamp', 'timestamp'),
        {"extend_existing": True}
    )
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    
    # Action details
    action_type = Column(String(100), nullable=False)  # LOGIN, UPLOAD, GENERATE_BOQ, etc.
    resource_type = Column(String(100), nullable=True)  # PROJECT, BOQ, USER, etc.
    resource_id = Column(UUID(as_uuid=True), nullable=True)
    
    # Detailed information
    description = Column(Text, nullable=False)
    metadata = Column(JSONB, default=dict)  # Additional context
    
    # Request information
    ip_address = Column(String(50), nullable=True)
    user_agent = Column(String(500), nullable=True)
    
    # Status
    status = Column(String(20), nullable=False)  # SUCCESS, FAILURE, ERROR
    error_message = Column(Text, nullable=True)
    
    # Timestamp
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    user = relationship("User", back_populates="audit_logs")
    
    def __repr__(self):
        return f"<AuditLog {self.action_type} at {self.timestamp}>"


# backend/app/models/transaction.py
"""Payment transaction tracking for M-Pesa integration"""

from sqlalchemy import Column, String, DateTime, ForeignKey, Float, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
import enum
from app.database import Base


class TransactionStatus(str, enum.Enum):
    """Transaction status types"""
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = {"extend_existing": True}
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    # Transaction details
    transaction_id = Column(String(100), unique=True, nullable=False)  # M-Pesa transaction ID
    phone_number = Column(String(20), nullable=False)
    amount = Column(Float, nullable=False)
    
    # Transaction type
    payment_method = Column(String(50), default="mpesa")  # mpesa, airtel_money
    payment_type = Column(String(50), nullable=False)  # SUBSCRIPTION, PROJECT_PAYMENT
    
    # Subscription details (if applicable)
    subscription_plan = Column(String(50), nullable=True)
    subscription_duration = Column(Integer, default=30)  # days
    
    # Status tracking
    status = Column(SQLEnum(TransactionStatus), default=TransactionStatus.PENDING)
    mpesa_receipt_number = Column(String(100), nullable=True)
    
    # Callback data
    callback_data = Column(JSONB, default=dict)
    
    # Timestamps
    initiated_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    
    def __repr__(self):
        return f"<Transaction {self.transaction_id}: {self.amount} KES>"


# backend/app/models/__init__.py
"""
Export all models for easy importing
"""

from app.database import Base
from app.models.user import User, UserRole, SubscriptionPlan
from app.models.project import Project, ProjectStatus
from app.models.boq import BOQItem
from app.models.bbs import BBSItem
from app.models.material import Material
from app.models.expense import Expense
from app.models.sitelog import SiteLog
from app.models.comment import Comment
from app.models.audit import AuditLog
from app.models.transaction import Transaction, TransactionStatus

__all__ = [
    "Base",
    "User",
    "UserRole",
    "SubscriptionPlan",
    "Project",
    "ProjectStatus",
    "BOQItem",
    "BBSItem",
    "Material",
    "Expense",
    "SiteLog",
    "Comment",
    "AuditLog",
    "Transaction",
    "TransactionStatus"
]

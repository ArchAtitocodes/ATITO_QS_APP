# backend/app/database.py
"""
ATITO QS App - Database Connection and Session Management
Author: Eng. STEPHEN ODHIAMBO
"""

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import NullPool
from typing import Generator
from app.config import settings

# Create database engine with connection pooling
engine = create_engine(
    settings.DATABASE_URL,
    pool_size=settings.DATABASE_POOL_SIZE,
    max_overflow=settings.DATABASE_MAX_OVERFLOW,
    pool_pre_ping=True,  # Verify connections before using
    echo=settings.DEBUG
)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for models
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """Dependency for getting database sessions"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# backend/app/models/user.py
"""User model with role-based access control"""

from sqlalchemy import Column, String, Boolean, DateTime, Enum as SQLEnum, Integer, Float
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from datetime import datetime, timedelta
import uuid
import enum
from app.database import Base


class UserRole(str, enum.Enum):
    """User roles for RBAC"""
    SUPER_USER = "super_user"
    ADMIN = "admin"
    QS = "qs"
    CLIENT = "client"
    CONTRACTOR = "contractor"


class SubscriptionPlan(str, enum.Enum):
    """Subscription plan types"""
    FREE = "free"
    PRO = "pro"
    BUSINESS = "business"


class User(Base):
    __tablename__ = "users"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=False)
    phone_number = Column(String(20), nullable=True)
    
    # Role and subscription
    role = Column(SQLEnum(UserRole), default=UserRole.CLIENT, nullable=False)
    subscription_plan = Column(SQLEnum(SubscriptionPlan), default=SubscriptionPlan.FREE)
    
    # Account status
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    
    # Trial and usage tracking
    trial_start_date = Column(DateTime, default=datetime.utcnow)
    trial_end_date = Column(DateTime, default=lambda: datetime.utcnow() + timedelta(days=30))
    daily_token_count = Column(Integer, default=0)
    last_token_reset = Column(DateTime, default=datetime.utcnow)
    
    # Subscription tracking
    subscription_start_date = Column(DateTime, nullable=True)
    subscription_end_date = Column(DateTime, nullable=True)
    subscription_active = Column(Boolean, default=False)
    
    # Session management
    last_login_at = Column(DateTime, nullable=True)
    refresh_token = Column(String(500), nullable=True)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Additional user preferences
    preferences = Column(JSONB, default=dict)
    
    # Relationships
    projects = relationship("Project", back_populates="owner", cascade="all, delete-orphan")
    site_logs = relationship("SiteLog", back_populates="user", cascade="all, delete-orphan")
    expenses = relationship("Expense", back_populates="user", cascade="all, delete-orphan")
    comments = relationship("Comment", back_populates="user", cascade="all, delete-orphan")
    audit_logs = relationship("AuditLog", back_populates="user", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<User {self.email}>"
    
    def is_super_user(self) -> bool:
        """Check if user is a super user"""
        return self.role == UserRole.SUPER_USER
    
    def can_create_project(self, current_project_count: int) -> bool:
        """Check if user can create more projects based on plan"""
        if self.is_super_user():
            return True
        
        if self.subscription_plan == SubscriptionPlan.FREE:
            return current_project_count < 1
        elif self.subscription_plan == SubscriptionPlan.PRO:
            # Daily limit
            if self.last_token_reset.date() < datetime.utcnow().date():
                return True
            return self.daily_token_count < 8
        else:  # BUSINESS
            return True
    
    def get_max_floors(self) -> int:
        """Get maximum allowed floors based on subscription"""
        if self.is_super_user():
            return 999
        
        if self.subscription_plan == SubscriptionPlan.FREE:
            return 1
        elif self.subscription_plan == SubscriptionPlan.PRO:
            return 5
        else:  # BUSINESS
            return 10


# backend/app/models/project.py
"""Project model with comprehensive metadata"""

from sqlalchemy import Column, String, DateTime, ForeignKey, Integer, Float, Enum as SQLEnum, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
import enum
from app.database import Base


class ProjectStatus(str, enum.Enum):
    """Project lifecycle status"""
    DRAFT = "draft"
    PROCESSING = "processing"
    ACTIVE = "active"
    COMPLETED = "completed"
    FINALIZED = "finalized"
    ARCHIVED = "archived"


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = {"extend_existing": True}
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    # Basic information
    name = Column(String(255), nullable=False, index=True)
    description = Column(Text, nullable=True)
    status = Column(SQLEnum(ProjectStatus), default=ProjectStatus.DRAFT)
    
    # Location details
    location = Column(String(255), nullable=True)
    county = Column(String(50), nullable=True)
    
    # Project classification
    client_type = Column(String(50), nullable=True)  # public/private
    soil_type = Column(String(50), nullable=True)
    structural_system = Column(String(50), nullable=True)
    building_use = Column(String(50), nullable=True)
    
    # Building specifications
    number_of_floors = Column(Integer, nullable=True)
    floor_area = Column(Float, nullable=True)  # sqm per floor
    total_gfa = Column(Float, nullable=True)  # Total Gross Floor Area
    
    # File references
    uploaded_files = Column(JSONB, default=list)  # List of file paths
    processed_files = Column(JSONB, default=dict)  # Processed file metadata
    
    # AI Processing metadata
    ai_confidence_score = Column(Float, default=0.0)
    ai_remarks = Column(JSONB, default=dict)
    needs_review = Column(JSONB, default=list)  # Items flagged for review
    
    # Costing summary
    estimated_cost = Column(Float, default=0.0)
    actual_cost = Column(Float, default=0.0)
    contingency_percentage = Column(Float, default=0.10)
    
    # Project phases
    is_finalized = Column(Boolean, default=False)
    finalized_at = Column(DateTime, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_accessed = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    owner = relationship("User", back_populates="projects")
    boq_items = relationship("BOQItem", back_populates="project", cascade="all, delete-orphan")
    bbs_items = relationship("BBSItem", back_populates="project", cascade="all, delete-orphan")
    expenses = relationship("Expense", back_populates="project", cascade="all, delete-orphan")
    site_logs = relationship("SiteLog", back_populates="project", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Project {self.name}>"


# backend/app/models/boq.py
"""Bill of Quantities model"""

from sqlalchemy import Column, String, DateTime, ForeignKey, Integer, Float, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
from app.database import Base


class BOQItem(Base):
    __tablename__ = "boq_items"
    __table_args__ = {"extend_existing": True}
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    
    # Item identification
    item_number = Column(String(50), nullable=False)  # e.g., A.1.1
    category = Column(String(100), nullable=False)  # e.g., Substructure
    sub_category = Column(String(100), nullable=True)
    description = Column(Text, nullable=False)
    
    # Quantity details
    unit = Column(String(20), nullable=False)  # sqm, m, No., etc.
    net_quantity = Column(Float, nullable=False)
    waste_factor = Column(Float, default=1.0)
    gross_quantity = Column(Float, nullable=False)
    
    # Costing
    unit_rate = Column(Float, default=0.0)
    total_cost = Column(Float, default=0.0)
    
    # Materials breakdown
    materials_breakdown = Column(JSONB, default=dict)  # Detailed material list
    
    # AI metadata
    confidence_score = Column(Float, default=1.0)
    ai_extracted = Column(Boolean, default=False)
    needs_review = Column(Boolean, default=False)
    remarks = Column(Text, nullable=True)
    
    # As-built tracking
    as_built_quantity = Column(Float, nullable=True)
    as_built_remarks = Column(Text, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    project = relationship("Project", back_populates="boq_items")
    comments = relationship("Comment", back_populates="boq_item", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<BOQItem {self.item_number}: {self.description}>"


# backend/app/models/bbs.py
"""Bar Bending Schedule model"""

from sqlalchemy import Column, String, DateTime, ForeignKey, Integer, Float, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
from app.database import Base


class BBSItem(Base):
    __tablename__ = "bbs_items"
    __table_args__ = {"extend_existing": True}
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    
    # Bar identification
    bar_mark = Column(String(50), nullable=False)
    member_type = Column(String(100), nullable=False)  # Beam, Column, Slab, etc.
    member_location = Column(String(255), nullable=True)
    
    # Bar specifications
    bar_diameter = Column(Integer, nullable=False)  # mm (e.g., 12, 16, 20)
    bar_type = Column(String(10), nullable=False)  # Type (T, R, Y)
    shape_code = Column(String(10), nullable=False)  # BS 8666 shape code
    
    # Dimensions (all in mm)
    length_a = Column(Float, nullable=True)
    length_b = Column(Float, nullable=True)
    length_c = Column(Float, nullable=True)
    length_d = Column(Float, nullable=True)
    length_e = Column(Float, nullable=True)
    
    # Calculations
    total_length = Column(Float, nullable=False)  # mm
    number_of_bars = Column(Integer, nullable=False)
    unit_weight = Column(Float, nullable=False)  # kg/m
    total_weight = Column(Float, nullable=False)  # kg (rounded to nearest 50kg)
    
    # Additional notes
    remarks = Column(Text, nullable=True)
    
    # As-built tracking
    as_built_quantity = Column(Integer, nullable=True)
    as_built_weight = Column(Float, nullable=True)
    as_built_remarks = Column(Text, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    project = relationship("Project", back_populates="bbs_items")
    comments = relationship("Comment", back_populates="bbs_item", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<BBSItem {self.bar_mark}: {self.bar_diameter}mm {self.bar_type}>"


# To be continued in next artifact with remaining models...

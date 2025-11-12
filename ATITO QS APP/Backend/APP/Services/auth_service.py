# backend/app/services/auth_service.py
"""
Authentication and Authorization Service
Handles user registration, login, token management, and RBAC
Author: Eng. STEPHEN ODHIAMBO
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
import secrets

from app.config import settings
from app.models.user import User, UserRole, SubscriptionPlan
from app.database import get_db

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# HTTP Bearer token scheme
security = HTTPBearer()


class AuthService:
    """Authentication and authorization service"""
    
    @staticmethod
    def hash_password(password: str) -> str:
        """Hash a plain text password"""
        return pwd_context.hash(password)
    
    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """Verify a password against its hash"""
        return pwd_context.verify(plain_password, hashed_password)
    
    @staticmethod
    def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
        """Create JWT access token"""
        to_encode = data.copy()
        
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        
        to_encode.update({"exp": expire, "type": "access"})
        encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
        return encoded_jwt
    
    @staticmethod
    def create_refresh_token(data: Dict[str, Any]) -> str:
        """Create JWT refresh token"""
        to_encode = data.copy()
        expire = datetime.utcnow() + timedelta(minutes=settings.REFRESH_TOKEN_EXPIRE_MINUTES)
        to_encode.update({"exp": expire, "type": "refresh"})
        encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
        return encoded_jwt
    
    @staticmethod
    def decode_token(token: str) -> Dict[str, Any]:
        """Decode and verify JWT token"""
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
            return payload
        except JWTError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
    
    @staticmethod
    def is_super_user(email: str) -> bool:
        """Check if email belongs to super user"""
        return email in settings.SUPER_USER_EMAILS
    
    @staticmethod
    def get_user_role(email: str, requested_role: Optional[UserRole] = None) -> UserRole:
        """Determine user role based on email and request"""
        if AuthService.is_super_user(email):
            return UserRole.SUPER_USER
        return requested_role or UserRole.CLIENT
    
    @staticmethod
    def register_user(
        db: Session,
        email: str,
        password: str,
        full_name: str,
        phone_number: Optional[str] = None,
        role: Optional[UserRole] = None
    ) -> User:
        """Register a new user"""
        # Check if user already exists
        existing_user = db.query(User).filter(User.email == email).first()
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )
        
        # Determine role
        user_role = AuthService.get_user_role(email, role)
        
        # Create new user
        new_user = User(
            email=email,
            hashed_password=AuthService.hash_password(password),
            full_name=full_name,
            phone_number=phone_number,
            role=user_role,
            subscription_plan=SubscriptionPlan.FREE,
            is_active=True,
            is_verified=False if user_role != UserRole.SUPER_USER else True,
            trial_start_date=datetime.utcnow(),
            trial_end_date=datetime.utcnow() + timedelta(days=settings.FREE_TRIAL_DAYS)
        )
        
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        
        return new_user
    
    @staticmethod
    def authenticate_user(db: Session, email: str, password: str) -> Optional[User]:
        """Authenticate user with email and password"""
        user = db.query(User).filter(User.email == email).first()
        
        if not user:
            return None
        
        if not AuthService.verify_password(password, user.hashed_password):
            return None
        
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is deactivated"
            )
        
        # Update last login
        user.last_login_at = datetime.utcnow()
        db.commit()
        
        return user
    
    @staticmethod
    def login(db: Session, email: str, password: str) -> Dict[str, Any]:
        """User login with email and password"""
        user = AuthService.authenticate_user(db, email, password)
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Create tokens
        access_token = AuthService.create_access_token(
            data={
                "sub": str(user.id),
                "email": user.email,
                "role": user.role.value
            }
        )
        
        refresh_token = AuthService.create_refresh_token(
            data={"sub": str(user.id)}
        )
        
        # Save refresh token to database
        user.refresh_token = refresh_token
        db.commit()
        
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "user": {
                "id": str(user.id),
                "email": user.email,
                "full_name": user.full_name,
                "role": user.role.value,
                "subscription_plan": user.subscription_plan.value
            }
        }
    
    @staticmethod
    def refresh_access_token(db: Session, refresh_token: str) -> Dict[str, str]:
        """Refresh access token using refresh token"""
        payload = AuthService.decode_token(refresh_token)
        
        if payload.get("type") != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type"
            )
        
        user_id = payload.get("sub")
        user = db.query(User).filter(User.id == user_id).first()
        
        if not user or user.refresh_token != refresh_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token"
            )
        
        # Create new access token
        new_access_token = AuthService.create_access_token(
            data={
                "sub": str(user.id),
                "email": user.email,
                "role": user.role.value
            }
        )
        
        return {
            "access_token": new_access_token,
            "token_type": "bearer"
        }
    
    @staticmethod
    def logout(db: Session, user_id: str):
        """Logout user by invalidating refresh token"""
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            user.refresh_token = None
            db.commit()


# Dependency for getting current user from token
async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    """Get current authenticated user from token"""
    token = credentials.credentials
    payload = AuthService.decode_token(token)
    
    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials"
        )
    
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )
    
    # Reset daily token count if new day
    if user.last_token_reset.date() < datetime.utcnow().date():
        user.daily_token_count = 0
        user.last_token_reset = datetime.utcnow()
        db.commit()
    
    return user


# Role-based access control decorators
def require_role(*allowed_roles: UserRole):
    """Decorator to require specific roles"""
    async def role_checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed_roles and current_user.role != UserRole.SUPER_USER:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions"
            )
        return current_user
    return role_checker


# Subscription validation
async def validate_subscription(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> User:
    """Validate user has active subscription"""
    # Super users always have access
    if current_user.is_super_user():
        return current_user
    
    # Check trial period for free users
    if current_user.subscription_plan == SubscriptionPlan.FREE:
        if datetime.utcnow() > current_user.trial_end_date:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail="Free trial has expired. Please upgrade your subscription."
            )
        return current_user
    
    # Check paid subscription status
    if not current_user.subscription_active:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Subscription is not active. Please renew your subscription."
        )
    
    # Check subscription expiry
    if current_user.subscription_end_date and datetime.utcnow() > current_user.subscription_end_date:
        current_user.subscription_active = False
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Subscription has expired. Please renew your subscription."
        )
    
    return current_user


# Permission checker for project access
class PermissionChecker:
    """Check user permissions for specific resources"""
    
    @staticmethod
    def can_view_project(user: User, project) -> bool:
        """Check if user can view a project"""
        if user.is_super_user():
            return True
        
        # Owner can always view
        if project.owner_id == user.id:
            return True
        
        # Check if user is a team member (to be implemented with team model)
        return False
    
    @staticmethod
    def can_edit_project(user: User, project) -> bool:
        """Check if user can edit a project"""
        if user.is_super_user():
            return True
        
        # Only owner can edit (or admins/QS if they're team members)
        if project.owner_id == user.id:
            return True
        
        # Check team member with edit permissions
        return False
    
    @staticmethod
    def can_delete_project(user: User, project) -> bool:
        """Check if user can delete a project"""
        if user.is_super_user():
            return True
        
        # Only owner can delete
        return project.owner_id == user.id
    
    @staticmethod
    def can_comment(user: User) -> bool:
        """Check if user can comment"""
        # All authenticated users can comment
        return True
    
    @staticmethod
    def can_create_project(user: User, db: Session) -> bool:
        """Check if user can create more projects"""
        if user.is_super_user():
            return True
        
        # Count user's active projects
        from app.models.project import Project
        project_count = db.query(Project).filter(
            Project.owner_id == user.id,
            Project.status != "archived"
        ).count()
        
        return user.can_create_project(project_count)


# backend/app/schemas/user.py
"""
Pydantic schemas for User API
"""

from pydantic import BaseModel, EmailStr, validator
from typing import Optional
from datetime import datetime
from app.models.user import UserRole, SubscriptionPlan


class UserCreate(BaseModel):
    """Schema for user registration"""
    email: EmailStr
    password: str
    full_name: str
    phone_number: Optional[str] = None
    
    @validator('password')
    def validate_password(cls, v):
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters long')
        return v


class UserLogin(BaseModel):
    """Schema for user login"""
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    """Schema for user response"""
    id: str
    email: str
    full_name: str
    phone_number: Optional[str]
    role: UserRole
    subscription_plan: SubscriptionPlan
    is_active: bool
    trial_end_date: datetime
    subscription_active: bool
    created_at: datetime
    
    class Config:
        from_attributes = True


class TokenResponse(BaseModel):
    """Schema for token response"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: dict


class RefreshTokenRequest(BaseModel):
    """Schema for refresh token request"""
    refresh_token: str


# backend/app/api/auth.py
"""
Authentication API endpoints
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.auth_service import AuthService, get_current_user
from app.schemas.user import UserCreate, UserLogin, UserResponse, TokenResponse, RefreshTokenRequest
from app.models.user import User
from app.models.audit import AuditLog

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(user_data: UserCreate, db: Session = Depends(get_db)):
    """
    Register a new user
    
    - **Free Trial**: 30 days, 50 tokens/day, max 1 project (1 floor)
    - **Auto-assigns super user role** if email matches configured super user emails
    """
    try:
        new_user = AuthService.register_user(
            db=db,
            email=user_data.email,
            password=user_data.password,
            full_name=user_data.full_name,
            phone_number=user_data.phone_number
        )
        
        # Log registration
        audit_log = AuditLog(
            user_id=new_user.id,
            action_type="USER_REGISTRATION",
            resource_type="USER",
            resource_id=new_user.id,
            description=f"User {new_user.email} registered successfully",
            status="SUCCESS"
        )
        db.add(audit_log)
        db.commit()
        
        return new_user
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Registration failed: {str(e)}"
        )


@router.post("/login", response_model=TokenResponse)
async def login(credentials: UserLogin, db: Session = Depends(get_db)):
    """
    User login
    
    Returns access token and refresh token for persistent login
    """
    try:
        result = AuthService.login(db, credentials.email, credentials.password)
        
        # Log successful login
        user = db.query(User).filter(User.email == credentials.email).first()
        audit_log = AuditLog(
            user_id=user.id,
            action_type="USER_LOGIN",
            resource_type="USER",
            resource_id=user.id,
            description=f"User {user.email} logged in successfully",
            status="SUCCESS"
        )
        db.add(audit_log)
        db.commit()
        
        return result
    
    except HTTPException:
        # Log failed login attempt
        audit_log = AuditLog(
            action_type="USER_LOGIN",
            resource_type="USER",
            description=f"Failed login attempt for {credentials.email}",
            status="FAILURE",
            error_message="Invalid credentials"
        )
        db.add(audit_log)
        db.commit()
        raise


@router.post("/refresh", response_model=dict)
async def refresh_token(request: RefreshTokenRequest, db: Session = Depends(get_db)):
    """
    Refresh access token using refresh token
    """
    try:
        result = AuthService.refresh_access_token(db, request.refresh_token)
        return result
    except HTTPException:
        raise


@router.post("/logout")
async def logout(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    Logout current user
    """
    AuthService.logout(db, str(current_user.id))
    
    # Log logout
    audit_log = AuditLog(
        user_id=current_user.id,
        action_type="USER_LOGOUT",
        resource_type="USER",
        resource_id=current_user.id,
        description=f"User {current_user.email} logged out",
        status="SUCCESS"
    )
    db.add(audit_log)
    db.commit()
    
    return {"message": "Logged out successfully"}


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: User = Depends(get_current_user)):
    """
    Get current user information
    """
    return current_user


@router.get("/validate")
async def validate_token(current_user: User = Depends(get_current_user)):
    """
    Validate current access token
    """
    return {
        "valid": True,
        "user_id": str(current_user.id),
        "email": current_user.email
    }

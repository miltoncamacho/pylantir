#!/usr/bin/env python3

"""
    Author: Milton Camacho
    Date: 2025-11-18
    FastAPI application for Pylantir worklist management.
    
    Provides RESTful API endpoints for:
    - GET /worklist: Retrieve worklist items with optional filtering
    - POST /worklist: Create new worklist items
    - PUT /worklist/{id}: Update existing worklist items
    - DELETE /worklist/{id}: Delete worklist items
    - GET /users: List users (admin only)
    - POST /users: Create users (admin only)
    - PUT /users/{id}: Update users (admin only)
    - DELETE /users/{id}: Delete users (admin only)
"""

import logging
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta

try:
    from fastapi import FastAPI, HTTPException, Depends, status, Query
    from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
    from fastapi.middleware.cors import CORSMiddleware
    from pydantic import BaseModel, validator
except ImportError:
    raise ImportError(
        "FastAPI dependencies not installed. Install with: pip install pylantir[api]"
    )

from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from .db_setup import get_db
from .auth_db_setup import get_auth_db, init_auth_database, create_initial_admin_user
from .models import WorklistItem
from .auth_models import User, UserRole
from .auth_utils import (
    authenticate_user, 
    create_access_token, 
    verify_token, 
    get_password_hash,
    AuthenticationError,
    AuthorizationError
)

lgr = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Pylantir API",
    description="RESTful API for DICOM Modality Worklist Management",
    version="0.2.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Security
security = HTTPBearer()


# Pydantic models for API
class WorklistItemResponse(BaseModel):
    """Response model for worklist items."""
    id: int
    study_instance_uid: Optional[str]
    patient_name: Optional[str]
    patient_id: Optional[str]
    patient_birth_date: Optional[str]
    patient_sex: Optional[str]
    patient_weight_lb: Optional[str]
    accession_number: Optional[str]
    referring_physician_name: Optional[str]
    modality: Optional[str]
    study_description: Optional[str]
    scheduled_station_aetitle: Optional[str]
    scheduled_start_date: Optional[str]
    scheduled_start_time: Optional[str]
    performing_physician: Optional[str]
    procedure_description: Optional[str]
    protocol_name: Optional[str]
    station_name: Optional[str]
    performed_procedure_step_status: Optional[str]

    class Config:
        from_attributes = True


class WorklistItemCreate(BaseModel):
    """Model for creating worklist items."""
    study_instance_uid: Optional[str] = None
    patient_name: str
    patient_id: str
    patient_birth_date: Optional[str] = None
    patient_sex: Optional[str] = None
    patient_weight_lb: Optional[str] = "100"
    accession_number: Optional[str] = None
    referring_physician_name: Optional[str] = None
    modality: Optional[str] = None
    study_description: Optional[str] = None
    scheduled_station_aetitle: Optional[str] = None
    scheduled_start_date: Optional[str] = None
    scheduled_start_time: Optional[str] = None
    performing_physician: Optional[str] = None
    procedure_description: Optional[str] = None
    protocol_name: Optional[str] = None
    station_name: Optional[str] = None
    performed_procedure_step_status: str = "SCHEDULED"

    @validator('performed_procedure_step_status')
    def validate_status(cls, v):
        allowed_statuses = ['SCHEDULED', 'IN_PROGRESS', 'COMPLETED', 'DISCONTINUED']
        if v not in allowed_statuses:
            raise ValueError(f'Status must be one of: {allowed_statuses}')
        return v


class WorklistItemUpdate(BaseModel):
    """Model for updating worklist items."""
    patient_name: Optional[str] = None
    patient_birth_date: Optional[str] = None
    patient_sex: Optional[str] = None
    patient_weight_lb: Optional[str] = None
    referring_physician_name: Optional[str] = None
    modality: Optional[str] = None
    study_description: Optional[str] = None
    scheduled_station_aetitle: Optional[str] = None
    scheduled_start_date: Optional[str] = None
    scheduled_start_time: Optional[str] = None
    performing_physician: Optional[str] = None
    procedure_description: Optional[str] = None
    protocol_name: Optional[str] = None
    station_name: Optional[str] = None
    performed_procedure_step_status: Optional[str] = None

    @validator('performed_procedure_step_status')
    def validate_status(cls, v):
        if v is not None:
            allowed_statuses = ['SCHEDULED', 'IN_PROGRESS', 'COMPLETED', 'DISCONTINUED']
            if v not in allowed_statuses:
                raise ValueError(f'Status must be one of: {allowed_statuses}')
        return v


class UserResponse(BaseModel):
    """Response model for users."""
    id: int
    username: str
    email: Optional[str]
    full_name: Optional[str]
    role: str
    is_active: bool
    created_at: datetime
    last_login: Optional[datetime]

    class Config:
        from_attributes = True


class UserCreate(BaseModel):
    """Model for creating users."""
    username: str
    email: Optional[str] = None
    full_name: Optional[str] = None
    password: str
    role: str = "read"

    @validator('role')
    def validate_role(cls, v):
        allowed_roles = ['admin', 'write', 'read']
        if v not in allowed_roles:
            raise ValueError(f'Role must be one of: {allowed_roles}')
        return v


class UserUpdate(BaseModel):
    """Model for updating users."""
    email: Optional[str] = None
    full_name: Optional[str] = None
    password: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None

    @validator('role')
    def validate_role(cls, v):
        if v is not None:
            allowed_roles = ['admin', 'write', 'read']
            if v not in allowed_roles:
                raise ValueError(f'Role must be one of: {allowed_roles}')
        return v


class Token(BaseModel):
    """Token response model."""
    access_token: str
    token_type: str


class LoginRequest(BaseModel):
    """Login request model."""
    username: str
    password: str


# Authentication dependency
async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    auth_db: Session = Depends(get_auth_db)
) -> User:
    """
    Get current authenticated user from JWT token.
    
    Args:
        credentials: HTTP Authorization credentials
        auth_db: Authentication database session
        
    Returns:
        User: Authenticated user object
        
    Raises:
        HTTPException: If authentication fails
    """
    try:
        token = credentials.credentials
        payload = verify_token(token)
        
        if payload is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        username = payload.get("sub")
        if username is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        user = auth_db.query(User).filter(User.username == username).first()
        if user is None or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found or inactive",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        return user
        
    except HTTPException:
        raise
    except Exception as e:
        lgr.error(f"Authentication error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed",
            headers={"WWW-Authenticate": "Bearer"},
        )


def require_permission(action: str, resource: str = "worklist"):
    """
    Dependency factory for permission checking.
    
    Args:
        action: Required action permission
        resource: Resource type
        
    Returns:
        Dependency function
    """
    def permission_checker(current_user: User = Depends(get_current_user)) -> User:
        if not current_user.has_permission(action, resource):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions for {action} on {resource}"
            )
        return current_user
    
    return permission_checker


# Authentication endpoints
@app.post("/auth/login", response_model=Token)
async def login(
    login_data: LoginRequest,
    auth_db: Session = Depends(get_auth_db)
):
    """Authenticate user and return access token."""
    try:
        user = authenticate_user(auth_db, login_data.username, login_data.password)
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username or password",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        access_token = create_access_token(data={"sub": user.username})
        
        lgr.info(f"User {user.username} logged in successfully")
        
        return {
            "access_token": access_token,
            "token_type": "bearer"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        lgr.error(f"Login error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Login failed"
        )


# Worklist endpoints
@app.get("/worklist", response_model=List[WorklistItemResponse])
async def get_worklist_items(
    status: Optional[List[str]] = Query(
        default=["SCHEDULED", "IN_PROGRESS"],
        description="Filter by procedure status (SCHEDULED, IN_PROGRESS, COMPLETED, DISCONTINUED)"
    ),
    limit: int = Query(default=100, le=1000, description="Maximum number of items to return"),
    offset: int = Query(default=0, ge=0, description="Number of items to skip"),
    patient_id: Optional[str] = Query(default=None, description="Filter by patient ID"),
    modality: Optional[str] = Query(default=None, description="Filter by modality"),
    current_user: User = Depends(require_permission("read", "worklist")),
    db: Session = Depends(get_db)
):
    """
    Get worklist items with optional filtering.
    
    Requires: read permission on worklist
    """
    try:
        query = db.query(WorklistItem)
        
        # Apply filters
        if status:
            query = query.filter(WorklistItem.performed_procedure_step_status.in_(status))
        
        if patient_id:
            query = query.filter(WorklistItem.patient_id.ilike(f"%{patient_id}%"))
            
        if modality:
            query = query.filter(WorklistItem.modality == modality)
        
        # Apply pagination
        items = query.offset(offset).limit(limit).all()
        
        lgr.info(f"User {current_user.username} retrieved {len(items)} worklist items")
        
        return items
        
    except Exception as e:
        lgr.error(f"Error retrieving worklist items: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve worklist items"
        )


@app.post("/worklist", response_model=WorklistItemResponse)
async def create_worklist_item(
    item_data: WorklistItemCreate,
    current_user: User = Depends(require_permission("create", "worklist")),
    db: Session = Depends(get_db)
):
    """
    Create a new worklist item.
    
    Requires: write permission on worklist
    """
    try:
        # Generate study_instance_uid if not provided
        if not item_data.study_instance_uid:
            import uuid
            item_data.study_instance_uid = f"1.2.840.10008.3.1.2.3.4.{uuid.uuid4().int}"
        
        # Create database object
        db_item = WorklistItem(**item_data.dict())
        
        db.add(db_item)
        db.commit()
        db.refresh(db_item)
        
        lgr.info(f"User {current_user.username} created worklist item {db_item.id}")
        
        return db_item
        
    except Exception as e:
        lgr.error(f"Error creating worklist item: {e}")
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Failed to create worklist item"
        )


@app.put("/worklist/{item_id}", response_model=WorklistItemResponse)
async def update_worklist_item(
    item_id: int,
    item_data: WorklistItemUpdate,
    current_user: User = Depends(require_permission("update", "worklist")),
    db: Session = Depends(get_db)
):
    """
    Update an existing worklist item.
    
    Requires: write permission on worklist
    """
    try:
        db_item = db.query(WorklistItem).filter(WorklistItem.id == item_id).first()
        
        if not db_item:
            raise HTTPException(
                status_code=404,
                detail=f"Worklist item {item_id} not found"
            )
        
        # Update fields that are provided
        update_data = item_data.dict(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_item, field, value)
        
        db.commit()
        db.refresh(db_item)
        
        lgr.info(f"User {current_user.username} updated worklist item {item_id}")
        
        return db_item
        
    except HTTPException:
        raise
    except Exception as e:
        lgr.error(f"Error updating worklist item {item_id}: {e}")
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Failed to update worklist item"
        )


@app.delete("/worklist/{item_id}")
async def delete_worklist_item(
    item_id: int,
    current_user: User = Depends(require_permission("delete", "worklist")),
    db: Session = Depends(get_db)
):
    """
    Delete a worklist item.
    
    Requires: write permission on worklist
    """
    try:
        db_item = db.query(WorklistItem).filter(WorklistItem.id == item_id).first()
        
        if not db_item:
            raise HTTPException(
                status_code=404,
                detail=f"Worklist item {item_id} not found"
            )
        
        db.delete(db_item)
        db.commit()
        
        lgr.info(f"User {current_user.username} deleted worklist item {item_id}")
        
        return {"message": f"Worklist item {item_id} deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        lgr.error(f"Error deleting worklist item {item_id}: {e}")
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Failed to delete worklist item"
        )


# User management endpoints (admin only)
@app.get("/users", response_model=List[UserResponse])
async def get_users(
    current_user: User = Depends(require_permission("read", "users")),
    auth_db: Session = Depends(get_auth_db)
):
    """
    Get list of all users.
    
    Requires: admin role
    """
    try:
        users = auth_db.query(User).all()
        
        lgr.info(f"Admin {current_user.username} retrieved user list")
        
        return users
        
    except Exception as e:
        lgr.error(f"Error retrieving users: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve users"
        )


@app.post("/users", response_model=UserResponse)
async def create_user(
    user_data: UserCreate,
    current_user: User = Depends(require_permission("create", "users")),
    auth_db: Session = Depends(get_auth_db)
):
    """
    Create a new user.
    
    Requires: admin role
    """
    try:
        # Check if username already exists
        existing_user = auth_db.query(User).filter(User.username == user_data.username).first()
        if existing_user:
            raise HTTPException(
                status_code=400,
                detail="Username already exists"
            )
        
        # Hash password
        hashed_password = get_password_hash(user_data.password)
        
        # Create user
        db_user = User(
            username=user_data.username,
            email=user_data.email,
            full_name=user_data.full_name,
            hashed_password=hashed_password,
            role=UserRole(user_data.role),
            is_active=True,
            created_at=datetime.utcnow(),
            created_by=current_user.id
        )
        
        auth_db.add(db_user)
        auth_db.commit()
        auth_db.refresh(db_user)
        
        lgr.info(f"Admin {current_user.username} created user {db_user.username}")
        
        return db_user
        
    except HTTPException:
        raise
    except Exception as e:
        lgr.error(f"Error creating user: {e}")
        auth_db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Failed to create user"
        )


@app.put("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    user_data: UserUpdate,
    current_user: User = Depends(require_permission("update", "users")),
    auth_db: Session = Depends(get_auth_db)
):
    """
    Update an existing user.
    
    Requires: admin role
    """
    try:
        db_user = auth_db.query(User).filter(User.id == user_id).first()
        
        if not db_user:
            raise HTTPException(
                status_code=404,
                detail=f"User {user_id} not found"
            )
        
        # Update fields that are provided
        update_data = user_data.dict(exclude_unset=True)
        
        # Handle password hashing separately
        if 'password' in update_data:
            update_data['hashed_password'] = get_password_hash(update_data.pop('password'))
        
        # Handle role conversion
        if 'role' in update_data:
            update_data['role'] = UserRole(update_data['role'])
        
        for field, value in update_data.items():
            setattr(db_user, field, value)
        
        auth_db.commit()
        auth_db.refresh(db_user)
        
        lgr.info(f"Admin {current_user.username} updated user {db_user.username}")
        
        return db_user
        
    except HTTPException:
        raise
    except Exception as e:
        lgr.error(f"Error updating user {user_id}: {e}")
        auth_db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Failed to update user"
        )


@app.delete("/users/{user_id}")
async def delete_user(
    user_id: int,
    current_user: User = Depends(require_permission("delete", "users")),
    auth_db: Session = Depends(get_auth_db)
):
    """
    Delete a user.
    
    Requires: admin role
    """
    try:
        if user_id == current_user.id:
            raise HTTPException(
                status_code=400,
                detail="Cannot delete your own account"
            )
        
        db_user = auth_db.query(User).filter(User.id == user_id).first()
        
        if not db_user:
            raise HTTPException(
                status_code=404,
                detail=f"User {user_id} not found"
            )
        
        auth_db.delete(db_user)
        auth_db.commit()
        
        lgr.info(f"Admin {current_user.username} deleted user {db_user.username}")
        
        return {"message": f"User {db_user.username} deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        lgr.error(f"Error deleting user {user_id}: {e}")
        auth_db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Failed to delete user"
        )


# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "timestamp": datetime.utcnow()}


# Initialize authentication database on startup
@app.on_event("startup")
async def startup_event():
    """Initialize authentication system on startup."""
    try:
        # Try to load configuration to get users_db_path
        # This will work when started via CLI, but fallback gracefully for direct API startup
        import os
        users_db_path = os.getenv("USERS_DB_PATH")  # Set by CLI when config is loaded
        
        init_auth_database(users_db_path)
        create_initial_admin_user(users_db_path)
        lgr.info("Pylantir API server started successfully")
    except Exception as e:
        lgr.error(f"Failed to initialize API server: {e}")
        raise


if __name__ == "__main__":
    import uvicorn
    lgr.info("Starting Pylantir API server...")
    uvicorn.run(app, host="0.0.0.0", port=8000)
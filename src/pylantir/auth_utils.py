#!/usr/bin/env python3

"""
    Author: Milton Camacho
    Date: 2025-11-18
    Authentication utilities for password hashing, JWT token generation,
    and user authentication functions.
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from passlib.context import CryptContext
from jose import JWTError, jwt
from sqlalchemy.orm import Session

lgr = logging.getLogger(__name__)

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT configuration
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30


class AuthenticationError(Exception):
    """Raised when authentication fails."""
    pass


class AuthorizationError(Exception):
    """Raised when user lacks required permissions."""
    pass


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a plain password against a hashed password.
    
    Args:
        plain_password: Plain text password
        hashed_password: Hashed password from database
        
    Returns:
        bool: True if password matches
    """
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except Exception as e:
        lgr.error(f"Password verification error: {e}")
        return False


def get_password_hash(password: str) -> str:
    """
    Hash a plain password using bcrypt.
    
    Args:
        password: Plain text password
        
    Returns:
        str: Hashed password
    """
    try:
        return pwd_context.hash(password)
    except Exception as e:
        lgr.error(f"Password hashing error: {e}")
        raise AuthenticationError("Failed to hash password")


def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """
    Create a JWT access token.
    
    Args:
        data: Data to encode in token (typically user info)
        expires_delta: Token expiration time
        
    Returns:
        str: JWT token
    """
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    
    try:
        encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
        return encoded_jwt
    except Exception as e:
        lgr.error(f"Token creation error: {e}")
        raise AuthenticationError("Failed to create access token")


def verify_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Verify and decode a JWT token.
    
    Args:
        token: JWT token string
        
    Returns:
        Dict containing token payload or None if invalid
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError as e:
        lgr.warning(f"Token verification failed: {e}")
        return None


def authenticate_user(db: Session, username: str, password: str):
    """
    Authenticate user with username and password.
    
    Args:
        db: Database session
        username: Username
        password: Plain text password
        
    Returns:
        User object if authentication successful, None otherwise
    """
    from .auth_models import User
    
    try:
        user = db.query(User).filter(User.username == username).first()
        
        if not user:
            lgr.warning(f"Authentication attempt for non-existent user: {username}")
            return None
            
        if not user.is_active:
            lgr.warning(f"Authentication attempt for inactive user: {username}")
            return None
            
        if not verify_password(password, user.hashed_password):
            lgr.warning(f"Failed password authentication for user: {username}")
            return None
            
        # Update last login time
        user.last_login = datetime.utcnow()
        db.commit()
        
        lgr.info(f"Successful authentication for user: {username}")
        return user
        
    except Exception as e:
        lgr.error(f"Authentication error for user {username}: {e}")
        db.rollback()
        return None


def create_admin_user(db: Session, username: str = "admin", password: str = "admin123", 
                     email: str = "admin@localhost", full_name: str = "System Administrator"):
    """
    Create initial admin user if no users exist.
    
    Args:
        db: Database session
        username: Admin username
        password: Admin password
        email: Admin email
        full_name: Admin full name
        
    Returns:
        User object or None if creation fails
    """
    from .auth_models import User, UserRole
    
    try:
        # Check if any users exist
        user_count = db.query(User).count()
        
        if user_count > 0:
            lgr.info("Users already exist, skipping admin user creation")
            return None
            
        # Create admin user
        hashed_password = get_password_hash(password)
        
        admin_user = User(
            username=username,
            email=email,
            full_name=full_name,
            hashed_password=hashed_password,
            role=UserRole.ADMIN,
            is_active=True,
            created_at=datetime.utcnow()
        )
        
        db.add(admin_user)
        db.commit()
        db.refresh(admin_user)
        
        lgr.info(f"Created initial admin user: {username}")
        return admin_user
        
    except Exception as e:
        lgr.error(f"Failed to create admin user: {e}")
        db.rollback()
        return None
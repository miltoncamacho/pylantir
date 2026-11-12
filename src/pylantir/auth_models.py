#!/usr/bin/env python3

"""
    Author: Milton Camacho
    Date: 2025-11-18
    This script provides the SQLAlchemy models for user authentication and authorization.
    
    User roles:
    - admin: Full access to users and worklist data (CRUD operations)
    - write: Read and write access to worklist data only
    - read: Read-only access to worklist data only
"""

from sqlalchemy.orm import declarative_base
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Enum
from datetime import datetime
import logging
import enum

AuthBase = declarative_base()

lgr = logging.getLogger(__name__)


class UserRole(enum.Enum):
    """User role enumeration for access control."""
    ADMIN = "admin"
    WRITE = "write"  
    READ = "read"


class User(AuthBase):
    """User model for API authentication and authorization."""
    
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(100), unique=True, nullable=True)
    full_name = Column(String(100), nullable=True)
    hashed_password = Column(String(255), nullable=False)
    role = Column(Enum(UserRole), nullable=False, default=UserRole.READ)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime, nullable=True)
    created_by = Column(Integer, nullable=True)  # ID of user who created this account
    
    def __repr__(self):
        return f"<User(id={self.id}, username={self.username}, role={self.role.value}, active={self.is_active})>"

    def has_permission(self, action: str, resource: str = "worklist") -> bool:
        """
        Check if user has permission for specific action on resource.
        
        Args:
            action: Action type ('read', 'write', 'delete', 'create')
            resource: Resource type ('worklist', 'users')
        
        Returns:
            bool: True if user has permission
        """
        if not self.is_active:
            return False
            
        # Admin has all permissions
        if self.role == UserRole.ADMIN:
            return True
            
        # Non-admin users cannot manage other users
        if resource == "users":
            return False
            
        # Worklist permissions based on role
        if resource == "worklist":
            if action == "read":
                return self.role in [UserRole.READ, UserRole.WRITE, UserRole.ADMIN]
            elif action in ["write", "create", "update", "delete"]:
                return self.role in [UserRole.WRITE, UserRole.ADMIN]
                
        return False
#!/usr/bin/env python3

"""
    Author: Milton Camacho
    Date: 2025-11-18
    Database setup for authentication system.
    Manages separate users database connection and session handling.
"""

import os
import logging
from typing import Optional
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import SQLAlchemyError
from pathlib import Path

lgr = logging.getLogger(__name__)


class AuthDatabaseError(Exception):
    """Raised when authentication database operations fail."""
    pass


def get_auth_database_url(users_db_path: Optional[str] = None) -> str:
    """
    Get authentication database URL from configuration, environment, or default location.
    
    Args:
        users_db_path: Optional path to users database from configuration
    
    Returns:
        str: SQLite database URL for authentication
    """
    if users_db_path:
        # Use explicitly provided users database path from configuration
        auth_db_path = os.path.expanduser(users_db_path)
        lgr.info(f"Using configured users database path: {auth_db_path}")
    else:
        # Fallback to environment variable or default location
        auth_db_path_env = os.getenv("USERS_DB_PATH")
        
        if auth_db_path_env:
            auth_db_path = os.path.expanduser(auth_db_path_env)
            lgr.info(f"Using environment users database path: {auth_db_path}")
        else:
            # Default: users.db in same directory as main database
            main_db_path = os.getenv("DB_PATH", "~/Desktop/worklist.db")
            main_db_path = os.path.expanduser(main_db_path)
            
            db_dir = Path(main_db_path).parent
            auth_db_path = db_dir / "users.db"
            lgr.info(f"Using default users database path: {auth_db_path}")
    
    return f"sqlite:///{auth_db_path}"


# Create authentication database engine
auth_engine = None
AuthSessionLocal = None


def init_auth_database(users_db_path: Optional[str] = None) -> None:
    """
    Initialize authentication database engine and session factory.
    
    Args:
        users_db_path: Optional path to users database from configuration
    """
    global auth_engine, AuthSessionLocal
    
    try:
        database_url = get_auth_database_url(users_db_path)
        lgr.info(f"Initializing authentication database: {database_url}")
        
        auth_engine = create_engine(
            database_url,
            connect_args={"check_same_thread": False},  # SQLite specific
            echo=os.getenv("DB_ECHO", "False").lower() == "true"
        )
        
        AuthSessionLocal = sessionmaker(
            autocommit=False, 
            autoflush=False, 
            bind=auth_engine
        )
        
        # Create all tables
        from .auth_models import AuthBase
        AuthBase.metadata.create_all(bind=auth_engine)
        
        lgr.info("Authentication database initialized successfully")
        
    except Exception as e:
        lgr.error(f"Failed to initialize authentication database: {e}")
        raise AuthDatabaseError(f"Database initialization failed: {e}")


def get_auth_db() -> Session:
    """
    Get authentication database session.
    
    Returns:
        Session: SQLAlchemy session for authentication database
        
    Raises:
        AuthDatabaseError: If database is not initialized
    """
    if AuthSessionLocal is None:
        init_auth_database()
        
    if AuthSessionLocal is None:
        raise AuthDatabaseError("Authentication database not initialized")
    
    db = AuthSessionLocal()
    try:
        yield db
    except SQLAlchemyError as e:
        lgr.error(f"Database session error: {e}")
        db.rollback()
        raise AuthDatabaseError(f"Database operation failed: {e}")
    finally:
        db.close()


def create_initial_admin_user(users_db_path: Optional[str] = None) -> None:
    """
    Create initial admin user if no users exist in database.
    
    Args:
        users_db_path: Optional path to users database from configuration
    """
    try:
        # Initialize database with correct path if not already done
        if AuthSessionLocal is None:
            init_auth_database(users_db_path)
            
        db = next(get_auth_db())
        
        from .auth_utils import create_admin_user
        
        admin_user = create_admin_user(
            db=db,
            username="admin",
            password="admin123",  # Should be changed immediately
            email="admin@localhost",
            full_name="System Administrator"
        )
        
        if admin_user:
            lgr.warning("Created default admin user with password 'admin123'. Please change this immediately!")
            lgr.info("Use 'pylantir admin-password' command to change the admin password")
        
    except Exception as e:
        lgr.error(f"Failed to create initial admin user: {e}")


def backup_auth_database(backup_path: Optional[str] = None) -> bool:
    """
    Create backup of authentication database.
    
    Args:
        backup_path: Optional custom backup path
        
    Returns:
        bool: True if backup successful
    """
    try:
        database_url = get_auth_database_url()
        source_path = database_url.replace("sqlite:///", "")
        
        if backup_path is None:
            # Create backup in same directory with timestamp
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = f"{source_path}.backup_{timestamp}"
        
        # Copy database file
        import shutil
        shutil.copy2(source_path, backup_path)
        
        lgr.info(f"Authentication database backed up to: {backup_path}")
        return True
        
    except Exception as e:
        lgr.error(f"Failed to backup authentication database: {e}")
        return False
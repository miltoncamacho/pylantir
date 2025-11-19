#!/usr/bin/env python3

"""
    Author: Milton Camacho
    Date: 2025-11-18
    Database transaction management utilities for safe concurrent access.
    
    Ensures API operations don't interfere with RedCap sync functionality
    through proper transaction isolation and retry logic.
"""

import logging
import time
import functools
from contextlib import contextmanager
from sqlalchemy.exc import OperationalError, IntegrityError
from typing import Generator, Any, Callable

lgr = logging.getLogger(__name__)

class DatabaseBusyError(Exception):
    """Raised when database is busy and operation should be retried."""
    pass


def retry_on_database_busy(max_retries: int = 3, delay: float = 0.1):
    """
    Decorator to retry database operations on SQLite busy/locked errors.
    
    Args:
        max_retries: Maximum number of retry attempts
        delay: Initial delay between retries (exponential backoff)
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except OperationalError as e:
                    last_exception = e
                    error_message = str(e).lower()
                    
                    # Check if it's a database busy/locked error
                    if any(keyword in error_message for keyword in 
                          ['database is locked', 'database busy', 'locked']):
                        
                        if attempt < max_retries:
                            wait_time = delay * (2 ** attempt)  # Exponential backoff
                            lgr.warning(f"Database busy, retrying in {wait_time}s (attempt {attempt + 1}/{max_retries})")
                            time.sleep(wait_time)
                            continue
                        else:
                            lgr.error(f"Database busy after {max_retries} retries: {e}")
                            raise DatabaseBusyError(f"Database busy after {max_retries} retries") from e
                    else:
                        # Not a busy error, re-raise immediately
                        raise
                except Exception as e:
                    # Non-database errors, re-raise immediately
                    raise
            
            # This should never be reached, but just in case
            if last_exception:
                raise last_exception
            else:
                raise DatabaseBusyError("Unknown database error occurred")
        
        return wrapper
    return decorator


@contextmanager
def safe_database_transaction(session) -> Generator[Any, None, None]:
    """
    Context manager for safe database transactions with automatic rollback.
    
    Args:
        session: SQLAlchemy database session
        
    Yields:
        session: The database session within transaction context
        
    Raises:
        DatabaseBusyError: If database is busy after retries
        IntegrityError: If data integrity constraints are violated
    """
    try:
        # Begin explicit transaction
        session.begin()
        
        yield session
        
        # Commit if no exceptions occurred
        session.commit()
        lgr.debug("Database transaction committed successfully")
        
    except OperationalError as e:
        session.rollback()
        error_message = str(e).lower()
        
        if any(keyword in error_message for keyword in 
              ['database is locked', 'database busy', 'locked']):
            lgr.warning(f"Database transaction rolled back due to busy database: {e}")
            raise DatabaseBusyError("Database is busy, transaction rolled back") from e
        else:
            lgr.error(f"Database transaction rolled back due to operational error: {e}")
            raise
            
    except IntegrityError as e:
        session.rollback()
        lgr.warning(f"Database transaction rolled back due to integrity error: {e}")
        raise
        
    except Exception as e:
        session.rollback()
        lgr.error(f"Database transaction rolled back due to unexpected error: {e}")
        raise
    
    finally:
        # Ensure session is clean
        session.close()


def isolation_level_read_committed(session):
    """
    Set SQLite to use READ COMMITTED isolation level for better concurrency.
    
    Args:
        session: SQLAlchemy database session
    """
    try:
        # SQLite pragma for better concurrency
        session.execute("PRAGMA journal_mode=WAL")  # Write-Ahead Logging for concurrent reads
        session.execute("PRAGMA synchronous=NORMAL")  # Balance safety and performance 
        session.execute("PRAGMA busy_timeout=30000")  # 30 second timeout
        session.execute("PRAGMA temp_store=MEMORY")  # Use memory for temp tables
        session.commit()
        lgr.debug("Database isolation level configured for concurrency")
    except Exception as e:
        lgr.warning(f"Could not configure database isolation level: {e}")


class ConcurrencyManager:
    """
    Manager class for handling database concurrency between API and RedCap sync.
    """
    
    @staticmethod
    def configure_api_session(session):
        """
        Configure database session for API operations with concurrency optimizations.
        
        Args:
            session: SQLAlchemy database session
        """
        isolation_level_read_committed(session)
    
    @staticmethod
    @retry_on_database_busy(max_retries=5, delay=0.1)
    def safe_api_operation(session, operation_func, *args, **kwargs):
        """
        Execute API database operation with retry logic and transaction safety.
        
        Args:
            session: Database session
            operation_func: Function to execute database operation
            *args, **kwargs: Arguments for operation function
            
        Returns:
            Result of operation function
            
        Raises:
            DatabaseBusyError: If database remains busy after retries
        """
        with safe_database_transaction(session) as tx_session:
            ConcurrencyManager.configure_api_session(tx_session)
            return operation_func(tx_session, *args, **kwargs)
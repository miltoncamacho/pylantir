import os
import logging
from sqlalchemy import create_engine, pool
from sqlalchemy.orm import sessionmaker
from .models import Base
from dotenv import load_dotenv
import threading

lgr = logging.getLogger(__name__)

load_dotenv()

def get_engine(db_path="worklist.db", echo=False):
    """
    Create a SQLAlchemy engine for an SQLite database.

    Args:
        db_path (str): The file path for the SQLite database.
        echo (bool): If True, SQLAlchemy will log all SQL queries.

    Returns:
        Engine: A SQLAlchemy engine connected to the encrypted SQLite database.
    """
    # Ensure the directory for the database exists
    db_dir = os.path.dirname(db_path)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir)

    # Construct the connection string
    connection_string = f"sqlite:///{db_path}"

    # Create the engine
    engine = create_engine(connection_string, echo=echo)
    return engine


def get_threadsafe_engine(db_path="worklist.db", echo=False):
    """
    Create a thread-safe SQLAlchemy engine with proper concurrency handling.
    
    Args:
        db_path (str): The file path for the SQLite database.
        echo (bool): If True, SQLAlchemy will log all SQL queries.
        
    Returns:
        Engine: A thread-safe SQLAlchemy engine for concurrent operations.
    """
    # Ensure the directory for the database exists
    db_dir = os.path.dirname(db_path)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir)

    # Construct connection string with SQLite-specific options for concurrency
    connection_string = f"sqlite:///{db_path}"
    
    # Create engine with SQLite concurrency optimizations
    engine = create_engine(
        connection_string,
        echo=echo,
        poolclass=pool.StaticPool,  # Thread-safe connection pooling
        pool_pre_ping=True,  # Validate connections before use
        connect_args={
            "check_same_thread": False,  # Allow multi-threading
            "timeout": 30,  # 30 second timeout for busy database
        },
        # SQLite-specific options for better concurrency
        execution_options={
            "isolation_level": "AUTOCOMMIT"  # Immediate commits for consistency
        }
    )
    return engine

# Load environment variables (you can use dotenv for more flexibility)
DB_PATH = os.getenv("DB_PATH", "worklist.db")  # Default: current directory
DB_PATH = os.path.expanduser(DB_PATH)
DB_ECHO = os.getenv("DB_ECHO", "False").lower() in ("true", "1")

lgr.info(f"Using worklist database path: {DB_PATH}")

# Create the engine
engine = get_engine(db_path=DB_PATH, echo=DB_ECHO)

# Create tables if they do not already exist
Base.metadata.create_all(engine)

# Session factories - separate engines for API and RedCap isolation
Session = sessionmaker(bind=engine)  # Sync session for RedCap compatibility

# Create thread-safe engine for API operations
api_engine = get_threadsafe_engine(db_path=DB_PATH, echo=DB_ECHO)
ApiSession = sessionmaker(
    bind=api_engine,
    expire_on_commit=False,
    autoflush=True,
    autocommit=False
)

def get_db():
    """
    FastAPI dependency to get sync database session (legacy compatibility).
    
    Yields:
        Session: SQLAlchemy database session
    """
    db = Session()
    try:
        yield db
    finally:
        db.close()


def get_api_db():
    """
    FastAPI dependency to get thread-safe database session for API operations.
    Isolated from RedCap sync to prevent interference.
    
    Yields:
        Session: Thread-safe SQLAlchemy database session
    """
    db = ApiSession()
    try:
        yield db
    finally:
        db.close()

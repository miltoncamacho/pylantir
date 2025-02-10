import os
import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from .models import Base
from dotenv import load_dotenv

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

# Load environment variables (you can use dotenv for more flexibility)
DB_PATH = os.getenv("DB_PATH", "worklist.db")  # Default: current directory
DB_ECHO = os.getenv("DB_ECHO", "False").lower() in ("true", "1")

# Create the engine
engine = get_engine(db_path=DB_PATH, echo=DB_ECHO)

# Create tables if they do not already exist
Base.metadata.create_all(engine)

# Session factory
Session = sessionmaker(bind=engine)

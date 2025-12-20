"""
Database module for JANATPMP.
Re-exports all operations from db.operations for backward compatibility.
"""

from db.operations import *

# Re-export connection utilities
from db.operations import get_connection, DB_PATH


def init_db():
    """Database is initialized via schema.sql - this is a no-op for compatibility."""
    pass

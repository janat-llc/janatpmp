"""
Data models for the inventory feature.
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

@dataclass
class Project:
    path: Path
    project_type: str
    detected_at: datetime
    id: Optional[int] = None

@dataclass
class FileItem:
    path: Path
    filename: str
    extension: str
    size_bytes: int
    modified_at: datetime
    indexed_at: datetime
    project_id: Optional[int] = None
    id: Optional[int] = None

@dataclass
class ScanRun:
    root_path: Path
    started_at: datetime
    completed_at: Optional[datetime] = None
    file_count: int = 0
    error_count: int = 0
    id: Optional[int] = None

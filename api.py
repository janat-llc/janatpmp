"""
JANATPMP API Layer - All functions exposed via gr.api()
Import and re-export all API-compatible functions.
"""
from database import (
    start_scan_run, complete_scan_run, save_file, save_project,
    get_files, get_projects, get_scan_history, search_files
)
from features.inventory.scanner import scan_directory

# These will be wrapped with gr.api() in app.py
__all__ = [
    'scan_directory',
    'start_scan_run', 'complete_scan_run', 
    'save_file', 'save_project',
    'get_files', 'get_projects', 'get_scan_history', 'search_files'
]

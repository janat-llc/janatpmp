import sqlite3
from pathlib import Path
from contextlib import contextmanager
from datetime import datetime

DB_PATH = Path("janatpmp.db")

def init_db():
    """Initialize the SQLite database schema."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Projects table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                path TEXT NOT NULL UNIQUE,
                project_type TEXT,
                detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Files table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER,
                path TEXT NOT NULL,
                filename TEXT NOT NULL,
                extension TEXT,
                size_bytes INTEGER,
                modified_at TIMESTAMP,
                indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (project_id) REFERENCES projects (id)
            )
        ''')

        # Scan runs table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS scan_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                root_path TEXT NOT NULL,
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                file_count INTEGER DEFAULT 0,
                error_count INTEGER DEFAULT 0
            )
        ''')
        conn.commit()

@contextmanager
def get_db_connection(db_path_str: str | None = None):
    """Context manager for database connections."""
    path = Path(db_path_str) if db_path_str else DB_PATH
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

# API-Compatible Functions

def start_scan_run(db_path: str, root_path: str) -> dict:
    """Start a scan run, return {scan_run_id, started_at}"""
    started_at = datetime.now().isoformat()
    try:
        with get_db_connection(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO scan_runs (root_path, started_at) VALUES (?, ?)",
                (root_path, started_at)
            )
            conn.commit()
            return {
                "scan_run_id": cursor.lastrowid, 
                "started_at": started_at
            }
    except Exception as e:
        print(f"Error starting scan run: {e}")
        return {"error": str(e)}

def complete_scan_run(db_path: str, scan_run_id: int, file_count: int, error_count: int) -> dict:
    """Complete a scan run, return {scan_run_id, completed_at}"""
    completed_at = datetime.now().isoformat()
    try:
        with get_db_connection(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE scan_runs 
                SET completed_at = ?, file_count = ?, error_count = ? 
                WHERE id = ?
                """,
                (completed_at, file_count, error_count, scan_run_id)
            )
            conn.commit()
            return {
                "scan_run_id": scan_run_id, 
                "completed_at": completed_at
            }
    except Exception as e:
        print(f"Error completing scan run: {e}")
        return {"error": str(e)}

def save_file(db_path: str, scan_run_id: int, file_data: dict) -> dict:
    """Save single file record, return {file_id}"""
    # Note: scan_run_id is unused in the current files table schema, but kept in signature as requested/implied for context
    try:
        with get_db_connection(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO files (project_id, path, filename, extension, size_bytes, modified_at, indexed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    file_data.get('project_id'),
                    file_data['path'],
                    file_data['filename'],
                    file_data['extension'],
                    file_data['size_bytes'],
                    file_data['modified_at'],
                    file_data.get('indexed_at', datetime.now().isoformat())
                )
            )
            conn.commit()
            return {"file_id": cursor.lastrowid}
    except Exception as e:
        # Don't crash on individual file save errors
        return {"error": str(e), "path": file_data.get('path')}

def save_project(db_path: str, project_data: dict) -> dict:
    """Save project root, return {project_id}"""
    try:
        with get_db_connection(db_path) as conn:
            cursor = conn.cursor()
            # Use INSERT OR IGNORE or handle unique constraint
            cursor.execute(
                """
                INSERT INTO projects (path, project_type, detected_at)
                VALUES (?, ?, ?)
                ON CONFLICT(path) DO UPDATE SET
                project_type=excluded.project_type,
                detected_at=excluded.detected_at
                """,
                (
                    project_data['path'],
                    project_data['project_type'],
                    project_data.get('detected_at', datetime.now().isoformat())
                )
            )
            conn.commit()
            
            # If updated/inserted, get the ID. 
            if cursor.lastrowid:
                return {"project_id": cursor.lastrowid}
            else:
                # If updated, lastrowid might not be set in some sqlite versions/configs, so fetch it
                cursor.execute("SELECT id FROM projects WHERE path = ?", (project_data['path'],))
                row = cursor.fetchone()
                return {"project_id": row['id'] if row else None}
    except Exception as e:
        return {"error": str(e)}

def get_files(db_path: str, extension: str | None = None, limit: int = 100) -> list[dict]:
    """Query files, return list of file dicts"""
    try:
        with get_db_connection(db_path) as conn:
            cursor = conn.cursor()
            query = "SELECT * FROM files"
            params = []
            
            if extension:
                query += " WHERE extension = ?"
                params.append(extension)
            
            query += " ORDER BY id DESC LIMIT ?"
            params.append(limit)
            
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        return [{"error": str(e)}]

def get_projects(db_path: str) -> list[dict]:
    """Get all detected projects, return list of project dicts"""
    try:
        with get_db_connection(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM projects ORDER BY path")
            return [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        return [{"error": str(e)}]

def get_scan_history(db_path: str, limit: int = 10) -> list[dict]:
    """Get recent scans, return list of scan dicts"""
    try:
        with get_db_connection(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM scan_runs ORDER BY started_at DESC LIMIT ?", (limit,))
            return [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        return [{"error": str(e)}]

def search_files(db_path: str, query: str, limit: int = 50) -> list[dict]:
    """Search files by name/path, return list of file dicts"""
    try:
        with get_db_connection(db_path) as conn:
            cursor = conn.cursor()
            sql_query = "SELECT * FROM files WHERE filename LIKE ? OR path LIKE ? LIMIT ?"
            like_query = f"%{query}%"
            cursor.execute(sql_query, (like_query, like_query, limit))
            return [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        return [{"error": str(e)}]

if __name__ == "__main__":
    init_db()
    print(f"Database initialized at {DB_PATH.absolute()}")

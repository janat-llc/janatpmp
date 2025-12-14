import os
from pathlib import Path
from datetime import datetime
from .config import ScanConfig
import fnmatch

def scan_directory(root_path: str, config: dict | None = None) -> dict:
    """
    Scan directory and return results. API-compatible.
    
    Args:
        root_path: Absolute path to scan (string for API compatibility)
        config: Optional config overrides as dict
        
    Returns:
        dict with keys: files, projects, stats, errors
    """
    path_root = Path(root_path)
    
    # Initialize config
    scan_config = ScanConfig()
    if config:
        if 'include_extensions' in config:
            scan_config.include_extensions = config['include_extensions']
        if 'skip_directories' in config:
            scan_config.skip_directories = config['skip_directories']
        if 'project_markers' in config:
            scan_config.project_markers = config['project_markers']
            
    results = {
        "files": [],
        "projects": [],
        "stats": {
            "total_files": 0,
            "total_size_bytes": 0,
            "projects_found": 0,
            "scan_started": datetime.now().isoformat(),
        },
        "errors": []
    }
    
    print(f"Starting scan of: {root_path}")
    
    try:
        for root, dirs, files in os.walk(path_root):
            # Modify dirs in-place to skip ignored directories
            dirs[:] = [d for d in dirs if d not in scan_config.skip_directories]
            
            root_p = Path(root)
            
            # Check for project markers
            project_type = None
            for marker, ptype in scan_config.project_markers.items():
                # Check explicit matches and glob patterns
                if any(fnmatch.fnmatch(f, marker) for f in files):
                    project_type = ptype
                    break
            
            if project_type:
                results["projects"].append({
                    "path": str(root_p),
                    "project_type": project_type,
                    "detected_at": datetime.now().isoformat()
                })
                results["stats"]["projects_found"] += 1

            for filename in files:
                file_path = root_p / filename
                suffix = file_path.suffix.lower()
                
                if suffix in scan_config.include_extensions:
                    try:
                        stat = file_path.stat()
                        file_data = {
                            "path": str(file_path),
                            "filename": filename,
                            "extension": suffix,
                            "size_bytes": stat.st_size,
                            "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                            "indexed_at": datetime.now().isoformat()
                        }
                        results["files"].append(file_data)
                        results["stats"]["total_files"] += 1
                        results["stats"]["total_size_bytes"] += stat.st_size
                    except OSError as e:
                        results["errors"].append({
                            "path": str(file_path),
                            "error": str(e)
                        })

    except Exception as e:
        results["errors"].append({
            "path": root_path,
            "error": f"Fatal scan error: {str(e)}"
        })
        
    results["stats"]["scan_completed"] = datetime.now().isoformat()
    print(f"Scan complete. Found {results['stats']['total_files']} files, {results['stats']['projects_found']} projects.")
    
    return results

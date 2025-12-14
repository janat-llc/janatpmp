from dataclasses import dataclass, field

@dataclass
class ScanConfig:
    include_extensions: list[str] = field(default_factory=lambda: [
        '.py', '.md', '.html', '.js', '.ts', '.json', '.yaml', '.yml'
    ])
    
    skip_directories: list[str] = field(default_factory=lambda: [
        '__pycache__', 'node_modules', '.git', 'venv', '.venv', 
        'bin', 'obj', '.idea', '.vscode', 'dist', 'build'
    ])
    
    project_markers: dict[str, str] = field(default_factory=lambda: {
        'pyproject.toml': 'python',
        'setup.py': 'python', 
        'package.json': 'node',
        '*.csproj': 'csharp',
        '*.sln': 'csharp'
    })

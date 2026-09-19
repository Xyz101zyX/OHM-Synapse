import os
import sys
import subprocess
import shutil
from pathlib import Path

ROOT = Path(__file__).parent


GITIGNORE = """# Python
__pycache__/
*.py[cod]
*.egg-info/
.eggs/
build/
dist/
.pytest_cache/
.mypy_cache/
.coverage
htmlcov/

# Virtual environments
venv/
env/
.venv/

# OHM data
ohm_data/
.ohm/
*.pem
auth.json
sessions.json

# Cleanup artifacts
_backups/

# OS
.DS_Store
Thumbs.db

# IDE
.vscode/
.idea/
*.swp

# Secrets
.pypirc
*.token
"""


def run(cmd, check=True):
    print(f"$ {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
    if result.stdout.strip():
        print(result.stdout.strip())
    if result.stderr.strip():
        print(result.stderr.strip())
    if check and result.returncode != 0:
        raise RuntimeError(f"command failed: {cmd}")
    return result


def is_git_installed():
    try:
        subprocess.run(["git", "--version"], capture_output=True, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def main():
    print("=" * 60)
    print("OHM-SYNAPSE — GIT PRIVATE SETUP")
    print("=" * 60)
    print()

    if not is_git_installed():
        print("[FAIL] git is not installed")
        print("install from: https://git-scm.com/downloads")
        return 1

    print("[ok] git is installed")
    print()

    gitignore_path = ROOT / ".gitignore"
    if gitignore_path.exists():
        print(f"[skip] .gitignore already exists")
    else:
        gitignore_path.write_text(GITIGNORE, encoding="utf-8")
        print(f"[ok] created .gitignore")

    git_dir = ROOT / ".git"
    if git_dir.exists():
        print(f"[skip] git repository already initialized")
    else:
        run(["git", "init"])
        run(["git", "branch", "-M", "main"])
        print(f"[ok] initialized git repository")

    print()
    print("-- repository status --")
    run(["git", "status", "--short"], check=False)

    print()
    print("=" * 60)
    print("NEXT STEPS")
    print("=" * 60)
    print()
    print("The repository is local and private. To configure your identity:")
    print()
    print('  git config user.email "you@example.com"')
    print('  git config user.name "Your Name"')
    print()
    print("To make your first commit:")
    print()
    print("  git add .")
    print('  git commit -m "Initial commit: OHM-Synapse v0.0.1"')
    print()
    print("To add a remote (GitHub private, GitLab, etc.):")
    print()
    print("  git remote add origin <url>")
    print("  git push -u origin main")
    print()
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
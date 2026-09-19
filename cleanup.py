import os
import sys
import shutil
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).parent
BACKUPS_DIR = ROOT / "_backups"

PATTERNS_TO_MOVE = [
    "*.bak", "*.bak2", "*.bak3", "*.bak4", "*.bak5",
    "*.bak_*", "*.bak_mypy*", "*.bak_revoke", "*.bak_auth",
    "*.bak_parser", "*.bak_llm", "*.bak_scope*", "*.bak_thr",
    "*.bak_v4", "*.bak_v5", "*.bak_v6", "*.bak_mh2", "*.bak_iso",
    "*.bak_emb", "*.bak_cache", "*.bak_fix8", "*.bak_safe",
    "*.bak_minimal", "*.bak_modular", "*.bak_fixmod",
    "*.bak_fib", "*.bak_ascii", "*.bak_episodes", "*.bak_v3",
    "*.bak_scope_v2", "*.bak_scope_v3",
]

SCRIPTS_TO_MOVE = [
    "apply_*.py",
    "fix_*.py",
    "mypy_*.py",
    "recover_*.py",
    "patch_*.py",
    "clean_all_ascii.py",
    "find_good_backup.py",
    "modularize.py",
    "verify_modularize.py",
]


def backup_current():
    """Snapshot the entire project into _backups/before_cleanup/."""
    dest = BACKUPS_DIR / "before_cleanup"
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True, exist_ok=True)
    for f in ROOT.iterdir():
        if f.is_dir() and f.name in ("_backups", "ohm_data", "__pycache__", ".git"):
            continue
        if f.name == "cleanup.py":
            continue
        if f.is_file():
            shutil.copy2(f, dest / f.name)
        elif f.is_dir() and f.name == "ohm":
            shutil.copytree(f, dest / "ohm", ignore=shutil.ignore_patterns("__pycache__"))
    print(f"[ok] backup snapshot saved to {dest}")


def collect_backups():
    found = []
    for pattern in PATTERNS_TO_MOVE:
        for f in ROOT.rglob(pattern):
            if not f.is_file():
                continue
            if "_backups" in f.parts:
                continue
            found.append(f)
    return sorted(set(found))


def collect_scripts():
    found = []
    for pattern in SCRIPTS_TO_MOVE:
        for f in ROOT.glob(pattern):
            if not f.is_file():
                continue
            if f.name == "cleanup.py":
                continue
            found.append(f)
    return sorted(set(found))


def move_to_backups(files, subfolder):
    dest = BACKUPS_DIR / subfolder
    dest.mkdir(parents=True, exist_ok=True)
    n = 0
    for f in files:
        try:
            rel = f.relative_to(ROOT)
        except ValueError:
            rel = Path(f.name)
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            target.unlink()
        shutil.move(str(f), str(target))
        n += 1
    return n


def report(files, label):
    print(f"\n-- {label}: {len(files)} files --")
    for f in files[:15]:
        print(f"  {f.relative_to(ROOT)}")
    if len(files) > 15:
        print(f"  ... and {len(files) - 15} more")


def main():
    print("=" * 60)
    print("OHM-SYNAPSE CLEANUP")
    print("=" * 60)
    print()
    print("This will:")
    print("  1. Snapshot the whole project to _backups/before_cleanup/")
    print("  2. Move all .bak_* backup files to _backups/")
    print("  3. Move all fix_*.py / apply_*.py / mypy_*.py to _backups/")
    print()
    print("Nothing is deleted. Everything is recoverable.")
    print()

    ans = input("Continue? [y/N] ").strip().lower()
    if ans != "y":
        print("aborted")
        return 1

    print()
    backup_current()

    backups = collect_backups()
    scripts = collect_scripts()

    report(backups, "backup files found")
    report(scripts, "one-shot scripts found")

    n_backups = move_to_backups(backups, "old_backups")
    n_scripts = move_to_backups(scripts, "old_scripts")

    print()
    print("=" * 60)
    print(f"moved {n_backups} backup files")
    print(f"moved {n_scripts} one-shot scripts")
    print(f"backup location: {BACKUPS_DIR}")
    print("=" * 60)
    print()
    print("If anything breaks, copy files back from _backups/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
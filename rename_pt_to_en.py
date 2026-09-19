"""Rename Portuguese-suffixed artifacts to English equivalents."""

from __future__ import annotations

import pathlib

ROOT = pathlib.Path(".")
RENAMES = {
    "manual_fase9.py": "manual_phase9.py",
    "ohm_synapse.py.pre_fase5": "ohm_synapse.py.pre_phase5",
    "ohm_synapse.py.stable_fase5": "ohm_synapse.py.stable_phase5",
    "ohm_synapse.py.before_subject2": "ohm_synapse.py.before_subject_v2",
}


def main():
    for src, dst in RENAMES.items():
        p = ROOT / src
        if p.exists():
            target = ROOT / dst
            if target.exists():
                print(f"  skip (exists): {dst}")
                continue
            p.rename(target)
            print(f"  renamed: {src} -> {dst}")


if __name__ == "__main__":
    main()
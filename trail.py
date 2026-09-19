"""Show recorded runs from .trail."""

from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent
TRAIL = ROOT / ".trail"
LINE_RE = re.compile(r"checked=(\d+) ok=(\d+) failed=(\d+)")


def summarize(log):
    checked = ok = failed = 0
    for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
        m = LINE_RE.search(line)
        if m:
            checked += int(m.group(1))
            ok += int(m.group(2))
            failed += int(m.group(3))
    return f"TOTAL checked={checked} ok={ok} failed={failed}"


def main():
    if not TRAIL.is_dir():
        print("no trail yet")
        return 0

    pattern = sys.argv[1] if len(sys.argv) > 1 else "*"
    logs = sorted(TRAIL.glob(f"{pattern}_*.log"))

    if not logs:
        print(f"no logs matching {pattern}")
        return 0

    for log in logs:
        parts = log.stem.split("_")
        stage = parts[0]
        stamp = "_".join(parts[1:])
        print(f"{stamp}  {stage:<8}  {summarize(log)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
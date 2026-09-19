"""FASE 2 runner — per-file isolation, unified format, trail."""

from __future__ import annotations

import argparse
import datetime as dt
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent
TRAIL = ROOT / ".trail"

RAN_RE = re.compile(r"^Ran (\d+) tests? in", re.MULTILINE)
OK_RE = re.compile(r"^OK(?:\s|$)", re.MULTILINE)
FAIL_RE = re.compile(r"^FAILED\s*\(([^)]*)\)", re.MULTILINE)


def discover():
    return sorted(
        p for p in ROOT.glob("test_*.py")
        if p.is_file() and ".bak" not in p.name
    )


def run_one(path):
    proc = subprocess.run(
        [sys.executable, "-m", "unittest", path.stem, "-v"],
        cwd=ROOT, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    ran = RAN_RE.search(out)
    total = int(ran.group(1)) if ran else 0
    if OK_RE.search(out):
        failed = 0
    elif (m := FAIL_RE.search(out)):
        nums = re.findall(r"=(\d+)", m.group(1))
        failed = sum(int(n) for n in nums) if nums else total
    else:
        failed = total or 1
    return max(total - failed, 0), failed, out


def fmt(name, ok, bad):
    return f"[{name}] checked={ok + bad} ok={ok} failed={bad}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--skip", default="")
    args = ap.parse_args()

    only = {s.strip() for s in args.only.split(",") if s.strip()}
    skip = {s.strip() for s in args.skip.split(",") if s.strip()}

    files = discover()
    if only:
        files = [f for f in files if f.stem in only]
    if skip:
        files = [f for f in files if f.stem not in skip]

    if not files:
        print("no test files found")
        return 1

    TRAIL.mkdir(exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = TRAIL / f"fase2_{stamp}.log"

    total_ok = total_bad = 0
    failed_stems = []

    print(f"# run_tests - FASE 2 - {ROOT}\n")

    with log_path.open("w", encoding="utf-8") as log:
        for path in files:
            ok, bad, out = run_one(path)
            line = fmt(path.stem, ok, bad)
            print(f"  {line}")
            log.write(f"### {path.stem} — {line}\n")
            log.write(out)
            log.write("\n")
            total_ok += ok
            total_bad += bad
            if bad:
                failed_stems.append(path.stem)

    print()
    print(f"TOTAL checked={total_ok + total_bad} ok={total_ok} failed={total_bad}")
    print(f"log: {log_path.relative_to(ROOT)}")
    if failed_stems:
        print(f"failed files: {', '.join(failed_stems)}")

    return 1 if total_bad else 0


if __name__ == "__main__":
    sys.exit(main())
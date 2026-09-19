"""Record a manual phase result into .trail/."""

from __future__ import annotations

import argparse
import datetime as dt
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent
TRAIL = ROOT / ".trail"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("phase")
    ap.add_argument("checked", type=int)
    ap.add_argument("ok", type=int)
    ap.add_argument("failed", type=int)
    ap.add_argument("--note", default="")
    args = ap.parse_args()

    TRAIL.mkdir(exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    line = f"TOTAL checked={args.checked} ok={args.ok} failed={args.failed}"
    log = TRAIL / f"{args.phase}_{stamp}.log"
    body = f"### {args.phase} - {line}\n"
    if args.note:
        body += f"note: {args.note}\n"
    log.write_text(body, encoding="utf-8")
    print(f"stamped: {log.relative_to(ROOT)}")
    print(line)


if __name__ == "__main__":
    main()
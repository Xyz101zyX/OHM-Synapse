import ast
import pathlib
import sys

root = pathlib.Path(".")
files = sorted(
    p for p in root.rglob("*.py")
    if "__pycache__" not in p.parts
)

ok = bad = 0
for f in files:
    try:
        ast.parse(f.read_text(encoding="utf-8"), filename=str(f))
        ok += 1
    except SyntaxError as e:
        bad += 1
        print(f"[FAIL] {f}:{e.lineno}:{e.offset}: {e.msg}")

print(f"checked={ok + bad} ok={ok} failed={bad}")
sys.exit(1 if bad else 0)
"""Fix benchmark_multi_model.py: proper timeout propagation."""

import ast
import pathlib
import sys

TARGET = pathlib.Path("benchmark_multi_model.py")
src = TARGET.read_text(encoding="utf-8")

# ---------------------------------------------------------------- patch 1
OLD = "def run_model(model, cases):"
NEW = "def run_model(model, cases, timeout=90):"
if src.count(OLD) != 1:
    print(f"[abort] 'def run_model' count={src.count(OLD)}")
    sys.exit(1)
src = src.replace(OLD, NEW, 1)
print("[patch 1] run_model accepts timeout")

# ---------------------------------------------------------------- patch 2
OLD = "        brain = make_brain(model)"
NEW = "        brain = make_brain(model, timeout=timeout)"
if src.count(OLD) != 1:
    print(f"[abort] 'brain = make_brain(model)' count={src.count(OLD)}")
    sys.exit(1)
src = src.replace(OLD, NEW, 1)
print("[patch 2] make_brain receives timeout")

# ---------------------------------------------------------------- patch 3
OLD = "            result = run_model(model, cases)"
NEW = ("            result = run_model(model, cases,\n"
       "                               timeout=args.timeout_per_case)")
if src.count(OLD) != 1:
    print(f"[abort] 'result = run_model(model, cases)' count={src.count(OLD)}")
    sys.exit(1)
src = src.replace(OLD, NEW, 1)
print("[patch 3] call site passes timeout")

try:
    ast.parse(src)
except SyntaxError as e:
    print(f"[abort] syntax error: {e}")
    sys.exit(1)

TARGET.write_text(src, encoding="utf-8")
print("[ok] wrote benchmark_multi_model.py")
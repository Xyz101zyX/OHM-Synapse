"""Add per-phase progress output to verify_all.py."""

import ast
import pathlib
import sys

TARGET = pathlib.Path("verify_all.py")
src = TARGET.read_text(encoding="utf-8")

if "print(f\"  --> {name} ...\"" in src:
    print("[abort] already patched")
    sys.exit(1)

OLD = '''    for name in phases:
        r = PHASES[name]()'''

NEW = '''    for name in phases:
        print(f"  --> {name} ...", end=" ", flush=True)
        r = PHASES[name]()'''

if OLD not in src:
    print("[abort] loop not found verbatim")
    sys.exit(1)

src = src.replace(OLD, NEW, 1)

try:
    ast.parse(src)
except SyntaxError as e:
    print(f"[abort] syntax error: {e}")
    sys.exit(1)

TARGET.write_text(src, encoding="utf-8")
print("[ok] wrote verify_all.py")	
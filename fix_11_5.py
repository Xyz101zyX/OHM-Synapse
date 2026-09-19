import ast
import pathlib

p = pathlib.Path("run_peer.py")
src = p.read_text(encoding="utf-8")

old = "        return self.auth.validate_session(token)"
new = "        self.auth._load()\n        return self.auth.validate_session(token)"

if src.count(old) != 1:
    raise SystemExit(f"anchor count={src.count(old)}")

patched = src.replace(old, new, 1)

try:
    ast.parse(patched)
except SyntaxError as e:
    raise SystemExit(f"syntax error, not writing: {e}")

pathlib.Path("run_peer.py").write_text(patched, encoding="utf-8")
print("patched run_peer.py: _check_auth reloads sessions from disk")
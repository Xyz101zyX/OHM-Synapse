import ast
import pathlib

src = pathlib.Path("run_peer.py").read_text(encoding="utf-8")
lines = src.split("\n")

http_starts = [i for i, l in enumerate(lines) if l.startswith("def run_http")]
main_starts = [i for i, l in enumerate(lines) if l.startswith("if __name__")]

if not http_starts or not main_starts:
    raise SystemExit(f"markers missing: run_http={len(http_starts)} main={len(main_starts)}")

header = lines[:http_starts[0]]
last_block = lines[http_starts[-1]:main_starts[0]]
tail = lines[main_starts[0]:]

out = "\n".join(header + [""] + last_block + [""] + tail) + "\n"

try:
    ast.parse(out)
except SyntaxError as e:
    raise SystemExit(f"refusing to write: line {e.lineno}: {e.msg}")

pathlib.Path("run_peer_clean.py").write_text(out, encoding="utf-8")
print(f"input  {len(lines)}")
print(f"header {len(header)}  (1..{http_starts[0]})")
print(f"block  {len(last_block)}  ({http_starts[-1]+1}..{main_starts[0]})")
print(f"tail   {len(tail)}  ({main_starts[0]+1}..{len(lines)})")
print(f"output {len(out.splitlines())}  -> run_peer_clean.py")
import pathlib

p = pathlib.Path("run_peer.py")
lines = p.read_text(encoding="utf-8").splitlines(keepends=False)

http_starts = [i for i, l in enumerate(lines) if l.lstrip().startswith("def run_http")]
main_starts = [i for i, l in enumerate(lines) if l.lstrip().startswith("if __name__")]

if not http_starts or not main_starts:
    raise SystemExit("markers not found")

header = lines[:http_starts[0]]
last_block = lines[http_starts[-1]:main_starts[0]]
tail = lines[main_starts[0]:]

out = header + [""] + last_block + [""] + tail
pathlib.Path("run_peer_clean.py").write_text("\n".join(out) + "\n", encoding="utf-8")

print(f"input       {len(lines):>5}")
print(f"header      {len(header):>5}  (1..{http_starts[0]})")
print(f"last_block  {len(last_block):>5}  ({http_starts[-1]+1}..{main_starts[0]})")
print(f"tail        {len(tail):>5}  ({main_starts[0]+1}..{len(lines)})")
print(f"output      {len(out):>5}")
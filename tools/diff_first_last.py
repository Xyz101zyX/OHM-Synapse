import difflib
import pathlib

lines = pathlib.Path("run_peer.py").read_text(encoding="utf-8").splitlines()
starts = [i for i, l in enumerate(lines) if l.startswith("def run_http")]

first = lines[starts[0]:starts[1]]
last = lines[starts[-1]:[i for i, l in enumerate(lines) if l.startswith("if __name__")][0]]

print(f"first block: {len(first)} lines")
print(f"last  block: {len(last)} lines\n")

for line in difflib.unified_diff(first, last, lineterm="", n=1):
    print(line)
import difflib
import pathlib

lines = pathlib.Path("run_peer.py").read_text(encoding="utf-8").splitlines()

starts = [i for i, l in enumerate(lines) if l.startswith("def run_http")]
first, second = starts[0], starts[1]

block1 = lines[first:second]
block2 = lines[second:starts[2]]

print(f"block1: lines {first + 1}-{second}  ({len(block1)} lines)")
print(f"block2: lines {second + 1}-{starts[2]}  ({len(block2)} lines)\n")

for line in difflib.unified_diff(block1, block2, lineterm="", n=1):
    print(line)
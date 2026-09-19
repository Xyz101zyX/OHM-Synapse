import ast
import pathlib

p = pathlib.Path("check_all.py")
src = p.read_text(encoding="utf-8")
lines = src.splitlines()

# 1) remove the stray module-level block that references total_ok
drop_keys = ("total_line =", 'print(total_line)', 'TRAIL.mkdir(', 'stamp =', 'log.write_text(', 'log = TRAIL', 'print(f"log:')
keep = []
for l in lines:
    if any(k in l for k in drop_keys) and not l.startswith("    "):
        continue
    keep.append(l)
src = "\n".join(keep) + "\n"

# 2) re-insert the trail block inside main(), after the TOTAL print
anchor = '    print(f"TOTAL checked={total_ok + total_bad} ok={total_ok} failed={total_bad}")'
if anchor not in src:
    raise SystemExit("anchor 'print(TOTAL...)' not found inside main()")

insert = '''
    TRAIL.mkdir(exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    log = TRAIL / f"fase3_{stamp}.log"
    log.write_text(f"### fase3 - {total_line}\\n", encoding="utf-8")
    print(f"log: {log.relative_to(ROOT)}")
'''
# need total_line defined inside main too
src = src.replace(
    anchor,
    '    total_line = f"TOTAL checked={total_ok + total_bad} ok={total_ok} failed={total_bad}"\n'
    '    print(total_line)\n'
    + insert,
    1,
)
print("rebuilt main() TOTAL block")

# 3) ensure import datetime as dt exists once at top
if "import datetime as dt" not in src:
    src = src.replace("import ast\n", "import ast\nimport datetime as dt\n", 1)
    print("added import datetime as dt")

# 4) ensure TRAIL defined after ROOT
if "TRAIL = ROOT" not in src:
    src = src.replace('PKG_DIR = ROOT / PACKAGE', 'PKG_DIR = ROOT / PACKAGE\nTRAIL = ROOT / ".trail"', 1)
    print("added TRAIL")

try:
    ast.parse(src)
except SyntaxError as e:
    raise SystemExit(f"syntax error, not writing: {e}")

p.write_text(src, encoding="utf-8")
print("done")
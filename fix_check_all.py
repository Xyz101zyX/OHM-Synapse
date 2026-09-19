import pathlib

p = pathlib.Path("check_all.py")
lines = p.read_text(encoding="utf-8").splitlines()

# find indices of the offending lines
idx_root = next((i for i, l in enumerate(lines) if l.startswith("ROOT = ")), None)
idx_trail = next((i for i, l in enumerate(lines) if l.startswith("TRAIL = ")), None)
idx_dt = next((i for i, l in enumerate(lines) if l.strip() == "import datetime as dt"), None)

if idx_root is None:
    raise SystemExit("ROOT not found")
if idx_trail is None:
    raise SystemExit("TRAIL not found")

if idx_trail < idx_root:
    trail_line = lines.pop(idx_trail)
    if idx_dt is not None and idx_dt > idx_trail:
        idx_dt -= 1
    idx_root = next(i for i, l in enumerate(lines) if l.startswith("ROOT = "))
    lines.insert(idx_root + 1, trail_line)
    print("moved TRAIL below ROOT")

if idx_dt is not None:
    dt_line = lines.pop(idx_dt)
    insert_at = next(i for i, l in enumerate(lines) if l.startswith("import ")) 
    last_import = max(i for i, l in enumerate(lines) if l.startswith("import ") or l.startswith("from "))
    lines.insert(last_import + 1, dt_line)
    print("moved datetime import")

p.write_text("\n".join(lines) + "\n", encoding="utf-8")
print("done")
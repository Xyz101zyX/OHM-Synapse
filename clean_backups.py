import pathlib

keep = {
    "ohm_synapse.py.stable_fase5",   # âncora FASE 5
    "check_all.py.bak",              # antes do fix do trail
}

root = pathlib.Path(".")
removed = []
for p in root.glob("*.bak*"):
    if p.name in keep:
        continue
    p.unlink()
    removed.append(p.name)

for p in root.glob("*.pre_*"):
    p.unlink()
    removed.append(p.name)

for p in root.glob("*.before_*"):
    p.unlink()
    removed.append(p.name)

# remove only the stale stable file
stale = root / "ohm_synapse.py.stable_fase5_with_subject_match"
if stale.exists():
    stale.unlink()
    removed.append(stale.name)

for name in sorted(removed):
    print(f"  removed: {name}")
print(f"total: {len(removed)}")
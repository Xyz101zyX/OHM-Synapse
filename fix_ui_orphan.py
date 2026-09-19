import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).parent
UI = ROOT / "ohm_ui.py"


def read_norm(p):
    return p.read_bytes().decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")


def write_norm(p, t):
    p.write_bytes(t.encode("utf-8"))


def main():
    shutil.copy2(UI, UI.with_suffix(".py.bak_orphan"))
    print(f"backup: {UI.name}.bak_orphan")

    lines = read_norm(UI).split("\n")
    removed = []

    # Remove specific orphaned lines
    targets = [
        '    if auth_verify is not None:',
        '        _UI_AUTH_VERIFY["fn"] = auth_verify',
        '_UI_AUTH_VERIFY = {"fn": None}',
    ]

    new_lines = []
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if any(stripped == t.strip() for t in targets):
            removed.append((i, line))
            continue
        new_lines.append(line)

    if not removed:
        print("[skip] no orphaned lines found")
        return

    write_norm(UI, "\n".join(new_lines))

    print(f"[ok]   removed {len(removed)} orphaned lines:")
    for n, line in removed:
        print(f"       {n}: {line.strip()}")

    # Verify the signature is now clean
    final = read_norm(UI)
    if "auth_verify" in final:
        print("[WARN] 'auth_verify' still appears somewhere else:")
        for i, l in enumerate(final.split("\n"), 1):
            if "auth_verify" in l:
                print(f"       {i}: {l}")

    if "_UI_AUTH_VERIFY" in final:
        print("[WARN] '_UI_AUTH_VERIFY' still appears:")
        for i, l in enumerate(final.split("\n"), 1):
            if "_UI_AUTH_VERIFY" in l:
                print(f"       {i}: {l}")

    try:
        import py_compile
        py_compile.compile(str(UI), doraise=True)
        print("[ok]   py_compile clean")
    except Exception as e:
        print(f"[FAIL] py_compile: {e}")
        shutil.copy2(UI.with_suffix(".py.bak_orphan"), UI)
        sys.exit(1)


if __name__ == "__main__":
    main()
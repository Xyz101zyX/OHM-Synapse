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
    shutil.copy2(UI, UI.with_suffix(".py.bak_uifn"))
    print(f"backup: {UI.name}.bak_uifn")

    text = read_norm(UI)

    # Candidate old signatures (in order of preference)
    candidates = [
        "def build_ui(ohm_instance, peer_name: str, own_port: int):",
        "def build_ui(ohm_instance, peer_name, own_port):",
        "def build_ui(ohm_instance, peer_name: str, own_port: int, auth_verify=None):",
    ]

    for old in candidates:
        if old in text:
            print(f"[info] found signature: {old}")
            if "auth_verify=None" in old:
                print("[skip] already has auth_verify")
                return
            new = old[:-2] + ", auth_verify=None):"
            text = text.replace(old, new, 1)
            write_norm(UI, text)
            print(f"[ok]   patched to: {new}")
            break
    else:
        print("[FAIL] build_ui signature not found in any known form")
        print("       first 20 lines of ohm_ui.py:")
        for i, line in enumerate(text.split("\n")[:20], 1):
            print(f"  {i}: {line}")
        sys.exit(1)

    # Verify
    final = read_norm(UI)
    if "auth_verify=None" not in final:
        print("[FAIL] signature not persisted")
        shutil.copy2(UI.with_suffix(".py.bak_uifn"), UI)
        sys.exit(1)

    # Verify py_compile
    try:
        import py_compile
        py_compile.compile(str(UI), doraise=True)
        print("[ok]   py_compile clean")
    except Exception as e:
        print(f"[FAIL] py_compile: {e}")
        shutil.copy2(UI.with_suffix(".py.bak_uifn"), UI)
        sys.exit(1)


if __name__ == "__main__":
    main()
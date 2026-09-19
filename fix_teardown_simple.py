import shutil
from pathlib import Path

ROOT = Path(__file__).parent
TARGET = ROOT / "test_fase15.py"


def read_norm(p):
    return p.read_bytes().decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")


def write_norm(p, t):
    p.write_bytes(t.encode("utf-8"))


def main():
    shutil.copy2(TARGET, TARGET.with_suffix(".py.bak_tear2"))
    print(f"backup: {TARGET.name}.bak_tear2")

    text = read_norm(TARGET)
    orig = text

    old = "if self.peer_proc and self.peer_proc.poll() is None:"
    new = "if getattr(self, 'peer_proc', None) and self.peer_proc.poll() is None:"

    if new in text:
        print("[skip] already patched")
        return

    count = text.count(old)
    if count == 0:
        print(f"[FAIL] anchor not found ({count} matches)")
        return

    text = text.replace(old, new)
    write_norm(TARGET, text)
    print(f"[ok]   replaced {count} occurrences")

    try:
        import py_compile
        py_compile.compile(str(TARGET), doraise=True)
        print("[ok]   py_compile clean")
    except Exception as e:
        print(f"[FAIL] py_compile: {e}")
        shutil.copy2(TARGET.with_suffix(".py.bak_tear2"), TARGET)


if __name__ == "__main__":
    main()
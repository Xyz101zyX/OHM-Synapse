import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).parent
TARGET = ROOT / "test_fase15.py"


def read_norm(p):
    return p.read_bytes().decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")


def write_norm(p, t):
    p.write_bytes(t.encode("utf-8"))


def fix_teardown_in_class(text, class_name, correct_body):
    pat = re.compile(
        rf"(class {re.escape(class_name)}\(unittest\.TestCase\):\n)"
        rf"((?:    .*\n|\n)*?)"
        rf"    def tearDown\(self\):\n"
        rf"((?:        .*\n|\n)*?)"
        rf"(?=    def |\nclass |\Z)",
        re.MULTILINE | re.DOTALL,
    )

    def replacer(m):
        header = m.group(1)
        before = m.group(2)
        body = m.group(3)
        if "peer_proc" in body:
            return header + before + correct_body
        return m.group(0)

    return pat.sub(replacer, text, count=1)


SIMPLE_TEARDOWN = (
    "    def tearDown(self):\n"
    "        if getattr(self, \"old_env\", None) is not None:\n"
    "            os.environ[\"OHM_HOME\"] = self.old_env\n"
    "        else:\n"
    "            os.environ.pop(\"OHM_HOME\", None)\n"
    "        if getattr(self, \"tmpdir\", None):\n"
    "            shutil.rmtree(self.tmpdir, ignore_errors=True)\n\n"
)


def main():
    shutil.copy2(TARGET, TARGET.with_suffix(".py.bak_tear"))
    print(f"backup: {TARGET.name}.bak_tear")

    text = read_norm(TARGET)
    orig = text

    for cls in ("TestCLIInit", "TestRegistry", "TestCLISmoke"):
        text = fix_teardown_in_class(text, cls, SIMPLE_TEARDOWN)

    if text != orig:
        write_norm(TARGET, text)
        print("[ok]   fixed tearDown blocks")

        try:
            import py_compile
            py_compile.compile(str(TARGET), doraise=True)
            print("[ok]   py_compile clean")
        except Exception as e:
            print(f"[FAIL] py_compile: {e}")
            shutil.copy2(TARGET.with_suffix(".py.bak_tear"), TARGET)
            sys.exit(1)
    else:
        print("[skip] no changes needed")


if __name__ == "__main__":
    main()
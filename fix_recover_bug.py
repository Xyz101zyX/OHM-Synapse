import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).parent
CLI = ROOT / "ohm_cli.py"


def read_norm(p):
    return p.read_bytes().decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")


def write_norm(p, t):
    p.write_bytes(t.encode("utf-8"))


def main():
    shutil.copy2(CLI, CLI.with_suffix(".py.bak_recover"))
    print(f"backup: {CLI.name}.bak_recover")

    text = read_norm(CLI)

    m = re.search(r"^def cmd_recover\(", text, re.MULTILINE)
    if not m:
        print("[FAIL] cmd_recover not found")
        sys.exit(1)

    start = m.start()
    nxt = re.search(r"^def \w+\(", text[m.end():], re.MULTILINE)
    end = m.end() + nxt.start() if nxt else len(text)

    print("\n--- current cmd_recover (first 40 lines) ---")
    for line in text[start:end].split("\n")[:40]:
        print(f"  {line}")
    print("---")

    new_func = (
        'def cmd_recover(args: argparse.Namespace) -> int:\n'
        '    name = args.name\n'
        '    pdir = peer_dir(name)\n'
        '    if not pdir.exists():\n'
        '        print(f"error: peer \'{name}\' not initialized")\n'
        '        return 1\n'
        '    auth = AuthManager(pdir)\n'
        '    if not auth.configured:\n'
        '        print(f"peer \'{name}\' has no auth configured")\n'
        '        return 0\n'
        '    print(f"recovery for \'{name}\'")\n'
        '    print("choose method:")\n'
        '    print("  1. answer 3 personal questions")\n'
        '    print("  2. use recovery phrase")\n'
        '    choice = input("method [1/2]: ").strip()\n'
        '    ok = False\n'
        '    if choice == "1":\n'
        '        answers = []\n'
        '        for i, q in enumerate(auth.get_questions(), 1):\n'
        '            a = input(f"  {q}  ").strip()\n'
        '            answers.append(a)\n'
        '        ok = auth.verify_answers(answers)\n'
        '    elif choice == "2":\n'
        '        phrase = input("recovery phrase: ").strip()\n'
        '        ok = auth.verify_recovery_phrase(phrase)\n'
        '    else:\n'
        '        print("invalid choice")\n'
        '        return 2\n'
        '    if not ok:\n'
        '        print("error: verification failed")\n'
        '        return 1\n'
        '    import getpass\n'
        '    new_pw = getpass.getpass("New password: ")\n'
        '    confirm = getpass.getpass("Confirm: ")\n'
        '    if new_pw != confirm:\n'
        '        print("error: passwords do not match")\n'
        '        return 1\n'
        '    try:\n'
        '        auth.reset_password(new_pw)\n'
        '    except ValueError as e:\n'
        '        print(f"error: {e}")\n'
        '        return 1\n'
        '    print(f"[ok] password reset; all sessions revoked")\n'
        '    return 0\n\n\n'
    )

    new_text = text[:start] + new_func + text[end:]
    write_norm(CLI, new_text)
    print("[ok]   cmd_recover rewritten (no `n` reference)")

    try:
        import py_compile
        py_compile.compile(str(CLI), doraise=True)
        print("[ok]   py_compile clean")
    except Exception as e:
        print(f"[FAIL] py_compile: {e}")
        shutil.copy2(CLI.with_suffix(".py.bak_recover"), CLI)
        sys.exit(1)


if __name__ == "__main__":
    main()
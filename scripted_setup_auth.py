import os
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

from ohm_auth import AuthManager

OHM_HOME = Path(os.environ.get("OHM_HOME", Path.home() / ".ohm"))


def main():
    name = input("peer name (ex: bob): ").strip()
    if not name:
        print("aborted")
        return 1

    pdir = OHM_HOME / "peers" / name
    if not pdir.exists():
        print(f"error: peer '{name}' does not exist. Run: ohm init {name}")
        return 1

    auth = AuthManager(pdir)
    if auth.configured:
        print(f"auth already configured for '{name}'")
        return 1

    print(f"\n=== setup auth for '{name}' ===")
    print("(inputs echo normally here; no getpass)")
    print()

    pw = input("password: ").strip()
    if pw != input("confirm : ").strip():
        print("error: passwords do not match")
        return 1
    if len(pw) < 6:
        print("error: password must be >= 6 chars")
        return 1

    print()
    print("3 personal questions:")
    questions = []
    for i in range(1, 4):
        q = input(f"  Q{i}: ").strip()
        a = input(f"  A{i}: ").strip()
        if not q or not a:
            print("error: question and answer cannot be empty")
            return 1
        questions.append((q, a))

    try:
        phrase = auth.configure(pw, questions)
    except ValueError as e:
        print(f"error: {e}")
        return 1

    print()
    print("=" * 60)
    print("  RECOVERY PHRASE - WRITE THIS DOWN")
    print("=" * 60)
    print()
    print(f"    {phrase}")
    print()
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
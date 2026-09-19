import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).parent
PEER = ROOT / "run_peer.py"


def read_norm(p):
    return p.read_bytes().decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")


def write_norm(p, t):
    p.write_bytes(t.encode("utf-8"))


def main():
    shutil.copy2(PEER, PEER.with_suffix(".py.bak_revert"))
    print(f"backup: {PEER.name}.bak_revert")

    text = read_norm(PEER)

    marker_start = text.find("def run_gradio(")
    marker_end = text.find("def run_http(")

    if marker_start < 0 or marker_end < 0:
        print("[FAIL] markers not found")
        sys.exit(1)

    new_block = '''def run_gradio(brain, name, port):
    from ohm_ui import build_ui, CUSTOM_CSS
    demo = build_ui(brain, name, port)
    demo.launch(
        server_name="0.0.0.0",
        server_port=port,
        share=False,
        show_error=True,
        quiet=False,
        prevent_thread_lock=False,
        css=CUSTOM_CSS,
    )


'''

    text = text[:marker_start] + new_block + text[marker_end:]
    write_norm(PEER, text)
    print("[ok]   run_peer.py: reverted to plain gradio launch")

    try:
        import py_compile
        py_compile.compile(str(PEER), doraise=True)
        print("[ok]   py_compile clean")
    except Exception as e:
        print(f"[FAIL] py_compile: {e}")
        shutil.copy2(PEER.with_suffix(".py.bak_revert"), PEER)
        sys.exit(1)


if __name__ == "__main__":
    main()
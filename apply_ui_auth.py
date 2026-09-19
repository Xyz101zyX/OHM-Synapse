import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).parent
UI = ROOT / "ohm_ui.py"
PEER = ROOT / "run_peer.py"


def read_norm(p):
    return p.read_bytes().decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")


def write_norm(p, t):
    p.write_bytes(t.encode("utf-8"))


def backup(p):
    b = p.with_suffix(p.suffix + ".bak_uiauth")
    if not b.exists():
        shutil.copy2(p, b)


def patch_ui():
    backup(UI)
    text = read_norm(UI)
    orig = text

    if "def build_ui(ohm_instance" not in text:
        print("[FAIL] build_ui not found in ohm_ui.py")
        sys.exit(1)

    # Modify the run_gradio to accept an auth_verify callback
    # We patch ohm_ui's launch path indirectly by modifying the return signature
    # but simpler: pass the auth object through build_ui args

    old_sig = "def build_ui(ohm_instance, peer_name: str, own_port: int):"
    new_sig = "def build_ui(ohm_instance, peer_name: str, own_port: int, auth_verify=None):"
    if new_sig not in text:
        text = text.replace(old_sig, new_sig, 1)

    # Store auth_verify in a module-level so run_gradio can read it
    # Actually simpler: define a wrapper demo.load trick
    if "_UI_AUTH_VERIFY" not in text:
        # Insert a module-level dict after imports
        anchor = 'CUSTOM_CSS = """'
        if anchor in text:
            text = text.replace(
                anchor,
                "_UI_AUTH_VERIFY = {\"fn\": None}\n\n\n" + anchor,
                1,
            )

    # Inside build_ui, wire auth_verify into the dict
    anchor = "    with gr.Blocks(title=f\"OHM {peer_name}\") as demo:"
    new_anchor = (
        "    if auth_verify is not None:\n"
        "        _UI_AUTH_VERIFY[\"fn\"] = auth_verify\n\n"
        + anchor
    )
    if new_anchor not in text:
        text = text.replace(anchor, new_anchor, 1)

    if text != orig:
        write_norm(UI, text)
        print("[ok]   ohm_ui.py: build_ui accepts auth_verify")
    else:
        print("[skip] ohm_ui.py: no changes")


def patch_peer():
    backup(PEER)
    text = read_norm(PEER)
    orig = text

    # Add auth_verify helper + wire into run_gradio
    if "def _make_gradio_auth" not in text:
        anchor = "def run_gradio(brain, name, port):"
        if anchor not in text:
            print("[FAIL] run_gradio not found")
            sys.exit(1)

        helper = (
            "def _make_gradio_auth(auth, peer_name):\n"
            "    if auth is None or not auth.configured:\n"
            "        return None\n"
            "    def _verify(username, password):\n"
            "        return auth.verify_password(password)\n"
            "    return _verify\n\n\n"
        )
        text = text.replace(anchor, helper + anchor, 1)

    # Modify run_gradio to pass auth when launching
    old_launch = (
        "def run_gradio(brain, name, port):\n"
        "    from ohm_ui import build_ui, CUSTOM_CSS\n"
        "    demo = build_ui(brain, name, port)\n"
        "    demo.launch(\n"
        "        server_name=\"0.0.0.0\",\n"
        "        server_port=port,\n"
        "        share=False,\n"
        "        show_error=True,\n"
        "        quiet=False,\n"
        "        prevent_thread_lock=False,\n"
        "        css=CUSTOM_CSS,\n"
        "    )\n"
    )
    new_launch = (
        "def run_gradio(brain, name, port):\n"
        "    from ohm_ui import build_ui, CUSTOM_CSS\n"
        "    _auth = None\n"
        "    try:\n"
        "        _pdir = Path(brain.config.memory_cfg.get(\"persistence_file\", \"./mem.json\")).parent\n"
        "        _auth = AuthManager(_pdir)\n"
        "    except Exception:\n"
        "        _auth = None\n"
        "    _verify = _make_gradio_auth(_auth, name)\n"
        "    demo = build_ui(brain, name, port, auth_verify=_verify)\n"
        "    _launch_kwargs = dict(\n"
        "        server_name=\"0.0.0.0\",\n"
        "        server_port=port,\n"
        "        share=False,\n"
        "        show_error=True,\n"
        "        quiet=False,\n"
        "        prevent_thread_lock=False,\n"
        "        css=CUSTOM_CSS,\n"
        "    )\n"
        "    if _verify is not None:\n"
        "        _launch_kwargs[\"auth\"] = _verify\n"
        "    demo.launch(**_launch_kwargs)\n"
    )

    if old_launch in text:
        text = text.replace(old_launch, new_launch, 1)
        print("[ok]   run_peer.py: run_gradio passes auth callback")
    elif new_launch in text:
        print("[skip] run_peer.py: already patched")
    else:
        print("[WARN] run_peer.py: launch block not matched, may need manual edit")

    if text != orig:
        write_norm(PEER, text)

    try:
        import py_compile
        py_compile.compile(str(PEER), doraise=True)
        py_compile.compile(str(UI), doraise=True)
        print("[ok]   py_compile clean")
    except Exception as e:
        print(f"[FAIL] py_compile: {e}")
        shutil.copy2(PEER.with_suffix(".py.bak_uiauth"), PEER)
        shutil.copy2(UI.with_suffix(".py.bak_uiauth"), UI)
        sys.exit(1)


def main():
    print("=" * 60)
    print("APPLY UI AUTH (Gradio Basic Auth)")
    print("=" * 60)
    patch_ui()
    print()
    patch_peer()
    print("=" * 60)
    print("DONE")
    print("=" * 60)


if __name__ == "__main__":
    main()
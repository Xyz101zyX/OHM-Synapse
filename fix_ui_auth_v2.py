import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).parent
CLI = ROOT / "ohm_cli.py"
PEER = ROOT / "run_peer.py"


def read_norm(p):
    return p.read_bytes().decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")


def write_norm(p, t):
    p.write_bytes(t.encode("utf-8"))


def backup(p):
    b = p.with_suffix(p.suffix + ".bak_uiauth2")
    if not b.exists():
        shutil.copy2(p, b)


def patch_peer():
    backup(PEER)
    text = read_norm(PEER)
    orig = text

    # Replace the old _make_gradio_auth helper with a simpler version
    old_helper = (
        "def _make_gradio_auth(auth, peer_name):\n"
        "    if auth is None or not auth.configured:\n"
        "        return None\n"
        "    def _verify(username, password):\n"
        "        return auth.verify_password(password)\n"
        "    return _verify\n\n\n"
    )
    new_helper = ""  # remove — no longer needed
    if old_helper in text:
        text = text.replace(old_helper, new_helper, 1)
        print("[ok]   removed old _make_gradio_auth helper")

    # Replace run_gradio body
    old_run = (
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

    new_run = (
        "def run_gradio(brain, name, port):\n"
        "    from ohm_ui import build_ui, CUSTOM_CSS\n"
        "    demo = build_ui(brain, name, port)\n"
        "    _launch_kwargs = dict(\n"
        "        server_name=\"0.0.0.0\",\n"
        "        server_port=port,\n"
        "        share=False,\n"
        "        show_error=True,\n"
        "        quiet=False,\n"
        "        prevent_thread_lock=False,\n"
        "        css=CUSTOM_CSS,\n"
        "    )\n"
        "    _ui_pass = os.environ.get(\"OHM_UI_PASSWORD\", \"\")\n"
        "    if _ui_pass:\n"
        "        _launch_kwargs[\"auth\"] = (\"ohm\", _ui_pass)\n"
        "        print(f\"[{name}] UI auth enabled (user: ohm)\", flush=True)\n"
        "    demo.launch(**_launch_kwargs)\n"
    )

    if new_run in text:
        print("[ok]   run_gradio already uses tuple auth")
    elif old_run in text:
        text = text.replace(old_run, new_run, 1)
        print("[ok]   run_gradio: switched to tuple auth via env var")
    else:
        print("[FAIL] run_gradio block not matched")
        sys.exit(1)

    if text != orig:
        write_norm(PEER, text)

    try:
        import py_compile
        py_compile.compile(str(PEER), doraise=True)
        print("[ok]   py_compile run_peer.py")
    except Exception as e:
        print(f"[FAIL] py_compile: {e}")
        shutil.copy2(PEER.with_suffix(".py.bak_uiauth2"), PEER)
        sys.exit(1)


def patch_cli():
    backup(CLI)
    text = read_norm(CLI)
    orig = text

    # Insert getpass capture + env var in cmd_run
    anchor = (
        "    headless = args.headless\n"
        "\n"
        "    print(f\"[ohm] starting peer '{name}' on port {port}{' (headless)' if headless else ''}\")\n"
        "    proc = _spawn_peer(name, port, headless)\n"
    )

    new_anchor = (
        "    headless = args.headless\n"
        "\n"
        "    ui_password = \"\"\n"
        "    if not headless and auth.configured:\n"
        "        import getpass\n"
        "        ui_password = getpass.getpass(f\"UI password for '{name}': \")\n"
        "        if not auth.verify_password(ui_password):\n"
        "            print(\"error: invalid password\")\n"
        "            return 1\n"
        "\n"
        "    print(f\"[ohm] starting peer '{name}' on port {port}{' (headless)' if headless else ''}\")\n"
        "    proc = _spawn_peer(name, port, headless, extra_env={\"OHM_UI_PASSWORD\": ui_password} if ui_password else None)\n"
    )

    if new_anchor in text:
        print("[ok]   cmd_run already patched")
    elif anchor in text:
        text = text.replace(anchor, new_anchor, 1)
        print("[ok]   cmd_run: prompts for UI password")
    else:
        print("[WARN] cmd_run anchor not found; will need manual edit")

    # Extend _spawn_peer signature to accept extra_env
    old_spawn = (
        "def _spawn_peer(name: str, port: int, headless: bool, extra: List[str] = None) -> subprocess.Popen:\n"
        "    pdir = peer_dir(name)\n"
        "    if not pdir.exists():\n"
        "        raise RuntimeError(f\"peer '{name}' not initialized. run: ohm init {name}\")\n"
        "\n"
        "    env = os.environ.copy()\n"
        "    env[\"OHM_HOME\"] = str(OHM_HOME)\n"
    )
    new_spawn = (
        "def _spawn_peer(name: str, port: int, headless: bool, extra: List[str] = None,\n"
        "                extra_env: Optional[Dict[str, str]] = None) -> subprocess.Popen:\n"
        "    pdir = peer_dir(name)\n"
        "    if not pdir.exists():\n"
        "        raise RuntimeError(f\"peer '{name}' not initialized. run: ohm init {name}\")\n"
        "\n"
        "    env = os.environ.copy()\n"
        "    env[\"OHM_HOME\"] = str(OHM_HOME)\n"
        "    if extra_env:\n"
        "        env.update(extra_env)\n"
    )

    if new_spawn in text:
        print("[ok]   _spawn_peer already supports extra_env")
    elif old_spawn in text:
        text = text.replace(old_spawn, new_spawn, 1)
        print("[ok]   _spawn_peer: extra_env added")
    else:
        print("[WARN] _spawn_peer anchor not found")

    if text != orig:
        write_norm(CLI, text)

    try:
        import py_compile
        py_compile.compile(str(CLI), doraise=True)
        print("[ok]   py_compile ohm_cli.py")
    except Exception as e:
        print(f"[FAIL] py_compile: {e}")
        shutil.copy2(CLI.with_suffix(".py.bak_uiauth2"), CLI)
        sys.exit(1)


def main():
    print("=" * 60)
    print("FIX UI AUTH v2 (tuple + env var)")
    print("=" * 60)
    patch_peer()
    print()
    patch_cli()
    print("=" * 60)
    print("DONE")
    print("=" * 60)


if __name__ == "__main__":
    main()
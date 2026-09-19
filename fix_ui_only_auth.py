import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).parent
PEER = ROOT / "run_peer.py"
CLI = ROOT / "ohm_cli.py"


def read_norm(p):
    return p.read_bytes().decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")


def write_norm(p, t):
    p.write_bytes(t.encode("utf-8"))


def backup(p):
    b = p.with_suffix(p.suffix + ".bak_uionly")
    if not b.exists():
        shutil.copy2(p, b)


def patch_peer():
    backup(PEER)
    text = read_norm(PEER)
    orig = text

    # 1. Ensure imports exist (base64 for Basic Auth decoding)
    if "import base64" not in text:
        text = text.replace("import time\n", "import base64\nimport time\n", 1)
        print("[ok]   peer: added base64 import")

    # 2. Replace run_gradio entirely with middleware approach
    old_run = (
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

    new_run = (
        "def _install_auth_middleware(demo, auth, name):\n"
        "    if auth is None or not auth.configured:\n"
        "        print(f\"[{name}] UI auth: not configured\", flush=True)\n"
        "        return\n"
        "    try:\n"
        "        from fastapi import Request\n"
        "        from fastapi.responses import Response as FastResponse\n"
        "    except ImportError:\n"
        "        print(f\"[{name}] UI auth: fastapi not available\", flush=True)\n"
        "        return\n"
        "    app = getattr(demo, \"app\", None)\n"
        "    if app is None:\n"
        "        print(f\"[{name}] UI auth: demo.app not available\", flush=True)\n"
        "        return\n"
        "    PUBLIC_PATHS = (\"/ping\", \"/health\", \"/favicon.ico\")\n"
        "    @app.middleware(\"http\")\n"
        "    async def _basic_auth(request: Request, call_next):\n"
        "        path = request.url.path\n"
        "        if path in PUBLIC_PATHS or path.startswith(\"/static/\"):\n"
        "            return await call_next(request)\n"
        "        header = request.headers.get(\"authorization\", \"\")\n"
        "        if not header.startswith(\"Basic \"):\n"
        "            return FastResponse(status_code=401, headers={\"WWW-Authenticate\": 'Basic realm=\"OHM\"'})\n"
        "        try:\n"
        "            decoded = base64.b64decode(header[6:]).decode(\"utf-8\")\n"
        "            user, _, pw = decoded.partition(\":\")\n"
        "        except Exception:\n"
        "            return FastResponse(status_code=401, headers={\"WWW-Authenticate\": 'Basic realm=\"OHM\"'})\n"
        "        if not auth.verify_password(pw):\n"
        "            return FastResponse(status_code=401, headers={\"WWW-Authenticate\": 'Basic realm=\"OHM\"'})\n"
        "        return await call_next(request)\n"
        "    print(f\"[{name}] UI auth enabled (user: any, password: as configured)\", flush=True)\n\n\n"
        "def run_gradio(brain, name, port):\n"
        "    from ohm_ui import build_ui, CUSTOM_CSS\n"
        "    _auth = None\n"
        "    try:\n"
        "        _pdir = Path(brain.config.memory_cfg.get(\"persistence_file\", \"./mem.json\")).parent\n"
        "        _auth = AuthManager(_pdir)\n"
        "    except Exception:\n"
        "        _auth = None\n"
        "    demo = build_ui(brain, name, port)\n"
        "    _install_auth_middleware(demo, _auth, name)\n"
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

    if new_run in text:
        print("[ok]   peer: run_gradio already uses middleware")
    elif old_run in text:
        text = text.replace(old_run, new_run, 1)
        print("[ok]   peer: run_gradio switched to middleware")
    else:
        print("[FAIL] peer: run_gradio block not matched")
        print("       first 10 lines starting with 'def run_gradio':")
        idx = text.find("def run_gradio")
        if idx >= 0:
            for line in text[idx:idx + 600].split("\n")[:10]:
                print(f"       {line}")
        sys.exit(1)

    if text != orig:
        write_norm(PEER, text)

    try:
        import py_compile
        py_compile.compile(str(PEER), doraise=True)
        print("[ok]   py_compile run_peer.py")
    except Exception as e:
        print(f"[FAIL] py_compile: {e}")
        shutil.copy2(PEER.with_suffix(".py.bak_uionly"), PEER)
        sys.exit(1)


def patch_cli():
    backup(CLI)
    text = read_norm(CLI)
    orig = text

    # Remove the "not logged in" check from cmd_run
    old_check = (
        "    auth = AuthManager(pdir)\n"
        "    if auth.configured and not auth_disabled_by_env():\n"
        "        token = _load_session_token(name)\n"
        "        if not token or not auth.validate_session(token):\n"
        "            print(f\"error: not logged in to '{name}'. run: ohm login {name}\")\n"
        "            return 1\n"
        "    reg = load_registry()\n"
    )
    new_check = (
        "    auth = AuthManager(pdir)\n"
        "    reg = load_registry()\n"
    )

    if new_check in text and "error: not logged in to" not in text:
        print("[ok]   cli: login requirement already removed from cmd_run")
    elif old_check in text:
        text = text.replace(old_check, new_check, 1)
        print("[ok]   cli: login requirement removed from cmd_run")
    else:
        print("[WARN] cli: cmd_run login check not found; may already be different")
        for i, line in enumerate(text.split("\n"), 1):
            if "not logged in to" in line:
                print(f"       line {i}: {line.strip()}")

    # Remove the UI password prompt from cmd_run
    old_prompt = (
        "    ui_password = \"\"\n"
        "    if not headless and auth.configured:\n"
        "        import getpass\n"
        "        ui_password = getpass.getpass(f\"UI password for '{name}': \")\n"
        "        if not auth.verify_password(ui_password):\n"
        "            print(\"error: invalid password\")\n"
        "            return 1\n"
        "\n"
        "    print(f\"[ohm] starting peer '{name}' on port {port}{' (headless)' if headless else ''}\")\n"
        "    proc = _spawn_peer(name, port, headless,\n"
        "                       extra_env={\"OHM_UI_PASSWORD\": ui_password} if ui_password else None)\n"
    )
    new_prompt = (
        "    print(f\"[ohm] starting peer '{name}' on port {port}{' (headless)' if headless else ''}\")\n"
        "    if not headless and auth.configured:\n"
        "        print(f\"[ohm] UI will ask for password when opened in browser\")\n"
        "    proc = _spawn_peer(name, port, headless)\n"
    )

    if new_prompt in text:
        print("[ok]   cli: UI password prompt already removed from cmd_run")
    elif old_prompt in text:
        text = text.replace(old_prompt, new_prompt, 1)
        print("[ok]   cli: UI password prompt removed from cmd_run")
    else:
        print("[WARN] cli: UI password prompt block not found")

    if text != orig:
        write_norm(CLI, text)

    try:
        import py_compile
        py_compile.compile(str(CLI), doraise=True)
        print("[ok]   py_compile ohm_cli.py")
    except Exception as e:
        print(f"[FAIL] py_compile: {e}")
        shutil.copy2(CLI.with_suffix(".py.bak_uionly"), CLI)
        sys.exit(1)


def main():
    print("=" * 60)
    print("SIMPLIFY AUTH: ONLY BROWSER PROMPTS")
    print("=" * 60)
    patch_peer()
    print()
    patch_cli()
    print("=" * 60)
    print("DONE")
    print("=" * 60)


if __name__ == "__main__":
    main()
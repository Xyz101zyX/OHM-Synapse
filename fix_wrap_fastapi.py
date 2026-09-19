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
    shutil.copy2(PEER, PEER.with_suffix(".py.bak_fastapi"))
    print(f"backup: {PEER.name}.bak_fastapi")

    text = read_norm(PEER)

    marker_start = text.find("def _install_auth_middleware(")
    marker_end = text.find("def run_http(")

    if marker_start < 0:
        print("[FAIL] _install_auth_middleware not found")
        sys.exit(1)
    if marker_end < 0:
        print("[FAIL] run_http not found")
        sys.exit(1)

    new_block = '''def run_gradio(brain, name, port):
    from ohm_ui import build_ui, CUSTOM_CSS
    try:
        import uvicorn
        from fastapi import FastAPI, Request
        from fastapi.responses import Response as FastResponse
    except ImportError as e:
        print(f"[{name}] FastAPI/uvicorn not available ({e}); launching without auth", flush=True)
        demo = build_ui(brain, name, port)
        demo.launch(server_name="0.0.0.0", server_port=port,
                    share=False, show_error=True, quiet=False,
                    prevent_thread_lock=False, css=CUSTOM_CSS)
        return

    _auth = None
    try:
        _pdir = Path(brain.config.memory_cfg.get("persistence_file", "./mem.json")).parent
        _auth = AuthManager(_pdir)
    except Exception:
        _auth = None

    demo = build_ui(brain, name, port)

    app = FastAPI()

    if _auth is not None and _auth.configured:
        PUBLIC_PATHS = ("/ping", "/health", "/favicon.ico")

        @app.middleware("http")
        async def _basic_auth(request: Request, call_next):
            path = request.url.path
            if path in PUBLIC_PATHS or path.startswith("/static/"):
                return await call_next(request)
            header = request.headers.get("authorization", "")
            if not header.startswith("Basic "):
                return FastResponse(status_code=401, headers={"WWW-Authenticate": 'Basic realm="OHM"'})
            try:
                decoded = base64.b64decode(header[6:]).decode("utf-8")
                _user, _, pw = decoded.partition(":")
            except Exception:
                return FastResponse(status_code=401, headers={"WWW-Authenticate": 'Basic realm="OHM"'})
            if not _auth.verify_password(pw):
                return FastResponse(status_code=401, headers={"WWW-Authenticate": 'Basic realm="OHM"'})
            return await call_next(request)

        print(f"[{name}] UI auth enabled (user: any, password: as configured)", flush=True)
    else:
        print(f"[{name}] UI auth: not configured", flush=True)

    try:
        from gradio.routes import mount_gradio_app
    except ImportError:
        try:
            from gradio import mount_gradio_app
        except ImportError:
            print(f"[{name}] mount_gradio_app not found; falling back to plain gradio", flush=True)
            demo.launch(server_name="0.0.0.0", server_port=port,
                        share=False, show_error=True, quiet=False,
                        prevent_thread_lock=False, css=CUSTOM_CSS)
            return

    app = mount_gradio_app(app, demo, path="/")

    print(f"[{name}] launching FastAPI + Gradio on port {port}", flush=True)
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")


'''

    text = text[:marker_start] + new_block + text[marker_end:]

    if "import gradio as gr" not in text and "import gradio" not in text:
        anchor = "from ohm_auth import AuthManager"
        if anchor in text:
            text = text.replace(anchor, "import gradio\n" + anchor, 1)
            print("[ok]   added `import gradio`")

    write_norm(PEER, text)
    print("[ok]   run_gradio wrapped in FastAPI + mount_gradio_app")

    try:
        import py_compile
        py_compile.compile(str(PEER), doraise=True)
        print("[ok]   py_compile clean")
    except Exception as e:
        print(f"[FAIL] py_compile: {e}")
        shutil.copy2(PEER.with_suffix(".py.bak_fastapi"), PEER)
        sys.exit(1)


if __name__ == "__main__":
    main()
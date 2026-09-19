"""
ui_gateway.py - reverse proxy com login por cookie (48h) na frente do Gradio.
Requer: pip install aiohttp
Uso:
    set OHM_UI_PASSWORD=minhasenha
    python ui_gateway.py
Abre no celular: http://<ip-notebook>:8080
"""
import asyncio, hashlib, hmac, os, secrets, sys, time
from pathlib import Path
import aiohttp
from aiohttp import web, ClientSession, WSMsgType

BACKEND_HOST = "127.0.0.1"
BACKEND_PORT = int(os.environ.get("OHM_UI_BACKEND", "7860"))
GATEWAY_PORT = int(os.environ.get("OHM_UI_PORT", "8080"))
SESSION_HOURS = 48
COOKIE = "ohm_ui"
SECRET_PATH = Path.home() / ".ohm" / "ui_secret"


def load_secret() -> bytes:
    SECRET_PATH.parent.mkdir(parents=True, exist_ok=True)
    if SECRET_PATH.exists():
        return SECRET_PATH.read_bytes()
    s = secrets.token_bytes(32)
    SECRET_PATH.write_bytes(s)
    try: os.chmod(SECRET_PATH, 0o600)
    except OSError: pass
    return s


SECRET = load_secret()


def make_token(exp: int) -> str:
    sig = hmac.new(SECRET, f"{exp}".encode(), hashlib.sha256).hexdigest()
    return f"{exp}.{sig}"


def verify(token: str) -> bool:
    try:
        exp_s, sig = token.split(".", 1)
        exp = int(exp_s)
    except (ValueError, AttributeError):
        return False
    if exp < time.time():
        return False
    expected = hmac.new(SECRET, f"{exp}".encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(sig, expected)


def get_password():
    p = os.environ.get("OHM_UI_PASSWORD")
    if p: return p
    f = Path.home() / ".ohm" / "ui_password"
    if f.exists(): return f.read_text().strip()
    return None


LOGIN_HTML = """<!doctype html><html><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>Ohm - Login</title><style>
body{font-family:system-ui,sans-serif;background:#0e1116;color:#e6edf3;
display:flex;min-height:100vh;align-items:center;justify-content:center;margin:0}
form{background:#161b22;padding:2rem;border-radius:12px;box-shadow:0 4px 20px #0008;
width:min(92vw,360px)}h1{margin:0 0 1rem;font-size:1.4rem}
input,button{width:100%;box-sizing:border-box;padding:.7rem;border-radius:8px;
border:1px solid #30363d;background:#0d1117;color:#e6edf3;font-size:1rem}
button{margin-top:1rem;background:#238636;border-color:#2ea043;cursor:pointer}
button:hover{background:#2ea043}.err{color:#f85149;font-size:.9rem;
min-height:1.2em;margin-top:.5rem}</style></head><body>
<form method=post action=/login><h1>Ohm - Login</h1>
<input name=password type=password placeholder="Senha da UI" autofocus required>
<button type=submit>Entrar</button><div class=err>__ERR__</div>
</form></body></html>"""


def ok(req):
    t = req.cookies.get(COOKIE)
    return bool(t and verify(t))


async def login_get(req):
    return web.Response(text=LOGIN_HTML.replace("__ERR__", ""), content_type="text/html")


async def login_post(req):
    data = await req.post()
    expected = get_password() or ""
    if not hmac.compare_digest(data.get("password", ""), expected):
        return web.Response(text=LOGIN_HTML.replace("__ERR__", "Senha incorreta"),
                            status=401, content_type="text/html")
    exp = int(time.time()) + SESSION_HOURS * 3600
    r = web.HTTPFound("/")
    r.set_cookie(COOKIE, make_token(exp), max_age=SESSION_HOURS * 3600,
                 httponly=True, samesite="Lax")
    raise r


async def http_proxy(req):
    if not ok(req):
        raise web.HTTPFound("/login")
    url = f"http://{BACKEND_HOST}:{BACKEND_PORT}{req.rel_url}"
    headers = {k: v for k, v in req.headers.items()
               if k.lower() not in ("host", "cookie", "content-length")}
    body = await req.read()
    async with ClientSession() as s:
        async with s.request(req.method, url, headers=headers, data=body,
                             allow_redirects=False) as up:
            data = await up.read()
            r = web.Response(body=data, status=up.status)
            for k, v in up.headers.items():
                if k.lower() in ("content-encoding", "content-length",
                                 "transfer-encoding", "connection"):
                    continue
                r.headers[k] = v
            return r


async def ws_proxy(req):
    if not ok(req):
        raise web.HTTPUnauthorized()
    ws_s = web.WebSocketResponse()
    await ws_s.prepare(req)
    url = f"ws://{BACKEND_HOST}:{BACKEND_PORT}{req.rel_url}"
    async with ClientSession() as s:
        async with s.ws_connect(url) as ws_c:
            async def up():
                async for m in ws_s:
                    if m.type == WSMsgType.TEXT: await ws_c.send_str(m.data)
                    elif m.type == WSMsgType.BINARY: await ws_c.send_bytes(m.data)
                    elif m.type in (WSMsgType.CLOSE, WSMsgType.ERROR): break
            async def down():
                async for m in ws_c:
                    if m.type == WSMsgType.TEXT: await ws_s.send_str(m.data)
                    elif m.type == WSMsgType.BINARY: await ws_s.send_bytes(m.data)
                    elif m.type in (WSMsgType.CLOSE, WSMsgType.ERROR): break
            await asyncio.gather(up(), down())
    return ws_s


def main():
    if not get_password():
        print("[FAIL] defina OHM_UI_PASSWORD ou ~/.ohm/ui_password")
        sys.exit(1)
    app = web.Application()
    app.router.add_get("/login", login_get)
    app.router.add_post("/login", login_post)
    app.router.add_get("/queue/join", ws_proxy)
    app.router.add_route("*", "/{tail:.*}", http_proxy)
    print(f"[ohm-ui] http://0.0.0.0:{GATEWAY_PORT}  ->  http://{BACKEND_HOST}:{BACKEND_PORT}")
    web.run_app(app, host="0.0.0.0", port=GATEWAY_PORT, print=None)


if __name__ == "__main__":
    main()
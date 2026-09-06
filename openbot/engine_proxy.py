"""Same-origin reverse proxy for official OpenCode web and Hermes dashboard.

The browser cannot reach 127.0.0.1 inside a Railway box. The board already
listens on the public port, so we iframe /engine/opencode/ and /engine/hermes/
and forward (including WebSockets) to the loopback engines. Do not reimplement
those UIs.
"""

from __future__ import annotations

import http.client
import json
import re
import select
import socket
import time
from urllib.parse import parse_qs, urljoin, urlparse

OPENCODE_PREFIX = "/engine/opencode"
HERMES_PREFIX = "/engine/hermes"
ENGINES = {
    OPENCODE_PREFIX: 4096,
    HERMES_PREFIX: 9119,
}
OPENCODE_ROOTS = (
    "/session",
    "/global",
    "/event",
    "/config",
    "/provider",
    "/pty",
    "/file",
    "/tui",
    "/experimental",
    "/doc",
    "/assets",
    "/project",
    "/path",
    "/vcs",
    "/find",
    "/agent",
    "/command",
    "/skill",
    "/lsp",
    "/formatter",
    "/instance",
    "/log",
    "/mcp",
    "/auth",
    "/permission",
    "/question",
    "/diff",
    "/patch",
    "/tool",
    "/oauth",
    "/worktree",
)
BOARD_PATHS = {
    "/",
    "/index.html",
    "/app.js",
    "/styles.css",
    "/favicon.png",
    "/logo.png",
    "/manifest.json",
    "/sw.js",
    "/NOTICE",
}
HERMES_ROOTS = (
    "/chat",
    "/cron",
    "/skills",
    "/sessions",
    "/models",
    "/system",
    "/env",
    "/ws",
    "/dashboard",
)
HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "proxy-connection",
}
DROP_RESPONSE = HOP | {
    "content-length",
    "x-frame-options",
    "content-security-policy",
    "content-security-policy-report-only",
}
ROOT_ATTR = re.compile(
    rb"""(?P<pre>\b(?:src|href|action)=["'])/(?P<path>(?!/|engine/(?:opencode|hermes)/)[^"']*)""",
    re.I,
)


def backend_path(request_path: str, prefix: str) -> str:
    path = urlparse(request_path).path or "/"
    query = urlparse(request_path).query
    if path == prefix:
        stripped = "/"
    elif path.startswith(prefix + "/"):
        stripped = path[len(prefix) :] or "/"
        if not stripped.startswith("/"):
            stripped = "/" + stripped
    else:
        stripped = path
    if query:
        return f"{stripped}?{query}"
    return stripped


def _root_hit(path: str, roots: tuple[str, ...]) -> bool:
    return any(path == root or path.startswith(root + "/") for root in roots)


def _opencode_spa_route(path: str) -> bool:
    parts = [part for part in (path or "").split("/") if part]
    if not parts or parts[0] in {"engine", "api", "web", "assets"}:
        return False
    decoded = _decode_opencode_dir(parts[0])
    if not decoded:
        return False
    return decoded.startswith("/") or (len(decoded) >= 2 and decoded[1] == ":")


def _engine_from_referer(referer: str) -> str | None:
    path = urlparse(referer or "").path or ""
    for prefix in ENGINES:
        if path == prefix or path.startswith(prefix + "/"):
            return prefix
    if _opencode_spa_route(path):
        return OPENCODE_PREFIX
    if _root_hit(path, HERMES_ROOTS):
        return HERMES_PREFIX
    if _root_hit(path, OPENCODE_ROOTS):
        return OPENCODE_PREFIX
    return None


def _is_board_path(path: str) -> bool:
    p = urlparse(path).path or "/"
    if p.startswith("/api/"):
        return True
    if p in BOARD_PATHS:
        return True
    if p.startswith("/favicon") or p.startswith("/logo"):
        return True
    return False


def engine_target(request_path: str, referer: str = "") -> tuple[str, int] | None:
    path = urlparse(request_path).path or "/"
    for prefix, port in ENGINES.items():
        if path == prefix or path.startswith(prefix + "/"):
            return prefix, port
    if _root_hit(path, HERMES_ROOTS):
        return HERMES_PREFIX, ENGINES[HERMES_PREFIX]
    if _root_hit(path, OPENCODE_ROOTS):
        return OPENCODE_PREFIX, ENGINES[OPENCODE_PREFIX]
    if _opencode_spa_route(path):
        return OPENCODE_PREFIX, ENGINES[OPENCODE_PREFIX]
    prefix = _engine_from_referer(referer)
    if prefix:
        return prefix, ENGINES[prefix]
    if not _is_board_path(request_path):
        return OPENCODE_PREFIX, ENGINES[OPENCODE_PREFIX]
    return None


def _rewrite_location(value: str, prefix: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return raw
    parsed = urlparse(raw)
    if parsed.scheme in {"http", "https"} and parsed.hostname not in {"127.0.0.1", "localhost", ""}:
        return raw
    path = parsed.path or "/"
    if path == prefix or path.startswith(prefix + "/"):
        return raw
    if prefix == OPENCODE_PREFIX and _opencode_spa_route(path):
        rebuilt = path
        if parsed.query:
            rebuilt = f"{rebuilt}?{parsed.query}"
        if parsed.fragment:
            rebuilt = f"{rebuilt}#{parsed.fragment}"
        return rebuilt
    if not path.startswith("/"):
        path = "/" + path
    rebuilt = prefix + path
    if parsed.query:
        rebuilt = f"{rebuilt}?{parsed.query}"
    if parsed.fragment:
        rebuilt = f"{rebuilt}#{parsed.fragment}"
    if parsed.scheme in {"http", "https"}:
        return urljoin(f"{parsed.scheme}://{parsed.netloc}", rebuilt)
    return rebuilt


def _rewrite_root_urls(body: bytes, prefix: str) -> bytes:
    pref = prefix.encode("ascii") + b"/"

    def repl(match: re.Match[bytes]) -> bytes:
        return match.group("pre") + pref + match.group("path")

    return ROOT_ATTR.sub(repl, body)


# Official OpenCode new layout hides the file tree (showFileTree=false) and
# defaults the side panel to Changes: git / branch / last-turn diffs only.
# Patch persist before the SPA boots so All files (the whole repo) is open.
OPENCODE_TREE_SCRIPT = (
    "<script>(function(){"
    "try{var orig=window.matchMedia.bind(window);window.matchMedia=function(q){"
    "if(/min-width:\\s*768px/i.test(String(q))){return{matches:true,media:q,onchange:null,"
    "addListener:function(){},removeListener:function(){},addEventListener:function(){},"
    "removeEventListener:function(){},dispatchEvent:function(){return false;}};}"
    "return orig(q);};}catch(e){}"
    "function withState(raw){if(!raw)return raw;try{var o=JSON.parse(raw);"
    "if(!o||typeof o!=='object'||Array.isArray(o))return raw;"
    "if('fileTree' in o||'sidebar' in o||'review' in o){"
    "o.fileTree=Object.assign({width:260},o.fileTree||{},{opened:true,tab:'all'});"
    "if(o.review&&typeof o.review==='object')o.review.panelOpened=false;}"
    "if(o.general&&typeof o.general==='object')o.general.showFileTree=true;"
    "return JSON.stringify(o);}catch(e){return raw;}}"
    "try{var get=localStorage.getItem.bind(localStorage);"
    "var set=localStorage.setItem.bind(localStorage);"
    "localStorage.getItem=function(k){var v=get(k);if(v)return withState(v);"
    "if(/layout/i.test(String(k||'')))return JSON.stringify({fileTree:{opened:true,width:260,tab:'all'},review:{panelOpened:false}});"
    "if(/settings/i.test(String(k||'')))return JSON.stringify({general:{showFileTree:true}});"
    "return v;};"
    "localStorage.setItem=function(k,v){return set(k,withState(String(v)));};}catch(e){}"
    "function labelOf(el){return (el.getAttribute('aria-label')||el.textContent||'').replace(/\\s+/g,' ').trim().toLowerCase();}"
    "function clickNamed(want){var nodes=document.querySelectorAll('button,[role=\"tab\"],[role=\"button\"]');"
    "for(var i=0;i<nodes.length;i++){var t=labelOf(nodes[i]);if(t===want){nodes[i].click();return true;}}return false;}"
    "function clickAll(){return clickNamed('all files');}"
    "var n=0;var toggled=false;var iv=setInterval(function(){n++;"
    "if(clickAll()){clearInterval(iv);return;}"
    "if(!toggled&&n>6){toggled=clickNamed('toggle file tree');}"
    "if(n>40)clearInterval(iv);},350);"
    "})();</script>"
)


def inject_opencode_tree(body: bytes, content_type: str = "") -> bytes:
    """Force official OpenCode web onto All files (whole repo) in the iframe."""
    if content_type and "html" not in content_type.lower():
        return body
    if b"showFileTree" in body:
        return body
    return _insert_head(body, OPENCODE_TREE_SCRIPT.encode("ascii"))


def _insert_head(body: bytes, snippet: bytes) -> bytes:
    lower = body.lower()
    idx = lower.find(b"<head>")
    if idx >= 0:
        at = idx + len(b"<head>")
        return body[:at] + snippet + body[at:]
    idx = lower.find(b"<head ")
    if idx >= 0:
        end = lower.find(b">", idx)
        if end >= 0:
            return body[: end + 1] + snippet + body[end + 1 :]
    return snippet + body


def _inject_embed_guard(body: bytes, prefix: str) -> bytes:
    marker = json.dumps(prefix)
    script = (
        "<script>(function(){var p="
        + marker
        + ";var api="
        + json.dumps(list(OPENCODE_ROOTS))
        + ";"
        + "function isApi(n){return api.some(function(r){return n===r||n.indexOf(r+'/')===0;});}"
        + "function prefixed(u){if(typeof u!=='string'||!u)return u;if(u.charAt(0)==='#')return u;"
        + "try{var x=new URL(u,location.origin);if(x.origin!==location.origin)return u;"
        + "if(x.pathname.indexOf(p)===0)return u;if(!isApi(x.pathname))return u;"
        + "x.pathname=p+x.pathname;return x.pathname+x.search+x.hash;}"
        + "catch(e){return u.charAt(0)==='/'&&u.indexOf(p)!==0&&isApi(u.split('?')[0])?p+u:u;}}"
        + "var ps=history.pushState.bind(history);"
        + "var rs=history.replaceState.bind(history);history.pushState=function(s,t,u){return ps(s,t,u==null?u:prefixed(u));};"
        + "history.replaceState=function(s,t,u){return rs(s,t,u==null?u:prefixed(u));};"
        + "var fo=XMLHttpRequest.prototype.open;XMLHttpRequest.prototype.open=function(m,u){if(typeof u==='string')arguments[1]=prefixed(u);return fo.apply(this,arguments);};"
        + "var ff=window.fetch;window.fetch=function(i,init){if(typeof i==='string')i=prefixed(i);else if(i&&i.url)i=new Request(prefixed(i.url),i);return ff.call(this,i,init);};"
        + "var WS=window.WebSocket;window.WebSocket=function(u,pr){if(typeof u==='string'){try{var w=new URL(u,location.href);if(w.origin===location.origin&&w.pathname.indexOf(p)!==0)w.pathname=p+w.pathname;u=w.toString();}catch(e){}}"
        + "return pr===undefined?new WS(u):new WS(u,pr);};window.WebSocket.prototype=WS.prototype;"
        + "if(window.EventSource){var ES=window.EventSource;window.EventSource=function(u,c){return c===undefined?new ES(prefixed(String(u||''))):new ES(prefixed(String(u||'')),c);};window.EventSource.prototype=ES.prototype;}"
        + "})();</script>"
    )
    if prefix == OPENCODE_PREFIX:
        script += OPENCODE_TREE_SCRIPT
    return _insert_head(body, script.encode("ascii"))


def _inject_base(body: bytes, prefix: str, content_type: str, request_path: str = "") -> bytes:
    if "html" not in (content_type or "").lower():
        return body
    body = _rewrite_root_urls(body, prefix)
    spa = prefix == OPENCODE_PREFIX and _opencode_spa_route(urlparse(request_path).path or "/")
    if b"<base" not in body.lower() and not spa:
        marker = f'<base href="{prefix}/">'
        lower = body.lower()
        idx = lower.find(b"<head>")
        if idx >= 0:
            insert_at = idx + len(b"<head>")
            body = body[:insert_at] + marker.encode("utf-8") + body[insert_at:]
        else:
            idx = lower.find(b"<head ")
            if idx >= 0:
                end = lower.find(b">", idx)
                if end >= 0:
                    body = body[: end + 1] + marker.encode("utf-8") + body[end + 1 :]
    return _inject_embed_guard(body, prefix)


def _copy_sockets(left, right) -> None:
    pair = [left, right]
    try:
        while True:
            readable, _, broken = select.select(pair, [], pair, 120)
            if broken or not readable:
                break
            for sock in readable:
                other = right if sock is left else left
                chunk = sock.recv(65536)
                if not chunk:
                    return
                other.sendall(chunk)
    except OSError:
        return


def _query_value(request_path: str, name: str) -> str:
    qs = parse_qs(urlparse(request_path).query)
    return (qs.get(name) or [""])[0].strip()


def _decode_opencode_dir(segment: str) -> str:
    if not segment:
        return ""
    raw = (segment or "").strip().replace("-", "+").replace("_", "/")
    pad = "=" * ((4 - len(raw) % 4) % 4)
    try:
        import base64

        return base64.b64decode(raw + pad).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return ""


def _opencode_folder_from_request(request_path: str, referer: str = "") -> str:
    folder = _query_value(request_path, "directory") or _query_value(referer, "directory")
    if folder:
        return folder
    path = urlparse(request_path).path or ""
    if path.startswith(OPENCODE_PREFIX):
        path = path[len(OPENCODE_PREFIX) :] or "/"
    parts = [part for part in path.split("/") if part]
    if not parts or _root_hit("/" + parts[0], OPENCODE_ROOTS):
        return ""
    return _decode_opencode_dir(parts[0])


def _opencode_spa_path(path: str) -> bool:
    stripped = urlparse(path).path or "/"
    if stripped in {"", "/"}:
        return False
    return not _root_hit(stripped, OPENCODE_ROOTS)


def _ensure_engine(prefix: str, request_path: str, referer: str = "") -> None:
    """Start the official engine if the iframe arrived before the tab POST."""
    from . import launch

    port = ENGINES[prefix]
    try:
        if launch._port_open("127.0.0.1", port):
            return
        if prefix == OPENCODE_PREFIX:
            folder = _opencode_folder_from_request(request_path, referer)
            if not folder:
                folder = launch._opencode_cwd or ""
            if not folder:
                return
            launch.start_opencode_web(folder)
            return
        home = (
            _query_value(request_path, "home")
            or _query_value(referer, "home")
            or (launch._hermes_dash_home or "")
        )
        launch.start_hermes_dashboard(home or None)
    except Exception:
        return


def _connect_engine(port: int, timeout: float = 8.0):
    last: OSError | None = None
    for _ in range(20):
        try:
            return socket.create_connection(("127.0.0.1", port), timeout=timeout)
        except OSError as err:
            last = err
            time.sleep(0.4)
    if last is not None:
        raise last
    raise OSError("engine not listening")


def _proxy_websocket(handler, prefix: str, port: int) -> None:
    path = backend_path(handler.path, prefix)
    try:
        backend = _connect_engine(port, timeout=8)
    except OSError as err:
        handler.send_error(502, f"engine proxy: {err}")
        return
    lines = [f"{handler.command} {path} HTTP/1.1"]
    for key, value in handler.headers.items():
        if key.lower() == "host":
            value = f"127.0.0.1:{port}"
        lines.append(f"{key}: {value}")
    payload = ("\r\n".join(lines) + "\r\n\r\n").encode("latin-1")
    backend.sendall(payload)
    handler.close_connection = True
    try:
        _copy_sockets(handler.connection, backend)
    finally:
        try:
            backend.close()
        except OSError:
            pass


def _proxy_http(handler, prefix: str, port: int) -> None:
    path = backend_path(handler.path, prefix)
    length = int(handler.headers.get("Content-Length") or 0)
    body = handler.rfile.read(length) if length else None
    headers: dict[str, str] = {}
    for key, value in handler.headers.items():
        lower = key.lower()
        if lower in HOP:
            continue
        if lower == "host":
            headers["Host"] = f"127.0.0.1:{port}"
        else:
            headers[key] = value
    last_err: Exception | None = None
    resp = None
    payload = b""
    for _ in range(20):
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=120)
        try:
            conn.request(handler.command, path, body=body, headers=headers)
            resp = conn.getresponse()
            payload = resp.read()
            last_err = None
            break
        except (OSError, http.client.HTTPException) as err:
            last_err = err
            time.sleep(0.4)
        finally:
            conn.close()
    if (
        last_err is None
        and resp is not None
        and handler.command == "GET"
        and prefix == OPENCODE_PREFIX
        and resp.status == 404
        and _opencode_spa_path(path)
    ):
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=120)
        try:
            conn.request("GET", "/", headers=headers)
            resp = conn.getresponse()
            payload = resp.read()
            last_err = None
        except (OSError, http.client.HTTPException) as err:
            last_err = err
        finally:
            conn.close()
    if last_err is not None or resp is None:
        handler.send_error(502, f"engine proxy: {last_err or 'not listening'}")
        return
    content_type = resp.getheader("Content-Type") or ""
    payload = _inject_base(payload, prefix, content_type, handler.path)
    try:
        handler.send_response(resp.status, resp.reason)
        for key, value in resp.getheaders():
            if key.lower() in DROP_RESPONSE:
                continue
            if key.lower() == "location":
                value = _rewrite_location(value, prefix)
            handler.send_header(key, value)
        handler.send_header("Content-Length", str(len(payload)))
        handler.send_header("X-Frame-Options", "SAMEORIGIN")
        handler.end_headers()
        handler.wfile.write(payload)
    except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
        return


def maybe_proxy(handler) -> bool:
    """Return True if this request was handled as an engine proxy."""
    target = engine_target(handler.path, handler.headers.get("Referer") or "")
    if not target:
        return False
    if not handler._unlocked():
        handler._json(401, {"error": "locked"})
        return True
    prefix, port = target
    _ensure_engine(prefix, handler.path, handler.headers.get("Referer") or "")
    upgrade = (handler.headers.get("Upgrade") or "").lower()
    if upgrade == "websocket":
        _proxy_websocket(handler, prefix, port)
        return True
    _proxy_http(handler, prefix, port)
    return True

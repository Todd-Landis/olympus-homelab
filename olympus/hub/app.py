#!/usr/bin/env python3
"""Olympus: one dashboard for helios, hephaestus and horae.

Polls an olympus-agent on each host for stats, containers and logs, checks every service
listed in config.json, and pulls a few widgets (Network Watch, Ollama). Stdlib only.
"""
import json
import logging
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import chat

HERE = Path(__file__).parent
CONFIG = json.loads(Path(os.environ.get("CONFIG", HERE / "config.json")).read_text())
BIND = os.environ.get("BIND", "0.0.0.0")
PORT = int(os.environ.get("PORT", "80"))
HISTORY = 180  # samples kept per host (15 min at 5 s)
SUITE_FILES = {"/suite.css": "text/css; charset=utf-8", "/suite.js": "text/javascript; charset=utf-8",
               "/viz.js": "text/javascript; charset=utf-8",
               "/echarts-6.1.0.min.js": "text/javascript; charset=utf-8"}  # vendored from suite/vendor
NETWORK_QUERY_KEYS = {"device", "person", "domain", "category", "status", "start", "end", "hours", "group", "limit", "noise"}

log = logging.getLogger("olympus")
lock = threading.Lock()
state = {"hosts": {}, "services": {}, "widgets": {}, "server_history": {}}


def fetch(url, method="GET", timeout=4, raw=False):
    req = urllib.request.Request(url, method=method, headers={"User-Agent": "olympus"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read()
        return body if raw else (json.loads(body) if body else {})


def agent_error(e):
    if isinstance(e, urllib.error.HTTPError):
        try:
            return json.loads(e.read()).get("error", str(e))
        except Exception:
            return str(e)
    return str(getattr(e, "reason", e))


# ---------------------------------------------------------------- pollers

def poll_host(h):
    name, agent = h["name"], h.get("agent")
    with lock:
        cur = state["hosts"].setdefault(name, {"online": False, "last_seen": None, "stats": None,
                                                "containers": [], "history": deque(maxlen=HISTORY), "error": None})
    if not agent:
        return
    try:
        stats = fetch(agent + "/stats")
        with lock:
            cur.update(online=True, last_seen=time.time(), stats=stats, error=None)
            mem = stats["memory"]
            cur["history"].append({"t": stats["time"], "cpu": stats["cpu"],
                                   "mem": round(100 * mem["used"] / mem["total"], 1),
                                   "rx": stats["net"]["rx"], "tx": stats["net"]["tx"],
                                   "gpu": (stats.get("gpu") or {}).get("util")})
            for g in stats.get("servers", []):
                hist = state["server_history"].setdefault(f'{name}/{g["name"]}', deque(maxlen=HISTORY))
                hist.append({"t": stats["time"], "cpu": g.get("cpu"), "mem": g.get("mem"), "players": g.get("player_count")})
    except Exception as e:
        with lock:
            cur.update(online=False, error=agent_error(e))


def poll_containers(h):
    if not h.get("agent"):
        return
    try:
        data = fetch(h["agent"] + "/containers")
        with lock:
            state["hosts"][h["name"]]["containers"] = data.get("items", [])
    except Exception:
        pass


def check_service(s):
    t0 = time.time()
    url = s.get("check") or s.get("url")
    try:
        fetch(url, timeout=4, raw=True)
        up, code = True, 200
    except urllib.error.HTTPError as e:
        up, code = e.code < 500, e.code  # 401/403 = alive behind a login
    except Exception as e:
        up, code = False, str(getattr(e, "reason", e))
    with lock:
        state["services"][s["id"]] = {"up": up, "code": code, "ms": round((time.time() - t0) * 1000), "checked": time.time()}


def poll_widgets():
    w = {}
    nw = CONFIG.get("widgets", {}).get("network_watch")
    if nw:
        try:
            s = fetch(nw + "/api/summary?hours=24&noise=1", timeout=5)
            w["network"] = {"queries": s["queries"], "blocked": s["blocked"], "sites": s["sites"],
                            "top": s["top"][:6], "series": [p["queries"] for p in s["series"]],
                            "devices": [{"name": d["name"], "queries": d["queries"]} for d in s["devices"][:5]],
                            "url": nw}
            w["network"]["pool"] = fetch(nw + "/api/lan", timeout=5)["pool"]  # home-address usage
        except Exception as e:
            w["network"] = {"error": str(e), "url": nw}
    models = []
    for o in CONFIG.get("widgets", {}).get("ollama", []):
        entry = {"host": o["host"], "online": False}
        try:
            tags = fetch(o["url"] + "/api/tags", timeout=3)
            ps = fetch(o["url"] + "/api/ps", timeout=3)
            entry.update(online=True, installed=len(tags.get("models", [])),
                         loaded=[{"name": m["name"], "vram": m.get("size_vram"), "until": m.get("expires_at")}
                                 for m in ps.get("models", [])])
        except Exception:
            pass
        models.append(entry)
    w["ollama"] = models
    with lock:
        state["widgets"] = w


def run_every(every, fn, *items):
    def loop():
        while True:
            try:
                if items:
                    with ThreadPoolExecutor(8) as pool:
                        list(pool.map(fn, items[0]))
                else:
                    fn()
            except Exception as e:
                log.warning("poller %s: %s", fn.__name__, e)
            time.sleep(every)
    threading.Thread(target=loop, daemon=True).start()


# ---------------------------------------------------------------- alerts + API views

def alerts():
    out = []
    for h in CONFIG["hosts"]:
        cur = state["hosts"].get(h["name"], {})
        if h.get("agent") and not cur.get("online"):
            if not h.get("sometimes_off"):
                out.append({"level": "bad", "host": h["name"], "text": f"{h['label']} is unreachable"})
            continue
        st = cur.get("stats") or {}
        for d in st.get("disks", []):
            pct = 100 * d["used"] / d["total"] if d["total"] else 0
            if pct >= 85:
                out.append({"level": "warn", "host": h["name"], "text": f"{h['label']} {d['mount']} is {pct:.0f}% full"})
        for t in st.get("temps", []):
            if t["name"] == "CPU" and t["c"] >= 85:
                out.append({"level": "warn", "host": h["name"], "text": f"{h['label']} CPU at {t['c']:.0f}°C"})
        b = st.get("battery")
        if b and not b.get("ac"):
            out.append({"level": "warn", "host": h["name"], "text": f"{h['label']} is on battery ({b.get('percent')}%)"})
        for c in cur.get("containers", []):
            if c["health"] == "unhealthy" or (c["state"] not in ("running", "created") and not c["status"].startswith("Exited (0)")):
                out.append({"level": "bad", "host": h["name"], "text": f"{c['name']} on {h['label']} is {c['status'].lower()}"})
        for u in st.get("units", []):
            if not u["active"]:
                out.append({"level": "bad", "host": h["name"], "text": f"{u['name']} on {h['label']} is not running"})
    for s in CONFIG["services"]:
        r = state["services"].get(s["id"])
        host_cfg = next((h for h in CONFIG["hosts"] if h["name"] == s["host"]), {})
        if r and not r["up"] and not host_cfg.get("sometimes_off"):
            out.append({"level": "bad", "host": s["host"], "text": f"{s['name']} is down ({r['code']})"})
    pool = (state["widgets"].get("network") or {}).get("pool")
    if pool and pool["pct"] >= 80:
        out.append({"level": "warn", "host": "horae",
                    "text": f"Home network is running low on addresses: {pool['in_use']} of {pool['size']} in use ({pool['pct']:.0f}%)"})
    return out


def servers_view():
    """Game servers from every online host's agent, with recent history (call with lock held)."""
    out = []
    for h in CONFIG["hosts"]:
        cur = state["hosts"].get(h["name"], {})
        if not cur.get("online"):
            continue
        mem_total = ((cur.get("stats") or {}).get("memory") or {}).get("total")
        for g in (cur.get("stats") or {}).get("servers", []):
            out.append({**g, "host": h["name"], "host_label": h["label"], "host_mem_total": mem_total,
                        "history": list(state["server_history"].get(f'{h["name"]}/{g["name"]}', []))})
    return out


def host_summary(h, detail=False):
    cur = state["hosts"].get(h["name"], {})
    containers = cur.get("containers", [])
    out = {
        "name": h["name"], "label": h["label"], "role": h.get("role"), "icon": h.get("icon"),
        "sometimes_off": h.get("sometimes_off", False), "has_agent": bool(h.get("agent")),
        "online": cur.get("online", False), "last_seen": cur.get("last_seen"), "error": cur.get("error"),
        "stats": cur.get("stats"),
        "containers_running": sum(c["state"] == "running" for c in containers),
        "containers_total": len(containers),
        "spark": [p["cpu"] for p in list(cur.get("history", []))[-60:]],
    }
    if detail:
        out["history"] = list(cur.get("history", []))
        out["containers"] = containers
        out["services"] = [{**s, **state["services"].get(s["id"], {})} for s in CONFIG["services"] if s["host"] == h["name"]]
    return out


def api_state():
    with lock:
        return {
            "time": time.time(),
            "hosts": [host_summary(h) for h in CONFIG["hosts"]],
            "services": [{**s, **state["services"].get(s["id"], {})} for s in CONFIG["services"]],
            "widgets": state["widgets"],
            "servers": servers_view(),
            "alerts": alerts(),
        }


def host_detail(name):
    h = next((h for h in CONFIG["hosts"] if h["name"] == name), None)
    if not h:
        raise ValueError("unknown host")
    with lock:
        return {**host_summary(h, detail=True), "alerts": [a for a in alerts() if a["host"] == h["name"]],
                "servers": [g for g in servers_view() if g["host"] == h["name"]]}


def container_logs(host, cid, tail):
    return fetch(f"{agent_for(host)}/containers/{cid}/logs?tail={int(tail)}", timeout=15).get("lines", [])


def agent_for(host):
    h = next((h for h in CONFIG["hosts"] if h["name"] == host), None)
    if not h or not h.get("agent"):
        raise ValueError("unknown host")
    return h["agent"]


# ---------------------------------------------------------------- HTTP

class Handler(BaseHTTPRequestHandler):
    server_version = "olympus"

    def log_message(self, fmt, *args):
        pass

    def _send(self, code, body, ctype="application/json", cache="no-store"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", cache)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(url.query)
        try:
            if url.path in ("/", "/index.html"):
                return self._send(200, (HERE / "static" / "index.html").read_bytes(), "text/html; charset=utf-8")
            if url.path in SUITE_FILES:
                cache = "public, max-age=604800, immutable" if "echarts" in url.path else "no-store"  # versioned name
                return self._send(200, (HERE / "static" / url.path.lstrip("/")).read_bytes(), SUITE_FILES[url.path], cache)
            if url.path == "/api/state":
                return self._send(200, api_state())
            m = re.match(r"^/api/host/([a-z0-9-]+)$", url.path)
            if m:
                h = next((h for h in CONFIG["hosts"] if h["name"] == m.group(1)), None)
                if not h:
                    return self._send(404, {"error": "unknown host"})
                return self._send(200, host_detail(h["name"]))
            if url.path in ("/api/devices", "/api/network/query"):
                nw = CONFIG.get("widgets", {}).get("network_watch")
                if not nw:
                    return self._send(404, {"error": "Network Watch isn't configured"})
                if url.path == "/api/devices":
                    return self._send(200, fetch(nw + "/api/registry", timeout=10))
                keep = {k: v for k, v in q.items() if k in NETWORK_QUERY_KEYS}  # charts drilling down, no model involved
                return self._send(200, fetch(nw + "/api/query?" + urllib.parse.urlencode(keep, doseq=True), timeout=20))
            if url.path == "/api/chat/info":
                return self._send(200, {"backends": chat.backends()})
            if url.path == "/api/logs":
                cid = q.get("id", [""])[0]
                if not re.match(r"^[0-9a-f]{12,64}$", cid):
                    return self._send(400, {"error": "bad container id"})
                tail = int(q.get("tail", ["300"])[0])
                return self._send(200, fetch(f"{agent_for(q.get('host', [''])[0])}/containers/{cid}/logs?tail={tail}", timeout=15))
            self._send(404, {"error": "not found"})
        except ValueError as e:
            self._send(400, {"error": str(e)})
        except Exception as e:
            self._send(502, {"error": agent_error(e)})

    def do_POST(self):
        # JSON-only: browsers won't send this cross-site without a CORS preflight.
        if not self.headers.get("Content-Type", "").startswith("application/json"):
            return self._send(415, {"error": "JSON only"})
        path = urllib.parse.urlparse(self.path).path
        if path == "/api/chat":
            return self.chat()
        if path == "/api/devices":
            return self.save_device()
        if path != "/api/action":
            return self._send(404, {"error": "not found"})
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
            cid, action = str(body.get("id", "")), body.get("action")
            if not re.match(r"^[0-9a-f]{12,64}$", cid) or action not in ("start", "stop", "restart"):
                return self._send(400, {"error": "bad request"})
            fetch(f"{agent_for(body.get('host', ''))}/containers/{cid}/{action}", method="POST", timeout=70)
            for h in CONFIG["hosts"]:
                if h["name"] == body["host"]:
                    poll_containers(h)
            self._send(200, {"ok": True})
        except ValueError as e:
            self._send(400, {"error": str(e)})
        except Exception as e:
            self._send(502, {"error": agent_error(e)})


    def save_device(self):
        nw = CONFIG.get("widgets", {}).get("network_watch")
        try:
            body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
            req = urllib.request.Request(nw + "/api/registry", data=body, method="POST",
                                         headers={"Content-Type": "application/json", "User-Agent": "olympus"})
            with urllib.request.urlopen(req, timeout=10) as r:
                return self._send(200, json.loads(r.read()))
        except urllib.error.HTTPError as e:
            return self._send(e.code, {"error": agent_error(e)})
        except Exception as e:
            return self._send(502, {"error": agent_error(e)})

    def chat(self):
        """Server-sent events: one JSON object per step, tile and answer, as they happen."""
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        except ValueError:
            return self._send(400, {"error": "bad JSON"})
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()

        def emit(ev):
            self.wfile.write(f"data: {json.dumps(ev, default=str)}\n\n".encode())
            self.wfile.flush()
        try:
            chat.ask(body, emit)
        except (BrokenPipeError, ConnectionResetError):
            pass  # the page went away mid-answer
        except Exception as e:
            log.exception("chat failed")
            try:
                emit({"type": "error", "text": f"Something broke: {e}"})
            except OSError:
                pass


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run_every(5, poll_host, CONFIG["hosts"])
    run_every(10, poll_containers, CONFIG["hosts"])
    run_every(20, check_service, CONFIG["services"])
    run_every(15, poll_widgets)
    chat.init(CONFIG, api_state, host_detail, container_logs)
    log.info("Olympus on %s:%d with %d hosts, %d services", BIND, PORT, len(CONFIG["hosts"]), len(CONFIG["services"]))
    ThreadingHTTPServer((BIND, PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()

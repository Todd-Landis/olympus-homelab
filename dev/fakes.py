#!/usr/bin/env python3
"""Stand-ins for the real home lab, so the UI can run anywhere (a laptop, a cloud session) with believable data.

  - Olympus agents for helios and horae (hephaestus stays "off", like it usually is)
  - a scripted Ollama: picks a tool from keywords in the question, then answers in one sentence.
    It is NOT a model; it only exists so chat pages render real tiles. Use the real one to judge answers.
  - a seeded Network Watch database: 7 days, four devices, three people, a daily and weekly rhythm
  - a Pi-hole API with just enough for Network Watch: no new lookups, your blocks, the adult-site list and the
    privacy level behind its two switches. Lowering the privacy level "restarts" it: 3 s of dropped connections.
    POST /api/__reset {"app_sudo": false, "installed": false, ...} sets up a state (dev/ui/states.mjs uses it).

usage: fakes.py <run-dir>      (writes <run-dir>/watch.db and serves on 127.0.0.1:9301/9302/9303/9311)
"""
import json
import math
import random
import sqlite3
import sys
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

RUN = Path(sys.argv[1])
NOW = time.time()


def reply(h, obj, code=200):
    b = json.dumps(obj).encode()
    h.send_response(code)
    h.send_header("Content-Type", "application/json")
    h.send_header("Content-Length", str(len(b)))
    h.end_headers()
    h.wfile.write(b)


def agent(host):
    gpu = host == "helios"

    class Agent(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            t = time.time()
            wave = (math.sin(t / 40) + 1) / 2
            if self.path == "/health":
                return reply(self, {"ok": True})
            if self.path == "/stats":
                return reply(self, {
                    "time": t, "cpu": round(12 + 30 * wave, 1), "cores": 8 if gpu else 4, "load": [0.8, 0.6, 0.5], "uptime": 412000,
                    "memory": {"used": (9.6e9 if gpu else 2.9e9) + 4e8 * wave, "total": 16e9 if gpu else 8e9, "swap_used": 0, "swap_total": 2e9},
                    "disks": [{"mount": "/", "used": 181e9 if gpu else 22e9, "total": 468e9 if gpu else 58e9}] + ([{"mount": "/srv/models", "used": 402e9, "total": 916e9}] if gpu else []),
                    "temps": [{"name": "CPU", "c": 58.0 + 6 * wave if gpu else 49.0 + 3 * wave}],
                    "net": {"rx": 48000 + 90000 * wave, "tx": 9000 + 12000 * wave},
                    "gpu": {"name": "NVIDIA GeForce GTX 1060 6GB", "util": round(40 * wave), "mem_used": 3100, "mem_total": 6144, "temp": 61, "power": 38} if gpu else None,
                    "battery": {"percent": 100, "ac": True, "status": "Full"} if gpu else None,
                    "units": [{"name": "dragonwilds", "active": True, "cpu": 3.2, "mem": 2.1e9}] if gpu else [],
                    "servers": [{"name": "Dragonwilds", "unit": "dragonwilds", "game": "RuneScape: Dragonwilds Dedicated Server",
                                 "build": "25808123", "updated": NOW - 30 * 3600, "running": True, "started": NOW - 6.2 * 3600,
                                 "cpu": round(18 + 25 * wave, 1), "mem": 3.4e9, "world": "zombois_rs",
                                 "players": [{"name": "Todd", "since": t - 2400}, {"name": "Sam", "since": t - 900}], "player_count": 2,
                                 "last_activity": t - 900, "net_version": 118, "mismatch": {"t": t - 3 * 3600, "server": 117, "client": 118},
                                 "last_save": t - 140, "log_found": True,
                                 "events": [{"t": t - 9000, "event": "joined", "player": "Alex"}, {"t": t - 5400, "event": "left", "player": "Alex"},
                                            {"t": t - 2400, "event": "joined", "player": "Todd"}, {"t": t - 900, "event": "joined", "player": "Sam"}]}] if gpu else []})
            if self.path == "/containers":
                items = ([("open-webui", "ghcr.io/open-webui/open-webui:main", "ai-stack"), ("ollama", "ollama/ollama:latest", "ai-stack"),
                          ("comfyui", "comfyui:local", "ai-stack"), ("ntfy", "binwiederhier/ntfy", "ai-stack"),
                          ("olympus", "olympus-hub", "olympus"), ("pihole-watch", "python:3.14-slim", "pihole-watch")] if gpu else
                         [("pihole", "pihole/pihole:latest", "pihub"), ("homeassistant", "ghcr.io/home-assistant/home-assistant:stable", "pihub"),
                          ("homepage", "ghcr.io/gethomepage/homepage:latest", "pihub"), ("olympus-agent", "python:3.14-slim", "olympus-agent")])
                return reply(self, {"items": [{"id": f"{i:02x}" * 6, "name": n, "image": img, "state": "running", "status": "Up 4 days",
                                               "health": "healthy" if n in ("pihole", "open-webui") else None, "project": p,
                                               "cpu": round(0.4 + i * 0.7, 1), "mem": {"used": (60 + i * 140) * 2**20}, "ports": []}
                                              for i, (n, img, p) in enumerate(items)]})
            if "/logs" in self.path:
                lines = [f"2026-10-09T{(i // 12) % 24:02d}:{(i * 5) % 60:02d}:00.000000Z "
                         + ("ERROR upstream timed out (8.8.8.8#53)" if i % 37 == 0 else "WARN rate limit hit for 192.168.1.140" if i % 53 == 0
                            else "query[A] api.reddit.com from 192.168.1.154 forwarded") for i in range(400)]
                return reply(self, {"lines": lines})
            reply(self, {"error": "not found"}, 404)
    return Agent


class Ollama(BaseHTTPRequestHandler):
    """Scripted stand-in: keyword -> one tool call -> one canned sentence. Good for screenshots, useless for judging answers."""
    def log_message(self, *a):
        pass

    def do_GET(self):
        if "tags" in self.path:
            return reply(self, {"models": [{"name": "puck:latest"}, {"name": "anansi:latest"}]})
        if "ps" in self.path:
            return reply(self, {"models": [{"name": "puck:latest", "size_vram": 4.1e9}]})
        reply(self, {"version": "0.12.0"})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        last = body["messages"][-1]
        if last["role"] == "tool":
            return reply(self, {"message": {"role": "assistant", "content": ANSWERS.get(body["messages"][-2]["tool_calls"][0]["function"]["name"], "Here's what I found.")}})
        q = last["content"].lower()
        call = next((c for k, c in SCRIPT if k in q), ("homelab_status", {}))
        reply(self, {"message": {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": call[0], "arguments": call[1]}}]}})


SCRIPT = [
    ("dragonwilds", ("game_servers", {})),
    ("adult", ("network_query", {"category": "adult", "group": "device", "hours": 168})),
    ("who used", ("network_query", {"group": "person", "hours": 168})),
    ("busiest", ("network_query", {"group": "weekday_hour", "hours": 168})),
    ("blocked", ("network_query", {"group": "site", "status": "blocked", "hours": 168})),
    ("sam", ("network_query", {"person": "sam", "group": "site", "hours": 48})),
    ("iphone", ("network_query", {"device": "iphone", "hours": 12, "group": "none", "limit": 40})),
    ("each hour", ("network_query", {"group": "hour", "hours": 24})),
    ("error", ("container_logs", {"container": "pihole", "contains": "error"})),
    ("horae", ("machine_details", {"machine": "horae"})),
    ("helios", ("machine_details", {"machine": "helios"})),
    ("model", ("ai_models", {})),
]
ANSWERS = {
    "network_query": "**Todd's iPhone** did most of the browsing this week, mostly YouTube and Reddit. About one lookup in six was a blocked ad or tracker.",
    "container_logs": "Pi-hole logged a handful of **upstream timeouts** to 8.8.8.8, spread through the day. Nothing is failing now.",
    "machine_details": "Horae is healthy: CPU is low, memory is under half, and all four containers are running.",
    "homelab_status": "Everything is up. Hephaestus is off, which is normal.",
    "ai_models": "**puck** is loaded on helios and using about 4 GB of the GPU.",
    "game_servers": "**Todd and Sam** are on Dragonwilds right now; it has been up about 6 hours on build 25808123.",
}


ADULT_LIST = "https://nsfw.oisd.nl"
PIHOLE_START = {"app_sudo": True, "installed": True, "enabled": True, "groups": [0], "privacylevel": 0}


class PiHole(BaseHTTPRequestHandler):
    state = dict(PIHOLE_START)
    deny = {"exact": [], "regex": [{"domain": r"(\.|^)tiktok\.com$", "comment": "Blocked from pihole-watch", "enabled": True, "date_added": NOW - 86400 * 3}]}
    down_until = 0

    def log_message(self, *a):
        pass

    def _go(self, method):
        if time.time() < PiHole.down_until:  # restarting: hang up without a reply
            self.close_connection = True
            return
        url = urllib.parse.urlparse(self.path)
        parts = url.path.split("/")[2:]  # after /api/
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}") if n else {}
        st, lst_path = PiHole.state, "/api/lists/" + urllib.parse.quote(ADULT_LIST, safe="")
        if url.path == "/api/auth":
            return reply(self, {"session": {"valid": True, "sid": "dev-sid"}})
        if url.path == "/api/__reset":
            PiHole.state = {**PIHOLE_START, **body}
            PiHole.down_until = 0
            return reply(self, PiHole.state)
        if url.path == "/api/queries":
            return reply(self, {"queries": [], "cursor": None})
        if url.path == "/api/network/devices":
            return reply(self, {"devices": []})
        if parts[:2] == ["domains", "deny"] and len(parts) >= 3:
            kind = parts[2]
            if method == "GET":
                return reply(self, {"domains": PiHole.deny[kind]})
            if method == "POST":
                PiHole.deny[kind].insert(0, {**body, "date_added": time.time()})
                return reply(self, {"domains": PiHole.deny[kind][:1]}, 201)
            if method == "DELETE":
                d = urllib.parse.unquote(parts[3])
                PiHole.deny[kind] = [x for x in PiHole.deny[kind] if x["domain"] != d]
                return reply(self, {})
        if url.path == lst_path:
            if not st["installed"]:
                return reply(self, {"lists": []})
            if method == "PUT":
                st.update(enabled=bool(body.get("enabled")), groups=list(body.get("groups") or []))
            return reply(self, {"lists": [{"address": ADULT_LIST, "comment": "Adult sites (OISD NSFW), added by adult-content.sh",
                                           "groups": st["groups"], "enabled": st["enabled"], "type": "block", "number": 473658,
                                           "abp_entries": 473658, "status": 2}]})
        if url.path == "/api/config/misc/privacylevel":
            return reply(self, {"config": {"misc": {"privacylevel": st["privacylevel"]}}})
        if url.path == "/api/config" and method == "PATCH":
            if not st["app_sudo"]:
                return reply(self, {"error": {"key": "forbidden", "message": "Unable to change configuration (read-only)"}}, 403)
            level = body["config"]["misc"]["privacylevel"]
            lower = level < st["privacylevel"]
            st["privacylevel"] = level
            if lower:  # the real one restarts to read its history back in
                PiHole.down_until = time.time() + 3
            return reply(self, {"config": {"misc": {"privacylevel": level}}})
        return reply(self, {"error": {"key": "not_found", "message": "Not found"}}, 404)

    def do_GET(self):
        self._go("GET")

    def do_POST(self):
        self._go("POST")

    def do_PUT(self):
        self._go("PUT")

    def do_PATCH(self):
        self._go("PATCH")

    def do_DELETE(self):
        self._go("DELETE")


def seed_network(path):
    """A week of lookups with a daily rhythm (quiet nights, busy evenings) and per-device habits."""
    path.unlink(missing_ok=True)
    db = sqlite3.connect(path)
    db.executescript("CREATE TABLE q (id INTEGER, t REAL, client TEXT, domain TEXT, base TEXT, status TEXT, type TEXT, PRIMARY KEY (id, t));"
                     "CREATE INDEX q_t ON q(t); CREATE INDEX q_base_t ON q(base, t); CREATE INDEX q_client_t ON q(client, t);")
    rnd = random.Random(7)
    devices = {  # ip: (weight, favourite sites)
        "192.168.1.154": (5, ["youtube.com", "reddit.com", "instagram.com", "tiktok.com"]),
        "100.110.215.44": (2, ["youtube.com", "reddit.com", "spotify.com"]),
        "192.168.1.140": (3, ["github.com", "stackoverflow.com", "youtube.com", "claude.ai"]),
        "192.168.1.162": (3, ["roblox.com", "youtube.com", "tiktok.com", "minecraft.net"]),
        "192.168.1.171": (1, ["netflix.com", "hulu.com", "spotify.com"]),
    }
    subs = {"youtube.com": ["www.youtube.com", "i.ytimg.com", "youtubei.googleapis.com"], "reddit.com": ["www.reddit.com", "api.reddit.com"],
            "tiktok.com": ["www.tiktok.com", "v16-webapp.tiktok.com"], "netflix.com": ["www.netflix.com", "api-global.netflix.com"]}
    trackers = ["ads.doubleclick.net", "googleads.g.doubleclick.net", "graph.facebook.com", "app-measurement.com", "browser-intake-datadoghq.com"]
    rows, i = [], 0
    for h in range(7 * 24):
        t0 = NOW - (7 * 24 - h) * 3600
        lt = time.localtime(t0)
        daily = [0.15, 0.08, 0.05, 0.04, 0.04, 0.08, 0.3, 0.6, 0.7, 0.6, 0.55, 0.6, 0.7, 0.6, 0.6, 0.7, 0.85, 1.0, 1.1, 1.2, 1.15, 1.0, 0.7, 0.35][lt.tm_hour]
        weekend = 1.25 if lt.tm_wday >= 5 else 1.0
        for ip, (w, favs) in devices.items():
            for _ in range(int(rnd.gauss(14 * w * daily * weekend, 3)) if daily > 0.05 else 0):
                if rnd.random() < 0.16:
                    dom = rnd.choice(trackers)
                    base, status = ".".join(dom.split(".")[-2:]), "GRAVITY"
                else:
                    base = rnd.choice(favs) if rnd.random() < 0.85 else rnd.choice(["wikipedia.org", "amazon.com", "nytimes.com", "weather.gov"])
                    dom, status = rnd.choice(subs.get(base, ["www." + base, base])), "FORWARDED"
                rows.append((i, t0 + rnd.random() * 3600, ip, dom, base, status, "A"))
                i += 1
    # a few late-night lookups of made-up domains that dev/stack.sh puts on the "adult" category list
    for k in range(40):
        t0 = NOW - rnd.randint(0, 6) * 86400 - rnd.choice([1, 2, 3]) * 3600 + rnd.random() * 1800
        dom = rnd.choice(["www.adult-video.example", "cdn.adult-video.example", "nsfw-gallery.example"])
        rows.append((i, t0, rnd.choice(["192.168.1.140", "192.168.1.140", "192.168.1.171"]), dom, ".".join(dom.split(".")[-2:]), "FORWARDED", "A"))
        i += 1
    db.executemany("INSERT INTO q VALUES (?,?,?,?,?,?,?)", rows)
    db.commit()
    return len(rows)


def serve(port, handler):
    s = ThreadingHTTPServer(("127.0.0.1", port), handler)
    Thread(target=s.serve_forever, daemon=True).start()


if __name__ == "__main__":
    RUN.mkdir(parents=True, exist_ok=True)
    n = seed_network(RUN / "watch.db")
    (RUN / "adult-list.txt").write_text("# stand-in for the OISD NSFW list (dev only)\n" + "\n".join(
        ["adult-video.example", "nsfw-gallery.example"] + [f"filler{k}.example" for k in range(200)]) + "\n")
    names = RUN / "names.json"
    if not names.exists():  # starting point for the Devices & people editor; edits made while testing persist per run dir
        names.write_text(json.dumps({"192.168.1.154": "Todd's iPhone", "100.110.215.44": "Todd's iPhone", "192.168.1.140": "desktop-ajq2ikv",
                                     "192.168.1.162": "Sam's iPad"}, indent=2))
        (RUN / "people.json").write_text(json.dumps({"Todd's iPhone": ["Todd"], "desktop-ajq2ikv": ["Todd", "Alex"], "Sam's iPad": ["Sam"]}, indent=2))
    serve(9301, agent("helios"))
    serve(9302, agent("horae"))
    serve(9303, PiHole)
    serve(9311, Ollama)
    print(f"fakes up: {n} lookups seeded", flush=True)
    while True:
        time.sleep(3600)

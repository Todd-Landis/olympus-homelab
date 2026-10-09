#!/usr/bin/env python3
"""pihole-watch: mirrors Pi-hole's query log into SQLite and serves a browsing dashboard.

Stdlib only. Config via environment:
  PIHOLE_URL          Pi-hole base URL (default http://100.123.23.100:8080)
  PIHOLE_SECRET_FILE  file holding a Pi-hole *app password* (default /run/secrets/pihole)
  DB_PATH             SQLite file (default /data/watch.db)
  NAMES_FILE          optional JSON {"ip": "friendly name"} overrides (default /data/names.json)
  PEOPLE_FILE         JSON {"device name": ["person", ...]} (default people.json next to NAMES_FILE)
  TS_SOCKET           tailscaled socket, used to name tailnet devices
  RETENTION_DAYS      days of history to keep (default 30)
  SYNC_SECONDS        how often to pull from Pi-hole (default 60)
  PORT                HTTP port (default 8095)
"""
import http.client
import json
import logging
import os
import re
import socket
import sqlite3
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PIHOLE_API = os.environ.get("PIHOLE_URL", "http://100.123.23.100:8080").rstrip("/") + "/api"
SECRET_FILE = Path(os.environ.get("PIHOLE_SECRET_FILE", "/run/secrets/pihole"))
DB_PATH = os.environ.get("DB_PATH", "/data/watch.db")
NAMES_FILE = Path(os.environ.get("NAMES_FILE", "/data/names.json"))
PEOPLE_FILE = Path(os.environ.get("PEOPLE_FILE", str(NAMES_FILE.with_name("people.json"))))
TS_SOCKET = os.environ.get("TS_SOCKET", "/var/run/tailscale/tailscaled.sock")
RETENTION_DAYS = int(os.environ.get("RETENTION_DAYS", "30"))
SYNC_SECONDS = int(os.environ.get("SYNC_SECONDS", "60"))
PORT = int(os.environ.get("PORT", "8095"))
STATIC = Path(__file__).with_name("static")

SUITE_FILES = {"/suite.css": "text/css; charset=utf-8", "/suite.js": "text/javascript; charset=utf-8"}
BLOCK_COMMENT = "Blocked from pihole-watch"
VISIT_GAP = 300  # seconds of quiet that end one "visit" to a site

BLOCKED = (
    "GRAVITY", "REGEX", "DENYLIST", "GRAVITY_CNAME", "REGEX_CNAME", "DENYLIST_CNAME",
    "EXTERNAL_BLOCKED_IP", "EXTERNAL_BLOCKED_NULL", "EXTERNAL_BLOCKED_NXRA",
    "EXTERNAL_BLOCKED_EDE15", "SPECIAL_DOMAIN",
)
BLOCKED_SQL = "status IN (%s)" % ",".join("'%s'" % s for s in BLOCKED)

# Background chatter from operating systems and infrastructure, hidden when "hide background" is on.
NOISE = {
    "apple.com", "icloud.com", "apple-dns.net", "aaplimg.com", "mzstatic.com", "icloud-content.com",
    "cdn-apple.com", "apple-cloudkit.com", "push.apple.com",
    "microsoft.com", "msftconnecttest.com", "msftncsi.com", "windows.com", "windowsupdate.com",
    "windows.net", "live.com", "microsoftonline.com", "msedge.net", "azureedge.net", "trafficmanager.net",
    "office.net", "skype.com", "s-microsoft.com",
    "tailscale.com", "tailscale.io", "ts.net",
    "gstatic.com", "googleapis.com", "1e100.net", "gvt1.com", "gvt2.com", "googleusercontent.com",
    "akamaiedge.net", "akamai.net", "akamaihd.net", "akadns.net", "edgekey.net", "edgesuite.net",
    "cloudfront.net", "amazonaws.com", "fastly.net", "fastly-edge.com", "cloudflare-dns.com",
    "digicert.com", "letsencrypt.org", "lencr.org", "pki.goog", "sectigo.com", "ocsp.digicert.com",
    "ntp.org", "pool.ntp.org", "time.windows.com", "docker.io", "docker.com", "ubuntu.com",
    "raspberrypi.com", "debian.org", "github.com", "githubusercontent.com", "ghcr.io",
}
MULTI_SUFFIX = {
    "co.uk", "org.uk", "ac.uk", "gov.uk", "com.au", "net.au", "org.au", "co.nz", "co.jp", "ne.jp",
    "com.br", "com.mx", "co.in", "co.za", "com.cn", "com.tw", "com.hk", "co.kr", "com.sg", "com.tr",
}
DOMAIN_RE = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$")

log = logging.getLogger("pihole-watch")


def base_domain(domain):
    parts = domain.rstrip(".").lower().split(".")
    if len(parts) <= 2:
        return ".".join(parts)
    if ".".join(parts[-2:]) in MULTI_SUFFIX:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


# ---------------------------------------------------------------- Pi-hole API

class PiHoleError(Exception):
    pass


class PiHole:
    def __init__(self):
        self.sid = None
        self.lock = threading.Lock()

    def _raw(self, method, path, body=None):
        headers = {"Content-Type": "application/json"}
        if self.sid:
            headers["X-FTL-SID"] = self.sid
        req = urllib.request.Request(
            PIHOLE_API + path, method=method, headers=headers,
            data=json.dumps(body).encode() if body is not None else None)
        with urllib.request.urlopen(req, timeout=30) as resp:
            text = resp.read()
            return json.loads(text) if text else {}

    def _login(self):
        if not SECRET_FILE.is_file():
            raise PiHoleError(f"No Pi-hole app password yet ({SECRET_FILE} missing)")
        self.sid = None
        session = self._raw("POST", "/auth", {"password": SECRET_FILE.read_text().strip()})["session"]
        if not session.get("valid"):
            raise PiHoleError("Pi-hole rejected the app password")
        self.sid = session["sid"]

    def call(self, method, path, body=None):
        with self.lock:
            try:
                if not self.sid:
                    self._login()
                try:
                    return self._raw(method, path, body)
                except urllib.error.HTTPError as e:
                    if e.code != 401:
                        raise
                    self._login()
                    return self._raw(method, path, body)
            except urllib.error.HTTPError as e:
                detail = e.read().decode(errors="replace")
                try:
                    detail = json.loads(detail)["error"]["message"]
                except Exception:
                    pass
                if e.code == 401:
                    self.sid = None
                raise PiHoleError(f"Pi-hole {e.code}: {detail}") from None
            except urllib.error.URLError as e:
                raise PiHoleError(f"Can't reach Pi-hole: {e.reason}") from None


# ---------------------------------------------------------------- device names

class UnixHTTPConnection(http.client.HTTPConnection):
    def __init__(self, path):
        super().__init__("local-tailscaled.sock", timeout=5)
        self.unix_path = path

    def connect(self):
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(5)
        sock.connect(self.unix_path)
        self.sock = sock


class Names:
    """Maps client IPs to friendly names: names.json overrides > Tailscale > IP."""

    def __init__(self):
        self.tailnet = {}
        self.fetched = 0
        self.lock = threading.Lock()

    def _refresh(self):
        if time.time() - self.fetched < 300:
            return
        self.fetched = time.time()
        try:
            conn = UnixHTTPConnection(TS_SOCKET)
            conn.request("GET", "/localapi/v0/status")
            status = json.loads(conn.getresponse().read())
            names = {}
            for peer in [status["Self"], *status.get("Peer", {}).values()]:
                label = (peer.get("DNSName") or "").split(".")[0] or peer.get("HostName") or "?"
                for ip in peer.get("TailscaleIPs", []):
                    names[ip] = label
            self.tailnet = names
        except Exception as e:
            log.warning("tailscale names unavailable: %s", e)

    def mapping(self):
        with self.lock:
            self._refresh()
            names = {"127.0.0.1": "horae", "::1": "horae", **self.tailnet}
            try:
                names.update(json.loads(NAMES_FILE.read_text()))
            except FileNotFoundError:
                pass
            except Exception as e:
                log.warning("bad %s: %s", NAMES_FILE, e)
            return names

    def name(self, ip, mapping=None):
        return (mapping or self.mapping()).get(ip, ip)


# ---------------------------------------------------------------- devices and the people who use them
# A device is every IP that maps to one name. Renaming writes names.json for all of its IPs (so giving a LAN IP
# the same name as a Tailscale device merges them); people.json says who uses each device.

registry_lock = threading.Lock()
NAME_RE = re.compile(r"^[^\x00-\x1f]{1,60}$")


def read_json(path, default):
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        return default
    except Exception as e:
        log.warning("bad %s: %s", path, e)
        return default


def write_json(path, data):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    tmp.replace(path)  # atomic: readers never see half a file


def people_map():
    return {k: v for k, v in read_json(PEOPLE_FILE, {}).items() if isinstance(v, list)}


def api_registry(names):
    with db() as c:
        rows = c.execute("SELECT client, COUNT(*) n, MAX(t) last FROM q WHERE t >= ? GROUP BY client",
                         [time.time() - 86400]).fetchall()
        seen = {r["client"]: r["last"] for r in c.execute(
            "SELECT client, MAX(t) last FROM q WHERE t >= ? GROUP BY client", [time.time() - RETENTION_DAYS * 86400])}
    day = {r["client"]: r["n"] for r in rows}
    people, devs = people_map(), {}
    for ip in set(names) | set(seen):
        name = names.get(ip, ip)
        d = devs.setdefault(name, {"name": name, "ips": [], "people": people.get(name, []), "lookups_24h": 0, "last": None})
        d["ips"].append(ip)
        d["lookups_24h"] += day.get(ip, 0)
        if seen.get(ip):
            d["last"] = max(d["last"] or 0, seen[ip])
    for d in devs.values():
        d["ips"].sort()
    return sorted(devs.values(), key=lambda d: (-(d["last"] or 0), d["name"]))


def api_registry_save(names, body):
    name = str(body.get("name", "")).strip()
    new = str(body.get("new_name") or name).strip()
    people = sorted({str(p).strip()[:40] for p in body.get("people", []) if str(p).strip()})[:8]
    if not NAME_RE.match(new):
        raise ValueError("Names are 1 to 60 characters")
    with registry_lock:
        mapping = names.mapping()
        ips = [ip for ip, n in mapping.items() if n == name]
        if not ips:
            with db() as c:
                if c.execute("SELECT 1 FROM q WHERE client = ? LIMIT 1", [name]).fetchone():
                    ips = [name]  # an unnamed device, known only by its IP
        if not ips:
            raise ValueError(f"No device called {name!r}")
        if new != name:
            overrides = read_json(NAMES_FILE, {})
            overrides.update({ip: new for ip in ips})
            write_json(NAMES_FILE, overrides)
        pm = people_map()
        pm.pop(name, None)
        if people:
            pm[new] = people
        else:
            pm.pop(new, None)
        write_json(PEOPLE_FILE, pm)
    return {"ok": True, "name": new, "ips": ips, "people": people}


# ---------------------------------------------------------------- storage + sync

def db():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    with db() as c:
        c.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS q (
                id INTEGER, t REAL, client TEXT, domain TEXT, base TEXT, status TEXT, type TEXT,
                PRIMARY KEY (id, t));
            CREATE INDEX IF NOT EXISTS q_t ON q(t);
            CREATE INDEX IF NOT EXISTS q_base_t ON q(base, t);
            CREATE INDEX IF NOT EXISTS q_client_t ON q(client, t);
        """)


STATE = {"last_sync": None, "last_error": None, "synced_rows": 0}


def sync_once(ph):
    now = time.time()
    with db() as c:
        last = c.execute("SELECT MAX(t) FROM q").fetchone()[0]
    # Re-read a minute back so in-progress queries get their final status.
    since = last - 60 if last else now - RETENTION_DAYS * 86400
    page, start, cursor, rows = 2000, 0, None, []
    while True:
        path = f"/queries?from={int(since)}&until={int(now) + 1}&length={page}&start={start}"
        if cursor is not None:
            path += f"&cursor={cursor}"
        resp = ph.call("GET", path)
        batch = resp.get("queries", [])
        if cursor is None:
            cursor = resp.get("cursor")
        for x in batch:
            domain = (x.get("domain") or "").lower().rstrip(".")
            if x.get("type") == "PTR" or "." not in domain or domain.endswith(".arpa") or domain == "pi.hole":
                continue
            rows.append((x["id"], x["time"], (x.get("client") or {}).get("ip") or "?", domain,
                         base_domain(domain), x.get("status") or "UNKNOWN", x.get("type")))
        if len(batch) < page:
            break
        start += page
    with db() as c:
        c.executemany("INSERT OR REPLACE INTO q VALUES (?,?,?,?,?,?,?)", rows)
        c.execute("DELETE FROM q WHERE t < ?", (now - RETENTION_DAYS * 86400,))
    return len(rows)


def sync_loop(ph):
    while True:
        try:
            n = sync_once(ph)
            STATE.update(last_sync=time.time(), last_error=None)
            STATE["synced_rows"] += n
        except Exception as e:
            STATE["last_error"] = str(e)
            log.warning("sync failed: %s", e)
        time.sleep(SYNC_SECONDS)


# ---------------------------------------------------------------- queries for the API

class Filters:
    def __init__(self, params, names):
        self.hours = max(1, min(int(float(params.get("hours", ["24"])[0] or 24)), RETENTION_DAYS * 24))
        self.since = time.time() - self.hours * 3600
        self.device = params.get("device", [""])[0]
        self.noise = params.get("noise", ["1"])[0] != "0"  # 1 = hide background
        self.names = names

    def where(self, extra=None):
        sql, args = ["t >= ?"], [self.since]
        if self.device:
            ips = [ip for ip, n in self.names.items() if n == self.device] or [self.device]
            sql.append("client IN (%s)" % ",".join("?" * len(ips)))
            args += ips
        if self.noise:
            sql.append("base NOT IN (%s)" % ",".join("?" * len(NOISE)))
            args += sorted(NOISE)
        if extra:
            sql.append(extra)
        return " AND ".join(sql), args


def api_summary(f):
    w, a = f.where()
    bucket = 3600 if f.hours <= 72 else 86400
    with db() as c:
        per_client = c.execute(
            f"SELECT client, COUNT(*) n, SUM({BLOCKED_SQL}) b, COUNT(DISTINCT base) s, MAX(t) last "
            f"FROM q WHERE {w} GROUP BY client", a).fetchall()
        totals = c.execute(
            f"SELECT COUNT(*) n, SUM({BLOCKED_SQL}) b, COUNT(DISTINCT base) s FROM q WHERE {w}", a).fetchone()
        hist = c.execute(
            f"SELECT CAST((t - ?) / ? AS INT) k, COUNT(*) n, SUM({BLOCKED_SQL}) b FROM q WHERE {w} GROUP BY k",
            [f.since, bucket, *a]).fetchall()
        top = c.execute(
            f"SELECT base, COUNT(*) n FROM q WHERE {w} AND NOT {BLOCKED_SQL} GROUP BY base ORDER BY n DESC LIMIT 10",
            a).fetchall()
    devices = {}
    for r in per_client:
        d = devices.setdefault(f.names.get(r["client"], r["client"]), {"queries": 0, "blocked": 0, "sites": 0, "last": 0, "ips": []})
        d["queries"] += r["n"]; d["blocked"] += r["b"] or 0
        d["sites"] = max(d["sites"], r["s"]); d["last"] = max(d["last"], r["last"]); d["ips"].append(r["client"])
    nb = int(f.hours * 3600 // bucket) + 1
    series = [{"t": f.since + i * bucket, "queries": 0, "blocked": 0} for i in range(nb)]
    for r in hist:
        if 0 <= r["k"] < nb:
            series[r["k"]].update(queries=r["n"], blocked=r["b"] or 0)
    return {
        "queries": totals["n"], "blocked": totals["b"] or 0, "sites": totals["s"],
        "devices": [{"name": k, **v} for k, v in sorted(devices.items(), key=lambda kv: -kv[1]["queries"])],
        "bucket": bucket, "series": series, "top": [dict(r) for r in top],
    }


def api_sites(f):
    w, a = f.where()
    with db() as c:
        rows = c.execute(
            f"SELECT base, client, COUNT(*) n, SUM({BLOCKED_SQL}) b, MIN(t) first, MAX(t) last "
            f"FROM q WHERE {w} GROUP BY base, client", a).fetchall()
    sites = {}
    for r in rows:
        s = sites.setdefault(r["base"], {"site": r["base"], "queries": 0, "blocked": 0, "first": r["first"], "last": 0, "devices": {}})
        s["queries"] += r["n"]; s["blocked"] += r["b"] or 0
        s["first"] = min(s["first"], r["first"]); s["last"] = max(s["last"], r["last"])
        name = f.names.get(r["client"], r["client"])
        s["devices"][name] = s["devices"].get(name, 0) + r["n"]
    return sorted(sites.values(), key=lambda s: -s["last"])[:3000]


def collapse_visits(events, names):
    """Turn raw lookups into visits: same device + same site, no gap longer than VISIT_GAP."""
    open_, visits = {}, []
    for e in events:
        key = (names.get(e["client"], e["client"]), e["base"])
        v = open_.get(key)
        if v and e["t"] - v["end"] <= VISIT_GAP:
            v["end"] = e["t"]; v["queries"] += 1; v["blocked"] += e["blk"]
            v["domains"].add(e["domain"])
        else:
            v = {"device": key[0], "site": key[1], "start": e["t"], "end": e["t"], "queries": 1,
                 "blocked": e["blk"], "domains": {e["domain"]}}
            open_[key] = v
            visits.append(v)
    for v in visits:
        v["domains"] = sorted(v["domains"])
    return sorted(visits, key=lambda v: -v["start"])


def api_timeline(f):
    w, a = f.where()
    with db() as c:
        events = c.execute(
            f"SELECT t, client, domain, base, {BLOCKED_SQL} blk FROM q WHERE {w} ORDER BY t", a).fetchall()
    return collapse_visits(events, f.names)[:4000]


def api_site(f, site):
    w, a = f.where("base = ?")
    a = [*a, site]
    with db() as c:
        subs = c.execute(
            f"SELECT domain, COUNT(*) n, SUM({BLOCKED_SQL}) b, MAX(t) last FROM q WHERE {w} "
            f"GROUP BY domain ORDER BY n DESC", a).fetchall()
        events = c.execute(
            f"SELECT t, client, domain, base, {BLOCKED_SQL} blk FROM q WHERE {w} ORDER BY t", a).fetchall()
    return {"site": site, "subdomains": [dict(r) for r in subs], "visits": collapse_visits(events, f.names)[:1000]}


def api_blocked(f):
    w, a = f.where(BLOCKED_SQL)
    with db() as c:
        rows = c.execute(
            f"SELECT domain, base, client, status, COUNT(*) n, MAX(t) last FROM q WHERE {w} "
            f"GROUP BY domain, client ORDER BY last DESC LIMIT 2000", a).fetchall()
    merged = {}  # one row per domain + device, even when a device has several IPs
    for r in rows:
        device = f.names.get(r["client"], r["client"])
        m = merged.setdefault((r["domain"], device), {**dict(r), "device": device, "n": 0, "last": 0})
        m["n"] += r["n"]
        m["last"] = max(m["last"], r["last"])
    return sorted(merged.values(), key=lambda m: -m["last"])


def api_query(params, names):
    """One flexible, read-only query over the lookup log (used by Olympus' chat).

    device: friendly name or IP; a case-insensitive part of a name works ("iphone").
    domain: part of a domain ("tiktok", "youtube.com"). status: any | blocked | allowed.
    start/end: unix seconds (default: the last `hours`, default 24).
    person: someone from people.json; matches the devices they use (part of a name works).
    group: site | domain | device | person | hour | day | weekday_hour | none (none = the lookups, newest first).
    """
    p = lambda k, d="": (params.get(k, [d])[0] or d).strip()
    now = time.time()
    end = float(p("end") or now)
    start = float(p("start") or end - float(p("hours", "24")) * 3600)
    start = max(start, now - RETENTION_DAYS * 86400)
    group, status, limit = p("group", "site"), p("status", "any"), max(1, min(int(p("limit", "25")), 200))
    if group not in ("site", "domain", "device", "person", "hour", "day", "weekday_hour", "none") or status not in ("any", "blocked", "allowed"):
        raise ValueError("bad group or status")
    sql, args = ["t >= ?", "t < ?"], [start, end]
    matched = []
    if p("device"):
        want = p("device").lower()
        ips = [ip for ip, n in names.items() if n.lower() == want or ip == want]
        if not ips:
            ips = [ip for ip, n in names.items() if want in n.lower()]
        matched = sorted({names.get(ip, ip) for ip in ips}) or [p("device")]
        ips = ips or [p("device")]
        sql.append("client IN (%s)" % ",".join("?" * len(ips)))
        args += ips
    pm, people_matched = people_map(), []
    if p("person"):
        want = p("person").lower()
        hit = lambda exact: [d for d, ps in pm.items() if any((x.lower() == want) if exact else (want in x.lower()) for x in ps)]
        devs = hit(True) or hit(False)
        people_matched = sorted({x for d in devs for x in pm[d] if want in x.lower()}) or [p("person")]
        ips = [ip for ip, n in names.items() if n in devs] or ["(nobody)"]
        sql.append("client IN (%s)" % ",".join("?" * len(ips)))
        args += ips
    if p("domain"):
        sql.append(r"domain LIKE ? ESCAPE '\'")
        args.append("%" + re.sub(r"[%\\]", "", p("domain").lower()).replace("_", r"\_") + "%")
    if status != "any":
        sql.append(BLOCKED_SQL if status == "blocked" else f"NOT {BLOCKED_SQL}")
    if p("noise", "1") != "0" and not p("domain"):  # asking for a domain by name means you want it, background or not
        sql.append("base NOT IN (%s)" % ",".join("?" * len(NOISE)))
        args += sorted(NOISE)
    w = " AND ".join(sql)
    off = time.localtime(end).tm_gmtoff  # buckets follow the local clock
    with db() as c:
        tot = c.execute(f"SELECT COUNT(*) n, SUM({BLOCKED_SQL}) b FROM q WHERE {w}", args).fetchone()
        if group == "none":
            rows = [{"t": r["t"], "device": names.get(r["client"], r["client"]), "domain": r["domain"],
                     "blocked": bool(r["blk"])}
                    for r in c.execute(f"SELECT t, client, domain, {BLOCKED_SQL} blk FROM q WHERE {w} "
                                       f"ORDER BY t DESC LIMIT ?", [*args, limit])]
        elif group == "weekday_hour":  # Monday = 0; 1970-01-01 was a Thursday
            rows = [{"weekday": r["wd"], "hour": r["hr"], "queries": r["n"], "blocked": r["b"] or 0}
                    for r in c.execute(f"SELECT (lt / 86400 + 3) % 7 wd, (lt % 86400) / 3600 hr, COUNT(*) n, SUM(blk) b FROM "
                                       f"(SELECT CAST(t + ? AS INTEGER) lt, {BLOCKED_SQL} blk FROM q WHERE {w}) GROUP BY wd, hr",
                                       [off, *args])]
        elif group in ("hour", "day"):
            size = 3600 if group == "hour" else 86400
            rows = [{"t": r["k"] * size - off, "queries": r["n"], "blocked": r["b"] or 0}
                    for r in c.execute(f"SELECT CAST((t + ?) / ? AS INT) k, COUNT(*) n, SUM({BLOCKED_SQL}) b "
                                       f"FROM q WHERE {w} GROUP BY k ORDER BY k", [off, size, *args])]
        else:
            col = {"site": "base", "domain": "domain", "device": "client", "person": "client"}[group]
            merged = {}
            for r in c.execute(f"SELECT {col} k, COUNT(*) n, SUM({BLOCKED_SQL}) b, MIN(t) first, MAX(t) last "
                               f"FROM q WHERE {w} GROUP BY {col}", args):
                keys = [r["k"]]
                if group in ("device", "person"):  # one row per device (not per IP), or per person using it
                    keys = [names.get(r["k"], r["k"])]
                    if group == "person":
                        keys = pm.get(keys[0]) or ["Unassigned"]  # a shared device counts for each of its people
                for key in keys:
                    m = merged.setdefault(key, {"name": key, "queries": 0, "blocked": 0, "first": r["first"], "last": 0})
                    m["queries"] += r["n"]; m["blocked"] += r["b"] or 0
                    m["first"] = min(m["first"], r["first"]); m["last"] = max(m["last"], r["last"])
            rows = sorted(merged.values(), key=lambda m: -m["queries"])[:limit]
            if group == "device":
                for m in rows:
                    m["people"] = pm.get(m["name"], [])
    return {"group": group, "start": start, "end": end, "status": status, "device": p("device"), "devices_matched": matched,
            "person": p("person"), "people_matched": people_matched,
            "domain": p("domain"), "queries": tot["n"], "blocked": tot["b"] or 0, "rows": rows}


def site_regex(site):
    return r"(\.|^)" + site.replace(".", r"\.") + "$"


def api_blocklist(ph):
    out = []
    for kind in ("exact", "regex"):
        for d in ph.call("GET", f"/domains/deny/{kind}").get("domains", []):
            out.append({"kind": kind, "domain": d["domain"], "comment": d.get("comment"),
                        "enabled": d.get("enabled"), "added": d.get("date_added")})
    return sorted(out, key=lambda d: -(d["added"] or 0))


def api_block(ph, body):
    target = str(body.get("domain", "")).strip().lower().rstrip(".")
    if not DOMAIN_RE.match(target):
        raise ValueError("That doesn't look like a domain name")
    if body.get("scope") == "exact":
        kind, value = "exact", target
    else:
        kind, value = "regex", site_regex(base_domain(target))
    ph.call("POST", f"/domains/deny/{kind}", {"domain": value, "comment": BLOCK_COMMENT, "enabled": True})
    return {"ok": True, "kind": kind, "domain": value}


def api_unblock(ph, body):
    kind = body.get("kind")
    if kind not in ("exact", "regex"):
        raise ValueError("kind must be exact or regex")
    value = str(body.get("domain", ""))
    ph.call("DELETE", f"/domains/deny/{kind}/" + urllib.parse.quote(value, safe=""))
    return {"ok": True}


# ---------------------------------------------------------------- HTTP

class Handler(BaseHTTPRequestHandler):
    server_version = "pihole-watch"

    def log_message(self, fmt, *args):
        pass

    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)

    def _route(self, method):
        url = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(url.query)
        try:
            if method == "GET" and url.path in ("/", "/index.html"):
                return self._send(200, (STATIC / "index.html").read_bytes(), "text/html; charset=utf-8")
            if method == "GET" and url.path in SUITE_FILES:  # shared Olympus Suite look
                return self._send(200, (STATIC / url.path.lstrip("/")).read_bytes(), SUITE_FILES[url.path])
            if not url.path.startswith("/api/"):
                return self._send(404, {"error": "not found"})
            ph, names = self.server.pihole, self.server.names
            if method == "GET":
                f = Filters(params, names.mapping())
                routes = {
                    "/api/health": lambda: {**STATE, "retention_days": RETENTION_DAYS,
                                            "has_secret": SECRET_FILE.is_file()},
                    "/api/devices": lambda: sorted(set(f.names.values())),
                    "/api/summary": lambda: api_summary(f),
                    "/api/sites": lambda: api_sites(f),
                    "/api/site": lambda: api_site(f, params.get("site", [""])[0]),
                    "/api/timeline": lambda: api_timeline(f),
                    "/api/blocked": lambda: api_blocked(f),
                    "/api/query": lambda: api_query(params, f.names),
                    "/api/registry": lambda: api_registry(f.names),
                    "/api/blocklist": lambda: api_blocklist(ph),
                }
            else:
                # JSON-only POSTs: browsers won't send these cross-site without a CORS preflight.
                if not self.headers.get("Content-Type", "").startswith("application/json"):
                    return self._send(415, {"error": "JSON only"})
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
                routes = {
                    "/api/block": lambda: api_block(ph, body),
                    "/api/unblock": lambda: api_unblock(ph, body),
                    "/api/registry": lambda: api_registry_save(names, body),
                }
            if url.path not in routes:
                return self._send(404, {"error": "not found"})
            return self._send(200, routes[url.path]())
        except (ValueError, PiHoleError) as e:
            return self._send(400 if isinstance(e, ValueError) else 502, {"error": str(e)})
        except Exception as e:
            log.exception("request failed")
            return self._send(500, {"error": str(e)})

    def do_GET(self):
        self._route("GET")

    def do_POST(self):
        self._route("POST")


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    init_db()
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    server.pihole, server.names = PiHole(), Names()
    threading.Thread(target=sync_loop, args=(server.pihole,), daemon=True).start()
    log.info("pihole-watch on :%d, Pi-hole at %s, keeping %d days", PORT, PIHOLE_API, RETENTION_DAYS)
    server.serve_forever()


if __name__ == "__main__":
    main()

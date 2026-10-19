#!/usr/bin/env python3
"""pihole-watch: mirrors Pi-hole's query log into SQLite and serves a browsing dashboard.

Stdlib only. Config via environment:
  PIHOLE_URL          Pi-hole base URL (default http://100.123.23.100:8080)
  PIHOLE_SECRET_FILE  file holding a Pi-hole *app password* (default /run/secrets/pihole)
  DB_PATH             SQLite file (default /data/watch.db)
  NAMES_FILE          optional JSON {"ip": "friendly name"} overrides (default /data/names.json)
  PEOPLE_FILE         JSON {"device name": ["person", ...]} (default people.json next to NAMES_FILE)
  CATEGORY_LISTS      JSON {"category": "list URL or file path"} of domain lists to tag lookups with
                      (default: adult = OISD NSFW). Lists refresh daily into <data>/categories/.
  ADULT_LIST          the Pi-hole blocklist the adult-site filter switch turns on and off (default https://nsfw.oisd.nl)
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
CATEGORY_LISTS = json.loads(os.environ.get("CATEGORY_LISTS", "") or '{"adult": "https://nsfw.oisd.nl/domainswild2"}')
CATEGORY_DIR = Path(DB_PATH).parent / "categories"
CATEGORY_REFRESH = 86400  # seconds between list downloads
PEOPLE_FILE = Path(os.environ.get("PEOPLE_FILE", str(NAMES_FILE.with_name("people.json"))))
TS_SOCKET = os.environ.get("TS_SOCKET", "/var/run/tailscale/tailscaled.sock")
RETENTION_DAYS = int(os.environ.get("RETENTION_DAYS", "30"))
SYNC_SECONDS = int(os.environ.get("SYNC_SECONDS", "60"))
PORT = int(os.environ.get("PORT", "8095"))
SYSLOG_PORT = int(os.environ.get("SYSLOG_PORT", "5514"))            # the ASUS sends its system log here
WIFI_FILE = Path(os.environ.get("WIFI_FILE", "/data/wifi.json"))    # {"wl0": "5016Shoreside", "wl0.1": ...}
DHCP_POOL = os.environ.get("DHCP_POOL", "192.168.50.100-192.168.50.254")
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
    def __init__(self, message, code=None):
        super().__init__(message)
        self.code = code  # Pi-hole's HTTP status; None when it couldn't be reached


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
                raise PiHoleError(f"Pi-hole {e.code}: {detail}", e.code) from None
            except urllib.error.URLError as e:
                raise PiHoleError(f"Can't reach Pi-hole: {e.reason}") from None
            except (ConnectionError, TimeoutError, http.client.HTTPException) as e:  # cut off mid-reply (it restarts)
                raise PiHoleError(f"Can't reach Pi-hole: {e}") from None


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
    """Maps devices (MACs, and IPs without one) to friendly names: names.json > Tailscale > Pi-hole (router DHCP names)
    > maker. A LAN IP gets the name of the device holding it now."""

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
            with db() as c:
                hosts = {r["ip"]: r["name"] for r in c.execute("SELECT ip, name FROM names")}
                dev_hosts = {r["dev"]: r["name"] for r in c.execute("SELECT dev, name FROM devnames")}
                hw = {r["ip"]: (r["mac"], r["vendor"]) for r in c.execute("SELECT ip, mac, vendor FROM devices")}
            try:
                overrides = json.loads(NAMES_FILE.read_text())
            except FileNotFoundError:
                overrides = {}
            except Exception as e:
                log.warning("bad %s: %s", NAMES_FILE, e)
                overrides = {}
            # Keys are IPs, hardware (MAC) addresses, or router hostnames (case-insensitive) for devices without a fixed IP.
            by_key = {k.lower(): v for k, v in overrides.items()}
            vendors = {m: v for m, v in hw.values()}
            # Named on purpose: by MAC, or by the reserved IP it holds. These may merge devices (that's how renames merge).
            chosen = {m: by_key[m] for m in vendors if m in by_key}
            for ip, (m, _) in hw.items():
                if ip in overrides and m not in chosen:
                    chosen[m] = overrides[ip]
            # Automatic names, weakest first. Fallback for devices that never send a name: maker + end of the hardware
            # address, e.g. "TP-Link ·e3:20". Then the router hostname, or names.json's name for that hostname.
            auto = {m: f"{short_vendor(v) or 'Device'} ·{m[-5:]}" for m, v in vendors.items()}
            for key, host in {**hosts, **dev_hosts}.items():
                auto[key] = by_key.get(host.lower(), host)
            # A hostname isn't an identity: two Macs both called "Mac" stay two devices ("Mac ·35:c1", "Mac ·bd:26").
            # Renamed devices still count, so naming one doesn't change the other's name.
            shared = {}
            for m in vendors:
                shared.setdefault(auto[m], []).append(m)
            for name, ms in shared.items():
                if len(ms) > 1:
                    for m in ms:
                        auto[m] = name if name.endswith(m[-5:]) else f"{name} ·{m[-5:]}"
            names = {**auto, "127.0.0.1": "horae", "::1": "horae", **self.tailnet, **chosen}
            names.update(overrides)
            for ip, (m, _) in hw.items():
                if ip not in overrides:
                    names[ip] = names[m]
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


SPLIT_SUFFIX = re.compile(r" ·[0-9a-f]{2}:[0-9a-f]{2}$")


def people_map(names=None):
    pm = {k: v for k, v in read_json(PEOPLE_FILE, {}).items() if isinstance(v, list)}
    for n in set((names or {}).values()):  # "iPad ·e2:48" keeps the people given to "iPad" before it was split
        base = SPLIT_SUFFIX.sub("", n)
        if n not in pm and base != n and base in pm:
            pm[n] = pm[base]
    return pm


def api_registry(names):
    with db() as c:
        rows = c.execute("SELECT dev, COUNT(*) n, MAX(t) last FROM q WHERE t >= ? GROUP BY dev",
                         [time.time() - 86400]).fetchall()
        seen = {r["dev"]: r["last"] for r in c.execute(
            "SELECT dev, MAX(t) last FROM q WHERE t >= ? GROUP BY dev", [time.time() - RETENTION_DAYS * 86400])}
    day = {r["dev"]: r["n"] for r in rows}
    people, devs = people_map(names), {}
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
                if c.execute("SELECT 1 FROM q WHERE dev = ? LIMIT 1", [name]).fetchone():
                    ips = [name]  # an unnamed device, known only by its IP or MAC
        if not ips:
            raise ValueError(f"No device called {name!r}")
        if new != name:
            overrides = read_json(NAMES_FILE, {})
            lan = lan_info()
            for ip in ips:
                # Prefer the MAC: home devices get automatic IPs, so an IP key could later label a different device.
                key = (lan.get(ip) or {}).get("mac") or ip
                overrides[key] = new
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
            CREATE TABLE IF NOT EXISTS names (ip TEXT PRIMARY KEY, name TEXT, t REAL);
            CREATE TABLE IF NOT EXISTS devices (ip TEXT PRIMARY KEY, mac TEXT, vendor TEXT, t REAL);
            CREATE TABLE IF NOT EXISTS wifi (mac TEXT PRIMARY KEY, iface TEXT, connected INTEGER, t REAL);
            CREATE TABLE IF NOT EXISTS domcat (domain TEXT PRIMARY KEY, category TEXT);  -- every domain checked; NULL = no list
            CREATE INDEX IF NOT EXISTS domcat_cat ON domcat(category);
        """)
        try:  # added later: when Pi-hole last saw a query from this IP
            c.execute("ALTER TABLE devices ADD COLUMN last REAL")
        except sqlite3.OperationalError:
            pass
        # Added 2026-10-15: dev = the device behind a lookup (its MAC when Pi-hole knows it, else the IP), fixed when the
        # lookup is stored, so history stays with the device when the router hands its IP to another one later.
        c.execute("CREATE TABLE IF NOT EXISTS devnames (dev TEXT PRIMARY KEY, name TEXT, t REAL)")  # dev -> router hostname
        if "dev" not in [r[1] for r in c.execute("PRAGMA table_info(q)")]:
            c.execute("ALTER TABLE q ADD COLUMN dev TEXT")
            # Older rows only have the IP: give them the MAC that holds it now (what names showed before this change).
            c.execute("UPDATE q SET dev = COALESCE((SELECT mac FROM devices d WHERE d.ip = q.client), client)")
            c.execute("INSERT OR IGNORE INTO devnames SELECT COALESCE(d.mac, n.ip), n.name, n.t "
                      "FROM names n LEFT JOIN devices d ON d.ip = n.ip")
        c.execute("CREATE INDEX IF NOT EXISTS q_dev_t ON q(dev, t)")


STATE = {"last_sync": None, "last_error": None, "synced_rows": 0}


def sync_once(ph):
    now = time.time()
    with db() as c:
        last = c.execute("SELECT MAX(t) FROM q").fetchone()[0]
        macs = {r["ip"]: r["mac"] for r in c.execute("SELECT ip, mac FROM devices")}
    # Re-read a minute back so in-progress queries get their final status.
    since = last - 60 if last else now - RETENTION_DAYS * 86400
    page, start, cursor, rows, seen = 2000, 0, None, [], {}
    while True:
        path = f"/queries?from={int(since)}&until={int(now) + 1}&length={page}&start={start}"
        if cursor is not None:
            path += f"&cursor={cursor}"
        resp = ph.call("GET", path)
        batch = resp.get("queries", [])
        if cursor is None:
            cursor = resp.get("cursor")
        for x in batch:
            client = x.get("client") or {}
            if client.get("ip") and client.get("name"):  # hostname Pi-hole got from the router
                seen[client["ip"]] = client["name"].split(".")[0]
            domain = (x.get("domain") or "").lower().rstrip(".")
            if x.get("type") == "PTR" or "." not in domain or domain.endswith(".arpa") or domain == "pi.hole":
                continue
            ip = (x.get("client") or {}).get("ip") or "?"
            rows.append((x["id"], x["time"], ip, domain, base_domain(domain), x.get("status") or "UNKNOWN",
                         x.get("type"), macs.get(ip) or ip))
        if len(batch) < page:
            break
        start += page
    with db() as c:
        c.executemany("INSERT OR REPLACE INTO q (id, t, client, domain, base, status, type, dev) VALUES (?,?,?,?,?,?,?,?)", rows)
        c.executemany("INSERT OR REPLACE INTO names VALUES (?,?,?)", [(ip, n, now) for ip, n in seen.items()])
        c.executemany("INSERT OR REPLACE INTO devnames VALUES (?,?,?)", [(macs.get(ip) or ip, n, now) for ip, n in seen.items()])
        c.execute("DELETE FROM q WHERE t < ?", (now - RETENTION_DAYS * 86400,))
    return len(rows)


def sync_devices(ph):
    """Pi-hole's network table: which hardware address and maker sits behind each IP."""
    now, rows = time.time(), []
    for d in ph.call("GET", "/network/devices?max_devices=500&max_addresses=8").get("devices", []):
        mac = (d.get("hwaddr") or "").lower()
        if not re.match(r"^([0-9a-f]{2}:){5}[0-9a-f]{2}$", mac):
            continue
        for a in d.get("ips", []):
            if a.get("ip"):
                rows.append((a["ip"], mac, d.get("macVendor") or "", now, a.get("lastSeen") or d.get("lastQuery") or 0))
    rows.sort(key=lambda r: r[4])  # Pi-hole remembers old holders of an IP too: the one seen last must win
    with db() as c:
        c.executemany("INSERT OR REPLACE INTO devices (ip, mac, vendor, t, last) VALUES (?,?,?,?,?)", rows)


# ---------------------------------------------------------------- router log (Wi-Fi network per device)

# ASUS wireless events, e.g. "wlceventd: wlceventd_proc_event(...): wl1.1: Assoc AA:BB:CC:DD:EE:FF, status: ..."
WIFI_EVENT = re.compile(r"\b(wl\d+(?:\.\d+)?)\s*:\s*(ReAssoc|Assoc|Auth|Deauth|Disassoc)\w*\s+([0-9a-f]{2}(?::[0-9a-f]{2}){5})", re.I)
ROUTER_LOG = {"lines": 0, "last": None, "events": 0}


def syslog_loop():
    """Receive the router's syslog over UDP; keep the raw lines (capped) and record Wi-Fi joins/leaves."""
    raw = Path(DB_PATH).with_name("router.log")
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", SYSLOG_PORT))
    log.info("listening for router syslog on udp/%d", SYSLOG_PORT)
    while True:
        try:
            data, addr = sock.recvfrom(8192)
            line = data.decode(errors="replace").strip()
            ROUTER_LOG.update(lines=ROUTER_LOG["lines"] + 1, last=time.time())
            if raw.exists() and raw.stat().st_size > 2_000_000:
                raw.replace(raw.with_suffix(".log.1"))
            with raw.open("a") as fh:
                fh.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {addr[0]} {line}\n")
            m = WIFI_EVENT.search(line)
            if m:
                iface, event, mac = m.group(1), m.group(2).lower(), m.group(3).lower()
                joined = event in ("assoc", "reassoc", "auth")
                with db() as c:
                    if joined:
                        c.execute("INSERT OR REPLACE INTO wifi VALUES (?,?,?,?)", (mac, iface, 1, time.time()))
                    else:
                        c.execute("UPDATE wifi SET connected = 0, t = ? WHERE mac = ? AND iface = ?", (time.time(), mac, iface))
                ROUTER_LOG["events"] += 1
        except Exception as e:
            log.warning("syslog: %s", e)


def wifi_labels():
    try:
        return json.loads(WIFI_FILE.read_text())
    except Exception:
        return {}


def lan_info():
    """ip (and mac) -> {mac, vendor, wifi, last} for devices Pi-hole has seen; wifi = network name (or radio, until named)."""
    labels = wifi_labels()
    with db() as c:
        wifi = {r["mac"]: r["iface"] for r in c.execute("SELECT mac, iface FROM wifi")}
        rows = c.execute("SELECT ip, mac, vendor, last FROM devices").fetchall()
    out = {}
    for r in rows:
        iface = wifi.get(r["mac"])
        # wifi.json maps radios to network names, and can also pin a MAC (e.g. a wired device -> "Wired").
        net = labels.get(r["mac"]) or (labels.get(iface, iface) if iface else None)
        out[r["ip"]] = {"mac": r["mac"], "vendor": r["vendor"], "last": r["last"], "wifi": net}
        if r["mac"] not in out or (r["last"] or 0) >= (out[r["mac"]]["last"] or 0):  # by MAC too (lookups' dev key)
            out[r["mac"]] = out[r["ip"]]
    for key, net in labels.items():  # IP keys (e.g. horae, which Pi-hole doesn't list with a MAC)
        if ip_num(key) is not None:
            out.setdefault(key, {"mac": None, "vendor": "", "last": None, "wifi": None})["wifi"] = net
    return out


def ip_num(ip):
    try:
        a, b, c_, d = (int(x) for x in ip.split("."))
        return (a << 24) | (b << 16) | (c_ << 8) | d
    except ValueError:
        return None


def api_lan():
    """Address-pool usage (devices seen in the last 24 h, matching the router's 24 h leases) and Wi-Fi networks."""
    lo, hi = (ip_num(x) for x in DHCP_POOL.split("-"))
    info, now = lan_info(), time.time()
    in_use = sorted({ip for ip, v in info.items() if (n := ip_num(ip)) and lo <= n <= hi and (v["last"] or 0) > now - 86400})
    size = hi - lo + 1
    return {"pool": {"range": DHCP_POOL, "size": size, "in_use": len(in_use), "pct": round(100 * len(in_use) / size, 1)},
            "networks": sorted({v["wifi"] for v in info.values() if v["wifi"]}),
            "router_log": ROUTER_LOG}


VENDOR_TRIM = re.compile(r"[,.]?\s+(inc|corp|corporation|corporate|co|ltd|limited|llc|gmbh|pte|systems|technology|technologies|electronics|international)\b.*$", re.I)


def short_vendor(v):
    """'TP-Link Systems Inc' -> 'TP-Link', 'Espressif Inc.' -> 'Espressif'. Pi-hole says 'Private' for hidden makers."""
    v = (v or "").strip()
    if not v or v.lower() == "private":
        return ""
    return " ".join(VENDOR_TRIM.sub("", v).split()[:2]).rstrip(",.")


def sync_loop(ph):
    last_devices = 0
    while True:
        try:
            if time.time() - last_devices > 300:
                sync_devices(ph)
                last_devices = time.time()
            n = sync_once(ph)
            STATE.update(last_sync=time.time(), last_error=None)
            STATE["synced_rows"] += n
        except Exception as e:
            STATE["last_error"] = str(e)
            log.warning("sync failed: %s", e)
        time.sleep(SYNC_SECONDS)


# ---------------------------------------------------------------- category lists (e.g. adult content)
# A list names domains; a lookup matches if its domain or any parent domain is listed. Domains are classified once
# into the domcat table (new ones every minute; everything again when a list changes), so queries are a simple join.

CATEGORY_STATE = {}


def parse_list(text):
    """Plain domains, "*.domain", hosts files ("0.0.0.0 domain") and Adblock ("||domain^") all work."""
    out = set()
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line or line.startswith("!") or line.startswith("["):
            continue
        parts = line.split()
        d = parts[1] if len(parts) > 1 and re.match(r"^(0\.0\.0\.0|127\.0\.0\.1|::1?)$", parts[0]) else parts[0]
        d = d.lower().removeprefix("||").removeprefix("*.").split("^", 1)[0].rstrip(".")
        if "." in d and DOMAIN_RE.match(d):
            out.add(d)
    return out


def refresh_lists(force=False):
    """Download stale lists (keeping the last good copy on failure) and load them. Returns True if anything changed."""
    CATEGORY_DIR.mkdir(parents=True, exist_ok=True)
    changed = False
    for name, src in CATEGORY_LISTS.items():
        path, st = CATEGORY_DIR / f"{name}.txt", CATEGORY_STATE.setdefault(name, {"domains": set(), "mtime": None, "error": None})
        try:
            if src.startswith(("http://", "https://")):
                if force or not path.exists() or time.time() - path.stat().st_mtime > CATEGORY_REFRESH:
                    req = urllib.request.Request(src, headers={"User-Agent": "pihole-watch (home network monitor)"})
                    with urllib.request.urlopen(req, timeout=120) as r:
                        text = r.read().decode("utf-8", "replace")
                    if len(parse_list(text)) < 100:
                        raise ValueError("downloaded list looks empty")
                    tmp = path.with_suffix(".tmp")
                    tmp.write_text(text)
                    tmp.replace(path)
            else:
                path = Path(src)
            st["error"] = None
        except Exception as e:
            st["error"] = f"update failed, using the last copy: {e}" if path.exists() else f"no list yet: {e}"
            log.warning("category %s: %s", name, e)
        if path.exists() and path.stat().st_mtime != st["mtime"]:
            st["domains"], st["mtime"] = parse_list(path.read_text(errors="replace")), path.stat().st_mtime
            log.info("category %s: %d domains", name, len(st["domains"]))
            changed = True
    return changed


def category_of(domain):
    labels = domain.split(".")
    suffixes = [".".join(labels[i:]) for i in range(len(labels) - 1)]
    for name, st in CATEGORY_STATE.items():
        if any(s in st["domains"] for s in suffixes):
            return name
    return None


def classify(all_again=False):
    with db() as c:
        if all_again:
            c.execute("DELETE FROM domcat")
        new = [r[0] for r in c.execute("SELECT DISTINCT q.domain FROM q LEFT JOIN domcat d ON d.domain = q.domain WHERE d.domain IS NULL")]
        c.executemany("INSERT OR REPLACE INTO domcat VALUES (?, ?)", [(d, category_of(d)) for d in new])
    return len(new)


def category_loop():
    last_refresh = 0
    while True:
        try:
            changed = False
            if time.time() - last_refresh > 3600:  # checks hourly; downloads only when a list is a day old
                changed, last_refresh = refresh_lists(), time.time()
            classify(all_again=changed)
        except Exception as e:
            log.warning("categories: %s", e)
        time.sleep(60)


def api_categories():
    with db() as c:
        counts = dict(c.execute("SELECT category, COUNT(*) FROM domcat WHERE category IS NOT NULL GROUP BY category").fetchall())
    return {name: {"source": CATEGORY_LISTS[name], "list_domains": len(st["domains"]), "updated": st["mtime"],
                   "error": st["error"], "domains_seen": counts.get(name, 0)} for name, st in CATEGORY_STATE.items()}


# ---------------------------------------------------------------- queries for the API

class Filters:
    def __init__(self, params, names):
        self.hours = max(1, min(int(float(params.get("hours", ["24"])[0] or 24)), RETENTION_DAYS * 24))
        self.since = time.time() - self.hours * 3600
        self.device = params.get("device", [""])[0]
        self.wifi = params.get("wifi", [""])[0]
        self.noise = params.get("noise", ["1"])[0] != "0"  # 1 = hide background
        self.names = names
        self.lan = lan_info()

    def where(self, extra=None):
        sql, args = ["t >= ?"], [self.since]
        if self.device:
            keys = [k for k, n in self.names.items() if n == self.device] or [self.device]
            sql.append("dev IN (%s)" % ",".join("?" * len(keys)))
            args += keys
        if self.wifi:
            keys = [k for k, v in self.lan.items() if v["wifi"] == self.wifi] or ["-"]
            sql.append("dev IN (%s)" % ",".join("?" * len(keys)))
            args += keys
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
            f"SELECT dev, GROUP_CONCAT(DISTINCT client) ips, COUNT(*) n, SUM({BLOCKED_SQL}) b, COUNT(DISTINCT base) s, "
            f"MAX(t) last FROM q WHERE {w} GROUP BY dev", a).fetchall()
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
        d = devices.setdefault(f.names.get(r["dev"], r["dev"]), {"queries": 0, "blocked": 0, "sites": 0, "last": 0, "ips": [], "wifi": None})
        d["wifi"] = d["wifi"] or (f.lan.get(r["dev"]) or {}).get("wifi")
        d["queries"] += r["n"]; d["blocked"] += r["b"] or 0
        d["sites"] = max(d["sites"], r["s"]); d["last"] = max(d["last"], r["last"])
        d["ips"] += [ip for ip in (r["ips"] or "").split(",") if ip and ip not in d["ips"]]
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
            f"SELECT base, dev, COUNT(*) n, SUM({BLOCKED_SQL}) b, MIN(t) first, MAX(t) last "
            f"FROM q WHERE {w} GROUP BY base, dev", a).fetchall()
    sites = {}
    for r in rows:
        s = sites.setdefault(r["base"], {"site": r["base"], "queries": 0, "blocked": 0, "first": r["first"], "last": 0, "devices": {}})
        s["queries"] += r["n"]; s["blocked"] += r["b"] or 0
        s["first"] = min(s["first"], r["first"]); s["last"] = max(s["last"], r["last"])
        name = f.names.get(r["dev"], r["dev"])
        s["devices"][name] = s["devices"].get(name, 0) + r["n"]
    return sorted(sites.values(), key=lambda s: -s["last"])[:3000]


def collapse_visits(events, names):
    """Turn raw lookups into visits: same device + same site, no gap longer than VISIT_GAP."""
    open_, visits = {}, []
    for e in events:
        key = (names.get(e["dev"], e["dev"]), e["base"])
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
            f"SELECT t, dev, domain, base, {BLOCKED_SQL} blk FROM q WHERE {w} ORDER BY t", a).fetchall()
    return collapse_visits(events, f.names)[:4000]


def api_site(f, site):
    w, a = f.where("base = ?")
    a = [*a, site]
    with db() as c:
        subs = c.execute(
            f"SELECT domain, COUNT(*) n, SUM({BLOCKED_SQL}) b, MAX(t) last FROM q WHERE {w} "
            f"GROUP BY domain ORDER BY n DESC", a).fetchall()
        events = c.execute(
            f"SELECT t, dev, domain, base, {BLOCKED_SQL} blk FROM q WHERE {w} ORDER BY t", a).fetchall()
    return {"site": site, "subdomains": [dict(r) for r in subs], "visits": collapse_visits(events, f.names)[:1000]}


def api_blocked(f):
    w, a = f.where(BLOCKED_SQL)
    with db() as c:
        rows = c.execute(
            f"SELECT domain, base, client, dev, status, COUNT(*) n, MAX(t) last FROM q WHERE {w} "
            f"GROUP BY domain, dev ORDER BY last DESC LIMIT 2000", a).fetchall()
    merged = {}  # one row per domain + device, even when a device has several IPs
    for r in rows:
        device = f.names.get(r["dev"], r["dev"])
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
        keys = [k for k, n in names.items() if n.lower() == want or k.lower() == want]
        if not keys:
            keys = [k for k, n in names.items() if want in n.lower()]
        matched = sorted({names.get(k, k) for k in keys}) or [p("device")]
        keys = [k for k, n in names.items() if n in matched] + [p("device")]  # an IP or MAC asked for: its whole device
        sql.append("dev IN (%s)" % ",".join("?" * len(keys)))
        args += keys
    pm, people_matched = people_map(names), []
    if p("person"):
        want = p("person").lower()
        hit = lambda exact: [d for d, ps in pm.items() if any((x.lower() == want) if exact else (want in x.lower()) for x in ps)]
        devs = hit(True) or hit(False)
        people_matched = sorted({x for d in devs for x in pm[d] if want in x.lower()}) or [p("person")]
        keys = [k for k, n in names.items() if n in devs] or ["(nobody)"]
        sql.append("dev IN (%s)" % ",".join("?" * len(keys)))
        args += keys
    if p("domain"):
        sql.append(r"domain LIKE ? ESCAPE '\'")
        args.append("%" + re.sub(r"[%\\]", "", p("domain").lower()).replace("_", r"\_") + "%")
    if status != "any":
        sql.append(BLOCKED_SQL if status == "blocked" else f"NOT {BLOCKED_SQL}")
    if p("category"):
        if p("category") not in CATEGORY_LISTS:
            raise ValueError(f"unknown category; known: {', '.join(CATEGORY_LISTS)}")
        sql.append("domain IN (SELECT domain FROM domcat WHERE category = ?)")
        args.append(p("category"))
    if p("noise", "1") != "0" and not p("domain") and not p("category"):  # asked for by name or category: show it all
        sql.append("base NOT IN (%s)" % ",".join("?" * len(NOISE)))
        args += sorted(NOISE)
    w = " AND ".join(sql)
    off = time.localtime(end).tm_gmtoff  # buckets follow the local clock
    with db() as c:
        tot = c.execute(f"SELECT COUNT(*) n, SUM({BLOCKED_SQL}) b FROM q WHERE {w}", args).fetchone()
        if group == "none":
            rows = [{"t": r["t"], "device": names.get(r["dev"], r["dev"]), "domain": r["domain"],
                     "blocked": bool(r["blk"])}
                    for r in c.execute(f"SELECT t, dev, domain, {BLOCKED_SQL} blk FROM q WHERE {w} "
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
            col = {"site": "base", "domain": "domain", "device": "dev", "person": "dev"}[group]
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
            "person": p("person"), "people_matched": people_matched, "category": p("category"),
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


# ---------------------------------------------------------------- switches: the adult-site filter and Incognito
# The filter is Pi-hole's adult-site list (./deploy.sh adult adds it). Off leaves the list enabled, so Pi-hole keeps
# updating it, but takes it out of every group, so it blocks nothing; on puts it back. (Disabling the list instead
# would drop its sites at the next weekly list update, and turning it on again would block nothing until the one after.)
# Incognito is Pi-hole's privacy level 3: it records no lookups at all, so Network Watch has nothing to copy. Changing a
# setting with an app password needs webserver.api.app_sudo (horae/stack/docker-compose.yml turns it on).

ADULT_LIST = os.environ.get("ADULT_LIST", "https://nsfw.oisd.nl")
CONTROLS_FILE = Path(DB_PATH).parent / "controls.json"  # when Incognito began; the groups and privacy level to go back to
INCOGNITO_LEVEL = 3
controls_lock = threading.Lock()


def friendly(e):
    if e.code == 403:
        return PiHoleError("Pi-hole doesn't let Network Watch change settings yet. Run ./deploy.sh horae-stack on the Mac, "
                           "then the sudo command it prints on horae.", 403)
    return e


def adult_list(ph):
    path = "/lists/" + urllib.parse.quote(ADULT_LIST, safe="") + "?type=block"
    try:
        found = ph.call("GET", path).get("lists", [])
    except PiHoleError as e:
        if e.code != 404:
            raise
        found = []
    return path, next((x for x in found if x.get("address") == ADULT_LIST), None)


def privacy_level(ph):
    return int(ph.call("GET", "/config/misc/privacylevel")["config"]["misc"]["privacylevel"])


def api_controls(ph):
    _, lst = adult_list(ph)
    incognito = privacy_level(ph) >= INCOGNITO_LEVEL
    saved = read_json(CONTROLS_FILE, {})
    if not incognito and "incognito_since" in saved:  # turned off in Pi-hole's own settings
        with controls_lock:
            saved = read_json(CONTROLS_FILE, {})
            if saved.pop("incognito_since", None) is not None:
                write_json(CONTROLS_FILE, saved)
    return {
        "filter": {"installed": lst is not None, "on": bool(lst and lst.get("enabled") and lst.get("groups")),
                   "sites": lst and (lst.get("abp_entries") or lst.get("number")) or 0},
        "incognito": {"on": incognito, "since": saved.get("incognito_since")},
    }


def api_filter(ph, body):
    on = body.get("on")
    if not isinstance(on, bool):
        raise ValueError("on must be true or false")
    with controls_lock:
        path, lst = adult_list(ph)
        if lst is None:
            raise ValueError("Pi-hole doesn't have the adult-site list. Add it once with ./deploy.sh adult")
        saved = read_json(CONTROLS_FILE, {})
        if on:
            groups = lst.get("groups") or saved.get("filter_groups") or [0]  # 0: Pi-hole's Default group
        else:
            saved["filter_groups"] = lst.get("groups") or saved.get("filter_groups") or [0]
            write_json(CONTROLS_FILE, saved)
            groups = []
        try:
            ph.call("PUT", path, {"comment": lst.get("comment"), "groups": groups, "type": "block",
                                  "enabled": True if on else bool(lst.get("enabled"))})
        except PiHoleError as e:
            raise friendly(e) from None
        _, after = adult_list(ph)
        if bool(after and after.get("enabled") and after.get("groups")) != on:
            raise PiHoleError("Pi-hole didn't take the change. Check the list on Pi-hole's Lists page.")
    log.info("adult-site filter %s", "on" if on else "off")
    return api_controls(ph)


def api_incognito(ph, body):
    on = body.get("on")
    if not isinstance(on, bool):
        raise ValueError("on must be true or false")
    with controls_lock:
        saved = read_json(CONTROLS_FILE, {})
        level = privacy_level(ph)
        if on and level < INCOGNITO_LEVEL:
            try:
                ph.call("PATCH", "/config", {"config": {"misc": {"privacylevel": INCOGNITO_LEVEL}}})  # applies at once
            except PiHoleError as e:
                raise friendly(e) from None
            saved.update(incognito_since=time.time(), privacy_restore=level)
        elif not on and level >= INCOGNITO_LEVEL:
            back = min(int(saved.get("privacy_restore") or 0), INCOGNITO_LEVEL - 1)
            try:  # recording again means a restart: Pi-hole may drop this reply, and DNS pauses for a few seconds
                ph.call("PATCH", "/config", {"config": {"misc": {"privacylevel": back}}})
            except PiHoleError as e:
                if e.code is not None:
                    raise friendly(e) from None
            deadline = time.time() + 45
            while True:
                try:
                    if privacy_level(ph) < INCOGNITO_LEVEL:
                        break
                except PiHoleError:
                    pass  # still restarting
                if time.time() > deadline:
                    raise PiHoleError("Pi-hole hasn't come back from its restart. Check horae: docker logs --tail 50 pihole")
                time.sleep(2)
            saved.pop("incognito_since", None)
        write_json(CONTROLS_FILE, saved)
    log.info("incognito %s", "on" if on else "off")
    return api_controls(ph)


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
                    "/api/lan": api_lan,
                    "/api/categories": api_categories,
                    "/api/summary": lambda: api_summary(f),
                    "/api/sites": lambda: api_sites(f),
                    "/api/site": lambda: api_site(f, params.get("site", [""])[0]),
                    "/api/timeline": lambda: api_timeline(f),
                    "/api/blocked": lambda: api_blocked(f),
                    "/api/query": lambda: api_query(params, f.names),
                    "/api/registry": lambda: api_registry(f.names),
                    "/api/blocklist": lambda: api_blocklist(ph),
                    "/api/controls": lambda: api_controls(ph),
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
                    "/api/filter": lambda: api_filter(ph, body),
                    "/api/incognito": lambda: api_incognito(ph, body),
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
    threading.Thread(target=syslog_loop, daemon=True).start()
    threading.Thread(target=category_loop, daemon=True).start()
    log.info("pihole-watch on :%d, Pi-hole at %s, keeping %d days", PORT, PIHOLE_API, RETENTION_DAYS)
    server.serve_forever()


if __name__ == "__main__":
    main()

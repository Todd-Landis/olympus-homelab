#!/usr/bin/env python3
"""olympus-agent: host + Docker stats for the Olympus hub, plus container start/stop/restart.

Stdlib only. Runs in Docker with the host's /proc, /sys and / mounted read-only and the
Docker socket mounted. Answers only clients listed in ALLOW (Tailscale addresses are
authenticated by WireGuard, so they can't be spoofed from inside the tailnet).

Environment:
  BIND        address to listen on (the host's Tailscale IP)
  PORT        default 9101
  ALLOW       comma-separated client IPs allowed to talk to the agent
  DISKS       comma-separated host mount points to report, e.g. "/,/srv/models"
  UNITS       comma-separated systemd units to report, e.g. "dragonwilds"
  HOST_PROC / HOST_SYS / HOST_ROOT   where the host's /proc, /sys, / are mounted
"""
import http.client
import json
import os
import re
import shutil
import socket
import subprocess
import threading
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BIND = os.environ.get("BIND", "0.0.0.0")
PORT = int(os.environ.get("PORT", "9101"))
ALLOW = {a.strip() for a in os.environ.get("ALLOW", "127.0.0.1").split(",") if a.strip()}
DISKS = [d.strip() for d in os.environ.get("DISKS", "/").split(",") if d.strip()]
UNITS = [u.strip() for u in os.environ.get("UNITS", "").split(",") if u.strip()]
PROC = os.environ.get("HOST_PROC", "/host/proc")
SYS = os.environ.get("HOST_SYS", "/host/sys")
ROOT = os.environ.get("HOST_ROOT", "/host/root")
DOCKER_SOCK = os.environ.get("DOCKER_SOCK", "/var/run/docker.sock")
HOSTNAME = os.environ.get("HOST_NAME") or open(f"{PROC}/sys/kernel/hostname").read().strip()


def read(path, default=None):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return default


# ---------------------------------------------------------------- host stats

class Host:
    def __init__(self):
        self.prev_cpu = None
        self.prev_net = None
        self.prev_units = {}
        self.snapshot = {}
        self.has_gpu = shutil.which("nvidia-smi") is not None
        self.amd = None if self.has_gpu else self.find_amd()

    def find_amd(self):
        """The AMD card with the most VRAM (skips an integrated GPU), read from sysfs: no tools needed."""
        best = None
        base = f"{SYS}/class/drm"
        for card in sorted(os.listdir(base)) if os.path.isdir(base) else []:
            dev = f"{base}/{card}/device"
            if not re.match(r"^card\d+$", card) or read(f"{dev}/vendor") != "0x1002" or read(f"{dev}/gpu_busy_percent") is None:
                continue
            vram = int(read(f"{dev}/mem_info_vram_total", "0") or 0)
            if not best or vram > best[1]:
                best = (dev, vram)
        return best[0] if best else None

    def cpu(self):
        fields = [int(x) for x in read(f"{PROC}/stat").splitlines()[0].split()[1:]]
        idle, total = fields[3] + fields[4], sum(fields[:8])
        pct = None
        if self.prev_cpu:
            dt = total - self.prev_cpu[1]
            pct = round(100 * (1 - (idle - self.prev_cpu[0]) / dt), 1) if dt else 0.0
        self.prev_cpu = (idle, total)
        return pct

    def memory(self):
        m = {}
        for line in read(f"{PROC}/meminfo").splitlines():
            k, v = line.split(":", 1)
            m[k] = int(v.split()[0]) * 1024
        return {"total": m["MemTotal"], "used": m["MemTotal"] - m["MemAvailable"],
                "swap_total": m.get("SwapTotal", 0), "swap_used": m.get("SwapTotal", 0) - m.get("SwapFree", 0)}

    def network(self):
        rx = tx = 0
        for line in read(f"{PROC}/1/net/dev", "").splitlines()[2:]:
            name, data = line.split(":", 1)
            name = name.strip()
            if name == "lo" or name.startswith(("veth", "docker", "br-")):
                continue
            v = data.split()
            rx += int(v[0]); tx += int(v[8])
        now, rate = time.time(), {"rx": None, "tx": None}
        if self.prev_net:
            dt = now - self.prev_net[0]
            rate = {"rx": round((rx - self.prev_net[1]) / dt), "tx": round((tx - self.prev_net[2]) / dt)}
        self.prev_net = (now, rx, tx)
        return rate

    def temps(self):
        out = []
        base = f"{SYS}/class/hwmon"
        for hw in sorted(os.listdir(base)) if os.path.isdir(base) else []:
            name = read(f"{base}/{hw}/name", hw)
            vals = []
            for f in os.listdir(f"{base}/{hw}"):
                m = re.match(r"temp(\d+)_input$", f)
                if m:
                    v = read(f"{base}/{hw}/{f}")
                    if v and v.lstrip("-").isdigit():
                        vals.append((read(f"{base}/{hw}/temp{m.group(1)}_label", ""), int(v) / 1000))
            if not vals:
                continue
            pkg = [v for l, v in vals if l.lower().startswith("package")]
            label = {"coretemp": "CPU", "cpu_thermal": "CPU", "k10temp": "CPU", "nvme": "NVMe",
                     "amdgpu": "GPU", "pch_cannonlake": "Chipset", "iwlwifi_1": "Wi-Fi"}.get(name, name)
            out.append({"name": label, "c": round(pkg[0] if pkg else max(v for _, v in vals), 1)})
        return out

    def disks(self):
        out = []
        for mount in DISKS:
            try:
                st = os.statvfs(ROOT + (mount if mount != "/" else ""))
            except OSError:
                continue
            total, free = st.f_blocks * st.f_frsize, st.f_bavail * st.f_frsize
            out.append({"mount": mount, "total": total, "used": total - free})
        return out

    def battery(self):
        base = f"{SYS}/class/power_supply"
        for ps in sorted(os.listdir(base)) if os.path.isdir(base) else []:
            if read(f"{base}/{ps}/type") == "Battery":
                ac = any(read(f"{base}/{p}/online") == "1" for p in os.listdir(base)
                         if read(f"{base}/{p}/type") == "Mains")
                cap = read(f"{base}/{ps}/capacity")
                return {"percent": int(cap) if cap and cap.isdigit() else None,
                        "status": read(f"{base}/{ps}/status"), "ac": ac}
        return None

    def amd_gpu(self):
        dev = self.amd
        num = lambda x: float(x) if x and re.match(r"^\d+$", x) else None
        hw = next((f"{dev}/hwmon/{h}" for h in sorted(os.listdir(f"{dev}/hwmon"))), None) if os.path.isdir(f"{dev}/hwmon") else None
        temp = num(read(f"{hw}/temp1_input")) if hw else None
        power = num(read(f"{hw}/power1_average") or read(f"{hw}/power1_input")) if hw else None
        used, total = num(read(f"{dev}/mem_info_vram_used")), num(read(f"{dev}/mem_info_vram_total"))
        return {"name": read(f"{dev}/product_name") or "AMD Radeon", "util": num(read(f"{dev}/gpu_busy_percent")),
                "mem_used": round(used / 2**20) if used is not None else None,      # MiB, like nvidia-smi
                "mem_total": round(total / 2**20) if total is not None else None,
                "temp": temp / 1000 if temp is not None else None, "power": power / 1e6 if power is not None else None}

    def gpu(self):
        if self.amd:
            try:
                return self.amd_gpu()
            except OSError:
                return None
        if not self.has_gpu:
            return None
        try:
            out = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw",
                 "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=5).stdout.strip()
            name, util, used, total, temp, power = [x.strip() for x in out.splitlines()[0].split(",")]
            num = lambda x: float(x) if re.match(r"^[\d.]+$", x) else None
            return {"name": name, "util": num(util), "mem_used": num(used), "mem_total": num(total),
                    "temp": num(temp), "power": num(power)}
        except Exception:
            return None

    def units(self):
        out, now = [], time.time()
        for unit in UNITS:
            name = unit if "." in unit else unit + ".service"
            path = f"{SYS}/fs/cgroup/system.slice/{name}"
            procs = read(f"{path}/cgroup.procs")
            active = bool(procs)
            cpu = None
            usage = read(f"{path}/cpu.stat", "")
            m = re.search(r"usage_usec (\d+)", usage)
            if m:
                u = int(m.group(1))
                prev = self.prev_units.get(name)
                if prev:
                    cpu = round((u - prev[1]) / ((now - prev[0]) * 1e6) * 100, 1)
                self.prev_units[name] = (now, u)
            mem = read(f"{path}/memory.current")
            out.append({"name": unit, "active": active, "cpu": cpu,
                        "mem": int(mem) if mem and mem.isdigit() else None})
        return out

    def collect(self):
        load = read(f"{PROC}/loadavg").split()[:3]
        self.snapshot = {
            "host": HOSTNAME, "time": time.time(), "cpu": self.cpu(), "cores": os.cpu_count(),
            "load": [float(x) for x in load], "uptime": float(read(f"{PROC}/uptime").split()[0]),
            "memory": self.memory(), "net": self.network(), "temps": self.temps(), "disks": self.disks(),
            "battery": self.battery(), "gpu": self.gpu(), "units": self.units(),
        }


# ---------------------------------------------------------------- docker

class UnixHTTPConnection(http.client.HTTPConnection):
    def __init__(self, path, timeout=15):
        super().__init__("docker", timeout=timeout)
        self.unix_path = path

    def connect(self):
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        sock.connect(self.unix_path)
        self.sock = sock


def docker(method, path, timeout=15, raw=False):
    conn = UnixHTTPConnection(DOCKER_SOCK, timeout)
    try:
        conn.request(method, path)
        resp = conn.getresponse()
        body = resp.read()
        if resp.status >= 400:
            try:
                msg = json.loads(body).get("message", body.decode(errors="replace"))
            except Exception:
                msg = body.decode(errors="replace")
            raise RuntimeError(f"Docker {resp.status}: {msg}")
        if raw:
            return body
        return json.loads(body) if body else {}
    finally:
        conn.close()


class Containers:
    def __init__(self):
        self.prev = {}
        self.items = []
        self.error = None

    def _stats(self, cid):
        try:
            return cid, docker("GET", f"/containers/{cid}/stats?stream=false&one-shot=true", timeout=10)
        except Exception:
            return cid, None

    def collect(self):
        try:
            listing = docker("GET", "/containers/json?all=1")
        except Exception as e:
            self.error = str(e)
            return
        running = [c["Id"] for c in listing if c["State"] == "running"]
        with ThreadPoolExecutor(8) as pool:
            stats = dict(pool.map(self._stats, running))
        items = []
        for c in listing:
            s, cpu, mem = stats.get(c["Id"]), None, None
            if s:
                total = s.get("cpu_stats", {}).get("cpu_usage", {}).get("total_usage")
                system = s.get("cpu_stats", {}).get("system_cpu_usage")
                ncpu = s.get("cpu_stats", {}).get("online_cpus") or os.cpu_count()
                prev = self.prev.get(c["Id"])
                # A restarted container's counter starts over; skip one sample instead of going negative.
                if total is not None and system and prev and system > prev[1] and total >= prev[0]:
                    cpu = round((total - prev[0]) / (system - prev[1]) * ncpu * 100, 1)
                if total is not None and system:
                    self.prev[c["Id"]] = (total, system)
                ms = s.get("memory_stats", {})
                if ms.get("usage") is not None:
                    mem = {"used": ms["usage"] - ms.get("stats", {}).get("inactive_file", 0), "limit": ms.get("limit")}
            status = c.get("Status", "")
            health = "healthy" if "(healthy)" in status else "unhealthy" if "(unhealthy)" in status \
                else "starting" if "(health: starting)" in status else None
            labels = c.get("Labels") or {}
            items.append({
                "id": c["Id"][:12], "name": c["Names"][0].lstrip("/"), "image": c["Image"],
                "state": c["State"], "status": status, "health": health, "created": c["Created"],
                "project": labels.get("com.docker.compose.project"),
                "service": labels.get("com.docker.compose.service"),
                "ports": sorted({f"{p.get('IP', '')}:{p['PublicPort']}->{p['PrivatePort']}/{p['Type']}"
                                 for p in c.get("Ports", []) if p.get("PublicPort")}),
                "cpu": cpu, "mem": mem,
            })
        self.items = sorted(items, key=lambda i: (i["project"] or "~", i["name"]))
        self.error = None


def container_logs(cid, tail):
    info = docker("GET", f"/containers/{cid}/json")
    body = docker("GET", f"/containers/{cid}/logs?stdout=1&stderr=1&timestamps=1&tail={tail}", raw=True)
    if info.get("Config", {}).get("Tty"):
        text = body.decode(errors="replace")
    else:  # demultiplex Docker's 8-byte frame headers
        out, i = [], 0
        while i + 8 <= len(body):
            size = int.from_bytes(body[i + 4:i + 8], "big")
            out.append(body[i + 8:i + 8 + size])
            i += 8 + size
        text = b"".join(out).decode(errors="replace")
    return {"name": info["Name"].lstrip("/"), "lines": text.splitlines()[-tail:]}


# ---------------------------------------------------------------- HTTP

HOST, CONTAINERS = Host(), Containers()


def loop(fn, every):
    while True:
        try:
            fn()
        except Exception as e:
            print("collect failed:", e, flush=True)
        time.sleep(every)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _send(self, code, body):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _allowed(self):
        if self.client_address[0] in ALLOW:
            return True
        self._send(403, {"error": "not allowed"})
        return False

    def do_GET(self):
        if not self._allowed():
            return
        url = urllib.parse.urlparse(self.path)
        try:
            if url.path == "/stats":
                return self._send(200, HOST.snapshot)
            if url.path == "/containers":
                return self._send(200, {"items": CONTAINERS.items, "error": CONTAINERS.error})
            m = re.match(r"^/containers/([0-9a-f]{12,64})/logs$", url.path)
            if m:
                tail = max(10, min(int(urllib.parse.parse_qs(url.query).get("tail", ["300"])[0]), 5000))
                return self._send(200, container_logs(m.group(1), tail))
            self._send(404, {"error": "not found"})
        except Exception as e:
            self._send(502, {"error": str(e)})

    def do_POST(self):
        if not self._allowed():
            return
        m = re.match(r"^/containers/([0-9a-f]{12,64})/(start|stop|restart)$", self.path)
        if not m:
            return self._send(404, {"error": "not found"})
        try:
            docker("POST", f"/containers/{m.group(1)}/{m.group(2)}?t=10", timeout=60)
            CONTAINERS.collect()
            self._send(200, {"ok": True})
        except Exception as e:
            self._send(502, {"error": str(e)})


def main():
    HOST.collect()
    threading.Thread(target=loop, args=(HOST.collect, 5), daemon=True).start()
    threading.Thread(target=loop, args=(CONTAINERS.collect, 10), daemon=True).start()
    print(f"olympus-agent {HOSTNAME} on {BIND}:{PORT}, allowing {sorted(ALLOW)}", flush=True)
    ThreadingHTTPServer((BIND, PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()

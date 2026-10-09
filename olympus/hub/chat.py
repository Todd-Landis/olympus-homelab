"""Olympus chat: answers questions about the home lab by calling read-only tools.

The model (local Ollama by default, or Claude) decides which tools to call; the hub runs them, streams each
result to the page as a tile, then streams the model's short answer. Every tool only reads: nothing here can
restart, block or change anything.
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
import uuid
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

log = logging.getLogger("olympus.chat")
TZ = ZoneInfo(os.environ.get("TZ", "America/New_York"))
MAX_ROUNDS = 6          # tool round-trips per question
MODEL_CHARS = 6000      # cap on one tool result as the model sees it (small local models have small contexts)

SYSTEM = """You are the assistant built into Olympus, the dashboard for Todd's home lab.

The home lab:
- helios: always-on Ubuntu laptop (GTX 1060). Runs the AI stack (Open WebUI, ComfyUI, Ollama, ntfy), Olympus and Network Watch.
- horae: Raspberry Pi 4. Runs Pi-hole (DNS and ad blocking for the house), Home Assistant and the Homepage dashboard.
- hephaestus: a tower that is usually off or booted into Windows; it only reports when it runs Ubuntu.
- Network Watch keeps 30 days of every DNS lookup each device made, through Pi-hole: device, domain, time, blocked or not.
  Devices have names, and Todd can say which people use each device (a shared device belongs to several people).

How to answer:
- Look things up with the tools before answering; never guess numbers, names or times.
- The page shows every tool result to Todd as a card right above your answer, so don't repeat it as a table or list.
  Answer in one to three short sentences that say what matters (the answer, anything unusual, what to look at).
- For browsing questions use network_query. Domains are matched by any part ("tiktok" finds www.tiktok.com).
  Device names can be partial ("iphone"). For a person ("what has Sam been doing") use the person filter, which covers
  all their devices. Call network_devices if a device or person doesn't match anything.
- Times are local. Each question ends with the current time; work out start/end from it.
- You can only look. If Todd asks you to restart, block or change something, say where in Olympus or Network to do it.
- Plain text only; **bold** is fine. No headings, no tables."""


class Hub:
    """What chat needs from the hub (set by init)."""
    state = host = logs = None
    network_url = ""
    hosts = []


H = Hub()
CFG = {}
convs = {}
convs_lock = threading.Lock()
ollama_gate = threading.Semaphore(1)   # one local generation at a time; the 1060 can't do two


def init(config, state, host, logs):
    CFG.update(config.get("chat", {}))
    H.state, H.host, H.logs = state, host, logs
    H.network_url = config.get("widgets", {}).get("network_watch", "")
    H.hosts = [h["name"] for h in config["hosts"]]


def now_text():
    return datetime.now(TZ).strftime("%A %d %B %Y, %H:%M %Z")


def local(t):
    return datetime.fromtimestamp(t, TZ).strftime("%a %d %b %H:%M") if t else None


def get_json(url, timeout=10):
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "olympus"}), timeout=timeout) as r:
        return json.loads(r.read())


def post_json(url, body, timeout):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "User-Agent": "olympus"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


# ---------------------------------------------------------------- tools
# Each returns (what the model sees, the tile the page draws). Inputs come from a model: check everything.

def pct(a, b):
    return round(100 * a / b) if b else None


def brief_host(h):
    s = h.get("stats") or {}
    if not h.get("online") or not s:
        return {"name": h["name"], "online": False, "note": "usually off" if h.get("sometimes_off") else h.get("error")}
    disk = (s.get("disks") or [{}])[0]
    cpu_t = next((t["c"] for t in s.get("temps", []) if t["name"] == "CPU"), None)
    out = {"name": h["name"], "online": True, "uptime_h": round((s.get("uptime") or 0) / 3600),
           "cpu_pct": round(s.get("cpu") or 0), "mem_pct": pct(s["memory"]["used"], s["memory"]["total"]),
           "root_disk_pct": pct(disk.get("used", 0), disk.get("total", 0)), "cpu_temp_c": cpu_t,
           "containers": f'{h.get("containers_running")}/{h.get("containers_total")} running'}
    if s.get("gpu"):
        out["gpu"] = {"util_pct": s["gpu"].get("util"), "temp_c": s["gpu"].get("temp"),
                      "vram_mb": f'{s["gpu"].get("mem_used")}/{s["gpu"].get("mem_total")}'}
    if s.get("battery"):
        out["battery"] = {"pct": s["battery"].get("percent"), "on_power": s["battery"].get("ac")}
    return out


def t_status(_):
    st = H.state()
    model = {"machines": [brief_host(h) for h in st["hosts"]],
             "services": [{"name": s["name"], "host": s["host"], "up": s.get("up"), "ms": s.get("ms")} for s in st["services"]],
             "alerts": [a["text"] for a in st["alerts"]]}
    return model, {"kind": "status", "hosts": st["hosts"], "services": st["services"], "alerts": st["alerts"]}


def pick_host(name):
    name = str(name or "").strip().lower()
    match = [h for h in H.hosts if h == name] or [h for h in H.hosts if name and name in h]
    if not match:
        raise ValueError(f"unknown machine {name!r}; machines are {', '.join(H.hosts)}")
    return match[0]


def t_machine(a):
    d = H.host(pick_host(a.get("machine")))
    s = d.get("stats") or {}
    model = {**brief_host(d), "alerts": [x["text"] for x in d.get("alerts", [])],
             "containers": [{"name": c["name"], "state": c["state"], "status": c["status"], "health": c.get("health"),
                             "cpu_pct": c.get("cpu"), "mem_mb": round(c["mem"]["used"] / 2**20) if c.get("mem") else None}
                            for c in d.get("containers", [])]}
    if s:
        model["disks"] = [{"mount": x["mount"], "pct": pct(x["used"], x["total"]), "free_gb": round((x["total"] - x["used"]) / 2**30)} for x in s.get("disks", [])]
        model["temps_c"] = {t["name"]: round(t["c"]) for t in s.get("temps", [])}
        model["system_services"] = [{"name": u["name"], "active": u["active"]} for u in s.get("units", [])]
        model["load"] = s.get("load")
    return model, {"kind": "host", "host": d}


def t_logs(a):
    want = str(a.get("container") or "").strip().lower()
    if not want:
        raise ValueError("container is required")
    hosts = [pick_host(a["machine"])] if a.get("machine") else H.hosts
    every = []
    for h in hosts:
        try:
            every += [(h, c) for c in H.host(h).get("containers", [])]
        except Exception:
            continue
    # An exact name on any machine beats a partial match: "pihole" means pihole on horae, not pihole-watch on helios.
    found = [x for x in every if x[1]["name"].lower() == want] or [x for x in every if want in x[1]["name"].lower()]
    if not found:
        raise ValueError(f"no container matching {want!r}")
    host, c = found[0]
    lines = max(50, min(int(a.get("lines") or 300), 2000))
    raw = H.logs(host, c["id"], lines)
    needle = str(a.get("contains") or "").strip().lower()
    hits = [l for l in raw if needle in l.lower()] if needle else raw
    model = {"machine": host, "container": c["name"], "status": c["status"], "lines_read": len(raw),
             "matching": len(hits), "last_lines": [l[:300] for l in hits[-60:]]}
    return model, {"kind": "logs", "host": host, "container": c["name"], "contains": needle, "read": len(raw), "lines": hits[-400:]}


def parse_local(v):
    v = str(v or "").strip()
    if not v:
        return None
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(v, fmt).replace(tzinfo=TZ).timestamp()
        except ValueError:
            pass
    raise ValueError(f"can't read time {v!r}; use YYYY-MM-DD HH:MM")


def t_network(a):
    if not H.network_url:
        raise ValueError("Network Watch isn't configured")
    q = {"group": a.get("group") or "site", "status": a.get("status") or "any", "limit": int(a.get("limit") or 25)}
    for k in ("device", "domain", "person"):
        if a.get(k):
            q[k] = str(a[k])
    start, end = parse_local(a.get("start")), parse_local(a.get("end"))
    if start:
        q["start"] = start
    if end:
        q["end"] = end
    if not start:
        q["hours"] = float(a.get("hours") or 24)
    if a.get("include_background"):
        q["noise"] = 0
    r = get_json(H.network_url + "/api/query?" + urllib.parse.urlencode(q), timeout=20)
    rows = r["rows"]
    if r["group"] == "none":
        mrows = [{"time": local(x["t"]), "device": x["device"], "domain": x["domain"], "blocked": x["blocked"]} for x in rows]
    elif r["group"] == "weekday_hour":
        days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        mrows = [{"when": f'{days[x["weekday"]]} {x["hour"]:02d}:00', "lookups": x["queries"]} for x in sorted(rows, key=lambda x: -x["queries"])[:12]]
    elif r["group"] in ("hour", "day"):
        mrows = [{"from": local(x["t"]), "lookups": x["queries"], "blocked": x["blocked"]} for x in rows if x["queries"]]
    else:
        mrows = [{"name": x["name"], "lookups": x["queries"], "blocked": x["blocked"], "first": local(x["first"]), "last": local(x["last"])} for x in rows]
    model = {"from": local(r["start"]), "to": local(r["end"]), "device_filter": r["device"] or None,
             "devices_matched": r["devices_matched"], "person_filter": r["person"] or None, "people_matched": r["people_matched"],
             "domain_filter": r["domain"] or None, "status": r["status"],
             "total_lookups": r["queries"], "total_blocked": r["blocked"], "grouped_by": r["group"], "rows": mrows}
    return model, {"kind": "network", **r}


def t_devices(_):
    reg = get_json(H.network_url + "/api/registry")
    return {"devices": [{"name": d["name"], "people": d["people"], "lookups_24h": d["lookups_24h"], "last_seen": local(d["last"])}
                        for d in reg]}, None


def t_models(_):
    o = H.state()["widgets"].get("ollama") or []
    model = [{"host": x["host"], "online": x["online"], "installed": x.get("installed"),
              "loaded": [m["name"] for m in x.get("loaded", [])]} for x in o]
    return {"ollama": model}, {"kind": "models", "ollama": o}


TOOLS = [
    ("homelab_status", t_status,
     "Live state of every machine (online, CPU, memory, disk, temperatures, container counts), every service "
     "(up or down, response time) and current alerts. Use for 'is everything OK?' and anything across machines.",
     {}, []),
    ("machine_details", t_machine,
     "Everything live about one machine: CPU, memory, GPU, disks, temperatures, system services, and every Docker "
     "container with its state, health, CPU and memory.",
     {"machine": {"type": "string", "description": "helios, horae or hephaestus"}}, ["machine"]),
    ("container_logs", t_logs,
     "Recent log lines of one Docker container, optionally only lines containing some text. The machine is found "
     "automatically if you leave it out.",
     {"container": {"type": "string", "description": "Container name or part of it, e.g. 'pihole', 'comfyui'"},
      "machine": {"type": "string", "description": "Optional: helios, horae or hephaestus"},
      "contains": {"type": "string", "description": "Optional: only lines containing this text (case-insensitive), e.g. 'error'"},
      "lines": {"type": "integer", "description": "How many recent lines to read before filtering (default 300, max 2000)"}},
     ["container"]),
    ("network_query", t_network,
     "Search the DNS lookup history (30 days) of every device in the house. Filter by device, by domain and by "
     "blocked/allowed, by person, over a time window, and either group the results (site, domain, device, person, "
     "hour, day, weekday_hour for 'when is it usually busy') or list the individual lookups (group 'none', newest "
     "first). Background noise (OS telemetry, CDNs) is hidden unless include_background is true or you filter by domain.",
     {"device": {"type": "string", "description": "Device name or part of it, e.g. 'iphone'. Leave out for all devices."},
      "person": {"type": "string", "description": "A person's name: covers every device they use. Leave out for everyone."},
      "domain": {"type": "string", "description": "Any part of a domain, e.g. 'tiktok' or 'youtube.com'"},
      "status": {"type": "string", "enum": ["any", "blocked", "allowed"], "description": "Default any"},
      "hours": {"type": "number", "description": "Look back this many hours from now (default 24). Ignored if start is set."},
      "start": {"type": "string", "description": "Optional window start, local time 'YYYY-MM-DD HH:MM'"},
      "end": {"type": "string", "description": "Optional window end, local time 'YYYY-MM-DD HH:MM' (default now)"},
      "group": {"type": "string", "enum": ["site", "domain", "device", "person", "hour", "day", "weekday_hour", "none"],
                "description": "site = per website (default), domain = exact domains, device = per device, person = per person, "
                               "hour/day = activity over time, weekday_hour = usual weekly pattern, none = individual lookups"},
      "limit": {"type": "integer", "description": "Max rows (default 25, max 200)"},
      "include_background": {"type": "boolean", "description": "Include background noise (default false)"}},
     []),
    ("network_devices", t_devices, "Every device Network Watch knows: its name and the people who use it.", {}, []),
    ("ai_models", t_models, "Ollama models installed and currently loaded on helios and hephaestus.", {}, []),
]
TOOL_FNS = {name: fn for name, fn, *_ in TOOLS}
LABELS = {"homelab_status": "Checking every machine", "machine_details": "Looking at {machine}",
          "container_logs": "Reading {container} logs", "network_query": "Searching network history",
          "network_devices": "Listing devices and people", "ai_models": "Checking AI models"}


def schema(props, required):
    return {"type": "object", "properties": props, "required": required}


def claude_tools():
    return [{"name": n, "description": d, "input_schema": schema(p, r)} for n, _, d, p, r in TOOLS]


def ollama_tools():
    return [{"type": "function", "function": {"name": n, "description": d, "parameters": schema(p, r)}} for n, _, d, p, r in TOOLS]


def run_tool(name, args, emit):
    """Run one tool; stream its tile. Returns (text for the model, is_error)."""
    args = args if isinstance(args, dict) else {}
    label = LABELS.get(name, name)
    try:
        label = label.format(**{k: args.get(k, "") for k in ("machine", "container")})
    except Exception:
        pass
    step = uuid.uuid4().hex[:8]
    emit({"type": "step", "id": step, "label": label, "tool": name, "input": args})
    try:
        if name not in TOOL_FNS:
            raise ValueError(f"no tool called {name}")
        model, tile = TOOL_FNS[name](args)
        emit({"type": "step_done", "id": step})
        if tile:
            emit({"type": "tile", "tile": tile})
        text = json.dumps(model, separators=(",", ":"), default=str)
        if len(text) > MODEL_CHARS:
            text = text[:MODEL_CHARS] + '..."(cut: more rows are shown to Todd on the page)"'
        return text, False
    except Exception as e:
        log.info("tool %s failed: %s", name, e)
        emit({"type": "step_done", "id": step, "error": str(e)})
        return f"Error: {e}", True


# ---------------------------------------------------------------- backends

def claude_key():
    p = Path(CFG.get("claude", {}).get("key_file", "/secrets/anthropic.key"))
    try:
        return p.read_text().strip() or None
    except OSError:
        return None


def backends():
    out = []
    o = CFG.get("ollama")
    if o:
        out.append({"id": "ollama", "label": f'Local · {o.get("model", "?")}', "available": True})
    c = CFG.get("claude")
    if c:
        try:
            import anthropic  # noqa: F401  (installed by the hub's Dockerfile)
            ok, why = bool(claude_key()), "Add the API key: see docs/HANDOFF.md"
        except ImportError:
            ok, why = False, "The anthropic package isn't installed in this image"
        out.append({"id": "claude", "label": "Claude", "available": ok, **({} if ok else {"why": why})})
    return out


_claude = None


def claude_client():
    global _claude
    if _claude is None:
        import anthropic
        _claude = anthropic.Anthropic(api_key=claude_key(), timeout=120.0)
    return _claude


def run_claude(conv, question, emit):
    import anthropic
    cfg = CFG["claude"]
    msgs = conv["messages"]
    msgs.append({"role": "user", "content": f"{question}\n\n(Current time: {now_text()})"})
    for _ in range(MAX_ROUNDS):
        try:
            r = claude_client().beta.messages.create(
                model=cfg.get("model", "claude-opus-5-5"),
                max_tokens=16000,
                system=[{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}],
                tools=claude_tools(),
                messages=msgs,
                output_config={"effort": cfg.get("effort", "medium")},
                # On a safety decline, the API retries on a fallback model inside the same call.
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
        except anthropic.AuthenticationError:
            return emit({"type": "error", "text": "Claude rejected the API key. Check the key file on helios."})
        except anthropic.RateLimitError:
            return emit({"type": "error", "text": "Claude is rate-limiting this key. Try again in a minute."})
        except anthropic.APIStatusError as e:
            return emit({"type": "error", "text": f"Claude API error {e.status_code}: {e.message}"})
        except anthropic.APIConnectionError:
            return emit({"type": "error", "text": "Couldn't reach the Claude API from helios."})
        msgs.append({"role": "assistant", "content": r.content})  # unchanged, so thinking blocks stay valid
        text = "".join(b.text for b in r.content if b.type == "text").strip()
        uses = [b for b in r.content if b.type == "tool_use"]
        if r.stop_reason == "refusal":
            return emit({"type": "answer", "text": "Claude declined to answer that one."})
        if r.stop_reason == "tool_use" and uses:
            if text:
                emit({"type": "note", "text": text})
            results = []
            for b in uses:
                out, err = run_tool(b.name, b.input, emit)
                results.append({"type": "tool_result", "tool_use_id": b.id, "content": out, **({"is_error": True} if err else {})})
            msgs.append({"role": "user", "content": results})  # all results in one message
            continue
        if r.stop_reason == "pause_turn":
            continue
        return emit({"type": "answer", "text": text or "(no answer)"})
    emit({"type": "answer", "text": "That took more lookups than I allow for one question. Try asking something narrower."})


THINK_RE = re.compile(r"<think>.*?</think>", re.S)


def run_ollama(conv, question, emit):
    cfg = CFG["ollama"]
    msgs = conv["messages"]
    if not msgs:
        msgs.append({"role": "system", "content": SYSTEM})
    # Small context: keep the system prompt and only the last two questions' worth of history.
    users = [i for i, m in enumerate(msgs) if m["role"] == "user"]
    if len(users) >= 2:
        del msgs[1:users[-2]]
    msgs.append({"role": "user", "content": f"{question}\n\n(Current time: {now_text()})"})
    for _ in range(MAX_ROUNDS):
        body = {"model": cfg["model"], "messages": msgs, "tools": ollama_tools(), "stream": False,
                "keep_alive": cfg.get("keep_alive", "15m"), "options": {"num_ctx": cfg.get("num_ctx", 8192)}}
        if "think" in cfg:
            body["think"] = cfg["think"]
        with ollama_gate:
            try:
                r = post_json(cfg.get("url", "http://127.0.0.1:11434") + "/api/chat", body, timeout=cfg.get("timeout", 300))
            except urllib.error.HTTPError as e:
                detail = e.read().decode(errors="replace")[:300]
                return emit({"type": "error", "text": f"Ollama error {e.code}: {detail}"})
            except Exception as e:
                return emit({"type": "error", "text": f"Couldn't reach Ollama: {getattr(e, 'reason', e)}"})
        m = r.get("message") or {}
        calls = m.get("tool_calls") or []
        msgs.append({"role": "assistant", "content": m.get("content", ""), **({"tool_calls": calls} if calls else {})})
        text = THINK_RE.sub("", m.get("content") or "").strip()
        if not calls:
            return emit({"type": "answer", "text": text or "(no answer)"})
        for c in calls:
            fn = c.get("function") or {}
            args = fn.get("arguments")
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except ValueError:
                    args = {}
            out, _ = run_tool(fn.get("name", ""), args, emit)
            msgs.append({"role": "tool", "tool_name": fn.get("name", ""), "content": out})
    emit({"type": "answer", "text": "That took more lookups than I allow for one question. Try asking something narrower."})


def ask(body, emit):
    """Answer one question, streaming events through emit(). Conversations live in memory for two hours."""
    question = str(body.get("question") or "").strip()[:2000]
    backend = body.get("backend") or "ollama"
    avail = {b["id"]: b for b in backends()}
    if not question:
        return emit({"type": "error", "text": "Ask something first."})
    if backend not in avail or not avail[backend]["available"]:
        return emit({"type": "error", "text": avail.get(backend, {}).get("why", f"{backend} isn't set up")})
    with convs_lock:
        for k in [k for k, c in convs.items() if time.time() - c["t"] > 7200]:
            del convs[k]
        cid = str(body.get("conv") or "")
        conv = convs.get(cid)
        if not conv or conv["backend"] != backend:  # switching model starts a fresh conversation
            cid = uuid.uuid4().hex
            conv = convs[cid] = {"backend": backend, "messages": [], "t": time.time(), "lock": threading.Lock()}
        conv["t"] = time.time()
    emit({"type": "start", "conv": cid, "backend": backend})
    if not conv["lock"].acquire(blocking=False):
        return emit({"type": "error", "text": "Still working on the last question in this conversation."})
    try:
        (run_claude if backend == "claude" else run_ollama)(conv, question, emit)
    finally:
        conv["lock"].release()
    emit({"type": "done"})

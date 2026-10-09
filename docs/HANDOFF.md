# Handoff: olympus-homelab

Written 2026-10-08 at the end of the chat that built all of this. Read `README.md` first for the layout; this file is the
history, current state, open items, and the traps already hit.

## What exists now

**Machines** (Tailscale tailnet `tail247b74.ts.net`, Linux user `synestri` everywhere, SSH key auth only):

| Name | Tailscale IP | LAN | Notes |
|---|---|---|---|
| helios | 100.88.170.59 | 192.168.1.129 (Wi-Fi) | Ubuntu laptop server. Also runs `/opt/ai-stack` (NOT in this repo; see `~/handoff/HANDOFF.md` on helios) |
| horae | 100.123.23.100 | 192.168.1.224 (reserved in router) | Raspberry Pi 4, Pi OS Lite (trixie, cloud-init). Renamed from `pihub` |
| hephaestus | 100.102.134.107 | | Tower, dual boot; only a server in Ubuntu. Usually offline |
| desktop-ajq2ikv | 100.73.62.100 | 192.168.1.140 | Todd's Windows laptop (this PC) |
| iphone181 | 100.110.215.44 | 192.168.1.154 | Todd's iPhone |

**Running services**

- **horae** `/opt/pihub` (compose in `horae/stack/`): Pi-hole (host network, admin `:8080`, DNS `:53`), Home Assistant (`:8123`, host
  network), Homepage (`:80`). Tailscale on, Tailscale SSH off, `--accept-dns=false`.
- **helios** `~/pihole-watch` ("Network", http://helios:8095): Python stdlib app, syncs Pi-hole `/api/queries` every 5 s into
  SQLite (`data/watch.db`, 30-day retention), block/unblock via Pi-hole API. Auth = Pi-hole **app password** in
  `~/pihole-watch/pihole.secret` (600). Device names: Tailscale local API + `data/names.json`.
- **helios** `~/olympus` (http://helios/, port 80 on Tailscale IP): hub polls agents (5 s stats, 10 s containers), checks services
  (20 s), widgets (Network summary, Ollama). Agents on helios and horae (`~/olympus-agent`) listen on `:9101` and only answer
  `100.88.170.59`. Restart/stop/start and logs work through the agent. No login on Olympus or Network.

**DNS / network state**

- Spectrum router (app-managed, can't set LAN DHCP DNS: its "DNS server" fields are the router's own upstream). Pointing them at
  the Pi broke all DNS. Todd set primary back to 192.168.1.1; advice was to use 1.1.1.1 / 1.0.0.1 instead (not confirmed done).
- iPhone: manual DNS 192.168.1.224 on home Wi-Fi.
- Tailscale admin DNS: global nameserver `100.123.23.100` with **Override DNS servers on**, so every tailnet device uses Pi-hole
  while Tailscale is connected.
- Pi-hole runs with host networking so each client shows by its real IP (LAN 192.168.1.x or Tailscale 100.x).
  `172.18.0.1` in old history = Tailscale traffic from before that fix.

**Design** (`suite/`): light only, warm off-white, Inter, Fraunces only for the "Olympus" wordmark, plain labels, thin borders,
one terracotta accent, per-host colors (helios ochre, horae laurel, hephaestus terracotta), tiny sun arc by the clock,
`Ctrl K` search palette in all three apps. Todd **rejected** a heavily themed version (temples/stamps/"Oracle" wording) as an
art project; keep it subtle, modern and readable. No dark mode.

## Open items (Todd's to-do list)

1. **ASUS RT-BE58U router** ordered, replaces the Spectrum router. Plan: same SSID/password/WPA2+WPA3 mixed; set LAN IP to
   `192.168.1.1` so the subnet stays; reserve `88:a2:9e:6f:6f:45` -> `192.168.1.224`; LAN > DHCP Server DNS = `192.168.1.224`;
   point IPv6 DNS at the Pi (or disable it); leave ASUS's built-in AdGuard DNS **off**. Then set the iPhone DNS back to Automatic
   and check new device IPs in `names.json`.
2. **Tailscale exit node**: `~/exit-node.sh` is on horae (IP forwarding + `accept_ra=2` for eth0 so IPv6 survives). Not confirmed
   run/approved yet. After `sudo bash ~/exit-node.sh`, approve in Tailscale admin > Machines > horae > Edit route settings.
3. **Home Assistant**: Todd still needs to create the account, then a long-lived token for a Homepage/Olympus HA widget.
   Don't route the token through chat; have him paste it into a file on the server himself.
4. **This PC**: set Wi-Fi DNS to 192.168.1.224 (optional once the ASUS is in) and switch the network profile to **Private**
   (Windows blocks mDNS on Public, which is why `horae.local` doesn't resolve here).
5. ~~**hephaestus** agent~~ done 2026-10-09: running from `olympus/agent-hephaestus/` (`./deploy.sh hephaestus-agent` while
   it's in Ubuntu; not part of `all` because the tower is often off). AMD GPU stats come from `/sys/class/drm` (agent.py `amd_gpu`); temps from hwmon.
6. Daytime look of the sun arc not visually verified (only seen at night).
7. Possible: add a login to Olympus/Network if the tailnet is ever shared.
9. **Olympus chat** is the main view of http://helios/ (the old overview is the **Dashboard** tab; links to every hosted
   site sit in the header). Questions are answered by a model that calls read-only tools (machine status, container
   logs, Network Watch's `/api/query`); the answer text comes first, then tiles with charts.
   - Charts: Apache ECharts 6.1.0, vendored in `suite/vendor/` (Apache-2.0), drawn by `olympus/hub/static/viz.js`.
     Clicking a bar drills down through the hub's `/api/network/query` without asking the model again.
   - Devices & people: edited on the Dashboard tab; stored by Network Watch in `data/names.json` (renames, all IPs of
     a device) and `data/people.json` (who uses what). The chat can filter and group by person.
   - Local model is `chat.ollama.model` in `olympus/hub/config.json` (must be installed on helios: `ollama pull <name>`).
   - **Local only for now** (Todd's choice; a Pro subscription doesn't cover API use). To turn Claude back on, add
     `"claude": {"model": "claude-opus-5-5", "effort": "medium", "key_file": "/secrets/anthropic.key"}` under `chat`
     in config.json and create the key file below.
   - Claude option: the hub image (`olympus/image/Dockerfile`) has the `anthropic` package; the key lives in
     `~/olympus/secrets/anthropic.key` on helios (created by Todd, never committed or pasted in chat):
     `read -rsp "Anthropic API key: " k && printf '%s' "$k" > ~/olympus/secrets/anthropic.key && chmod 600 ~/olympus/secrets/anthropic.key; unset k`
     Model `claude-opus-5-5`, with server-side refusal fallback on. Only the rows a question looks up leave the house.
   - Read-only by design for now; action buttons (restart, block) in tiles are a planned next step.
8. The Apps panel (iframes of each service on the overview) was tried and removed in favour of the chat.
   `ha-allow-framing.sh` had already set `http: use_x_frame_options: false` in Home Assistant's configuration.yaml on
   horae; it's harmless, but to undo it delete that line (a `.bak-` copy sits next to the file) and restart Home Assistant.

## How to work here

- UI work: follow `.claude/skills/olympus-design` (design system in `docs/DESIGN.md`, history in `docs/design-log.md`).
  `dev/stack.sh start` runs Olympus + Network Watch locally on fake data; `/ui-audit` and `/ui-critique` check it.

- Edit in this repo, then `./deploy.sh olympus|netwatch|horae-agent|horae-theme|all`, verify, commit, push.
  Don't edit files on the servers directly.
- Verify UI changes in the browser (http://helios/, http://helios:8095/, http://horae/). The built-in browser pane may report
  `document.hidden`; the pages pause polling when hidden, which looks like "not refreshing" in tests.
- **No passwordless sudo** on any machine (by design). Anything needing root: write a script, have Todd run
  `sudo bash ~/script.sh`. Docker works without sudo (user is in the `docker` group).
- **Credentials**: don't read, print or pipe passwords/tokens between machines; the auto-mode classifier blocks it anyway.
  Have Todd create secrets and save them via a hidden prompt or `nano` on the target machine.
- Pi-hole admin password: `sudo cat /opt/pihub/.pihole-password` on horae (Todd runs it).

## Traps already hit (don't repeat)

- **cloud-init** re-applies the hostname at every boot (`preserve_hostname: false`). horae's name is pinned by
  `/etc/cloud/cloud.cfg.d/99-keep-hostname.cfg` and `hostname: horae` in `/boot/firmware/user-data`.
- **Line endings**: Git on this PC uses autocrlf; `.gitattributes` forces LF. Scripts with CRLF break on Linux.
- **Python as PID 1** ignores SIGTERM: every custom container has `init: true` (restarts take ~0.4 s, not 10 s).
- **Docker port publishing hides client IPs** for Tailscale traffic: that's why Pi-hole and the agents use host networking.
- `/mnt/win-ai-workspace` on helios is a CIFS share from this PC; it's excluded from agent disk stats because statvfs hangs when the PC sleeps.
- `pi-setup.sh` rewrites `/opt/pihub/docker-compose.yml` if re-run; `pi-extras.sh` / `pihole-hostnet.sh` re-apply the later edits.
  The repo's `horae/stack/docker-compose.yml` is the current truth.
- Homepage's Tailwind uses `.grid`; `deploy.sh horae-theme` strips the suite's `.grid` rule from the bundle. If you change that
  rule in `suite.css`, update the grep in `deploy.sh`.
- Homepage can only load `custom.css`/`custom.js`, so the suite is bundled into them (loading from helios was blocked cross-origin).
- Pi-hole `pihole-FTL --config database.DBinterval` didn't persist; it's set via `FTLCONF_database_DBinterval` in compose.
- Spectrum's "DNS server" setting is upstream DNS for the router, not what it hands to devices.
- The Pi's IPv6 comes from kernel router advertisements; enabling forwarding without `accept_ra=2` would drop it.

## Backups

- horae: nightly `/var/backups/pihub/pihub-YYYY-MM-DD.tar.gz` (14 kept, `pihub-backup.timer`). Copying them off the Pi isn't set up.
- Code: this repo.

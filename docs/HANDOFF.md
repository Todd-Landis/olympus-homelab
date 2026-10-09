# Handoff: olympus-homelab

Written 2026-10-08 at the end of the chat that built all of this. Read `README.md` first for the layout; this file is the
history, current state, open items, and the traps already hit.

## What exists now

**Machines** (Tailscale tailnet `tail247b74.ts.net`, Linux user `synestri` everywhere, SSH key auth only):

| Name | Tailscale IP | LAN | Notes |
|---|---|---|---|
| helios | 100.88.170.59 | 192.168.50.3 (reserved, Wi-Fi 5016Shoreside) | Ubuntu laptop server. Also runs `/opt/ai-stack` (NOT in this repo; see `~/handoff/HANDOFF.md` on helios) |
| horae | 100.123.23.100 | 192.168.50.2 (reserved, Ethernet) | Raspberry Pi 4, Pi OS Lite (trixie, cloud-init). Renamed from `pihub` |
| hephaestus | 100.102.134.107 | 192.168.50.5 (reserved, Wi-Fi 5016Shoreside) | Tower, dual boot; only a server in Ubuntu. Olympus agent installed |
| desktop-ajq2ikv | 100.73.62.100 | automatic | Todd's Windows laptop (this PC) |
| iphone181 | 100.110.215.44 | automatic | Todd's iPhone |

**Running services**

- **horae** `/opt/pihub` (compose in `horae/stack/`): Pi-hole (host network, admin `:8080`, DNS `:53`), Home Assistant (`:8123`, host
  network), Homepage (`:80`). Tailscale on, Tailscale SSH off, `--accept-dns=false`.
- **helios** `~/pihole-watch` ("Network", http://helios:8095): Python stdlib app, syncs Pi-hole `/api/queries` every 5 s into
  SQLite (`data/watch.db`, 30-day retention), block/unblock via Pi-hole API. Auth = Pi-hole **app password** in
  `~/pihole-watch/pihole.secret` (600). Device names: `data/names.json` (keys = IPs or router hostnames) > Tailscale > Pi-hole/router names.
- **helios** `~/olympus` (http://helios/, port 80 on Tailscale IP): hub polls agents (5 s stats, 10 s containers), checks services
  (20 s), widgets (Network summary, Ollama). Agents on helios and horae (`~/olympus-agent`) listen on `:9101` and only answer
  `100.88.170.59`. Restart/stop/start and logs work through the agent. No login on Olympus or Network.

**DNS / network state** (full details: `docs/NETWORK.md`)

- ASUS RT-BE58U on 192.168.50.0/24 hands out Pi-hole (`192.168.50.2`) as the only DNS, so every LAN device (IoT too) uses it.
  Pi-hole names LAN clients via conditional forwarding to the ASUS. Port forwards: UDP 7777 + 8888 to helios (Dragonwilds).
- Tailscale admin DNS: global nameserver `100.123.23.100` with **Override DNS servers on**, so every tailnet device uses Pi-hole
  while Tailscale is connected.
- Pi-hole runs with host networking so each client shows by its real IP (LAN 192.168.50.x or Tailscale 100.x).
  `172.18.0.1` in old history = Tailscale traffic from before that fix.

**Design** (`suite/`): light only, warm off-white, Inter, Fraunces only for the "Olympus" wordmark, plain labels, thin borders,
one terracotta accent, per-host colors (helios ochre, horae laurel, hephaestus terracotta), tiny sun arc by the clock,
`Ctrl K` search palette in all three apps. Todd **rejected** a heavily themed version (temples/stamps/"Oracle" wording) as an
art project; keep it subtle, modern and readable. No dark mode.

## Open items (Todd's to-do list)

1. **ASUS router move** (done 2026-10-09, see `docs/NETWORK.md`). Left: switch this PC (and todd-desktop) to 5016Shoreside and
   set it **Private**; check the iPhone's Configure DNS is Automatic; confirm Dragonwilds is joinable from outside.
2. **Tailscale exit node**: `~/exit-node.sh` is on horae (IP forwarding + `accept_ra=2` for eth0 so IPv6 survives). Not confirmed
   run/approved yet. After `sudo bash ~/exit-node.sh`, approve in Tailscale admin > Machines > horae > Edit route settings.
3. **Home Assistant**: Todd still needs to create the account, then a long-lived token for a Homepage/Olympus HA widget.
   Don't route the token through chat; have him paste it into a file on the server himself.
3a. **Matter (Apple Home stays primary)**: `matter-server` container added to `horae/stack/` (matterjs-server, localhost:5580).
   Todd: `./deploy.sh horae-stack`, then on horae `sudo bash ~/matter-setup.sh`, then add the Matter integration in HA
   (`ws://localhost:5580/ws`) and share each device from Apple Home (Turn On Pairing Mode -> code -> HA). State syncs live
   over Matter; devices added to Apple Home later must be shared the same way. Not yet run on the Pi.
   `pi-setup.sh`'s embedded compose is older than `horae/stack/` (no Matter, Pi-hole not on host network).
4. **This PC**: network profile must be **Private** (Windows blocks mDNS on Public, which is why `horae.local` doesn't resolve).
5. **hephaestus**: Olympus agent is installed; check it reports in Olympus when the tower is in Ubuntu.
6. Daytime look of the sun arc not visually verified (only seen at night).
7. Possible: add a login to Olympus/Network if the tailnet is ever shared.

## How to work here

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

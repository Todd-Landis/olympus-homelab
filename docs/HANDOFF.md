# Handoff: olympus-homelab

Last updated 2026-10-15 (design refresh shipped from the Mac; see `docs/design-log.md`). Read `README.md` for the repo layout and `docs/NETWORK.md` for the home network.
This file is the current state, what changed recently, open items, how to work here, and traps already hit.

## What exists now

**Machines** (Tailscale tailnet `tail247b74.ts.net`, Linux user `synestri` everywhere, SSH key auth only):

| Name | Tailscale IP | LAN | Notes |
|---|---|---|---|
| helios | 100.88.170.59 | 192.168.50.3 (reserved, Wi-Fi 5016Shoreside 2.4 GHz) | Ubuntu laptop server. Also runs `/opt/ai-stack` (NOT in this repo; see `~/handoff/HANDOFF.md` on helios) |
| horae | 100.123.23.100 | 192.168.50.2 (reserved, Ethernet) | Raspberry Pi 4, Pi OS Lite (trixie, cloud-init). Renamed from `pihub` |
| hephaestus | 100.102.134.107 | 192.168.50.5 (reserved, Wi-Fi 5016Shoreside 5 GHz, Wi-Fi 7) | Tower, dual boot; a server only in Ubuntu. Olympus agent reports |
| todd-macbook-pro | 100.115.118.44 | automatic | Todd's Mac, his laptop since 2026-10-15; deploys run from here. helios and horae trust its SSH key (`~/.ssh/id_ed25519`) |
| iphone181 | 100.110.215.44 | automatic | Todd's iPhone, on 5016Shoreside |

The old Windows laptop (`desktop-ajq2ikv`, 100.73.62.100) was **wiped and given away** (2026-10-15). It can't be used for
anything: don't suggest it. Its leftovers: remove it from the Tailscale admin console, its SSH key from `authorized_keys` on
helios and horae, and the Odysseus share it served (see "Odysseus after a reboot").

**Running services**

- **horae** `/opt/pihub` (compose in `horae/stack/`): Pi-hole (host network, admin `:8080`, DNS `:53`), Home Assistant (`:8123`,
  host network), Matter server (`localhost:5580`, healthy), Homepage (`:80`), Olympus agent. Tailscale on, `--accept-dns=false`,
  **Tailscale exit node** (approved; forwarding in `/etc/sysctl.d/99-tailscale.conf`).
- **helios** `~/pihole-watch` ("Network", http://helios:8095): syncs Pi-hole queries every 5 s into SQLite (`data/watch.db`, 30-day
  retention); block/unblock via the Pi-hole API with an **app password** in `~/pihole-watch/pihole.secret` (600). Also:
  - reads Pi-hole's network table every 5 min (IP -> MAC + maker),
  - listens for the ASUS syslog on udp/514 (`5514` in the container) and records which Wi-Fi network each device joins,
  - `/api/lan`: home-address pool usage (devices seen in the last 24 h) and the list of Wi-Fi networks.
- **helios** `~/olympus` (http://helios/, port 80 on the Tailscale IP): **chat is the main view** (see below), old overview = Dashboard tab; hub + agents on helios, horae and hephaestus (`:9101`, answer
  only `100.88.170.59`). Network card shows home-address usage; alert at 80%. Restart/stop/start and logs through the agents.
  No login on Olympus or Network.
- **helios** Dragonwilds server (systemd `dragonwilds.service`, UDP 7777 game + 8888 beacon, forwarded on the router).
- **helios** `~/bin/odysseus-autostart.sh` from synestri's crontab `@reboot` (see "Odysseus after a reboot").

**Device names in Network** (`~/pihole-watch/data/names.json`): keys may be an IP, a MAC (preferred for devices without a fixed IP),
or a router hostname (case-insensitive). Unnamed devices show as maker + end of MAC (e.g. `TP-Link ·e3:20`). Order: names.json >
Tailscale > router hostname (via Pi-hole) > maker fallback. Renames from the Olympus Dashboard are saved by MAC when Pi-hole
knows it (IP otherwise), so a name doesn't drift to another device when automatic IPs change.

**Wi-Fi per device** (`~/pihole-watch/data/wifi.json`, copy in `pihole-watch/wifi.example.json`): `wl0.1`/`wl1.1` = 5016Shoreside,
`wl0.2`/`wl1.2` = SpectrumSetup-DB35 (IoT), `192.168.50.2` = Wired. Devices show their network after they next (re)connect.

**Design** (rulebook: `docs/DESIGN.md`, shared code: `suite/`): light only, marble page, white cards edged by light
rather than borders, ink text, one Aegean-blue accent, Inter. Four quiet classical nods only: the inscribed "OLYMPUS"
wordmark with a temple-front mark, a mark per machine (helios sun, horae hourglass, hephaestus anvil), the sun arc by the
clock, and a faint daylight glow that follows the real sun. Status colours mean status only (per-host colours were
dropped on 2026-10-15). `Ctrl K` search in all three apps. Home Assistant has a matching **Olympus** theme
(`./deploy.sh horae-ha`, then `sudo bash ~/olympus-ha/ha-theme.sh` on horae); Pi-hole uses `default-light`. Todd
**rejected** a heavily themed version (temples/stamps/"Oracle" wording) as an art project; keep it subtle, modern and
readable. No dark mode.

## Changes on 2026-10-15

1. **horae trusts the Mac.** With no password login and no key on helios for horae, the key went in through the SD card:
   a `bootcmd` appended to `user-data` on the card's FAT boot partition (`/boot/firmware/user-data` on the Pi) adds the
   Mac's key (comment `todd-mac`) to synestri's `authorized_keys` at every boot if it's missing. The pre-change copy is
   `/boot/firmware/user-data.bak-20261015`. To keep the Mac online while the Pi was off: Tailscale off and Wi-Fi DNS
   1.1.1.1 (both undone afterwards).
2. **Design refresh shipped**: `./deploy.sh olympus`, `netwatch`, `horae-theme`, `horae-ha`, and `horae-stack` (the live
   `/opt/pihub/docker-compose.yml` was missing the `FTLCONF_webserver_interface_theme: "default-light"` line, so
   `docker compose up -d pihole` alone would have changed nothing). Todd ran `ha-theme.sh` (configuration.yaml backup
   `/opt/pihub/homeassistant/configuration.yaml.bak-20261015-130424`) and recreated Pi-hole. Served CSS checked
   against the repo on all three dashboards.
3. **Network Watch can't show full URLs**, only domains: it's built on DNS, and paths travel inside HTTPS. Getting them
   would take a TLS-intercepting proxy; Todd was told why that's not recommended here.

## Changes on 2026-10-09

1. **Router swap: Spectrum router -> ASUS RT-BE58U** (details: `docs/NETWORK.md`).
   - Kept ASUS's `192.168.50.0/24`. Reservations below `.100` for hosting machines only (horae `.2`, helios `.3`/`.4`, hephaestus
     `.5`/`.6`); pool `.100`–`.254`. Laptops/phones/IoT are automatic by choice.
   - DHCP DNS = Pi-hole only (`192.168.50.2`, "advertise router's IP" off), so **every LAN device, IoT included, goes through
     Pi-hole**. IPv6 is off on the ASUS (only local `fd04:` ULA addresses; no IPv6 DNS handed out).
   - Two SSIDs on one LAN: **5016Shoreside** (primary) and **SpectrumSetup-DB35** (old name, for IoT). Todd decided to keep them
     on one subnet (no IoT isolation: Apple Home is the primary hub and needs the accessories on its network).
   - horae moved to `.2` (stack applied with sudo + reboot). Pi-hole got `horae.home -> 192.168.50.2` and conditional
     forwarding to the ASUS (`FTLCONF_dns_hosts` / `FTLCONF_dns_revServers` in `horae/stack/docker-compose.yml`).
   - helios and hephaestus moved to 5016Shoreside with `scripts/wifi-switch.sh` (netplan rewrite, systemd job, auto-rollback).
     The first version had a quoting bug (SSID stored with literal quotes; the rollback job died with the SSH session); fixed.
   - This PC moved to 5016Shoreside and set Private; iPhone on 5016Shoreside.
2. **Dragonwilds port forwards**: UDP 7777 and 8888 -> `192.168.50.3`; UFW on helios allows both (old combined
   `7777,8888,45453` rule removed). Server restarted to re-register with the new public IP. 45453 is an outbound port, not needed.
3. **Network Watch**: device names from the router (via Pi-hole), MAC-based labels with maker fallback, Wi-Fi column + filter
   from the router syslog, home-address usage line. Olympus: pool bar + 80% alert.
4. **History cleared**: all browsing history before the new router (before 2026-10-09 15:58:40) deleted from Network Watch and
   from Pi-hole's query DB, plus old `192.168.1.x` / `172.18.0.1` names. The backups were made and then deleted by Todd.
   Two tiny earlier copies of the device-name list remain on helios (`data/names.json.bak`, `.bak2`); Todd may delete them.
5. **Odysseus** was down ~12 h after helios rebooted at 04:30 (bind mount of the laptop share failed at boot). Started it and
   added the `@reboot` auto-start script.
6. `deploy.sh horae-stack` now only copies files and prints the `sudo` command (the Pi's `.env` is root-only).
7. **Git**: today's commits were made on branch `claude/determined-bell-wxx907` while a parallel session's work (chat, categories,
   game servers, hephaestus agent) sat on `claude/tender-ritchie-d71y1t`. Deploys from the first branch had removed the
   second's features from helios; the branches were merged, redeployed, `main` fast-forwarded, and both `claude/*` branches
   deleted (locally and on GitHub). Dashboard renames now store MACs (see "Device names").
8. **Tailscale exit node on horae**: `horae/scripts/exit-node.sh` run (IPv4+IPv6 forwarding, `accept_ra=2` so the Pi keeps
   its IPv6), approved in the admin console (Machines > horae > Edit route settings > Use as exit node). Tested from this PC:
   first hop 100.123.23.100, then the router. Use: Tailscale app > Exit Node > horae; off = None.

## Open items

1. **Dragonwilds from outside**: not yet confirmed joinable (friend, or phone on mobile data with Wi-Fi + Tailscale off).
   If it fails, read `journalctl -u dragonwilds` around the attempt.
2. **Exit node from away**: try it on the iPhone off home Wi-Fi; https://ifconfig.me should show the home IP.
3. **todd-desktop** (and other PCs) -> 5016Shoreside when convenient. iPhone: confirm Configure DNS = Automatic.
4. **Design refresh (2026-10-15) follow-ups** (it's deployed): Todd looked at all four sites and found nothing broken, though
   the change felt subtle to him (a hard refresh, ⌘⇧R, rules out cached CSS). Still open from `docs/design-log.md`: HA
   variables that stay default-coloured, a real iPhone pass, raw errors in the status banner. Optional: make Olympus HA's
   default theme on every device (Developer tools > Actions > "Frontend: Set the default theme").
5. **Home Assistant**: the account exists (onboarding done; one user, `talandis`; if the password is forgotten, Todd resets it on
   horae with `docker exec homeassistant python -m homeassistant --script auth --config /config change_password talandis …`
   and restarts HA). Matter integration (`ws://localhost:5580/ws`) and sharing Apple Home devices (Turn On Pairing
   Mode -> code -> HA) still to check/finish. Then a long-lived token for an HA widget; Todd saves it on the server himself.
6. **Unidentified devices** in Network (`Device ·16:0c`, `Device ·5e:c5`, `Device ·5a:4e`, `virtual interface ·00:00`, the TP-Link /
   Espressif / AMPAK / Logitech ones): name them by MAC (Olympus Dashboard or `names.json`) once Todd knows what they are.
7. **Wi-Fi column** fills in as devices reconnect (joins right after the router reboot weren't logged).
8. Prefer `horae` or `horae.home` over `horae.local` (mDNS resolved only partly on the old Windows laptop).
9. Possible: login on Olympus/Network if the tailnet is ever shared. Network logs **everyone's** browsing at home
   (e.g. Connor's S24, guests); Todd was told it's fair to let household members know.

Done today (details above): router move, Dragonwilds forwards, history clean-up, Odysseus auto-start, branch merge +
`main` fast-forward, exit node.

## Olympus chat (from the parallel session, merged 2026-10-09)

- **Olympus chat** is the main view of http://helios/ (the old overview is the **Dashboard** tab; links to every hosted
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
- The Apps panel (iframes of each service on the overview) was tried and removed in favour of the chat.
  `ha-allow-framing.sh` had already set `http: use_x_frame_options: false` in Home Assistant's configuration.yaml on
  horae; it's harmless, but to undo it delete that line (a `.bak-` copy sits next to the file) and restart Home Assistant.


## Content categories (Network Watch)

- `CATEGORY_LISTS` (default `{"adult": "https://nsfw.oisd.nl/domainswild2"}`, the OISD NSFW list) is downloaded daily
  to `~/pihole-watch/data/categories/`; the last good copy is kept if a download fails. Every domain seen is tagged
  once in the `domcat` table (a domain matches if it or a parent domain is listed). `/api/categories` shows list size,
  last update, errors and how many seen domains matched. The chat's network query takes `category: "adult"`.
- It matches DNS lookups, not page views: ads, previews and embeds can trigger them. Pi-hole could also *block* the same
  list (add it as an adlist in Pi-hole) if that's ever wanted; this only reports.

## Game servers

- The helios agent watches game servers listed in `SERVERS` (olympus/docker-compose.yml): systemd unit (running,
  uptime, CPU, memory), Steam build (`steamapps/appmanifest_<appid>.acf`) and players from the server log.
- Dragonwilds: unit `dragonwilds`, install `/home/synestri/dragonwilds`, appid 4019830, log
  `RSDragonwilds/Saved/Logs/RSDragonwilds.log` (rotated to `-backup-<date>.log` on restart). Updates are handled by
  `dragonwilds-version-watch` (watches the journal for client/server protocol mismatches, runs
  `~/steamcmd/auto-update-dragonwilds.sh`). The unit runs at low priority (CPUWeight=20, Nice=10) so the AI stack wins.
- Player lines (`agent.py` `UE_PATTERNS`, checked against real Dragonwilds logs 2026-10-09): `Login request: …?Name=<name>
  userId: RedpointEOS:<id>` maps id → name (names can contain spaces), `Join succeeded: <name>` is a join, and
  `UNetConnection::Close: … UniqueId: <id>` is a leave. Disconnects from ids that never logged in are ignored.
  Another game can override any of these with `"patterns": {...}` in its SERVERS entry.

- UI work: follow `.claude/skills/olympus-design` (design system in `docs/DESIGN.md`, history in `docs/design-log.md`).
  `dev/stack.sh start` runs Olympus + Network Watch locally on fake data; `/ui-audit` and `/ui-critique` check it.

## How to work here

- Edit in this repo, then `./deploy.sh olympus|netwatch|horae-agent|horae-stack|horae-theme|all`, verify, commit, push.
  Don't edit files on the servers directly. Data files that live only on the servers: `names.json`, `wifi.json`, the DBs.
- Check `git status -sb` first: make sure you're on the branch you think you're on.
- Verify UI changes in the browser (http://helios/, http://helios:8095/, http://horae/). The built-in browser pane may report
  `document.hidden`; the pages pause polling when hidden, which looks like "not refreshing" in tests.
- **No passwordless sudo** on any machine (by design). Anything needing root: write a script, have Todd run
  `sudo bash ~/script.sh` (or a one-line `sudo …`). Docker works without sudo (`docker` group).
- **Credentials**: don't read, print or pipe passwords/tokens between machines; the auto-mode classifier blocks it anyway.
  Have Todd create secrets and save them via a hidden prompt or `nano` on the target machine. Router admin is Todd's.
- Pi-hole admin password: `sudo cat /opt/pihub/.pihole-password` on horae (Todd runs it).
- Deleting data: back up first, tell Todd where the backup is, let him delete it.

## Traps already hit (don't repeat)

- **cloud-init** re-applies the hostname at every boot (`preserve_hostname: false`). horae's name is pinned by
  `/etc/cloud/cloud.cfg.d/99-keep-hostname.cfg` and `hostname: horae` in `/boot/firmware/user-data`.
- **Line endings**: `.gitattributes` forces LF (Git on Windows used autocrlf). Scripts with CRLF break on Linux.
- **Python as PID 1** ignores SIGTERM: every custom container has `init: true` (restarts take ~0.4 s, not 10 s).
- **Docker port publishing hides client IPs** for Tailscale traffic: that's why Pi-hole and the agents use host networking.
- `/mnt/win-ai-workspace` on helios was a CIFS share from the old Windows laptop (systemd automount), which is gone; excluded
  from agent disk stats because statvfs hangs when the share is unreachable, and it's why Odysseus can fail to start at boot.
- `pi-setup.sh` rewrites `/opt/pihub/docker-compose.yml` if re-run; the repo's `horae/stack/docker-compose.yml` is the truth.
  Applying it needs sudo (`.env` is root-only).
- Homepage's Tailwind uses `.grid`; `deploy.sh horae-theme` strips the suite's `.grid` rule from the bundle. If you change that
  rule in `suite.css`, update the grep in `deploy.sh`.
- Homepage can only load `custom.css`/`custom.js`, so the suite is bundled into them (loading from helios was blocked cross-origin).
- Pi-hole `pihole-FTL --config database.DBinterval` didn't persist; settings go in compose as `FTLCONF_*`.
- Pi-hole doesn't list its own machine with a MAC; pin horae by IP in `wifi.json`/`names.json`.
- The Pi's IPv6 comes from kernel router advertisements; enabling forwarding without `accept_ra=2` would drop it.
- **netplan set** paths: no quotes around keys, or the quotes become part of the SSID. `wifi-switch.sh` now rewrites
  `60-wifi.yaml` with YAML single quotes instead.
- Anything that must survive an SSH drop: run it via `systemd-run` (a `setsid nohup` job died with the session).
- After a router reboot, Wi-Fi joins happen before the ASUS logger starts, so they aren't sent; devices show up as they reconnect.
- ASUS allows one admin web session at a time, so don't poll the router's API (it would log Todd out); use the syslog.
- A public IP change needs `sudo systemctl restart dragonwilds` so the in-game browser advertises the new address.
- Shell one-liners with nested quotes over SSH broke several times (perl/sed/python): write a script file, `scp`, run it.
- The file tools need a real Read before Write; viewing a file through the shell doesn't count.
- **Tailscale on the Mac**: the menu-bar toggle kept flipping back to off (2026-10-15). `tailscale up --accept-routes` from the
  CLI (`/Applications/Tailscale.app/Contents/MacOS/Tailscale`) connected it; plain `tailscale up` refuses without that flag.
  Check with `tailscale status`, not the menu. horae still resolves over the LAN through Pi-hole when Tailscale is off, helios doesn't.
- **horae is DNS for everything** (home DHCP and Tailscale's DNS): before powering it off, turn Tailscale off and set the Mac's
  Wi-Fi DNS to 1.1.1.1 (or use the iPhone hotspot), and undo both afterwards.
- `/boot/firmware/user-data` has a password hash: grep/tail only, never print it whole. It has one top-level `bootcmd:`;
  add new entries under it rather than a second `bootcmd:` key.

## Backups

- horae: nightly `/var/backups/pihub/pihub-YYYY-MM-DD.tar.gz` (14 kept, `pihub-backup.timer`; skips Pi-hole's query DB and HA's
  history DB). Copying them off the Pi isn't set up.
- Code: this repo.

## Odysseus after a reboot

Odysseus (`/opt/ai-stack/odysseus`) bind-mounts `/mnt/win-ai-workspace`, a CIFS share from Todd's laptop. If the laptop
isn't reachable when helios boots, Docker fails to start it ("no such device") and doesn't retry. `scripts/helios/odysseus-autostart.sh`
(installed as `~/bin/odysseus-autostart.sh`, run by synestri's crontab `@reboot`) retries every 30 s for 30 min once the share
is readable. Log: `journalctl -t odysseus-autostart`. If the laptop is off longer, start it from Olympus. Tested 2026-10-09.

**2026-10-15: that laptop is wiped and gone**, so the share will never come back. Odysseus needs its workspace moved
(a local folder on helios, or a share from the Mac) before it can start again; until then the autostart retries and gives up.

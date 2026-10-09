# Handoff: olympus-homelab

Last updated 2026-10-09 (evening). Read `README.md` for the repo layout and `docs/NETWORK.md` for the home network.
This file is the current state, what changed recently, open items, how to work here, and traps already hit.

## What exists now

**Machines** (Tailscale tailnet `tail247b74.ts.net`, Linux user `synestri` everywhere, SSH key auth only):

| Name | Tailscale IP | LAN | Notes |
|---|---|---|---|
| helios | 100.88.170.59 | 192.168.50.3 (reserved, Wi-Fi 5016Shoreside 2.4 GHz) | Ubuntu laptop server. Also runs `/opt/ai-stack` (NOT in this repo; see `~/handoff/HANDOFF.md` on helios) |
| horae | 100.123.23.100 | 192.168.50.2 (reserved, Ethernet) | Raspberry Pi 4, Pi OS Lite (trixie, cloud-init). Renamed from `pihub` |
| hephaestus | 100.102.134.107 | 192.168.50.5 (reserved, Wi-Fi 5016Shoreside 5 GHz, Wi-Fi 7) | Tower, dual boot; a server only in Ubuntu. Olympus agent reports |
| desktop-ajq2ikv | 100.73.62.100 | automatic | Todd's Windows laptop (this PC), on 5016Shoreside, profile Private |
| iphone181 | 100.110.215.44 | automatic | Todd's iPhone, on 5016Shoreside |

**Running services**

- **horae** `/opt/pihub` (compose in `horae/stack/`): Pi-hole (host network, admin `:8080`, DNS `:53`), Home Assistant (`:8123`,
  host network), Matter server (`localhost:5580`, healthy), Homepage (`:80`), Olympus agent. Tailscale on, `--accept-dns=false`.
- **helios** `~/pihole-watch` ("Network", http://helios:8095): syncs Pi-hole queries every 5 s into SQLite (`data/watch.db`, 30-day
  retention); block/unblock via the Pi-hole API with an **app password** in `~/pihole-watch/pihole.secret` (600). Also:
  - reads Pi-hole's network table every 5 min (IP -> MAC + maker),
  - listens for the ASUS syslog on udp/514 (`5514` in the container) and records which Wi-Fi network each device joins,
  - `/api/lan`: home-address pool usage (devices seen in the last 24 h) and the list of Wi-Fi networks.
- **helios** `~/olympus` (http://helios/, port 80 on the Tailscale IP): hub + agents on helios, horae and hephaestus (`:9101`, answer
  only `100.88.170.59`). Network card shows home-address usage; alert at 80%. Restart/stop/start and logs through the agents.
  No login on Olympus or Network.
- **helios** Dragonwilds server (systemd `dragonwilds.service`, UDP 7777 game + 8888 beacon, forwarded on the router).
- **helios** `~/bin/odysseus-autostart.sh` from synestri's crontab `@reboot` (see "Odysseus after a reboot").

**Device names in Network** (`~/pihole-watch/data/names.json`): keys may be an IP, a MAC (preferred for devices without a fixed IP),
or a router hostname (case-insensitive). Unnamed devices show as maker + end of MAC (e.g. `TP-Link ·e3:20`). Order: names.json >
Tailscale > router hostname (via Pi-hole) > maker fallback.

**Wi-Fi per device** (`~/pihole-watch/data/wifi.json`, copy in `pihole-watch/wifi.example.json`): `wl0.1`/`wl1.1` = 5016Shoreside,
`wl0.2`/`wl1.2` = SpectrumSetup-DB35 (IoT), `192.168.50.2` = Wired. Devices show their network after they next (re)connect.

**Design** (`suite/`): light only, warm off-white, Inter, Fraunces only for the "Olympus" wordmark, plain labels, thin borders,
one terracotta accent, per-host colors (helios ochre, horae laurel, hephaestus terracotta), tiny sun arc by the clock,
`Ctrl K` search in all three apps. Todd **rejected** a heavily themed version (temples/stamps/"Oracle" wording) as an
art project; keep it subtle, modern and readable. No dark mode.

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
   from Pi-hole's query DB, plus old `192.168.1.x` / `172.18.0.1` names. Backups (Todd deletes them when happy):
   - helios `~/pihole-watch/data/watch.db.before-router-20261009-165828`, `names.json.before-router-20261009-165828`
   - horae `/opt/pihub/pihole/pihole-FTL.db.before-router-20261009-170142` (root-owned)
5. **Odysseus** was down ~12 h after helios rebooted at 04:30 (bind mount of the laptop share failed at boot). Started it and
   added the `@reboot` auto-start script.
6. `deploy.sh horae-stack` now only copies files and prints the `sudo` command (the Pi's `.env` is root-only).
7. **Git**: today's commits were made on branch `claude/determined-bell-wxx907` (the folder had been left on it by the session
   that added Matter). `main` was behind; see open item 1.

## Open items

1. **Get `main` up to date** with `claude/determined-bell-wxx907` (fast-forward; `main` has nothing the branch lacks), then check
   out `main` in `C:\Users\Todd\olympus-homelab`. There is also an older branch `claude/tender-ritchie-d71y1t` to review.
2. **Dragonwilds from outside**: not yet confirmed joinable (friend, or phone on mobile data with Wi-Fi + Tailscale off).
   If it fails, read `journalctl -u dragonwilds` around the attempt.
3. **todd-desktop** (and other PCs) -> 5016Shoreside when convenient. iPhone: confirm Configure DNS = Automatic.
4. **Delete the history backups** above once Todd is happy (commands already given to him).
5. **Tailscale exit node**: `~/exit-node.sh` on horae (IP forwarding + `accept_ra=2` so the Pi's IPv6 survives). Not run/approved yet.
   After `sudo bash ~/exit-node.sh`, approve in Tailscale admin > Machines > horae > Edit route settings.
6. **Home Assistant**: account + Matter integration (`ws://localhost:5580/ws`) and sharing Apple Home devices (Turn On Pairing
   Mode -> code -> HA) still to check/finish. Then a long-lived token for an HA widget; Todd saves it on the server himself.
7. **Unidentified devices** in Network (`Device ·16:0c`, `Device ·5e:c5`, `Device ·5a:4e`, `virtual interface ·00:00`, the TP-Link /
   Espressif / AMPAK / Logitech ones): name them in `names.json` by MAC once Todd knows what they are.
8. `horae.local` resolves only partly on this PC (mDNS); use `horae` or `horae.home`.
9. Possible: login on Olympus/Network if the tailnet is ever shared. Network now logs **everyone's** browsing at home
   (e.g. Connor's S24, guests); Todd was told it's fair to let household members know.

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
- **Line endings**: Git on this PC uses autocrlf; `.gitattributes` forces LF. Scripts with CRLF break on Linux.
- **Python as PID 1** ignores SIGTERM: every custom container has `init: true` (restarts take ~0.4 s, not 10 s).
- **Docker port publishing hides client IPs** for Tailscale traffic: that's why Pi-hole and the agents use host networking.
- `/mnt/win-ai-workspace` on helios is a CIFS share from this PC (systemd automount); excluded from agent disk stats because statvfs
  hangs when the PC sleeps, and it's why Odysseus can fail to start at boot.
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

## Backups

- horae: nightly `/var/backups/pihub/pihub-YYYY-MM-DD.tar.gz` (14 kept, `pihub-backup.timer`; skips Pi-hole's query DB and HA's
  history DB). Copying them off the Pi isn't set up.
- Code: this repo.

## Odysseus after a reboot

Odysseus (`/opt/ai-stack/odysseus`) bind-mounts `/mnt/win-ai-workspace`, a CIFS share from Todd's laptop. If the laptop
isn't reachable when helios boots, Docker fails to start it ("no such device") and doesn't retry. `scripts/helios/odysseus-autostart.sh`
(installed as `~/bin/odysseus-autostart.sh`, run by synestri's crontab `@reboot`) retries every 30 s for 30 min once the share
is readable. Log: `journalctl -t odysseus-autostart`. If the laptop is off longer, start it from Olympus. Tested 2026-10-09.

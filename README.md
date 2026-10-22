# olympus-homelab

Code and config for the home lab: three machines on Tailscale, one dashboard suite.

| Machine | What it is | Runs |
|---|---|---|
| **helios** | Always-on Ubuntu laptop (GTX 1060) | AI stack (`/opt/ai-stack`, not in this repo), **Olympus** dashboard, **Network Watch**, Dragonwilds server |
| **horae** | Raspberry Pi 4 (Pi OS Lite), LAN 192.168.50.2 | Pi-hole (DNS + ad blocking), Home Assistant + Matter server, Homepage, Tailscale exit node |
| **hephaestus** | Tower, dual boot (AMD GPU); a server only when in Ubuntu | Ollama coding models, Olympus agent |

Network (addresses, DNS, port forwards, moving a server's Wi-Fi): see [`docs/NETWORK.md`](docs/NETWORK.md).

## Apps

| App | URL (Tailscale) | Source |
|---|---|---|
| Olympus (overview of every machine, service, container, log) | http://helios/ | `olympus/` |
| Network (browsing activity per device, blocking) | http://helios:8095/ | `pihole-watch/` |
| Horae (the Pi's own Homepage dashboard) | http://horae/ | `horae/homepage/` |
| Pi-hole admin | http://horae:8080/admin | `horae/stack/` |
| Home Assistant | http://horae:8123 | `horae/stack/` |

Every site follows one rulebook, [`docs/DESIGN.md`](docs/DESIGN.md) (light, marble and ink, one Aegean accent, Inter,
`Ctrl K` search). The three dashboards share `suite/`: edit it there and deploy; `deploy.sh` copies it into each app (and
bundles it into Homepage's `custom.css`/`custom.js` for horae). Home Assistant gets the matching **Olympus** theme
(`horae/homeassistant/`), Pi-hole its built-in light theme.

## Layout

```
olympus/            hub (app.py, chat.py, config.json, static/index.html + viz.js) + agent (agent.py)
  image/            Dockerfile for the hub (adds the anthropic package for chat's Claude option)
  agent-horae/      compose file for the agent on horae
pihole-watch/       Network Watch: syncs Pi-hole's query log into SQLite, serves the browsing UI
suite/              shared CSS/JS (+ horae-specific overrides.css / mount.js); vendor/ = ECharts
horae/
  scripts/          pi-setup.sh (stack install), pi-extras.sh (logs, backups, Tailscale),
                    pihole-hostnet.sh, exit-node.sh, rename-horae.sh, matter-setup.sh, ha-theme.sh, adult-content.sh
  stack/            /opt/pihub/docker-compose.yml (Pi-hole, Home Assistant, Matter server, Homepage)
  homepage/         Homepage config (services, widgets, settings)
  homeassistant/    Olympus theme for Home Assistant (themes/olympus.yaml, www/olympus/fonts.js)
  first-boot/       cloud-init templates for re-flashing the SD card (placeholders only)
dev/                run everything locally against fake machines (dev/stack.sh), UI check tooling (dev/ui/)
.claude/skills/     design skills: olympus-design, ui-audit, ui-critique, ui-polish, and Emil Kowalski's emil-design-eng,
                    animate, review-animations, find-animation-opportunities, animation-performance, apple-design,
                    mobile-native, break-ui (vendored, MIT; see docs/DESIGN.md)
scripts/           wifi-switch.sh (headless Ubuntu Wi-Fi move), helios/ (Odysseus autostart), mac/wifi-drops.sh (daily drop report)
deploy.sh           push changes to the servers
```

## Deploying

```bash
./deploy.sh olympus       # hub + helios agent
./deploy.sh netwatch      # Network Watch
./deploy.sh horae-agent   # Olympus agent on horae
./deploy.sh horae-stack   # /opt/pihub compose (Pi-hole, HA, Matter) + matter-setup.sh
./deploy.sh horae-theme   # Homepage theme + config on horae
./deploy.sh horae-ha      # Home Assistant theme files to horae; then on horae: sudo bash ~/olympus-ha/ha-theme.sh
./deploy.sh adult         # adult sites: purge them from Pi-hole's and Network Watch's history, then block them (asks for the Pi's sudo password)
./deploy.sh hephaestus-agent  # Olympus agent on hephaestus (only while it's in Ubuntu; not in "all")
./deploy.sh all
```

Needs SSH access to `helios` and `synestri@horae` over Tailscale. Root-level changes on the servers
(scripts in `horae/scripts/`) are run by hand with `sudo`; nothing here has passwordless sudo.

## Security notes

- Olympus agents (port 9101) only answer helios' Tailscale IP. Olympus and Network Watch bind to helios'
  Tailscale address only and have no login, so anyone on the tailnet can use them (currently only Todd's devices).
- Secrets are never committed (see `.gitignore`): Pi-hole app password (`pihole-watch/pihole.secret`),
  Pi-hole admin password (`/opt/pihub/.pihole-password`), `.env` files, the browsing database (`data/`).
- The Matter server API (`:5580`) has no auth, so it listens on localhost only; Home Assistant is its one client.
  Its fabric keys live in `/opt/pihub/matter` (covered by the nightly backup; treat backups as secret).
- `horae/first-boot/user-data.example` has placeholders; the real file holds a password hash.

## Backups

horae backs up `/opt/pihub` nightly to `/var/backups/pihub` (14 kept) via `pihub-backup.timer`.

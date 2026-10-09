# olympus-homelab

Code and config for the home lab: three machines on Tailscale, one dashboard suite.

| Machine | What it is | Runs |
|---|---|---|
| **helios** | Always-on Ubuntu laptop (GTX 1060) | AI stack (`/opt/ai-stack`, not in this repo), **Olympus** dashboard, **Network Watch**, Dragonwilds server |
| **horae** | Raspberry Pi 4 (Pi OS Lite), LAN 192.168.1.224 | Pi-hole (DNS + ad blocking), Home Assistant, Homepage, Tailscale exit node |
| **hephaestus** | Tower, dual boot; a server only when in Ubuntu | Ollama coding models (Olympus agent not installed yet) |

## Apps

| App | URL (Tailscale) | Source |
|---|---|---|
| Olympus (overview of every machine, service, container, log) | http://helios/ | `olympus/` |
| Network (browsing activity per device, blocking) | http://helios:8095/ | `pihole-watch/` |
| Horae (the Pi's own Homepage dashboard) | http://horae/ | `horae/homepage/` |
| Pi-hole admin | http://horae:8080/admin | `horae/stack/` |
| Home Assistant | http://horae:8123 | `horae/stack/` |

All three dashboards share one look from `suite/` (light, Inter, `Ctrl K` search). Edit it there and deploy;
`deploy.sh` copies it into each app (and bundles it into Homepage's `custom.css`/`custom.js` for horae).

## Layout

```
olympus/            hub (app.py, chat.py, config.json, static/index.html) + agent (agent.py)
  image/            Dockerfile for the hub (adds the anthropic package for chat's Claude option)
  agent-horae/      compose file for the agent on horae
pihole-watch/       Network Watch: syncs Pi-hole's query log into SQLite, serves the browsing UI
suite/              shared CSS/JS (+ horae-specific overrides.css / mount.js)
horae/
  scripts/          pi-setup.sh (stack install), pi-extras.sh (logs, backups, Tailscale),
                    pihole-hostnet.sh, exit-node.sh, rename-horae.sh,
                    ha-allow-framing.sh (lets Olympus show Home Assistant in its Apps panel)
  stack/            /opt/pihub/docker-compose.yml (Pi-hole, Home Assistant, Homepage)
  homepage/         Homepage config (services, widgets, settings)
  first-boot/       cloud-init templates for re-flashing the SD card (placeholders only)
deploy.sh           push changes to the servers
```

## Deploying

```bash
./deploy.sh olympus       # hub + helios agent
./deploy.sh netwatch      # Network Watch
./deploy.sh horae-agent   # Olympus agent on horae
./deploy.sh horae-theme   # Homepage theme + config on horae
./deploy.sh all
```

Needs SSH access to `helios` and `synestri@horae` over Tailscale. Root-level changes on the servers
(scripts in `horae/scripts/`) are run by hand with `sudo`; nothing here has passwordless sudo.

## Security notes

- Olympus agents (port 9101) only answer helios' Tailscale IP. Olympus and Network Watch bind to helios'
  Tailscale address only and have no login, so anyone on the tailnet can use them (currently only Todd's devices).
- Secrets are never committed (see `.gitignore`): Pi-hole app password (`pihole-watch/pihole.secret`),
  Pi-hole admin password (`/opt/pihub/.pihole-password`), `.env` files, the browsing database (`data/`).
- `horae/first-boot/user-data.example` has placeholders; the real file holds a password hash.

## Backups

horae backs up `/opt/pihub` nightly to `/var/backups/pihub` (14 kept) via `pihub-backup.timer`.

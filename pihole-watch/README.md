# Network Watch

Browsing timeline, unique sites, blocked attempts and one-click blocking,
built on Pi-hole (horae). Runs on helios, reachable at http://helios:8095 over Tailscale.

- `app/app.py` pulls Pi-hole's query log every minute into `data/watch.db`
  and keeps 30 days (`RETENTION_DAYS`).
- Devices are named from Tailscale; override or name LAN IPs in `data/names.json`
  (see `names.example.json`).
- History is kept per device: each lookup stores the MAC behind its IP at that moment (`q.dev`), so it
  stays with the device when the router reuses the IP. Devices sharing a router hostname stay apart (`Mac ·35:c1`).
- `pihole.secret` holds a Pi-hole **app password** (Pi-hole > Settings > Web interface / API >
  Configure app password). Never commit it.
- Two switches above the tabs change Pi-hole for every device: the **adult-site filter** (Pi-hole's OISD NSFW
  list in or out of its groups) and **Incognito** (Pi-hole's privacy level 3: nothing recorded). Incognito needs
  `webserver.api.app_sudo` on Pi-hole (horae's compose file sets it). Details: `docs/HANDOFF.md`, Content categories.

Update: `docker compose up -d --force-recreate`

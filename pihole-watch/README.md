# Network Watch

Browsing timeline, unique sites, blocked attempts and one-click blocking,
built on Pi-hole (horae). Runs on helios, reachable at http://helios:8095 over Tailscale.

- `app/app.py` pulls Pi-hole's query log every minute into `data/watch.db`
  and keeps 30 days (`RETENTION_DAYS`).
- Devices are named from Tailscale; override or name LAN IPs in `data/names.json`
  (see `names.example.json`).
- `pihole.secret` holds a Pi-hole **app password** (Pi-hole > Settings > Web interface / API >
  Configure app password). Never commit it.

Update: `docker compose up -d --force-recreate`

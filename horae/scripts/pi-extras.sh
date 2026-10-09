#!/usr/bin/env bash
# One-time extras for pihub: log limits (SD card wear), dashboard secrets,
# nightly backups, and Tailscale. Run on the Pi:  sudo bash ~/pi-extras.sh
# Safe to re-run.
set -euo pipefail

if [[ $EUID -ne 0 ]]; then echo "Run with sudo: sudo bash $0"; exit 1; fi

USER_NAME="${SUDO_USER:-synestri}"
STACK_DIR="/opt/pihub"
COMPOSE="$STACK_DIR/docker-compose.yml"

echo "== [1/5] Lock down the Pi-hole password file =="
chmod 600 "$STACK_DIR/.pihole-password"

echo "== [2/5] Reduce SD card writes =="
# Cap Docker container logs (applies to containers created after this).
if [[ ! -f /etc/docker/daemon.json ]]; then
  cat >/etc/docker/daemon.json <<'EOF'
{
  "log-driver": "json-file",
  "log-opts": { "max-size": "10m", "max-file": "3" }
}
EOF
  systemctl restart docker
else
  echo "   /etc/docker/daemon.json already exists, leaving it alone"
fi
# Cap the system journal and flush it to disk less often.
mkdir -p /etc/systemd/journald.conf.d
cat >/etc/systemd/journald.conf.d/90-pihub.conf <<'EOF'
[Journal]
SystemMaxUse=100M
SyncIntervalSec=15m
EOF
systemctl restart systemd-journald

echo "== [3/5] Update the stack (dashboard Pi-hole key, Pi-hole DB writes) =="
cp -n "$COMPOSE" "$COMPOSE.orig" || true
# Homepage reads the Pi-hole password from .env instead of a config file.
grep -q 'HOMEPAGE_VAR_PIHOLE_KEY' "$COMPOSE" || \
  sed -i '/HOMEPAGE_ALLOWED_HOSTS:/a\      HOMEPAGE_VAR_PIHOLE_KEY: ${PIHOLE_PASSWORD}' "$COMPOSE"
# Pi-hole writes its query history to disk every 5 min instead of every minute.
grep -q 'FTLCONF_database_DBinterval' "$COMPOSE" || \
  sed -i '/FTLCONF_dns_listeningMode:/a\      FTLCONF_database_DBinterval: "300"' "$COMPOSE"
cd "$STACK_DIR"
docker compose config --quiet
docker compose up -d --force-recreate

echo "== [4/5] Nightly backups to /var/backups/pihub (14 kept) =="
cat >/usr/local/sbin/pihub-backup <<EOF
#!/usr/bin/env bash
# Archive /opt/pihub config. Skips the big, rebuildable history databases.
set -euo pipefail
DEST=/var/backups/pihub
mkdir -p "\$DEST"
OUT="\$DEST/pihub-\$(date +%F).tar.gz"
tar -czf "\$OUT.tmp" -C /opt \\
  --exclude='pihub/pihole/pihole-FTL.db*' \\
  --exclude='pihub/homeassistant/home-assistant_v2.db*' \\
  --exclude='pihub/homepage/logs' \\
  pihub
mv "\$OUT.tmp" "\$OUT"
chown root:$USER_NAME "\$DEST" "\$OUT"
chmod 750 "\$DEST"
chmod 640 "\$OUT"
find "\$DEST" -name 'pihub-*.tar.gz' -mtime +13 -delete
echo "Backup written: \$OUT (\$(du -h "\$OUT" | cut -f1))"
EOF
chmod 755 /usr/local/sbin/pihub-backup

cat >/etc/systemd/system/pihub-backup.service <<'EOF'
[Unit]
Description=Back up /opt/pihub config

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/pihub-backup
EOF
cat >/etc/systemd/system/pihub-backup.timer <<'EOF'
[Unit]
Description=Nightly /opt/pihub backup

[Timer]
OnCalendar=*-*-* 03:30
RandomizedDelaySec=15m
Persistent=true

[Install]
WantedBy=timers.target
EOF
systemctl daemon-reload
systemctl enable --now pihub-backup.timer
/usr/local/sbin/pihub-backup

echo "== [5/5] Tailscale =="
if ! command -v tailscale >/dev/null; then
  curl -fsSL https://tailscale.com/install.sh | sh
fi
echo
echo "   If a login link appears below, open it and approve 'pihub' in your Tailscale account."
echo
# accept-dns=false: the Pi keeps resolving through its own setup, not through tailnet DNS.
tailscale up --hostname=horae --accept-dns=false
echo
echo "Tailscale IP: $(tailscale ip -4)"
echo
echo "All done."

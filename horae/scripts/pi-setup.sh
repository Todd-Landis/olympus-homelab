#!/usr/bin/env bash
# One-shot setup for a Raspberry Pi 4B home server: Docker, Pi-hole,
# Home Assistant (Container) and a Homepage dashboard.
# Copy to the SD card's boot partition, then on the Pi run:
#   sudo bash /boot/firmware/pi-setup.sh
# Safe to re-run: it skips what is already done and just restarts the stack.
set -euo pipefail

if [[ $EUID -ne 0 ]]; then echo "Run with sudo: sudo bash $0"; exit 1; fi

USER_NAME="${SUDO_USER:-$(logname 2>/dev/null || echo pi)}"
STACK_DIR="/opt/pihub"
LOG="/var/log/pi-setup.log"
exec > >(tee -a "$LOG") 2>&1

TZ_NAME="$(timedatectl show -p Timezone --value 2>/dev/null || echo UTC)"
IP_ADDR="$(hostname -I | awk '{print $1}')"
HOST="$(hostname)"

echo "== [1/5] System update =="
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get -y full-upgrade
apt-get -y install curl git vim htop ca-certificates unattended-upgrades
dpkg-reconfigure -f noninteractive unattended-upgrades

echo "== [2/5] Docker =="
if ! command -v docker >/dev/null; then
  curl -fsSL https://get.docker.com | sh
fi
usermod -aG docker "$USER_NAME"
systemctl enable --now docker

echo "== [3/5] Stack files in $STACK_DIR =="
mkdir -p "$STACK_DIR"/{pihole,homeassistant,homepage}

# Pi-hole web password: generated once, kept in a root-only file.
PW_FILE="$STACK_DIR/.pihole-password"
if [[ ! -f "$PW_FILE" ]]; then
  tr -dc 'A-Za-z0-9' </dev/urandom | head -c 20 >"$PW_FILE"
  chmod 600 "$PW_FILE"
fi

cat >"$STACK_DIR/.env" <<EOF
TZ=$TZ_NAME
PIHOLE_PASSWORD=$(cat "$PW_FILE")
EOF
chmod 600 "$STACK_DIR/.env"

cat >"$STACK_DIR/docker-compose.yml" <<'EOF'
# Edit this file, then: cd /opt/pihub && docker compose up -d
services:
  pihole:
    image: pihole/pihole:latest
    container_name: pihole
    restart: unless-stopped
    ports:
      - "53:53/tcp"
      - "53:53/udp"
      - "8080:80/tcp"     # Pi-hole admin: http://<pi>:8080/admin
      - "8443:443/tcp"
    environment:
      TZ: ${TZ}
      FTLCONF_webserver_api_password: ${PIHOLE_PASSWORD}
      FTLCONF_dns_listeningMode: "all"
    volumes:
      - ./pihole:/etc/pihole
    cap_add:
      - SYS_NICE

  homeassistant:
    image: ghcr.io/home-assistant/home-assistant:stable
    container_name: homeassistant
    restart: unless-stopped
    network_mode: host    # needed for device discovery; UI on :8123
    privileged: true
    environment:
      TZ: ${TZ}
    volumes:
      - ./homeassistant:/config
      - /etc/localtime:/etc/localtime:ro
      - /run/dbus:/run/dbus:ro

  homepage:
    image: ghcr.io/gethomepage/homepage:latest
    container_name: homepage
    restart: unless-stopped
    ports:
      - "80:3000"         # Dashboard: http://<pi>/
    environment:
      HOMEPAGE_ALLOWED_HOSTS: "*"   # LAN-only box; tighten to "pihub.local,192.168.x.x" if you like
    volumes:
      - ./homepage:/app/config
      - /var/run/docker.sock:/var/run/docker.sock:ro
EOF

# Starter dashboard tiles; Homepage fills in its other config files on first start.
if [[ ! -f "$STACK_DIR/homepage/services.yaml" ]]; then
  cat >"$STACK_DIR/homepage/services.yaml" <<EOF
- Home:
    - Home Assistant:
        href: http://$HOST.local:8123
        description: Smart home
        icon: home-assistant.png
        container: homeassistant
    - Pi-hole:
        href: http://$HOST.local:8080/admin
        description: Network ad blocking
        icon: pi-hole.png
        container: pihole
EOF
  cat >"$STACK_DIR/homepage/docker.yaml" <<'EOF'
local:
  socket: /var/run/docker.sock
EOF
fi

chown -R "$USER_NAME:$USER_NAME" "$STACK_DIR/homepage" "$STACK_DIR/docker-compose.yml"

echo "== [4/5] Starting containers (first pull takes a few minutes) =="
cd "$STACK_DIR"
docker compose pull
docker compose up -d

echo "== [5/5] Done =="
MAC="$(cat /sys/class/net/eth0/address 2>/dev/null || echo unknown)"
cat <<EOF

  Dashboard ....... http://$HOST.local/        (http://$IP_ADDR/)
  Home Assistant .. http://$HOST.local:8123    (first visit creates your HA account)
  Pi-hole admin ... http://$HOST.local:8080/admin
  Pi-hole password  sudo cat $PW_FILE

  Next steps:
   1. In your router, reserve IP $IP_ADDR for MAC $MAC (DHCP reservation).
   2. Check Pi-hole works:  nslookup example.com $IP_ADDR
   3. Then set the router's DHCP DNS server to $IP_ADDR.
   4. Log out and back in so '$USER_NAME' can run docker without sudo.

  Log of this run: $LOG
EOF

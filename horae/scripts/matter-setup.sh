#!/usr/bin/env bash
# One-time host prep for the Matter server on horae, then start it.
# Run on the Pi:  sudo bash ~/matter-setup.sh   (safe to re-run)
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo "Run with sudo: sudo bash $0"; exit 1; }

STACK_DIR="/opt/pihub"
IFACE="eth0"

echo "== [1/4] Data directory (container runs as uid 1000) =="
mkdir -p "$STACK_DIR/matter"
chown -R 1000:1000 "$STACK_DIR/matter"
chmod -R u+rwX,go+rX "$STACK_DIR/matter"

echo "== [2/4] IPv6 settings for Thread devices behind Apple border routers =="
# HomePods / Apple TVs advertise routes to the Thread network in IPv6 router
# advertisements; the Pi has to accept them to reach Thread devices.
# accept_ra itself is left alone: 1 is the default and exit-node.sh sets 2.
# The UDP timeout keeps sleepy devices' subscriptions alive through conntrack.
cat >/etc/sysctl.d/60-matter.conf <<CONF
net.ipv6.conf.$IFACE.accept_ra_rt_info_max_plen = 64
CONF
if [[ -e /proc/sys/net/netfilter/nf_conntrack_udp_timeout_stream ]]; then
  echo "net.netfilter.nf_conntrack_udp_timeout_stream = 3600" >>/etc/sysctl.d/60-matter.conf
fi
sysctl -p /etc/sysctl.d/60-matter.conf

# NetworkManager handles router advertisements itself when it manages the link.
if command -v nmcli >/dev/null && nmcli -t -f DEVICE,STATE device | grep -q "^$IFACE:connected"; then
  CONN="$(nmcli -g GENERAL.CONNECTION device show "$IFACE")"
  echo "   NetworkManager manages $IFACE ('$CONN'), ipv6.method=$(nmcli -g ipv6.method connection show "$CONN")"
  echo "   It should be 'auto'. If it is 'disabled' or 'ignore', Thread devices won't be reachable."
fi

echo "== [3/4] Start the Matter server =="
cd "$STACK_DIR"
docker compose up -d matter-server

echo "== [4/4] Check =="
sleep 5
docker ps --filter name=matter-server --format '   {{.Names}}: {{.Status}}'
THREAD_ROUTES="$(ip -6 route show | grep -c '^fd.* via fe80' || true)"
echo "   IPv6 routes to Thread networks: $THREAD_ROUTES"
[[ "$THREAD_ROUTES" -gt 0 ]] || echo "   (none yet is fine without Thread devices or before the HomePod's next advertisement)"
cat <<EOF

  Next, in Home Assistant (http://horae:8123):
    Settings > Devices & services > Add integration > Matter
    Untick the official add-on option and enter: ws://localhost:5580/ws

  Then for each device, in the Apple Home app:
    long-press it > Accessory Settings > Turn On Pairing Mode, copy the code.
    In the HA Companion app: Settings > Devices & services > Add device >
    Matter, say it is already used by another app, and paste the code.
  Logs: docker logs -f matter-server
EOF

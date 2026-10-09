#!/usr/bin/env bash
# Make pihub a Tailscale exit node. Run: sudo bash ~/exit-node.sh
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo "Run with sudo: sudo bash $0"; exit 1; }

echo "== Enable IP forwarding (persists across reboots) =="
cat >/etc/sysctl.d/99-tailscale.conf <<"CONF"
net.ipv4.ip_forward = 1
net.ipv6.conf.all.forwarding = 1
# Keep taking IPv6 addresses/routes from the router while forwarding
net.ipv6.conf.eth0.accept_ra = 2
CONF
sysctl -p /etc/sysctl.d/99-tailscale.conf

echo "== Offer horae as an exit node =="
tailscale set --advertise-exit-node
echo
echo "Done. Now approve it: Tailscale admin -> Machines -> horae -> ... -> Edit route settings -> Use as exit node."

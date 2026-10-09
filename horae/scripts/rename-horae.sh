#!/usr/bin/env bash
# Rename this Pi from pihub to horae (hostname, .local name, Tailscale name).
# Run: sudo bash ~/rename-horae.sh
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo "Run with sudo: sudo bash $0"; exit 1; }
OLD=pihub NEW=horae

echo "== Keep cloud-init from restoring the old name at boot =="
sed -i "s/^hostname: $OLD\$/hostname: $NEW/" /boot/firmware/user-data
grep -q "^hostname: $NEW\$" /boot/firmware/user-data
printf "preserve_hostname: true\n" >/etc/cloud/cloud.cfg.d/99-keep-hostname.cfg

echo "== Hostname and $NEW.local =="
hostnamectl set-hostname "$NEW"
sed -i "s/\b$OLD\b/$NEW/g" /etc/hosts
systemctl restart avahi-daemon

echo "== Tailscale name =="
tailscale set --hostname="$NEW"
sed -i "s/--hostname=$OLD/--hostname=$NEW/" /home/synestri/pi-extras.sh

echo
echo "Hostname: $(hostname)"
grep "$NEW" /etc/hosts
tailscale status --self | head -1
echo "Done. Reconnect with: ssh synestri@$NEW"

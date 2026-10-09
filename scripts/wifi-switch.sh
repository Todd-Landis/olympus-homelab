#!/usr/bin/env bash
# Move a headless Ubuntu machine (netplan + systemd-networkd Wi-Fi) to another Wi-Fi network, with automatic rollback.
#   sudo bash ~/wifi-switch.sh "5016Shoreside"
# Asks for the Wi-Fi password (hidden) and rewrites /etc/netplan/60-wifi.yaml with only that network.
# The switch, the check and any rollback run as a separate systemd job, so a dropped SSH session can't stop them.
# Result: /var/log/wifi-switch.log (readable without sudo).
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo "Run with sudo: sudo bash $0 \"SSID\""; exit 1; }
SSID="${1:?usage: sudo bash $0 \"SSID\"}"
FILE=/etc/netplan/60-wifi.yaml
LOG=/var/log/wifi-switch.log

IFACE=""
for n in /sys/class/net/*; do [[ -d $n/wireless ]] && { IFACE=$(basename "$n"); break; }; done
[[ -n $IFACE ]] || { echo "No Wi-Fi interface found"; exit 1; }
echo "Wi-Fi interface: $IFACE (currently on: $(iw dev "$IFACE" link | sed -n 's/^\s*SSID: //p'))"

read -rsp "Wi-Fi password for $SSID: " PW; echo
[[ ${#PW} -ge 8 ]] || { echo "That password is shorter than 8 characters; nothing changed."; exit 1; }

BACKUP=/root/netplan-backup-$(date +%Y%m%d-%H%M%S)
cp -a /etc/netplan "$BACKUP"
echo "Backed up /etc/netplan to $BACKUP"

# YAML single-quoted strings: only a single quote needs escaping (doubled). Backslashes and " are literal.
q() { printf "'%s'" "$(printf %s "$1" | sed "s/'/''/g")"; }
umask 077
cat >"$FILE" <<EOF
network:
  version: 2
  wifis:
    $IFACE:
      optional: true
      dhcp4: true
      access-points:
        $(q "$SSID"):
          auth:
            key-management: "psk"
            password: $(q "$PW")
EOF
unset PW
chmod 600 "$FILE"
if ! netplan generate; then
  rm -rf /etc/netplan && cp -a "$BACKUP" /etc/netplan
  echo "The new config was invalid; restored the backup. Nothing was applied."; exit 1
fi

echo "$(date '+%F %T') starting switch to $SSID (backup $BACKUP)" >"$LOG"; chmod 644 "$LOG"
systemd-run --quiet --collect --unit="wifi-switch-$(date +%s)" bash -c "
  sleep 2; netplan apply
  for i in \$(seq 1 24); do
    sleep 5
    if iw dev $IFACE link | grep -qF 'SSID: $SSID' && ping -c1 -W3 -I $IFACE 1.1.1.1 >/dev/null 2>&1; then
      echo \"\$(date '+%F %T') OK: on $SSID, \$(ip -4 -br addr show $IFACE | tr -s ' ')\" >>$LOG; exit 0
    fi
  done
  rm -rf /etc/netplan && cp -a $BACKUP /etc/netplan && netplan apply
  echo \"\$(date '+%F %T') ROLLED BACK: $SSID did not come up within 2 minutes; restored $BACKUP\" >>$LOG
"
echo
echo "Switching to $SSID now. This SSH session may freeze; reconnect in about a minute."
echo "If $SSID doesn't work, the old network comes back automatically within 2 minutes."
echo "Result: cat $LOG"

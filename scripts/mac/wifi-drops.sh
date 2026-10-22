#!/usr/bin/env bash
# Why does the Mac lose its connection at about the same time every day? Gathers what the Mac, the router (its log
# on helios), Network Watch and horae saw in a window around that time on each of the last few days.
# Read-only: no sudo, changes nothing, prints nothing secret. Run on the Mac, from the repo:
#   bash scripts/mac/wifi-drops.sh [HH:MM] [days]      (default 15:45, 3 days; the window is 1 hour either side)
# Paste the whole output back. macOS ships bash 3.2: keep this script free of bash 4 features.
set -u
AT=${1:-15:45}
DAYS=${2:-3}
TS_IP=100.115.118.44   # this Mac's Tailscale address (docs/HANDOFF.md)
TS=/Applications/Tailscale.app/Contents/MacOS/Tailscale
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
SSH="ssh -o ConnectTimeout=8 -o BatchMode=yes"

# The windows: "YYYY-MM-DD HH:MM:SS" strings (router and Pi-hole logs are in local time) and epoch seconds.
NOW=$(date "+%F %H:%M:%S"); NOW_S=$(date +%s)
WINDOWS=""; EPOCHS=""
i=$((DAYS - 1))
while [ "$i" -ge 0 ]; do
  day=$(date -v-"${i}"d +%F)
  s=$(date -j -f "%F %H:%M" "$day $AT" -v-60M "+%F %H:%M:%S"); e=$(date -j -f "%F %H:%M" "$day $AT" -v+60M "+%F %H:%M:%S")
  if [[ ! "$s" > "$NOW" ]]; then
    [[ "$e" > "$NOW" ]] && e=$NOW
    WINDOWS="$WINDOWS$s|$e|"
    EPOCHS="$EPOCHS $(date -j -f "%F %H:%M:%S" "$s" +%s) $(date -j -f "%F %H:%M:%S" "$e" +%s)"
  fi
  i=$((i - 1))
done
in_windows() {  # keep lines whose first 19 characters (a local timestamp) fall inside one of the windows
  awk -v w="$WINDOWS" 'BEGIN { n = split(w, a, "|") } { t = substr($0, 1, 19); for (i = 1; i < n; i += 2) if (t >= a[i] && t <= a[i + 1]) { print; next } }'
}
say() { printf '\n== %s\n' "$*"; }

say "The Mac now ($NOW)"
IF=$(networksetup -listallhardwareports | awk '/Wi-Fi/ { getline; print $2; exit }'); IF=${IF:-en0}
MAC=$(ifconfig "$IF" 2>/dev/null | awk '/ether/ { print $2 }')
LAN_IP=$(ipconfig getifaddr "$IF" 2>/dev/null || true)
HOST=$(scutil --get LocalHostName 2>/dev/null || true)
echo "Wi-Fi $IF · hardware address $MAC · address ${LAN_IP:-none} · name $HOST · macOS $(sw_vers -productVersion)"
system_profiler SPAirPortDataType 2>/dev/null | awk '/Current Network Information:/ { f = 1; n = 0 } f && n < 14 { print; n++ }' \
  | grep -E "PHY Mode|Channel|Country|Network Type|Security|Signal / Noise|Transmit Rate" | sed 's/^ */  /'
lease=$(ipconfig getpacket "$IF" 2>/dev/null | awk -F': ' '/^lease_time/ { print $2 }')
[ -n "$lease" ] && echo "  DHCP lease: $(printf '%d' "$lease") s"
ipconfig getsummary "$IF" 2>/dev/null | grep -i -E "LeaseStart|LeaseExpir|RouterIPAddress" | sed 's/^ */  /'
echo "  DNS servers in use: $(scutil --dns | awk '/nameserver\[/ { print $3 }' | sort -u | tr '\n' ' ')"
if [ -x "$TS" ]; then
  echo "  Tailscale $("$TS" version 2>/dev/null | head -1): $("$TS" debug prefs 2>/dev/null | grep -E '"(ExitNodeID|ExitNodeIP|ExitNodeAllowLANAccess|CorpDNS|RouteAll|WantRunning)"' | tr -d ' \n')"
  "$TS" status 2>/dev/null | grep -i "exit node" | sed 's/^/  /'
else
  echo "  Tailscale command line not found at $TS"
fi

say "The Mac's own log in each window (Wi-Fi joins and drops, address and DNS changes)"
set -- $EPOCHS
while [ $# -ge 2 ]; do
  s=$(date -r "$1" "+%F %H:%M:%S"); e=$(date -r "$2" "+%F %H:%M:%S"); shift 2
  echo "-- $s to ${e#* }"
  log show --style compact --start "$s" --end "$e" --predicate \
    '(process == "configd" AND eventMessage CONTAINS "network changed") OR (process == "airportd" AND (eventMessage CONTAINS[c] "disassoc" OR eventMessage CONTAINS[c] "deauth" OR eventMessage CONTAINS[c] "link down")) OR (eventMessage CONTAINS[c] "link down")' \
    2>/dev/null | grep -v -E '^(Timestamp|Filtering)' | cut -c1-200 | tail -40
done

say "Router log (the ASUS sends it to helios): lines about this Mac, last $DAYS days"
if $SSH helios 'cat ~/pihole-watch/data/router.log.1 ~/pihole-watch/data/router.log 2>/dev/null' > "$TMP/router.log"; then
  echo "($(wc -l < "$TMP/router.log" | tr -d ' ') lines kept, from $(head -c 19 "$TMP/router.log"))"
  pat=$(printf '%s' "$MAC" | tr 'A-Z' 'a-z')
  [ -n "$LAN_IP" ] && pat="$pat|$LAN_IP[^0-9]"
  [ -n "$HOST" ] && pat="$pat|$HOST"
  grep -i -E "$pat" "$TMP/router.log" | cut -c1-200 | tail -60
  echo "-- the router itself in each window: radar and channel changes, restarts, internet line, weak-signal kicks"
  in_windows < "$TMP/router.log" | grep -i -E "radar|dfs|chanspec|channel|acsd|restart|reboot|watchdog|start|stop|wan|link|roamast|kernel" \
    | cut -c1-200 | tail -40
else
  echo "Couldn't reach helios over SSH."
fi

say "This Mac's lookups reaching Pi-hole, per minute (Network Watch's copy)"
echo "(t = through Tailscale, L = straight over Wi-Fi, B = both, . = none; a run of dots is when lookups stopped arriving)"
args=""; set -- $EPOCHS
while [ $# -ge 2 ]; do args="$args $1:$(date -r "$1" +%F_%H%M):$2"; shift 2; done
$SSH helios "docker exec -i pihole-watch python - $TS_IP ${MAC:-none} ${LAN_IP:-none} $args" <<'PY' || echo "Couldn't read Network Watch on helios."
import sqlite3, sys
ts_ip, mac, lan_ip, windows = sys.argv[1], sys.argv[2].lower(), sys.argv[3], sys.argv[4:]
con = sqlite3.connect("/data/watch.db", timeout=30)
for w in windows:
    start, label, end = w.split(":")
    day, hhmm = label.split("_")
    start, end, base = int(start), int(end), int(hhmm[:2]) * 60 + int(hhmm[2:])
    mins = max(1, (end - start) // 60)
    marks, status = [set() for _ in range(mins)], {}
    for t, client, dev, st in con.execute("SELECT t, client, dev, status FROM q WHERE t >= ? AND t <= ? AND (client IN (?, ?) OR dev = ?)",
                                          (start, end, ts_ip, lan_ip, mac)):
        marks[min(int(t - start) // 60, mins - 1)].add("t" if client == ts_ip else "L")
        status[st] = status.get(st, 0) + 1
    hm = lambda m: "%02d:%02d" % (((base + m) // 60) % 24, (base + m) % 60)
    print("-- %s %s to %s" % (day, hm(0), hm(mins - 1)))
    row = "".join("B" if len(s) == 2 else (s.pop() if s else ".") for s in [set(x) for x in marks])
    for k in range(0, mins, 30):
        print("   %s %s" % (hm(k), row[k:k + 30]))
    gaps, run = [], None
    for k, c in enumerate(row + "x"):
        if c == "." and run is None:
            run = k
        elif c != "." and run is not None:
            if k - run >= 3:
                gaps.append("%s–%s (%d min)" % (hm(run), hm(k - 1), k - run))
            run = None
    print("   no lookups for 3+ min: %s" % (", ".join(gaps) or "none"))
    print("   answers: %s" % (", ".join("%s %d" % kv for kv in sorted(status.items(), key=lambda kv: -kv[1])) or "none"))
PY

say "horae (Pi-hole and the Tailscale exit node)"
# shellcheck disable=SC2086
$SSH horae "bash -s $EPOCHS" <<'SH' || echo "Couldn't reach horae over SSH."
echo "booted $(uptime -s); up $(uptime -p)"
docker inspect -f '{{.Name}}: started {{.State.StartedAt}}, restarted {{.RestartCount}} times' pihole homeassistant matter-server homepage 2>&1
echo "tailscale $(tailscale version 2>/dev/null | head -1)"
echo "-- timers (LAST = when each one last ran)"
systemctl list-timers --all --no-pager 2>/dev/null | cut -c1-150
if ! id -nG | grep -q -w -E 'adm|systemd-journal'; then echo "(the system journal needs sudo here; skipped)"; exit 0; fi
while [ $# -ge 2 ]; do
  s=$1; e=$2; shift 2
  echo "-- journal $(date -d "@$s" '+%F %H:%M') to $(date -d "@$e" '+%H:%M'): warnings, Tailscale, Docker, network, kernel, services started"
  { journalctl --no-pager -q -o short-iso --since "@$s" --until "@$e" -p warning
    journalctl --no-pager -q -o short-iso --since "@$s" --until "@$e" -u tailscaled -u docker -u NetworkManager -u dhcpcd -u systemd-networkd
    journalctl --no-pager -q -o short-iso --since "@$s" --until "@$e" -k
    journalctl --no-pager -q -o short-iso --since "@$s" --until "@$e" _PID=1 | grep -E "Start(ed|ing)|Finished"
  } 2>&1 | sort -u | grep -v -E "netcheck|magicsock: (endpoints|derp)|derphttp|pam_unix|CRON\[" | cut -c1-200 | tail -40
done
SH
echo "-- Pi-hole's own log in each window (restarts, warnings, errors)"
$SSH horae "docker exec pihole sh -c 'cat /var/log/pihole/FTL.log.1 /var/log/pihole/FTL.log 2>/dev/null'" 2>/dev/null \
  | in_windows | grep -i -E "warn|err|crit|started|shutting|terminat|restart|reload|gravity|timeout|refused" | cut -c1-200 | tail -40

say "Done. Paste everything above back to Claude."

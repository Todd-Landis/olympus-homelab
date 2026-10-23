#!/usr/bin/env bash
# Why does the Mac lose its connection at about the same time every day? Gathers what the Mac, the router (its log
# on helios), Network Watch and horae saw in a window around that time on each of the last few days.
# Read-only: no sudo, changes nothing, prints nothing secret. Run on the Mac, from the repo:
#   bash scripts/mac/wifi-drops.sh [HH:MM] [days]      (default 15:45, 3 days; the window is 1 hour either side)
#   bash scripts/mac/wifi-drops.sh now                 while it's broken, before turning Wi-Fi off: 10 s of checks
#   bash scripts/mac/wifi-drops.sh watch               leave running: catches each outage by itself (~/wifi-watch.log)
#   bash scripts/mac/wifi-drops.sh link HH:MM          the Mac's signal, beacons and traffic every 30 s around HH:MM today
# Paste the whole output back. macOS ships bash 3.2: keep this script free of bash 4 features.
set -u
TS_IP=100.115.118.44   # this Mac's Tailscale address (docs/HANDOFF.md)
TS=/Applications/Tailscale.app/Contents/MacOS/Tailscale
IF=$(networksetup -listallhardwareports | awk '/Wi-Fi/ { getline; print $2; exit }'); IF=${IF:-en0}

quick_check() {  # which layer is stuck? Each check uses only what it names, with a short timeout
  echo "== Quick check $(date '+%F %H:%M:%S')"
  echo "Wi-Fi address: $(ipconfig getifaddr "$IF" 2>/dev/null || echo none) · DNS in use: $(scutil --dns | awk '/nameserver\[/ { print $3 }' | sort -u | tr '\n' ' ')"
  ok() { printf '  %-4s %s\n' "$1" "$2"; }
  run() {  # run "label" command...  ->  OK/FAIL plus the first line of output
    local label=$1; shift
    local out; out=$("$@" 2>&1 | head -1)
    if [ -n "$out" ] && ! printf '%s' "$out" | grep -q -i -E "timed out|timeout|no reply|no servers|unreachable|error|failed| 0 packets received|100.0% packet loss|^000"; then
      ok OK "$label: $out"; return 0
    fi
    ok FAIL "$label: ${out:-no answer}"; return 1
  }
  run "1 router over Wi-Fi (ping 192.168.50.1)" sh -c 'ping -c 2 -t 3 192.168.50.1 | grep -E "packets"'; R1=$?
  run "2 horae over Wi-Fi (ping 192.168.50.2)" sh -c 'ping -c 2 -t 3 192.168.50.2 | grep -E "packets"'; R2=$?
  run "3 Pi-hole straight over Wi-Fi (apple.com)" dig +time=2 +tries=1 +short @192.168.50.2 apple.com; R3=$?
  run "4 Pi-hole through Tailscale, the Mac's normal way" dig +time=2 +tries=1 +short @100.100.100.100 apple.com; R4=$?
  run "5 internet with no lookup (https://1.1.1.1)" curl -sS -o /dev/null --max-time 4 -w '%{http_code}' https://1.1.1.1; R5=$?
  run "6 a website the normal way (https://www.apple.com)" curl -sS -o /dev/null --max-time 6 -w '%{http_code}' https://www.apple.com; R6=$?
  [ -x "$TS" ] && run "7 Tailscale to horae" "$TS" ping -c 2 --timeout 3s horae
  [ -x "$TS" ] && "$TS" status 2>/dev/null | grep -E "^100\.123\.23\.100" | sed 's/^/       path: /'
  echo "-- what that means"
  if [ "$R1" -ne 0 ]; then
    echo "  The Mac says it's on Wi-Fi but can't even reach the router: the Wi-Fi link itself is stuck. That's the Mac's"
    echo "  Wi-Fi (or the router's radio), not Pi-hole or Tailscale."
  elif [ "$R4" -ne 0 ] && [ "$R3" -eq 0 ]; then
    echo "  Wi-Fi and Pi-hole are fine; lookups that go through Tailscale fail. Tailscale's route to horae is the cause."
  elif [ "$R3" -ne 0 ] && [ "$R4" -ne 0 ]; then
    echo "  Pi-hole isn't answering at all (horae, or Pi-hole on it)."
  elif [ "$R5" -ne 0 ]; then
    echo "  Lookups work but the internet doesn't: the router's internet line (or the modem)."
  elif [ "$R6" -ne 0 ]; then
    echo "  Everything checked works except a normal website: send this to Claude as is."
  else
    echo "  Everything works right now. If it was broken a moment ago, it recovered on its own."
  fi
}
details() {  # what the Mac itself says about the link while it's stuck
  echo "-- the Mac's side"
  ifconfig "$IF" 2>/dev/null | grep -E "status|inet " | sed 's/^[[:space:]]*/  /'
  echo "  router's hardware address as the Mac knows it: $(arp -n 192.168.50.1 2>/dev/null | awk '{ print $4 }')"
  echo "  default route: $(route -n get default 2>/dev/null | awk '/gateway|interface/ { printf "%s ", $2 }')"
  system_profiler SPAirPortDataType 2>/dev/null | awk '/Current Network Information:/ { f = 1; n = 0 } f && n < 14 { print; n++ }' \
    | grep -E "Channel|Signal / Noise|Transmit Rate|PHY Mode" | head -4 | sed 's/^ */  /'
}
healthy() {  # router, Pi-hole straight over Wi-Fi, and the internet all answer
  ping -c 1 -t 2 192.168.50.1 >/dev/null 2>&1 && dig +time=2 +tries=1 +short @192.168.50.2 apple.com 2>/dev/null | grep -q '^[0-9]' \
    && ping -c 1 -t 2 1.1.1.1 >/dev/null 2>&1
}

if [ "${1:-}" = now ]; then
  # Also saved to a file, since the internet may be down while this runs.
  OUT=~/wifi-check-$(date +%Y%m%d-%H%M%S).txt
  { quick_check; details; echo "Saved to $OUT"; } 2>&1 | tee "$OUT"
  exit 0
fi

if [ "${1:-}" = link ]; then
  # The Mac's own Wi-Fi measurements (airportd logs them every 5 s), in 30 s steps around a moment today. Needs nothing
  # but the Mac, so it works with Tailscale off. Reading it: "router beacons" is how many of the router's ~10-a-second
  # beacons the Mac heard (about 300 per 30 s is healthy). Beacons fine but "data frames" near 0 while you were trying
  # to use it = the link was up but traffic stopped (a stall). Beacons dropping = the Mac stopped hearing the router.
  AT=${2:?usage: bash $0 link HH:MM [minutes before] [minutes after]}
  day=$(date +%F)
  s=$(date -j -v-"${3:-8}"M -f "%F %H:%M" "$day $AT" "+%F %H:%M:%S"); e=$(date -j -v+"${4:-3}"M -f "%F %H:%M" "$day $AT" "+%F %H:%M:%S")
  echo "== The Mac's Wi-Fi measurements, $s to ${e#* } (every 30 s: weakest signal, busiest air, slowest rates, totals)"
  log show --style compact --start "$s" --end "$e" --predicate 'process == "airportd" AND eventMessage CONTAINS "LQM"' 2>/dev/null | awk '
    function val(name,   r) { if (match($0, name "=-?[0-9.]+")) return substr($0, RSTART + length(name) + 1, RLENGTH - length(name) - 1) + 0; return "" }
    function flush() {
      if (cur != "") printf "  %s  signal %4s dBm  air busy %3d%%  up %4s Mbps  down %4s Mbps  router beacons %3d  data frames %5d\n", \
        cur, rssi, cca, (tx < 0 ? "-" : int(tx / 1000)), (rx < 0 ? "-" : int(rx / 1000)), bcn, data
    }
    $2 ~ /^[0-9][0-9]:/ {
      t = substr($2, 1, 8); b = substr(t, 1, 6) (substr(t, 7, 2) + 0 < 30 ? "00" : "30")
      if (b != cur) { flush(); cur = b; rssi = 0; cca = 0; tx = -1; rx = -1; bcn = 0; data = 0 }
      if (index($0, "] LQM: rssi=")) { v = val("rssi"); if (rssi == 0 || v < rssi) rssi = v; c = val("cca"); if (c > cca) cca = c }
      else if (index($0, "WeightAvgLQM")) { v = val("txRate"); if (tx < 0 || v < tx) tx = v; v = val("rxRate"); if (rx < 0 || v < rx) rx = v }
      else if (index($0, "rxBeaconMbss=")) { bcn += val("rxBeaconMbss"); data += val("rxDataUcastMbss") }
    }
    END { flush() }'
  echo "== Anything the Wi-Fi driver or macOS flagged in that time"
  log show --style compact --start "$s" --end "$e" --predicate 'process == "kernel" OR process == "airportd" OR process == "wifid"' 2>/dev/null \
    | grep -i -E "stall|watchdog|beacon ?lo(ss|st)|bcn ?lo|tx ?fail|reset|recover|link ?(down|lost)|disassoc|deauth|roam(ing)? (start|scan)|poorlink|badrssi" \
    | grep -v -E "unsupported (get|set) ioctl|NSEntityDescription|RoamMO" | cut -c1-200 | head -40
  exit 0
fi

if [ "${1:-}" = watch ]; then
  # Checks every 5 s; two failures in a row = an outage: runs the full check at that moment and logs it, then logs
  # when it comes back. A gap of more than 30 s between checks means the Mac slept, which isn't an outage.
  LOG=~/wifi-watch.log
  echo "Watching this Mac's connection every 5 s. Leave this window open; Ctrl-C stops it. Outages go to $LOG"
  echo "== watch started $(date '+%F %H:%M:%S')" >> "$LOG"
  bad=0; down=""; down_s=0; last=$(date +%s)
  while :; do
    now_s=$(date +%s)
    if [ $((now_s - last)) -gt 30 ]; then bad=0; [ -n "$down" ] && echo "$(date '+%F %H:%M:%S') (the Mac slept)" | tee -a "$LOG"; down=""; fi
    if healthy; then
      if [ -n "$down" ]; then
        echo "$(date '+%F %H:%M:%S') back after $((now_s - down_s)) s ($(ifconfig "$IF" 2>/dev/null | grep -q 'status: active' && echo 'Wi-Fi on' || echo 'Wi-Fi off'))" | tee -a "$LOG"
        down=""
      fi
      bad=0
    else
      bad=$((bad + 1))
      if [ "$bad" -eq 2 ] && [ -z "$down" ]; then
        down=$(date '+%F %H:%M:%S'); down_s=$now_s
        { echo; echo "== OUTAGE noticed $down"; quick_check; details; } 2>&1 | tee -a "$LOG"
        printf '\a'   # a beep
      fi
    fi
    last=$(date +%s)   # after the checks, which can take 30 s during an outage, so they don't look like sleep
    sleep 5
  done
fi

AT=${1:-15:45}
DAYS=${2:-3}
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
SSH="ssh -o ConnectTimeout=8 -o BatchMode=yes"

# The windows: "YYYY-MM-DD HH:MM:SS" strings (router and Pi-hole logs are in local time) and epoch seconds.
NOW=$(date "+%F %H:%M:%S"); NOW_S=$(date +%s)
WINDOWS=""; EPOCHS=""
i=$((DAYS - 1))
while [ "$i" -ge 0 ]; do
  day=$(date -v-"${i}"d +%F)
  # -v before -f: macOS date stops reading options at the date itself, and would silently ignore a -v after it
  s=$(date -j -v-60M -f "%F %H:%M" "$day $AT" "+%F %H:%M:%S"); e=$(date -j -v+60M -f "%F %H:%M" "$day $AT" "+%F %H:%M:%S")
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
around() {  # around "YYYY-MM-DD HH:MM:SS" -90 +60  ->  that time shifted by each number of seconds
  local t=$1; shift
  for d in "$@"; do date -j -v"${d}"S -f "%F %H:%M:%S" "$t" "+%F %H:%M:%S"; done
}
WIFI_LOG='process IN {"airportd", "wifid", "configd", "mDNSResponder"} OR subsystem BEGINSWITH "com.apple.wifi" OR (process == "kernel" AND eventMessage CONTAINS[c] "link")'
WIFI_WORDS='disassoc|deauth|link ?(down|up|lost|quality)|roam|beacon|reason|leav|disconnect|network changed|bssid|rssi'

say "The Mac now ($NOW)"
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
  echo "  How the Mac reaches horae (straight across the LAN would be via 192.168.50.2):"
  "$TS" ping -c 3 horae 2>&1 | sed 's/^/    /'
else
  echo "  Tailscale command line not found at $TS"
fi

say "Router log (the ASUS sends it to helios): lines about this Mac, last $DAYS days"
if $SSH -n helios 'cat ~/pihole-watch/data/router.log.1 ~/pihole-watch/data/router.log 2>/dev/null' > "$TMP/router.log"; then
  echo "($(wc -l < "$TMP/router.log" | tr -d ' ') lines kept, from $(head -c 19 "$TMP/router.log"))"
  pat=$(printf '%s' "$MAC" | tr 'A-Z' 'a-z')
  [ -n "$LAN_IP" ] && pat="$pat|$LAN_IP[^0-9]"
  [ -n "$HOST" ] && pat="$pat|$HOST"
  grep -i -E "$pat" "$TMP/router.log" | grep -v -E "DHCP(REQUEST|ACK)|group key" | cut -c1-200 | tail -40
  echo "-- address requests from the Mac per hour (a healthy Mac asks every few hours; dozens an hour means it keeps reconnecting)"
  grep -i "$MAC" "$TMP/router.log" | grep DHCPREQUEST | cut -c1-13 | uniq -c | awk '{ printf "   %s %s:00  %d\n", $2, $3, $1 }' | tail -30
  echo "-- the router itself in each window: radar and channel changes, restarts, internet line, weak-signal kicks"
  in_windows < "$TMP/router.log" | grep -i -E "radar|dfs|chanspec|channel|acsd|restart|reboot|watchdog|start|stop|wan|link|roamast|kernel" \
    | cut -c1-200 | tail -40
else
  echo "Couldn't reach helios over SSH."
fi

say "Every time this Mac dropped off the Wi-Fi (router log), and when it came back"
awk -v mac="$(printf '%s' "$MAC" | tr 'A-Z' 'a-z')" '
  { l = tolower($0) }
  index(l, mac) == 0 || index(l, "wlceventd") == 0 { next }
  { t = substr($0, 1, 19); radio = ""; if (match(l, /wl[0-9]+(\.[0-9]+)?:/)) radio = substr(l, RSTART, RLENGTH - 1) }
  l ~ /disassoc|deauth/ {
    if (left == "") { left = t; why = $0; sub(/.*reason: /, "", why); sub(/, rssi.*/, "", why); from = radio }
    next
  }
  l ~ /assoc/ && left != "" {
    rssi = ""; if (match(l, /rssi:-?[0-9]+/)) rssi = substr(l, RSTART + 5, RLENGTH - 5)
    printf "%s left %s, back %s on %s (signal %s dBm) · %s\n", left, from, substr(t, 12), radio, rssi, substr(why, 1, 70); left = ""
  }
  END { if (left != "") printf "%s left %s, not back yet · %s\n", left, from, substr(why, 1, 70) }
' "$TMP/router.log" 2>/dev/null | tee "$TMP/drops" | tail -40
[ -s "$TMP/drops" ] || echo "(none in the router log)"

say "The Mac's side of the last few drops: its Wi-Fi log from 90 s before to 60 s after"
tail -6 "$TMP/drops" 2>/dev/null | cut -c1-19 | while read -r d t; do
  set -- $(around "$d $t" -90 +60 | tr ' ' '_'); s=${1/_/ }; e=${2/_/ }
  echo "-- $d $t"
  log show --style compact --start "$s" --end "$e" --predicate "$WIFI_LOG" 2>/dev/null \
    | grep -i -E "$WIFI_WORDS" | cut -c1-220 | head -25
  pmset -g log 2>/dev/null | awk -v s="$s" -v e="$e" '{ t = substr($0, 1, 19) } t >= s && t <= e && ($4 == "Sleep" || $4 == "Wake" || $4 == "DarkWake")' | cut -c1-200
done

say "Sleep and wake on the Mac in each window (a closed lid or idle sleep drops Wi-Fi too)"
pmset -g log 2>/dev/null | awk '$4 == "Sleep" || $4 == "Wake" || $4 == "DarkWake"' | in_windows | cut -c1-160 | tail -30

say "The Mac's own Wi-Fi log in each window"
set -- $EPOCHS
while [ $# -ge 2 ]; do
  s=$(date -r "$1" "+%F %H:%M:%S"); e=$(date -r "$2" "+%F %H:%M:%S"); shift 2
  echo "-- $s to ${e#* }"
  log show --style compact --start "$s" --end "$e" --predicate "$WIFI_LOG" 2>/dev/null \
    | grep -i -E "network changed|disassoc|deauth|link ?(down|lost)|disconnect" | cut -c1-200 | tail -25
done

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
$SSH -n horae "docker exec pihole sh -c 'cat /var/log/pihole/FTL.log.1 /var/log/pihole/FTL.log 2>/dev/null'" 2>/dev/null \
  | in_windows | grep -i -E "warn|err|crit|started|shutting|terminat|restart|reload|gravity|timeout|refused" | cut -c1-200 | tail -40

say "Done. Paste everything above back to Claude."

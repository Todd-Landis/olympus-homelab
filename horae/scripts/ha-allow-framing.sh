#!/usr/bin/env bash
# Let Olympus show Home Assistant in its Apps panel (an iframe on http://helios/).
# HA sends "X-Frame-Options: SAMEORIGIN" by default, which blocks that; this turns it off.
# Run on horae: sudo bash ~/ha-allow-framing.sh
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo "Run with sudo: sudo bash $0"; exit 1; }

CONF=/opt/pihub/homeassistant/configuration.yaml
[[ -f $CONF ]] || { echo "No $CONF yet. Open http://horae:8123 once so Home Assistant creates it, then re-run."; exit 1; }

echo "== Edit $CONF =="
BACKUP="$CONF.bak-$(date +%Y%m%d-%H%M%S)"
cp -p "$CONF" "$BACKUP"
echo "Backup: $BACKUP"

# Set use_x_frame_options: false under the top-level http: block (adding the block if there isn't one).
RESULT=$(python3 - "$CONF" <<"PY"
import re, sys
path = sys.argv[1]
lines = open(path).read().split("\n")
http = next((i for i, l in enumerate(lines) if re.match(r"^http:\s*(#.*)?$", l)), None)
if http is None:
    if any(re.match(r"^http:", l) for l in lines):
        print("include"); sys.exit()   # e.g. "http: !include http.yaml": leave it to a human
    while lines and lines[-1] == "":
        lines.pop()
    lines += ["", "http:", "  use_x_frame_options: false", ""]
    print("added")
else:
    end = next((i for i in range(http + 1, len(lines)) if lines[i] and not lines[i][0].isspace() and not lines[i].startswith("#")), len(lines))
    block = range(http + 1, end)
    indent = next((re.match(r"^(\s+)", lines[i]).group(1) for i in block if lines[i].strip() and not lines[i].lstrip().startswith("#")), "  ")
    found = next((i for i in block if re.match(r"^\s+use_x_frame_options\s*:", lines[i])), None)
    if found is not None and re.match(r"^\s+use_x_frame_options\s*:\s*false\b", lines[found]):
        print("already"); sys.exit()
    if found is not None:
        lines[found] = f"{indent}use_x_frame_options: false"
    else:
        lines.insert(http + 1, f"{indent}use_x_frame_options: false")
    print("changed")
open(path, "w").write("\n".join(lines))
PY
)
case "$RESULT" in
  already) echo "Already set; nothing to change."; rm -f "$BACKUP"; exit 0 ;;
  include) echo "Your http: settings live in an !include file. Add 'use_x_frame_options: false' there by hand."; rm -f "$BACKUP"; exit 1 ;;
  added)   echo "Added an http: block." ;;
  changed) echo "Updated the existing http: block." ;;
esac
grep -n -A3 '^http:' "$CONF"

echo "== Check the config (takes a minute or two on the Pi) =="
if ! docker exec homeassistant python -m homeassistant --script check_config -c /config; then
  cp -p "$BACKUP" "$CONF"
  echo "Config check failed, so the original file is restored. Nothing was restarted."
  exit 1
fi

echo "== Restart Home Assistant =="
docker restart homeassistant >/dev/null
printf "Waiting for it to come back"
for _ in $(seq 60); do
  if headers=$(curl -fsS --max-time 3 -D - -o /dev/null http://127.0.0.1:8123/ 2>/dev/null); then
    echo
    if grep -qi '^x-frame-options' <<<"$headers"; then
      echo "Home Assistant is up but still sends X-Frame-Options. Check $CONF."; exit 1
    fi
    echo "Done. Home Assistant no longer blocks framing; its tab in Olympus' Apps panel switches over within about 20 s."
    exit 0
  fi
  printf "."; sleep 3
done
echo
echo "Home Assistant hasn't answered after 3 minutes. Check: docker logs --tail 50 homeassistant"
exit 1

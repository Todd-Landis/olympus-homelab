#!/usr/bin/env bash
# Install the Olympus theme in Home Assistant (theme + font loader), and make sure HA loads them.
# Copy the files first from this repo:  ./deploy.sh horae-ha
# Then on horae:                         sudo bash ~/olympus-ha/ha-theme.sh     (safe to re-run)
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo "Run with sudo: sudo bash $0"; exit 1; }

SRC="$(cd "$(dirname "$0")" && pwd)"
HA=/opt/pihub/homeassistant
CONF=$HA/configuration.yaml
[[ -f $CONF ]] || { echo "No $CONF yet. Open http://horae:8123 once so Home Assistant creates it, then re-run."; exit 1; }
[[ -f $SRC/olympus.yaml && -f $SRC/fonts.js ]] || { echo "Missing olympus.yaml or fonts.js next to this script. Run ./deploy.sh horae-ha first."; exit 1; }

echo "== [1/3] Theme files =="
restart=no
[[ -d $HA/www ]] || restart=yes   # Home Assistant only serves /local/ if www/ existed when it started
install -d -m 755 "$HA/themes" "$HA/www/olympus"
install -m 644 "$SRC/olympus.yaml" "$HA/themes/olympus.yaml"
install -m 644 "$SRC/fonts.js" "$HA/www/olympus/fonts.js"
chown -R --reference="$HA" "$HA/themes" "$HA/www/olympus"
echo "   $HA/themes/olympus.yaml"
echo "   $HA/www/olympus/fonts.js"

echo "== [2/3] configuration.yaml: frontend themes + font loader =="
BACKUP="$CONF.bak-$(date +%Y%m%d-%H%M%S)"
cp -p "$CONF" "$BACKUP"
# Under the top-level frontend: block, make sure there is
#   themes: !include_dir_merge_named themes
#   extra_module_url: [... /local/olympus/fonts.js]
# adding the block if there isn't one. Anything unusual (an !include, an inline list) is left to a human.
RESULT=$(python3 - "$CONF" <<"PY"
import re, sys
path, URL = sys.argv[1], "/local/olympus/fonts.js"
lines = open(path).read().split("\n")
notes, changed = [], False
top = lambda l: l and not l[0].isspace() and not l.startswith("#")
fe = next((i for i, l in enumerate(lines) if re.match(r"^frontend:\s*(#.*)?$", l)), None)
if fe is None:
    if any(re.match(r"^frontend:", l) for l in lines):
        print("manual:frontend: is an !include; add the lines from docs/DESIGN.md (Home Assistant) by hand"); sys.exit()
    while lines and lines[-1] == "":
        lines.pop()
    lines += ["", "frontend:", "  themes: !include_dir_merge_named themes", "  extra_module_url:", f"    - {URL}", ""]
    changed = True
else:
    end = next((i for i in range(fe + 1, len(lines)) if top(lines[i])), len(lines))
    body = [i for i in range(fe + 1, end) if lines[i].strip() and not lines[i].lstrip().startswith("#")]
    ind = re.match(r"^(\s+)", lines[body[0]]).group(1) if body else "  "
    key = lambda k: next((i for i in body if re.match(rf"^{ind}{k}\s*:", lines[i])), None)
    t = key("themes")
    if t is None:
        lines.insert(fe + 1, f"{ind}themes: !include_dir_merge_named themes"); changed = True
        end += 1; body = [fe + 1] + [i + 1 for i in body]
    elif "!include_dir_merge_named" not in lines[t]:
        notes.append("themes: is set differently; check that themes/olympus.yaml is loaded")
    m = key("extra_module_url")
    if m is None:
        at = max(body) + 1 if body else fe + 1   # right after the block's last line, before any blank lines
        lines[at:at] = [f"{ind}extra_module_url:", f"{ind}  - {URL}"]; changed = True
    elif URL in "\n".join(lines[m:end]):
        pass
    elif re.match(rf"^{ind}extra_module_url\s*:\s*(#.*)?$", lines[m]):
        items = [i for i in range(m + 1, end) if re.match(r"^\s+-\s", lines[i])]
        item_ind = re.match(r"^(\s+)-", lines[items[0]]).group(1) if items else ind + "  "
        lines.insert((items[-1] if items else m) + 1, f"{item_ind}- {URL}"); changed = True
    else:
        notes.append(f"extra_module_url is written inline; add {URL} to it by hand")
if changed:
    open(path, "w").write("\n".join(lines))
print(("changed" if changed else "already") + "".join("|" + n for n in notes))
PY
)
case "$RESULT" in
  manual:*) echo "   ${RESULT#manual:}"; rm -f "$BACKUP"; exit 1 ;;
  already*) echo "   Already set."; rm -f "$BACKUP" ;;
  changed*) echo "   Updated (backup: $BACKUP)"; restart=yes ;;
esac
if [[ $RESULT == *"|"* ]]; then tr '|' '\n' <<<"${RESULT#*|}" | sed 's/^/   Note: /'; fi
grep -n -A6 '^frontend:' "$CONF" | sed 's/^/   /' || true

if [[ $restart == yes ]]; then
  echo "== [3/3] Check the config, then restart Home Assistant (a minute or two on the Pi) =="
  if [[ -f $BACKUP ]] && ! docker exec homeassistant python -m homeassistant --script check_config -c /config; then
    cp -p "$BACKUP" "$CONF"
    echo "Config check failed, so the original file is restored. Nothing was restarted."
    exit 1
  fi
  docker restart homeassistant >/dev/null
  printf "   Waiting for it to come back"
  for _ in $(seq 60); do
    if curl -fsS --max-time 3 -o /dev/null http://127.0.0.1:8123/local/olympus/fonts.js 2>/dev/null; then echo " up."; break; fi
    printf "."; sleep 3
  done
  curl -fsS --max-time 3 -o /dev/null http://127.0.0.1:8123/ 2>/dev/null || echo " not back after 3 minutes. Check: docker logs --tail 50 homeassistant"
else
  echo "== [3/3] Reload themes =="
  echo "   Nothing in configuration.yaml changed, so no restart. In Home Assistant: Developer tools > YAML > Themes (reload)."
fi
cat <<EOF

  Pick the theme: your profile (bottom left) > Browser settings > Theme > Olympus.
  Make it the default on every device: Developer tools > Actions > "Frontend: Set the default theme", name: Olympus.
  Undo: delete $HA/themes/olympus.yaml and $HA/www/olympus, remove the lines under frontend:, restart.
EOF

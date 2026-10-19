#!/usr/bin/env bash
# Adult sites, on horae's Pi-hole: (1) remove every lookup of them from Pi-hole's history for good, then (2) block them.
# "Adult sites" = OISD's NSFW list, the one Network Watch tags "adult" with (a site counts if it or a parent domain is listed).
#
# Normally run by  ./deploy.sh adult  (copies this script and Network Watch's copy of the list, runs it, then cleans
# Network Watch's own history). By hand on horae:  sudo bash ~/olympus-adult/adult-content.sh [purge|block|all]
# Safe to re-run. Purging stops Pi-hole for about a minute: DNS is down for every device at home meanwhile.
set -Eeuo pipefail   # -E: the "start Pi-hole again" safety net below also covers failures inside functions
[[ $EUID -eq 0 ]] || { echo "Run with sudo: sudo bash $0"; exit 1; }

SRC="$(cd "$(dirname "$0")" && pwd)"
STACK=/opt/pihub
DB=$STACK/pihole/pihole-FTL.db
LIST=$SRC/adult.txt                              # the list to match history against (deploy.sh copies Network Watch's)
LIST_URL=https://nsfw.oisd.nl/domainswild2       # fallback download, the same list Network Watch uses
BLOCK_URL=https://nsfw.oisd.nl                   # the same OISD list in Adblock format: Pi-hole then blocks subdomains too
STEP=${1:-all}
[[ $STEP =~ ^(purge|block|all)$ ]] || { echo "usage: sudo bash $0 [purge|block|all]"; exit 1; }

compose() { (cd "$STACK" && docker compose "$@"); }
wait_for_pihole() {
  printf "   Waiting for Pi-hole to answer"
  for _ in $(seq 60); do
    if curl -fsS --max-time 2 -o /dev/null http://127.0.0.1:8080/api/info/login 2>/dev/null; then echo " up."; return 0; fi
    printf "."; sleep 2
  done
  echo; echo "   Pi-hole hasn't come back after 2 minutes. Check: docker logs --tail 50 pihole"; return 1
}

purge() {
  echo "== Remove adult-site lookups from Pi-hole's history =="
  [[ -f $DB ]] || { echo "   No $DB. Is Pi-hole set up in $STACK?"; exit 1; }
  if [[ ! -s $LIST ]]; then  # before Pi-hole stops: the download needs DNS
    echo "   No copy of the list beside this script; downloading $LIST_URL"
    curl -fsS --max-time 120 -A "olympus adult-content.sh" -o "$LIST" "$LIST_URL"
  fi
  local size free
  size=$(stat -c %s "$DB"); free=$(df --output=avail -B1 "$STACK/pihole" | tail -1)
  (( free > size * 3 )) || { echo "   Not enough free space for a backup and a compacted copy ($((size/1048576)) MB database)."; exit 1; }

  echo "   Stopping Pi-hole; it writes the last 24 h it holds in memory to the database on the way down"
  compose stop -t 30 pihole
  BACKUP=/root/pihole-FTL.db.before-adult-purge-$(date +%Y%m%d-%H%M%S)
  trap 'echo "   Something failed: starting Pi-hole again. The database as it was before: $BACKUP"; compose up -d pihole' ERR
  for f in "$DB" "$DB-wal" "$DB-shm"; do
    if [[ -f $f ]]; then cp -p "$f" "$BACKUP${f#"$DB"}"; fi
  done
  chmod 600 "$BACKUP"*

  local owner; owner=$(stat -c %u:%g "$DB")
  python3 - "$DB" "$LIST" <<"PY"
import os, re, shutil, sqlite3, sys
db, listfile = sys.argv[1], sys.argv[2]
DOMAIN = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$")

def parse(text):  # same rules as Network Watch: plain domains, "*.d", hosts lines and "||d^" all count
    out = set()
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line or line.startswith(("!", "[")):
            continue
        parts = line.split()
        d = parts[1] if len(parts) > 1 and re.match(r"^(0\.0\.0\.0|127\.0\.0\.1|::1?)$", parts[0]) else parts[0]
        d = d.lower().removeprefix("||").removeprefix("*.").split("^", 1)[0].rstrip(".")
        if "." in d and DOMAIN.match(d):
            out.add(d)
    return out

listed = parse(open(listfile, errors="replace").read())
if len(listed) < 1000:
    sys.exit(f"   The list has only {len(listed)} domains; it looks broken, so nothing was changed.")

def hit(d):
    labels = str(d).lower().rstrip(".").split(".")
    return any(".".join(labels[i:]) in listed for i in range(len(labels) - 1))

con = sqlite3.connect(db, timeout=60)
# the layout this was written for: Pi-hole v6 (domains and CNAME targets stored once, lookups point at them by id)
cols = lambda t: {r[1] for r in con.execute(f"PRAGMA table_info({t})")}
if not ({"id", "domain", "additional_info"} <= cols("query_storage") and {"id", "domain"} <= cols("domain_by_id")
        and {"id", "type", "content"} <= cols("addinfo_by_id")):
    sys.exit("   Pi-hole's database isn't laid out as expected (not Pi-hole v6?); nothing was changed.")
con.execute("PRAGMA secure_delete = ON")  # deleted rows are overwritten with zeros, not just unlinked
domain_ids = [i for i, d in con.execute("SELECT id, domain FROM domain_by_id") if hit(d)]
cname_ids = [i for i, c in con.execute("SELECT id, content FROM addinfo_by_id WHERE type = 1") if hit(c)]  # 1 = CNAME target
text_domains = [d for (d,) in con.execute("SELECT DISTINCT domain FROM query_storage WHERE typeof(domain) = 'text'") if hit(d)]
con.executescript("CREATE TEMP TABLE pd (id INTEGER PRIMARY KEY); CREATE TEMP TABLE pc (id INTEGER PRIMARY KEY); CREATE TEMP TABLE pt (d TEXT PRIMARY KEY);")
con.executemany("INSERT INTO pd VALUES (?)", [(i,) for i in domain_ids])
con.executemany("INSERT INTO pc VALUES (?)", [(i,) for i in cname_ids])
con.executemany("INSERT INTO pt VALUES (?)", [(d,) for d in text_domains])
with con:
    lookups = con.execute("""DELETE FROM query_storage
        WHERE (typeof(domain) = 'integer' AND domain IN (SELECT id FROM pd))
           OR (typeof(domain) = 'text' AND domain IN (SELECT d FROM pt))
           OR (typeof(additional_info) = 'integer' AND additional_info IN (SELECT id FROM pc))""").rowcount
    con.execute("DELETE FROM domain_by_id WHERE id IN (SELECT id FROM pd)")
    con.execute("DELETE FROM addinfo_by_id WHERE id IN (SELECT id FROM pc)")
def n(k, word):
    return "{:,} {}{}".format(k, word, "" if k == 1 else "s")
redirects = " (and {})".format(n(len(cname_ids), "redirect target")) if cname_ids else ""
print("   Removed {} of {}{}; the list has {:,} domains.".format(
    n(lookups, "lookup"), n(len(domain_ids) + len(text_domains), "adult site"), redirects, len(listed)))
con.execute("VACUUM")                       # rebuild the file so nothing of the deleted rows is left in it
con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
con.close()
PY
  chown "$owner" "$DB"*   # Pi-hole runs as its own user: keep the files it writes its own

  echo "   Starting a fresh Pi-hole container (its raw text logs, a few days of every lookup, go with the old one)"
  compose up -d --force-recreate pihole
  trap - ERR
  wait_for_pihole
  echo "   Backup of the database as it was: $BACKUP (it still holds the removed lookups)."
  # root expands the *: your own shell can't look inside /root, so "sudo rm /root/...*" finds nothing
  echo "   Once you're happy, delete it:  sudo sh -c 'rm -v $BACKUP*'"
}

block() {
  echo "== Block adult sites =="
  docker exec pihole pihole-FTL sqlite3 /etc/pihole/gravity.db \
    "INSERT OR IGNORE INTO adlist (address, enabled, comment, type) VALUES ('$BLOCK_URL', 1, 'Adult sites (OISD NSFW), added by adult-content.sh', 0);
     UPDATE adlist SET enabled = 1 WHERE address = '$BLOCK_URL' AND type = 0;"
  echo "   Updating Pi-hole's lists (downloads them all; a minute or two on the Pi)"
  local out; out=$(mktemp)
  if ! docker exec pihole pihole -g >"$out" 2>&1; then
    echo "   Pi-hole's list update failed. Its last lines:"; tail -15 "$out" | sed 's/^/     /'; rm -f "$out"; exit 1
  fi
  rm -f "$out"
  local row number abp status
  row=$(docker exec pihole pihole-FTL sqlite3 /etc/pihole/gravity.db \
    "SELECT number, abp_entries, status FROM adlist WHERE address = '$BLOCK_URL' AND type = 0;")
  IFS='|' read -r number abp status <<<"$row"
  case "$status" in
    1|2) ;;
    3) echo "   The list couldn't be downloaded this time; Pi-hole is using its saved copy." ;;
    *) echo "   The list couldn't be downloaded and there's no saved copy. Check horae's internet and DNS, then re-run: sudo bash $0 block"; exit 1 ;;
  esac
  if (( ${abp:-0} < 1000 )); then
    echo "   Pi-hole loaded ${number:-0} entries but only ${abp:-0} as 'site and all its subdomains' rules; check the list in Pi-hole's Lists page."
    exit 1
  fi
  echo "   Blocking $(python3 -c 'import sys; print("{:,}".format(int(sys.argv[1])))' "$abp") adult sites and all their subdomains, for every device."
  echo "   Something legitimate blocked? Pi-hole admin > Domains > Allow."
}

case "$STEP" in
  purge) purge ;;
  block) block ;;
  all) purge; block ;;
esac

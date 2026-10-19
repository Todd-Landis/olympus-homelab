#!/usr/bin/env bash
# Run Olympus (http://127.0.0.1:9290) and Network Watch (http://127.0.0.1:9295) locally against fake machines.
#   dev/stack.sh start | stop | status
# State (fake database, names, logs, pids, screenshots) lives in dev/.run/ (git-ignored).
set -euo pipefail
cd "$(dirname "$0")/.."
RUN=dev/.run
PY=${PYTHON:-python3}

stop() {
  for f in "$RUN"/*.pid; do [ -f "$f" ] && kill "$(cat "$f")" 2>/dev/null || true; rm -f "$f"; done
}
case "${1:-}" in
  stop) stop; echo "stopped"; exit 0 ;;
  status) for f in "$RUN"/*.pid; do [ -f "$f" ] && { kill -0 "$(cat "$f")" 2>/dev/null && echo "$(basename "$f" .pid): running" || echo "$(basename "$f" .pid): dead"; }; done; exit 0 ;;
  start) ;;
  *) echo "usage: $0 start|stop|status"; exit 1 ;;
esac
stop
mkdir -p "$RUN"
# The apps serve the shared suite from their own static folders (deploy.sh copies it there on the servers).
cp suite/suite.css suite/suite.js olympus/hub/static/
cp suite/vendor/echarts-6.1.0.min.js olympus/hub/static/
cp suite/suite.css suite/suite.js pihole-watch/app/static/
$PY dev/fakes.py "$RUN" > "$RUN/fakes.log" 2>&1 & echo $! > "$RUN/fakes.pid"
for _ in $(seq 40); do grep -q "fakes up" "$RUN/fakes.log" 2>/dev/null && break; sleep 0.25; done
echo dev > "$RUN/pihole.secret"   # the fake Pi-hole takes any password
(cd pihole-watch/app && DB_PATH="../../$RUN/watch.db" NAMES_FILE="../../$RUN/names.json" PORT=9295 \
  PIHOLE_URL=http://127.0.0.1:9303 PIHOLE_SECRET_FILE="../../$RUN/pihole.secret" SYNC_SECONDS=5 \
  CATEGORY_LISTS="{\"adult\": \"../../$RUN/adult-list.txt\"}" \
  exec $PY app.py) > "$RUN/netwatch.log" 2>&1 & echo $! > "$RUN/netwatch.pid"
(cd olympus/hub && CONFIG=../../dev/config.json BIND=127.0.0.1 PORT=9290 exec $PY app.py) > "$RUN/olympus.log" 2>&1 & echo $! > "$RUN/olympus.pid"
for _ in $(seq 40); do curl -sf http://127.0.0.1:9290/api/state >/dev/null 2>&1 && curl -sf http://127.0.0.1:9295/api/health >/dev/null 2>&1 && break; sleep 0.25; done
sleep 2  # first service checks and agent polls
echo "Olympus       http://127.0.0.1:9290/"
echo "Network Watch http://127.0.0.1:9295/"
echo "($(cat "$RUN/fakes.log"))"

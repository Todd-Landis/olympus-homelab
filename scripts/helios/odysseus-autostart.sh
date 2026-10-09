#!/usr/bin/env bash
# Start Odysseus after boot once its Windows share is reachable.
# Odysseus bind-mounts /mnt/win-ai-workspace (CIFS from Todd's laptop). If the laptop isn't reachable when Docker
# starts containers at boot, the mount fails ("no such device") and Docker doesn't retry, so Odysseus stays down.
# Installed on helios as ~/bin/odysseus-autostart.sh and run from synestri's crontab:  @reboot ~/bin/odysseus-autostart.sh
# Checks every 30 s for up to 30 min. Log: journalctl -t odysseus-autostart
CONTAINER=odysseus-odysseus-1
SHARE=/mnt/win-ai-workspace

sleep 60  # let Docker and Tailscale come up first
for _ in $(seq 1 60); do
  [[ $(docker inspect -f '{{.State.Status}}' "$CONTAINER" 2>/dev/null) == running ]] && exit 0
  if timeout 10 ls "$SHARE" >/dev/null 2>&1; then
    if docker start "$CONTAINER" >/dev/null 2>&1; then
      logger -t odysseus-autostart "started $CONTAINER after boot"
      exit 0
    fi
  fi
  sleep 30
done
logger -t odysseus-autostart "gave up after 30 min: $SHARE not reachable (is the laptop on?); start it from Olympus"

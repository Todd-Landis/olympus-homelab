#!/usr/bin/env bash
# Switch Pi-hole to host networking so it sees each client IP. Run: sudo bash ~/pihole-hostnet.sh
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo "Run with sudo: sudo bash $0"; exit 1; }
cd /opt/pihub
cp docker-compose.yml docker-compose.yml.before-hostnet
install -m 644 -o synestri -g synestri /home/synestri/docker-compose.new.yml docker-compose.yml
sed -i "s#url: http://pihole:80#url: http://host.docker.internal:8080#" homepage/services.yaml
docker compose config --quiet
docker compose up -d --remove-orphans
echo "Done. Old config saved as /opt/pihub/docker-compose.yml.before-hostnet"

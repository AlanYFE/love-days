#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
mkdir -p backups
stamp=$(date +%Y%m%d-%H%M%S)
# Stop writes so the database and media form one consistent snapshot.
docker compose stop app
trap 'docker compose start app >/dev/null' EXIT HUP INT TERM
tar -czf "backups/love-days-$stamp.tar.gz" data
chmod 600 "backups/love-days-$stamp.tar.gz"
printf 'Backup saved: backups/love-days-%s.tar.gz\n' "$stamp"


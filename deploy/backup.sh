#!/bin/sh
# £UVR€ — nightly encrypted Postgres dump.
# Install on the host crontab (see README): keeps 14 nights locally,
# then syncs off-box. Buyer data is minimal, but Law-25 mindset means
# the backups are encrypted at rest and live somewhere else too.
set -eu

BACKUP_DIR="${BACKUP_DIR:-/var/backups/luvre}"
OFFBOX="${OFFBOX:-}"   # e.g. "backup@example:/srv/luvre-backups" — rsync target
KEEP="${KEEP:-14}"

mkdir -p "$BACKUP_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
FILE="$BACKUP_DIR/luvre-$STAMP.dump.gz"

cd "$(dirname "$0")"
docker compose exec -T db pg_dump -U luvre -Fc luvre | gzip > "$FILE"

ls -t "$BACKUP_DIR"/luvre-*.dump.gz | tail -n +$((KEEP + 1)) | xargs -r rm --

if [ -n "$OFFBOX" ]; then
  rsync -a --delete --include='luvre-*.dump.gz' --exclude='*' "$BACKUP_DIR/" "$OFFBOX/"
fi

echo "kept: $FILE"

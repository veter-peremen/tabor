#!/usr/bin/env bash
# Резервная копия локальной БД бота (events.db).
# Использует безопасный SQLite .backup (не ломает работающую БД).
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/tabor}"
DB_FILE="${DB_FILE:-$APP_DIR/events.db}"
BACKUP_DIR="${BACKUP_DIR:-$APP_DIR/backups}"
KEEP="${KEEP:-30}"   # сколько последних копий хранить

mkdir -p "$BACKUP_DIR"
STAMP="$(date +%Y%m%d-%H%M%S)"
OUT="$BACKUP_DIR/events-$STAMP.db"

if [ ! -f "$DB_FILE" ]; then
    echo "БД не найдена: $DB_FILE" >&2
    exit 1
fi

sqlite3 "$DB_FILE" ".backup '$OUT'"
gzip -f "$OUT"
echo "Бэкап создан: $OUT.gz"

# Чистим старые копии, оставляя последние $KEEP
ls -1t "$BACKUP_DIR"/events-*.db.gz 2>/dev/null | tail -n +"$((KEEP + 1))" | xargs -r rm -f

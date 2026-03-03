#!/bin/sh
set -e

TS=$(date -u +%Y%m%d_%H%M%S)
FILE="/backups/pg_backup_${TS}.sql.gz"
HASHFILE="${FILE}.sha256"

pg_dump -h db -U ai -d ai_data | gzip > "${FILE}"
sha256sum "${FILE}" > "${HASHFILE}"

python3 /backup/notify_email.py "Backup OK" "Created ${FILE} with hash ${HASHFILE}"

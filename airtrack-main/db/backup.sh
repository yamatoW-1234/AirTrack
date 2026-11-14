#!/bin/bash
# Backup the airtrack database. Usage: bash db/backup.sh
mkdir -p backups
mysqldump -u root -p --single-transaction --routines airtrack > backups/airtrack_$(date +%Y%m%d_%H%M%S).sql
echo "Backup saved in backups/"
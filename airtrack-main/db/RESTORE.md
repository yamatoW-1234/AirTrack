# Restore the airtrack database

1. Take a backup: bash db/backup.sh
2. Simulate disaster: in MySQL run  DROP DATABASE airtrack;
3. Recreate it empty: CREATE DATABASE airtrack;
4. Restore (use your backup file name):
   mysql -u root -p airtrack < backups/airtrack_YYYYMMDD_HHMMSS.sql
5. Verify: SELECT COUNT(*) FROM reading;  and  SELECT COUNT(*) FROM aqi_record;
   The counts must equal the ones before the drop.
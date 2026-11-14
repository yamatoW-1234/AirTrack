# Ingestion layer: data loading and ACID evidence

**Source.** Readings come from the CPCB real-time air quality resource on the Open Government Data (OGD) platform. The API returns only the latest hourly value for each station and pollutant and keeps no history. Any history in our database therefore exists only because the hourly job kept running, and an hour that was missed cannot be fetched later.

**Pipeline.** One run fetches the records for the five chosen Delhi stations, looks up station ids by name, cleans the records, and loads them as one batch. Cleaning skips and counts, by reason, records with an unknown station or pollutant, a pollutant not assigned to the station, a missing (`NA`), non-numeric or negative value, an unreadable date, or a duplicate within the batch. The load inserts the readings, calculates sub-indexes, and calculates the daily AQI for every date in the batch, all inside **one transaction**: it ends in `COMMIT`, and any error ends in `ROLLBACK`.

**Atomicity.** A batch of 32 new made-up readings was loaded with a failure forced after the AQI step, just before the commit. The error was logged and the counts were identical before and after (2895 readings and 2 AQI rows), so the inserted rows, sub-indexes and AQI row were all undone. The same batch then loaded without the failure and the counts rose to 2927 and 3.

**Consistency.** Reading rows are guarded twice. The database rejected a reading for a station and pollutant pair missing from `station_pollutant` (composite foreign key, MySQL error 1452) and a negative value (CHECK constraint, error 3819); the row count did not change. The cleaning step catches the same kinds of rows earlier and logs the reason. A `UNIQUE (station, pollutant, datetime)` key makes loading idempotent: duplicates are absorbed with `ON DUPLICATE KEY UPDATE`, not `INSERT IGNORE`, so foreign-key violations still raise errors.

**Isolation.** While a writer transaction held 24 uncommitted rows open (count 2951 inside it), a second session at the default `REPEATABLE-READ` level kept answering and still saw 2927. The rows disappeared on rollback.

**Durability.** After the committed batch, the MySQL80 service was restarted (server uptime fell from 351190 s to 9 s). The counts (2927 readings, 3 AQI rows) and the committed AQI row were unchanged.

**Idempotence and run log.** Running the live job twice in a row inserted 19 readings and then none (19 duplicates); loading the saved samples twice also inserted nothing. Every run logs its start, record counts, skip reasons, load counts, exit code and duration to a log file that rotates daily. A run that fetches no records at all is logged as a WARNING.

**Fallback.** If the API is unavailable, the same cleaning and loading code can read saved API responses or a CSV file. Such data is labelled as sample or imported data, not live.

**Limits (honest note).** (1) The job has not yet been verified running unattended for many hours, so the 16-hour rule for a live daily AQI has not been demonstrated on live data. (2) On 1 Nov 2026 the API answered HTTP 200 with zero records for all of Delhi, and the resource's last update stamp was 31 Oct 2026 18:02 UTC; so the feed can go empty, and history will have gaps. (3) The CSV importer was tested only on made-up data, because no real CPCB download was available. (4) The isolation demo used a plain insert transaction, not the loader itself. (5) The local database still holds made-up test data (sample stations, January 2026 test readings); what the final demo database shows (live data only, or clearly labelled mock data) is still to be agreed with the team.

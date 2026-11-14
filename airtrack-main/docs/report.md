# Database layer

**Integrity.** Seven InnoDB tables with primary keys, foreign keys, UNIQUE,
NOT NULL, ENUM and CHECK constraints. A composite foreign key from
reading(station_id, pollutant_id) to station_pollutant means a reading is only
accepted for a pollutant assigned to that station. Negative concentrations are
rejected by CHECK, and duplicate readings by a UNIQUE key.

**Normalization.** Each table holds facts about one entity, with every
non-key column depending only on its key (3NF). The many-to-many link between
stations and pollutants is resolved by station_pollutant. reading.sub_index is
derivable from concentration and the breakpoint table, so it is a deliberate
denormalisation: stored once for fast reads by the API and charts.

**Calculation inside the database.** calc_subindex.sql converts readings to
sub-indices with the breakpoint formula. calc_daily_aqi.sql averages each
pollutant per day (HAVING COUNT(*) >= 16), takes the highest sub-index as the
AQI, finds the category, and saves it with INSERT ... ON DUPLICATE KEY UPDATE,
so re-runs are safe.

**Views and indexing.** v_latest_reading, v_daily_aqi_full and
v_station_availability simplify API queries. An index on
reading(station_id, reading_datetime) speeds station and date lookups.

**Security.** airtrack_reader has SELECT only; airtrack_writer can INSERT and
UPDATE on four tables. Both are denied DELETE and changes to reference tables.

**Durability.** mysqldump --single-transaction backup; the database was
dropped and restored, and row counts matched before and after.

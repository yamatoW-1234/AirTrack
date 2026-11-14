# AirTrack: Ingestion (Member 2) README

My personal explainer for the `ingestion/` part of AirTrack. Updated at the end of every phase. *Last updated: Phase G (pull request prep), 1 Nov 2026.*

## 1. What my part does
```
OGD API (data.gov.in)  ->  ingestion (Python)  ->  MySQL  ->  Flask API  ->  dashboard
```
Every hour my code fetches the latest CPCB air-quality readings for Anand Vihar and a few nearby Delhi stations (PM2.5, PM10, NO2, SO2), saves each batch **all or nothing**, then triggers the SQL that computes sub-indices and the daily AQI. It must never crash on bad data. The API gives only the latest values, so history exists only because the hourly job keeps running.

## 2. Status
| Phase | Topic | Status |
|---|---|---|
| A | Setup and DB verification | Done |
| B | Explore API, choose region | Done |
| C | API client and transform | Done |
| D | Transactional loader | Done |
| E | CLI, scheduler, CSV fallback, logging | Done on sample and offline tests (1 Nov 2026) |
| F | Failure test, ACID proof, report text | Done (1 Nov 2026). **Unattended hourly run NOT verified** |
| G | Integration, PR, viva prep | In progress |

## 3. Folder layout
```
ingestion/
  config/region.json     the 5 chosen stations (Phase B, pushed)
  samples/               raw API JSON examples (Phases B and C); csv_test_wide.csv is MADE-UP test data
  logs/                  run logs, ignored by git (Phase E)
  explore.py             throwaway: fetch Anand Vihar (Phase B)
  explore_delhi.py       throwaway: fetch all Delhi, verify facts (Phase B)
  ping_test.py           throwaway: diagnose the 502 error (Phase B)
  ogd_client.py          fetches data from the API (Phase C)
  transform.py           cleans and converts records (Phase C)
  test_transform.py      offline test of transform.py (Phase C)
  test_client_failures.py  tests no key / bad key / API down (Phase C)
  load.py                transactional insert + calculations (Phase D)
  test_load.py           tests load.py on the real local DB (Phase D)
  ingest.py              command-line entry point + scheduler (Phase E)
  csv_import.py          fallback if the API is down (Phase E)
  test_ingest.py         offline tests of ingest.py and csv_import.py (Phase E/F)
  demo_atomicity.py      ACID demo: forced failure vs success (Phase F, run once only)
  demo_consistency.py    ACID demo: FK 1452 and CHECK 3819 (Phase F)
  demo_isolation.py      ACID demo: uncommitted rows invisible to others (Phase F)
  stations_real.sql      real stations for Member 1's table (Phase B, pushed)
  db_check.py            Phase A: connection test
  perm_check.py          Phase A: permission test
  requirements.txt       Python packages
  README_ingestion.md    this file
```
Also in the repo: `.gitignore` in `ingestion/` (ignores `logs/`) and `docs/REPORT_ingestion_acid.md` (report section). Kept local only: `diag_api.py`, `cleanup_sample_data.sql` (it empties all readings, never share it).

## 4. How to run (Git Bash)
```
cd <your repo folder>
source ingestion/venv/Scripts/activate
python ingestion/db_check.py
python ingestion/ogd_client.py --region
python ingestion/test_transform.py
python ingestion/test_client_failures.py
python ingestion/load.py
python ingestion/test_load.py
python ingestion/test_ingest.py
python ingestion/ingest.py --sample
python ingestion/ingest.py --once
```
`.env` (repo root, never committed) holds the database login and the API key.

## 5. Phase A: Setup and database verification (done)

### What we did
1. Merged `origin/main` into my branch `m2-ingest` to get Member 1's `db/` folder.
2. Ran `schema.sql`, `seed_reference.sql`, `sample_data.sql`, `views.sql`, `roles.sql` in Workbench, in that order.
3. Verified: 7 tables + 3 views, 2678 sample readings, station 1 = Anand Vihar.
4. Changed the writer password locally (`ALTER USER`), so the real password is not in the repo.
5. Built a Python virtual environment and installed the 4 libraries.
6. Created `.env` and made sure git ignores `.env`, `venv/` and `ingestion/logs/`.
7. Wrote `db_check.py` and `perm_check.py` to prove the writer account works and is restricted.

### Why each piece exists
- **Virtual environment (`venv`)**: a private copy of Python so this project's libraries do not mix with others. Rebuilt by teammates from `requirements.txt`.
- **`.env` file**: keeps passwords and the API key out of the code and out of git.
- **`.gitignore`**: tells git which files never to commit.
- **Writer account (`airtrack_writer`)**: a limited MySQL user. It can read everything and INSERT/UPDATE on `reading`, `aqi_record`, `monitoring_station`, `station_pollutant`. It cannot DELETE or change the schema.

### What the scripts do
- **`db_check.py`**: loads `.env`, connects to MySQL as the writer, runs `SELECT COUNT(*) FROM reading`, prints it (2678). `load_dotenv` reads the file, `os.getenv` fetches each value, `cursor.execute` sends SQL, `fetchone()[0]` takes the first value of the result.
- **`perm_check.py`**: runs a SELECT (works), then a `DELETE FROM reading` inside `try/except`. MySQL refuses with error 1142, the `except` catches it and prints it. `rollback()` is a safety net in case a delete ever slipped through.

### Problems I hit and how they were solved
- **"no db named airtrack"**: `schema.sql` had to run first because it creates the database.
- **Two venvs / stray file**: a mistyped command made a `venv` in the wrong folder; deleted it and rebuilt inside `ingestion/`.
- **Edited `.env.example` by mistake**: restored with `git restore`; the real values go in `.env`.
- **`.gitignore` line glued together**: `echo` appended text to a last line that had no newline, giving `backups/ingestion/logs/`. Fixed with `sed`, confirmed with `git check-ignore`.
- **Access denied for user '<my name>'**: I used my own name as `DB_WRITER_USER`. It must be the MySQL account `airtrack_writer`.

### Viva questions (short answers)
- *Why a separate writer account?* Least privilege: the ingestion code can add and update data but cannot delete rows or alter tables, so a bug cannot wipe the data.
- *Why not commit `.env`?* It contains passwords; anything committed stays in git history.
- *Why does `schema.sql` start with DROP DATABASE?* It makes the build repeatable, but it deletes everything, so it must never be re-run after real data exists.
- *Why `try/except` around the DELETE?* A refused statement raises an exception; catching it lets the script report it instead of crashing.

## 6. Phase B: Explore the API and choose the region (done)

### What we did
1. Got a personal API key from data.gov.in (account page, **My Info** tab) and put it in `.env` as `OGD_API_KEY`.
2. Wrote `explore.py` to fetch Anand Vihar and save the raw JSON. It failed with a timeout, then with **HTTP 502**.
3. Diagnosed the 502 step by step (see "Problems" below) and found the cause: the gateway rejects Python's default User-Agent.
4. Fixed it by sending curl-like headers, then re-ran `explore.py` successfully.
5. Wrote `explore_delhi.py` to fetch every Delhi record, list the stations, and check the exact field formats.
6. Chose 5 stations near Anand Vihar and checked that all 5 names exist exactly in the live data.
7. Wrote `config/region.json` and `stations_real.sql`, ran the SQL in Workbench, then pushed only those two files and messaged the team.

### What I learned about the real data (verified, 31 Oct 2026)
| Question | Answer |
|---|---|
| Pollutant names | `PM2.5`, `PM10`, `NO2`, `SO2` exactly (also `CO`, `NH3`, `OZONE`, which we ignore) |
| Date format | `DD-MM-YYYY HH:MM:SS`, e.g. `31-10-2026 17:00:00` |
| Missing value | the text `NA` |
| Unit field | none |
| State | exactly `Delhi` |
| Value fields | `min_value`, `max_value`, `avg_value`, all **text**, not numbers |
| Size | Delhi = 59 stations, 413 records, one page of 500 |

I use `avg_value` as the concentration. (The shared contract said `pollutant_avg`; the live records use the short name. The team was told.)

### The 5 stations in the region
| DB id | Station | From |
|---|---|---|
| 1 | Anand Vihar, Delhi - DPCC | `seed_reference.sql` |
| 5 | Vivek Vihar, Delhi - DPCC | `stations_real.sql` |
| 6 | IHBAS, Dilshad Garden, Delhi - CPCB | `stations_real.sql` |
| 7 | Patparganj, Delhi - DPCC | `stations_real.sql` |
| 8 | ITO, Delhi - CPCB | `stations_real.sql` |

Ids 2-4 are Member 1's fake Sample Stations B, C, D. Because ids can have gaps, my loader will look up `station_id` by station **name**, never by number.

### What each new file does
- **`config/region.json`**: the list of stations the Python code will fetch (name, location, coordinates, which of the 4 pollutants).
- **`stations_real.sql`**: inserts the 4 new stations into `monitoring_station`, then links each to the 4 pollutants in `station_pollutant` using **sub-selects on names**, not hard-coded ids. Run it **once**: `station_name` is UNIQUE, so a second run fails with a duplicate-key error (a safe failure).
- **`explore.py`**: one request for Anand Vihar. Reads the key from `.env`, sends the request (with 3 retries), checks the status code, prints the response structure and 3 records, saves the JSON.
- **`explore_delhi.py`**: loops over pages (using `offset`) until all Delhi records are fetched, groups readings by station, prints the facts above, and marks each `region.json` station FOUND or MISSING. It refuses to save a sample if the API key appears in the text.
- **`ping_test.py`**: sends the same tiny request twice, once with Python's default headers and once with curl-like headers, to prove which one the gateway rejects.

### Problems I hit and how they were solved
- **Could not find the API key on the website**: the dropdown only showed my email and Logout. The key is on the account page, **My Info** tab.
- **`ReadTimeout`**: the server was slow. Fixed with `timeout=(10, 120)` and a retry loop.
- **HTTP 502 with an empty reply**: even `limit=1` failed. A request with no key returned 400 (so the gateway was alive), and `curl` with my key returned 200 (so key and network were fine). Python alone failed, so the cause was the default `python-requests` User-Agent. Sending `User-Agent: curl/8.0` fixed it.
- **Wrong catalog entry**: "Sameer (National Air Quality Index)" has no API. The right one is "Real time Air Quality Index".
- **The zip download was stale**: it is an XML file from November 2023 with a different structure. I used it only to shortlist stations, then confirmed every name against the live API before pushing.
- **My "5 stations, ids 1 to 5" expectation was wrong**: Member 1's sample data already had stations 2-4, so the new ones got ids 5-8.
- **Possible key leak**: some `requests` error messages include the full URL with the key. So my scripts print only the error type (`type(e).__name__`), and I never paste a full traceback.

### Viva questions (short answers)
- *Why did Python get a 502 while curl worked?* The API gateway rejected the default `python-requests` User-Agent header. Sending a normal-looking header fixed it. A 502 can come from how a client identifies itself, not only from a server fault.
- *Why `timeout` and retries?* Government servers are sometimes slow. A timeout stops the script hanging forever, and retries cope with short failures.
- *Why read the key from `.env`?* So it never appears in code, samples, logs or git.
- *Why sub-selects on names in `stations_real.sql`?* Ids are assigned by MySQL and can differ between machines; names are stable.
- *Why is the loader going to look up stations by name?* Ids 2-4 are sample stations, so the real ones have gaps in their ids. Names are the only stable link to the API data.
- *Why verify field formats on real data?* My notes said `pollutant_avg`, but the real field is `avg_value`, and values are text. Guessing would have broken the transform.
- *Why are `region.json` names copied exactly?* The API filter and later matching compare text exactly. One extra space (some real stations have one) means no match.
- *Why push only two files early?* Teammates depend on those two; the rest is still work in progress.

## 7. Phase C: API client and transform (done)

### What we did
1. Wrote `ogd_client.py`: a clean, reusable version of the request code from `explore.py`.
2. Added `load_region()` and `fetch_region()` so the client fetches all 5 stations from `region.json` (35 records: 5 stations x 7 pollutants).
3. Saved a third sample, `region_20261031_1825.json`, which contains a real `PM10 NA`.
4. Wrote `transform.py`: turns raw records into clean rows and counts what it skipped and why.
5. Wrote `test_transform.py` (runs offline on the saved samples plus hand-made bad records). All pass.
6. Wrote `test_client_failures.py`: no key, bad key (API answered HTTP 403), API down. All pass. I also checked with Wi-Fi off: it retries 3 times and then fails cleanly.

### Why each piece exists
- **Client and transform are separate files**: the client talks to the internet, the transform only cleans data. Because transform needs no network or database, I can test it any time with saved files.
- **The station map is passed into `transform`**: the loader (Phase D) will build it from the database. Passing it in keeps the transform testable offline.
- **Custom exceptions**: lets the caller tell "no key", "bad key" and "API down" apart, and lets me write messages that never contain the key.
- **Skip report**: the hourly job must not crash on bad data, but I must still know what was dropped. Each dropped record is counted under a reason.

### What each new file does
- **`ogd_client.py`**
  - `get_api_key()`: reads `OGD_API_KEY`; raises `MissingApiKeyError` if empty.
  - `_get_page(params)`: one request with the curl-like headers, `timeout=(10, 120)` and up to 3 tries. It retries on timeouts, connection errors and 500/502/503/504, waiting 5 s then 10 s (exponential backoff). A 4xx raises `ApiRejectedError` straight away, because the same key would fail again. After 3 failed tries it raises `ApiUnavailableError`. Only the exception type is stored, never the message.
  - `fetch_station(name)`: asks with `filters[station]` and keeps increasing `offset` until all `total` records are read; returns the list of raw dicts.
  - `fetch_region()`: calls `fetch_station` for each station in `region.json`. If one fails, nothing is returned (all or nothing).
  - `save_raw_response(records, name)`: saves `samples/<name>_<timestamp>.json`; refuses if the key is in the text.
- **`transform.py`**
  - `parse_value(text)`: `NA`/blank -> `missing_value`; not a number (including `nan`, `inf`) -> `non_numeric_value`; below 0 -> `negative_value`; otherwise a float rounded to 2 decimals.
  - `parse_date(text)`: `DD-MM-YYYY HH:MM:SS` -> `YYYY-MM-DDTHH:MM:SS`, or `None`.
  - `transform(records, station_ids, ...)`: checks each record in order (station, pollutant, assigned to station, value, date, duplicate), skips with a reason at the first failure, otherwise builds `{station_id, pollutant_id, reading_datetime, concentration_value}`. Returns `(rows, report)`.
- **`test_transform.py`**: checks the sample files (every record counted once, rows have the right keys and types), 9 hand-made bad records (each lands in the right reason), rounding, duplicates and the "not assigned" check.
- **`test_client_failures.py`**: removes the key for one run (no key), sends a fake key (rejected), and points the client at a dead address (retries, then "unavailable").

### What the real numbers looked like
- Region sample: 35 records = 19 kept + 1 `missing_value` + 15 `unknown_pollutant` (CO, NH3, OZONE at 5 stations). 19 + 1 = 20 = 5 stations x 4 pollutants.
- Whole-Delhi sample: 413 = 19 kept + 1 missing + 15 unknown pollutant + 378 unknown station (the other 54 stations).
- A fake key gets HTTP 403.

### Decisions
- **Duplicates:** the same station + pollutant + time twice in a batch: keep the first, count the rest as `duplicate_in_batch`. The same pollutant at a different time is a different reading and is kept. (The phase file said "latest `last_update` wins", but the feed has one timestamp for everything.)
- Station names are compared **exactly**: a trailing space means "unknown station".
- A 4xx is not retried; 5xx and network errors are.

### Problems I hit and how they were solved
- **Not sure of the `region.json` field names**: I pasted the file before the code that uses it was written, so `fetch_region` uses the real names (`station_name`).
- **Duplicate sample**: `delhi_..._1804.json` and `..._1805.json` are the same feed saved twice; harmless.
- **"Does it loop forever with no internet?"**: no, it tries 3 times (about 15 s of waiting) and then stops with a clear error. The hourly scheduler (Phase E) will try again at the next hour.

### Viva questions (short answers)
- *Why separate the client and the transform?* Different jobs: one talks to the network, one cleans data. The transform can be tested offline and reused for the CSV fallback.
- *Why is the station map passed into `transform`?* So the function has no database dependency and the tests run offline; the loader builds the map from the DB.
- *What is exponential backoff?* Waiting longer after each failed try (5 s, then 10 s) so a struggling server is not hammered and short outages can pass.
- *Why not retry a 403?* The same key would fail again; retrying only wastes time. Only network errors and 5xx may be temporary.
- *Why is the value a string and how do you convert it?* The API sends text. I strip it, reject `NA`/blank, convert with `float()` inside `try/except ValueError`, reject `nan`/`inf` and negatives, and round to 2 decimals to match `DECIMAL(8,2)`.
- *Why are CO, NH3 and OZONE "skipped"?* The project covers only four pollutants, so the other three are dropped on purpose and counted as `unknown_pollutant`.
- *Which duplicate wins?* The first in the batch; a duplicate is the same station + pollutant + time. Different times are separate readings.
- *Why must errors never print the exception message?* A `requests` error can contain the URL with the API key. Printing only the type keeps the key out of the logs.
- *Why is `fetch_region` all or nothing?* A half-fetched batch would give an incomplete picture; failing as a whole matches the all-or-nothing database batch.
- *Why save samples and test offline?* The API cannot be replayed (latest values only), and saved real samples make tests repeatable without internet.

## 8. Phase D: Transactional loader (done)

### What we did
1. Read `schema.sql` and confirmed the `reading` table: columns `reading_id, station_id, pollutant_id, reading_datetime, concentration_value, sub_index`, and `UNIQUE (station_id, pollutant_id, reading_datetime)`. So the duplicate rule from Phase C matches the database.
2. Checked Member 1's two calculation files: no `;` inside strings, so splitting on `;` is safe. `calc_subindex.sql` is 3 statements (`SET SQL_SAFE_UPDATES`, two `UPDATE`s). `calc_daily_aqi.sql` is exactly one statement (`INSERT ... WITH ... SELECT`).
3. Wrote `load.py`: saves one batch of clean rows **all or nothing**, then runs both calculations.
4. Wrote `test_load.py`: five groups of checks against the real local database. **All pass.**

### Why each piece exists
- **One transaction per batch**: if anything fails halfway (a bad row, a crash, the power), the database goes back to exactly how it was. No half-saved hour.
- **`ON DUPLICATE KEY UPDATE reading_id = reading_id` instead of `INSERT IGNORE`**: both skip a duplicate reading. But `INSERT IGNORE` also turns a foreign-key error into a quiet warning, which would hide the "pollutant not assigned to this station" error that I must be able to demonstrate.
- **Counting rows before and after**: `cursor.rowcount` is unreliable with `ON DUPLICATE KEY`, so "new rows" is `COUNT(*)` after minus `COUNT(*)` before, inside the same transaction.
- **`@d` set per date**: `calc_daily_aqi.sql` has a fixed date inside it. I remove that line and run `SET @d = <date>` myself before each run, on the same connection (a `@variable` only lives on its own connection).
- **Daily AQI once per date in the batch**: a batch taken just after midnight can contain the last hour of yesterday, so I run it for every distinct date, not only today.
- **Failure hook**: `fail_after` lets a test break the batch on purpose, so I can prove the rollback works (Phase F).

### What each new file does
- **`load.py`**
  - `get_connection()`: connects as `airtrack_writer` using `.env`, then `autocommit = False` (nothing is saved until I call `commit()`).
  - `load_station_ids(conn)`: `{station_name: station_id}` from `monitoring_station`. `load_assigned(conn)`: `{station_id: {pollutant_ids}}` from `station_pollutant`. Both are inputs for `transform()`. They call `commit()` at the end because even a `SELECT` opens a transaction when autocommit is off, and `start_transaction()` would then complain.
  - `read_sql_statements(path, skip_prefixes)`: reads a `.sql` file, drops comment lines, the `USE` line and any line starting with a skip prefix, splits on `;` and returns the statements. For the daily file I skip `SET @D`, and the function that calls it checks that exactly one statement is left.
  - `load_batch(conn, rows, fail_after=None)`: `start_transaction()`, `executemany` insert, `calc_subindex.sql`, then for each date `SET @d` and the daily statement, then `commit()`. On any error: `rollback()` and raise `LoadError` (the original error stays in `__cause__`). Returns a dict: `submitted, inserted, duplicates, dates, aqi_new, aqi_affected`.
  - `LoadError`, `SimulatedFailure`, `FAIL_POINTS = ("insert", "subindex", "aqi")`.
  - Run `python ingestion/load.py` on its own to test the connection; it prints the 8 stations with their pollutant ids.
- **`test_load.py`**: see the results below.

### Test results (31 Oct 2026, all PASS)
| Check | Result |
|---|---|
| Load all files in `samples/` twice | 23 new rows the first time, 0 the second; reading count 2701 before and after the second pass |
| `sub_index` filled | 0 readings with NULL `sub_index` |
| 16 hours of PM2.5 (90) + PM10 (100) on 2026-01-15 | `aqi_record` created: AQI 201, dominant pollutant PM2.5, `hours_of_data` 16 |
| 15 hours on 2026-01-16 | no `aqi_record` (16-hour rule) |
| Re-load the same batch | 0 new rows |
| `fail_after` = insert, subindex, aqi | counts identical before and after (2763 readings, 1 AQI row, 0 NULL sub-index) |
| Pollutant 99 in a batch with one good row | MySQL error **1452**; the good row was not saved either |

Note: only 23 rows were new because the three Delhi/region sample files are the same feed (same stations, pollutants and timestamp), so after the first one (19 rows) the rest were duplicates. The 4 extra rows came from `anand_vihar_1.json`, an earlier hour.

### Things to remember
- The writer account cannot `DELETE`, so the test rows (January 2026) stay in my DB, plus 1 `aqi_record`. They are wiped by `cleanup_sample_data.sql` before the final long run, which empties all `reading` and `aqi_record` rows.
- `test_load.py` can be run again at any time; it adds nothing the second time.
- With the real feed, a daily AQI only appears after 16 hourly readings on one date.

### Problems I hit and how they were solved
- **Expected `rowcount` to count new rows**: it does not, reliably, with `ON DUPLICATE KEY`. Solved by comparing row counts before and after.
- **`start_transaction()` can fail after a `SELECT`**: with autocommit off, a `SELECT` already opened a transaction. Solved by ending reads with `commit()`.
- **`@d` in a separate connection would be empty**: solved by running `SET @d` and the daily statement on the same cursor and connection.

### Viva questions (short answers)
- *What does "all or nothing" mean here and how do you get it?* All steps of a batch (insert, sub-index, daily AQI) run in one transaction. `commit()` saves them together; any error calls `rollback()`, which undoes everything since `start_transaction()`.
- *Why not `INSERT IGNORE`?* It hides foreign-key errors as warnings. `ON DUPLICATE KEY UPDATE reading_id = reading_id` only skips duplicates; real errors still stop the batch.
- *How does the database know a reading is a duplicate?* `UNIQUE (station_id, pollutant_id, reading_datetime)` on `reading`. A second insert with the same three values triggers the `ON DUPLICATE KEY` branch, which changes nothing.
- *What is error 1452?* A foreign-key failure: `reading` has a composite foreign key `(station_id, pollutant_id)` into `station_pollutant`, so a pollutant that is not assigned to the station is refused.
- *Why is `rowcount` not used to count new rows?* With `ON DUPLICATE KEY` it counts rows in a confusing way, so I compare `COUNT(*)` before and after in the same transaction.
- *How do you pass a date into `calc_daily_aqi.sql`?* The file sets `@d` to a fixed date. I skip that line and run `SET @d = %s` on the same connection before the statement. A user variable belongs to one connection, so it must be the same connection.
- *Why run the daily calculation for every date in the batch?* A batch after midnight can hold yesterday's last hour; yesterday's AQI must be refreshed too.
- *Why does the daily AQI sometimes not appear?* The calculation needs at least 16 hourly readings per pollutant on one date, and at least two pollutants including a PM. Early in the day there are not enough.
- *Why is autocommit off?* With autocommit on, every statement would be saved immediately and I could not undo a half-finished batch.
- *How did you prove the rollback works?* `fail_after` raises an error after the insert, after the sub-index, or after the daily AQI (just before `commit`). The row counts before and after were identical each time.
- *Why does the writer account matter here?* It has no DELETE or DDL permission, so even a bug in `load.py` cannot drop tables or remove data.


## 9. Phase E: CLI, scheduler, CSV fallback, logging

### What we did and why
Phases C and D gave me the pieces (fetch, clean, save). Phase E joins them into one command that can run by itself every hour, and adds a CSV route for data the API cannot give me (the API only returns the latest hour, so missed hours cannot be fetched later).

### Files
| File | What it does |
|---|---|
| `ingest.py` | The main command. `run_once()` does fetch, connect, look up station ids, `transform`, `load_batch`. Never crashes; returns an exit code. |
| `csv_import.py` | Reads a CPCB-style CSV, turns each cell into an API-shaped record, then uses the same `transform` and `load_batch`. |
| `test_ingest.py` | Offline tests: sample run and CSV run are idempotent, bad CSV input exits 3, simulated API down / key rejected / bug / load failure give exit codes 1, 1, 3, 2 and write nothing. |
| `samples/csv_test_wide.csv` | MADE-UP test data (Anand Vihar, 17 Jan 2026, 24 hours). Not real. |
| `logs/ingest.log` | One log file, a new file each midnight, 30 days kept. Git ignores it. |

### How to use (Git Bash, from the repo root, venv active)
```
python ingestion/ingest.py --once        # fetch live data and load once
python ingestion/ingest.py --sample      # same, from samples/*.json
python ingestion/ingest.py schedule      # run now, then at :05 of every hour
python ingestion/csv_import.py file.csv --station "Anand Vihar, Delhi - DPCC"
```
`--station` is only needed if the CSV has no station column. The CSV can be WIDE (one column per pollutant, unpivoted by the script) or LONG (one row per reading).

### Decisions
- **One batch per run** (all 5 stations together). `fetch_region()` already fails as a whole if any station fails, so a run is all or nothing, which matches the transaction story. One batch per station would isolate failures better but needs more code.
- **Fetch first, connect second**, so the DB connection is not held open while the slow API answers.
- **Exit codes:** 0 success, 1 API problem, 2 load failed (rolled back), 3 anything else.
- **Nothing secret in logs:** API errors log the message of our own exceptions (they never hold the key or URL); unexpected errors log only the exception type name.
- **CSV reuses `transform` and `load_batch`**, so there is one set of rules for all data.

### Log format (one run)
```
RUN START source=api
stations requested: 5
rows fetched: 35
transform report: {'kept': 19, 'unknown_pollutant': 15, 'missing_value': 1}
loaded: submitted=19 inserted=19 duplicates=0 dates=['2026-10-31'] aqi_new=0 aqi_affected=0
RUN END exit_code=0 duration=8.5s
```

### Results so far
- `--once` twice: 1st run inserted 19, 2nd run inserted 0 with 19 duplicates (idempotent).
- CSV test twice: 1st inserted 94 and created 1 `aqi_record`; 2nd inserted 0 (idempotent).
- CSV without `--station`: clear error, exit code 3, nothing written.

### Not yet verified (be honest in the report)
- The scheduler and Task Scheduler setup have NOT yet run unattended for several hours. The code path (`run_once`, exit codes, logging) is tested through `test_ingest.py` and manual runs, but a real multi-hour run is still to do.
- The :05 minute of the hourly schedule is a guess; check the first real runs for `inserted=0` and move it later if the feed publishes later.
- The first real-data run was on 31 Oct 2026 at 23:11 (`--once`, 19 rows inserted).

### Running it every hour

**Option 1: leave `python ingestion/ingest.py schedule` running in a terminal.** Simplest. Stops if the terminal closes or the laptop sleeps.

**Option 2: Windows Task Scheduler** (survives closing the terminal):
1. Open Task Scheduler, then Create Task.
2. Trigger: Daily, then tick "Repeat task every 1 hour" for a duration of 1 day.
3. Action, Program/script: the FULL path to the venv Python:
   `<repo folder>\ingestion\venv\Scripts\python.exe` (the full path on your machine)
4. Add arguments: `ingest.py --once`
5. Start in: `<repo folder>\ingestion`
6. Settings: tick "Run task as soon as possible after a scheduled start is missed". Use "Run whether user is logged on or not" only if the laptop stays on.
7. Check results in the "Last Run Result" column: `0x0` is success; `0x1`, `0x2`, `0x3` match the exit codes above.

The scripts find `.env` and the `logs` folder from their own file location, so a wrong "Start in" does not break them. Do not run Task Scheduler and `schedule` mode at the same time (harmless because of idempotency, but pointless).

**Option 3: cron (Linux/Mac):**
`0 * * * * cd /path/to/ingestion && ./venv/bin/python ingest.py --once`

### Honest limitations (state these in the report)
- The API gives only the latest hour. When the laptop sleeps or the job is off, those hours are lost.
- A daily AQI needs at least 16 readings per pollutant on one date. Gaps can only be filled by CSV or sample data, which must be labelled as such.
- The meaning of a CPCB CSV "From Date" (start or end of the hour) is not verified; the script keeps the time as written.
- `csv_import.py` was tested only on the made-up test CSV, not on a real CPCB download.

### Viva questions
- **Why one batch per run?** The run is all or nothing, like one transaction; simple to explain and to roll back.
- **Why does the second `--once` insert nothing?** The `reading` table has a UNIQUE key on (station, pollutant, datetime) and the insert uses `ON DUPLICATE KEY UPDATE reading_id = reading_id`, so repeated readings are skipped.
- **Why not `INSERT IGNORE`?** It also hides foreign key errors; I want the "pollutant not assigned to station" error (1452) to show up.
- **What if the API is down at 3 pm?** The error is logged, the exit code is 1, nothing is written and the scheduler continues at the next hour. That hour is lost.
- **How does the CSV path avoid duplicating logic?** It builds API-shaped records and calls the same `transform` and `load_batch`.
- **Why log only the exception type name?** Some exception texts contain the request URL, which includes the API key.

## 10. Phase F: proving the ingestion is safe (ACID), and the empty-feed lesson

### What we did, in plain words
Phase F is not about new features. It is about **proof**: showing the loader keeps the database correct even when things go wrong. We showed the four ACID properties, plus "running it twice changes nothing", and we wrote half a page for the report.

### The four properties and how we showed them
- **Atomicity (all or nothing).** We loaded 32 test readings but forced an error just before the `COMMIT`. The readings, sub-indexes and daily AQI row had all been written inside the transaction, yet afterwards the counts were exactly what they were before. The loader then rolled everything back. We loaded the same batch without the error and the counts rose. *Script: `demo_atomicity.py`. Also `test_load.py` section 4.*
- **Consistency (the data obeys the rules).** MySQL itself refused a reading for a station/pollutant pair that does not exist in `station_pollutant` (the composite foreign key, error 1452) and a negative value (the CHECK constraint, error 3819). Our `transform` step also skips such rows before they reach MySQL and counts the reason. Two guards are better than one. *Script: `demo_consistency.py`.*
- **Isolation (transactions do not disturb each other).** One program inserted 24 rows and **did not commit**. Another connection kept reading and still saw the old row count. MySQL's default level `REPEATABLE-READ` hides uncommitted changes from other sessions. *Script: `demo_isolation.py`.*
- **Durability (committed means kept).** After a committed load we restarted the MySQL service. The server uptime dropped from 351190 seconds to 9, and all committed rows were still there.

### Idempotence
Running the same load twice adds nothing. Two things make this work: the `UNIQUE (station_id, pollutant_id, reading_datetime)` key, and `ON DUPLICATE KEY UPDATE reading_id = reading_id` in the insert. We use that instead of `INSERT IGNORE` because IGNORE would also hide foreign-key errors.

### A test that went stale (and why that matters)
`test_load.py` used 17 Jan 2026 as a date that "must stay empty" for the failure test. The CSV import in Phase E then filled that date, so the test inserted nothing and "nothing changed after rollback" proved nothing. We moved it to 18 Jan. The lesson: a rollback test only means something if the batch really inserts rows first.

### The empty feed (1 Nov 2026)
Around 01:34 the API answered HTTP 200 with **zero records**, even for the whole of Delhi (`diag_api.py`). The pipeline coped: nothing was written and nothing crashed. But it exposed a weakness: a run with zero records still looked like a healthy run. We changed `ingest.py` so an empty answer writes a `WARNING` line to the log. The exit code stays 0, because an empty feed is not our fault. `test_ingest.py` section 5 checks this.

### What each new file does
- `demo_atomicity.py`: prints counts, runs a batch that fails before commit, prints counts again, then runs the same batch for real. Uses 19 Jan 2026, so it can be run only once.
- `demo_consistency.py`: tries two bad inserts, rolls both back, then shows `transform` skip reasons.
- `demo_isolation.py`: holds a transaction open for 90 seconds so a second window can show it cannot see the uncommitted rows, then rolls back.
- `diag_api.py`: throwaway; prints the HTTP status and `total` of three API calls without printing the key or URL. Not committed.
- `ingest.py`: now logs a WARNING when 0 records are fetched.

### Honest limits
- The hourly job has **not** been verified running unattended for many hours, so a live 16-hour daily AQI has not been shown. The 16-hour rule is shown on **made-up data** only (15 Jan, 17 Jan and 19 Jan 2026), and it is always labelled that way.
- The isolation demo uses a plain insert transaction, not `load_batch` itself.
- The CSV importer is tested only on made-up data.
- The local database still holds made-up test data (sample stations B-D, January 2026 test readings). What the final demo database shows (live only, or labelled mock data) is still to be decided with the team.

### Viva questions with short answers
1. **What does rollback guarantee?** If any step of a batch fails, none of its rows stay in the database. The batch is all or nothing.
2. **How did you prove it?** I forced an error just before the commit and compared the counts before and after; they were identical, and the same batch then loaded normally.
3. **Why `ON DUPLICATE KEY UPDATE` and not `INSERT IGNORE`?** IGNORE also turns foreign-key errors into warnings, which would hide a real violation.
4. **What stops a negative value or an unknown station/pollutant pair?** The CHECK constraint and the composite foreign key in MySQL, and earlier the `transform` step, which skips and counts them.
5. **What isolation level does MySQL use?** `REPEATABLE-READ`: another session does not see uncommitted rows.
6. **What does durability mean here?** Once `COMMIT` returns, the data survives a restart. I restarted the MySQL service and the rows were still there.
7. **Why does the API give no history?** It returns only the latest hourly value, so history exists only because the job keeps running; a missed hour cannot be fetched later.
8. **What happened when the API returned nothing?** It answered HTTP 200 with zero records. Nothing was written and the run finished normally; now a WARNING is logged so it is visible.
9. **What is NOT proven?** The hourly job running unattended for hours, and a live 16-hour AQI. Those are shown on mock data only.

## 11. Glossary
- **OGD**: Open Government Data platform (data.gov.in), source of the API.
- **CPCB**: Central Pollution Control Board, who measure the readings.
- **Transaction**: a group of SQL steps that either all succeed (commit) or all undo (rollback).
- **Least privilege**: giving an account only the permissions it needs.
- **User-Agent**: a header telling the server what kind of program is making the request.
- **HTTP 502 (Bad Gateway)**: the gateway in front of a service could not get a valid answer from it.
- **HTTP 403 (Forbidden)**: the server understood the request but refuses it; here, a bad API key.
- **Paging (`limit` / `offset`)**: asking the API for results in chunks; `offset` says where the next chunk starts.
- **NA**: the text the API uses when a value is missing; it is not a number and must be skipped.
- **Exponential backoff**: waiting longer and longer between retries (5 s, 10 s, ...).
- **Custom exception**: my own error type (for example `ApiUnavailableError`) so callers can react to specific failures.
- **Skip report**: a count of records dropped, grouped by reason.
- **Offline test**: a test that needs no internet or database because it uses saved files.
- **Commit / rollback**: `commit()` makes a transaction permanent; `rollback()` undoes all of it.
- **Autocommit**: when on, every SQL statement is saved by itself. I turn it off so a batch can be undone.
- **ON DUPLICATE KEY UPDATE**: MySQL clause that handles a row that would break a UNIQUE key; mine does nothing, so duplicates are skipped.
- **Foreign key (composite)**: a rule that a pair of values (station, pollutant) must exist in another table (`station_pollutant`). Breaking it gives error 1452.
- **User variable (`@d`)**: a value stored for one MySQL connection only; used to pass the date into Member 1's calculation.
- **Failure hook (`fail_after`)**: a test switch that makes `load_batch` fail on purpose after a chosen step.
- **Exit code**: the number a program returns when it ends; here 0 = success, 1 = API problem, 2 = load failed and rolled back, 3 = anything else.
- **Idempotent**: running the same operation twice gives the same result as running it once.
- **Atomicity / Consistency / Isolation / Durability (ACID)**: all or nothing / rules always hold / transactions do not disturb each other / committed data survives a restart.
- **REPEATABLE-READ**: MySQL's default isolation level; a session does not see other sessions' uncommitted rows.
- **Mock data**: made-up or imported data used for tests and demos; always labelled, never presented as live.

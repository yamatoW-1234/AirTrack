# AirTrack backend (Flask REST API)

Owner: Member 3. This API sits between the MySQL database and the dashboard. It follows Section 8 of the
shared contract and reads and writes only with parameterized SQL (`%s` placeholders, never string joining).

## Run it

You need MySQL 8 with the `airtrack` database loaded, and Python 3.10+.

1. Load the database in MySQL Workbench, in this order: `db/schema.sql`, `db/seed_reference.sql`,
   `db/sample_data.sql`, `db/roles.sql`, `db/calc_subindex.sql`, then `db/calc_daily_aqi.sql`
   (it works on one date at a time: change the `SET @d = ...` line and run it for each date, 2026-10-18 to 2026-10-24).
2. In the repo root (the folder that holds `backend/` and `db/`), copy `.env.example` to `.env` and fill it in:
   `DB_READER_USER`, `DB_READER_PASSWORD`, `DB_WRITER_USER`, `DB_WRITER_PASSWORD` (the accounts made by
   `db/roles.sql`) and `ADMIN_KEY` (any long secret you choose). `.env` is never committed.
3. From `backend/`:
   ```
   python -m venv venv
   venv\Scripts\activate
   pip install -r requirements.txt
   python app.py
   ```
4. Open http://localhost:5000/api/stations. The API listens on port 5000 and allows the frontend on
   `http://localhost:5500` (CORS). Stop it with Ctrl+C; it does not reload by itself.

## Endpoints

Base URL `http://localhost:5000/api`. All answers are JSON. Dates are `YYYY-MM-DD`; times are local (IST),
`YYYY-MM-DDTHH:MM:SS`. List endpoints accept `limit` (default 100, max 500) and `offset`.

| Method | Path | Parameters | What it returns |
|---|---|---|---|
| GET | `/stations` | none | all stations |
| GET | `/pollutants` | none | PM2.5, PM10, NO2, SO2 with units |
| GET | `/categories` | none | the 6 AQI categories with colours and health text |
| GET | `/stations/{id}/latest` | none | newest reading of each pollutant (with sub-index) |
| GET | `/stations/{id}/aqi` | `date` (optional, default latest) | daily AQI, category, dominant pollutant, hours of data |
| GET | `/stations/{id}/summary` | `date` (optional, default latest with readings) | per pollutant avg/min/max plus the hourly values (only hours that exist) |
| GET | `/readings` | `station_id`, `pollutant`, `from`, `to`, `limit`, `offset` | `total` and a page of readings, newest first |
| GET | `/aqi-records` | `station_id`, `from`, `to`, `category` (name or id 1-6), `limit`, `offset` | `total` and daily AQI rows, newest first |
| GET | `/reports/compare` | `date` (optional) | all stations on that date, highest AQI first |
| GET | `/reports/most-polluted` | `date` (optional) | the station with the highest AQI |
| GET | `/reports/average` | `station_id` (required), `period` = `daily` or `monthly`, `from`, `to` | average AQI per day or month |
| GET | `/reports/availability` | none | reading count, first and last time per station and pollutant |
| POST | `/admin/stations` | JSON station fields, `station_name` required | 201 `{"station_id": n}` |
| PUT | `/admin/stations/{id}` | JSON fields to change | 200 |
| POST | `/admin/station-pollutants` | `{"station_id": 1, "pollutant": "PM2.5"}` | 201 |
| POST | `/admin/readings` | `station_id`, `pollutant`, `reading_datetime`, `concentration_value` | 201 `{"reading_id": n, "sub_index": n}` |

Admin routes need the header `X-Admin-Key: <your ADMIN_KEY>`.

**Errors** are always `{"error": "message"}` with status 400 (bad input), 404 (not found), 409 (duplicate),
500 (server problem), or 401 (wrong or missing admin key, an addition to the contract's list).
SQL errors and stack traces are logged on the server and never sent to the client.
Reports and AQI routes answer 404 when the requested date has no AQI yet.

## Database accounts and security

- **Reader** (`DB_READER_*`): SELECT only. Every GET route uses it.
- **Writer** (`DB_WRITER_*`): SELECT, INSERT, UPDATE on the tables the admin routes touch; no DELETE.
  Only the admin routes use it.
- All SQL uses `%s` placeholders. The few places where a column name is built into a query take it from a
  fixed whitelist in the code, never from the request.
- Admin key is compared in constant time; a missing `ADMIN_KEY` in `.env` locks all admin routes (401).
- Input is checked before it reaches the database: dates, integers, limits, enums, number ranges, field names.

## Transactions and isolation level

- **Atomicity:** `POST /admin/readings` does the INSERT, the sub-index calculation (a join on `breakpoint`, same
  formula as `db/calc_subindex.sql`) and the commit as ONE transaction. If any step fails, everything is rolled
  back, so a reading never exists without its sub-index. A pollutant that is not assigned to the station is
  rejected by the composite foreign key `(station_id, pollutant_id)` and answered with 400; a repeated
  `(station, pollutant, time)` is rejected by the UNIQUE key and answered with 409.
- **Isolation level: REPEATABLE READ** (the InnoDB default, not changed). Plain GET routes read one consistent
  snapshot without locks, so readers and the writer never block each other. `/readings` and `/aqi-records` run
  their COUNT and their page query in one transaction with a consistent snapshot, so `total` always matches the
  rows returned. READ COMMITTED would let a commit slip in between those two queries; SERIALIZABLE would turn
  every SELECT into a locking read and make the readers wait for the writer, for no benefit here.

## Tests

```
pip install -r requirements-dev.txt
python -m pytest tests/test_api.py -v
```

`tests/test_api.py` has at least one test per endpoint and a table of bad-input cases (58 test cases). It uses the
sample data. Admin tests are skipped if `ADMIN_KEY` is not set. They write to one fixed test station,
`TEST_PYTEST_STATION`, so re-running does not create new stations.

**Concurrency test** (start the API first, then use a second window):

```
python tests/concurrency_test.py
```

30 reader threads call GET endpoints for 20 seconds while one thread keeps posting readings. It reports the
number of requests, errors, readings seen without a sub-index (must be 0), `total` versus rows (must match) and
a final check that everything the writer was told is in the database. The exit code is 0 only if everything is clean.
It writes to `TEST_CONCURRENCY_STATION`.

**Cleaning up:** the tests leave their rows behind (the writer account cannot delete). Run
`tests/cleanup_test_data.sql` in MySQL Workbench before a demo; it removes only the two test stations and their readings.

## Folder layout

```
backend/
  app.py              starts Flask and registers the route files
  config.py           reads .env (repo root)
  db.py               connection pools (reader and writer), fetch helpers, transaction()
  errors.py           ApiError and the error JSON for every failure
  validators.py       input checks (dates, integers, paging, choices)
  routes/
    public.py         lookups, latest, daily AQI, 24-hour summary
    search.py         /readings and /aqi-records
    reports.py        /reports/*
    admin.py          /admin/* (X-Admin-Key)
  tests/
    test_api.py, concurrency_test.py, cleanup_test_data.sql
  requirements.txt, requirements-dev.txt
```

# AirTrack

AirTrack shows how clean or polluted the air is in Delhi.

It collects air quality readings, saves them in a MySQL database, works out a daily **Air Quality Index (AQI)** for each station, and shows the results on a web dashboard.

```
Government data  ->  ingestion  ->  MySQL database  ->  Flask API  ->  web dashboard
```

A DBMS course project at NIT Delhi.

## Team

| Member | Name | Part | Folder |
|---|---|---|---|
| 1 | Harsh | Database | `db/` |
| 2 | Laksh | Data ingestion | `ingestion/` |
| 3 | Hitesh | Backend API | `backend/` |
| 4 | Moulando | Frontend | `frontend/` |

## What you need

- Python 3.10 or newer
- MySQL 8 (and MySQL Workbench, if you like clicking more than typing)
- A web browser with internet
- Git

You do **not** need any API key to try the project. It comes with sample data.

## How to run it

Follow these steps in order. Run every command from the main `airtrack` folder unless it says otherwise.

### Step 1: Get the code

```
git clone <repository-url>
cd airtrack
```

### Step 2: Create the database

Open MySQL Workbench, log in as `root`, and run these files from the `db/` folder **in this order**:

1. `schema.sql`
2. `seed_reference.sql`
3. `sample_data.sql`
4. `roles.sql`
5. `calc_subindex.sql`
6. `calc_daily_aqi.sql`

Two things to know:

- **`roles.sql`** creates two database users. Before running it, change the placeholder passwords in the file (`change_me_reader` and `change_me_writer`). Remember them for Step 3.
- **`calc_daily_aqi.sql`** works on one date at a time. Near the top is a line like `SET @d = '2026-10-18';`. Run the file once for each date from `2026-10-18` to `2026-10-24`, changing that line each time (7 runs).

Prefer the terminal? In Git Bash, macOS or Linux, this runs all 7 dates in one go:

```
for d in 2026-10-18 2026-10-19 2026-10-20 2026-10-21 2026-10-22 2026-10-23 2026-10-24; do
  sed "s/^SET @d = .*/SET @d = '$d';/" db/calc_daily_aqi.sql
done | mysql -u root -p airtrack
```

### Step 3: Create your `.env` file

Copy `.env.example` to a new file called `.env` in the main folder.

```
# Windows
copy .env.example .env

# macOS / Linux
cp .env.example .env
```

Open `.env` and fill in these lines:

| Setting | What to put |
|---|---|
| `DB_READER_USER` | `airtrack_reader` |
| `DB_READER_PASSWORD` | The reader password you chose in Step 2 |
| `DB_WRITER_USER` | `airtrack_writer` |
| `DB_WRITER_PASSWORD` | The writer password you chose in Step 2 |
| `ADMIN_KEY` | Any long secret word you make up (you will type it on the Admin page) |

Leave the other lines as they are. Never share or upload your `.env` file.

### Step 4: Start the backend

```
cd backend
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # macOS / Linux
pip install -r requirements.txt
python app.py
```

Check that it works: open http://localhost:5000/api/stations in your browser. You should see a list of stations.

Leave this window open.

### Step 5: Start the frontend

1. Open `frontend/js/config.js` and change `USE_MOCK = true` to `USE_MOCK = false`.
2. Open a **new** terminal window and run:

```
cd frontend
python -m http.server 5500
```

3. Open http://localhost:5500 in your browser.

Use port **5500** exactly. The backend only accepts requests from that port.

**Done!** You should see the AQI dashboard.

> Just want to look at the pages without the database? Leave `USE_MOCK = true`. The pages will show fake sample data and a yellow banner.

## What is on each page

| Page | What you can do |
|---|---|
| Dashboard | Pick a station and see its AQI, category and latest pollutant values |
| 24-Hour Summary | See hourly charts and average, lowest and highest values for one day |
| Search | Look through readings and AQI records with filters |
| Reports | Compare stations on one date, or see a station's average AQI |
| Admin | Add or edit stations (type your `ADMIN_KEY` first) |

The sample data covers 18 to 24 October 2026, so the newest AQI you will see is for **24 Oct 2026**.

## Optional: use live data

The sample data is enough to use every page. If you want real, current readings:

1. Get a free API key from [data.gov.in](https://data.gov.in) and put it in `.env` as `OGD_API_KEY`.
2. Add the real stations (run once): `mysql -u root -p < ingestion/stations_real.sql`
3. Set up ingestion:

```
python -m venv ingestion/venv
source ingestion/venv/Scripts/activate      # Git Bash on Windows
# ingestion\venv\Scripts\activate           # Windows cmd
# source ingestion/venv/bin/activate        # macOS / Linux
pip install -r ingestion/requirements.txt
```

4. Fetch data:

```
python ingestion/ingest.py --once       # fetch the latest readings once
python ingestion/ingest.py schedule     # fetch now, then every hour
```

The government API only gives the **latest hour**, so history builds up only while this keeps running. The AQI is calculated automatically after each fetch. More details are in [`ingestion/README_ingestion.md`](ingestion/README_ingestion.md).

## Something not working?

| Problem | Fix |
|---|---|
| Yellow "Showing sample data" banner | In `frontend/js/config.js`, set `USE_MOCK = false` and reload |
| "Cannot reach the backend" | Start the backend (Step 4) and check http://localhost:5000/api/stations |
| CORS error in the browser | Run the frontend on port 5500, and don't double-click the HTML files |
| "Missing DB_READER_USER" | `.env` is missing, in the wrong folder, or empty. It must be in the main `airtrack` folder |
| Backend can't connect to MySQL | Make sure MySQL is running and the passwords in `.env` match `roles.sql` |
| Admin page says "Unauthorized" | The key you typed must match `ADMIN_KEY` in `.env`. Restart the backend after changing `.env` |
| "No AQI data available" | Run `calc_daily_aqi.sql` for each date (Step 2) |
| Charts are empty | Check your internet connection (charts load from the internet) |
| `python` or `pip` not found | Install Python 3.10+, or try `python3` and `pip3` |

## Learn more

- Backend API, endpoints and tests: [`backend/README.md`](backend/README.md)
- Database design and ER diagram: [`docs/report.md`](docs/report.md), [`docs/er_diagram.png`](docs/er_diagram.png)
- How data is loaded safely (ACID): [`docs/REPORT_ingestion_acid.md`](docs/REPORT_ingestion_acid.md)
- Backup and restore: [`db/RESTORE.md`](db/RESTORE.md)
- Assumptions we made about the AQI: [`docs/assumptions.md`](docs/assumptions.md)

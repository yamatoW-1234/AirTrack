import math
import random
from datetime import datetime, timedelta

random.seed(42)  # same fake data every time you run it

START = datetime(2026, 10, 18)   # 7 days: 18 Oct to 24 Oct 2026
DAYS = 7

# Typical level of each pollutant per station.
# Pollutant ids: 1=PM2.5, 2=PM10, 3=NO2, 4=SO2
# Station ids: 1=Anand Vihar (already in seed), 2,3,4 = Sample Station B,C,D
base = {
    1: {1: 200, 2: 320, 3: 90,  4: 25},   # very polluted
    2: {1: 85,  2: 150, 3: 60,  4: 18},   # moderate
    3: {1: 40,  2: 80,  3: 35,  4: 12},   # cleaner
    4: {1: 140, 2: 240, 3: 110, 4: 30},   # poor
}

# Each day is cleaner or dirtier, so several categories appear
day_factor = [1.0, 0.7, 1.3, 0.5, 1.6, 0.9, 1.1]

# One gap on purpose: Station B, PM2.5, 21 Oct, hours 0-9 are missing.
# That day has only 14 readings, which is fewer than 16, so it tests the 16-hour rule.
SKIP_STATION, SKIP_POLLUTANT = 2, 1
SKIP_DAY = datetime(2026, 10, 21).date()
SKIP_HOURS = range(0, 10)

lines = []
lines.append("USE airtrack;\n")

# Three extra fake stations (Anand Vihar already exists from the seed file)
lines.append("""INSERT INTO monitoring_station
(station_id, station_name, location, latitude, longitude, station_type, status) VALUES
(2, 'Sample Station B', 'Sample Area B, Delhi', 28.6500, 77.3000, 'Ambient', 'Active'),
(3, 'Sample Station C', 'Sample Area C, Delhi', 28.6000, 77.2500, 'Ambient', 'Active'),
(4, 'Sample Station D', 'Sample Area D, Delhi', 28.7000, 77.1500, 'Ambient', 'Active');
""")

# Each of them measures all 4 pollutants
pairs = ", ".join(f"({s}, {p})" for s in (2, 3, 4) for p in (1, 2, 3, 4))
lines.append(f"INSERT INTO station_pollutant (station_id, pollutant_id) VALUES {pairs};\n")

# Hourly readings. sub_index is left empty; calc_subindex.sql fills it later.
for station_id in base:
    for pollutant_id in base[station_id]:
        rows = []
        for d in range(DAYS):
            for hour in range(24):
                t = START + timedelta(days=d, hours=hour)
                if (station_id == SKIP_STATION and pollutant_id == SKIP_POLLUTANT
                        and t.date() == SKIP_DAY and hour in SKIP_HOURS):
                    continue
                daily_wave = 1 + 0.3 * math.sin(2 * math.pi * (hour - 6) / 24)
                noise = random.uniform(0.9, 1.1)
                value = round(max(0, base[station_id][pollutant_id] * day_factor[d] * daily_wave * noise), 2)
                rows.append(f"({station_id}, {pollutant_id}, '{t:%Y-%m-%d %H:%M:%S}', {value})")
        lines.append(
            "INSERT INTO reading (station_id, pollutant_id, reading_datetime, concentration_value) VALUES\n"
            + ",\n".join(rows) + ";\n"
        )

with open("db/sample_data.sql", "w") as f:
    f.write("\n".join(lines))

print("Done: db/sample_data.sql written")
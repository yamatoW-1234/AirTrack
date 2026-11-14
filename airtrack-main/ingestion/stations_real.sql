-- AirTrack: real stations near Anand Vihar (Phase B, Member 2)
-- Station 1 (Anand Vihar) already exists from seed_reference.sql, so it is NOT inserted here.
-- Names and coordinates come from the CPCB data (OGD). PROVISIONAL: taken from a 2023 snapshot,
-- to be confirmed against a live API response before pushing. Run this file ONCE.

USE airtrack;

INSERT INTO monitoring_station
    (station_name, location, latitude, longitude, station_type, status)
VALUES
    ('Vivek Vihar, Delhi - DPCC',           'Vivek Vihar, Delhi',           28.672342, 77.315260, 'Ambient', 'Active'),
    ('IHBAS, Dilshad Garden, Delhi - CPCB', 'IHBAS, Dilshad Garden, Delhi', 28.681174, 77.302523, 'Ambient', 'Active'),
    ('Patparganj, Delhi - DPCC',            'Patparganj, Delhi',            28.623763, 77.287209, 'Ambient', 'Active'),
    ('ITO, Delhi - CPCB',                   'ITO, Delhi',                   28.628624, 77.241060, 'Ambient', 'Active');

-- Link each new station to the 4 pollutants by NAME, not by hard-coded id
INSERT INTO station_pollutant (station_id, pollutant_id)
SELECT s.station_id, p.pollutant_id
FROM monitoring_station s, pollutant p
WHERE s.station_name IN (
        'Vivek Vihar, Delhi - DPCC',
        'IHBAS, Dilshad Garden, Delhi - CPCB',
        'Patparganj, Delhi - DPCC',
        'ITO, Delhi - CPCB')
  AND p.pollutant_name IN ('PM2.5', 'PM10', 'NO2', 'SO2');

-- Check: expect 5 stations (ids 1 to 5), each with 4 pollutants
SELECT s.station_id, s.station_name, COUNT(sp.pollutant_id) AS n_pollutants
FROM monitoring_station s
LEFT JOIN station_pollutant sp ON sp.station_id = s.station_id
GROUP BY s.station_id, s.station_name
ORDER BY s.station_id;

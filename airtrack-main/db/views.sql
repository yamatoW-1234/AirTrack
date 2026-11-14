USE airtrack;

-- View 1: the most recent reading for each station and pollutant
CREATE OR REPLACE VIEW v_latest_reading AS
SELECT r.station_id,
       s.station_name,
       p.pollutant_name AS pollutant,
       r.concentration_value AS concentration,
       r.sub_index,
       r.reading_datetime
FROM reading r
JOIN monitoring_station s ON s.station_id = r.station_id
JOIN pollutant p ON p.pollutant_id = r.pollutant_id
WHERE r.reading_datetime = (
        SELECT MAX(r2.reading_datetime)
        FROM reading r2
        WHERE r2.station_id = r.station_id
          AND r2.pollutant_id = r.pollutant_id
      );

-- View 2: daily AQI with station, category, colour and dominant pollutant joined in
CREATE OR REPLACE VIEW v_daily_aqi_full AS
SELECT a.aqi_id,
       a.station_id,
       s.station_name,
       a.record_date,
       a.aqi_value,
       c.category_name,
       c.color_code,
       c.health_impact,
       p.pollutant_name AS dominant_pollutant,
       a.hours_of_data,
       a.last_updated
FROM aqi_record a
JOIN monitoring_station s ON s.station_id = a.station_id
JOIN aqi_category c ON c.category_id = a.category_id
JOIN pollutant p ON p.pollutant_id = a.dominant_pollutant_id;

-- View 3: how much data each station has for each pollutant
CREATE OR REPLACE VIEW v_station_availability AS
SELECT s.station_name,
       p.pollutant_name AS pollutant,
       COUNT(r.reading_id)       AS reading_count,
       MIN(r.reading_datetime)   AS first_reading,
       MAX(r.reading_datetime)   AS last_reading
FROM station_pollutant sp
JOIN monitoring_station s ON s.station_id = sp.station_id
JOIN pollutant p ON p.pollutant_id = sp.pollutant_id
LEFT JOIN reading r
       ON r.station_id = sp.station_id AND r.pollutant_id = sp.pollutant_id
GROUP BY s.station_name, p.pollutant_name;
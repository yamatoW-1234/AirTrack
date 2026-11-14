USE airtrack;

-- Q1 (JOIN): Latest AQI of every station with category name
SELECT s.station_name, a.record_date, a.aqi_value, c.category_name
FROM aqi_record a
JOIN monitoring_station s ON s.station_id = a.station_id
JOIN aqi_category c ON c.category_id = a.category_id
WHERE a.record_date = (SELECT MAX(record_date) FROM aqi_record);

-- Q2 (GROUP BY + AVG): Average PM2.5 per station
SELECT s.station_name, ROUND(AVG(r.concentration_value),1) AS avg_pm25
FROM reading r
JOIN monitoring_station s ON s.station_id = r.station_id
WHERE r.pollutant_id = 1
GROUP BY s.station_name;

-- Q3 (HAVING): Station-days with at least 16 PM2.5 readings
SELECT station_id, DATE(reading_datetime) AS day, COUNT(*) AS n
FROM reading
WHERE pollutant_id = 1
GROUP BY station_id, DATE(reading_datetime)
HAVING COUNT(*) >= 16;

-- Q4 (HAVING, other side): Station-days that fail the 16-hour rule
SELECT station_id, pollutant_id, DATE(reading_datetime) AS day, COUNT(*) AS n
FROM reading
GROUP BY station_id, pollutant_id, DATE(reading_datetime)
HAVING COUNT(*) < 16;

-- Q5 (subquery): Station-day with the highest AQI ever recorded
SELECT s.station_name, a.record_date, a.aqi_value
FROM aqi_record a
JOIN monitoring_station s ON s.station_id = a.station_id
WHERE a.aqi_value = (SELECT MAX(aqi_value) FROM aqi_record);

-- Q6 (GROUP BY): How many station-days fell in each category
SELECT c.category_name, COUNT(*) AS station_days
FROM aqi_record a
JOIN aqi_category c ON c.category_id = a.category_id
GROUP BY c.category_id, c.category_name
ORDER BY c.category_id;

-- Q7 (NOT EXISTS): Stations that measure EVERY pollutant
SELECT s.station_name
FROM monitoring_station s
WHERE NOT EXISTS (
    SELECT 1 FROM pollutant p
    WHERE NOT EXISTS (
        SELECT 1 FROM station_pollutant sp
        WHERE sp.station_id = s.station_id AND sp.pollutant_id = p.pollutant_id));

-- Q8 (UNION): Stations with an AQI above 200 OR a PM10 reading above 350
SELECT DISTINCT station_id, 'AQI above 200' AS reason FROM aqi_record WHERE aqi_value > 200
UNION
SELECT DISTINCT station_id, 'PM10 above 350' FROM reading
WHERE pollutant_id = 2 AND concentration_value > 350;

-- Q9 (IN, INTERSECT style): Stations with BOTH a day above 200 and a day at or below 100
SELECT DISTINCT station_id FROM aqi_record
WHERE aqi_value > 200
  AND station_id IN (SELECT station_id FROM aqi_record WHERE aqi_value <= 100);

-- Q10 (view + ORDER BY + LIMIT): Top 5 most polluted station-days
SELECT * FROM v_daily_aqi_full ORDER BY aqi_value DESC LIMIT 5;

-- Q11 (view + GROUP BY): How often each pollutant was dominant
SELECT dominant_pollutant, COUNT(*) AS times_dominant
FROM v_daily_aqi_full
GROUP BY dominant_pollutant
ORDER BY times_dominant DESC;
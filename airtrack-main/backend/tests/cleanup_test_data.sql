-- Removes the rows created by tests/test_api.py and tests/concurrency_test.py.
-- Run it in MySQL Workbench with your normal (root) account. The API's writer account has no
-- DELETE right on purpose, so the tests cannot clean up after themselves.
-- It only touches the two test stations named below, never real or sample stations.
USE airtrack;

DELETE FROM reading
 WHERE station_id IN (SELECT station_id FROM monitoring_station
                       WHERE station_name IN ('TEST_PYTEST_STATION', 'TEST_CONCURRENCY_STATION'));

DELETE FROM station_pollutant
 WHERE station_id IN (SELECT station_id FROM monitoring_station
                       WHERE station_name IN ('TEST_PYTEST_STATION', 'TEST_CONCURRENCY_STATION'));

DELETE FROM monitoring_station
 WHERE station_name IN ('TEST_PYTEST_STATION', 'TEST_CONCURRENCY_STATION');

-- Optional: if you tried the curl example from the instructions, this removes that one reading
-- (station 1, PM2.5, 4 Nov 2026 10:00). Remove the two dashes at the start of the next line to run it.
-- DELETE FROM reading WHERE station_id = 1 AND pollutant_id = 1 AND reading_datetime = '2026-11-04 10:00:00';

-- Check: back to the sample data
SELECT (SELECT COUNT(*) FROM monitoring_station) AS stations,
       (SELECT COUNT(*) FROM reading)            AS readings;

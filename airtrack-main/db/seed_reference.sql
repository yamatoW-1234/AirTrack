USE airtrack;

-- 4 pollutants
INSERT INTO pollutant (pollutant_id, pollutant_name, unit) VALUES
(1, 'PM2.5', 'ug/m3'),
(2, 'PM10',  'ug/m3'),
(3, 'NO2',   'ug/m3'),
(4, 'SO2',   'ug/m3');

-- 6 AQI categories
INSERT INTO aqi_category (category_id, category_name, min_aqi, max_aqi, color_code, health_impact) VALUES
(1, 'Good',                0,  50, '#00B050', 'Minimal impact'),
(2, 'Satisfactory',       51, 100, '#92D050', 'May cause minor breathing discomfort to sensitive people'),
(3, 'Moderately Polluted',101, 200, '#FFD700', 'May cause breathing discomfort to people with lung or heart disease, children and older adults'),
(4, 'Poor',               201, 300, '#FF9900', 'May cause breathing discomfort on prolonged exposure'),
(5, 'Very Poor',          301, 400, '#FF0000', 'May cause respiratory illness on prolonged exposure'),
(6, 'Severe',             401, 500, '#800000', 'Affects healthy people and seriously impacts those with existing diseases');

-- 24 breakpoints: (pollutant, category, conc_low, conc_high, index_low, index_high)
INSERT INTO breakpoint (pollutant_id, category_id, conc_low, conc_high, index_low, index_high) VALUES
-- PM2.5
(1, 1,   0,  30,   0,  50),
(1, 2,  30,  60,  51, 100),
(1, 3,  60,  90, 101, 200),
(1, 4,  90, 120, 201, 300),
(1, 5, 120, 250, 301, 400),
(1, 6, 250, 500, 401, 500),
-- PM10
(2, 1,   0,  50,   0,  50),
(2, 2,  50, 100,  51, 100),
(2, 3, 100, 250, 101, 200),
(2, 4, 250, 350, 201, 300),
(2, 5, 350, 430, 301, 400),
(2, 6, 430, 600, 401, 500),
-- NO2
(3, 1,   0,  40,   0,  50),
(3, 2,  40,  80,  51, 100),
(3, 3,  80, 180, 101, 200),
(3, 4, 180, 280, 201, 300),
(3, 5, 280, 400, 301, 400),
(3, 6, 400, 500, 401, 500),
-- SO2
(4, 1,   0,  40,   0,  50),
(4, 2,  40,  80,  51, 100),
(4, 3,  80, 380, 101, 200),
(4, 4, 380, 800, 201, 300),
(4, 5, 800,1600, 301, 400),
(4, 6,1600,2000, 401, 500);

-- Anand Vihar and the 4 pollutants it measures
INSERT INTO monitoring_station (station_id, station_name, location, latitude, longitude, station_type, status)
VALUES (1, 'Anand Vihar, Delhi - DPCC', 'Anand Vihar, Delhi', 28.6469, 77.3164, 'Ambient', 'Active');

INSERT INTO station_pollutant (station_id, pollutant_id) VALUES
(1, 1), (1, 2), (1, 3), (1, 4);
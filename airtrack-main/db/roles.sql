USE airtrack;

-- Placeholder passwords. Change them locally and never commit real ones.
DROP USER IF EXISTS 'airtrack_reader'@'localhost';
DROP USER IF EXISTS 'airtrack_writer'@'localhost';

CREATE USER 'airtrack_reader'@'localhost' IDENTIFIED BY 'change_me_reader';
CREATE USER 'airtrack_writer'@'localhost' IDENTIFIED BY 'change_me_writer';

-- Reader: SELECT only
GRANT SELECT ON airtrack.* TO 'airtrack_reader'@'localhost';

-- Writer: SELECT everywhere, INSERT/UPDATE on the tables ingestion and admin touch
GRANT SELECT ON airtrack.* TO 'airtrack_writer'@'localhost';
GRANT INSERT, UPDATE ON airtrack.reading            TO 'airtrack_writer'@'localhost';
GRANT INSERT, UPDATE ON airtrack.aqi_record         TO 'airtrack_writer'@'localhost';
GRANT INSERT, UPDATE ON airtrack.monitoring_station TO 'airtrack_writer'@'localhost';
GRANT INSERT, UPDATE ON airtrack.station_pollutant  TO 'airtrack_writer'@'localhost';

FLUSH PRIVILEGES;
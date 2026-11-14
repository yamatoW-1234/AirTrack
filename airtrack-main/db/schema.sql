DROP DATABASE IF EXISTS airtrack;
CREATE DATABASE airtrack;
USE airtrack;

CREATE TABLE pollutant(
    pollutant_id INT PRIMARY KEY AUTO_INCREMENT,
    pollutant_name VARCHAR(10) UNIQUE NOT NULL,
    unit VARCHAR(15) NOT NULL
);

CREATE TABLE monitoring_station(
    station_id INT PRIMARY KEY AUTO_INCREMENT,
    station_name VARCHAR(100) UNIQUE NOT NULL,
    location VARCHAR(100),
    latitude DECIMAL(9,6),
    longitude DECIMAL(9,6),
    station_type VARCHAR(30),
    status ENUM('Active','Inactive') DEFAULT 'Active',
    installation_date DATE
);

CREATE TABLE aqi_category(
    category_id INT PRIMARY KEY,
    category_name VARCHAR(30) NOT NULL,
    min_aqi INT NOT NULL,
    max_aqi INT NOT NULL,
    color_code CHAR(7) NOT NULL,
    health_impact VARCHAR(255)
);

-- Which station measures which pollutant (many-to-many)
CREATE TABLE station_pollutant(
    station_id INT,
    pollutant_id INT,
    PRIMARY KEY (station_id, pollutant_id),
    FOREIGN KEY (station_id) REFERENCES monitoring_station(station_id),
    FOREIGN KEY (pollutant_id) REFERENCES pollutant(pollutant_id)
);

-- Conversion chart: concentration range -> AQI range
CREATE TABLE breakpoint(
    breakpoint_id INT PRIMARY KEY AUTO_INCREMENT,
    pollutant_id INT NOT NULL,
    category_id INT NOT NULL,
    conc_low DECIMAL(8,2) NOT NULL,
    conc_high DECIMAL(8,2) NOT NULL,
    index_low INT NOT NULL,
    index_high INT NOT NULL,
    FOREIGN KEY (pollutant_id) REFERENCES pollutant(pollutant_id),
    FOREIGN KEY (category_id) REFERENCES aqi_category(category_id),
    UNIQUE (pollutant_id, category_id)
);

-- Hourly measurements
CREATE TABLE reading(
    reading_id BIGINT PRIMARY KEY AUTO_INCREMENT,
    station_id INT NOT NULL,
    pollutant_id INT NOT NULL,
    reading_datetime DATETIME NOT NULL,
    concentration_value DECIMAL(8,2) NOT NULL,
    sub_index INT NULL,
    CHECK (concentration_value >= 0),
    -- composite FK: only pollutants assigned to the station are accepted
    FOREIGN KEY (station_id, pollutant_id)
        REFERENCES station_pollutant(station_id, pollutant_id),
    UNIQUE (station_id, pollutant_id, reading_datetime),
    INDEX idx_reading_station_time (station_id, reading_datetime)
);

-- Daily AQI result per station
CREATE TABLE aqi_record(
    aqi_id INT PRIMARY KEY AUTO_INCREMENT,
    station_id INT NOT NULL,
    record_date DATE NOT NULL,
    aqi_value INT NOT NULL,
    category_id INT NOT NULL,
    dominant_pollutant_id INT NOT NULL,
    hours_of_data TINYINT,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (station_id) REFERENCES monitoring_station(station_id),
    FOREIGN KEY (category_id) REFERENCES aqi_category(category_id),
    FOREIGN KEY (dominant_pollutant_id) REFERENCES pollutant(pollutant_id),
    UNIQUE (station_id, record_date)
);
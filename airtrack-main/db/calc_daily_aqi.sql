USE airtrack;

SET @d = '2026-10-18';

INSERT INTO aqi_record
       (station_id, record_date, aqi_value, category_id,
        dominant_pollutant_id, hours_of_data)
WITH si AS (
    SELECT d.station_id,
           d.pollutant_id,
           d.hours_count,
           CASE
             WHEN d.avg_conc >= top.conc_high THEN 500
             ELSE ROUND(
                  (b.index_high - b.index_low) / (b.conc_high - b.conc_low)
                  * (d.avg_conc - b.conc_low) + b.index_low)
           END AS sub_index
    FROM (
            SELECT r.station_id,
                   r.pollutant_id,
                   AVG(r.concentration_value) AS avg_conc,
                   COUNT(*)                   AS hours_count
            FROM reading r
            WHERE r.reading_datetime >= @d
              AND r.reading_datetime <  DATE_ADD(@d, INTERVAL 1 DAY)
            GROUP BY r.station_id, r.pollutant_id
            HAVING COUNT(*) >= 16
         ) d
    JOIN breakpoint top
      ON top.pollutant_id = d.pollutant_id AND top.category_id = 6
    JOIN breakpoint b
      ON b.pollutant_id = d.pollutant_id
     AND b.conc_low = (
            SELECT MAX(x.conc_low)
            FROM breakpoint x
            WHERE x.pollutant_id = d.pollutant_id
              AND x.conc_low <= d.avg_conc
         )
),
best AS (
    SELECT s.station_id,
           MIN(s.pollutant_id) AS dominant_pollutant_id,
           s.sub_index         AS aqi_value,
           MIN(s.hours_count)  AS hours_of_data
    FROM si s
    WHERE s.sub_index = (SELECT MAX(s2.sub_index) FROM si s2
                         WHERE s2.station_id = s.station_id)
      AND s.station_id IN (
            SELECT station_id
            FROM si
            GROUP BY station_id
            HAVING COUNT(*) >= 2
               AND SUM(pollutant_id IN (1, 2)) >= 1
      )
    GROUP BY s.station_id, s.sub_index
)
SELECT bst.station_id,
       @d,
       bst.aqi_value,
       c.category_id,
       bst.dominant_pollutant_id,
       bst.hours_of_data
FROM best bst
JOIN aqi_category c
  ON bst.aqi_value BETWEEN c.min_aqi AND c.max_aqi
ON DUPLICATE KEY UPDATE
       aqi_value             = VALUES(aqi_value),
       category_id           = VALUES(category_id),
       dominant_pollutant_id = VALUES(dominant_pollutant_id),
       hours_of_data         = VALUES(hours_of_data);
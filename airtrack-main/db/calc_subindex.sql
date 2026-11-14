USE airtrack;
SET SQL_SAFE_UPDATES = 0;

-- Part 1: readings that fall inside a breakpoint range
UPDATE reading r
JOIN breakpoint b
  ON b.pollutant_id = r.pollutant_id
 AND r.concentration_value >= b.conc_low
 AND r.concentration_value <  b.conc_high
SET r.sub_index = ROUND(
      (b.index_high - b.index_low) / (b.conc_high - b.conc_low)
      * (r.concentration_value - b.conc_low)
      + b.index_low
    )
WHERE r.sub_index IS NULL;

-- Part 2: readings at or above the top of the Severe range are capped at 500
UPDATE reading r
JOIN breakpoint b
  ON b.pollutant_id = r.pollutant_id
 AND b.category_id = 6
 AND r.concentration_value >= b.conc_high
SET r.sub_index = 500
WHERE r.sub_index IS NULL;
# Assumptions

1. The Severe range has no official upper limit, so we chose caps for the
   formula: PM2.5 500, PM10 600, NO2 500, SO2 2000. Values above the cap
   are limited to AQI 500.
2. We store continuous ranges (each conc_high equals the next conc_low).
   The official table writes 0-30, 31-60 and so on. A value exactly on a
   boundary, such as PM2.5 = 30, falls in the higher category.
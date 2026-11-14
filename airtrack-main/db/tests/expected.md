# AQI verification examples

Method: daily average per pollutant (only if 16+ hourly readings), convert
each average to a sub-index with the breakpoint formula, AQI = highest sub-index.

## Example 1: Station 1, 2026-10-18 (normal day)
Averages: PM2.5 = _196.00_, PM10 = _318.44_, NO2 = _90.32_, SO2 = _24.84_ (24 readings each)
Stored result: AQI = _359_, category = _very poor_, dominant = _PM2.5_
Checked: sub-index of the dominant pollutant recomputed with the formula = _358.87_ (matches)

## Example 2: Station 2, 2026-10-21 (16-hour rule)
PM2.5 has only 14 readings, so it is excluded.
Averages used: PM10 = _76.60_, NO2 = _29.74_, SO2 = _45.82_
Stored result: AQI = _77_, category = _satisfactory_, dominant = _PM10_ (not PM2.5), hours_of_data = _24_
Checked: PM10 sub-index recomputed = 77.07 (matches).

## Example 3: Station _Anand Vihar,Delhi-DPCC_, date _2026-10-22_ (highest AQI in the data)
Averages: PM2.5 = _323.29_, PM10 = _511.60_, NO2 = _147.99_, SO2 = _39.65_
Stored result: AQI = _449_, category = _severe_, dominant = _PM10_
Checked: sub-index of the dominant pollutant recomputed with the formula = _449_ (matches)
# KO Scan Data Analysis

Generated: 2026-03-31 22:25 | Source: `data/cache/` | 64 total entries

---

## Overview

- Total cache entries: 64
- With KO detected: 62 (96.9%)
- Explicitly no-KO (NONE suffix): 2 (3.1%)
- Legacy null entries (no suffix, old format): 0 (0.0%)

Characters in dataset: DOCTOR_STRANGE, JEFF_THE_LAND_SHARK, SQUIRREL_GIRL, THOR

## Tier Distribution

```
  QUAD       7 ( 10.9%)  #######.......................
  TRIPLE    29 ( 45.3%)  ##############################
  DOUBLE    22 ( 34.4%)  ######################........
  KO         4 (  6.2%)  ####..........................
  NONE       2 (  3.1%)  ##............................
  null       0 (  0.0%)  ..............................
```

### Per character

- **DOCTOR_STRANGE** (3 clips): DOUBLE:3
- **JEFF_THE_LAND_SHARK** (1 clips): DOUBLE:1
- **SQUIRREL_GIRL** (16 clips): QUAD:2, TRIPLE:10, DOUBLE:4
- **THOR** (44 clips): QUAD:5, TRIPLE:19, DOUBLE:14, KO:4, NONE:2

## KO Event Timing (start_ts)

start_ts = timestamp of the first KO detection in the clip (seconds from clip start).

  start_ts n=62  min=7.00s  max=33.00s  mean=13.27s  median=11.50s  p10=8.50s  p90=18.50s

### Histogram (5s buckets)
```
  0-5s          0  ..............................
  5-10s        19  #######################.......
  10-15s       24  ##############################
  15-20s       13  ################..............
  20-25s        3  ###...........................
  25-30s        2  ##............................
  30-35s        1  #.............................
  35-40s        0  ..............................
  40-45s        0  ..............................
  45-50s        0  ..............................
  50-55s        0  ..............................
  55-60s        0  ..............................
```

### Percentile table

| Percentile | start_ts |
|------------|----------|
| min | 7.00s |
| p10 | 8.50s |
| p25 | 9.50s |
| p50 | 11.50s |
| p75 | 16.00s |
| p90 | 18.50s |
| max | 33.00s |

### Optimisation insight

- 90% of KO events begin before **18.5s** into the clip
- 10% of KO events begin after **8.5s** (earliest is 7.0s)
- Scanning could safely stop at ~22s (p90 + ~3s buffer for banner to fully show)
- SKIP_SECS could be raised to ~6.5s (current earliest KO minus 0.5s safety)

## KO Sequence Duration (end_ts - start_ts)

Measures how long a multi-kill event lasts from first to last KO banner.

  sequence_duration n=62  min=1.00s  max=25.00s  mean=7.58s  median=5.75s  p10=2.00s  p90=16.00s

### By tier

- **KO**:    n=4  min=1.00s  max=2.50s  mean=1.38s  median=1.00s  p10=1.00s  p90=2.50s
- **DOUBLE**:    n=22  min=1.00s  max=25.00s  mean=7.16s  median=3.25s  p10=2.00s  p90=19.00s
- **TRIPLE**:    n=29  min=1.50s  max=16.50s  mean=7.50s  median=6.00s  p10=3.50s  p90=13.50s
- **QUAD**:    n=7  min=6.50s  max=17.50s  mean=12.79s  median=13.00s  p10=6.50s  p90=17.50s

### Optimisation insight

- After detecting a KO event, skip ahead by at least 16.0s (p90 sequence duration) before resuming scan
- This avoids redundant OCR frames mid-sequence

## Kill Chain Spacing (time between consecutive kills)

For multi-kill events (DOUBLE+), the time between each kill in the chain.

  inter-kill gap n=62  min=2.00s  max=24.00s  mean=5.67s  median=4.50s  p10=2.00s  p90=9.00s

### By tier

- **DOUBLE**:    n=11  min=2.00s  max=24.00s  mean=9.50s  median=8.00s  p10=2.50s  p90=21.00s
- **TRIPLE**:    n=35  min=2.00s  max=11.00s  mean=4.70s  median=4.00s  p10=2.00s  p90=8.00s
- **QUAD**:    n=16  min=2.00s  max=10.00s  mean=5.16s  median=4.50s  p10=2.00s  p90=9.00s

### Optimisation insight

- p90 inter-kill gap = 9.00s - OCR cooldown window can be set to this safely

## Clip Duration Distribution

  clip_duration n=64  min=16.41s  max=48.43s  mean=29.86s  median=29.55s  p10=19.17s  p90=41.37s

### Histogram (5s buckets)
```
  15-20s        7  ###########...................
  20-25s       13  #####################.........
  25-30s       13  #####################.........
  30-35s       18  ##############################
  35-40s        5  ########......................
  40-45s        5  ########......................
  45-50s        3  #####.........................
```

### By tier

- **KO**:    n=4  min=18.49s  max=34.47s  mean=24.50s  median=22.52s  p10=18.49s  p90=34.47s
- **DOUBLE**:    n=22  min=16.41s  max=48.43s  mean=32.75s  median=31.99s  p10=22.38s  p90=45.86s
- **TRIPLE**:    n=29  min=17.21s  max=41.37s  mean=28.18s  median=28.06s  p10=21.70s  p90=36.56s
- **QUAD**:    n=7  min=23.95s  max=42.66s  mean=34.07s  median=34.33s  p10=23.95s  p90=42.66s
- **NONE**:    n=2  min=18.47s  max=18.71s  mean=18.59s  median=18.59s  p10=18.47s  p90=18.71s

## Scan Time Analysis (for time-estimation model)

  scan_time n=64  min=14.31s  max=65.43s  mean=32.10s  median=29.37s  p10=20.17s  p90=48.52s
  scan/clip ratio n=64  min=0.77x  max=2.67x  mean=1.10x  median=0.99x  p10=0.92x  p90=1.12x

### Linear model: scan_time = 0.849 * clip_duration + 6.753
R-squared: 0.3909

Use this model in the time-estimation UI:
  `predicted_scan_s = 0.849 * clip_duration_s + 6.753`

| Clip length | Predicted scan time |
|-------------|---------------------|
| 15s | 19.5s |
| 20s | 23.7s |
| 25s | 28.0s |
| 30s | 32.2s |
| 45s | 45.0s |
| 60s | 57.7s |

### Optimisation insight

- Average scan overhead: 1.10x real-time (scan takes ~1.1s per 1s of clip)

## KO Position in Clip (start_ts / clip_duration)

0.0 = clip start, 1.0 = clip end. Shows where in the clip the kill tends to happen.

  relative_pos n=62  min=0.20  max=0.76  mean=0.44  median=0.43  p10=0.30  p90=0.58

### Histogram (10% buckets)
```
  0-10%           0  ..............................
  10-20%          1  #.............................
  20-30%          5  #######.......................
  30-40%         19  ############################..
  40-50%         20  ##############################
  50-60%         11  ################..............
  60-70%          5  #######.......................
  70-80%          1  #.............................
  80-90%          0  ..............................
  90-100%         0  ..............................
```

### Optimisation insight

- 90% of KOs occur within the first 58% of the clip
- Scanner can bail out early for long clips with no detection yet

## Full Entry Table

| Character | Date | Tier | start_ts | clip_dur | scan_time |
|-----------|------|------|----------|----------|-----------|
| DOCTOR_STRANGE | 2025-12-05 | DOUBLE | 9.0s | 22.4s | 21.8s |
| DOCTOR_STRANGE | 2025-12-14 | DOUBLE | 8.0s | 18.0s | 16.5s |
| DOCTOR_STRANGE | 2025-12-29 | DOUBLE | 22.0s | 36.3s | 37.9s |
| JEFF_THE_LAND_SHARK | 2025-12-29 | DOUBLE | 7.5s | 16.4s | 14.3s |
| SQUIRREL_GIRL | 2026-02-16 | TRIPLE | 13.5s | 30.6s | 29.7s |
| SQUIRREL_GIRL | 2026-02-16 | DOUBLE | 13.0s | 22.9s | 23.9s |
| SQUIRREL_GIRL | 2026-02-21 | TRIPLE | 14.5s | 28.1s | 28.6s |
| SQUIRREL_GIRL | 2026-02-28 | TRIPLE | 7.0s | 17.2s | 15.1s |
| SQUIRREL_GIRL | 2026-03-01 | DOUBLE | 14.0s | 41.9s | 45.6s |
| SQUIRREL_GIRL | 2026-03-05 | TRIPLE | 10.0s | 23.1s | 23.6s |
| SQUIRREL_GIRL | 2026-03-07 | DOUBLE | 9.0s | 31.1s | 36.1s |
| SQUIRREL_GIRL | 2026-03-13 | QUAD | 14.0s | 33.5s | 34.8s |
| SQUIRREL_GIRL | 2026-03-17 | TRIPLE | 8.5s | 27.5s | 28.0s |
| SQUIRREL_GIRL | 2026-03-17 | TRIPLE | 11.5s | 23.5s | 23.3s |
| SQUIRREL_GIRL | 2026-03-18 | TRIPLE | 13.0s | 23.3s | 22.6s |
| SQUIRREL_GIRL | 2026-03-22 | TRIPLE | 15.5s | 27.6s | 26.8s |
| SQUIRREL_GIRL | 2026-03-22 | TRIPLE | 9.5s | 21.7s | 20.2s |
| SQUIRREL_GIRL | 2026-03-26 | TRIPLE | 9.5s | 19.2s | 18.4s |
| SQUIRREL_GIRL | 2026-03-28 | QUAD | 8.5s | 42.7s | 48.6s |
| SQUIRREL_GIRL | 2026-03-30 | DOUBLE | 22.0s | 32.0s | 32.9s |
| THOR | 2026-03-05 | DOUBLE | 10.0s | 25.1s | 25.0s |
| THOR | 2026-03-05 | QUAD | 9.5s | 23.9s | 18.5s |
| THOR | 2026-03-05 | QUAD | 12.5s | 34.6s | 37.8s |
| THOR | 2026-03-07 | TRIPLE | 13.5s | 32.9s | 31.9s |
| THOR | 2026-03-07 | QUAD | 9.0s | 34.3s | 38.4s |
| THOR | 2026-03-13 | TRIPLE | 9.5s | 25.6s | 25.8s |
| THOR | 2026-03-16 | DOUBLE | 9.5s | 23.1s | 22.4s |
| THOR | 2026-03-16 | DOUBLE | 16.5s | 46.7s | 49.2s |
| THOR | 2026-03-17 | TRIPLE | 18.5s | 38.1s | 42.4s |
| THOR | 2026-03-17 | TRIPLE | 9.5s | 24.9s | 22.9s |
| THOR | 2026-03-17 | TRIPLE | 18.0s | 30.8s | 30.2s |
| THOR | 2026-03-17 | NONE | - | 18.7s | 47.1s |
| THOR | 2026-03-17 | DOUBLE | 14.5s | 40.9s | 41.3s |
| THOR | 2026-03-17 | QUAD | 17.5s | 33.8s | 34.8s |
| THOR | 2026-03-20 | DOUBLE | 16.0s | 33.9s | 34.4s |
| THOR | 2026-03-20 | TRIPLE | 10.5s | 31.9s | 32.9s |
| THOR | 2026-03-21 | DOUBLE | 11.5s | 30.1s | 29.4s |
| THOR | 2026-03-21 | TRIPLE | 9.5s | 41.4s | 45.0s |
| THOR | 2026-03-22 | TRIPLE | 17.5s | 30.7s | 28.9s |
| THOR | 2026-03-22 | DOUBLE | 26.5s | 45.9s | 48.6s |
| THOR | 2026-03-22 | DOUBLE | 22.0s | 32.0s | 29.0s |
| THOR | 2026-03-22 | KO | 8.5s | 24.9s | 65.4s |
| THOR | 2026-03-22 | TRIPLE | 9.0s | 24.4s | 23.8s |
| THOR | 2026-03-22 | TRIPLE | 8.5s | 29.2s | 28.3s |
| THOR | 2026-03-22 | TRIPLE | 15.5s | 34.2s | 33.9s |
| THOR | 2026-03-22 | TRIPLE | 15.5s | 28.1s | 27.1s |
| THOR | 2026-03-23 | TRIPLE | 18.0s | 26.5s | 27.5s |
| THOR | 2026-03-23 | DOUBLE | 33.0s | 43.3s | 48.5s |
| THOR | 2026-03-24 | TRIPLE | 10.5s | 28.9s | 27.3s |
| THOR | 2026-03-24 | TRIPLE | 10.0s | 27.1s | 27.0s |
| THOR | 2026-03-24 | DOUBLE | 16.0s | 48.4s | 52.6s |
| THOR | 2026-03-26 | DOUBLE | 25.5s | 39.0s | 40.9s |
| THOR | 2026-03-26 | TRIPLE | 17.5s | 31.2s | 29.2s |
| THOR | 2026-03-27 | KO | 10.8s | 18.5s | 49.5s |
| THOR | 2026-03-27 | DOUBLE | 10.5s | 29.3s | 29.3s |
| THOR | 2026-03-27 | KO | 9.0s | 20.1s | 19.2s |
| THOR | 2026-03-28 | KO | 14.5s | 34.5s | 32.2s |
| THOR | 2026-03-28 | NONE | - | 18.5s | 48.5s |
| THOR | 2026-03-28 | DOUBLE | 12.5s | 27.1s | 25.9s |
| THOR | 2026-03-29 | TRIPLE | 10.0s | 23.1s | 21.3s |
| THOR | 2026-03-29 | TRIPLE | 16.0s | 36.6s | 35.6s |
| THOR | 2026-03-29 | QUAD | 10.5s | 35.7s | 36.3s |
| THOR | 2026-03-29 | TRIPLE | 10.0s | 29.8s | 27.8s |
| THOR | 2026-03-29 | DOUBLE | 10.5s | 34.6s | 32.6s |

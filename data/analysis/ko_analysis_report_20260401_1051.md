# KO Scan Data Analysis

Generated: 2026-04-01 10:51 | Source: `data/cache/` | 68 total entries

---

## Overview

- Total cache entries: 68
- With KO detected: 65 (95.6%)
- Explicitly no-KO (NONE suffix): 3 (4.4%)
- Legacy null entries (no suffix, old format): 0 (0.0%)

Characters in dataset: DOCTOR_STRANGE, JEFF_THE_LAND_SHARK, SQUIRREL_GIRL, THOR

## Tier Distribution

```
  HEXA       0 (  0.0%)  ..............................
  PENTA      0 (  0.0%)  ..............................
  QUAD       7 ( 10.3%)  ######........................
  TRIPLE    32 ( 47.1%)  ##############################
  DOUBLE    22 ( 32.4%)  ####################..........
  KO         4 (  5.9%)  ###...........................
  NONE       3 (  4.4%)  ##............................
  null       0 (  0.0%)  ..............................
```

### Per character

- **DOCTOR_STRANGE** (3 clips): DOUBLE:3
- **JEFF_THE_LAND_SHARK** (1 clips): DOUBLE:1
- **SQUIRREL_GIRL** (16 clips): QUAD:2, TRIPLE:10, DOUBLE:4
- **THOR** (48 clips): QUAD:5, TRIPLE:22, DOUBLE:14, KO:4, NONE:3

## KO Event Timing (start_ts)

start_ts = timestamp of the first KO detection in the clip (seconds from clip start).

  start_ts n=65  min=7.00s  max=22.00s  mean=12.73s  median=11.50s  p10=8.50s  p90=18.00s

### Histogram (2s buckets)
```
  6-8s          2  ###...........................
  8-10s        18  ##############################
  10-12s       13  #####################.........
  12-14s        7  ###########...................
  14-16s       10  ################..............
  16-18s        7  ###########...................
  18-20s        4  ######........................
  20-22s        1  #.............................
  22-24s        3  #####.........................
```

### Percentile table

| Percentile | start_ts |
|------------|----------|
| min | 7.00s |
| p10 | 8.50s |
| p25 | 9.50s |
| p50 | 11.50s |
| p75 | 15.50s |
| p90 | 18.00s |
| max | 22.00s |

### Optimisation insight

- 90% of KO events begin before **18.0s** into the clip
- 10% of KO events begin after **8.5s** (earliest is 7.0s)
- Scanning could safely stop at ~21s (p90 + ~3s buffer for banner to fully show)
- SKIP_SECS could be raised to ~6.5s (current earliest KO minus 0.5s safety)

## KO Sequence Duration (end_ts - start_ts)

Measures how long a multi-kill event lasts from first to last KO banner.

  sequence_duration n=65  min=1.00s  max=21.25s  mean=7.41s  median=6.00s  p10=2.00s  p90=14.00s

### By tier

- **KO**:    n=4  min=1.00s  max=2.50s  mean=1.38s  median=1.00s  p10=1.00s  p90=2.50s
- **DOUBLE**:    n=22  min=1.00s  max=21.25s  mean=6.41s  median=3.25s  p10=2.00s  p90=11.50s
- **TRIPLE**:    n=32  min=1.50s  max=16.50s  mean=7.67s  median=6.25s  p10=4.00s  p90=12.50s
- **QUAD**:    n=7  min=6.50s  max=17.50s  mean=12.79s  median=13.00s  p10=6.50s  p90=17.50s

### Optimisation insight

- After detecting a KO event, skip ahead by at least 14.0s (p90 sequence duration) before resuming scan
- This avoids redundant OCR frames mid-sequence

## Kill Chain Spacing (time between consecutive kills)

For multi-kill events (DOUBLE+), the time between each kill in the chain.

  inter-kill gap n=67  min=2.00s  max=13.50s  mean=5.27s  median=4.50s  p10=2.00s  p90=9.00s

### By tier

- **DOUBLE**:    n=12  min=2.00s  max=13.50s  mean=6.96s  median=6.88s  p10=2.50s  p90=13.50s
- **TRIPLE**:    n=39  min=2.00s  max=11.00s  mean=4.79s  median=4.50s  p10=2.00s  p90=9.00s
- **QUAD**:    n=16  min=2.00s  max=10.00s  mean=5.16s  median=4.50s  p10=2.00s  p90=9.00s

### Optimisation insight

- p90 inter-kill gap = 9.00s - OCR cooldown window can be set to this safely

## Clip Duration Distribution

  clip_duration n=68  min=16.41s  max=48.43s  mean=29.98s  median=29.98s  p10=19.17s  p90=41.37s

### Histogram (5s buckets)
```
  15-20s        7  ##########....................
  20-25s       13  ###################...........
  25-30s       14  #####################.........
  30-35s       20  ##############################
  35-40s        6  #########.....................
  40-45s        5  #######.......................
  45-50s        3  ####..........................
```

### By tier

- **KO**:    n=4  min=18.49s  max=34.47s  mean=24.50s  median=22.52s  p10=18.49s  p90=34.47s
- **DOUBLE**:    n=22  min=16.41s  max=48.43s  mean=32.31s  median=31.52s  p10=22.38s  p90=45.86s
- **TRIPLE**:    n=32  min=17.21s  max=41.37s  mean=28.60s  median=28.46s  p10=23.07s  p90=35.35s
- **QUAD**:    n=7  min=23.95s  max=42.66s  mean=34.07s  median=34.33s  p10=23.95s  p90=42.66s
- **NONE**:    n=3  min=18.47s  max=38.98s  mean=25.39s  median=18.71s  p10=18.47s  p90=38.98s

## Scan Time Analysis (for time-estimation model)

  scan_time n=68  min=9.87s  max=106.18s  mean=28.92s  median=25.84s  p10=17.15s  p90=40.08s
  scan/clip ratio n=68  min=0.60x  max=2.45x  mean=0.95x  median=0.84x  p10=0.74x  p90=1.52x

### Scan Time Outliers (ratio > 1.5x)

Entries with unusually high scan times relative to clip duration.
Likely caused by system load, background processes, or cold-start effects.
Excluded from the filtered model below.

| Character | Date | Tier | clip_dur | scan_time | ratio |
|-----------|------|------|----------|-----------|-------|
| THOR | 2026-03-23 | DOUBLE | 43.3s | 105.9s | 2.45x |
| THOR | 2026-03-22 | DOUBLE | 45.9s | 106.2s | 2.32x |
| THOR | 2026-03-22 | KO | 24.9s | 51.5s | 2.07x |
| THOR | 2026-03-28 | NONE | 18.5s | 36.4s | 1.97x |
| THOR | 2026-03-27 | KO | 18.5s | 35.5s | 1.92x |
| THOR | 2026-03-17 | NONE | 18.7s | 34.6s | 1.85x |
| THOR | 2026-03-26 | NONE | 39.0s | 59.4s | 1.52x |

Filtered dataset: 61 of 68 entries (outliers removed)

### Model Comparison

| Model | Formula | R² | Dataset |
|-------|---------|-----|---------|
| Linear (all data) | 1.315x - 10.491 | 0.3765 | 68 entries |
| Linear (filtered) | 0.977x - 4.118 | 0.9010 | 61 entries |
| Power (filtered) | 0.358 * x^1.248 | 0.8854 | 61 entries |

### Recommended model

**Filtered linear model** (R²=0.9010):
  `predicted_scan_s = 0.977 * clip_duration_s - 4.118`

| Clip length | Predicted scan time |
|-------------|---------------------|
| 15s | 10.5s |
| 20s | 15.4s |
| 25s | 20.3s |
| 30s | 25.2s |
| 45s | 39.9s |
| 60s | 54.5s |

### Optimisation insights

- Average scan overhead: 0.95x real-time (scan takes ~1.0s per 1s of clip)
- Excluding outliers: 0.83x real-time

## KO Position in Clip (start_ts / clip_duration)

0.0 = clip start, 1.0 = clip end. Shows where in the clip the kill tends to happen.

  relative_pos n=65  min=0.20  max=0.69  mean=0.43  median=0.42  p10=0.30  p90=0.57

### Histogram (10% buckets)
```
  0-10%           0  ..............................
  10-20%          1  #.............................
  20-30%          5  ######........................
  30-40%         22  ##############################
  40-50%         22  ##############################
  50-60%         11  ###############...............
  60-70%          4  #####.........................
  70-80%          0  ..............................
  80-90%          0  ..............................
  90-100%         0  ..............................
```

### Optimisation insight

- 90% of KOs occur within the first 57% of the clip
- Scanner can bail out early for long clips with no detection yet

## Full Entry Table

| Character | Date | Tier | start_ts | clip_dur | scan_time |
|-----------|------|------|----------|----------|-----------|
| DOCTOR_STRANGE | 2025-12-05 | DOUBLE | 9.0s | 22.4s | 19.0s |
| DOCTOR_STRANGE | 2025-12-14 | DOUBLE | 8.0s | 18.0s | 12.9s |
| DOCTOR_STRANGE | 2025-12-29 | DOUBLE | 22.0s | 36.3s | 35.3s |
| JEFF_THE_LAND_SHARK | 2025-12-29 | DOUBLE | 7.5s | 16.4s | 9.9s |
| SQUIRREL_GIRL | 2026-02-16 | TRIPLE | 13.5s | 30.6s | 26.4s |
| SQUIRREL_GIRL | 2026-02-16 | DOUBLE | 13.0s | 22.9s | 19.4s |
| SQUIRREL_GIRL | 2026-02-21 | TRIPLE | 14.5s | 28.1s | 25.7s |
| SQUIRREL_GIRL | 2026-02-28 | TRIPLE | 7.0s | 17.2s | 11.4s |
| SQUIRREL_GIRL | 2026-03-01 | DOUBLE | 14.0s | 41.9s | 42.2s |
| SQUIRREL_GIRL | 2026-03-05 | TRIPLE | 10.0s | 23.1s | 19.3s |
| SQUIRREL_GIRL | 2026-03-07 | DOUBLE | 9.0s | 31.1s | 28.9s |
| SQUIRREL_GIRL | 2026-03-13 | QUAD | 14.0s | 33.5s | 30.1s |
| SQUIRREL_GIRL | 2026-03-17 | TRIPLE | 8.5s | 27.5s | 24.2s |
| SQUIRREL_GIRL | 2026-03-17 | TRIPLE | 11.5s | 23.5s | 19.0s |
| SQUIRREL_GIRL | 2026-03-18 | TRIPLE | 13.0s | 23.3s | 18.2s |
| SQUIRREL_GIRL | 2026-03-22 | TRIPLE | 15.5s | 27.6s | 23.4s |
| SQUIRREL_GIRL | 2026-03-22 | TRIPLE | 9.5s | 21.7s | 16.6s |
| SQUIRREL_GIRL | 2026-03-26 | TRIPLE | 9.5s | 19.2s | 14.0s |
| SQUIRREL_GIRL | 2026-03-28 | QUAD | 8.5s | 42.7s | 41.5s |
| SQUIRREL_GIRL | 2026-03-30 | DOUBLE | 22.0s | 32.0s | 27.3s |
| THOR | 2026-03-05 | DOUBLE | 10.0s | 25.1s | 19.4s |
| THOR | 2026-03-05 | QUAD | 9.5s | 23.9s | 18.3s |
| THOR | 2026-03-05 | QUAD | 12.5s | 34.6s | 31.8s |
| THOR | 2026-03-07 | TRIPLE | 13.5s | 32.9s | 27.8s |
| THOR | 2026-03-07 | QUAD | 9.0s | 34.3s | 32.8s |
| THOR | 2026-03-13 | TRIPLE | 9.5s | 25.6s | 20.5s |
| THOR | 2026-03-16 | DOUBLE | 9.5s | 23.1s | 17.1s |
| THOR | 2026-03-16 | DOUBLE | 16.5s | 46.7s | 33.8s |
| THOR | 2026-03-17 | TRIPLE | 18.5s | 38.1s | 36.0s |
| THOR | 2026-03-17 | TRIPLE | 9.5s | 24.9s | 19.0s |
| THOR | 2026-03-17 | TRIPLE | 18.0s | 30.8s | 26.8s |
| THOR | 2026-03-17 | NONE | - | 18.7s | 34.6s |
| THOR | 2026-03-17 | DOUBLE | 14.5s | 40.9s | 31.7s |
| THOR | 2026-03-17 | QUAD | 17.5s | 33.8s | 30.5s |
| THOR | 2026-03-20 | DOUBLE | 16.0s | 33.9s | 30.1s |
| THOR | 2026-03-20 | TRIPLE | 10.5s | 31.9s | 26.0s |
| THOR | 2026-03-21 | DOUBLE | 11.5s | 30.1s | 24.5s |
| THOR | 2026-03-21 | TRIPLE | 9.5s | 41.4s | 40.1s |
| THOR | 2026-03-22 | TRIPLE | 17.5s | 30.7s | 25.5s |
| THOR | 2026-03-22 | DOUBLE | 21.0s | 45.9s | 106.2s |
| THOR | 2026-03-22 | DOUBLE | 22.0s | 32.0s | 25.1s |
| THOR | 2026-03-22 | KO | 8.5s | 24.9s | 51.5s |
| THOR | 2026-03-22 | TRIPLE | 9.0s | 24.4s | 19.5s |
| THOR | 2026-03-22 | TRIPLE | 8.5s | 29.2s | 24.0s |
| THOR | 2026-03-22 | TRIPLE | 15.5s | 34.2s | 29.9s |
| THOR | 2026-03-22 | TRIPLE | 15.5s | 28.1s | 23.4s |
| THOR | 2026-03-23 | TRIPLE | 18.0s | 26.5s | 23.0s |
| THOR | 2026-03-23 | DOUBLE | 15.0s | 43.3s | 105.9s |
| THOR | 2026-03-24 | TRIPLE | 10.5s | 28.9s | 23.9s |
| THOR | 2026-03-24 | TRIPLE | 10.0s | 27.1s | 21.9s |
| THOR | 2026-03-24 | DOUBLE | 16.0s | 48.4s | 35.7s |
| THOR | 2026-03-26 | NONE | - | 39.0s | 59.4s |
| THOR | 2026-03-26 | TRIPLE | 17.5s | 31.2s | 25.4s |
| THOR | 2026-03-27 | KO | 10.8s | 18.5s | 35.5s |
| THOR | 2026-03-27 | DOUBLE | 10.5s | 29.3s | 24.7s |
| THOR | 2026-03-27 | KO | 9.0s | 20.1s | 14.8s |
| THOR | 2026-03-28 | KO | 14.5s | 34.5s | 26.4s |
| THOR | 2026-03-28 | NONE | - | 18.5s | 36.4s |
| THOR | 2026-03-28 | DOUBLE | 12.5s | 27.1s | 21.4s |
| THOR | 2026-03-29 | TRIPLE | 10.0s | 23.1s | 17.3s |
| THOR | 2026-03-29 | TRIPLE | 16.0s | 36.6s | 31.8s |
| THOR | 2026-03-29 | QUAD | 10.5s | 35.7s | 32.1s |
| THOR | 2026-03-29 | TRIPLE | 10.0s | 29.8s | 24.0s |
| THOR | 2026-03-29 | DOUBLE | 10.5s | 34.6s | 29.1s |
| THOR | 2026-03-29 | TRIPLE | 14.0s | 35.4s | 30.6s |
| THOR | 2026-03-30 | DOUBLE | 12.5s | 29.4s | 23.2s |
| THOR | 2026-03-30 | TRIPLE | 9.5s | 31.4s | 27.7s |
| THOR | 2026-03-30 | TRIPLE | 18.0s | 31.4s | 26.0s |

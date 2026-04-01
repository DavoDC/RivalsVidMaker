# KO Scan Data Analysis

Generated: 2026-04-01 23:40 | Source: `data/cache/` | 68 total entries

---

## Overview

- Total cache entries: 68
- With KO detected: 67 (98.5%)
- Explicitly no-KO (NONE suffix): 1 (1.5%)
- Legacy null entries (no suffix, old format): 0 (0.0%)

Characters in dataset: DOCTOR_STRANGE, JEFF_THE_LAND_SHARK, SQUIRREL_GIRL, THOR

## Tier Distribution

```
  HEXA       0 (  0.0%)  ..............................
  PENTA      0 (  0.0%)  ..............................
  QUAD       7 ( 10.3%)  ######........................
  TRIPLE    32 ( 47.1%)  ##############################
  DOUBLE    23 ( 33.8%)  #####################.........
  KO         5 (  7.4%)  ####..........................
  NONE       1 (  1.5%)  ..............................
  null       0 (  0.0%)  ..............................
```

### Per character

- **DOCTOR_STRANGE** (3 clips): DOUBLE:3
- **JEFF_THE_LAND_SHARK** (1 clips): DOUBLE:1
- **SQUIRREL_GIRL** (16 clips): QUAD:2, TRIPLE:10, DOUBLE:4
- **THOR** (48 clips): QUAD:5, TRIPLE:22, DOUBLE:15, KO:5, NONE:1

## KO Event Timing (start_ts)

start_ts = timestamp of the first KO detection in the clip (seconds from clip start).

  start_ts n=67  min=7.00s  max=28.75s  mean=12.96s  median=11.50s  p10=8.50s  p90=18.50s

### Histogram (2s buckets)
```
  6-8s          2  ###...........................
  8-10s        20  ##############################
  10-12s       12  ##################............
  12-14s        7  ##########....................
  14-16s        9  #############.................
  16-18s        7  ##########....................
  18-20s        5  #######.......................
  20-22s        1  #.............................
  22-24s        3  ####..........................
  28-30s        1  #.............................
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
| max | 28.75s |

### Optimisation insight

- 90% of KO events begin before **18.5s** into the clip
- 10% of KO events begin after **8.5s** (earliest is 7.0s)
- Scanning could safely stop at ~22s (p90 + ~3s buffer for banner to fully show)
- SKIP_SECS could be raised to ~6.5s (current earliest KO minus 0.5s safety)

## KO Sequence Duration (end_ts - start_ts)

Measures how long a multi-kill event lasts from first to last KO banner.

  sequence_duration n=67  min=1.00s  max=19.00s  mean=7.22s  median=6.00s  p10=2.50s  p90=13.50s

### By tier

- **KO**:    n=5  min=1.00s  max=3.12s  mean=2.35s  median=2.50s  p10=1.00s  p90=3.12s
- **DOUBLE**:    n=23  min=1.00s  max=19.00s  mean=5.97s  median=3.50s  p10=2.00s  p90=11.50s
- **TRIPLE**:    n=32  min=1.50s  max=16.50s  mean=7.67s  median=6.25s  p10=4.00s  p90=12.50s
- **QUAD**:    n=7  min=6.50s  max=17.50s  mean=12.79s  median=13.00s  p10=6.50s  p90=17.50s

### Optimisation insight

- After detecting a KO event, skip ahead by at least 13.5s (p90 sequence duration) before resuming scan
- This avoids redundant OCR frames mid-sequence

## Kill Chain Spacing (time between consecutive kills)

For multi-kill events (DOUBLE+), the time between each kill in the chain.

  inter-kill gap n=67  min=2.00s  max=13.50s  mean=5.16s  median=4.50s  p10=2.00s  p90=9.00s

### By tier

- **DOUBLE**:    n=12  min=2.00s  max=13.50s  mean=6.33s  median=6.06s  p10=2.50s  p90=9.00s
- **TRIPLE**:    n=39  min=2.00s  max=11.00s  mean=4.79s  median=4.50s  p10=2.00s  p90=9.00s
- **QUAD**:    n=16  min=2.00s  max=10.00s  mean=5.16s  median=4.50s  p10=2.00s  p90=9.00s

### Optimisation insight

- p90 inter-kill gap = 9.00s, p10 = 2.00s
- OCR COOLDOWN_SECS should stay <= p10 (2.0s) to avoid missing rapid kill chains - do NOT set to p90

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

- **KO**:    n=5  min=18.47s  max=34.47s  mean=23.34s  median=20.11s  p10=18.47s  p90=34.47s
- **DOUBLE**:    n=23  min=16.41s  max=48.43s  mean=32.60s  median=31.97s  p10=22.38s  p90=45.86s
- **TRIPLE**:    n=32  min=17.21s  max=41.37s  mean=28.60s  median=28.46s  p10=23.07s  p90=35.35s
- **QUAD**:    n=7  min=23.95s  max=42.66s  mean=34.07s  median=34.33s  p10=23.95s  p90=42.66s
- **NONE**:    n=1  min=18.49s  max=18.49s  mean=18.49s  median=18.49s  p10=18.49s  p90=18.49s

## Scan Pass Breakdown

scan_pass = which scanner pass detected the KO (1 = fast pass, 2 = fallback pass).

```
  Pass 1    61 ( 89.7%)  ##########################....
  Pass 2     7 ( 10.3%)  ###...........................
```

### By tier

| Pass | KO | DOUBLE | TRIPLE | QUAD | NONE |
|------|--------|--------|--------|--------|--------|
| 1 | 2 | 20 | 32 | 7 | 0 |
| 2 | 3 | 3 | 0 | 0 | 1 |

### Scan time by pass

- **Pass 1** (n=61):   scan_time n=61  min=9.59s  max=47.49s  mean=25.16s  median=24.80s  p10=17.08s  p90=32.93s
  - Mean scan/clip ratio: 0.83x
- **Pass 2** (n=7):   scan_time n=7  min=55.77s  max=191.39s  mean=113.89s  median=85.02s  p10=55.77s  p90=191.39s
  - Mean scan/clip ratio: 3.62x

### Optimisation insight

- Pass 1 scans at **0.83x** real-time; pass 2 at **3.62x** (4.4x slower)
- Pass 2 accounts for 7 / 68 clips (10.3%)
- All scan-time outliers are pass-2 clips - slow scan is structural, not system noise

## Scan Time Analysis (for time-estimation model)

  scan_time n=68  min=9.59s  max=191.39s  mean=34.29s  median=25.94s  p10=17.08s  p90=55.77s
  scan/clip ratio n=68  min=0.58x  max=4.33x  mean=1.11x  median=0.84x  p10=0.74x  p90=2.98x

### Scan Time Outliers (ratio > 1.5x)

Entries with unusually high scan times relative to clip duration.
Excluded from the filtered model below. All are pass-2 scans (see Scan Pass Breakdown).

| Character | Date | Tier | Pass | clip_dur | scan_time | ratio |
|-----------|------|------|------|----------|-----------|-------|
| THOR | 2026-03-23 | DOUBLE | 2 | 43.3s | 187.3s | 4.33x |
| THOR | 2026-03-22 | DOUBLE | 2 | 45.9s | 191.4s | 4.17x |
| THOR | 2026-03-26 | DOUBLE | 2 | 39.0s | 161.2s | 4.13x |
| THOR | 2026-03-22 | KO | 2 | 24.9s | 85.0s | 3.41x |
| THOR | 2026-03-28 | KO | 2 | 18.5s | 58.9s | 3.19x |
| THOR | 2026-03-27 | NONE | 2 | 18.5s | 57.7s | 3.12x |
| THOR | 2026-03-17 | KO | 2 | 18.7s | 55.8s | 2.98x |

Filtered dataset: 61 of 68 entries (outliers removed)

### Model Comparison

| Model | Formula | R² | Dataset |
|-------|---------|-----|---------|
| Linear (all data) | 1.984x - 25.188 | 0.1936 | 68 entries |
| Linear (filtered) | 1.012x - 5.199 | 0.8851 | 61 entries |
| Power (filtered) | 0.320 * x^1.280 | 0.8719 | 61 entries |

### Recommended model

**Filtered linear model** (R²=0.8851):
  `predicted_scan_s = 1.012 * clip_duration_s - 5.199`

| Clip length | Predicted scan time |
|-------------|---------------------|
| 15s | 10.0s |
| 20s | 15.0s |
| 25s | 20.1s |
| 30s | 25.2s |
| 45s | 40.3s |
| 60s | 55.5s |

### Optimisation insights

- Average scan overhead: 1.11x real-time (scan takes ~1.1s per 1s of clip)
- Excluding outliers: 0.83x real-time

## KO Position in Clip (start_ts / clip_duration)

0.0 = clip start, 1.0 = clip end. Shows where in the clip the kill tends to happen.

  relative_pos n=67  min=0.20  max=0.69  mean=0.43  median=0.43  p10=0.30  p90=0.57

### Histogram (10% buckets)
```
  0-10%           0  ..............................
  10-20%          1  #.............................
  20-30%          5  ######........................
  30-40%         21  ##########################....
  40-50%         24  ##############################
  50-60%         11  #############.................
  60-70%          5  ######........................
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
| DOCTOR_STRANGE | 2025-12-05 | DOUBLE | 9.0s | 22.4s | 17.5s |
| DOCTOR_STRANGE | 2025-12-14 | DOUBLE | 8.0s | 18.0s | 13.8s |
| DOCTOR_STRANGE | 2025-12-29 | DOUBLE | 22.0s | 36.3s | 32.8s |
| JEFF_THE_LAND_SHARK | 2025-12-29 | DOUBLE | 7.5s | 16.4s | 9.6s |
| SQUIRREL_GIRL | 2026-02-16 | TRIPLE | 13.5s | 30.6s | 25.9s |
| SQUIRREL_GIRL | 2026-02-16 | DOUBLE | 13.0s | 22.9s | 19.2s |
| SQUIRREL_GIRL | 2026-02-21 | TRIPLE | 14.5s | 28.1s | 23.8s |
| SQUIRREL_GIRL | 2026-02-28 | TRIPLE | 7.0s | 17.2s | 10.9s |
| SQUIRREL_GIRL | 2026-03-01 | DOUBLE | 14.0s | 41.9s | 41.8s |
| SQUIRREL_GIRL | 2026-03-05 | TRIPLE | 10.0s | 23.1s | 19.0s |
| SQUIRREL_GIRL | 2026-03-07 | DOUBLE | 9.0s | 31.1s | 28.7s |
| SQUIRREL_GIRL | 2026-03-13 | QUAD | 14.0s | 33.5s | 29.9s |
| SQUIRREL_GIRL | 2026-03-17 | TRIPLE | 8.5s | 27.5s | 23.5s |
| SQUIRREL_GIRL | 2026-03-17 | TRIPLE | 11.5s | 23.5s | 18.9s |
| SQUIRREL_GIRL | 2026-03-18 | TRIPLE | 13.0s | 23.3s | 18.2s |
| SQUIRREL_GIRL | 2026-03-22 | TRIPLE | 15.5s | 27.6s | 22.5s |
| SQUIRREL_GIRL | 2026-03-22 | TRIPLE | 9.5s | 21.7s | 16.1s |
| SQUIRREL_GIRL | 2026-03-26 | TRIPLE | 9.5s | 19.2s | 14.0s |
| SQUIRREL_GIRL | 2026-03-28 | QUAD | 8.5s | 42.7s | 41.6s |
| SQUIRREL_GIRL | 2026-03-30 | DOUBLE | 22.0s | 32.0s | 27.3s |
| THOR | 2026-03-05 | DOUBLE | 10.0s | 25.1s | 19.4s |
| THOR | 2026-03-05 | QUAD | 9.5s | 23.9s | 18.6s |
| THOR | 2026-03-05 | QUAD | 12.5s | 34.6s | 32.1s |
| THOR | 2026-03-07 | TRIPLE | 13.5s | 32.9s | 28.2s |
| THOR | 2026-03-07 | QUAD | 9.0s | 34.3s | 32.9s |
| THOR | 2026-03-13 | TRIPLE | 9.5s | 25.6s | 20.5s |
| THOR | 2026-03-16 | DOUBLE | 9.5s | 23.1s | 17.2s |
| THOR | 2026-03-16 | DOUBLE | 16.5s | 46.7s | 35.0s |
| THOR | 2026-03-17 | TRIPLE | 18.5s | 38.1s | 35.6s |
| THOR | 2026-03-17 | TRIPLE | 9.5s | 24.9s | 18.8s |
| THOR | 2026-03-17 | TRIPLE | 18.0s | 30.8s | 26.7s |
| THOR | 2026-03-17 | KO | 8.4s | 18.7s | 55.8s |
| THOR | 2026-03-17 | DOUBLE | 14.5s | 40.9s | 31.3s |
| THOR | 2026-03-17 | QUAD | 17.5s | 33.8s | 30.1s |
| THOR | 2026-03-20 | DOUBLE | 16.0s | 33.9s | 29.7s |
| THOR | 2026-03-20 | TRIPLE | 10.5s | 31.9s | 26.9s |
| THOR | 2026-03-21 | DOUBLE | 11.5s | 30.1s | 27.5s |
| THOR | 2026-03-21 | TRIPLE | 9.5s | 41.4s | 47.5s |
| THOR | 2026-03-22 | TRIPLE | 17.5s | 30.7s | 26.4s |
| THOR | 2026-03-22 | DOUBLE | 21.8s | 45.9s | 191.4s |
| THOR | 2026-03-22 | DOUBLE | 22.0s | 32.0s | 24.8s |
| THOR | 2026-03-22 | KO | 9.2s | 24.9s | 85.0s |
| THOR | 2026-03-22 | TRIPLE | 9.0s | 24.4s | 19.3s |
| THOR | 2026-03-22 | TRIPLE | 8.5s | 29.2s | 23.7s |
| THOR | 2026-03-22 | TRIPLE | 15.5s | 34.2s | 29.6s |
| THOR | 2026-03-22 | TRIPLE | 15.5s | 28.1s | 23.1s |
| THOR | 2026-03-23 | TRIPLE | 18.0s | 26.5s | 22.8s |
| THOR | 2026-03-23 | DOUBLE | 28.8s | 43.3s | 187.3s |
| THOR | 2026-03-24 | TRIPLE | 10.5s | 28.9s | 23.7s |
| THOR | 2026-03-24 | TRIPLE | 10.0s | 27.1s | 21.6s |
| THOR | 2026-03-24 | DOUBLE | 16.0s | 48.4s | 35.3s |
| THOR | 2026-03-26 | DOUBLE | 18.5s | 39.0s | 161.2s |
| THOR | 2026-03-26 | TRIPLE | 17.5s | 31.2s | 25.2s |
| THOR | 2026-03-27 | NONE | - | 18.5s | 57.7s |
| THOR | 2026-03-27 | DOUBLE | 10.5s | 29.3s | 24.4s |
| THOR | 2026-03-27 | KO | 9.0s | 20.1s | 14.7s |
| THOR | 2026-03-28 | KO | 14.5s | 34.5s | 26.0s |
| THOR | 2026-03-28 | KO | 9.2s | 18.5s | 58.9s |
| THOR | 2026-03-28 | DOUBLE | 12.5s | 27.1s | 21.2s |
| THOR | 2026-03-29 | TRIPLE | 10.0s | 23.1s | 17.1s |
| THOR | 2026-03-29 | TRIPLE | 16.0s | 36.6s | 31.6s |
| THOR | 2026-03-29 | QUAD | 10.5s | 35.7s | 31.8s |
| THOR | 2026-03-29 | TRIPLE | 10.0s | 29.8s | 23.8s |
| THOR | 2026-03-29 | DOUBLE | 10.5s | 34.6s | 28.9s |
| THOR | 2026-03-29 | TRIPLE | 14.0s | 35.4s | 30.4s |
| THOR | 2026-03-30 | DOUBLE | 12.5s | 29.4s | 23.1s |
| THOR | 2026-03-30 | TRIPLE | 9.5s | 31.4s | 27.5s |
| THOR | 2026-03-30 | TRIPLE | 18.0s | 31.4s | 25.8s |

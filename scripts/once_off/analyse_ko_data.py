"""
analyse_ko_data.py - One-off statistical analysis of all KO scan cache data.

Reads every .ko.json in data/cache/, computes stats across all fields, and
writes a report to data/analysis/ko_analysis_report.md.

Usage:
    python scripts/analyse_ko_data.py
"""

import json
import math
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from datetime import datetime

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CACHE_DIR = REPO_ROOT / "data" / "cache"
OUTPUT_DIR = REPO_ROOT / "data" / "analysis"

# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_all_cache_entries():
    """
    Returns a list of dicts, one per .ko.json file.
    Each dict has all JSON fields plus:
      - 'character': hero name from directory (e.g. 'THOR')
      - 'filename': the .ko.json filename stem (without extension)
      - 'path': Path object
    """
    records = []
    for json_path in sorted(CACHE_DIR.rglob("*.ko.json")):
        # Character is the top-level folder under data/cache/
        try:
            rel = json_path.relative_to(CACHE_DIR)
            character = rel.parts[0]  # e.g. THOR, SQUIRREL_GIRL
        except ValueError:
            character = "UNKNOWN"

        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            print(f"  WARN: could not read {json_path}: {e}")
            continue

        data["character"] = character
        data["filename"] = json_path.stem
        data["path"] = json_path
        # Normalise tier: _null_result entries (NONE suffix) have no tier field
        if data.get("_null_result") and "tier" not in data:
            data["tier"] = "NONE"
        records.append(data)

    return records


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TIER_ORDER = ["KO", "DOUBLE", "TRIPLE", "QUAD", "PENTA", "HEXA", "NONE"]

def pct(n, total):
    return f"{100 * n / total:.1f}%" if total else "n/a"

def stats_block(values, label="", unit="s"):
    """Return a compact stats string for a list of floats."""
    if not values:
        return f"  {label}: no data"
    n = len(values)
    s = sorted(values)
    mean = sum(s) / n
    median = s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2
    p10 = s[int(n * 0.10)]
    p90 = s[int(n * 0.90)]
    return (
        f"  {label} n={n}  "
        f"min={s[0]:.2f}{unit}  max={s[-1]:.2f}{unit}  "
        f"mean={mean:.2f}{unit}  median={median:.2f}{unit}  "
        f"p10={p10:.2f}{unit}  p90={p90:.2f}{unit}"
    )

def linear_regression(xs, ys):
    """Returns (slope, intercept) for simple linear regression."""
    n = len(xs)
    if n < 2:
        return None, None
    sx = sum(xs)
    sy = sum(ys)
    sxx = sum(x * x for x in xs)
    sxy = sum(x * y for x, y in zip(xs, ys))
    denom = n * sxx - sx * sx
    if denom == 0:
        return None, None
    slope = (n * sxy - sx * sy) / denom
    intercept = (sy - slope * sx) / n
    return slope, intercept

def r_squared(xs, ys, slope, intercept):
    if slope is None:
        return None
    mean_y = sum(ys) / len(ys)
    ss_tot = sum((y - mean_y) ** 2 for y in ys)
    ss_res = sum((y - (slope * x + intercept)) ** 2 for x, y in zip(xs, ys))
    if ss_tot == 0:
        return 1.0
    return 1 - ss_res / ss_tot

def power_regression(xs, ys):
    """Fits y = a * x^b via log-linear regression. Returns (a, b) or (None, None)."""
    pairs = [(x, y) for x, y in zip(xs, ys) if x > 0 and y > 0]
    if len(pairs) < 2:
        return None, None
    log_xs = [math.log(x) for x, _ in pairs]
    log_ys = [math.log(y) for _, y in pairs]
    b, log_a = linear_regression(log_xs, log_ys)
    if b is None:
        return None, None
    return math.exp(log_a), b

def r_squared_power(xs, ys, a, b):
    """R² for y = a * x^b."""
    if a is None:
        return None
    pairs = [(x, y) for x, y in zip(xs, ys) if x > 0 and y > 0]
    ys_f = [y for _, y in pairs]
    predicted = [a * (x ** b) for x, _ in pairs]
    mean_y = sum(ys_f) / len(ys_f)
    ss_tot = sum((y - mean_y) ** 2 for y in ys_f)
    ss_res = sum((y - p) ** 2 for y, p in zip(ys_f, predicted))
    if ss_tot == 0:
        return 1.0
    return 1 - ss_res / ss_tot

def bucket_histogram(values, bucket_size=5, max_val=60):
    """Returns a list of (bucket_label, count) for a histogram."""
    buckets = defaultdict(int)
    for v in values:
        b = int(v // bucket_size) * bucket_size
        b = min(b, max_val - bucket_size)
        buckets[b] += 1
    result = []
    for b in range(0, max_val, bucket_size):
        label = f"{b}-{b + bucket_size}s"
        result.append((label, buckets[b]))
    return result

def bar(count, max_count, width=30):
    if max_count == 0:
        return ""
    filled = int(width * count / max_count)
    return "#" * filled + "." * (width - filled)


# ---------------------------------------------------------------------------
# Analysis sections
# ---------------------------------------------------------------------------

def section_overview(records, lines):
    total = len(records)
    has_tier = [r for r in records if r.get("tier") not in (None, "NONE")]
    null_tier = [r for r in records if r.get("tier") is None]
    none_tier = [r for r in records if r.get("tier") == "NONE"]
    lines.append("## Overview")
    lines.append(f"")
    lines.append(f"- Total cache entries: {total}")
    lines.append(f"- With KO detected: {len(has_tier)} ({pct(len(has_tier), total)})")
    lines.append(f"- Explicitly no-KO (NONE suffix): {len(none_tier)} ({pct(len(none_tier), total)})")
    lines.append(f"- Legacy null entries (no suffix, old format): {len(null_tier)} ({pct(len(null_tier), total)})")
    lines.append(f"")
    chars = sorted(set(r["character"] for r in records))
    lines.append(f"Characters in dataset: {', '.join(chars)}")
    lines.append(f"")


def section_tier_dist(records, lines):
    lines.append("## Tier Distribution")
    lines.append("")
    tiers = [r.get("tier") if r.get("tier") is not None else "null" for r in records]
    c = Counter(tiers)
    total = len(records)
    order = ["HEXA", "PENTA", "QUAD", "TRIPLE", "DOUBLE", "KO", "NONE", "null"]
    max_count = max(c.values()) if c else 1
    lines.append("```")
    for t in order:
        count = c.get(t, 0)
        lines.append(f"  {t:<8} {count:>3} ({pct(count, total):>6})  {bar(count, max_count)}")
    lines.append("```")
    lines.append("")
    # Per-character breakdown
    lines.append("### Per character")
    lines.append("")
    chars = sorted(set(r["character"] for r in records))
    for char in chars:
        char_recs = [r for r in records if r["character"] == char]
        char_tiers = Counter(r.get("tier") if r.get("tier") is not None else "null" for r in char_recs)
        parts = [f"{t}:{char_tiers.get(t,0)}" for t in order if char_tiers.get(t, 0) > 0]
        lines.append(f"- **{char}** ({len(char_recs)} clips): {', '.join(parts)}")
    lines.append("")


def section_ko_timing(records, lines):
    """When in the clip do KO events occur?"""
    lines.append("## KO Event Timing (start_ts)")
    lines.append("")
    lines.append("start_ts = timestamp of the first KO detection in the clip (seconds from clip start).")
    lines.append("")

    ko_recs = [r for r in records if r.get("tier") not in (None, "NONE") and "start_ts" in r]
    if not ko_recs:
        lines.append("No data.")
        return

    start_ts_vals = [r["start_ts"] for r in ko_recs]
    lines.append(stats_block(start_ts_vals, "start_ts"))
    lines.append("")

    # Histogram
    hist = bucket_histogram(start_ts_vals, bucket_size=2, max_val=30)
    max_count = max((v for _, v in hist), default=1)
    lines.append("### Histogram (2s buckets)")
    lines.append("```")
    for label, count in hist:
        if count:
            lines.append(f"  {label:<10}  {count:>3}  {bar(count, max_count)}")
    lines.append("```")
    lines.append("")

    # Percentile table
    s = sorted(start_ts_vals)
    n = len(s)
    p = lambda pct_val: s[min(int(n * pct_val), n - 1)]
    lines.append("### Percentile table")
    lines.append("")
    lines.append("| Percentile | start_ts |")
    lines.append("|------------|----------|")
    for pct_val, label in [(0.0, "min"), (0.1, "p10"), (0.25, "p25"), (0.5, "p50"), (0.75, "p75"), (0.9, "p90"), (1.0, "max")]:
        lines.append(f"| {label} | {p(pct_val):.2f}s |")
    lines.append("")

    # Optimisation insight
    p10_val = p(0.10)
    p90_val = p(0.90)
    lines.append("### Optimisation insight")
    lines.append(f"")
    lines.append(f"- 90% of KO events begin before **{p90_val:.1f}s** into the clip")
    lines.append(f"- 10% of KO events begin after **{p10_val:.1f}s** (earliest is {s[0]:.1f}s)")
    lines.append(f"- Scanning could safely stop at ~{p90_val + 3:.0f}s (p90 + ~3s buffer for banner to fully show)")
    if s[0] > 2:
        lines.append(f"- SKIP_SECS could be raised to ~{s[0] - 0.5:.1f}s (current earliest KO minus 0.5s safety)")
    lines.append("")


def section_kill_duration(records, lines):
    """How long does the KO event sequence last?"""
    lines.append("## KO Sequence Duration (end_ts - start_ts)")
    lines.append("")
    lines.append("Measures how long a multi-kill event lasts from first to last KO banner.")
    lines.append("")

    ko_recs = [r for r in records
               if r.get("tier") not in (None, "NONE")
               and "start_ts" in r and "end_ts" in r]
    if not ko_recs:
        lines.append("No data.")
        return

    durations = [r["end_ts"] - r["start_ts"] for r in ko_recs]
    lines.append(stats_block(durations, "sequence_duration"))
    lines.append("")
    lines.append("### By tier")
    lines.append("")
    for tier in ["KO", "DOUBLE", "TRIPLE", "QUAD"]:
        tier_recs = [r for r in ko_recs if r.get("tier") == tier]
        if not tier_recs:
            continue
        d = [r["end_ts"] - r["start_ts"] for r in tier_recs]
        lines.append(f"- **{tier}**: {stats_block(d, '')}")
    lines.append("")
    lines.append("### Optimisation insight")
    lines.append("")
    s = sorted(durations)
    n = len(s)
    p90 = s[min(int(n * 0.90), n - 1)]
    lines.append(f"- After detecting a KO event, skip ahead by at least {p90:.1f}s (p90 sequence duration) before resuming scan")
    lines.append(f"- This avoids redundant OCR frames mid-sequence")
    lines.append("")


def section_inter_event_spacing(records, lines):
    """Time between consecutive kills within a multi-kill."""
    lines.append("## Kill Chain Spacing (time between consecutive kills)")
    lines.append("")
    lines.append("For multi-kill events (DOUBLE+), the time between each kill in the chain.")
    lines.append("")

    gaps = []
    by_tier = defaultdict(list)
    for r in records:
        events = r.get("events", [])
        if len(events) < 2:
            continue
        tier = r.get("tier", "")
        for i in range(1, len(events)):
            gap = events[i]["ts"] - events[i - 1]["ts"]
            gaps.append(gap)
            by_tier[tier].append(gap)

    if not gaps:
        lines.append("No multi-kill events found.")
        return

    lines.append(stats_block(gaps, "inter-kill gap"))
    lines.append("")
    lines.append("### By tier")
    lines.append("")
    for tier in ["DOUBLE", "TRIPLE", "QUAD"]:
        d = by_tier.get(tier, [])
        if not d:
            continue
        lines.append(f"- **{tier}**: {stats_block(d, '')}")
    lines.append("")
    lines.append("### Optimisation insight")
    lines.append("")
    s = sorted(gaps)
    n = len(s)
    p90 = s[min(int(n * 0.90), n - 1)]
    lines.append(f"- p90 inter-kill gap = {p90:.2f}s - OCR cooldown window can be set to this safely")
    lines.append("")


def section_clip_duration(records, lines):
    """Clip length distribution."""
    lines.append("## Clip Duration Distribution")
    lines.append("")
    dur_recs = [r for r in records if "clip_duration" in r]
    if not dur_recs:
        lines.append("No clip_duration data (only new-format entries have this field).")
        return

    durations = [r["clip_duration"] for r in dur_recs]
    lines.append(stats_block(durations, "clip_duration"))
    lines.append("")
    hist = bucket_histogram(durations, bucket_size=5, max_val=120)
    max_count = max(v for _, v in hist)
    lines.append("### Histogram (5s buckets)")
    lines.append("```")
    for label, count in hist:
        if count:
            lines.append(f"  {label:<10}  {count:>3}  {bar(count, max_count)}")
    lines.append("```")
    lines.append("")
    lines.append("### By tier")
    lines.append("")
    for tier in ["KO", "DOUBLE", "TRIPLE", "QUAD", "NONE"]:
        t_recs = [r for r in dur_recs if r.get("tier") == tier]
        if not t_recs:
            continue
        d = [r["clip_duration"] for r in t_recs]
        lines.append(f"- **{tier}**: {stats_block(d, '')}")
    lines.append("")


def section_scan_time(records, lines):
    """Scan performance and time-estimation model."""
    lines.append("## Scan Time Analysis (for time-estimation model)")
    lines.append("")
    st_recs = [r for r in records if "scan_time" in r and "clip_duration" in r]
    if not st_recs:
        lines.append("No scan_time/clip_duration data yet.")
        return

    scan_times = [r["scan_time"] for r in st_recs]
    clip_durs = [r["clip_duration"] for r in st_recs]
    ratios = [st / cd for st, cd in zip(scan_times, clip_durs) if cd > 0]

    lines.append(stats_block(scan_times, "scan_time"))
    lines.append(stats_block(ratios, "scan/clip ratio", unit="x"))
    lines.append("")

    # --- Outlier detection ---
    OUTLIER_RATIO = 1.5  # flag if scan_time > 1.5x clip_duration
    outliers = [
        (r, r["scan_time"] / r["clip_duration"])
        for r in st_recs
        if r["clip_duration"] > 0 and r["scan_time"] / r["clip_duration"] > OUTLIER_RATIO
    ]
    clean_recs = [
        r for r in st_recs
        if r["clip_duration"] > 0 and r["scan_time"] / r["clip_duration"] <= OUTLIER_RATIO
    ]

    if outliers:
        lines.append(f"### Scan Time Outliers (ratio > {OUTLIER_RATIO}x)")
        lines.append("")
        lines.append("Entries with unusually high scan times relative to clip duration.")
        lines.append("Likely caused by system load, background processes, or cold-start effects.")
        lines.append("Excluded from the filtered model below.")
        lines.append("")
        lines.append("| Character | Date | Tier | clip_dur | scan_time | ratio |")
        lines.append("|-----------|------|------|----------|-----------|-------|")
        for r, ratio in sorted(outliers, key=lambda x: -x[1]):
            fn = r["filename"]
            m = re.search(r"(\d{4}-\d{2}-\d{2})", fn)
            date = m.group(1) if m else "?"
            lines.append(
                f"| {r['character']} | {date} | {r.get('tier','?')} "
                f"| {r['clip_duration']:.1f}s | {r['scan_time']:.1f}s | {ratio:.2f}x |"
            )
        lines.append("")
        lines.append(f"Filtered dataset: {len(clean_recs)} of {len(st_recs)} entries (outliers removed)")
        lines.append("")

    # --- Model comparison ---
    lines.append("### Model Comparison")
    lines.append("")

    # 1. Raw linear
    slope_raw, intercept_raw = linear_regression(clip_durs, scan_times)
    r2_raw = r_squared(clip_durs, scan_times, slope_raw, intercept_raw)

    # 2. Filtered linear
    if clean_recs:
        clean_xs = [r["clip_duration"] for r in clean_recs]
        clean_ys = [r["scan_time"] for r in clean_recs]
        slope_flt, intercept_flt = linear_regression(clean_xs, clean_ys)
        r2_flt = r_squared(clean_xs, clean_ys, slope_flt, intercept_flt)
    else:
        clean_xs, clean_ys = clip_durs, scan_times
        slope_flt, intercept_flt, r2_flt = slope_raw, intercept_raw, r2_raw

    # 3. Power model on filtered data
    a_pow, b_pow = power_regression(clean_xs, clean_ys)
    r2_pow = r_squared_power(clean_xs, clean_ys, a_pow, b_pow)

    lines.append("| Model | Formula | R² | Dataset |")
    lines.append("|-------|---------|-----|---------|")
    if slope_raw is not None:
        sign = "+" if intercept_raw >= 0 else "-"
        lines.append(
            f"| Linear (all data) | {slope_raw:.3f}x {sign} {abs(intercept_raw):.3f} "
            f"| {r2_raw:.4f} | {len(st_recs)} entries |"
        )
    if slope_flt is not None and clean_recs:
        sign = "+" if intercept_flt >= 0 else "-"
        lines.append(
            f"| Linear (filtered) | {slope_flt:.3f}x {sign} {abs(intercept_flt):.3f} "
            f"| {r2_flt:.4f} | {len(clean_recs)} entries |"
        )
    if a_pow is not None:
        lines.append(
            f"| Power (filtered) | {a_pow:.3f} * x^{b_pow:.3f} "
            f"| {r2_pow:.4f} | {len(clean_recs)} entries |"
        )
    lines.append("")

    # Pick best model
    candidates = []
    if slope_flt is not None and r2_flt is not None:
        candidates.append(("filtered_linear", r2_flt))
    if r2_pow is not None:
        candidates.append(("power", r2_pow))
    best_model = max(candidates, key=lambda x: x[1])[0] if candidates else "raw_linear"

    lines.append("### Recommended model")
    lines.append("")
    if best_model == "power" and a_pow is not None:
        lines.append(f"**Power model** has best fit (R²={r2_pow:.4f}):")
        lines.append(f"  `predicted_scan_s = {a_pow:.3f} * clip_duration_s ^ {b_pow:.3f}`")
        lines.append("")
        lines.append("| Clip length | Predicted scan time |")
        lines.append("|-------------|---------------------|")
        for cl in [15, 20, 25, 30, 45, 60]:
            pred = a_pow * (cl ** b_pow)
            lines.append(f"| {cl}s | {pred:.1f}s |")
    elif slope_flt is not None:
        sign = "+" if intercept_flt >= 0 else "-"
        lines.append(f"**Filtered linear model** (R²={r2_flt:.4f}):")
        lines.append(f"  `predicted_scan_s = {slope_flt:.3f} * clip_duration_s {sign} {abs(intercept_flt):.3f}`")
        lines.append("")
        lines.append("| Clip length | Predicted scan time |")
        lines.append("|-------------|---------------------|")
        for cl in [15, 20, 25, 30, 45, 60]:
            pred = slope_flt * cl + intercept_flt
            lines.append(f"| {cl}s | {pred:.1f}s |")
    lines.append("")

    lines.append("### Optimisation insights")
    lines.append("")
    mean_ratio = sum(ratios) / len(ratios) if ratios else 0
    lines.append(f"- Average scan overhead: {mean_ratio:.2f}x real-time (scan takes ~{mean_ratio:.1f}s per 1s of clip)")
    if outliers:
        clean_ratios = [r["scan_time"] / r["clip_duration"] for r in clean_recs if r["clip_duration"] > 0]
        if clean_ratios:
            mean_clean = sum(clean_ratios) / len(clean_ratios)
            lines.append(f"- Excluding outliers: {mean_clean:.2f}x real-time")
    lines.append("")


def section_start_ts_relative(records, lines):
    """start_ts as fraction of clip_duration - when in the clip (relative) does the KO happen?"""
    lines.append("## KO Position in Clip (start_ts / clip_duration)")
    lines.append("")
    lines.append("0.0 = clip start, 1.0 = clip end. Shows where in the clip the kill tends to happen.")
    lines.append("")

    recs = [r for r in records
            if r.get("tier") not in (None, "NONE")
            and "start_ts" in r and "clip_duration" in r
            and r["clip_duration"] > 0]
    if not recs:
        lines.append("No data.")
        return

    rel_pos = [r["start_ts"] / r["clip_duration"] for r in recs]
    lines.append(stats_block(rel_pos, "relative_pos", unit=""))
    lines.append("")
    hist = bucket_histogram([v * 100 for v in rel_pos], bucket_size=10, max_val=100)
    max_count = max(v for _, v in hist)
    lines.append("### Histogram (10% buckets)")
    lines.append("```")
    for i, (_, count) in enumerate(hist):
        label = f"{i*10}-{(i+1)*10}%"
        lines.append(f"  {label:<12}  {count:>3}  {bar(count, max_count)}")
    lines.append("```")
    lines.append("")
    s = sorted(rel_pos)
    n = len(s)
    p90 = s[min(int(n * 0.90), n - 1)]
    lines.append(f"### Optimisation insight")
    lines.append(f"")
    lines.append(f"- 90% of KOs occur within the first {p90 * 100:.0f}% of the clip")
    lines.append(f"- Scanner can bail out early for long clips with no detection yet")
    lines.append("")


def section_raw_summary(records, lines):
    """Full table of all entries for reference."""
    lines.append("## Full Entry Table")
    lines.append("")
    lines.append("| Character | Date | Tier | start_ts | clip_dur | scan_time |")
    lines.append("|-----------|------|------|----------|----------|-----------|")
    for r in sorted(records, key=lambda x: (x["character"], x["filename"])):
        # Extract date from filename (e.g. THOR_2026-03-05_...)
        fn = r["filename"]
        m = re.search(r"(\d{4}-\d{2}-\d{2})", fn)
        date = m.group(1) if m else "?"
        tier = r.get("tier") or "null"
        start = f"{r['start_ts']:.1f}s" if "start_ts" in r else "-"
        clip = f"{r['clip_duration']:.1f}s" if "clip_duration" in r else "-"
        scan = f"{r['scan_time']:.1f}s" if "scan_time" in r else "-"
        lines.append(f"| {r['character']} | {date} | {tier} | {start} | {clip} | {scan} |")
    lines.append("")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("Loading KO cache entries...")
    records = load_all_cache_entries()
    print(f"  {len(records)} entries found")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    now_dt = datetime.now()
    stamp = now_dt.strftime("%Y%m%d_%H%M")
    output_file = OUTPUT_DIR / f"ko_analysis_report_{stamp}.md"

    lines = []
    now = now_dt.strftime("%Y-%m-%d %H:%M")
    lines.append(f"# KO Scan Data Analysis")
    lines.append(f"")
    lines.append(f"Generated: {now} | Source: `data/cache/` | {len(records)} total entries")
    lines.append(f"")
    lines.append("---")
    lines.append("")

    section_overview(records, lines)
    section_tier_dist(records, lines)
    section_ko_timing(records, lines)
    section_kill_duration(records, lines)
    section_inter_event_spacing(records, lines)
    section_clip_duration(records, lines)
    section_scan_time(records, lines)
    section_start_ts_relative(records, lines)
    section_raw_summary(records, lines)

    report = "\n".join(lines)
    output_file.write_text(report, encoding="utf-8")
    print(f"Report saved to: {output_file}")
    print()
    # Also print key stats to terminal
    print("=== KEY FINDINGS ===")
    ko_recs = [r for r in records if r.get("tier") not in (None, "NONE")]
    print(f"KO-detected clips: {len(ko_recs)} / {len(records)}")
    if ko_recs:
        ts_vals = [r["start_ts"] for r in ko_recs if "start_ts" in r]
        if ts_vals:
            print(f"start_ts range: {min(ts_vals):.1f}s - {max(ts_vals):.1f}s  mean={sum(ts_vals)/len(ts_vals):.1f}s")
    st_recs = [r for r in records if "scan_time" in r and "clip_duration" in r]
    if st_recs:
        slope, intercept = linear_regression(
            [r["clip_duration"] for r in st_recs],
            [r["scan_time"] for r in st_recs]
        )
        if slope is not None:
            print(f"Scan time model: {slope:.3f} * clip_duration + {intercept:.3f}")


if __name__ == "__main__":
    main()

"""
ko_streaks.py - Pure helpers over a KO detection timeline (no I/O, no OCR, no ffmpeg).

build_streaks groups banner events into multi-kill streaks. pick_boundaries chooses clip
boundaries from scene-change peaks without ever cutting through a streak.

Events are the dicts scan_video returns ({"ts": seconds, "tier": "KO".."HEXA"}); plain
(seconds, tier) tuples are accepted too.
"""

TIERS = ["KO", "DOUBLE", "TRIPLE", "QUAD", "PENTA", "HEXA"]
_RANK = {t: i for i, t in enumerate(TIERS)}

# A streak survives gaps like Triple then Quad 17 s later (docs/MULTIKILL_DETECTION.md).
MAX_STREAK_GAP_SECS = 25.0
MIN_BOUNDARY_SPACING_SECS = 8.0


def _norm(event) -> dict:
    if isinstance(event, dict):
        return {"ts": float(event["ts"]), "tier": event["tier"]}
    ts, tier = event
    return {"ts": float(ts), "tier": tier}


def build_streaks(events, max_gap: float = MAX_STREAK_GAP_SECS) -> list[dict]:
    """
    Group events into streaks. A streak continues while the next event has a strictly
    higher tier and starts at most max_gap seconds after the previous event. An equal or
    lower tier (a KO after a Quad) or a longer gap starts a new streak. Skipped
    intermediate tiers are fine.

    Each streak: {"tier": highest tier, "start_ts": first event, "max_ts": when the
    highest tier first appeared, "end_ts": last event time, "events": [...]}.
    """
    ordered = sorted((_norm(e) for e in events), key=lambda e: e["ts"])
    streaks: list[dict] = []
    for ev in ordered:
        cur = streaks[-1] if streaks else None
        if (
            cur is not None
            and _RANK.get(ev["tier"], -1) > _RANK.get(cur["tier"], -1)
            and ev["ts"] - cur["end_ts"] <= max_gap
        ):
            cur["events"].append(ev)
            cur["tier"] = ev["tier"]
            cur["max_ts"] = ev["ts"]
            cur["end_ts"] = ev["ts"]
        else:
            streaks.append({
                "tier": ev["tier"], "start_ts": ev["ts"], "max_ts": ev["ts"],
                "end_ts": ev["ts"], "events": [ev],
            })
    return streaks


def pick_boundaries(
    peaks,
    n_segments: int,
    streaks,
    min_spacing: float = MIN_BOUNDARY_SPACING_SECS,
    pad: float = 0.0,
):
    """
    Choose the n_segments-1 strongest scene-change peaks as clip boundaries.

    peaks: iterable of (seconds, score). A peak strictly inside a streak (start_ts <
    t <= end_ts + pad) is never a boundary, and chosen boundaries are at least
    min_spacing apart (stronger peaks win). Returns (sorted boundary times, confidence)
    where confidence is the weakest chosen score divided by the best rejected-or-unused
    score: 0.0 if fewer than n_segments-1 boundaries exist, None if there are none to
    choose or no runner-up.
    """
    need = n_segments - 1
    if need <= 0:
        return [], None
    spans = [(s["start_ts"], s["end_ts"] + pad) for s in streaks]
    chosen: list[tuple[float, float]] = []
    runner_up = None
    for t, score in sorted(peaks, key=lambda p: (-p[1], p[0])):
        if any(lo < t <= hi for lo, hi in spans):
            continue
        if any(abs(t - c[0]) < min_spacing for c in chosen):
            continue
        if len(chosen) < need:
            chosen.append((t, score))
        elif runner_up is None:
            runner_up = score
            break
    boundaries = sorted(t for t, _ in chosen)
    if len(chosen) < need:
        return boundaries, 0.0
    if runner_up is None:
        return boundaries, None
    weakest = min(score for _, score in chosen)
    return boundaries, (weakest / runner_up if runner_up else None)

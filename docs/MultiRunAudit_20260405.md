# RivalsVidMaker - Multi-Run Batch Correctness Audit
**Date:** 2026-04-05

Scope: correctness when the pipeline runs twice in sequence (batch 1 completes + process exits, then batch 2 runs).

---

## Issue 1 - Partial encode silently re-used (HIGH)
**File:** `src/encoder.py:49-52`

If run 1 is interrupted mid-encode (FFmpeg killed, power loss, etc.), the `.mp4` exists but is incomplete/corrupt. Run 2 sees the file, assumes it's complete, and returns it without re-encoding.

```python
if out_path.exists() and not force:
    logging.warning("Output already exists: %s. Use --force to re-encode.", out_path)
    return out_path  # Returns corrupt file silently
```

**Fix:** Delete the output file before encoding starts (encoder already has a `finally` block that cleans the concat list - same pattern applies here). Alternatively, write to a `.tmp` path and rename atomically on success. Simplest fix:

```python
# Before the subprocess.run call, delete any pre-existing file
# so a partial run never leaves a "valid-looking" output.
out_path.unlink(missing_ok=True)
result = subprocess.run(cmd, ...)
```

This makes the encode idempotent: any interrupted run leaves no output, so run 2 always re-encodes cleanly.

---

## Issue 2 - Non-atomic state.json write (MEDIUM)
**File:** `src/state.py:39-42`

```python
def save(state: dict, state_path: Path) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
```

If the process crashes mid-write, `state.json` is partially written and corrupted. Run 2's `load()` catches the `JSONDecodeError` and returns empty state - all YouTube confirmations are lost.

**Fix:** Write to a `.tmp` then rename (atomic on Windows NTFS):

```python
def save(state: dict, state_path: Path) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = state_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    tmp.replace(state_path)
```

---

## Issue 3 - Relative temp path in dedup (LOW-MEDIUM)
**File:** `src/dedup.py:72` and `src/dedup.py:121`

```python
base = Path(tmp_dir) if tmp_dir else Path("data/dedup_tmp")
```

`data/dedup_tmp` is relative to CWD. If the process is ever launched from a different working directory (e.g., running `python src/main.py` from outside the project root), temp frames land in the wrong place. The path is used in two functions (`fingerprint_clip` and `find_duplicates`).

**Fix:** The caller in `pipeline.py` should pass an absolute path derived from `config`. Quick fix in `pipeline.py`:

```python
dedup.find_duplicates(clips, config.ffmpeg, tmp_dir=config.cache_dir / "dedup_tmp")
```

---

## Not a real issue - ko_detect.py globals
The subagent flagged module-level globals in `ko_detect.configure()`. These only matter if the pipeline runs in-process across batches without reimporting - which doesn't happen (process exits between batches). Not worth addressing now.

---

## Not a real issue - dedup exception cleanup
The subagent suggested the `shutil.rmtree` at dedup.py:151 could be skipped on exception. It cannot - all exceptions inside `_fingerprint_one` are caught at line 143 and converted to log warnings + empty hashes. The rmtree always runs. No fix needed.

---

## Test gaps

No tests currently cover multi-run scenarios. Suggested additions for `tests/test_multi_run_correctness.py`:

```python
def test_encode_reraises_if_partial_output_exists(tmp_path, ...):
    """Confirm run 2 does NOT silently return a partially-encoded file."""

def test_encode_skips_cleanly_when_valid_output_exists(tmp_path, ...):
    """Confirm run 2 skips encoding when run 1 fully succeeded."""

def test_state_atomic_write_survives_partial_crash(tmp_path):
    """Simulate crash mid-write; verify load() on run 2 still gets last good state."""

def test_state_roundtrip_preserves_youtube_confirmed(tmp_path):
    """save -> load -> save -> load cycle; confirmed flag must persist."""
```

---

## Issue 4 - Run 2 batch slug loses its number (HIGH)
**File:** `src/pipeline.py:593, 620` + `_batch_slug:250`

**Scenario:** 30 min of clips. Target = 15 min per batch.

- Run 1: `make_batches` sees 30 min -> returns 2 batches -> `len(batches)=2` -> slug = `THOR_Feb_2026_BATCH1`. Clips moved to `Output/THOR_Feb_2026_BATCH1/clips/`.
- Run 2: Only 15 min remain in Highlights -> `make_batches` sees 15 min -> returns 1 batch -> `len(batches)=1` -> slug = `THOR_Feb_2026` (no batch number). Should be `BATCH2`.

**Root cause:** `_batch_slug` only appends `_BATCH{n}` when `total_batches > 1`. On run 2, the batch count is recomputed from remaining clips only, so it comes back as 1.

**Impact:** Run 2 output folder name is wrong/ambiguous. Folder has no `_BATCH` suffix despite being a sequel to `_BATCH1`.

**Fix options:**
1. Detect at run 2 startup that a `_BATCH1` folder already exists for this character+date, scan `Output/` and start numbering from the next available batch number.
2. Store the next batch number in `state.json` so run 2 can continue from the right number.
3. Simpler: always append `_BATCH{n}` regardless - even a single-batch run gets `_BATCH1`. Consistent, predictable, never ambiguous.

Option 3 is the simplest change.

---

## Summary

| # | Severity | File | Fix |
|---|----------|------|-----|
| 1 | HIGH | `encoder.py:49-52` | Delete out_path before encoding; never leave partial file |
| 2 | HIGH | `pipeline.py:593,620` | Run 2 batch slug loses `_BATCH` number; always suffix or detect existing batches |
| 3 | MEDIUM | `state.py:39-42` | Atomic write via `.tmp` + rename |
| 4 | LOW | `dedup.py:72,121` | Pass absolute tmp_dir from config in pipeline.py |

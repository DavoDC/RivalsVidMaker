# Ideas & Future Work

## High-priority / structural

### Rewrite pipeline in Python
Replace the C++ pipeline entirely with Python (matching the SBS Downloader repo structure).
Encoder, batcher, clip list, description writer — all in Python alongside `ko_detect.py` (in 'src' folder).
Simpler to maintain, easier to iterate on.

### Run KO detection at clip-ingest stage
Currently detection runs at batch time. Running it earlier (when clips first land) allows
all clips to be processed in parallel, and results are ready before batching begins.
Encode KO info into the clip filename (see below) at this stage.

### Encode KO tier in clip filename
After detection, rename clips to embed their max KO classification:

    THOR_2026-03-16_22-18-00.mp4  →  THOR_2026-03-16_22-18-00_QUAD.mp4

Benefits:
- Instantly reviewable — open clip, filename tells you what to expect
- Description generation can read tier from filename (no re-scan needed)
- Enables future "Best of" compilations: filter by `_PENTA` or `_HEXA` without
  re-processing anything

### Document full pipeline end-to-end
Write a reference doc (or update CLAUDE.md) describing the complete workflow:
clip ingest → KO detection → batching → encode → description → YouTube upload.
Useful for onboarding Claude in future sessions.

---

## Lower priority / future

### Best-of compilation
A "Best of 2025/2026" video pulling only Penta and Hexa clips.
Made trivial once clips are named with their KO tier (see above).

### Review `full_vid_scan_test.txt`
Output from a full-video scan test is in `docs/full_vid_scan_test.txt`.
Review findings and incorporate any useful tuning into `ko_detect.py`.

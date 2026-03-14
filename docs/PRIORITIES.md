# CompilationVidMaker — Priorities

## #1 — KO Prompt Recognition (Start Here)

**Get ONE clip working perfectly before anything else.**

1. KO (knockout) prompt/frame detection is the top priority
2. Perfect a single clip end-to-end first — no batch processing until one clip is flawless
3. Write automated tests — TDD, tests first for every feature
4. **Single language** — if KO prompt detection requires Python (ML/CV libraries), rewrite the ENTIRE app in Python. No mixed languages.
5. Only scale to multi-clip / full video pipeline after one clip is verified perfect

## Known State of Kill Detection
- `scan_kills.py` (Python) — outputs nonsense, broken
- C++ clipcache kill detection — also broken (reported 6 kills / 4 timestamps for a quadra = 4 kills, timestamps wrong)
- Both implementations need a full rethink — scan example folder images first to understand what correct output looks like

## Lower Priority
- YouTube API upload
- Description format overhaul
- Group clips by output video
- Skip-if-exists logic
- Time estimation

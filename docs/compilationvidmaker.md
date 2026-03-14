# CompilationVidMaker

Repo: `C:\Users\David\GitHubRepos\CompilationVidMaker` (C++ / Visual Studio 2022)

**Purpose:** Automates building ~15-min YouTube compilation videos from short gameplay clips. Scans Clips/, batches by duration, encodes with FFmpeg (NVENC), writes YouTube description .txt.

## Known Bugs
- `config.txt` path bug: executable runs from `Project/x64/Release/`, can't find config.txt at repo root
- Log files going to `C:\Users\David\GitHubRepos\logs\` instead of inside the repo
- **`scan_kills.py` (Python) outputs nonsense** — kill detection is broken
- **C++ clipcache kill detection also broken** — KillCount and KillTimestamps both inaccurate (reported 6 kills / 4 timestamps for what was actually a quadra = 4 kills). Timestamps are wrong too.
- Both kill detection implementations are unreliable — needs a full rethink, not a patch

## Key Context (from TTD)
- Example folder has images to reference for kill frame detection — scan these first
- Title and description generation is a secondary task (after kill detection works)

## #1 Priority — KO Prompt Recognition

**When resuming this project: KO (knockout) prompt recognition is the top priority. Everything else is secondary.**

- Get ONE clip perfect first — don't try to batch-process until a single clip works flawlessly end-to-end
- Build automated tests for it — TDD, every feature starts with a test
- **Single language rule** — if KO prompt detection requires Python (e.g. for ML/CV libraries), rewrite the ENTIRE app in Python. Do not mix languages. Pick one and go all-in.
- Only move to multi-clip / full video pipeline after one clip is perfect

## Pending Improvements (Lower Priority)
YouTube API upload, description format overhaul, group clips by output vid, skip-if-exists, time estimation.

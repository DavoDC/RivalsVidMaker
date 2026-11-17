# RivalsVidMaker GUI architecture

Status: built, 2026-11-17. Parity run on a scratch library still to do. Look and copy are in [DESIGN.md](DESIGN.md); this file covers structure, the seam and the state contract.

## Shape

A local NiceGUI app in `src/gui/`, started by `scripts/gui.bat` (`pythonw -m gui --launch`), bound to 127.0.0.1 on port 8476. It runs the existing engine in process: no separate server, no second repo, no separate command-line layer.

## The seam

`src/gui/bridge.py` is the only GUI module that imports engine modules which change files or state (`pipeline`, `cleanup`, `preprocess`, `uploader`, `encoder`, `clip_sorter`, `dedup`, `state.save`). Everything else reads through `sources.py` and `view_model.py`, which may use read-only helpers (`clip_scanner`, `batcher`, `config`, `state.load`). An AST test fails the build if any other GUI module imports a mutating module or calls `input()` or `print()`.

Engine changes that make this possible, each test first: progress listeners in `progress.py`; plan and apply pairs for cleanup, uncompile and compile, so planning never moves or renames a file; a low-value callback in `preprocess_all` instead of a prompt; an encode progress callback; one upload retry path that reports "sign in needed" instead of deleting the saved token. The terminal menu calls the same functions.

## Jobs

One background worker runs one job at a time (sort, scan, compile, upload, cleanup, uncompile, recycle). A second start is refused with the running job's name. Jobs report real progress; scan and cleanup can be stopped between clips. History is kept in `data/gui/jobs.json`; a job that was running when the app stopped shows as interrupted.

## State contract

`GET /state.json` returns the whole page state with `schema`, `generated_at`, `stale`, `poll_interval`, `boot_id`, `build`, `fixture`, then `job`, `summary`, `clips`, `compile`, `videos`, `archive`, `activity`, `config_problems` (missing tools or bad paths, painted as fix cards) and `notices` (one-shot messages such as a sign-in failure). A video's `stage` is `live` once marked live, `cleaned_partly` when the video is gone but its clips or description remain, `uploaded` when a YouTube link is recorded, and `encoded` otherwise. `GET /state/<tab>.json` returns one tab. `GET /api/build` returns the build line, sha, dirty flag and boot id. Every row carries the `testid` painted on its element, and a check compares the two. Secrets (OAuth token, client secret) never appear in any payload.

## Fixtures and checks

Fixture scenarios cover every display state in DESIGN.md section 5 through the same view-model code as real data. One command, `python -m gui verify`, runs the tests, the painted-state check and a capture of every tab at 1024 and 1440 px.

## Security

Loopback bind, Host allowlist, Origin check on the websocket and every non-GET request, and a per-launch token on write endpoints.

## Not built yet

The rows marked missing or partial in the parity table below. Deferred past the first version: tray icon and watchdog, stopping an encode or upload mid-run, editing config from the page.

## Terminal parity

| Terminal action | GUI home | Status |
|---|---|---|
| Compile a new video, pick character | Compile tab: character, Plan video | built |
| Low-value clip: include or recycle | Compile plan rows: Keep, Recycle | built |
| Low-value clip: view in VLC | "Open in player" | missing |
| Video length | Compile tab: target length | built |
| Make video? | Compile video button | built |
| Duplicates | Keep both, Drop one | built |
| Delete token and sign in again | Videos tab: Sign in to YouTube again | built |
| Preprocess all clips | Clips tab: Scan for KOs | built |
| Per-clip delete in preprocess | Clips tab: low-value list | partial: Keep has no backend |
| Retry YouTube upload | Videos tab: Upload | built, retry path unverified |
| Clean up | Videos tab: Clean up, plan then apply | built |
| Is this video live? | Videos tab: Mark as live | built |
| Uncompile | Videos tab: Restore clips, Danger mode | built |
| Browse the archive | Archive tab | built |
| Quit | Header Quit: stops when idle, names the running job when busy | built |
| `--force` | Compile: Re-encode even if it exists | built |
| `--cleanup --dry-run` | Every plan view | built |
| `--dry-run` | Plan video without Compile | built |

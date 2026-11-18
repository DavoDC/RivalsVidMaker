# RivalsVidMaker GUI design

Source of truth for how the local GUI looks, reads and behaves. Code follows this file; when they disagree, fix one of them in the same commit. Architecture and the state contract live in [GUI.md](GUI.md).

## 1. Purpose and users

One player, at a desk, after a play session, turning saved Marvel Rivals highlight clips into YouTube compilation videos. The GUI replaces the terminal menu with one page that answers "is there anything to do?" and walks the clip lifecycle: new clips, sorted and scanned, compiled, uploaded, confirmed live, cleaned up into the archive.

## 2. Verification status

2026-11-18: every tab is built. No section is verified yet: a section is marked verified once a capture at both widths shows it.

Fixed since the first captures: the shell shares one content column, Quit and the state word sit at the right of the header, the state word comes from the running job, the job bar shows count and ETA as separate text, and table cells are padded. Seen in the shell, Archive and Activity captures at both widths.

Fixed in code since those captures, not yet seen in a capture: buttons are sentence case (`src/gui/theme.py:16`), numeric columns are right aligned (`src/gui/tabs/clips.py:47,50`; `src/gui/tabs/archive.py:50`), the header sits 12 px from the top (`src/gui/theme.py:19-20`), and tooltips and the connection-lost popup are themed (sections 5 and 10).

Gaps still open, each with a fix queued:

- Table body cells render bold; tables are Regular (section 6).

Designed but not built yet, each described in its section:

- The "Reading folders" loading copy and the fix card for errors (section 5).
- The stale banner (section 5).
- The 5 s Undo on a recycled clip (section 9).
- Relative times in Activity (section 12).
- The thin reel on each Videos row (section 7).
- The progress bar fill animation (section 7).

## 3. Principles

1. Fewest controls. One button per job, named by its result.
2. Risk-scaled weight. Recoverable actions are one click with Undo; actions that move many files show a plan first; the one action that rewrites a whole folder sits behind Danger mode.
3. Every plan is the dry run. There is no separate dry-run switch; planning never changes a file.
4. Calm until it matters. Neutral means fine. Colour means a highlight worth keeping or something that needs you.
5. Names from data are quoted and shown as text, never as markup.
6. No raw terminal output on the page. Logs are one click away as files.
7. Same verb everywhere. The button, the toast and the activity row use the same words.

## 4. Information architecture

The tabs run in lifecycle order. The tab key is the deep link (`/tab/<key>`).

| Key | Label | Answers |
|---|---|---|
| `clips` | Clips | What came in, what is scanned, which clips need a keep or recycle decision |
| `compile` | Compile | Which characters have enough minutes, what the next video will contain |
| `videos` | Videos | Which videos wait for upload, for a live check, or for cleanup |
| `archive` | Archive | Which Quad and better clips are kept for a best-of |
| `activity` | Activity | What ran, whether it worked, where its log is |

Open log opens the day's log in a new tab through the app (`/log/<name>`, `src/gui/state_api.py:144-153`), so the browser never blocks a file link.

Header on every tab, one row spanning the content column: the app mark and "RivalsVidMaker" on the left (`src/gui/chrome.py:120-134`); pushed to the right end, a state dot and word, then Quit. The state word comes from the snapshot's `job`: Idle when there is none, otherwise the job's phase word with its percent ("Encoding 33%"), Error after a failed job until the next start; the dot takes `working` while a job runs and `error` after a failure. It is announced to screen readers. Footer: fixed bottom left on every tab, showing the short sha and commit time (`<sha> <h:mmam>`, with `+dirty` last when tracked files changed); the full build line and start time are on hover (`src/gui/chrome.py:137-144`). A FIXTURE banner shows in fixture mode (`src/gui/chrome.py:147-152`). In a fixture run, Sort clips and Scan for KOs play a three-second fake job, so the job states can be seen; nothing on disk changes (`src/gui/wiring.py:296-305`).

Tray icon: the app runs windowless, so a tray icon (`src/gui/tray.py`) is the visible handle. It shows the app mark, and its tooltip reads "RivalsVidMaker: <state word>" (`tray.py:130-131`). Its menu has Open RivalsVidMaker, Reload and Quit, and a double left click opens the app (`tray.py:139-153`). Open goes to `http://localhost:<port>/?tab=<last tab>`, the tab shown last (`tray.py:77-81`, `src/gui/last_tab.py`); David-facing URLs say localhost, never 127.0.0.1 (`src/gui/security.py:35`). The `/` route does not read `?tab=` yet, so Open lands on the default tab (section 2). Quit stops the app when no job runs and otherwise says a job is still running (`tray.py:121-127`). The tray is off when `RVM_GUI_TRAY=0` or in a fixture run (`tray.py:37-39`).

## 5. Display-state vocabulary

Every view has these states and each has a fixture: loading ("Reading folders" in dim text, not built yet), empty (names the next action), ready, working (determinate bar up to 640 px wide, with count and ETA as two separate text runs; "Starting" until the first signal; `src/gui/components/job_bar.py:38,57,60-63`), needs decision, error (a fix card: red left rule, what happened, the fix, one action; not built yet on the page), stale (banner past four poll intervals, 8 s floor; the stale flag reaches the state but no banner is drawn yet), interrupted (a job that was running when the app stopped), busy refused (a second job start names the running one; `src/gui/jobs.py:36-41,152-155`).

When the connection to the app drops, NiceGUI's connection-lost popup shows in the panel and text colours with a red left rule, not light text on a light background (`src/gui/theme.py:31-32`).

## 6. Tokens

`src/gui/tokens.py` is the code source; a test checks this table matches it.

| Token | Hex | Meaning |
|---|---|---|
| `ground` | `#131722` | page background, a blue-black like a night map |
| `panel` | `#1B2130` | grouped surfaces |
| `line` | `#2A3247` | 1 px dividers and outlines |
| `text` | `#E3E7F0` | primary text, focus ring |
| `text_dim` | `#8E97AD` | secondary text |
| `working` | `#4FA3E0` | a job is running |
| `error` | `#E5484D` | failed, needs action |
| `tier_quad` | `#F2C14E` | QUAD |
| `tier_penta` | `#FF8A3D` | PENTA |
| `tier_hexa` | `#FF4D8D` | HEXA |
| `tier_low_1` | `#3B4359` | KO outline |
| `tier_low_2` | `#596380` | DOUBLE outline |
| `tier_low_3` | `#8089A3` | TRIPLE outline |
| `on_tier` | `#131722` | text on a tier fill |

There is no warning amber: gold always means QUAD. Warnings use `text` weight plus an icon.

Type: Bahnschrift, a system font on Windows, so nothing is downloaded. Display text (tab labels, headings, tier chips, reel timestamps, large durations) is SemiBold SemiCondensed (`font-weight: 600; font-stretch: 87.5%`). Body and tables are Regular. Numbers use tabular figures. Fallback: `Bahnschrift, "Segoe UI Variable", "Segoe UI", sans-serif`.

Size scale (px): 13 fine print, 16 tables and buttons, 17 body, 22 section heading, 22 tab labels, 26 tab heading, 32 app title, 40 the reel's total duration. Character avatars are 36 px.

Initials badges inside an avatar use 13 px SemiBold (`src/gui/avatars.py:63-66`). A portrait from `assets/characters` replaces the badge when the file is present (`src/gui/avatars.py`).

Spacing step 4: 4, 8, 12, 16, 24, 32. Radius: 2 px on chips and reel segments, 6 px on panels and buttons. No shadows. Lists are tables with row dividers, not card grids.

Contrast pairs checked by the capture run: `text` on `ground`, `text` on `panel`, `text_dim` on `panel`, `on_tier` on each tier fill.

## 7. Signature element

The reel strip on the Compile tab: one bar per planned video, the full column width, cut into segments sized by clip length. QUAD, PENTA and HEXA segments are lit in the tier ramp and labelled with the timestamp they get in the description; all other segments are quiet slate (`src/gui/components/reel.py:42-80`). It is the description made visible and the only saturated thing on screen. The Videos tab does not draw a reel yet; a thin version on each Videos row is still to build.

Near-ready characters on the Compile tab each show a thin gold bar, 240 px wide (`src/gui/tabs/compile.py:70`), beside their M:SS of 10:00 text, filled to their share of the ready length and full at 10:00.

The one motion: when a plan appears or a compile finishes, the lit segments light left to right once, about 600 ms in total (`src/gui/components/reel.py:17-18`). With reduced motion they appear lit at once (`reel.py:25`). The progress bar fill is meant to animate too, but no transition is built yet.

App mark: a gold tile with a slanted navy panel, and a gold play triangle cut by a navy KO slash. It is angular and original, in the two page colours from section 6, and uses no game logo or trademark. `src/gui/icon.py:37-47` draws it from the token colours; the header shows it at 28 px (`src/gui/chrome.py:120-134`).

## 8. Copy voice

Sentence case. Tier words stay upper case because the game prints them that way. Verbs: Sort clips, Scan for KOs, Plan video, Compile video, Upload to YouTube, Mark as live, Clean up, Restore clips, Keep, Recycle. Toasts reuse the verb in past tense with the quoted name where the job has one: Recycled "THOR_OCT-NOV_2026" (`src/gui/shell.py:79`). A job toasts twice: the -ing form when it starts (Compiling video.) and the past tense when it finishes (Compiled video.; `src/gui/shell.py:52-56`, `src/gui/wiring.py:198`); a failure toasts the job title and its error. The start toast is neutral (info, `src/gui/wiring.py:156-254`); only the finish toast is green (`src/gui/shell.py:79-82`).

Meta strings are never joined with a middle dot or a dash: put parts in separate elements with a 16 px gap ("3 of 9 steps" then "About 4 min left"). Upper case is for tier words and the FIXTURE banner word only; table headings and labels are sentence case.

Errors state what happened and the fix, never apologise: "FFmpeg is missing from dependencies/ffmpeg. Put ffmpeg.exe and ffprobe.exe there, then press Check again." (`src/gui/launcher.py:36-37`; the page does not draw this card yet). Empty states name the next action: "No new clips. Save highlights in game, then press Sort clips." (`src/gui/tabs/clips.py:20`).

## 9. Interaction and destructive actions

Clean up and Restore clips use plan then apply. The plan lists every file and its fate (to the archive, to the Recycle Bin, video optionally recycled, empty folder removed) with counts and sizes; nothing moves while planning. Apply runs exactly that plan: a plan is held under a single-use token, and a stale, reused or wrong-kind token is refused before any file moves (`src/gui/bridge.py:51-54`). Apply refuses if the folder changed since the plan. The totals line reads like "Archive 2 clips, recycle 1 file, 1.6 GB" (`src/gui/components/plan_list.py:44-56`), an "Also recycle the video" checkbox sits in the plan (`plan_list.py:109`), and the apply button is disabled when the plan has no moves. Clean up appears only after the video is marked live. Restore clips sits behind a Danger mode toggle and needs the folder name typed. Recycling one low-value clip is one click; the 5 s Undo is designed but not built yet (section 2). Deleted files go to the Recycle Bin, never straight to permanent deletion.

Long work (scan, encode, upload) runs as one background job at a time; the page stays usable and shows real progress. Starting a second job says which one is running (`src/gui/jobs.py:36-41,152-155`).

## 10. Accessibility and motion

Tabs use tablist and tabpanel roles. Icon buttons have labels. Focus ring is a visible 2 px `text` outline. The state word in the header is a live region. Reduced motion removes the reel reveal and every other transition and animation (`src/gui/theme.py:59-61`). Tier is never colour alone: chips carry the word. Held is never colour alone either: a held clip shows a lock icon and the word Held (`src/gui/tabs/clips.py:153-160`).

### Tooltips

Hovering a column heading on Clips shows what the column counts. The heading has a dotted underline; the text sits in a box with a 1 px line border on the panel colour, wraps, and is at most 300 px wide (`src/gui/theme.py:33-38`, `src/gui/tabs/clips.py:25-34,111-114`). The same box is styled for keyboard focus (`theme.py:34`). Button tooltips use Quasar's tooltip, styled to match at 16 px and up to 320 px (`theme.py:28-30`); Sort clips and Scan for KOs have one each (`src/gui/tabs/clips.py:240-241`). Tooltips add detail only: the column label, the count and the status word stay visible, so no tooltip is the only place a state is shown.

## 11. Layout

Desktop only, minimum width 1024 px, base text 17 px (`src/gui/theme.py:12`). One content column, width 100% up to 1280 px, centred, 24 px side gutters (`src/gui/shell.py:217-218`): the header, fixture banner, tab strip, panel and footer all share its edges, and their rules run its full width. The header title sits 12 px from the top. The footer is fixed to the bottom left of the window on every tab (`src/gui/theme.py:54-55`), and the page keeps 32 px of room under it so the last table row is never hidden (`theme.py:12`). Tables fill the column with 12 px horizontal cell padding (`theme.py:58`) and numbers right aligned (`src/gui/tabs/clips.py:47,50`; `src/gui/tabs/archive.py:50`). At 1440 the Clips tab shows the character table and the decision panel side by side; at 1024 the panel moves under the table.

The character table on Clips has Character, Clips, Length, Scanned and Best. Length counts scanned clips only, and a dim "N unscanned" line under it counts the rest (`src/gui/tabs/clips.py:117-121,135`).

The In Highlights root list is a table of character (avatar and display name), capture date, capture time and Status. It is sized to its content rather than the column (`src/gui/tabs/clips.py:187`), with the file name on hover (`clips.py:179`). Status shows a lock and the word Held for a protected clip, Next sort for a clip Sort will move, and stays blank for a name Sort cannot read (`clips.py:153-160`). A name Sort cannot read shows its file name and the unreadable note where the character would be, with empty date and time cells (`clips.py:176-178`). When any row is protected, one dim line leads the table: the root note (`clips.py:24,185-186`). There is no phone layout: the app runs beside the game on the same Windows machine.

## 12. Timestamps and numbers

Dates `DD/MM/YYYY`, times `h:mmam/pm` (`src/gui/timefmt.py:29-36`), durations `m:ss` (or `h:mm:ss` past an hour; `timefmt.py:57-66`), sizes in KB under 1 MB, MB with one decimal, GB with one decimal from 1 GB (`src/gui/components/plan_list.py:30-37`). Activity shows short dates and times that never wrap, with the full stamp on hover (`src/gui/tabs/activity.py:83-87`; short form in `timefmt.py:39-54`). Relative times ("3m ago") are designed for Activity with the absolute time on hover, but not built yet: the helper `timefmt.ago` has no caller (`timefmt.py:69-78`).

## 13. Driving the UI as Claude

Every fact on screen is also in `/state.json`; every row has a stable `data-testid` of the form `<kind>-<slug>-<hash>`. `/tab/<key>` opens any tab in one URL; a fixture scenario is chosen at launch with `--fixture <name>` (a per-URL scenario switch is queued). `window.__debug` exposes version, state, setTab, forceStatus and help (`src/gui/chrome.py:91-108`). The state API serves `/state.json`, `/api/build`, `/log/<name>`, `/__log` and `/__quit` (`src/gui/state_api.py:34-38`). The commands are in the CLAUDE.md run block: `--fixture NAME`, `verify` and `shot` (`CLAUDE.md:62-68`).

## 14. Non-goals

Editing config from the page, in-page video playback (Open in player launches the configured player), editing descriptions in the page (copy only), best-of compiles from the archive, phone width, network access from other machines.

## 15. Settled decisions

- 2026-11-17: the GUI lives in this repo under `src/gui/` and calls the engine in process; one bridge module imports the modules that change files, and a test enforces it.
- 2026-11-17: no separate command-line layer for the GUI; the terminal menu stays until the GUI covers every action.
- 2026-11-17: NiceGUI with tabs, port 8476, loopback only.
- 2026-11-17: desktop only; Bahnschrift; the reel strip is the one bold element.

## 16. UI work rules

Change tokens here and in `tokens.py` together. A new state needs a fixture before it needs code. Every UI change ends with the verify command passing and a look at the captures at both widths.

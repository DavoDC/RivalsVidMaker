# RivalsVidMaker GUI design

Source of truth for how the local GUI looks, reads and behaves. Code follows this file; when they disagree, fix one of them in the same commit. Architecture and the state contract live in [GUI.md](GUI.md).

## 1. Purpose and users

One player, at a desk, after a play session, turning saved Marvel Rivals highlight clips into YouTube compilation videos. The GUI replaces the terminal menu with one page that answers "is there anything to do?" and walks the clip lifecycle: new clips, sorted and scanned, compiled, uploaded, confirmed live, cleaned up into the archive.

## 2. Verification status

2026-11-17: shell, Archive and Activity are built; Clips, Compile and Videos are stubs. No section is verified yet: a section is marked verified once a capture at both widths shows it.

Fixed since the first captures: the shell shares one content column, Quit and the state word sit at the right of the header, the state word comes from the running job, the job bar spans the panel with separate count and ETA, and table cells are padded. Seen in the shell, Archive and Activity captures at both widths.

Gaps still open, each with a fix queued:

- About 40 px of extra space above the header and 60 px between the header and the fixture banner (section 11).
- Numeric table columns are left aligned (section 11).
- Buttons render upper case ("STOP"); labels are sentence case (section 8).
- Table body cells render bold; tables are Regular (section 6).

## 3. Principles

1. Fewest controls. One button per job, named by its result.
2. Risk-scaled weight. Recoverable actions are one click with Undo; actions that move many files show a plan first; the one action that rewrites a whole folder sits behind Danger mode.
3. Every plan is the dry run. There is no separate dry-run switch; planning never changes a file.
4. Calm until it matters. Neutral means fine. Colour means a highlight worth keeping or something that needs you.
5. Names from data are quoted and shown as text, never as markup.
6. No raw terminal output on the page. Logs are one click away as files.
7. Same verb everywhere. The button, the toast and the activity row use the same words.

## 4. Information architecture

Five tabs in lifecycle order. The tab key is the deep link (`/tab/<key>`).

| Key | Label | Answers |
|---|---|---|
| `clips` | Clips | What came in, what is scanned, which clips need a keep or recycle decision |
| `compile` | Compile | Which characters have enough minutes, what the next video will contain |
| `videos` | Videos | Which videos wait for upload, for a live check, or for cleanup |
| `archive` | Archive | Which Quad and better clips are kept for a best-of |
| `activity` | Activity | What ran, whether it worked, where its log is |

Header on every tab, one row spanning the content column: "RivalsVidMaker" on the left; pushed to the right end, a state dot and word, then Quit. The state word comes from the snapshot's `job`: Idle when there is none, otherwise the job's phase word with its percent ("Encoding 33%"), Error after a failed job until the next start; the dot takes `working` while a job runs and `error` after a failure. It is announced to screen readers. Footer: build line (`RivalsVidMaker <sha> <date> +dirty`), start time, "updated Ns ago", and a FIXTURE banner in fixture mode.

## 5. Display-state vocabulary

Every view has these states and each has a fixture: loading ("Reading folders" in dim text), empty (names the next action), ready, working (determinate bar spanning the panel width, with count and ETA as two separate text runs; "Starting" until the first signal), needs decision, error (a fix card: red left rule, what happened, the fix, one action), stale (banner past four poll intervals, 8 s floor), interrupted (a job that was running when the app stopped), busy refused (a second job start names the running one).

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

Size scale (px): 12 fine print, 14 tables and buttons, 16 body, 20 section heading, 26 tab heading, 40 the reel's total duration.

Spacing step 4: 4, 8, 12, 16, 24, 32. Radius: 2 px on chips and reel segments, 6 px on panels and buttons. No shadows. Lists are tables with row dividers, not card grids.

Contrast pairs checked by the capture run: `text` on `ground`, `text` on `panel`, `text_dim` on `panel`, `on_tier` on each tier fill.

## 7. Signature element

The reel strip on the Compile tab: one bar per planned video, about fifteen minutes wide, cut into segments sized by clip length. QUAD, PENTA and HEXA segments are lit in the tier ramp and labelled with the timestamp they get in the description; all other segments are quiet slate. It is the description made visible and the only saturated thing on screen. A thin version appears on each Videos row.

The one motion: when a plan appears or a compile finishes, the lit segments light left to right once, about 600 ms in total. With reduced motion they appear lit at once. Only the progress bar fill otherwise animates.

## 8. Copy voice

Sentence case. Tier words stay upper case because the game prints them that way. Verbs: Sort clips, Scan for KOs, Plan video, Compile video, Upload to YouTube, Upload again, Mark as live, Clean up, Restore clips, Keep, Recycle. Toasts reuse the verb in past tense with the quoted name: Compiled "THOR_OCT-NOV_2026".

Meta strings are never joined with a middle dot or a dash: put parts in separate elements with a 16 px gap ("3 of 9 steps" then "About 4 min left"). Upper case is for tier words and the FIXTURE banner word only; table headings and labels are sentence case.

Errors state what happened and the fix, never apologise: "FFmpeg is missing from dependencies/ffmpeg. Put ffmpeg.exe and ffprobe.exe there, then press Check again." Empty states name the next action: "No clips in Highlights. Save highlights in game, then press Refresh."

## 9. Interaction and destructive actions

Clean up and Restore clips use plan then apply. The plan lists every file and its fate (to the archive, to the Recycle Bin, video optionally recycled, empty folder removed) with counts and sizes; nothing moves while planning. Apply runs exactly that plan, refuses if the folder changed since, and the button says what it will do ("Archive 6 clips, recycle 14"). Clean up appears only after the video is marked live. Restore clips sits behind a Danger mode toggle and needs the folder name typed. Recycling one low-value clip is one click with a 5 s Undo. Deleted files go to the Recycle Bin, never straight to permanent deletion.

Long work (scan, encode, upload) runs as one background job at a time; the page stays usable and shows real progress. Starting a second job says which one is running.

## 10. Accessibility and motion

Tabs use tablist and tabpanel roles. Icon buttons have labels. Focus ring is a visible 2 px `text` outline. The state word in the header is a live region. Reduced motion removes the reel reveal. Tier is never colour alone: chips carry the word.

## 11. Layout

Desktop only, minimum width 1024 px, base text 16 px so it reads at browser 100%. One content column, width 100% up to 1280 px, centred, 24 px side gutters: the header, fixture banner, tab strip, panel and footer all share its edges, and their rules run its full width. The header sits 16 px from the top, not 60. Tables fill the column with 12 px horizontal cell padding and numbers right aligned. At 1440 the Clips tab shows the character table and the decision panel side by side; at 1024 the panel moves under the table. There is no phone layout: the app runs beside the game on the same Windows machine.

## 12. Timestamps and numbers

Dates `DD/MM/YYYY`, times `h:mmam/pm`, durations `m:ss` (or `h:mm:ss` past an hour), sizes in KB under 1 MB, MB with one decimal, GB with one decimal from 1 GB. Relative times ("3m ago") only in the footer and Activity, with the absolute time on hover.

## 13. Driving the UI as Claude

Every fact on screen is also in `/state.json`; every row has a stable `data-testid` of the form `<kind>-<slug>-<hash>`. `/tab/<key>` opens any tab in one URL; a fixture scenario is chosen at launch with `--fixture <name>` (a per-URL scenario switch is queued). `window.__debug` exposes version, state, setTab, forceStatus and help. Commands are listed in the CLAUDE.md run block once built.

## 14. Non-goals

Editing config from the page, in-page video playback (Open in player launches the configured player), editing descriptions in the page (copy only), best-of compiles from the archive, phone width, network access from other machines.

## 15. Settled decisions

- 2026-11-17: the GUI lives in this repo under `src/gui/` and calls the engine in process; one bridge module imports the modules that change files, and a test enforces it.
- 2026-11-17: no separate command-line layer for the GUI; the terminal menu stays until the GUI covers every action.
- 2026-11-17: NiceGUI with tabs, port 8476, loopback only.
- 2026-11-17: desktop only; Bahnschrift; the reel strip is the one bold element.

## 16. UI work rules

Change tokens here and in `tokens.py` together. A new state needs a fixture before it needs code. Every UI change ends with the verify command passing and a look at the captures at both widths.

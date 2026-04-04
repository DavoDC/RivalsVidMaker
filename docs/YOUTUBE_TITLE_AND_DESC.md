# YouTube Video Format Guide

Reference for generating titles, descriptions, and timestamps for Marvel Rivals compilation videos.

---

## Upload workflow (manual - current approach)

After a successful pipeline run, a `_description.txt` is produced in the output folder. The upload flow is:

1. **Open the output folder** (path shown in NEXT STEPS at end of run)
2. **Drag the .mp4 into YouTube Studio** - use the slug (e.g. `THOR_Mar_2026_BATCH1`) as the temporary title
3. **Paste the full DESCRIPTION section** from `_description.txt` into the YouTube description box
   - The description starts with an AI prompt - leave it in for now, replace it after
4. **Click Next and publish as Private** - get it saved fast, don't polish first
5. **Open the video in YouTube Studio and iterate:**
   - Paste the TITLE PROMPT into ChatGPT/Grok, pick a title, replace the temp title
   - Paste the description AI prompt into ChatGPT/Grok, get a one-liner, replace the prompt text in the description
   - Watch the video back, adjust timestamps if needed
6. **Change from Private to Public** once happy with title, description, and timestamps

Key principle: get it saved quickly, iterate in YouTube Studio, publish when it looks right.

---

## Full description structure

```
TITLE:
<see title examples below>

DESCRIPTION:
<one-liner — see description examples below>

TIMESTAMPS:
<streak start> - <max kill time> = <Tier> Kill
(Quad+ only; format confirmed perfect on vid2)

HIGHLIGHTS:
1. CLIP_FILENAME.mp4
2. CLIP_FILENAME_QUAD.mp4
3. CLIP_FILENAME_HEXA.mp4
...
(ideally clip filenames have KO tier appended — see IDEAS.md)
```

---

## Timestamp format

```
1:31 - 1:52 = Hexa Kill
4:13 - 4:19 = Quad Kill
```

- Left time  = when the FIRST KO banner appears (streak start — gives viewers the build-up)
- Right time = when the highest-tier banner (Quad/Penta/Hexa) first appears
- Quad and above only — Triple and below are detected internally but not shown

---

## Title examples

Current format (used from ~Oct 2025 onwards):
```
THOR OVERLOAD Back-to-Back Multikills (Feb-Mar 2026)       <- vid2, confirmed perfect
THOR AWAKENS Multikill Highlights (Feb 2026)
THOR IN FULL CONTROL Multikill Highlights (Dec 2025)
THOR AT PEAK POWER Multikill Highlights (Jan 2026)
UNSTOPPABLE THOR Multikill Highlights | Nov-Dec 2025
SQUIRREL GIRL MULTIKILL MONTAGE! (Dec 25 - Feb 26)
```

**Pattern:** `<CHARACTER> <CAPS TAGLINE> <subtitle> (<date range>)` - with lightning bolt emoji between tagline and subtitle

Legacy format (used before ~Oct 2025 - not ideal, avoid for new videos):
```
THOR HIGHLIGHTS, MULTIKILLS [FEB-MAY 2025]
THOR HIGHLIGHTS, MULTIKILLS [AUG 2025][Part 1]
SQUIRREL GIRL HIGHLIGHTS [AUG-OCT 2025]
```

Gameplay stream format (full session recordings, not compilations):
```
THOR RIVALS GAMEPLAY (13th Aug 2025)
MARVEL RIVALS Gameplay (1st Nov 2025)
```

---

## One-liner description examples

```
⚡ The storm answers only to the worthy — Mjölnir unleashed, lightning combos, and relentless Thor multikills across Feb–Mar 2026 in Marvel Rivals 🔥⚡
```
*(vid2 — confirmed perfect)*

```
⚡ The God of Thunder answers the call — Mjölnir strikes, lightning crashes, and Thor unleashes unstoppable multikills in Marvel Rivals 🔨⚡🔥
```

```
WORTHY OF MJÖLNIR ⚡ God of Thunder unleashed — insane Thor multikills, lightning combos, and clutch moments in Marvel Rivals 🔨🔥
```

```
⚡ BY THE POWER OF MJÖLNIR 🔨 Thor goes god-mode — nonstop multikills, thunder slams, and pure domination ⚡🔥
```

```
I am Asgard's might! ⚡ 9 Quadras, 3 Pentas, and one Hexa 💪
```
*(good when you have notable kill counts to call out)*

**Pattern:** punchy, hype, ends with "in Marvel Rivals" (or references the game). Emojis throughout.


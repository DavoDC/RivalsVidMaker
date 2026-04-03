# Tasks

Concrete next actions, ordered by priority. Completed tasks move to `docs/HISTORY.md`.

---

## Blocked / needs manual action

**Fix OAuth consent screen - add test user**

The YouTube OAuth flow returns `Error 403: access_denied` because the app has not completed Google verification.
Fix: add `davo29rhino@gmail.com` as a test user so it bypasses verification.

Steps:
1. Go to Google Cloud Console -> APIs & Services -> OAuth consent screen
2. Scroll to "Test users"
3. Click "+ Add users" -> add `davo29rhino@gmail.com`
4. Save
5. Re-run: `python scripts/yt_upload_test.py "C:\Users\David\Videos\MarvelRivals\Highlights\THOR\THOR_2026-03-05_19-27-05_QUAD.mp4"`

---

## Next up (in order)

1. **Implement channel verification in yt_upload_test.py** - call `channels.list?part=id&mine=true`, compare against `youtube_channel_id` in config, abort if mismatch. Do this before any real upload. See IDEAS.md item 1.

2. **Implement duplicate clip detection** - perceptual hash 5 frames per clip, flag near-duplicate pairs before encode. See IDEAS.md item 2 for full design.

3. **E2E Thor test - dry run** - `python src/main.py --dry-run` on 31 Thor clips.

4. **E2E Thor test - live run** - full pipeline after dry run looks good.

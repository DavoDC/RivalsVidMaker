# KO Prompt Detection — Reference Notes

## What we're detecting

The Marvel Rivals in-game KO banner that appears on the right side of the screen
when the player gets consecutive kills. It shows the current streak tier.

## Tier labels (in-game text)
| Event # | Text shown | Tier name in code |
|---------|------------|-------------------|
| 1       | KO         | Kill              |
| 2       | DOUBLE!    | Double Kill       |
| 3       | TRIPLE!    | Triple Kill       |
| 4       | QUAD!      | Quad Kill         |
| 5       | PENTA!     | Penta Kill        |
| 6       | HEXA!      | Hexa Kill         |

Only **Quad Kill and above** are recorded in the YouTube description timestamps.

## Banner position (screen fractions)
- X start: ~75–85% of video width
- X end: 100% (right edge)
- Y start: ~41–43% of video height
- Y end: ~57–61% of video height

The banner slides in from the right edge. It stays on screen for ~2–3 seconds,
then fades out before the next tier appears.

## Colour — varies by character!
| Character     | Banner colour         |
|---------------|-----------------------|
| Thor          | Vivid electric blue / cyan (~R=0, G=160, B=240) |
| Squirrel Girl | Vivid gold / yellow  (~R=220, G=180, B=0)       |

**Detection heuristic**: character-agnostic saturation check:
`max(R,G,B) > 180 AND max(R,G,B) - min(R,G,B) > 100`
This captures any vivid saturated colour while rejecting grey/muted backgrounds.

## Reference screenshots in this folder
- `thor_ko.png`       — Thor, KO banner, timestamp 00:05
- `thor_double.png`   — Thor, DOUBLE! banner, timestamp 00:09
- `thor_triple.png`   — Thor, TRIPLE! banner, timestamp 00:14
- `quad_example1.png` — Thor, QUAD! banner, stone ruins map
- `quad_example2.png` — Thor, QUAD! banner, Asgard-style map (blue/purple ambient)
- `quad_example3.png` — Squirrel Girl, TRIPLE! banner (gold/orange colour, neon space map)
- `example_a.png`     — Thor, TRIPLE! on circular arena map
- `example_b.png`     — Thor, KO on circular arena map
- `example_c.png`     — Thor, KO on circular arena map (different frame)
- `example_d.png`     — Thor, DOUBLE! on stone castle / Japanese map
- `example_e.png`     — Thor, QUAD! at JIKAWA MALL

## Scan parameters (KillDetector.cpp)
- Frame rate: 2 fps
- Skip first: 4 seconds (banner never appears this early)
- Crop: `crop=iw*0.25:ih*0.20:iw*0.75:ih*0.41`
- Vivid pixel threshold: 3% of crop area
- Event cooldown: 2s between distinct events

## TODO / future improvements
- Add more character banner colour samples as encountered
- If false positives occur in specific maps, consider tightening crop or threshold
- `quad_example2` has a blue/purple ambient map — keep an eye on false positives there
- `quad_example3` (Squirrel Girl) confirms the colour-agnostic saturation heuristic is working

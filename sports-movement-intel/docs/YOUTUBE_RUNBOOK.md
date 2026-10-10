# YouTube recording runbook

Only **SkillCorner open data (MIT)** appears on screen. Metrica and NBA SportVU are local-only (their data
license is unknown). Record with `SMIP_PUBLIC_DEMO=1`, which hides them from the catalog and returns 404
for their sessions.

## Before recording (about 20 minutes, once)

```bash
make setup && make data          # default PROFILE=sample: both demo SkillCorner matches + 2 NBA games (~550 MB)
make build && make up
make demo-seed                   # three sessions, parity + lineage checked (~12 min)
make ml-eval analyst-eval
make verify                      # must be all green; writes docs/STATUS.md
```

Then restart the API in public mode:

```bash
SMIP_PUBLIC_DEMO=1 docker compose up -d api
open http://127.0.0.1:18000
```

Close Docker Desktop notifications, set the browser to 1600×1000 and hide bookmarks.

## Suggested segments

| # | segment | what to show | deep link |
|---|---|---|---|
| 1 | cold open | the hero match at 20×: trails, hulls, defensive line | `?session=demo-soccer-hero&view=live&t=1832000` |
| 2 | "not pitch control" | Voronoi overlay. Say out loud that it is geometric, with no velocities | `...&overlays=voronoi,trails,labels` |
| 3 | player heatmap | click a player; the heatmap is replay-time bounded | `...&overlays=heatmap,labels&pick=skillcorner:player:23418` |
| 4 | similar moments | "find similar" → jump to a neighbour, lift number in the panel | `...&t=2410000&similar` |
| 5 | shape changes | timeline markers (PELT), click → seek | live view timeline |
| 6 | grounded analyst | ask "Which players covered the most distance?"; show evidence ids; ask a prompt injection → refused | `...&ask=...` |
| 7 | pipeline under faults | `demo-soccer-faults`: duplicates, corrections, quarantine, parity badge, lineage | `?session=demo-soccer-faults&view=pipeline` |
| 8 | lakehouse on disk | `ls lakehouse/data/warehouse` and `smip lakehouse inspect` | terminal |
| 9 | catalog and licenses | why only SkillCorner is shown | `?view=catalog` |

Add `&paused` to any link to freeze the frame for voice-over.

## Live replay on camera (optional)

```bash
# --no-inline hands the session to the replay service so it can be paused and re-sped
.venv/bin/smip replay start --match skillcorner:1886347 --speed 20 --session live-take-1 --no-inline
.venv/bin/smip replay control live-take-1 pause
.venv/bin/smip replay control live-take-1 speed --speed 50
.venv/bin/smip replay control live-take-1 resume
```

## Claims to say, and claims to avoid

Say:
- "historical match replay", "effectively-once per session", "parity with the batch run"
- the numbers from `docs/BENCHMARKS.md`, including the hardware they were measured on

Avoid:
- "live data", "real-time from the stadium", "exactly-once end to end", "pitch control", "AI coach"
- NBA numbers or Metrica footage in a public video

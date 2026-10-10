# YouTube Video Presentation Plan — Sports Movement Intelligence Platform

## Recommended Format

**Target length:** 25–28 minutes (hard cap 30). Hook → architecture → one frame's journey → break it on purpose → dashboard tour → code → tradeoffs + next level → run it yourself.

**Style:** Screen recording with voiceover. YouTube chapters via timestamps. Face cam optional (a small corner cam works well for the "break it on purpose" chapter).

**Tone:** Sports-broadcast energy on top of engineering precision. Use match commentary metaphors ("the pipeline takes a hit and keeps playing"), but every number said out loud comes from `docs/STATUS.md` or `docs/BENCHMARKS.md`.

**Humor rules:** the jokes ride *on* a real fact, never replace one. Deliver them dry: say the line, pause half a beat, move on, and don't laugh at your own joke. If a punchline doesn't land in the edit, cut it; the sentence before it must still work alone.

**On screen: SkillCorner only.** The public video shows **SkillCorner open data (MIT)** only. Metrica and NBA SportVU have no stated data license. They stay local, and you *talk* about them, you don't *show* them. Record with `SMIP_PUBLIC_DEMO=1` (see `docs/YOUTUBE_RUNBOOK.md`). This is also a nice honesty moment in Chapter 2.

**Browser:** 1600×1000, bookmarks hidden. Add `&paused` to any deep link to freeze a frame for voice-over.

---

## Video Structure (9 Chapters)

| # | chapter | length |
|---|---|---|
| 1 | Hook: a match replayed through a real streaming lakehouse | 1.5 min |
| 2 | The data, the "historical replay" promise, and why the same code works live | 2.5 min |
| 3 | Architecture overview | 3 min |
| 4 | The journey of one frame | 4.5 min |
| 5 | Break it on purpose: faults, quarantine and parity | 4 min |
| 6 | Dashboard tour: shape, space, similar moments, analyst | 4.5 min |
| 7 | Code walkthrough | 3 min |
| 8 | Tradeoffs and the next level (including going live) | 4.5 min |
| 9 | Run it yourself + closing | 1 min |
| | **total** | **~28.5 min** |

If the edit runs long, trim the Data / Models / Product lanes in Chapter 8 to one sentence each. Keep "Going live".

---

### Chapter 1 — Hook (≈1.5 min)

Open on the **end result**: the hero match at 20×, trails and hulls on.

- Deep link: `http://127.0.0.1:18000/?session=demo-soccer-hero&view=live&t=1832000`
- Let it play 5–6 seconds with no voice. Then talk.
- Toggle Voronoi on for one beat, then off again.
- Flash the Pipeline view parity badge for one second at the end ("exact").

**SPEECH:**

> Twenty-two players and a ball, ten times a second, for ninety minutes. That's what you're watching: a real A-League match, rebuilt from tracking data, dot by dot.
>
> But this isn't a video player. Every one of those dots just travelled through Kafka, through Spark Structured Streaming, into an Apache Iceberg lakehouse and ClickHouse, and back out to this React dashboard, in a few seconds.
>
> The team shapes, the defensive line, the trails: all computed *while the match streams*. And then I'm going to do the thing every data engineer secretly wants to do on camera: sabotage my own pipeline. Duplicates, late data, corrections, broken JSON. The streaming results will still match a clean batch run **row for row**. Zero differences. Not "roughly the same". Not "within tolerance". Zero.
>
> One `docker compose` on a laptop. No cloud account. No paid API. My laptop fan has opinions about this. We'll ignore them. Let's go.

---

### Chapter 2 — The data, the "historical replay" promise, and why the same code works live (≈2.5 min)

**On screen:** the Catalog view (`?view=catalog`), then one normalized frame in the terminal.

The normalized data lives in `data/normalized/skillcorner/1886347/` (the hero match). `tracking.parquet` has one row per player or ball per frame. Parquet is binary, so print the frame at minute 30 (the same moment as the hook):

```bash
cd /Users/amir/venv/sports-movement-intel
.venv/bin/python -c "
import json, pandas as pd
d = 'data/normalized/skillcorner/1886347/'
m = json.load(open(d + 'match.json'))
names = {m['home_team']['team_id']: m['home_team']['name'], m['away_team']['team_id']: m['away_team']['name']}
t = pd.read_parquet(d + 'tracking.parquet')
seq = t.loc[t.physical_time_ms >= 1_832_000, 'sequence'].min()
f = t[t.sequence == seq].assign(team=lambda x: x.team_id.map(names).fillna('-'))
print(f'frame {seq}  ·  {len(f)} rows  ·  clock {f.source_clock.iat[0]}')
print(f.sort_values(['entity_type', 'team', 'x_m'])[['entity_type','team','jersey','x_m','y_m','is_detected','position_source']].to_string(index=False))
" 2>/dev/null
```

Expected output:

```text
frame 18320  ·  23 rows  ·  clock 00:30:32.00
entity_type        team jersey    x_m    y_m  is_detected       position_source
       ball           -   None -35.66 -22.05         True              observed
     player Auckland FC     27 -36.16  11.27         True              observed
     player Auckland FC     10 -35.14   2.12         True              observed
     player Auckland FC     28 -34.14 -17.90         True              observed
     player Auckland FC     22 -32.45 -22.83         True              observed
     player Auckland FC     15 -30.20 -30.45         True              observed
     player Auckland FC     14 -24.96 -15.16         True              observed
     player Auckland FC      6 -23.82  -7.82        False provider_extrapolated
     player Auckland FC     17 -22.29  10.46         True              observed
     player Auckland FC      4  -9.46 -16.92        False provider_extrapolated
     player Auckland FC     23  -7.22  -3.11        False provider_extrapolated
     player Auckland FC     12  27.41  -2.82        False provider_extrapolated
     player   Newcastle      1 -50.25  -1.32         True              observed
     player   Newcastle     15 -37.29  -0.11         True              observed
     ...                                 (11 Newcastle players, all observed)
```

Talking points:
- One frame = 23 rows: 11 Auckland FC, 11 Newcastle, 1 ball. `x_m`/`y_m` are metres from the centre spot (the pitch is about ±52 m long).
- The frame tells a story: the ball is at −35 m, deep in Newcastle's half. Newcastle's keeper (#1) is at −50 m, on his line, and their whole team is packed between −37 and −23 m. Auckland is attacking.
- `is_detected` is the honesty flag. The four Auckland players far from the ball (#6, #4, #23, and #12 at +27 m, the last man back) are **off camera**: SkillCorner *estimated* them (`provider_extrapolated`). Broadcast cameras follow the ball. We keep this flag all the way through the pipeline.
- Punchline for this shot: *"Number 12 is standing alone at plus 27 metres. The camera doesn't know he exists. Honestly, neither does his striker."*

**SPEECH:**

> First, what *is* tracking data? Broadcast or in-stadium cameras record where every player is, many times per second. For football, SkillCorner publishes open data at **10 frames per second**: x, y, player id, team, plus a flag that tells you whether a player was actually seen by the camera or estimated. It's the difference between "I saw him there" and "trust me, bro". That flag matters, and we keep it all the way through the pipeline.
>
> **[SCREEN: Catalog view]**
>
> Here's the catalog. Every source is pinned to an exact Git commit and checksummed, so the data you download next year is byte-for-byte the data I used today.
>
> And here's the honest part. I also have NBA SportVU tracking on my laptop, a Christmas Day Warriors–Cavaliers game, 25 frames per second, plus Metrica samples. You won't see them in this video, because their data license isn't stated. The downloader on GitHub has an MIT licence, but that's a licence for the *code*, not for the data. So public mode hides them, and the API literally returns 404 for those sessions. SkillCorner is MIT. That's what's on screen. Final score: lawyers 1, me 0. And honestly, that's the correct result.
>
> One more promise: this is a **historical match replay**, not a live feed from the stadium. We replay a finished match into Kafka at any speed, from half speed to a hundred times faster. Why replay? Because it behaves exactly like a live stream to everything downstream, and it's *reproducible*. Same match, same seed, same answer. Every time.
>
> **[SCREEN: architecture.png, cover or circle the "replay" box]**
>
> And here's the key design idea. Look at the Kafka topic. Spark has no idea whether a frame came from my replay service or from a stadium. It just sees a tracking message: session, match, sequence, positions, timestamps, in the same contract. So going live means swapping **one box**: instead of a replay service reading parquet, you put a small producer that reads the provider's live feed and writes the *same* messages to the *same* topic. The validation, the reorder buffer, the windows, the sinks and the dashboard all stay exactly the same code.
>
> So why not do it live right now? Because live tracking feeds are licensed per league, per season, and priced for clubs and broadcasters, not for a guy with a YouTube channel and a MacBook. The replay is my stand-in. And because it goes through the same Kafka topic, with real event times, duplicates and late frames, the pipeline can't tell the difference. I checked. It doesn't even ask.
>
> Later, in the "make it big" chapter, I'll show what connecting a real live feed would take, and what changes when the match *isn't* already over.

---

### Chapter 3 — Architecture overview (≈3 min)

**On screen:** `docs/img/architecture.png` full screen. Zoom into each column as you talk (or use a slow pan in the edit). Then `docker compose ps`.

| column | tech | role |
|---|---|---|
| 1 Sources | SkillCorner, Metrica, SportVU | pinned, checksummed, licence-tagged |
| 2 Acquire | `smip sources` | download, adapters to one canonical contract, catalog |
| 3 Replay → Kafka | replay service, Kafka 4.3 KRaft | paced replay, seeded faults, idempotent producer |
| 4 Spark 4.1 | bronze query, engine query | validate/quarantine; stateful features with `applyInPandasWithState` |
| 5 Storage | Iceberg 1.11 (REST catalog, S3 gateway), ClickHouse 25.8 | the lakehouse of record; fast serving reads |
| 6 Serving | FastAPI, light ML, grounded analyst, React | metrics, similar moments, change points, answers with evidence |

**SPEECH:**

> **[SCREEN: architecture.png — whole picture]**
>
> Here's the whole system on one page. Read it left to right, like a play developing.
>
> **Column one, sources.** Public tracking data, pinned to a commit. **Column two**, the adapters. Every provider has its own coordinates, its own clock, its own idea of what a "frame" is. Every provider thinks it's the main character. The adapters turn all of it into one canonical contract: metres, centre origin, attack direction normalized, written as parquet. After this point, nothing downstream knows or cares which provider it came from.
>
> **Column three, replay and Kafka.** The replay service reads that parquet and produces frames into Kafka, keyed by session and match. So every frame of one replay lands on the same partition, in order. It's deterministic: pause, resume, change speed, and the event times don't change.
>
> **Column four, Spark Structured Streaming. Two queries.** The *bronze* query validates each record against the contract. If a record's broken, it goes to quarantine. The *engine* query is the brain: a stateful feature engine running inside `applyInPandasWithState`. It de-duplicates, reorders, applies corrections, and computes kinematics, sixty-second windows and team shape.
>
> **Column five, storage. Two stores, two jobs.** Apache Iceberg is the lakehouse of record: bronze, silver, gold and ops tables, sitting as real files in a folder on my disk, `./lakehouse`, behind a REST catalog. ClickHouse is the serving store: fast reads for the dashboard. Iceberg is the archivist who remembers everything. ClickHouse is the friend who answers before you finish the question.
>
> **Column six**: FastAPI serves frames, metrics, heatmaps, the ML features and the analyst, and React draws it.
>
> **[SCREEN: point to the dashed violet arrows at the bottom]**
>
> And these dashed arrows are the most important thing on the page. The *same* feature engine runs a second time, in plain batch mode, over the clean parquet. No Kafka, no Spark. Then we compare the two, row by row. If streaming and batch disagree, something is wrong, and we'll know. That's the **parity check**, and it's the spine of this whole video. If this video has a villain, it's the phrase "the numbers are slightly different".
>
> **[SCREEN: terminal — `docker compose ps`]**
>
> Seven services from one compose file: ClickHouse, the object store, the Iceberg REST catalog, Kafka, the API, replay, and Spark, plus a one-shot job that creates the Kafka topics and exits. The footer of the diagram shows the measured memory. It all fits in a 7.65 GiB Docker VM, and every port is bound to 127.0.0.1 only. Seven containers, one laptop, and a fan that occasionally sounds like it's cleared for take-off.

---

### Chapter 4 — The journey of one frame (≈4.5 min)

The core engineering chapter. Keep it moving: one frame, six stops. Show the Spark UI (`http://127.0.0.1:14040`) briefly and the ClickHouse/Iceberg bits in the terminal.

1. Adapter → canonical frame (metres, `physical_time_ms`, `is_detected`)
2. Replay → Kafka (`smip.tracking.v1`, key = `session|match`, `acks=all`, idempotent producer)
3. Bronze query → validate → Iceberg bronze / quarantine
4. Engine query → reorder buffer (2 s) → dedup → corrections → kinematics → windows → team shape
5. Sinks → Iceberg silver/gold (commit tag) + ClickHouse `ReplacingMergeTree`
6. API → dashboard, bounded by the replay cursor

**SPEECH:**

> **[SCREEN: architecture.png, highlight column 2 → 3]**
>
> Let's follow one single frame, minute 30 of the hero match, from a parquet file to a dot on your screen. Six stops.
>
> **Stop one: the adapter.** SkillCorner gives us positions and a video frame number. We convert it to metres from the centre spot and compute `physical_time_ms`: real match time, with half-time taken out. That's one of **four clocks** in this system: the game clock, physical time, replay event time, and processing time. They are *never* mixed. Mixing clocks is how sports pipelines lie to you. Four clocks: more than a Swiss train station, and just as strict about it.
>
> **Stop two: Kafka.** The replay service stamps the frame with a replay event time and produces it to `smip.tracking.v1`. The key is `session|match`. That gives us ordering per replay without a global order, which Kafka can't give you anyway. The producer is idempotent with `acks=all`, and it checkpoints every two seconds, so if replay crashes it resumes and re-sends, marked with `attempt+1`.
>
> **Stop three: the bronze query.** Spark reads the record and validates it against the contract. Good record? Into Iceberg bronze. Bad record? We still keep it — into quarantine. It's not punished. It just sits in a corner with a label on it, thinking about what it did. Quarantine is not a trash can we empty later. It's a real table: the raw bytes, a reason code for why it failed, and which session it belonged to. That way a broken JSON never quietly disappears, and you can open it later and see exactly what arrived. And for that session tag, we do not parse the broken body and hope. We take `session` and `match` from the *Kafka key*, which is intact even when the payload is garbage. We never invent meaning for a bad record.
>
> **[SCREEN: Spark UI slide / http://127.0.0.1:14040/StreamingQuery/]**
>
> **And here is that job, live.** Two streaming queries in one Spark app: *bronze* validating on the left, *engine* doing the stateful work on the right. Same Kafka topic in, two different responsibilities — and you can watch the micro-batches tick while the replay is running.
>
> **Stop four: the engine.** This is the fun one. Each replay session has its own state inside Spark: a small **reorder buffer**, two seconds of frames. Think of the players' tunnel before kickoff: everyone lines up in the right order before they walk out. If a frame shows up a bit late, it slots back into place. If the same sequence number arrives twice, the copy is dropped. If a correction arrives while the original is still waiting, the correction wins.
>
> Once a frame leaves the buffer, the physics happens. We smooth positions with a *causal* filter. Causal means it only looks backwards, which is why batch and stream can agree exactly. Then we compute speed, distance, high-speed running above 5.5 metres per second, and sprints above 7. We drop "teleports", anything faster than 12.5 metres per second, because Usain Bolt tops out around 12.4 and nobody in the A-League is Usain Bolt.
>
> Then windows: sixty seconds of **match time**, not wall time. That's the trick that makes this whole thing reproducible. A sixty-second window contains exactly the same frames whether I replay at half speed, twenty times, or flat out. Pause for coffee, resume, change speed: same windows, same numbers.
>
> And team shape for every frame: width, depth, the convex hull area, and the defensive line height. That's the average depth of the back four, in metres from their own goal.
>
> **[SCREEN: terminal — `.venv/bin/smip lakehouse inspect`, or `ls lakehouse/data/warehouse`]**
>
> **Stop five: the sinks.** Two stores, and each one is made retry-safe in its own way. Every Iceberg commit carries a tag, `smip.commit=query:batch`, so if Spark retries a micro-batch that already landed, we see the tag and skip it. ClickHouse uses `ReplacingMergeTree` keyed on the natural key, so a replayed row simply replaces itself. There's even a sink ledger recording every batch, so a retry is *visible*, not hidden.
>
> And look, these are real Iceberg tables on my disk. Parquet files, metadata, snapshots. Point this at S3 and Glue, and it's the same format.
>
> **Stop six: the dashboard.** The API reads ClickHouse. And everything "live" is bounded by the **replay cursor**, the furthest point the engine has actually processed. At minute 30, a heatmap shows minutes 0 to 30. Not a peek at the future. No spoilers. This dashboard is more spoiler-safe than your group chat.
>
> **[SCREEN: Pipeline view — latency numbers]**
>
> How fast is it? At 20× paced replay, a frame goes from produced to queryable in ClickHouse in **3.4 seconds at the median, 6.3 at p95**, with a two-second trigger. Flat out, the full match, 59,042 frames, goes end to end in 168 seconds. That's about 35 times real time, on a laptop. Seconds, not milliseconds, and I'll say that plainly: this is a replay analytics system, not a low-latency betting feed. If you came here for betting tips: wrong video. And please don't.

---

### Chapter 5 — Break it on purpose (≈4 min)

The signature chapter. **Face cam here if you use one.** Show the `demo-soccer-faults` session in the Pipeline view, then the terminal parity result.

- Deep link: `http://127.0.0.1:18000/?session=demo-soccer-faults&view=pipeline`
- Fault table from `docs/FAILURE_SEMANTICS.md` on screen (simple slide or the doc itself)
- Terminal: the `make verify` block from `docs/STATUS.md` (or re-run just the parity check)

| fault | rate |
|---|---|
| duplicate | 3% |
| out-of-order | 2% |
| delay (5 frames late) | 1% |
| correction (+0.5 m, then the truth) | 1% |
| malformed JSON | 0.2% |

**SPEECH:**

> Every streaming demo looks great when the data is perfect. Real streams are not perfect. So let's be mean to it. Monday-morning-production-incident mean.
>
> **[SCREEN: fault table]**
>
> Same league, a different match, replayed with seeded faults. Three percent of frames are duplicated. Two percent arrive out of order. One percent are delayed five frames. One percent are *wrong*: we shift a player half a metre, and then send the true frame three frames later as a correction. And two in a thousand are truncated, broken JSON. It's seeded with seed 7, so I can do exactly this again tomorrow. Basically, I built a small chaos monkey and gave it a football shirt.
>
> **[SCREEN: Pipeline view — counters]**
>
> Here's what the pipeline did with it. **1,748 duplicates dropped. 589 corrections applied. 114 malformed records quarantined**, each one still tagged with the replay it came from.
>
> Now the moment of truth. We take the *clean* parquet, with no Kafka, no faults and no Spark, and run the exact same feature engine over it in batch. Then we compare every final window.
>
> **[SCREEN: parity badge / terminal verify block]**
>
> 2,209 out of 2,209 player windows. 204 out of 204 team windows. 41,579 out of 41,579 heatmap cells. **Zero differences.** The stream took a beating and came out with exactly the right answer. Honestly, I've had worse days in production. And I came out with *more* differences.
>
> **[SCREEN: Lineage panel]**
>
> And lineage: source frames, then Kafka, then bronze, then silver, then gold. You can see where every extra record went. Bronze has more valid rows than the source, which is the duplicates. Silver has exactly the source count, because the duplicates are gone.
>
> Now, the careful wording. I'm **not** claiming "exactly-once end to end". That's the "I've never lost my keys" of data engineering: a lovely claim, and nobody believes it. Kafka here is at-least-once, and I'm happy to say it. The claim is narrower and testable: **effectively-once results per replay session**. At-least-once delivery, plus a deterministic engine, plus idempotent sinks. And it's tested on every `make verify`. If a claim isn't in a test, I don't put it in a YouTube video.

---

### Chapter 6 — Dashboard tour (≈4.5 min)

Quick, visual, one feature per ~40 seconds. Use the deep links from `docs/YOUTUBE_RUNBOOK.md`.

| beat | link |
|---|---|
| overlays: hulls, defensive line, trails | `?session=demo-soccer-hero&view=live&t=1832000` |
| Voronoi ("not pitch control") | `...&overlays=voronoi,trails,labels` |
| player heatmap | `...&overlays=heatmap,labels&pick=skillcorner:player:23418` |
| Players view | `?session=demo-soccer-hero&view=players` |
| shape changes on the timeline | live view timeline markers |
| similar moments | `...&t=2410000&similar` |
| grounded analyst + a refusal | analyst panel |

**SPEECH:**

> **[SCREEN: live view, overlays]**
>
> Okay, the payoff. The shaded polygons are each team's **convex hull**, the space the outfield players cover right now. This line is the **defensive line**. The tails are three-second trails. Everything is drawn from real served positions. Nothing's interpolated, nothing's invented.
>
> **[SCREEN: Voronoi]**
>
> Voronoi: every point on the pitch coloured by the nearest player. Pretty, right? And here's where I have to be the annoying engineer: this is **not pitch control**. Pitch control needs velocities, reaction times and ball travel. This is pure geometry, "who's closest". Fun to look at. Not a tactical model. The docs say so too. Voronoi is to pitch control what a horoscope is to a weather forecast: it *looks* scientific.
>
> **[SCREEN: click a player → heatmap]**
>
> Click a player and you get their heatmap: time spent in each zone, on a 21-by-13 grid. And watch what happens when I scrub backwards. The heatmap shrinks. It only knows about the match *up to this moment*. That's the replay cursor again. It literally forgets the future. Must be nice.
>
> **[SCREEN: Players view]**
>
> The Players view: distance, high-speed running, sprints, and a mini map per player. One honesty note: a few top-speed values look spicy, above 40 km/h. Either the A-League secretly signed a cheetah, or, more likely, the provider is extrapolating positions when a player is off camera. It's flagged, and I treat max speed as *indicative*, not gospel.
>
> **[SCREEN: timeline markers]**
>
> Those little markers on the timeline are **shape changes**, found with an algorithm called PELT from the `ruptures` library. It looks for moments where a team's width, depth or line height *shifts* and stays shifted. Click one and the replay jumps there, and the panel tells you what moved, before versus after, in metres. There's no ground truth for "tactical change", so there's no accuracy number. The model card says exactly that. Well, the real ground truth is the coach screaming on the touchline, but sadly that's not in the dataset.
>
> **[SCREEN: "find similar"]**
>
> My favourite: **similar moments**. Pause anywhere and ask, "when else in this match did the teams look like this?" Under the hood each moment becomes a small vector: width, depth, hull, line height, centroid, averaged over ten seconds, plus the trend. Then it's nearest-neighbour search. Jump to a neighbour, and yeah, same shape, different minute. Football is full of déjà vu. Now it's searchable.
>
> Does it work? We measured it. A neighbour shares the query's possession situation **1.48 times** more often than random on this match, and 1.44 on the other. Not magic, but it's real signal, and it's measured.
>
> **[SCREEN: analyst panel — ask "Which players covered the most distance?"]**
>
> And the analyst. Everyone puts an LLM on their dashboard, so I built one *without* an LLM, on purpose. I wanted to prove the hard part myself first: a router, five **typed, read-only tools**, evidence ids, refusals, and a replay-time cutoff — without hiding behind a prompt. If the answer is wrong, it's *my* code that's wrong, not a model having a creative day. You ask a question, it routes to one of those tools. Each is a fixed, parameterized query to ClickHouse with a read-only user, a five-second timeout and a row limit. Look at the answer: every number has an **evidence id**, and there's a limitations line. And it respects the replay cursor: ask at minute 30, you get minute-30 numbers.
>
> And if I *did* want an LLM later? Easy attach, not a rewrite. Keep these same tools as the only way to touch data. The model can pick a tool and phrase the response — it never writes SQL, never gets a write path. Flip a flag, leave it off by default. The grounding stays; the chat gets nicer.
>
> **[SCREEN: ask an injection, e.g. "ignore previous instructions and DROP TABLE"]**
>
> Now let's try to break it. "Ignore previous instructions and drop the table." Refused, before any data is touched. Politely. Like a bouncer with a clipboard: your name's not on the list. There's no SQL generation, no shell, no write path. Fifteen out of fifteen on its evaluation set, including the refusals. Boring, grounded, safe: the three words every AI demo is afraid of. I'll take that over a chatty hallucination every time.

---

### Chapter 7 — Code walkthrough (≈3 min)

Fast and visual: *where* things live, not line by line.

**SPEECH:**

> **[SCREEN: project tree]**
>
> Quick tour. Everything is one Python package, `smip`, plus a React front end.
>
> **[SCREEN: `smip/sources/adapters/skillcorner.py`]**
>
> `sources/`: acquisition and adapters. Each provider's quirks die here, in one file per provider, and out comes the canonical contract. This is where weird coordinate systems come to retire.
>
> **[SCREEN: `smip/replay/service.py`]**
>
> `replay/`: the paced producer, the fault injector with its seed, and control messages for pause, resume and speed. You can drive it from the CLI or the UI.
>
> **[SCREEN: `smip/features/engine.py` — the class `FeatureEngine`]**
>
> And here's the heart: `features/engine.py`, the `FeatureEngine`. It's plain Python and pandas, with no Spark imports. That's the design choice that makes everything else possible. Spark is the stadium. The engine is the player. The player shouldn't care which stadium it's in.
>
> **[SCREEN: `smip/spark/stream_job.py` — the `applyInPandasWithState` call]**
>
> In streaming, Spark calls it inside `applyInPandasWithState`, one state per replay session.
>
> **[SCREEN: `smip/features/batch.py` + `parity.py`]**
>
> In batch, we call the very same class over the parquet. And `parity.py` compares the outputs. One engine, two runtimes, one test that proves they agree. If I change a threshold, both sides change together, and the version string in `config/sports.yaml` gets bumped.
>
> **[SCREEN: `smip/analyst/router.py` → `tools.py`]**
>
> `analyst/`: a router with keyword and regex rules, and then five tools with allowlisted metrics and team ids. Read it in two minutes. That's the point. If your analyst needs a forty-page prompt to behave, that's not an analyst, that's a hostage negotiation.
>
> **[SCREEN: `frontend/src/Stage.tsx`]**
>
> And the front end: `Stage.tsx` draws the pitch, hulls, Voronoi and trails on a canvas. Just React and TypeScript, no heavy charting library.
>
> **[SCREEN: terminal — `make verify` output]**
>
> The whole thing is guarded by `make verify`: fifteen checks. Unit tests, lint, stack health, parity and lineage for each demo session, the fault counters, the analyst eval, the ML lift, the public-demo guard and the UI build. It writes its own result into `docs/STATUS.md`. **Fifteen out of fifteen.** The README only quotes numbers that a command in the repo produced. One red check, and the README loses its bragging rights.

---

### Chapter 8 — Tradeoffs and the next level (≈4.5 min)

**On screen:** architecture.png again. Optional four-lane slide: **Data → Models → Platform → Product**.

**SPEECH:**

> A few decisions I'd defend in any interview.
>
> **Why replay instead of "real live data"?** Because live sports tracking isn't public, and replay is *better for engineering*: it's reproducible. I can inject the same faults tomorrow and get the same counters.
>
> **Why Iceberg *and* ClickHouse?** Different jobs. Iceberg is the open, durable record, in a format any engine can read. ClickHouse is the fast serving layer. Asking one store to do both usually means doing both badly. It's like asking your goalkeeper to take the corners too: technically possible, tactically brave.
>
> **Why the same engine in batch and stream?** Because "streaming gives slightly different numbers" is the most common silent bug in data platforms. Here, it's a failing test.
>
> **Why no LLM in the analyst?** Grounding. Every number has to come from a tool call with evidence. An optional language layer can come later, but disabled by default, and never writing SQL.
>
> **Limits, said out loud:** one Kafka broker, Spark in local mode, one laptop. No multi-match concurrency measured. Latency in seconds. And Airflow exists as an optional profile, but Airflow plus the full streaming stack don't fit in 7.65 gigs together. They've been politely asked to take turns.
>
> **So, next level. Same architecture, bigger boxes.** And a bigger cloud bill, which I'll leave as an exercise for the viewer.
>
> **[SCREEN: architecture.png, the "replay" box swapped for a "live feed adapter" box (simple overlay in the edit)]**
>
> **Going live.** Remember the promise from the start: one box changes. Here's what that box has to do, and what live data adds that a replay never throws at you.
>
> **One: a live ingest adapter.** Providers push frames over a websocket, a streaming API or their own SDK. A small, boring service connects, converts their coordinates into our contract (metres, centre spot, our four clocks) and produces to the same `smip.tracking.v1` topic, keyed by match. Boring is the goal. If the adapter is exciting, something's wrong.
>
> **Two: the stream never "ends" on cue.** In replay I send an `end_of_stream` message. Live, the final whistle comes from the provider's match status, and if the feed just goes quiet, the existing 120-second idle timeout closes the session.
>
> **Three: real lateness, real corrections.** Live feeds really do send late frames and corrected positions. My fault injector was rehearsal for exactly this. The two-second reorder buffer becomes a knob: bigger means more correct, smaller means fresher. You tune it per provider with measured lateness, not vibes.
>
> **Four: parity moves to after the match.** You can't compare against a clean batch run while the match is still on. So you compare later: when the provider delivers its official post-match file, you run the same engine in batch over it and check how far the live results drifted. Same test, different timing.
>
> **Five: latency becomes a product decision.** Today, two-second triggers and seconds of latency are fine. For a live bench tablet you'd shrink the trigger, keep the hot path in ClickHouse, and let Iceberg take its time. Fast lane for the coach, slow lane for the archive.
>
> **Six: many matches at once.** A Saturday with ten games means ten sessions in parallel: more Kafka partitions, keyed by match, and Spark scaled out instead of `local[3]`. The per-session state already isolates matches, so they don't trip over each other.
>
> To be clear, I haven't run this against a real live feed. That needs the licence. But the seam is already there, and the replay exercises everything on the far side of it. The day someone hands me a live feed, I write one adapter, not a new platform. Ideally the same day they hand me the invoice.
>
> **Data.** Event data, like StatsBomb 360 and Wyscout, is already downloaded but not normalized yet. Join passes and shots to the tracking, and "the block dropped deeper" becomes "the block dropped deeper *after they lost the ball in midfield*".
>
> **Models.** Real pitch control with velocities. Cross-match similar moments with a vector store, so "find this shape in *any* match", not just this one. Learned embeddings from a temporal encoder instead of hand-picked features. And human-labelled pairs for a proper precision-at-k.
>
> **Platform.** This maps almost one-to-one onto AWS: Kafka to MSK, Spark to EMR or Glue streaming, the object store to S3, the REST catalog to Glue Data Catalog, ClickHouse to ClickHouse Cloud or a self-managed cluster. Partition by match, run many sessions in parallel, and automate Iceberg compaction and snapshot expiry. That mapping is in `docs/AWS_MAPPING.md`.
>
> **Product.** A coach's workflow: "show me every time we defended this narrow in the second half", a clip list built from similar moments, and shape changes lined up with substitutions.
>
> The parity test comes with us at every step. Bigger system, same promise: stream equals batch.

---

### Chapter 9 — Run it yourself + closing (≈1 min)

**On screen:** README quickstart, then the hero view one last time.

**SPEECH:**

> Want to run it? Clone the repo. `make setup`, `make data` for about 550 megabytes of open data, then `docker compose up -d` and `make demo-seed` for the demo sessions. Open 127.0.0.1:18000. `make verify` tells you if everything's green. Adding a match is one command: `smip sources available` lists them, and `smip sources download --match` grabs the one you want.
>
> **[SCREEN: hero replay]**
>
> Recap: public tracking data, replayed through Kafka, computed by a stateful Spark engine, stored in Iceberg and ClickHouse, served with evidence, and proven against a batch run even when I sabotage it.
>
> If you made it this far, you now know more about sixty-second tracking windows than most people ever will. Congrats, I think.
>
> Link's in the description. Replay a match, break it, and tell me in the comments what you'd build on top. And if you find a bug: congratulations, you're now a contributor. See you in the next one.

---

## Production Tips

- **Warm everything first.** `make demo-seed` takes ~12 minutes. Never record it; record the result.
- **Public mode:** `SMIP_PUBLIC_DEMO=1 docker compose up -d api` before recording. Double-check the catalog shows SkillCorner only.
- **Freeze frames:** append `&paused` to deep links for voice-over.
- **Optional live replay on camera** (Chapter 4 or 5), handed to the replay service so it can be paused and re-sped:

  ```bash
  .venv/bin/smip replay start --match skillcorner:1959846 --speed 20 --session live-take-1 --no-inline
  .venv/bin/smip replay control live-take-1 pause
  .venv/bin/smip replay control live-take-1 speed --speed 50
  .venv/bin/smip replay control live-take-1 resume
  ```

  `1959846` is Victory 3–4 Western United, seven goals, a good one for the "fun" factor.
- **Terminal:** 14–16 pt font, clean history, notifications off.
- **B-roll:** slow pan across `docs/img/architecture.png`; the Voronoi toggle; the parity badge flipping to "exact".
- **Chapters:** paste the timestamps into the description.

## Claims to say, and claims to avoid

| say | avoid |
|---|---|
| "historical match replay" | "live data", "real-time from the stadium" |
| "effectively-once per session", "parity with the batch run" | "exactly-once end to end" |
| "geometric Voronoi" | "pitch control" |
| "grounded analyst with typed tools" | "AI coach" |
| numbers from `docs/BENCHMARKS.md`, with the hardware (Apple M3, 7.65 GiB Docker VM) | NBA or Metrica footage or numbers on screen |

---

## Suggested Title Options

- "I Sabotaged My Own Streaming Pipeline — and It Still Got Every Number Right"
- "Replaying a Football Match Through Kafka, Spark and Iceberg (on a Laptop)"
- "Real Player-Tracking Data → Streaming Lakehouse → Tactical Dashboard | One Docker Compose"
- "Batch = Stream, Row for Row: A Sports Streaming Lakehouse Project"
- "22 Players, 10 Hz, Zero Differences: Building a Sports Movement Platform"

---

## YouTube Description Template

```
I built a sports movement intelligence platform on my laptop: real player-tracking data (SkillCorner open data, A-League) replayed through Kafka, processed by a stateful Spark Structured Streaming engine, stored in Apache Iceberg and ClickHouse, and served to a React tactical dashboard.

Then I injected duplicates, late frames, corrections and broken JSON — and the streaming results still matched a clean batch run row for row.

This is a historical match replay, not a live feed. All numbers were measured on an Apple M3 (Docker VM 7.65 GiB).

WHAT'S COVERED:
- Architecture: replay → Kafka → Spark → Iceberg + ClickHouse → FastAPI → React
- The journey of one frame: four clocks, reorder buffer, kinematics, 60 s match-time windows
- Fault injection: 1,748 duplicates dropped, 589 corrections, 114 quarantined — exact parity
- Team shape, hulls, defensive line, geometric Voronoi, heatmaps
- Similar moments (kNN, 1.48× lift over random) and shape change points (PELT)
- A grounded analyst with typed read-only tools and evidence ids (no LLM)
- Code walkthrough and how I'd scale it

TECH STACK:
- Apache Kafka 4.3 (KRaft)
- Apache Spark 4.1 Structured Streaming (applyInPandasWithState)
- Apache Iceberg 1.11 (REST catalog)
- ClickHouse 25.8
- FastAPI, React + TypeScript
- ruptures (PELT), NumPy kNN
- Docker Compose, Python 3.12

TIMESTAMPS:
0:00 — Hook
1:30 — The data, replay vs live
4:00 — Architecture
7:00 — The journey of one frame
11:30 — Break it on purpose (faults & parity)
15:30 — Dashboard tour
20:00 — Code walkthrough
23:00 — Tradeoffs, going live & next level
27:30 — Run it yourself

DATA:
SkillCorner open data (MIT) — credit SkillCorner. Other datasets without a stated data license were kept local and are not shown.

GitHub: [YOUR REPO LINK HERE]

#DataEngineering #Kafka #ApacheSpark #ApacheIceberg #ClickHouse #SportsAnalytics #Streaming #Portfolio
```

---

## Checklist Before Recording

- [ ] `docker compose ps` — all core services healthy
- [ ] `make verify` — 15/15 green (check `docs/STATUS.md` date)
- [ ] API restarted with `SMIP_PUBLIC_DEMO=1`; catalog shows SkillCorner only
- [ ] `demo-soccer-hero` and `demo-soccer-faults` sessions load; the Pipeline view shows the fault counters and the exact parity badge
- [ ] Deep links tested (hero at `t=1832000`, Voronoi, heatmap pick, similar at `t=2410000`)
- [ ] Analyst: a distance question and an injection prompt tested
- [ ] Spark UI http://127.0.0.1:14040 open (two streaming queries visible)
- [ ] `docs/img/architecture.png` open full screen
- [ ] Editor tabs ready: `smip/sources/adapters/skillcorner.py`, `smip/replay/service.py`, `smip/features/engine.py`, `smip/spark/stream_job.py`, `smip/features/parity.py`, `smip/analyst/router.py`, `frontend/src/Stage.tsx`
- [ ] Terminal clean, font 14+, notifications off, browser 1600×1000
- [ ] Optional: `live-take-1` replay commands tested once
- [ ] Record ~32 min raw, cut to 25–28

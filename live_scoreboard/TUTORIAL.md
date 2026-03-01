# YouTube Tutorial Script: Real-Time Multi-Sport Scoreboard Platform

**Target length**: 12-15 minutes
**Audience**: Data engineers, backend engineers, streaming enthusiasts
**Format**: Screen-share with narration -- read/paraphrase the talking points below while showing what's indicated by `[SHOW]` cues.

---

## [0:00 - 1:00] Introduction

**[SHOW]** The scoreboard UI at `localhost:5050` with live games visible.

**Talking points:**

> Hey everyone. In this video I'm going to walk you through a real-time multi-sport scoreboard platform that I built as a data engineering project.
>
> This platform ingests live data from 5 major sports leagues -- NBA, NFL, Premier League, La Liga, and Champions League -- streams it through Apache Kafka, and serves it to three parallel consumers: a live web scoreboard with animated match trackers, a PySpark streaming pipeline that writes to PostgreSQL, and a batch player statistics pipeline.
>
> The entire stack runs in 14 Docker Compose services. One command and everything spins up.
>
> What makes this interesting from an engineering perspective is the event-driven architecture, the unified message schema across very different data sources, and the live match tracker that pushes the limits of what's possible with free, publicly available sports APIs.
>
> Let's dive in.

---

## [1:00 - 2:30] Architecture Overview

**[SHOW]** The architecture diagram from the presentation (Slide 4), or open `PRESENTATION.md` and scroll to the architecture section. Alternatively, open the README on GitHub showing the Mermaid diagram.

**Talking points:**

> Let me walk you through the architecture.
>
> On the left we have our data sources. For the NBA we use the `nba_api` Python SDK combined with ESPN's API for coordinate data. For NFL, Premier League, La Liga, and Champions League we use ESPN's public REST API -- and importantly, all of these are completely free, no API keys required.
>
> Each league has its own Kafka producer written in Python. These producers run in their own Docker containers and poll the APIs every few seconds. They normalize the raw data into an enriched unified JSON schema and publish to league-specific Kafka topics -- so we have `nba_scores`, `nfl_scores`, `premier_league_scores`, and so on.
>
> The key design decision here is that producers only publish when the data actually changes. We compute a fingerprint of each game's state -- scores, status, number of plays -- and skip publishing if nothing is new. This prevents flooding Kafka with identical messages.
>
> From Kafka, we have three consumers running in parallel:
> - First, a Flask web application that reads from all 5 topics and serves a live scoreboard UI.
> - Second, a PySpark Structured Streaming job that writes to 3 PostgreSQL tables.
> - And third, a batch pipeline that fetches player season statistics every 6 hours.
>
> This is classic event-driven architecture -- producers are completely decoupled from consumers. Adding a new league means writing one new producer. Adding a new consumer means subscribing to the existing topics. Neither side needs to know about the other.

---

## [2:30 - 4:00] Data Sources Deep Dive

**[SHOW]** Open `shared/soccer_producer.py` in the editor. Scroll to the `fetch_match_details` function.

**Talking points:**

> Let's talk about data sources, because this is one of the most important engineering decisions in the project.
>
> All our data comes from free, public APIs. ESPN's scoreboard endpoint gives us live scores, game status, and quarter or half scores. Their summary endpoint goes deeper -- for soccer it returns goals, cards, substitutions, 20+ statistics fields like possession and shots, full commentary play-by-play, team lineups with formations and even team colors.
>
> For the NBA, we use the `nba_api` Python package which wraps NBA.com's endpoints, plus ESPN for coordinate data that helps us position the ball on the court.
>
> Rate limiting is critical here. We can't hammer ESPN every second. So we use a dynamic caching strategy -- live games get a 3-second cache TTL for soccer, 5 seconds for NFL. Finished games get 30 seconds. We also use `ThreadPoolExecutor` to fetch match details in parallel, with proper error handling for network failures.
>
> Now, here's an important point I want to be transparent about. Professional apps like 365Scores and LiveScore use paid data providers -- Sportradar, Opta, Genius Sports. These providers deliver real x,y coordinate data for the ball and players, with sub-second update frequency. That's how they achieve their smooth, accurate match trackers.
>
> With free ESPN data, we're working with text-based commentary -- "Corner, Liverpool" or "Free kick, Man City" -- and we estimate ball position from those descriptions. This gets us roughly 60 to 70% positional accuracy. It's a significant engineering challenge and a great learning exercise, but it's important to understand that the ceiling is set by the data source, not the code.
>
> If this were a production product, subscribing to Sportradar's API or embedding their LMT widget would be the path to 100% accuracy.

---

## [4:00 - 5:30] Demo: Starting the Platform

**[SHOW]** Terminal window. Run the commands below.

**Talking points:**

> Let me show you how easy it is to get everything running. The entire platform is containerized with Docker Compose.

**[SHOW]** Run:
```bash
cd scoreboard
docker compose up -d --build
```

> One command. This builds all the Docker images and starts 14 services: Kafka in KRaft mode, Kafka UI for monitoring, PostgreSQL, Spark master and worker, 5 league producers, the scoreboard UI, the Spark analytics job, and the player stats fetcher.
>
> Let me check the logs to see what's happening.

**[SHOW]** Run:
```bash
docker compose logs --tail=5 pl-producer
docker compose logs --tail=5 nba-producer
```

> You can see the producers are already fetching data and displaying scores in the console. The Premier League producer shows live games with scores and status. The NBA producer shows tonight's games.
>
> Give it about 30 seconds for everything to initialize, then let's look at the UI.

**[SHOW]** Wait ~20 seconds, then open `http://localhost:5050` in browser.

> And there it is -- live scores across all leagues. Let me also quickly show the Kafka UI.

**[SHOW]** Open `http://localhost:8080`, click on Topics, show the 5 topics and message counts.

> Here in Kafka UI you can see our 5 topics with messages flowing in. This is great for debugging and monitoring.

---

## [5:30 - 7:30] Demo: Live Scoreboard UI

**[SHOW]** Browser at `http://localhost:5050`. Click through matches in different leagues.

**Talking points:**

> The scoreboard UI is a Flask application with a dark-themed interface. It auto-refreshes every 3 seconds by polling a `/api/scores` endpoint that returns the latest data from memory.
>
> Each league has its own section. Let me click on a Premier League match to expand the detail view.

**[SHOW]** Click a live soccer match. Show the tabs.

> When you click a match, you get a tabbed interface. The first tab is the Live tracker -- I'll come back to that in a moment. Let me show you the Stats tab first.

**[SHOW]** Click "Stats" tab.

> This shows over 20 real-time statistics: possession, shots, shots on target, corners, fouls, passes, pass accuracy, tackles, interceptions, clearances, and more. All pulled from ESPN's summary endpoint and updated live.

**[SHOW]** Click "Line-ups" tab.

> The Line-ups tab shows both teams' starting elevens and substitutes, with formations, jersey numbers, and positions. When a substitution happens, you'll see the minute of entry and exit tracked in real time.

**[SHOW]** Click an NBA match, show Box Score and Stats tabs.

> For NBA games, the layout is different -- adapted to basketball. We have a Box Score tab showing every player's minutes, points, rebounds, assists, and all the detailed statistics. The Stats tab shows team-level comparisons like field goal percentage, three pointers, rebounds, turnovers.

**[SHOW]** Click an NFL match, show the drives tab.

> And for NFL, we show drives with yard-line progression, scoring plays by quarter, and team statistics. Each sport gets a presentation tailored to its data model, but the underlying architecture is the same.

---

## [7:30 - 9:00] Demo: Live Match Tracker

**[SHOW]** Click the "Live" tab on a soccer match. Show the SVG pitch with ball animation.

**Talking points:**

> Now let me show you the live match tracker, which is probably the most visually interesting part of the project.
>
> For soccer, you see an SVG football pitch with the ball represented as an animated dot. The ball moves based on ESPN's commentary data -- when a free kick is awarded, the ball moves to the appropriate area. When there's a corner, it goes to the corner spot. When a goal kick happens, it goes to the six-yard box.
>
> Below the pitch you have a possession indicator showing real-time possession with team colors, and a live commentary feed showing the latest events.

**[SHOW]** Point out the ball, the possession bar, and commentary feed.

> Under the hood, this uses a persistent JavaScript class called BallController. It manages the ball's DOM element independently of the UI re-renders -- this is critical because if you rebuild the HTML every refresh cycle, the ball would jump and flicker. Instead, the BallController smoothly transitions using CSS cubic-bezier curves.
>
> The position estimation works by parsing play descriptions. "Corner, Liverpool" maps to a corner position. "Free kick in the defensive half" maps to a calculated position. "Goal kick" puts the ball in the six-yard box. For general play, we use a deterministic hash-based positioning to keep the ball in a reasonable zone.

**[SHOW]** Show an NBA live tracker.

> For NBA, same concept -- SVG basketball court, ball positioned based on ESPN's coordinate data. NBA games actually have richer coordinate data than soccer from ESPN, so positioning is more accurate.

**[SHOW]** Show an NFL live tracker.

> NFL has a football field with yard-line markers and down-and-distance tracking from ESPN's drive data.
>
> Now, I want to be honest about the limitations. With free data, our tracker is roughly 60 to 70% accurate in terms of ball positioning. If you compare this to LiveScore or 365Scores, their trackers are smoother and more precise because they use paid coordinate feeds from Sportradar or Opta. The code architecture supports real-time coordinates -- if you plugged in a Sportradar feed, the BallController would work perfectly with actual x,y data. The bottleneck is the data source, not the implementation.

---

## [9:00 - 10:30] Code Walkthrough

**[SHOW]** Open `shared/soccer_producer.py` in the code editor.

**Talking points:**

> Let me walk you through some key code decisions.
>
> The three soccer producers -- Premier League, La Liga, Champions League -- share 99% of their logic. Instead of duplicating 300+ lines three times, we have a shared `SoccerEngine` class that handles everything: data fetching, normalization, caching, fingerprinting, display, and Kafka publishing.

**[SHOW]** Open `premier_league/producer.py` (show the 12-line wrapper).

> Each league producer is just a 12-line wrapper that instantiates `SoccerEngine` with league-specific parameters -- the Kafka topic name, the ESPN league slug, and a display name. That's it. This eliminated about 500 lines of duplication.

**[SHOW]** Open `scoreboard_ui/app.py`.

> The Flask backend is straightforward. A background daemon thread runs a Kafka consumer subscribed to all 5 topics. When messages arrive, it updates an in-memory dictionary protected by a threading lock. The `/api/scores` endpoint returns this dictionary as JSON. Simple, but effective.
>
> Notice the retry logic -- the Kafka consumer wraps in a while-True loop with exponential backoff, starting at 3 seconds and maxing at 30. This handles the race condition at startup where Kafka might not be ready yet.

**[SHOW]** Open `spark_analytics/stream_to_postgres.py`.

> The Spark streaming job reads from all 5 Kafka topics simultaneously, parses the JSON, and uses `foreachBatch` to write to 3 PostgreSQL tables. It uses `explode()` to flatten the games array into individual rows for events and period scores. Checkpointing ensures exactly-once semantics across restarts.

---

## [10:30 - 11:30] Database and Analytics

**[SHOW]** Open DBeaver (or terminal with `docker exec -it postgres psql -U scoreboard`) connected to the database.

**Talking points:**

> Let me show you the database side. We have 4 PostgreSQL tables.

**[SHOW]** Run:
```sql
SELECT COUNT(*) FROM game_scores;
SELECT COUNT(*) FROM match_events;
SELECT COUNT(*) FROM period_scores;
SELECT COUNT(*) FROM player_season_stats;
```

> `game_scores` is an append-only time series. Every time a score changes, a new row is inserted. This gives you score progression over time.

**[SHOW]** Run:
```sql
SELECT DISTINCT ON (league, game_id)
    league, game_id, home_team, home_score, away_team, away_score, status_text
FROM game_scores
ORDER BY league, game_id, ingested_at DESC;
```

> This query gives you the latest score for every game.

**[SHOW]** Run:
```sql
SELECT event_type, minute, player_name, team
FROM match_events
WHERE league = 'premier_league'
ORDER BY minute;
```

> `match_events` stores goals, cards, and substitutions from soccer. And `period_scores` stores quarter-by-quarter or half-by-half score breakdowns.
>
> The fourth table, `player_season_stats`, uses JSONB for the stats column. This is a deliberate design decision -- NBA, NFL, and soccer have completely different stat categories. Using JSONB lets each sport store its own stat structure without schema migrations.

**[SHOW]** Run:
```sql
SELECT player_name, team, (stats->>'points')::numeric AS ppg
FROM player_season_stats
WHERE league = 'nba'
ORDER BY ppg DESC
LIMIT 10;
```

> Here are the top NBA scorers. You can query JSONB fields like regular columns using the arrow operator.

---

## [11:30 - 13:00] Engineering Practices

**[SHOW]** Open terminal, then code files as mentioned.

**Talking points:**

> Let me quickly cover the engineering practices that bring this project to production quality. The codebase scored 8.5 out of 10 in a comprehensive code review.

**[SHOW]** Open any producer and show `import logging` and `logging.basicConfig(...)` at the top.

> First, every Python file uses the `logging` module instead of print statements. This gives you proper timestamps, severity levels, and the ability to redirect logs.

**[SHOW]** Show a docstring on a function in `shared/soccer_producer.py`.

> Every public function has a docstring. Magic numbers are extracted to named constants -- things like `MAX_DRIVES = 10`, `SUMMARY_TTL_LIVE = 3`, `RECENT_PLAYS_LIMIT = 30`.

**[SHOW]** Open `scoreboard_ui/templates/index.html`, search for `escapeHtml`.

> On the security side, we have an `escapeHtml()` function applied to over 40 dynamic content insertions in the frontend. This prevents XSS attacks -- if a team name or player name contained HTML, it would be escaped before rendering.

**[SHOW]** Open any `requirements.txt` file.

> All 8 requirements.txt files have version range pins. No bare package names.

**[SHOW]** Open `docker-compose.yaml`, point out the pinned image tags.

> Docker images are pinned to specific versions -- `kafka:3.7.0`, not `kafka:latest`. We also have a named volume for Spark checkpoints so streaming state survives container restarts. And a unique constraint on the `game_scores` table to prevent duplicate rows.

---

## [13:00 - 14:30] Production Path & Future Work

**[SHOW]** Slide 11 from the presentation, or just talk through the points.

**Talking points:**

> So what would it take to make this production-ready for a company like a sports media platform?
>
> The number one investment is data. You'd subscribe to Sportradar, Opta, or Genius Sports for real-time coordinate feeds. This immediately solves the tracker accuracy problem. Sportradar even offers embeddable widgets -- their LMT, or Live Match Tracker, is an HTML5 component you can drop into any page for a professional-quality visualization.
>
> On the delivery side, you'd replace HTTP polling with WebSockets or Server-Sent Events. Our current 3-second polling works fine at this scale, but for millions of concurrent users during a big match, push-based delivery is essential.
>
> You'd add Redis as a state store in front of PostgreSQL. Live match state goes into Redis for instant reads, and you use Redis pub/sub to fan out updates to multiple WebSocket gateway instances.
>
> For observability, Grafana connected to PostgreSQL gives you real-time dashboards and alerting. You could set up alerts for blowout games, overtime, or red cards.
>
> On the ML side, the `game_scores` table already contains score progression time series. You could train win probability models on historical data and serve predictions on the scoreboard.
>
> For horizontal scaling, Kafka supports partitioning topics across brokers. Spark can add more workers. Flask can sit behind a load balancer with multiple instances sharing state through Redis.
>
> And adding new leagues is architecturally trivial. The unified message schema means you write one new producer, add a Kafka topic, and every consumer automatically picks it up. Bundesliga, Serie A, MLS, MLB, NHL -- the pattern is the same.
>
> Finally, CI/CD with GitHub Actions for linting, testing, building Docker images, and pushing to a container registry would complete the production story.

---

## [14:30 - 15:00] Closing

**[SHOW]** The scoreboard UI one more time, then the GitHub repo page.

**Talking points:**

> To wrap up -- this project demonstrates a complete, end-to-end streaming data platform: from heterogeneous data sources through Kafka, into a real-time web UI and a PostgreSQL analytics store, all orchestrated with Docker Compose.
>
> The key engineering takeaways are:
> - Event-driven architecture with Kafka naturally decouples producers from consumers.
> - A unified enriched message schema makes heterogeneous data sources interchangeable.
> - The live match tracker pushes the limits of free data with creative text-based inference.
> - And code quality matters -- logging, error handling, dependency pinning, and XSS prevention turn a prototype into a real engineering artifact.
>
> The code is on GitHub at github.com/dreamgroup-il/nba-proj. You can clone it and have the entire platform running with a single `docker compose up -d`.
>
> Thanks for watching. If you have questions, drop them in the comments.

---

*End of Tutorial Script*

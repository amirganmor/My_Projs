# Model card: grounded analyst 0.1.0 (deterministic, no LLM)

**Code:** `smip/analyst/`. **API:** `POST /api/analyst/ask`. **Eval:** `smip analyst eval` (15 cases).

## What it does

It answers a bounded set of questions about one replay session, such as distance leaders, team shape trends,
data-quality gaps, shape changes and similar moments. Every number in an answer comes from a typed tool
call, and each answer lists its evidence ids and limitations.

## Design

- **Routing:** keyword and regex routing to one of five tools: `top_players`, `team_shape_trend`,
  `quality_gaps`, `shape_changes`, `similar_moments`. There is no model-generated SQL.
- **Tools:** each tool is a fixed, parameterized query. Metrics and team ids are checked against
  allowlists.
- **ClickHouse limits** on every query: `readonly=2`, `max_execution_time=5`, `max_result_rows=5000`
  with `throw` on overflow.
- **Refusals:** prompt-injection patterns, SQL fragments, predictions and out-of-scope questions are refused before
  any data is touched. There is no shell and no write path.
- **Cutoff:** in `replay_time` mode (the default), answers never read past `min(engine cursor, UI playhead)`, so an
  answer at minute 30 reflects only minute 30. `post_match` mode uses the engine cursor only.
- **Source text is data:** player and team names from providers are rendered, never interpreted.

## Evaluation (measured)

15/15 cases pass (`data/demo/analyst_eval.json`). The cases cover:
- **grounding:** the answer's numbers are recomputed independently from ClickHouse;
- **top-n and team filters;**
- **similar-moment exclusion;**
- **the replay-time cutoff:** the answer at the cutoff equals the reference at that cutoff, and is less than the full-match value;
- **refusals:** injection, SQL, prediction and off-topic questions.

## Limitations

- **Small question surface.** Unrecognized questions are refused, and the response includes the list of supported questions.
- **English-only keyword routing.**
- **Optional LLM phrasing is not part of v0.1.** Any future external provider must stay disabled by default.

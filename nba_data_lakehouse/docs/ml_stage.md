# ML Stage

## Overview

The ML stage sits after the Silver→Gold transformations and produces three analytical outputs:

1. **Underrated Players** — salary prediction vs actual
2. **Improvement Candidates** — breakout probability
3. **Trade Targets** — composite value score

## Value Model (Salary Prediction)

**Goal:** Estimate a player's market value from their performance profile.

**Features:**
- Demographics: age, years_pro, draft_pick
- Base stats: GP, MIN, PTS, REB, AST, STL, BLK, TOV, FG%, 3P%, FT%
- Advanced: TS%, USG%, OFF/DEF/NET rating, PIE
- Injury: total games missed, injury count
- Prior season: prev_PTS, prev_REB, prev_AST, prev_MIN

**Target:** salary (continuous)

**Models:** LinearRegression, RandomForestRegressor, GradientBoostingRegressor

**Split:** Time-based (train ≤ 2022-23, validation = 2023-24, test = 2024-25)

**Scoring:** predicted_salary - actual_salary = undervaluation gap

## Improvement Model (Breakout Prediction)

**Goal:** Predict which players will improve next season.

**Target:** improved_flag (binary — PTS increase ≥ 2.0 with GP ≥ 20)

**Features:** Current + previous season stats, deltas, injury history

**Models:** LogisticRegression, RandomForestClassifier, GradientBoostingClassifier

**Split:** Time-based (same cutoffs)

## Trade Target Scoring

**Method:** Composite weighted score (not ML-trained)

**Components:**
- Performance score (30%): points + rebounds + assists + stocks - turnovers
- Contract efficiency (25%): performance per $1M salary
- Age upside (15%): younger players score higher
- Durability (10%): fewer missed games score higher
- Efficiency (10%): TS% and advanced metrics
- Scouting (10%): scouting report grades

**Output:** Ranked list with tier labels (Elite Target, Strong Target, Moderate, Low Value)

## MLflow Integration

All training runs are logged to MLflow with:
- Parameters (model type, feature count, train size)
- Metrics (MAE, RMSE, R², accuracy, F1, AUC)
- Artifacts (trained model, feature importance JSON)
- Accessible at http://localhost:5001

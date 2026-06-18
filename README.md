# FIFA ML Predictor

Full-stack FIFA World Cup prediction lab with exact-score probabilities, moneyline edge checks, and parlay simulation.

## What it does

- Predicts exact scorelines with a Dixon-Coles-adjusted Poisson team-strength model.
- Trains an optional learned Poisson goal-rate model from free match-level data and falls back to the v2 heuristic when no validated artifact exists.
- Shows win/draw/loss percentages and top likely scores.
- Compares model probabilities against moneyline odds.
- Builds simulated parlays and estimates probability, payout, and EV.
- Uses real 2026 World Cup fixtures/results from football-data.org when available, with OpenFootball no-key fallback.
- Uses The Odds API for live sportsbook odds where available.
- Keeps API-Football optional because its free plan may not include 2026 World Cup access.
- Uses StatsBomb Open Data for real historical World Cup team/player event stats.
- Uses optional international results CSVs to weight recent form, including friendlies.
- Stores match-level international results for leakage-safe learned-model training.
- Uses optional World Football Elo CSV and player availability CSVs when you provide local files.
- Backtests finished matches and exposes calibration/quality flags for each prediction.

## Backend

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
uvicorn app.main:app --reload
```

Open API docs at `http://127.0.0.1:8000/docs`.

## Frontend

```powershell
cd frontend
npm install
npm run dev
```

The frontend expects the backend at `http://127.0.0.1:8000`.
In production, the built frontend uses same-origin API requests so Vercel can serve both the UI and FastAPI app from one deployment.

## Vercel Hosting with Auto Updates

This repo is configured for full-stack Vercel hosting:

- FastAPI runs as a Vercel Python Function from `app/main.py`.
- `npm --prefix frontend ci && npm --prefix frontend run build` builds the Vite app.
- FastAPI serves `frontend/dist` when it exists.
- Turso/libSQL stores production data so Vercel cold starts keep synced fixtures, odds, status, and model artifacts.
- GitHub Actions calls protected cron endpoints every 5 minutes for data sync and daily for model retraining.

### 1. Create Turso database

Create a free Turso database and token, then set these in Vercel Production environment variables:

```powershell
TURSO_DATABASE_URL="libsql://..."
TURSO_AUTH_TOKEN="..."
```

Local dev can keep using `DATABASE_URL=data/fifa_ml.sqlite3`; Turso is only used when both Turso variables exist.

### 2. Set Vercel environment variables

Set these in Vercel project settings:

```powershell
TURSO_DATABASE_URL="libsql://..."
TURSO_AUTH_TOKEN="..."
CRON_SECRET="generate-a-long-random-secret"
FOOTBALL_DATA_TOKEN="your-football-data-token"
THE_ODDS_API_KEY="your-odds-api-key"
API_FOOTBALL_KEY="optional-api-football-key"
ODDS_REGIONS="us"
ODDS_MARKETS="h2h,spreads,totals"
AUTO_SYNC_ENABLED="false"
```

`AUTO_SYNC_ENABLED=false` is recommended on Vercel because scheduled GitHub Actions invoke sync endpoints instead of relying on an in-process background loop.

### 3. Set GitHub repository secrets

Add these GitHub Actions secrets for `vihaana28/FIFA-ML`:

```powershell
PROD_URL="https://your-vercel-domain.vercel.app"
CRON_SECRET="same-value-as-vercel"
```

Workflows:

- `.github/workflows/production-sync.yml`: runs every 5 minutes and calls `POST /admin/cron/sync`.
- `.github/workflows/production-train.yml`: runs daily and calls `POST /admin/cron/train`.

Both endpoints require `Authorization: Bearer $CRON_SECRET`.

### 4. Deploy

Connect the GitHub repo to Vercel or run:

```powershell
vercel
vercel --prod
```

After deploy:

```powershell
curl https://your-vercel-domain.vercel.app/health
curl -X POST https://your-vercel-domain.vercel.app/admin/cron/sync -H "Authorization: Bearer $env:CRON_SECRET"
```

## Data

Default fixture data comes from OpenFootball so fake games are not shown. Live providers:

- football-data.org: free-token 2026 World Cup fixture/result feed for team-assigned matches and finished-match scores.
- StatsBomb Open Data: no-key historical World Cup event data for team/player feature engineering.
- International results CSV: optional local file for recent national-team form and friendlies.
- The Odds API: sportsbook h2h/spreads/totals odds where World Cup markets are active.
- OpenFootball: no-key fallback schedule for 2026 World Cup fixtures.
- API-Football: optional paid/eligible fallback for fixtures/odds. Free tier is quota-limited and may block the 2026 season.

Set keys in `.env` or your shell:

```powershell
$env:API_FOOTBALL_KEY="your-api-football-key"
$env:THE_ODDS_API_KEY="your-odds-api-key"
$env:FOOTBALL_DATA_TOKEN="your-football-data-token"
$env:ODDS_REGIONS="us"
$env:ODDS_MARKETS="h2h,spreads,totals"
$env:AUTO_SYNC_ENABLED="true"
$env:AUTO_SYNC_INTERVAL_SECONDS="300"
$env:INTERNATIONAL_RESULTS_CSV="data/raw/international_results.csv"
$env:TRAINING_RESULTS_CSV="data/raw/international_results.csv"
$env:WORLD_ELO_CSV="data/raw/world_elo.csv"
$env:PLAYER_AVAILABILITY_CSV="data/raw/player_availability.csv"
python scripts\sync_data.py
python scripts\sync_training_data.py
python scripts\sync_stats.py
python scripts\sync_recent_form.py
python scripts\sync_elo.py
python scripts\sync_player_availability.py
python scripts\train_model.py
```

`scripts\sync_data.py` also refreshes current-tournament team stats from finished match scores, so played games update goals, goals against, record, and points.
When the FastAPI app is running, auto-sync polls football-data.org around live match windows and the frontend refreshes local backend data every 60 seconds.
`scripts\sync_training_data.py` stores match-level rows from `TRAINING_RESULTS_CSV`, `INTERNATIONAL_RESULTS_CSV`, or the free martj42 GitHub CSV by default. `scripts\sync_recent_form.py` expects a CSV with columns like `date,home_team,away_team,home_score,away_score,tournament`; the public international results datasets used on Kaggle/GitHub follow this shape. Friendlies count at lower weight than competitive matches so they can move form without overwhelming tournament data, and those same rows are saved for learned-model training.
`scripts\sync_elo.py` expects `data/raw/world_elo.csv` columns like `team,rating`. It is meant for local snapshots from World Football Elo.
`scripts\sync_player_availability.py` expects `data/raw/player_availability.csv` columns: `team,player,status,importance,minutes_share,attack_contribution,defense_contribution`. Supported statuses are `available`, `doubtful`, `injured`, and `suspended`.

Free player stats are limited. StatsBomb Open Data gives real historical World Cup player events, but not live 2026 club/player form. API-Football enrichment is optional and only used when free/eligible endpoints return data; missing player stats reduce confidence instead of inventing precision.

Keys needed:

- Required for real odds: `THE_ODDS_API_KEY`
- Recommended for full World Cup fixtures/results: `FOOTBALL_DATA_TOKEN`
- Optional for API-Football paid/eligible access: `API_FOOTBALL_KEY`
- No key needed for StatsBomb Open Data or OpenFootball fixtures.
- No key needed for local or GitHub-hosted international results CSVs.

## Betting Scope

This app is a strategy simulator. It does not place bets, connect to sportsbooks, or guarantee profit. Same-match correlated parlay legs are blocked in the risk endpoint, and displayed EV should still be treated as model output, not advice.

## Tests

```powershell
pytest
cd frontend
npm test
npm run build
```

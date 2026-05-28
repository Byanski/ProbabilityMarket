# Local Telemetry Comparison Engine

A FastAPI boilerplate for aggregating market-style JSON feeds, stats endpoints, and RSS news into a local index dashboard at `http://localhost:9999`.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `.env` with your Source connector values:

```text
TELEMETRY_API_HOST=https://api.the-odds-api.com
TELEMETRY_API_KEY=your_secured_token_here
TELEMETRY_DEFAULT_REGION=us
TELEMETRY_DATA_FORMAT=american
```

Missing external configuration is allowed: the backend logs warnings and the dashboard renders placeholder data.

## Run

```powershell
python -m app.main
```

The app is intentionally bound to port `9999`.

## Structure

```text
app/
  api/routes.py              FastAPI route definitions
  core/config.py             Environment-driven settings
  core/logging.py            Local logging setup
  models/schemas.py          Typed response models
  services/collectors.py     Async HTTP feed collectors
  services/telemetry_connector.py Provider Source connector
  services/parsers.py        Nested market JSON and RSS parsers
  services/stats_ingestion.py Secondary stats ingestion
  analytics/processor.py     Probability, variance, and news adjustments
  static/                    HTML/CSS/JS dashboard
```

# Trackmania Tracker

Trackmania Tracker is a live tracking application for running three-player Trackmania Bingo challenge sessions against official Nadeo campaigns. It features a decoupled FastAPI backend with persistent Google Cloud Firestore session checkpointing, a modern dark-themed HTML5/JS single-page frontend, structured Cloud Logging, and legacy Streamlit support.

## Project Intentions

The project makes a live Trackmania challenge easy to run and follow:

- Select an official campaign from Nadeo Live Services.
- Build a fair 4x4 Bingo board from the 16 playable campaign tracks (distributing 1 track from each series across every row and column).
- Compare the configured players' personal bests and identify real-time track ownership.
- Poll leaderboard data at a controlled cadence instead of flooding the service, applying each processed snapshot once to the shared canonical game.
- Coordinate leaderboard polling across viewers with shared snapshots, aggregate pacing, and bounded recovery from transient service limits.
- Keep a timestamped record of newly observed personal bests during the session.
- Show the shared game state and one independently controlled timer for each player with client-side countdown calculations.
- Configure campaign, player timer duration, opening grace period, and maximum game length before starting.
- Automatically checkpoint active game state and player timers to Firestore, rehydrating sessions across server restarts or redeployments.

The application currently has three configured players: Eljay, Lry, and Timo. Player account IDs and API credentials are configuration concerns; credentials must never be committed.

## Requirements

- Python 3.13
- `uv`
- Ubisoft/Nadeo service-account credentials with access to the required Live Services endpoints
- (Optional) Google Cloud Project with Firestore enabled for persistent game checkpointing

## Setup

From PowerShell / bash in the repository root:

```bash
uv venv .venv_tm_tracker
uv pip install --python .venv_tm_tracker/bin/python -e ".[dev]"
source .venv_tm_tracker/bin/activate
```

*(On Windows PowerShell, use `.\.venv_tm_tracker\Scripts\Activate.ps1`)*

### Credentials and Environment Configuration

Set the required authentication values in `.env` (or environment variables):

```bash
BASIC_AUTH=<service-account-basic-authorization>
APP_PASSWORD_HASH=<pbkdf2-sha256-application-password-hash>
```

Optional environment variables:
- `PROJECT_NAME`, `MAINTAINER_HANDLE`, `EMAIL`: Identifying parameters for the Live API `User-Agent`.
- `GCP_PROJECT_ID`: Target GCP project for Cloud Logging and Firestore persistence.
- `FIRESTORE_DATABASE_ID`: Optional Firestore database ID (defaults to `(default)`).

For Streamlit execution, `.streamlit/secrets.toml` provides the same keys.

## Running Locally

### FastAPI Backend & SPA Frontend (Recommended)

Run the decoupled FastAPI server:

```bash
uv run --active uvicorn api:app --reload --port 8080
```

Open `http://localhost:8080` in your browser. The single-page application serves the complete interactive console with password unlock gate, campaign settings preview, board shuffle, 4x4 Bingo grid, player timer cards, and live PB record feed.

### Streamlit Mode (Legacy)

Run the Streamlit application:

```bash
uv run --active streamlit run streamlit_app.py
```

## Deployment to Google Cloud Run

The application is containerized with a production-ready `Dockerfile` and deploys seamlessly to GCP Cloud Run:

```bash
gcloud run deploy tm-tracker \
  --source . \
  --platform managed \
  --region europe-west1 \
  --allow-unauthenticated \
  --port 8080 \
  --max-instances 1 \
  --timeout 3600 \
  --set-secrets BASIC_AUTH=tm-basic-auth:latest,APP_PASSWORD_HASH=tm-password-hash:latest
```

### Key Cloud Run Deployment Flags

- `--max-instances 1`: **Required**. Enforces a single container instance to guarantee process-wide canonical game coordination, single-flight leaderboard refreshes, and API rate-limiting compliance.
- `--timeout 3600`: Extends request timeout up to 1 hour for uninterrupted live challenge monitoring and long connections.
- `--set-secrets`: Securely injects `BASIC_AUTH` and `APP_PASSWORD_HASH` from GCP Secret Manager without exposing secrets in code, build flags, or container layers.

On container restart or redeployment, the application connects to Firestore, automatically rehydrating any active session and player timer states.

## Development Checks

Run the full test suite with:

```bash
uv run --active python -m pytest
```

Execute pre-commit hooks (Ruff format, Ruff lint, Pylint, and mypy):

```bash
uv run --active pre-commit run --all-files
```

Run frontend timer JavaScript unit tests:

```bash
node tests/test_timer_countdown.js
```

See [DEVELOPER.md](DEVELOPER.md) for detailed architecture, persistence models, and development workflow.

## Documentation

- [Developer technical documentation](DEVELOPER.md)
- [Implementation plan](development-docs/IMPLEMENTATION-PLAN.md)
- [Changelog](development-docs/CHANGELOG.md)
- [Sketchbook](development-docs/SKETCHBOOK.md)

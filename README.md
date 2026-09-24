# Trackmania Bingo

Trackmania Bingo is a live tracking application for running three-player Trackmania Bingo challenge sessions against official Nadeo campaigns. It features a decoupled FastAPI backend with persistent Google Cloud Firestore session checkpointing, a modern dark-themed HTML5/JS single-page frontend, and structured Cloud Logging.

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

## Live Deployment

- **Live URL**: [https://shorturl.fm/tm-bingo](https://shorturl.fm/tm-bingo)
- **Direct Cloud Run URL**: `https://tm-bingo-281908789663.europe-west4.run.app`

## Requirements

- Python 3.13
- `uv`
- Ubisoft/Nadeo service-account credentials with access to the required Live Services endpoints
- (Optional) Google Cloud Project with Firestore enabled for persistent game checkpointing

## Setup

From PowerShell / bash in the repository root:

```bash
uv venv .venv_tm_bingo
uv pip install --python .venv_tm_bingo/bin/python -e ".[dev]"
source .venv_tm_bingo/bin/activate
```

*(On Windows PowerShell, use `.\.venv_tm_bingo\Scripts\Activate.ps1`)*

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

## Running Locally

Run the FastAPI server:

```bash
uv run --active uvicorn api:app --reload --port 8080
```

Open `http://localhost:8080` in your browser. The single-page application provides a focused challenge console with password unlock gate, distinct setup and playing views, 4x4 Bingo grid featuring player-claim colored squares and relative time deltas, streamlined player timers with single toggle start/reset controls, and a live PB record feed.

## Deployment to Google Cloud Run

The application is containerized with a production-ready `Dockerfile` and deploys seamlessly to GCP Cloud Run.

### Quick Deployment Script

For rapid automated deployment without manual configuration:

```bash
./scripts/deploy.sh
```

This script builds the image via Cloud Build, deploys to Cloud Run with required single-instance, timeout, and secret-manager configurations, and displays the direct Cloud Run URL as well as the short URL (`https://shorturl.fm/tm-bingo`).

### Building & Pushing the Container Image (Manual)

Build and push the image to Artifact Registry (replace `<PROJECT_ID>` and `<REGION>` with your GCP project and preferred region):

```bash
# Using Cloud Build (no local Docker daemon required):
gcloud builds submit --tag <REGION>-docker.pkg.dev/<PROJECT_ID>/tm-bingo-repo/tm-bingo:latest

# Or using local Docker:
gcloud auth configure-docker <REGION>-docker.pkg.dev
docker build -t <REGION>-docker.pkg.dev/<PROJECT_ID>/tm-bingo-repo/tm-bingo:latest .
docker push <REGION>-docker.pkg.dev/<PROJECT_ID>/tm-bingo-repo/tm-bingo:latest
```

### Cloud Run Deployment Command

Deploy the pushed image from Artifact Registry:

```bash
gcloud run deploy tm-bingo \
  --image <REGION>-docker.pkg.dev/<PROJECT_ID>/tm-bingo-repo/tm-bingo:latest \
  --platform managed \
  --region <REGION> \
  --allow-unauthenticated \
  --port 8080 \
  --max-instances 1 \
  --timeout 3600 \
  --service-account "tm-bingo-runner@<PROJECT_ID>.iam.gserviceaccount.com" \
  --set-secrets BASIC_AUTH=tm-bingo-basic-auth:latest,APP_PASSWORD_HASH=tm-bingo-password-hash:latest
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
- [Infrastructure setup guide](development-docs/INFRASTRUCTURE-SETUP.md)
- [Implementation plan](development-docs/IMPLEMENTATION-PLAN.md)
- [Changelog](development-docs/CHANGELOG.md)
- [Sketchbook](development-docs/SKETCHBOOK.md)

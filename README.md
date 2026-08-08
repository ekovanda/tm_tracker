# Trackmania Tracker

Trackmania Tracker is a small Streamlit application for running a three-player Trackmania Bingo session against an official campaign.

## Project Intentions

The project is intended to make a live Trackmania challenge easy to run and easy to follow:

- Select an official campaign from Nadeo Live Services.
- Build a fair 4x4 Bingo board from the 16 playable campaign tracks.
- Compare the configured players' personal bests and identify track ownership.
- Poll leaderboard data at a controlled cadence instead of flooding the service.
- Keep a timestamped record of newly observed personal bests during the session.
- Show the shared game state and one independently controlled ten-minute timer for each player.

The application currently has three configured players: Eljay, Lry, and Timo. Player account IDs and API credentials are configuration concerns; credentials must never be committed.

## Requirements

- Python 3.13
- `uv`
- Ubisoft/Nadeo service-account credentials with access to the required Live Services endpoints

## Setup

From PowerShell in the repository root:

```powershell
uv venv .venv_tm_tracker
uv pip install --python .venv_tm_tracker\Scripts\python.exe -e ".[dev]"
.\.venv_tm_tracker\Scripts\Activate.ps1
```

Create a private `.env` file with the required authentication value:

```text
BASIC_AUTH=<service-account-basic-authorization>
```

The application also accepts optional `PROJECT_NAME`, `MAINTAINER_HANDLE`, and `EMAIL` values for the identifying request `User-Agent`. Keep `.env` private and do not print or commit its contents.

## Run

```powershell
uv run --active streamlit run streamlit_app.py
```

Open the local URL printed by Streamlit, choose an official campaign, and start a Bingo session. The active page displays the board, session status, records, leaderboard refresh status, and the three player timers.

## Development Checks

Run the full test suite with:

```powershell
uv run --active python -m pytest
```

The repository also uses Ruff, Pylint, mypy, and pre-commit hooks. See [DEVELOPER.md](DEVELOPER.md) for architecture, implementation decisions, and the development workflow.

## Documentation

- [Developer technical documentation](DEVELOPER.md)
- [Implementation plan](development-docs/IMPLEMENTATION-PLAN.md)
- [Changelog](development-docs/CHANGELOG.md)
- [Sketchbook](development-docs/SKETCHBOOK.md)

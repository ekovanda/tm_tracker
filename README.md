# Trackmania Tracker

Trackmania Tracker is a small Streamlit application for running a three-player Trackmania Bingo session against an official campaign.

## Project Intentions

The project is intended to make a live Trackmania challenge easy to run and easy to follow:

- Select an official campaign from Nadeo Live Services.
- Build a fair 4x4 Bingo board from the 16 playable campaign tracks.
- Compare the configured players' personal bests and identify track ownership.
- Poll leaderboard data at a controlled cadence instead of flooding the service, applying each processed snapshot once to the shared game.
- Coordinate leaderboard polling across viewers with shared snapshots, aggregate pacing, and bounded recovery from transient service limits.
- Keep a timestamped record of newly observed personal bests during the session.
- Show the shared game state and one independently controlled timer for each player.
- Configure the campaign, player timer duration, opening grace period, and maximum game length before starting.

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

Create `.streamlit/secrets.toml` with the required authentication values:

```toml
BASIC_AUTH=<service-account-basic-authorization>
APP_PASSWORD_HASH=<pbkdf2-sha256-application-password-hash>
```

Set `APP_PASSWORD_HASH` to the PBKDF2-SHA256 application password hash before running the app. The app requests this password before contacting Nadeo. Keep this file private and do not commit it. Streamlit Cloud accepts the same TOML content in the app's Secrets settings.

The application also accepts optional `PROJECT_NAME`, `MAINTAINER_HANDLE`, and `EMAIL` values for the identifying request `User-Agent`.

For Streamlit Cloud, deploy `streamlit_app.py` from this repository and paste the same TOML into the app's Secrets settings. The Bingo game does not require external game-state storage: connected viewers share the process-wide in-memory game while they are served by the same running app process. A Streamlit Cloud restart intentionally clears that state, so the next game starts with fresh setup and current API data.

## Run

```powershell
uv run --active streamlit run streamlit_app.py
```

Open the local URL printed by Streamlit. The app displays its packaged version beneath the title. The pre-session settings page shows a color-coded 4x4 board preview with track values. Setup configuration and `Shuffle board` changes are shared across connected viewers while the app process is running, so any participating player can prepare the pending game. Every row and column contains one light-grey, green, blue, and red track. The first player to start establishes the shared game; stop and reset actions apply to that same game for all viewers. Once started, every rerun reads the shared live board, session status, records, leaderboard refresh status, and three player timers. A process restart clears the pending in-memory setup and requires a fresh configuration.

There is one game per running app process. Before start, viewers can change the shared pending configuration. The first successful start wins; later start attempts cannot replace it. Stop preserves the final shared snapshot, while reset returns every viewer to the shared pending setup. A restart is the clean new-game boundary and does not restore the previous board, records, or status.

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

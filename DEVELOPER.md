# Developer Technical Documentation

This document records the current implementation shape and the decisions that developers need when changing the Trackmania Tracker. Keep it synchronized with the code. It is a technical reference, not a progress diary.

## Architecture

The application is a Python 3.13 Streamlit app with a small functional domain layer:

- `streamlit_app.py` configures the wide Streamlit page, authenticates, and calls the page renderer.
- `streamlit_bingo_page.py` owns Streamlit rendering, session controls, timer controls, and the one-second UI fragment refresh.
- `bingo_service.py` orchestrates campaign/session loading, leaderboard polling, record de-duplication, and process-wide timer storage.
- `bingo.py` contains immutable Bingo state models and pure transitions for board ranking, line detection, session expiry, and manual timer transitions.
- `live_services.py` is the Nadeo Live Services adapter for campaigns, maps, and club leaderboard data.
- `authentication.py` handles Ubisoft/Nadeo tokens and constructs the identifying `User-Agent` header.
- `player.py`, `track.py`, `tm_lookups.py`, and `utils.py` contain configured domain data and small shared helpers.

Tests mirror these boundaries in `tests/`. Streamlit rendering tests use a fake Streamlit surface instead of requiring a running browser.

## Runtime Flow

1. `streamlit_app.main` obtains a Nadeo service token and renders `bingo_page`.
2. The page loads official campaigns and lets the user select one.
3. Starting a session calls `start_session_in_state`, which loads exactly 16 playable tracks and stores a `BingoSession` in Streamlit session state.
4. The active-session fragment renders timers, controls, status, the board, and records.
5. The fragment reruns every second for timer display. Leaderboard polling remains independently gated by `poll_is_due` at one-minute intervals, or by the explicit refresh button.
6. Polling loads each track in order, waits `REQUEST_DELAY_SECONDS` between leaderboard requests, de-duplicates new records, and applies the pure Bingo state transition.

## State Ownership

There are two deliberately different state scopes:

- `BingoSession` is stored in Streamlit session state. It contains the selected campaign, tracks, Bingo board state, record history, and de-duplication keys for one browser session.
- `SHARED_MANUAL_TIMER` is a process-wide, thread-safe `ManualTimerStore`. It keeps one `ManualTimerState` per configured player so multiple viewers see the same player timer state.

Do not move timer state into browser-local widget state when changing the timer. The process-wide store is the synchronization boundary for connected viewers. `ManualTimerStore.get_all` updates all states while holding one lock and must not call its lock-acquiring `get` method from inside that lock.

## Domain Invariants

- A Bingo board has exactly 16 distinct tracks: numbers 1-4, 6-9, 11-14, and 16-19.
- The board arrangement distributes one track from each five-track campaign series across every row and column.
- A track owner is the fastest configured player with a valid personal best. Ties do not produce an owner or margin.
- A Bingo line must remain owned by one player for `LINE_DURATION` (ten minutes) before completion.
- A session expires after `GAME_DURATION` (five hours).
- Manual player timers last `MANUAL_TIMER_DURATION` (ten minutes). They can be started, stopped, restarted, expire on reads, and reset with the Bingo session controls.

The pure functions in `bingo.py` return new frozen state values rather than mutating prior Bingo state. Keep service/API calls outside this module.

## API and Polling Decisions

- Nadeo requests use the service-account token path currently used by the app and include a useful identifying `User-Agent`.
- Authentication and Live Services credentials come from environment variables loaded by `python-dotenv`; never add credentials to source or documentation.
- Campaign loading uses the official campaign endpoint, then retrieves map metadata and selects the 16 playable track numbers.
- Leaderboard requests are paced with `REQUEST_DELAY_SECONDS` (currently 0.5 seconds) and accept an injected `SleepFn` in tests.
- The UI refresh interval and network poll interval are intentionally separate: one-second rendering must not become one-second API traffic.

## UI Decisions

- The page uses Streamlit's `layout="wide"` so the three timer cards have useful horizontal space.
- Timer action labels are intentionally short (`Start`, `Restart`, and `Stop`); the player heading and stable account-based widget keys provide identity without wrapping long labels.
- Timer, board, and record ownership colors are Eljay green, Lry yellow, and Timo blue. Yellow board cells use dark text to preserve readable contrast.
- Timer progress is rendered as an accessible HTML progressbar with a remaining fraction and player-specific color.
- Streamlit fragment execution is used when the runtime is available. The page has a direct content fallback so rendering helpers remain testable without a live Streamlit runtime.

## Testing and Quality Gates

Use the project environment through `uv`:

```powershell
uv run --active python -m pytest
uv run --active python -m pytest tests/test_streamlit_bingo_page.py
uv run --active python -m compileall .
uv run --active pre-commit run --all-files
```

Behavior-changing Python modules should have focused tests and at least 85% line coverage when a coverage check is applicable. Prefer injected clocks, loaders, sleepers, and fake Streamlit surfaces over live services or browser-dependent tests.

## Workflow Documents

- `development-docs/SKETCHBOOK.md` is the internal place for rough ideas and requirements; between captures it contains only its heading.
- `development-docs/IMPLEMENTATION-PLAN.md` is the concise, numbered list of testable implementation steps.
- `development-docs/CHANGELOG.md` records user-visible completed changes under `Unreleased`.
- The `plan-implementation` skill turns sketchbook ideas into a plan.
- The `implement-next` skill implements one unchecked step and must review and synchronize this document and the root `README.md`.
- The `create-commit` skill creates one focused local commit after validation. Never push from this workflow.

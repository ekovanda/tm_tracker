# Developer Technical Documentation

This document records the current implementation shape and the decisions that developers need when changing the Trackmania Tracker. Keep it synchronized with the code. It is a technical reference, not a progress diary.

## Architecture

The application is a Python 3.13 Streamlit app with a small functional domain layer:

- `streamlit_app.py` configures the wide Streamlit page, gates access with the configured app password, authenticates, displays the packaged version, and calls the page renderer.
- `streamlit_bingo_page.py` owns Streamlit rendering, session controls, timer controls, and the one-second UI fragment refresh.
- `bingo_service.py` orchestrates campaign/session loading, leaderboard polling, record de-duplication, and process-wide timer storage. It also defines the thread-safe `CanonicalGameStore` boundary for the single shared game's pending configuration and immutable session snapshots.
- `bingo.py` contains immutable Bingo state models and pure transitions for board ranking, line detection, session expiry, and manual timer transitions.
- `live_services.py` is the Nadeo Live Services adapter for campaigns, maps, and club leaderboard data.
- `authentication.py` handles Ubisoft/Nadeo tokens and constructs the identifying `User-Agent` header.
- `player.py`, `track.py`, `tm_lookups.py`, and `utils.py` contain configured domain data and small shared helpers.

Tests mirror these boundaries in `tests/`. Streamlit rendering tests use a fake Streamlit surface instead of requiring a running browser.

## Runtime Flow

1. `streamlit_app.main` requires the app password hash from Streamlit-managed `st.secrets["APP_PASSWORD_HASH"]` before obtaining a Nadeo service token, displays the package version from installed metadata, and renders `bingo_page`. A successful password check is retained in the current Streamlit session state; the password and hash are never logged.
2. Before a session exists, the page loads official campaigns and renders a color-coded 4x4 board preview plus controls for campaign, player timer duration, grace period, and maximum game length. These pending setup values are read from and written to `SHARED_CANONICAL_GAME`, including the board seed changed by shuffle, so connected viewers see the same configuration while the process is running.
3. Starting a session passes a `BingoSettings` value to `start_canonical_game`, which loads exactly 16 playable tracks and atomically stores the resulting `BingoSession` in `SHARED_CANONICAL_GAME`. The current page mirrors that canonical snapshot into local render state; the settings panel is not rendered while the canonical session exists.
4. The active-session fragment reads the current `BingoSession` from `SHARED_CANONICAL_GAME` on every rerun, then renders the shared timers, controls, status, board, records, and deadline. Streamlit session state retains only a render cache for compatibility.
5. The fragment reruns every second for timer display. Leaderboard polling remains independently gated by `poll_is_due` at one-minute intervals, or by the explicit refresh button, and calls `poll_canonical_game` so the resulting session snapshot is shared.
6. Polling uses the process-wide `SHARED_POLLING_COORDINATOR`. Successful snapshots are cached for one minute by campaign, token audience, and loader; overlapping viewers single-flight the same refresh, while `poll_canonical_game` atomically applies record de-duplication and Bingo transitions to the canonical session.
7. The coordinator reserves aggregate request start slots across viewers and accounts for request duration, keeping the configured 0.6-second minimum interval. Retryable 429 and 5xx failures use bounded exponential backoff, optionally honoring a numeric `Retry-After` header. Manual refresh bypasses the snapshot cache; automatic refresh remains one-minute gated.

## Deployment and Lifecycle

Deploy `streamlit_app.py` to Streamlit Cloud and provide `BASIC_AUTH` and `APP_PASSWORD_HASH` in the app's Secrets settings using TOML syntax. Optional identity settings may be supplied there as well. No external game-state store or storage credentials are required.

The process-wide `SHARED_CANONICAL_GAME` store is the boundary for one game shared by every viewer connected to that running app process. Pending settings may be changed before start, the first successful start wins, and later starts cannot replace the session. Stop retains the final immutable snapshot for all viewers; reset removes the session and returns all viewers to the shared pending setup. A process restart creates a fresh in-memory store, so the next game begins with fresh configuration and current API data rather than restored state.

## State Ownership

There are two deliberately different state scopes:

- `BingoSession` is owned by `SHARED_CANONICAL_GAME` and mirrored into Streamlit session state only as a render cache. It contains the selected campaign, tracks, Bingo board state, record history, and de-duplication keys for the shared game. Leaderboard updates enter it through the atomic `poll_canonical_game` service path.
- `BingoState.settings` stores immutable per-session settings, including the board seed, overall session duration, opening grace period, and player timer duration.
- `SHARED_MANUAL_TIMER` is a process-wide, thread-safe `ManualTimerStore`. It keeps one `ManualTimerState` per configured player so multiple viewers see the same player timer state.

The canonical-game work introduces `PendingGame`, `CanonicalGameState`, and the locked `CanonicalGameStore` in `bingo_service.py`. `SHARED_CANONICAL_GAME` is the process-wide singleton that all connected viewers use; it models one pending configuration or one started/stopped `BingoSession`, rejects configuration changes after start, and atomically enforces first-start-wins. Pending setup, lifecycle actions, leaderboard transitions, and active rendering use this shared boundary. Streamlit session state retains only viewer-local widget, cache, and refresh metadata. A process restart intentionally clears this in-memory game state, so the next game starts fresh from its selected configuration and current API data; no durable game-state storage is required.

Do not move timer state into browser-local widget state when changing the timer. The process-wide store is the synchronization boundary for connected viewers. `ManualTimerStore.get_all` updates all states while holding one lock and must not call its lock-acquiring `get` method from inside that lock.

## Domain Invariants

- A Bingo board has exactly 16 distinct tracks: numbers 1-4, 6-9, 11-14, and 16-19.
- The board arrangement distributes one track from each five-track campaign series across every row and column.
- Board generation is deterministic for a numeric seed and preserves one track from each series in every row and column. The four series are tracks 1-4 (light grey), 6-9 (green), 11-14 (blue), and 16-19 (red).
- A track owner is the fastest configured player with a valid personal best. Ties do not produce an owner or margin.
- A Bingo line must remain owned by one player for `LINE_DURATION` (ten minutes) before completion.
- A session expires after the configured game duration, which defaults to `GAME_DURATION` (five hours).
- The configured grace period defaults to 30 minutes. During grace, line-win timing does not start and manual player timer transitions remain blocked; the boundary itself is eligible for normal play.
- Manual player timers use `BingoSettings.manual_timer_duration`, defaulting to `MANUAL_TIMER_DURATION` (ten minutes). They can be started, stopped, restarted, expire on reads, and reset with the Bingo session controls.

The pure functions in `bingo.py` return new frozen state values rather than mutating prior Bingo state. Keep service/API calls outside this module.

## API and Polling Decisions

- Nadeo requests use the service-account token path currently used by the app and include a useful identifying `User-Agent`.
- Authentication and Live Services credentials come from environment variables loaded by `python-dotenv`; never add credentials to source or documentation.
- `APP_PASSWORD_HASH` stores a PBKDF2-SHA256 password hash in the format `pbkdf2_sha256$iterations$salt$digest`. Verification uses `secrets.compare_digest`; missing or malformed configuration stops the app before any Nadeo request.
- Service tokens retain the access-token `exp` value as `accessTokenExpiresAt`, refresh five minutes before expiry through the documented refresh endpoint, and replace access/refresh tokens together. Idempotent Live API operations retry once after a 401.
- Live API GET failures use `LiveServiceError` with a category (`authentication`, `rate_limit`, `server`, `timeout`, `connection`, `transport`, `json`, or `payload`), optional HTTP status, retryability metadata, and an optional parsed `Retry-After` delay. Polling translates malformed processed records into the same contract and retries only retryable failures with bounded backoff.
- Campaign loading uses the official campaign endpoint, then retrieves map metadata and selects the 16 playable track numbers.
- Leaderboard requests are coordinated process-wide by campaign and token audience. `REQUEST_DELAY_SECONDS` (currently 0.6 seconds) is a shared minimum between request starts, and request duration is included when calculating the next slot. The sleep function and coordinator clock are injectable in tests, which cover cache reuse, overlapping refreshes, aggregate pacing, and bounded retry backoff.
- The UI refresh interval and network poll interval are intentionally separate: one-second rendering must not become one-second API traffic.
- Session settings are passed into `start_bingo` and retained in `BingoState`; the pre-session configuration UI is separate from the domain enforcement. The board seed is persisted with the session settings.

## UI Decisions

- The page uses Streamlit's `layout="wide"` so the three timer cards have useful horizontal space.
- Timer action labels are intentionally short (`Start`, `Restart`, and `Stop`); the player heading and stable account-based widget keys provide identity without wrapping long labels.
- Timer and record ownership colors are Eljay green, Lry yellow, and Timo blue. Board cells use track-series colors: light grey, green, blue, and red, with dark text for readable contrast.
- Timer progress is rendered as an accessible HTML progressbar with a remaining fraction and player-specific color.
- Streamlit fragment execution is used when the runtime is available. The page has a direct content fallback so rendering helpers remain testable without a live Streamlit runtime.
- The pre-session settings panel is only rendered when no `BingoSession` exists. It renders the shared seeded board preview and shuffle action. Active sessions expose stop/reset controls and retain the board seed and timing values in their immutable state.
- The active-session fragment reads canonical state before rendering the configured grace period's remaining seconds, progress bar, player timers, status, board, and records. It reuses the one-second fragment refresh, while the gated refresh path updates the canonical session before rendering.

## Testing and Quality Gates

Use the project environment through `uv`:

```powershell
uv run --active python -m pytest
uv run --active python -m pytest tests/test_streamlit_bingo_page.py
uv run --active python -m pytest tests/test_authentication.py tests/test_streamlit_app.py
uv run --active python -m compileall .
uv run --active pre-commit run --all-files
```

Behavior-changing Python modules should have focused tests and at least 85% line coverage when a coverage check is applicable. Prefer injected clocks, loaders, sleepers, and fake Streamlit surfaces over live services or browser-dependent tests.

## Workflow Documents

- `development-docs/SKETCHBOOK.md` is the internal place for rough ideas and requirements; between captures it contains only its heading.
- `development-docs/IMPLEMENTATION-PLAN.md` is the concise, numbered list of testable implementation steps.
- `development-docs/CHANGELOG.md` records concise user-visible completed changes under `Unreleased`, grouped as `Added`, `Changed`, or `Fixed`. New entries use an ISO 8601 timestamp and the abbreviated commit ID once available; before a commit exists, the entry states that the ID is pending.
- The `plan-implementation` skill turns sketchbook ideas into a plan.
- The `implement-next` skill implements one unchecked step and must review and synchronize this document and the root `README.md`.
- The `create-commit` skill creates one focused local commit after validation. Never push from this workflow.

# Changelog

All notable changes to this project are documented here.

## [Unreleased]

### Added

- 2026-08-08T19:29:00+02:00: Added password protection before Nadeo authentication using a PBKDF2-SHA256 hash supplied through `APP_PASSWORD_HASH` (`7d70d6c`).
- 2026-08-08T19:17:00+02:00: Added the Trackmania logo asset used by the Streamlit shell (`af7d8ee`).
- 2026-08-08T10:48:00+02:00: Added pre-commit hooks for Ruff formatting and linting, Pylint, and mypy (`e1aa35e`).
- 2026-08-08T10:53:03+02:00: Added the project planning and implementation workflow (`6ed788a`).
- 2026-08-08T11:04:02+02:00: Added the Streamlit Bingo game with unique series-balanced boards, record history, and paced leaderboard polling (`f9a83a0`, `04ed824`, `b3c7467`).
- 2026-08-08T12:13:49+02:00: Added a shared ten-minute manual Bingo timer with visible countdown and terminal states (`afc5e25`).
- 2026-08-08T12:15:38+02:00: Added consistent identifying User-Agent headers to authentication and Live API requests (`cf63b96`).
- 2026-08-08T19:16:25+02:00: Added process-wide leaderboard polling coordination with shared caching, single-flight refreshes, aggregate pacing, and bounded transient-error backoff (`5b4be19`).

### Fixed

- 2026-08-08T19:19:22+02:00: Fixed active Bingo cells to use neutral grey for unclaimed tracks and the current player's color for claimed tracks (`d354751`).
- 2026-08-08T19:08:41+02:00: Translated Live API HTTP, transport, JSON, and payload failures into actionable errors while preserving status and retryability metadata (`c91b4ea`).
- 2026-08-08T19:04:00+02:00: Added service-token expiry tracking, refresh-before-expiry, and one-time recovery after an expired Live API authorization (`9ba8f28`).
- 2026-08-08T11:31:25+02:00: Updated authentication to use Nadeo service accounts and documented Live API campaign and map endpoints (`51d7094`).
- 2026-08-08T10:12:23+02:00: Fixed the project packaging and type-check configuration so the normal pre-commit hooks can run without bypassing verification (`bd0c880`).
- 2026-08-08T10:12:23+02:00: Fixed legacy lint findings in shared API and utility modules (`bd0c880`).

### Changed

- 2026-08-08T19:38:29+02:00: Documented the changelog maintenance convention and reconciled Unreleased entries with the completed commit history. A commit ID is not applicable before the resulting commit exists.
- 2026-08-08T19:35:49+02:00: Branded the Streamlit shell as TM Bingo with the logo favicon, packaged version caption, single Bingo header, and subtle Eljay credit. A commit ID is not applicable before the resulting commit exists.
- 2026-08-08T19:28:07+02:00: Added an ignored local `scripts/` folder for reusable service-credential and application-password setup utilities; no tracked commit contains these ignored files.
- 2026-08-08T19:16:06+02:00: Coordinated leaderboard polling across viewers with shared snapshots, aggregate pacing, single-flight refreshes, and bounded recovery from transient service limits (`5b4be19`).
- 2026-08-08T16:45:00+02:00: Enforced the 0.6-second minimum leaderboard delay so configurable polling cannot exceed two requests per second (`b3c7467`).
- 2026-08-08T16:35:29+02:00: Replaced named board layouts with a visible color-coded 4x4 preview and seeded shuffle control that preserves one track from each series in every row and column (`d96478f`).
- 2026-08-08T16:20:35+02:00: Added pre-session controls for campaign and integer timing settings, a live grace-period countdown, and a neutral dark-grey grace progress bar (`15878b1`).
- 2026-08-08T16:02:50+02:00: Updated the planning workflow so an emptied sketchbook contains only its heading, with the convention documented for developers (`beebf31`).
- 2026-08-08T15:57:47+02:00: Reconciled player colors across timer, Bingo board, and record indicators, with readable dark text for yellow board cells (`a8a63f6`).
- 2026-08-08T15:55:14+02:00: Added project and developer README documentation and updated `implement-next` to review and synchronize both documents with implementation and design decisions (`cecfaa3`).
- 2026-08-08T17:48:41+02:00: Added independently controlled ten-minute timers for each player, with one-second countdown refreshes, depleting progress bars, and responsive timer controls (`4730989`).
- 2026-08-08T17:20:05+02:00: Updated the create-commit workflow to preserve changelog history and require timestamped entries (`9dd4145`).
- 2026-08-08T17:31:46+02:00: Improved Bingo action controls with clear primary and secondary states, icons, and responsive full-width layout (`3d264d5`).
- 2026-08-08T10:48:00+02:00: Repaired the development hooks to run Pylint and mypy through the active Python environment and include requests type stubs (`e1aa35e`).
# Changelog

All notable changes to this project are documented here.

## [Unreleased]

### Added

- Added pre-commit hooks for Ruff formatting and linting, Pylint, and mypy.
- Added the project planning and implementation workflow.
- Added the Streamlit Bingo game with unique series-balanced boards, record history, and paced leaderboard polling.
- Added a shared ten-minute manual Bingo timer with visible countdown and terminal states.
- Added consistent identifying User-Agent headers to authentication and Live API requests.

### Fixed

- 2026-08-08T17:03:24Z: Added service-token expiry tracking, refresh-before-expiry, and one-time recovery after an expired Live API authorization. A commit ID is not applicable before the resulting commit exists.
- Updated authentication to use Nadeo service accounts and documented Live API campaign and map endpoints.
- Fixed the project packaging and type-check configuration so the normal pre-commit hooks can run without bypassing verification.
- Fixed legacy lint findings in shared API and utility modules.

### Changed

- 2026-08-08T16:45:00Z: Enforced the 0.6-second minimum leaderboard delay so configurable polling cannot exceed two requests per second. A commit ID is not applicable before the resulting commit exists.
- 2026-08-08T16:45:00Z: Tightened leaderboard request pacing to 0.6 seconds between requests and added measured test coverage proving the observed rate stays below two requests per second. A commit ID is not applicable before the resulting commit exists.
- 2026-08-08T16:35:29Z: Replaced named board layouts with a visible color-coded 4x4 preview and seeded shuffle control that preserves one track from each series in every row and column. A commit ID is not applicable before the resulting commit exists.
- 2026-08-08T16:25:36Z: Added a color-coded pre-session 4x4 board preview and a `Shuffle board` control that creates a new valid seeded configuration. Every row and column contains one track from each of the four series. A commit ID is not applicable before the resulting commit exists.
- 2026-08-08T16:20:05Z: Added pre-session controls for campaign and integer timing settings, a live grace-period countdown, and a neutral dark-grey grace progress bar. A commit ID is not applicable before the resulting commit exists.
- 2026-08-08T16:02:34Z: Updated the planning workflow so an emptied sketchbook contains only its heading, with the convention documented for developers. A commit ID is not applicable before the resulting commit exists.
- 2026-08-08T15:57:47Z: Reconciled player colors across timer, Bingo board, and record indicators, with readable dark text for yellow board cells. A commit ID is not applicable before the resulting commit exists.
- 2026-08-08T15:55:14Z: Added project and developer README documentation and updated `implement-next` to review and synchronize both documents with implementation and design decisions. A commit ID is not applicable before the resulting commit exists.
- 2026-08-08T15:48:04Z: Added independently controlled ten-minute timers for each player, with one-second countdown refreshes, depleting progress bars, and responsive timer controls. A commit ID is not applicable before the resulting commit exists.
- 2026-08-08T15:19:54Z: Updated the create-commit workflow to preserve changelog history and require timestamped entries. A commit ID is not applicable before the resulting commit exists.
- 2026-08-08T15:26:20Z: Improved Bingo action controls with clear primary and secondary states, icons, and responsive full-width layout. A commit ID is not applicable before the resulting commit exists.
- 2026-08-08T15:30:15Z: Repaired the development hooks to run Pylint and mypy through the active Python environment and include requests type stubs. A commit ID is not applicable before the resulting commit exists.
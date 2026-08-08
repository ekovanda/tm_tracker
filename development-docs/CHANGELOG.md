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

- Updated authentication to use Nadeo service accounts and documented Live API campaign and map endpoints.
- Fixed the project packaging and type-check configuration so the normal pre-commit hooks can run without bypassing verification.
- Fixed legacy lint findings in shared API and utility modules.

### Changed

- 2026-08-08T15:48:04Z: Added independently controlled ten-minute timers for each player, with one-second countdown refreshes, depleting progress bars, and responsive timer controls. A commit ID is not applicable before the resulting commit exists.
- 2026-08-08T15:19:54Z: Updated the create-commit workflow to preserve changelog history and require timestamped entries. A commit ID is not applicable before the resulting commit exists.
- 2026-08-08T15:26:20Z: Improved Bingo action controls with clear primary and secondary states, icons, and responsive full-width layout. A commit ID is not applicable before the resulting commit exists.
- 2026-08-08T15:30:15Z: Repaired the development hooks to run Pylint and mypy through the active Python environment and include requests type stubs. A commit ID is not applicable before the resulting commit exists.
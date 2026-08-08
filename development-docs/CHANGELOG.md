# Changelog

All notable changes to this project are documented here.

## [Unreleased]

### Added

- Added pre-commit hooks for Ruff formatting and linting, Pylint, and mypy.
- Added the project planning and implementation workflow.
- Added the Streamlit Bingo game with unique series-balanced boards, record history, and paced leaderboard polling.
- Added a shared ten-minute manual Bingo timer with visible countdown and terminal states.

### Fixed

- Updated authentication to use Nadeo service accounts and documented Live API campaign and map endpoints.
- Fixed the project packaging and type-check configuration so the normal pre-commit hooks can run without bypassing verification.
- Fixed legacy lint findings in shared API and utility modules.
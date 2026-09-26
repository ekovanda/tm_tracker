# Project Guidelines

## Project

- This is a Python application for tracking Trackmania Bingo data with a FastAPI backend and JS frontend.
- This is a learning project for API design and GCP infrastructure management.
- Preserve the existing module boundaries and use the current code as the style reference.
- Keep changes focused. Do not refactor unrelated code while implementing a feature.

## Learning and Collaboration

- Be helpful and instructive in responses, highlighting concepts and rationale.
- Be opinionated on technical design and best practices, proactively advising on technical implications, architectural trade-offs, and failure modes.
- Test the user's knowledge and understanding occasionally and offer opportunities for learning.
- Unless explicitly instructed to implement silently, surface architectural trade-offs, API design decisions, and learning opportunities at appropriate times.

## Cloud Infrastructure and Costs

- Proactively inform and warn about operations or infrastructure decisions likely to incur costs, especially potentially significant ones.
- Bear in mind that while the application is not widely distributed, services can accidentally run unobserved (e.g., idle compute, uncleaned resources, or missing scale-to-zero defaults). Recommend cost-effective, low-maintenance patterns with automatic scale-to-zero or explicit teardown.

## Workflow

- Put new ideas and rough requirements in `development-docs/SKETCHBOOK.md`.
- Use the `plan-implementation` skill to turn the sketch into a numbered, testable `development-docs/IMPLEMENTATION-PLAN.md`.
- Use the `implement-next` skill to implement exactly one unchecked plan step at a time.
- Keep the workflow documents concise and current. Do not use them as progress logs.
- Keep `development-docs/CHANGELOG.md` up to date. Add a user-visible entry when a feature is complete.
- Use the `create-commit` skill after a feature is complete. Never push to a remote.

## Python and Dependencies

- Use the project virtual environment for Python execution, development commands, and validation. Create it with `uv venv .venv_tm_bingo`, then activate it in PowerShell with `.\.venv_tm_bingo\Scripts\Activate.ps1` before running commands.
- Install dependencies with `uv pip install --python .venv_tm_bingo\Scripts\python.exe -e ".[dev]"`.
- Prefer the existing dependencies and simple standard-library solutions before adding a package.
- Run project commands from the repository root with the activated virtual environment, for example `uv run --active python -m pytest` or `uv run --active uvicorn api:app --reload`.
- Never expose, print, commit, or hard-code secrets. Treat `.env` and credentials as private.

## Validation

- Run the narrowest relevant check after each implementation step.
- For Python changes, run checks in the activated virtual environment through uv; at minimum run a syntax or import check when no focused test exists.
- After installing the dev extra, install the shared commit hooks with `pre-commit install`.
- Commit hooks run Ruff formatting, Ruff linting, Pylint, and mypy on Python files.
- Do not claim a check passed unless it was actually run.

## Git

- Do not push, amend unrelated commits, or change user-owned worktree changes.
- Do not stage files unrelated to the feature.
- Use clean imperative commit messages such as `feat(ui) add player focus filters`, `fix(auth) handle expired token`, or `docs(workflow) update implementation guide`.
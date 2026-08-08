# Project Guidelines

## Project

- This is a small Python and Streamlit application for tracking TrackMan data.
- Preserve the existing module boundaries and use the current code as the style reference.
- Keep changes focused. Do not refactor unrelated code while implementing a feature.

## Workflow

- Put new ideas and rough requirements in `development-docs/SKETCHBOOK.md`.
- Use the `plan-implementation` skill to turn the sketch into a numbered, testable `development-docs/IMPLEMENTATION-PLAN.md`.
- Use the `implement-next` skill to implement exactly one unchecked plan step at a time.
- Keep the workflow documents concise and current. Do not use them as progress logs.
- Keep `development-docs/CHANGELOG.md` up to date. Add a user-visible entry when a feature is complete.
- Use the `create-commit` skill after a feature is complete. Never push to a remote.

## Python and Dependencies

- Use Docker Compose for all Python execution, development commands, and validation. Do not run Python directly on the host.
- Build the development image with `docker compose build` before the first container command.
- Use `uv` inside the container for environment and dependency operations; do not use `pip` directly.
- Prefer the existing dependencies and simple standard-library solutions before adding a package.
- Run project commands as `docker compose run --rm app <command>`.
- Never expose, print, commit, or hard-code secrets. Treat `.env` and credentials as private.

## Validation

- Run the narrowest relevant check after each implementation step.
- For Python changes, run checks inside the `app` container; at minimum run a syntax or import check when no focused test exists.
- Install the shared commit hooks with `uv run --with pre-commit pre-commit install`; the hooks execute their checks in Docker.
- Commit hooks run Ruff formatting, Ruff linting, Pylint, and mypy on Python files.
- Do not claim a check passed unless it was actually run.

## Git

- Do not push, amend unrelated commits, or change user-owned worktree changes.
- Do not stage files unrelated to the feature.
- Use clean imperative commit messages such as `feat(ui) add player focus filters`, `fix(auth) handle expired token`, or `docs(workflow) update implementation guide`.
---
name: implement-next
description: "Implement the next unchecked step in development-docs/IMPLEMENTATION-PLAN.md for this Python and Streamlit project. Use after plan-implementation, one step per invocation, with focused validation and changelog maintenance."
argument-hint: "Optional instruction for the next plan step"
user-invocable: true
---

# Implement Next

Advance the current implementation plan by one step.

## Procedure

1. Run `git status --short`. If it produces any output, stop immediately and refuse to continue. Report that the repository must be clean before `implement-next` can proceed; do not read further project files, edit files, run tests, or modify the plan.
2. Read `development-docs/IMPLEMENTATION-PLAN.md` and select the first unchecked step. Before reading implementation details, review `README.md` and `DEVELOPER.md` so the intended user experience and current technical decisions are part of the step context. Then read only the nearby source and tests needed to implement it.
3. Implement only that step, following existing project patterns and the documented architecture. Use the activated project virtual environment for Python execution and uv for dependency operations. Never expose secrets.
4. Add or update automated tests for every behavior-changing step. Run the step's stated validation, or the narrowest available check, with uv (for example `uv run --active python -m pytest`). Fix local failures before continuing.
5. For testable Python feature code, require at least 85% line coverage for the changed modules. Use `uv run --active python -m pytest --cov=<changed-module> --cov-report=term-missing --cov-fail-under=85` or an equivalent focused command.
6. If the 85% target cannot be met because the code is difficult to test, add the missing seams or tests. Do not lower the threshold or mark the step complete without documenting an explicit user-approved exception in the plan.
7. Review the completed implementation against both `README.md` and `DEVELOPER.md`. Update the root README whenever project intent, user-visible behavior, setup, or usage changes. Update the technical README whenever module responsibilities, runtime flow, invariants, testing guidance, or design decisions change. Keep both documents concise and current; do not turn them into progress logs.
8. Mark only the completed step as `[x]` in `development-docs/IMPLEMENTATION-PLAN.md`, after the documentation review and any required updates are complete.
9. Keep the plan concise: update wording only when implementation revealed a necessary, concrete correction. Do not add a progress diary.
10. When the final step completes, add a concise user-visible entry under `## [Unreleased]` in `development-docs/CHANGELOG.md` and ensure `development-docs/SKETCHBOOK.md` remains its clean template.
11. If unchecked steps remain, report the completed step and the next step. If no unchecked steps remain, report that the feature is ready for the `create-commit` skill; do not push.

## Guardrails

- A clean repository is mandatory. Any uncommitted, staged, or untracked change reported by `git status --short` is a hard stop; do not stash, revert, reset, or work around it.
- One invocation implements one plan step. Do not opportunistically implement later steps.
- Every behavior-changing step needs automated test coverage; aim for at least 85% line coverage of changed testable modules.
- Every step must review `README.md` and `DEVELOPER.md`; keep both synchronized with current implementation and design decisions before marking the step complete.
- Do not commit unless the user explicitly requests the `create-commit` skill or the workflow explicitly invokes it after the completed feature.
- Do not change the plan into a log of implementation details.
- Do not mark a step complete when its focused validation failed.
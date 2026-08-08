---
name: implement-next
description: "Implement the next unchecked step in development-docs/IMPLEMENTATION-PLAN.md for this Dockerized Python and Streamlit project. Use after plan-implementation, one step per invocation, with Docker-based focused validation and changelog maintenance."
argument-hint: "Optional instruction for the next plan step"
user-invocable: true
---

# Implement Next

Advance the current implementation plan by one step.

## Procedure

1. Read `development-docs/IMPLEMENTATION-PLAN.md` and select the first unchecked step. Read only the nearby source and tests needed to implement it.
2. Check the worktree before editing. Do not overwrite or revert unrelated user changes.
3. Implement only that step, following existing project patterns. Use Docker for all Python execution and `uv` inside the container for dependency operations. Never expose secrets.
4. Add or update automated tests for every behavior-changing step. Run the step's stated validation, or the narrowest available check, with `docker compose run --rm app <command>`. Fix local failures before continuing.
5. For testable Python feature code, require at least 85% line coverage for the changed modules. Use `docker compose run --rm app pytest --cov=<changed-module> --cov-report=term-missing --cov-fail-under=85` or an equivalent focused command.
6. If the 85% target cannot be met because the code is difficult to test, add the missing seams or tests. Do not lower the threshold or mark the step complete without documenting an explicit user-approved exception in the plan.
7. Mark only the completed step as `[x]` in `development-docs/IMPLEMENTATION-PLAN.md`.
8. Keep the plan concise: update wording only when implementation revealed a necessary, concrete correction. Do not add a progress diary.
9. When the final step completes, add a concise user-visible entry under `## [Unreleased]` in `development-docs/CHANGELOG.md` and ensure `development-docs/SKETCHBOOK.md` remains its clean template.
10. If unchecked steps remain, report the completed step and the next step. If no unchecked steps remain, report that the feature is ready for the `create-commit` skill; do not push.

## Guardrails

- One invocation implements one plan step. Do not opportunistically implement later steps.
- Every behavior-changing step needs automated test coverage; aim for at least 85% line coverage of changed testable modules.
- Do not commit unless the user explicitly requests the `create-commit` skill or the workflow explicitly invokes it after the completed feature.
- Do not change the plan into a log of implementation details.
- Do not mark a step complete when its focused validation failed.
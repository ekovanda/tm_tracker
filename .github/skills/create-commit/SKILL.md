---
name: create-commit
description: "Create one clean local Git commit for a completed feature or fix. Use when implementation is complete and the user asks to commit, or when the project workflow reaches its final step. Never push or expose secrets."
argument-hint: "Optional scope and short summary"
user-invocable: true
---

# Commit

Create a focused local commit after implementation is complete.

## Procedure

1. Inspect `git status --short` and the diff. Preserve unrelated user changes.
2. Review the feature's `development-docs/CHANGELOG.md` entry and confirm the workflow documents in `development-docs/` are clean and current.
3. Run the narrowest relevant validation in the activated project virtual environment through uv, such as `uv run --active python -m pytest`. If validation fails, do not commit; report the failure.
4. Inspect the exact files that will be staged. Do not stage `.env`, credentials, tokens, private keys, or other secret material.
5. Stage only files belonging to the completed feature.
6. Create one local commit with an imperative message in this form: `type(scope) short summary`.
   - Use `feat` for a new capability, `fix` for a correction, `refactor` for behavior-preserving restructuring, `test` for tests, and `docs` for documentation.
   - Keep the summary concise, lowercase after the scope, and without a period.
   - Examples: `feat(ui) add track focus filters`, `fix(auth) handle expired token`.
7. Verify the commit with `git status --short` and `git log -1 --oneline`.

## Safety Rules

- Never run `git push`.
- Never use destructive commands such as `git reset --hard` or `git checkout --`.
- Never commit secrets or print their values.
- If unrelated changes are present, leave them untouched and commit only the requested feature.
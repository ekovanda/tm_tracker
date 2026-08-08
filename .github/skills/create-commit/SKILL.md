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
2. Append to `development-docs/CHANGELOG.md` before staging whenever the commit contains a user-visible feature, fix, behavior change, or workflow change. Never erase, rewrite, reorder, or replace existing changelog entries. The new entry must be a concise, accurate, user-visible summary in the repository's existing format and include its creation timestamp in ISO 8601 format. Include a commit ID when one is already applicable and known; do not invent or guess one, and do not delay or amend a commit solely to make it reference its own unknowable final ID. A commit must not proceed without a sensible changelog entry; planning-only changes may explicitly document why no entry is appropriate.
3. Review the appended changelog entry and confirm the workflow documents in `development-docs/` are clean and current. Ensure the changelog change is included in the same commit as the feature or fix it describes.
4. Run the narrowest relevant validation in the activated project virtual environment through uv, such as `uv run --active python -m pytest`. If focused validation fails, do not commit; report the failure.
5. Inspect the exact files that will be staged. Do not stage `.env`, credentials, tokens, private keys, or other secret material.
6. Stage only files belonging to the completed feature, including its changelog entry.
7. Create one local commit with an imperative message in this form: `type(scope) short summary`. Run the normal commit hooks first. If a hook fails, fix failures tied to the staged files and retry. If remaining failures are demonstrably unrelated, pre-existing, or environment-only, record the exact failures and stop without committing; do not bypass the hooks.
   - Use `feat` for a new capability, `fix` for a correction, `refactor` for behavior-preserving restructuring, `test` for tests, and `docs` for documentation.
   - Keep the summary concise, lowercase after the scope, and without a period.
   - Examples: `feat(ui) add track focus filters`, `fix(auth) handle expired token`.
8. Verify the commit with `git status --short` and `git log -1 --oneline`.

## Safety Rules

- Never run `git push`.
- Never use `--no-verify` to hide a failure in changed files or to skip focused validation.
- Never use destructive commands such as `git reset --hard` or `git checkout --`.
- Never commit secrets or print their values.
- If unrelated changes are present, leave them untouched and commit only the requested feature.
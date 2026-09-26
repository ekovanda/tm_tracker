---
name: review-code
description: "Perform an evidence-based code review and write findings to development-docs/CODE-REVIEW-FINDINGS.md. Use when reviewing code, auditing a feature, checking regressions, assessing production readiness, or evaluating Trackmania/Nadeo API integrations."
argument-hint: "Optional scope, feature, files, or commit to review"
user-invocable: true
---

# Code Review

Perform a focused code review of the requested scope and write the result to `development-docs/CODE-REVIEW-FINDINGS.md`.

## Review Principles

- Findings come first, ordered by severity. Put summaries and praise after the findings.
- Report concrete bugs, risks, regressions, missing safeguards, and missing tests rather than style preferences alone.
- Every finding must include a severity, a short title, an existing file link with a 1-based line number, the observed behavior, why it matters, and a practical fix direction.
- Do not invent runtime behavior. Mark assumptions and unverified paths explicitly.
- Preserve unrelated user changes. Do not modify production code while performing a review unless the user explicitly asks for fixes.
- Do not expose credentials, tokens, personal data, or contents of `.env` files in the report.

## Severity Tiers

Use exactly these tiers:

### P0: Critical Safety Concerns

Use for issues that can cause credential or token exposure, destructive or unauthorized actions, account/IP bans, data loss, serious security compromise, or an unsafe production deployment. A P0 finding should explain the exploit or failure path and the immediate containment action.

### P1: Robustness and Functionality Concerns

Use for behavior that does not work, can silently produce incorrect results, fails under expected production conditions, cannot scale to the intended workload, mishandles authentication or API errors, blocks an important workflow, or lacks necessary recovery and state handling.

### P2: Feature, UI, and UX Concerns

Use for behavior that conflicts with stated user preferences or the intended workflow, confusing or inaccessible controls, misleading status, poor information hierarchy, or a feature that needs redesign to be usable. Do not use P2 for a purely aesthetic preference without a user-impact explanation.

### P3: Performance, Code Quality, and Documentation

Use for lower-risk performance issues, maintainability problems, test gaps, duplicated logic, unclear APIs, stale documentation, or observability improvements that do not currently break the main workflow.

## Required Workflow

1. Inspect the repository status and the requested review scope. Preserve unrelated worktree changes.
2. Read the owning implementation, its callers, neighboring tests, configuration, and relevant documentation. Use the smallest set of files that can establish each finding.
3. For each finding, identify the controlling code path and a concrete reproduction or disconfirming check where possible.
4. Review tests for the changed behavior. Note missing boundary, failure, concurrency, timing, authorization, and UI-state coverage when relevant.
5. For Trackmania/Nadeo integrations, consult the current Openplanet documentation before concluding:
   - Home and responsible usage: https://webservices.openplanet.dev/
   - Authentication overview: https://webservices.openplanet.dev/auth
   - Service accounts: https://webservices.openplanet.dev/auth/service
   - Token usage: https://webservices.openplanet.dev/auth/token
   - Live API reference: https://webservices.openplanet.dev/live
   - Live leaderboard reference: https://webservices.openplanet.dev/live/leaderboards
   - Live campaign reference: https://webservices.openplanet.dev/live/campaigns
6. Compare implementation behavior with the Openplanet guidance, including:
   - Use of the current service-account authentication flow where applicable.
   - Correct token handling and separation between authentication domains.
   - Endpoint, parameter, response, and error-handling assumptions.
   - A useful `User-Agent` containing the project identity, maintainer identity, and contact address.
   - Responsible request pacing. Openplanet documents no formal rate limit but describes about two requests per second as an upper bound for short bursts and recommends lower frequency for bulk or semi-live monitoring. Review aggregate request rate, retries, concurrency, polling cadence, and backoff.
   - Status, timeout, retry, and partial-failure behavior for external services.
7. Run the narrowest relevant tests, type checks, linters, or reproducible commands available. Do not claim validation that was not run.
8. Write or replace `development-docs/CODE-REVIEW-FINDINGS.md` with the findings and evidence. Keep the report concise but complete.
9. Re-read the report for severity accuracy, file links, secret safety, and stale claims. Do not commit unless the user separately requests a commit.

## Report Format

Use this structure in `development-docs/CODE-REVIEW-FINDINGS.md`:

```markdown
# Code Review Findings

- Review scope: <files, feature, commit, or repository area>
- Reviewed: <ISO 8601 timestamp>
- Reviewer reference: Openplanet Web Services documentation, consulted <date>

## Findings

### P0: Critical Safety Concerns

#### P0-1: <short finding title>

- Location: [path/to/file.py](path/to/file.py#L123)
- Evidence: <specific code path, input, or observed behavior>
- Impact: <security, safety, data, or production consequence>
- Recommendation: <specific remediation or containment>

_No P0 findings._

### P1: Robustness and Functionality Concerns

...

### P2: Feature, UI, and UX Concerns

...

### P3: Performance, Code Quality, and Documentation

...

## Validation

- `<command>`: <result>

## Open Questions and Assumptions

- <question or assumption, if any>

## Summary

<Short secondary summary after all findings.>
```

Omit empty tier headings only if the report remains easy to scan; otherwise retain them with `_No findings._`. Findings must remain ordered P0 through P3, and within a tier from highest impact to lowest impact.

## Openplanet Research Notes

Treat the Openplanet documentation as community-maintained and potentially incomplete. Record the consulted URLs and date in the report when the review concerns Nadeo or Trackmania APIs. Do not treat an undocumented endpoint as safe merely because it works; flag unsupported assumptions as P1 or P3 according to impact.

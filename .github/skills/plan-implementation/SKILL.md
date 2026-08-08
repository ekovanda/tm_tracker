---
name: plan-implementation
description: "Turn the ideas and requirements in development-docs/SKETCHBOOK.md into a concise, step-by-step implementation plan in development-docs/IMPLEMENTATION-PLAN.md for this Python project. Use when planning a feature, refining a sketch, or preparing work for the implement-next skill."
argument-hint: "Optional feature focus"
user-invocable: true
---

# Plan Implementation

Convert the current sketch into an actionable plan without implementing code.

## Procedure

1. Read `development-docs/SKETCHBOOK.md`, the relevant source files, and nearby tests or validation commands.
2. Identify the feature goal, affected modules, user-visible behavior, constraints, and an appropriate validation check.
3. Resolve obvious ambiguity from the codebase using the least surprising existing pattern. Ask the user only when a product or technical decision cannot be inferred safely.
4. Reconcile `development-docs/IMPLEMENTATION-PLAN.md` into a clean current plan. Preserve completed steps and their status, but treat the new requirements in `SKETCHBOOK.md` as the current priority: integrate them into the earliest relevant existing steps, reorder unchecked work when dependencies allow, split or revise stale steps, and append new steps only when no existing step can own the work. Do not append history or duplicate the sketch.
5. Use this structure:

```markdown
# Implementation Plan

## Feature
One-sentence outcome.

## Steps
- [ ] 1. Concrete change, with the files or symbols involved and its validation.
- [ ] 2. ...

## Completion Checks
- Relevant tests or commands.
- Changelog entry required.
- Local commit required through the `create-commit` skill.
```

6. Keep steps small enough that `implement-next` can complete one step without guessing. Include dependencies in order and avoid speculative tasks. When reprioritizing, keep completed steps before dependent work and move unrelated future work after the new sketch requirements.
7. Replace `development-docs/SKETCHBOOK.md` with a clean capture template after transferring its content:

```markdown
# Sketchbook
```

Leave the file with only the heading so an emptied sketchbook has no default instructional sentence. Do not discard requirements; transfer them into the plan first.

## Validation Planning

- Write validation commands for the activated project virtual environment through uv, such as `uv run --active python -m pytest` or `uv run --active python -m compileall .`.

## Plan Reconciliation

- The sketchbook is a prioritized intake, not an append-only backlog.
- First map each new sketch requirement to an existing plan step by affected module, behavior, or validation.
- Revise or split that step when it already owns the behavior; move it earlier if it is currently behind unrelated unchecked work.
- Add a new step only when the requirement has no suitable owner. Keep the new step adjacent to its dependency rather than automatically placing it at the end.
- Preserve completed steps unless the new requirement proves their behavior or validation is obsolete; in that case, add a focused follow-up step explaining the regression or replacement.

## Rules

- Planning does not modify application code.
- Do not claim implementation or testing is complete.
- Do not include secrets from source files, environment files, logs, or tool output.
- Do not add a changelog entry for a plan alone.
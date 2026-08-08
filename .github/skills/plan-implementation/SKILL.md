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
4. Rewrite `development-docs/IMPLEMENTATION-PLAN.md` as a clean plan. Do not append history or duplicate the sketch.
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

6. Keep steps small enough that `implement-next` can complete one step without guessing. Include dependencies in order and avoid speculative tasks.
7. Replace `development-docs/SKETCHBOOK.md` with a clean capture template after transferring its content:

```markdown
# Sketchbook

Add rough feature ideas here. Include the desired outcome, important constraints, and examples when known.
```

Do not discard requirements; transfer them into the plan first.

## Validation Planning

- Write validation commands for the activated project virtual environment through uv, such as `uv run --active python -m pytest` or `uv run --active python -m compileall .`.

## Rules

- Planning does not modify application code.
- Do not claim implementation or testing is complete.
- Do not include secrets from source files, environment files, logs, or tool output.
- Do not add a changelog entry for a plan alone.
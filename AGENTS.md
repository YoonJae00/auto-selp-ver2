# Agent Instructions

## Skills

This project uses the **Compound Engineering** workflow to ensure continuous learning and prevent regressions.

The following skills are available in `./.antigravitycli/skills/`:
- `/ce-compound`: Document a recently solved problem.
- `/ce-sessions`: Search session history for relevant knowledge.
- `/ce-plan`: Technical planning workflow.

### Usage Rule

1. **Before starting work**: Always check `docs/solutions/` for related problems and solutions.
2. **After finishing work**: (When merging or creating a PR) ALWAYS run `/ce-compound mode:headless` to document the solution and lessons learned.
3. **During review**: After implementing fixes based on feedback, run `/ce-compound` to capture the insights from the review cycle.

## Documentation

- `docs/solutions/`: Searchable knowledge store of documented solutions.
- `docs/superpowers/`: Project-specific plans and specs.

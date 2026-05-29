# Agent Instructions

## Skills

This project uses a selective **Compound Engineering** workflow only for documenting resolved problems and lessons learned.

The following skill is available:
- `/ce-compound`: Document a recently solved problem.

### Usage Rule

1. **After finishing work**: (When merging or creating a PR) ALWAYS run `/ce-compound mode:headless` to document the solution and lessons learned in `docs/solutions/`.
2. **During review**: After implementing fixes based on feedback, run `/ce-compound` to capture the insights from the review cycle.

## Documentation

- `docs/solutions/`: Searchable knowledge store of documented solutions.
- `docs/superpowers/`: Project-specific plans and specs.

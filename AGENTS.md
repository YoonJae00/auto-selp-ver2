# Agent Instructions

## Skills

This project uses a selective **Compound Engineering** workflow only for documenting resolved problems and lessons learned.

The following skill is available:
- `/ce-compound`: Document a recently solved problem.

### Usage Rule

1. **After finishing work**: (When merging or creating a PR) ALWAYS run `/ce-compound mode:headless` to document the solution and lessons learned in `docs/solutions/`.
2. **During review**: After implementing fixes based on feedback, run `/ce-compound` to capture the insights from the review cycle.

## Documentation

- `docs/solutions/`: Searchable knowledge store of documented solutions (bugs, best practices, workflow patterns), organized by category with YAML frontmatter (`module`, `tags`, `problem_type`). Highly relevant when implementing or debugging in documented areas.
- `docs/superpowers/`: Project-specific plans and specs.

## Worktree Environment

When running inside a Codex-created worktree for this repository, before running tests, Docker Compose, LangGraph, or dev servers:

1. If `.env` is missing at the repository root, run `scripts/link-worktree-env.sh`.
2. Never copy or commit `.env`; it must remain ignored.
3. Prefer a symlink to the main checkout env file at `/Users/yoonjae/Desktop/auto-selp-ver2/.env`.

The script only links the env file path. It must not print, copy, or commit secret values.

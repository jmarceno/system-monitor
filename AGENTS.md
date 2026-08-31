# AGENTS.md

Guidelines for AI agents and contributors working in this repository.

## Project Overview

`system-monitor` is a system monitoring project. Keep contributions focused, well-tested, and documented.

## Repository Structure

```
system-monitor/
├── AGENTS.md       # This file — instructions for AI agents
├── README.md       # Project documentation
├── .gitignore      # Git ignore rules
└── src/            # Source code (create as needed)
```

## Development Workflow

1. **Branching:** Create feature branches from `master` (`feat/<name>`, `fix/<name>`, `docs/<name>`).
2. **Commits:** Use conventional commits (`feat:`, `fix:`, `docs:`, `chore:`, `refactor:`).
3. **Testing:** Add or update tests for any logic change. Run tests locally before pushing.
4. **Linting/Formatting:** Follow existing style. Run formatters/linters if configured before committing.

## Coding Conventions

- Prefer clarity over cleverness. Write small, focused functions.
- Add error handling for system-level operations (I/O, processes, network).
- Document public APIs and non-obvious logic.
- Avoid hardcoding thresholds or paths — use config or environment variables.

## Agent Instructions

- Read `README.md` before making structural changes.
- Keep `AGENTS.md` up to date if workflow or conventions change.
- Do not commit secrets, credentials, or `.env` files.
- Verify changes with `git status` and `git diff` before committing.
- Prefer editing existing files over creating duplicates.

## Security Notes

- Never log or commit sensitive system information.
- Validate inputs when exposing system metrics via API or UI.

## Getting Help

Open an issue or check `README.md` for setup and usage details.

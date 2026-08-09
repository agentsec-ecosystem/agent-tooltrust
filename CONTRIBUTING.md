# Contributing to Agent ToolTrust

Thanks for your interest in Agent ToolTrust. This project enforces contextual risk policy for tool-using agents — please keep that safety bar in mind in every contribution.

## Development Setup

```bash
# Install uv (dependency management)
brew install uv   # or: pip install uv

# Clone and sync dependencies
git clone https://github.com/deghosal-2026/agent-tooltrust.git
cd agent-tooltrust
uv sync --extra dev
```

## Commands

| Command | Purpose |
|---------|---------|
| `uv run pytest` | Run the test suite |
| `uv run pytest --cov=agent_tooltrust --cov-fail-under=90` | Run tests with coverage gate |
| `uv run ruff check .` | Lint (must pass with zero errors) |
| `uv run mypy` | Type check in strict mode (must pass) |

## Before Submitting

- [ ] Tests pass with coverage above 90%
- [ ] `ruff check .` passes with zero errors
- [ ] `mypy` passes in strict mode
- [ ] Code has comments where behavior is non-obvious
- [ ] No secrets, API keys, or credentials (even in test fixtures)

## Branching and Commits

- Work on a feature branch off `main`: `git checkout -b feat/your-feature`
- Commit messages follow the [Conventional Commits](https://www.conventionalcommits.org/) style (`feat:`, `fix:`, `docs:`, `test:`, `chore:`)
- Open a PR against `main` with a description of what and why

## License

By contributing, you agree that your contributions are licensed under the MIT License (see [LICENSE](LICENSE)).
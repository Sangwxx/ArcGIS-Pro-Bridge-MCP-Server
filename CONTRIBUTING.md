# Contributing Guide

Thank you for contributing to the ArcGIS Pro Bridge MCP Server.

## Development Environment

- OS: Windows
- Python: `3.11+` recommended
- Package manager: `uv`
- ArcPy-related capabilities require ArcGIS Pro installed on the machine

## Development Workflow

1. Fork or clone the repository.
2. Create a feature branch.
3. Install dependencies:

```bash
uv sync
```

4. Run local checks before committing:

```bash
uv run ruff check .
uv run ruff format --check .
uv run python -m unittest discover -s tests -p "test_*.py"
```

## Commit Suggestions

- Keep changes focused, avoid unrelated modifications.
- Prioritize adding unit tests.
- If you change Tool / Resource return structures, update README and examples accordingly.

## Pull Request Suggestions

- Describe the change background, implementation, and verification results.
- If the change involves ArcGIS Pro behavior differences, note the test environment and version.

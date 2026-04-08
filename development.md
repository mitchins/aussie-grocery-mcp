# Development Guide

This guide is for contributors and maintainers.

## Local Development

### Option A (recommended): uv

```bash
uv sync
uv run python main.py
```

### Option B: pip + venv

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
python main.py
```

## Testing And Linting

```bash
# Run tests
pytest -q

# Run linting
ruff check .

# Run tests with coverage report for SonarCloud
pytest -q --cov=main --cov=cache --cov-report=xml:coverage.xml
```

## CI/CD

### Workflows

- `.github/workflows/ci.yml`
  - Runs on push and pull request
  - Installs project dev extras from `pyproject.toml`
  - Runs Ruff and pytest
  - Generates `coverage.xml` and runs Sonar scan
- `.github/workflows/release-ghcr.yml`
  - Runs on tags matching `v*.*.*`
  - Runs quality gate (Ruff + pytest)
  - Builds and pushes Docker image to GHCR

### Required Repository Settings

- SonarCloud: add repository secret `SONAR_TOKEN`
- GHCR publishing: Actions must be allowed to write packages

## Release Process

### Publish Docker image on tag

```bash
git tag v0.1.0
git push origin v0.1.0
```

Image names:

- `ghcr.io/<owner>/<repo>:v0.1.0`
- `ghcr.io/<owner>/<repo>:latest`

Pull example:

```bash
docker pull ghcr.io/<owner>/<repo>:v0.1.0
```

## Sonar Notes

- Coverage appears in SonarCloud only when `coverage.xml` is present.
- Coverage path is configured via `sonar.python.coverage.reportPaths=coverage.xml`.

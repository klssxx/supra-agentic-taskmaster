# Changelog

All notable changes to SUPRA are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Changed
- Made `uv 0.11.28` the canonical Python package and environment manager.
- Added a checked-in `uv.lock` and reproducible `uv sync --all-extras --locked` setup.
- Replaced `pip install`, direct Python execution, and ad-hoc environments in the
  launcher, CI, and production Docker image with `uv` commands.
- Migrated CI to `astral-sh/setup-uv` v9.0.0, pinned to commit
  `c771a70e6277c0a99b617c7a806ffedaca235ff9`, with explicit cache pruning keyed
  by `uv.lock`.
- Declared Ruff, mypy, pip-audit, Bandit, Semgrep, pre-commit, and CycloneDX in
  the project `dev` extra.

### Security
- CI now exports the locked dependency graph and runs `pip-audit` with hashes
  and strict mode before package validation.
- The tag release workflow builds both distributions with `uv build` and uploads
  them as a GitHub Actions artifact; it does not publish or push automatically.
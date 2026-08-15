# v0.2.0 Release Checklist

**Status:** In progress
**Branch:** `rel-0.2.0`

| # | Step | Status | Notes |
|---|------|--------|-------|
| 1 | Update all docs with new features (PRD, README, user guide, quick start) | ❌ | Audit, analytics, PDP, calibration, packs, OPAL, M7 baselines |
| 2 | Check test consistency — all new features have integration + e2e tests | ❌ | Verify coverage per module |
| 3 | Regenerate all UI screenshots | ❌ | Run Playwright E2E suite |
| 4 | Update field tests for v0.2.0 scenarios | ❌ | Add new scenario packs |
| 5 | Run field tests A and B to confirm pass | ❌ | `tooltrust field-test` |
| 6 | Lint clean check | ❌ | `ruff check .` |
| 7 | Run security scans | ❌ | trufflehog, `tooltrust baseline check hardened` |
| 8 | Bump version in pyproject.toml to 0.2.0 | ❌ | `__version__` and pyproject.toml |
| 9 | Update SECURITY.md supported versions (add 0.2.x) | ❌ | Supported versions table |
| 10 | Build Docker image and verify all endpoints serve | ❌ | `docker compose up --wait` + smoke test |
| 11 | Write migration guide v0.1.x → v0.2.0 | ❌ | Breaking changes, new features |
| 12 | Update release notes + CHANGELOG | ❌ | `docs/reference/release-notes-v0.2.0.md` |
| 13 | Publish to PyPI | ❌ | `uv build && uv publish` |
| 14 | Tag release (`git tag v0.2.0`) and push | ❌ | Push tags to GitHub |
| 15 | Create GitHub Release with release notes | ❌ | Link to CHANGELOG |
| 16 | Update WBS status to released | ❌ | Mark `rel-0.2.0` as shipped |
| 17 | Create dev.to article on v0.2.0 release | ❌ | New features, issues fixed, reference to v0.1.0 article |
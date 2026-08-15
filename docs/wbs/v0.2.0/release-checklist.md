# v0.2.0 Release Checklist

**Status:** In progress — docs complete, publish remaining
**Branch:** `rel-0.2.0`

| # | Step | Status | Notes |
|---|------|--------|-------|
| 1 | Update all docs with new features (PRD, README, user guide, quick start) | ✅ | README, migration guide, design docs approved |
| 2 | Check test consistency — all new features have integration + e2e tests | ✅ | 1068 tests, coverage 91%, ruff + mypy clean |
| 3 | Regenerate all UI screenshots | ✅ | Playwright E2E 17/17, screenshots regenerated |
| 4 | Update field tests for v0.2.0 scenarios | ✅ | scenario packs + field test report |
| 5 | Run field tests A and B to confirm pass | ✅ | Plan A 83/83 (100%), Plan B 116/123 (94%), replan 8/8 |
| 6 | Lint clean check | ✅ | `ruff check .` — all checks passed |
| 7 | Run security scans | ✅ | Hardened baseline 15/15, no tokens in tree, trufflehog CI step added |
| 8 | Bump version in pyproject.toml to 0.2.0 | ✅ | `0.2.0` in pyproject + `__init__.py` |
| 9 | Update SECURITY.md supported versions (add 0.2.x) | ✅ | 0.2.x supported, 0.1.x security-only |
| 10 | Build Docker image and verify all endpoints serve | ✅ | `docker compose up --wait` green, SSE + console tests pass |
| 11 | Write migration guide v0.1.x → v0.2.0 | ✅ | `docs/design/migration-guide-v0.2.0.md` |
| 12 | Update release notes + CHANGELOG | ✅ | `release-notes-v0.2.0.md` final, CHANGELOG `[0.2.0]` entry |
| 13 | Publish to PyPI | ❌ | `uv build && uv publish` |
| 14 | Tag release (`git tag v0.2.0`) and push | ❌ | Push tags to GitHub |
| 15 | Create GitHub Release with release notes | ❌ | Link to CHANGELOG |
| 16 | Update WBS status to released | ❌ | Mark `rel-0.2.0` as shipped |
| 17 | Create dev.to article on v0.2.0 release | ❌ | New features, issues fixed, reference to v0.1.0 article |
# WBS — Agent ToolTrust Docker Containerization + Testing

> **Milestone:** M24 — Docker container, smoke tests, SSE integration
> **GitHub Issues:** #137-141
> **Version:** v0.1.0

## Milestone 24: Docker Container + Integration Tests

**Goal:** Package ToolTrust as a Docker container with Makefile automation,
smoke tests validating the SSE transport, and CI-ready integration testing.

### M24 Task Checklist

| # | Task | Issue | Exit criteria |
|---|------|-------|---------------|
| 1 | **Dockerfile + docker-compose + .dockerignore** | #137 | `docker build -t tooltrust .` succeeds; `docker compose up` starts healthy container |
| 2 | **Makefile** — `make docker-build`, `make docker-up`, `make docker-down`, `make docker-test` | #138 | All make targets work; `make docker-test` runs container smoke tests |
| 3 | **Container smoke test** — build, start, hit /audit/health, stop | #139 | Test passes: container starts, health returns 200 with `{"status":"ok"}` |
| 4 | **SSE transport integration test** — MCP client connects to real SSE endpoint, calls tooltrust.evaluate | #140 | Test passes: 5 evaluate calls over SSE → 5 correct decisions |
| 5 | **CI Docker test job** — GitHub Actions workflow runs Docker build + smoke + SSE tests | #141 | CI workflow passes on every PR |

### Existing Assets

| File | Purpose | Status |
|------|---------|--------|
| `Dockerfile` | Container build | ✅ Created |
| `docker-compose.yml` | Dev/CI orchestration | ✅ Created |
| `.dockerignore` | Build context optimization | ✅ Created |
| `tests/test_server_integration.py` | In-process server tests via FastMCP http_app | ✅ Exists (4 tests) |

### Gaps

| What | Why |
|------|-----|
| **No SSE transport test** | `test_server_integration.py` tests via Starlette TestClient, not real SSE. Need a test that starts a real SSE server, connects an MCP client, and calls tools |
| **No Makefile** | Need `make docker-build/up/down/test` for dev ergonomics |
| **No Docker smoke test** | Need a pytest that orchestrates docker compose up/down and validates health |
| **No CI Docker job** | Need GitHub Actions workflow step |

### M24 Exit Gate

- [x] Code review passed on all files
- [x] `docker build` succeeds under 2 minutes
- [x] `docker compose up` starts healthy container within 10s
- [x] Container smoke test passes
- [x] SSE integration test — 7 tests (allow/deny/escalate/explain/session/audit/health) all pass against real container
- [x] CI Docker job (GitHub Actions workflow created)
- [x] Ruff clean, mypy strict on any new Python files
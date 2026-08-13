# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-08-13

### Added

- **Core decision engine** (`agent_tooltrust.engine`) — five-stage pipeline
  `NORMALIZE → SCORE → DECIDE → EXPLAIN → AUDIT` returning one of four
  decisions: `allow`, `audit`, `escalate`, `deny`. Fails closed on any error;
  every undocumented failure is a deny, never an exception and never an allow.
- **Risk scoring** across five dimensions (tool category, action class,
  environment, data sensitivity, agent class) with a deterministic band
  mapping (`low→allow`, `medium→audit`, `high→escalate`, `critical→deny`).
- **Adversarial normalization** — Unicode NFKC + case fold + confusable
  transliteration (Cyrillic/Greek lookalikes) so tool names cannot be
  obfuscated past the engine (F-89 P0).
- **Policy model & presets** — balanced / strict / permissive postures, YAML
  loader with Pydantic schema, `tooltrust.yaml`, versioning, OPA/Rego backend,
  and hot-reload watcher.
- **Shadow / dry-run mode** — `allow` returned but the real verdict recorded
  in the audit trail.
- **6 framework adapters + raw + MCP wrapper** — LangGraph, PydanticAI,
  OpenAI Agents SDK, CrewAI, AutoGen, LlamaIndex, SmolAgents, ADK, raw
  Python `@engine.guard`, and an MCP server with `evaluate` / `explain` /
  `session_status` tools (SSE).
- **Audit logging & tamper-evident chain** — JSONL, SQLite, and Postgres
  sinks, `tooltrust audit` CLI, and a hash chain that detects tampering.
- **CLI** — `tooltrust init`, `evaluate`, `explain`, `check`, `diff`,
  `scan`, `report`, `audit`, `test`, `swebench`, and `field-test`.
- **Argument validators, output inspection, tool scanning** —
  `register_arg_validators` (path-traversal, URL, positive-int guards),
  output inspector (secret / PII / injection detection), and a tool scanner.
- **Observability & limits** — OpenTelemetry integration and rate-limit
  regression coverage.
- **Field test harness** — 83-agent roster across 10 frameworks, decision
  matrix (2,490 assertions, 83/83 Plan A), 100 adversarial assertions,
  determinism (A/B plans), and a model-replan round-trip (deny → different
  tool → allow). CI-safe scripted replan obsoletes the LLM dependency.
- **SWE-bench integration** (`agent_tooltrust.integrations.swe_bench`) —
  classifies raw coding-agent tool calls and replays 5-task benchmarks.
- **Docker image + compose** — containerized server with health endpoint and
  SSE integration tests.
- **Demo agent** (`examples/demo-agent/`) — 5-call decision spectrum
  (allow/audit/escalate/deny/replan) + adversarial variant showing prompt
  injection and Unicode/homoglyph denial (F-91).
- **Governance** — OWASP Agentic Top 10 mapping, security baseline, and
  tamper-evident audit reporting.

### Fixed

- Docker smoke port aligned to 9000 to match `docker-compose.yml`.
- CI `uv sync --group dev` now works (PEP 735 dependency groups) and mypy
  `python_version` aligned with the 3.13 toolchain.
- Scripted replan sweep loads the roster without importing a test module, so
  the installed CLI runs in CI.

### Known Limitations

- Coverage baseline accepted at 85% for this release (target raised in v0.2).
- OWASP Agentic Top 10: 5/10 covered in v0.1.0; remaining 5 target v0.2+.
- OpenSSF Silver/Sigstore and PyPI publication are staged for the release
  gate. Live-replan field sweep requires a local LLM endpoint (omlx).

## [Unreleased]

### Added
- Initial project scaffold with OSS community files
- M23: SWE-bench integration (`agent_tooltrust.integrations.swe_bench`) —
  `SWEBenchToolMapper` classifies raw coding-agent tool calls,
  `SWEBenchGuard` enforces policy per call with a per-task decision trace,
  `SWEBenchRunner` replays task fixtures, and `tooltrust swebench` runs a
  5-task benchmark with violations flagged (#135, F-92)

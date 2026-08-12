# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Initial project scaffold with OSS community files
- M23: SWE-bench integration (`agent_tooltrust.integrations.swe_bench`) —
  `SWEBenchToolMapper` classifies raw coding-agent tool calls,
  `SWEBenchGuard` enforces policy per call with a per-task decision trace,
  `SWEBenchRunner` replays task fixtures, and `tooltrust swebench` runs a
  5-task benchmark with violations flagged (#135, F-92)
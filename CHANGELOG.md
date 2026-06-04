# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project aims to adhere to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Apache License 2.0 (`LICENSE`) and attribution `NOTICE`, making the framework's
  open-source status explicit (#32).
- Framework / instance split: the domain-agnostic engine lives at the repo root and
  the retail reference instance moves to `examples/retail/`, with a
  `config/defaults.yaml` + per-instance config merge resolved via `AIOPS_INSTANCE`
  (#27, #36, #38).
- Instance-agnostic CI: the active instance is derived from the changed paths in a
  PR, and CI also triggers on framework changes under `evaluation/**` (#39, #41).
- Diátaxis `docs/` tree, including the canonical cost model and the Pillar 1
  (input governance) explanation (#24).

### Changed

- Cost model is denominated in **Snowflake AI Credits** (not USD), uses a
  cache-aware credit formula, and is calibrated against measured token actuals from
  observability traces (#28, #42).

### Fixed

- Phase 0 CI/CD stabilization: key-pair authentication for headless runs and removal
  of deprecated `COMPLETE('analyst')` Cortex calls from monitoring/health checks
  (#10, #25, #26, #33).
- Semantic-view question-bank evaluation scored 0% under the CI deployer role due to
  a Cortex Analyst response-shape mismatch in the SQL extractor (#37, #40).
- `audit_agent.py`: fail-fast on errors, percentage-based output, and stale-dataset
  detection (#16).
- `bootstrap.py`: state-tracking SQL splitter (handles `BEGIN…END` blocks and quoted
  semicolons) and clean observability view setup (#17).

## [v1] - 2026-04-30

Initial reference implementation.

### Added

- Two-loop architecture: Loop 1 (CI evaluation against a question bank, scored by an
  LLM judge) and Loop 2 (deterministic interaction-quality rules engine over
  `ai_observability_events`, no LLM cost).
- Structural semantic-view audit (`audit_semantic_view.py`) — offline, domain-agnostic
  rule checks (Pillar 1, input governance).
- Native `EXECUTE_AI_EVALUATION` integration with custom LLM-judge metrics
  (`safety`, `groundedness`, `execution_efficiency`) alongside built-in
  `answer_correctness` and `logical_consistency`.
- Two-tier DEV / PROD model with graduated CI/CD promotion thresholds.
- One-command setup via `bootstrap.py` (databases, RBAC, tables, semantic view,
  agent, first evaluation) using `CREATE AGENT … FROM SPECIFICATION` and
  `SYSTEM$CREATE_SEMANTIC_VIEW_FROM_YAML`.
- Streamlit-in-Snowflake monitoring dashboard (evaluations, interaction quality,
  feedback, token costs, alerts).

[Unreleased]: https://github.com/jar-ry/snowflake_AIOps_framework/compare/v1...HEAD
[v1]: https://github.com/jar-ry/snowflake_AIOps_framework/releases/tag/v1

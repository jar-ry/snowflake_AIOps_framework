# AI Evaluation Framework - Agent Instructions

## Project Overview

This is an end-to-end framework for developing, testing, promoting, and monitoring **Semantic Views** and **Cortex Agents** in Snowflake. It targets data teams who want to self-serve semantic view development while maintaining production-grade quality gates via CI/CD.

The mock domain is **retail/e-commerce** with a database of customers, products, orders, order items, returns, and stores.

## Conventions

- Always ask the user when unsure or when design decisions are needed
- Always plan and document the plan before starting any work
- Write all code to files so everything is reproducible (no ephemeral snippets)
- Generate mocked data and database schemas rather than relying on existing data
- All SQL follows Snowflake SQL syntax
- Python scripts use `snowflake-connector-python` and connect via named connections
- YAML is used for configuration (environments, thresholds, question banks, monitoring)
- GitHub Actions for CI/CD (not Jenkins, not GitLab CI)

## Snowflake Environment

| Resource | Value |
|----------|-------|
| DEV database | `RETAIL_AI_DEV` |
| PROD database | `RETAIL_AI_PROD` |
| Eval database | `RETAIL_AI_EVAL` |
| Schemas per env | `ANALYTICS` (tables), `SEMANTIC` (SV, agents, eval datasets) |
| Monitoring schema | `RETAIL_AI_EVAL.MONITORING` |
| Observability schema | `RETAIL_AI_EVAL.OBSERVABILITY` |
| Results schema | `RETAIL_AI_EVAL.RESULTS` |
| Warehouse | `RETAIL_AI_EVAL_WH` (XSMALL) |
| Semantic View | `RETAIL_AI_{ENV}.SEMANTIC.RETAIL_ANALYTICS_SV` |
| Agent | `RETAIL_AI_{ENV}.SEMANTIC.RETAIL_AGENT` |
| Agent LLM | `claude-opus-4-7` |
| LLM judge model | `claude-opus-4-7` (configurable in `config/defaults.yaml` → `llm.judge_model`) |

### RBAC Roles

| Role | Purpose |
|------|---------|
| `RETAIL_AI_ANALYST` | Create/edit SV in DEV, submit feedback, read results |
| `RETAIL_AI_REVIEWER` | Inherits Analyst, read access across envs |
| `RETAIL_AI_DEPLOYER` | Deploy SV/agents to DEV/PROD, write eval results, run tasks |
| `RETAIL_AI_ADMIN` | Full access to everything |

Hierarchy: ANALYST → REVIEWER → ADMIN, DEPLOYER → ADMIN → SYSADMIN

## Promotion Path (2-tier)

```
Feature branch → PR (CI: deploy to DEV + evaluate) → Merge to main → CD: promote to PROD
```

## Directory Structure

```
ai_evaluation_framework/
├── setup/                                # FRAMEWORK setup (bootstrap.py runs all, domain-agnostic)
│   ├── bootstrap.py                      # One-command setup: python setup/bootstrap.py --example examples/retail
│   ├── deploy.py                         # Config-driven SV/agent deploy (used by CI)
│   ├── 01_create_databases.sql           # DEV/PROD/EVAL databases, schemas, eval result tables, warehouse
│   ├── 04_rbac_setup.sql                 # Roles and grants
│   ├── 05_observability_setup.sql        # Views over snowflake.local.ai_observability_events
│   ├── 07_monitoring_tables.sql          # Feedback, usage, health, alert tables + RBAC
│   ├── 08_monitoring_tasks.sql           # 5 Snowflake Tasks + 2 stored procedures
│   ├── 09_monitoring_views.sql           # 7 trend views for Snowsight dashboards
│   ├── 10_monitoring_alerts.sql          # 7 Snowflake Alerts
│   ├── 11_interaction_quality_engine.sql # Rules-based interaction quality detection
│   └── teardown.sql                      # Token-rendered full purge (via bootstrap --render)
├── evaluation/                           # FRAMEWORK evaluation engine (config-driven)
│   ├── audit_semantic_view.py            # Best practices audit (DDL parsing, no SF connection)
│   ├── audit_agent.py                    # Native EXECUTE_AI_EVALUATION (GPA framework)
│   ├── evaluate_semantic_view.py         # Batch SV eval with SQL comparison + LLM judge
│   ├── llm_judge.py                      # LLM-as-a-Judge for SV ambiguous evaluation
│   └── utils.py                          # Instance resolver (load_config/instance_dir) + SF helpers
├── monitoring/                           # FRAMEWORK monitoring
│   ├── health_check.py                   # 7 DEV/PROD health checks (runnable locally or in CI)
│   ├── dashboard.py                      # Streamlit in Snowflake (SiS) monitoring dashboard
│   └── snowflake.yml.template            # SiS deploy descriptor (token-rendered at deploy time)
├── .github/workflows/                    # FRAMEWORK CI/CD (triggers on examples/retail/**)
│   ├── semantic_view_ci.yml              # PR: audit → question bank eval → PR comment
│   ├── semantic_view_cd.yml              # Merge: audit gate → final eval → deploy to PROD
│   ├── agent_ci.yml                      # PR: deploy to DEV → native GPA eval → PR comment
│   └── agent_cd.yml                      # Merge: native GPA eval gate → deploy to PROD
├── config/
│   └── defaults.yaml                     # FRAMEWORK defaults: LLM models + credit pricing (universal)
├── examples/retail/                      # INSTANCE: bundled retail example (copy to make your own)
│   ├── config/                           # environments.yaml, thresholds.yaml, monitoring.yaml, schedules.yaml
│   ├── semantic_views/{dev,prod}/        # CREATE SEMANTIC VIEW DDL per environment
│   ├── agents/{dev,prod}/                # CREATE CORTEX AGENT DDL per environment
│   ├── question_banks/{semantic_view,agent}/  # YAML question banks
│   ├── data/                             # 02_create_tables, 03_seed_data, 06_eval_dataset_setup (token-rendered)
│   ├── seed/seed_demo.py                 # Demo dashboard seeding (invoked by bootstrap)
│   └── demo/                             # demo_runbook.md, snowsight_walkthrough.md, market_positioning.md
├── AGENT.md                              # This file
└── README.md                             # Full documentation
```

## Key Technical Patterns

### Observability
- **Primary source**: `snowflake.local.ai_observability_events` (Snowflake's native AI observability view)
- No custom event table needed. Convenience views in `RETAIL_AI_EVAL.OBSERVABILITY` wrap the native view.
- Key span names: `ReasoningAgentStepPlanning-N`, `CodingAgent.Step-N`, `SqlExecution_CortexAnalyst`, `Agent`, `AgentV2RequestResponseInfo`
- Token fields: `snow.ai.observability.agent.planning.token_count.{input,output,total,cache_read_input}`
- Agent identity: `snow.ai.observability.{database.name,schema.name,object.name,object.type}`

### Evaluation Pipeline (Two Layers)

**Layer 1 — Audits (structural quality gate):**
- `audit_semantic_view.py`: Parses DDL, checks documentation, naming, metadata, relationships, inconsistencies, duplicates. Severity-based pass/fail (CRITICAL/ERROR = fail).
- `audit_agent.py`: Uses Snowflake's native `EXECUTE_AI_EVALUATION` with GPA framework metrics (`answer_correctness`, `logical_consistency`) plus custom metrics (`safety`, `groundedness`, `execution_efficiency`). Requires VARIANT-typed `ground_truth` column with `PARSE_JSON`.

**Layer 2 — Question Bank Evaluation (accuracy gate):**
- `evaluate_semantic_view.py`: Calls Cortex Analyst, compares generated SQL results to ground truth, uses LLM judge for ambiguous questions.

### Monitoring Layer

**Snowflake Tasks (automated daily/weekly):**

| Task | Schedule | What |
|------|----------|------|
| `TASK_DAILY_USAGE_AGGREGATION` | 02:00 UTC | Token/cost aggregation from observability events |
| `TASK_DAILY_FEEDBACK_ANALYSIS` | 02:15 UTC | CORTEX.SENTIMENT scoring + daily rollup |
| `TASK_DAILY_INTERACTION_QUALITY` | 02:30 UTC | Rules-based quality flag scan |
| `TASK_DAILY_HEALTH_CHECKS` | 06:00 UTC | SV/agent existence, error rate, latency |
| `TASK_WEEKLY_SV_EVAL` | Sun 04:00 UTC | PROD SV smoke test |
| `TASK_WEEKLY_AGENT_EVAL` | Sun 05:00 UTC | PROD agent smoke test |

**Snowflake Alerts (threshold-based):**

| Alert | Trigger |
|-------|---------|
| `ALERT_NEGATIVE_FEEDBACK_SPIKE` | >25% negative feedback in a day |
| `ALERT_ACCURACY_REGRESSION` | >10% accuracy drop between runs |
| `ALERT_LATENCY_DEGRADATION` | P95 > 30s |
| `ALERT_COST_ANOMALY` | Daily cost > 2x 7-day average |
| `ALERT_ERROR_SPIKE` | Error rate > 10% |
| `ALERT_HEALTH_FAILURE` | Any UNHEALTHY health check |
| `ALERT_INTERACTION_QUALITY` | >20% flagged requests or any CRITICAL |

**Interaction Quality Rules Engine:**
Deterministic rules over `ai_observability_events` that detect: tool looping, excessive steps, slow requests, high token burn, planning errors, abandoned conversations, rapid rephrasing, single-turn drop-offs. No LLM calls needed.

**Monitoring Views (for Snowsight dashboards):**
`V_EVAL_ACCURACY_TREND`, `V_FEEDBACK_TREND`, `V_TOKEN_COST_TREND`, `V_AGENT_USAGE_PATTERNS`, `V_HEALTH_DASHBOARD`, `V_ACTIVE_ALERTS`, `V_WEEKLY_EXECUTIVE_SUMMARY`, `V_INTERACTION_QUALITY_FLAGS`, `V_INTERACTION_QUALITY_DASHBOARD`, `V_REQUEST_QUALITY_SIGNALS`, `V_THREAD_QUALITY_SIGNALS`

**Streamlit Dashboard** (Streamlit in Snowflake):
Deployed as SiS app at `RETAIL_AI_EVAL.MONITORING.AI_MONITORING_DASHBOARD`.
Access via Snowsight: Projects → Streamlit → AI_MONITORING_DASHBOARD.
Deploy/redeploy: `cd monitoring && snow streamlit deploy --replace`.
6 tabs: Overview, Evaluations, Interaction Quality, Feedback, Token Costs, Alerts. Sidebar filters for environment and date range.

### CI/CD (GitHub Actions)

| Workflow | Trigger | What |
|----------|---------|------|
| `semantic_view_ci.yml` | PR on `examples/retail/semantic_views/` | Audit → eval on DEV → PR comment |
| `semantic_view_cd.yml` | Merge to main | Audit gate → eval on DEV → deploy to PROD |
| `agent_ci.yml` | PR on `examples/retail/agents/` | Deploy to DEV → native GPA eval → PR comment |
| `agent_cd.yml` | Merge to main | Native GPA eval on DEV → deploy to PROD |

### Connection Pattern

Python scripts connect via named connection or env vars:
```python
import os, snowflake.connector
conn = snowflake.connector.connect(
    connection_name=os.getenv("SNOWFLAKE_CONNECTION_NAME") or "default"
)
```

### Agent API Pattern

Agent calls use the Cortex Agents Run REST API (recommended by Snowflake):
```python
import requests
url = f"https://{host}/api/v2/cortex/agent:run"
payload = {
    "messages": [{"role": "user", "content": [{"type": "text", "text": question}]}],
    "tools": [{"tool_spec": {"type": "cortex_analyst_text_to_sql", "name": "RetailAnalyst", ...}}],
    "tool_resources": {
        "RetailAnalyst": {
            "semantic_view": "DB.SCHEMA.SV_NAME",
            "execution_environment": {"type": "warehouse", "warehouse": "WH_NAME"},
        }
    },
}
resp = requests.post(url, json=payload, headers=headers, stream=True)
```

The warehouse is passed at request time via `tool_resources.execution_environment` — no Snowsight UI configuration needed.

### Native Agent Evaluation (GPA Framework)
- `CALL EXECUTE_AI_EVALUATION('START', OBJECT_CONSTRUCT('run_name', '...'), '@stage/config.yaml')` — start evaluation
- `CALL EXECUTE_AI_EVALUATION('STATUS', OBJECT_CONSTRUCT('run_name', '...'), '@stage/config.yaml')` — poll status
- `SNOWFLAKE.LOCAL.GET_AI_EVALUATION_DATA(db, schema, agent, 'CORTEX AGENT', run)` — get results
- `SNOWFLAKE.LOCAL.GET_AI_RECORD_TRACE(db, schema, agent, 'CORTEX AGENT', record_id)` — drill into individual records
- `SNOWFLAKE.LOCAL.GET_AI_OBSERVABILITY_LOGS(db, schema, agent, 'CORTEX AGENT')` — errors and warnings
- `snowflake.local.ai_observability_events` — raw trace data
- LLM judges auto-selected by Snowflake (cross-region inference)

### Configuration Files

The framework reads a merged config: universal **defaults** at the repo root, overlaid by the active **instance** (set via `AIOPS_INSTANCE`, default `examples/retail`).

- `config/defaults.yaml` — FRAMEWORK defaults (universal): LLM model selection (`llm.model`, `llm.judge_model`) + Snowflake per-model credit pricing
- `examples/retail/config/environments.yaml` — INSTANCE: per-env database, schema, warehouse, SV/agent names, paths, and the `example` orchestration block (data_scripts, seed_module)
- `examples/retail/config/thresholds.yaml` — graduated accuracy thresholds (DEV 60% → PROD 85%)
- `examples/retail/config/monitoring.yaml` — alert thresholds, schedules, token cost estimates, notification settings
- `examples/retail/config/schedules.yaml` — task schedule profiles (demo/prod)

## GitHub Actions Secrets Required

| Secret | Description |
|--------|-------------|
| `SNOWFLAKE_ACCOUNT` | Snowflake account identifier |
| `SNOWFLAKE_USER` | Service account username |
| `SNOWFLAKE_PASSWORD` | Service account password |
| `SNOWFLAKE_CONNECTION_NAME` | Named connection (optional, defaults to `default`) |

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
| LLM judge model | `claude-opus-4-7` (configurable in `config/environments.yaml` → `llm.judge_model`) |

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
├── setup/                                # Snowflake SQL setup (run in order)
│   ├── 01_create_databases.sql           # DEV/TEST/PROD databases, eval results tables
│   ├── 02_create_tables.sql              # CUSTOMERS, PRODUCTS, ORDERS, ORDER_ITEMS, RETURNS, STORES
│   ├── 03_seed_data.sql                  # 500 customers, 100 products, 20 stores, 5000 orders
│   ├── 04_rbac_setup.sql                 # Roles and grants
│   ├── 05_observability_setup.sql        # Views over snowflake.local.ai_observability_events
│   ├── 06_eval_dataset_setup.sql         # OBJECT-typed ground truth for EXECUTE_AI_EVALUATION
│   ├── 07_monitoring_tables.sql          # Feedback, usage, health, alert tables + RBAC
│   ├── 08_monitoring_tasks.sql           # 5 Snowflake Tasks + 2 stored procedures
│   ├── 09_monitoring_views.sql           # 7 trend views for Snowsight dashboards
│   ├── 10_monitoring_alerts.sql          # 6 Snowflake Alerts
│   └── 11_interaction_quality_engine.sql # Rules-based interaction quality detection
├── semantic_views/{dev,prod}/          # CREATE SEMANTIC VIEW DDL per environment
├── agents/{dev,prod}/                  # CREATE CORTEX AGENT DDL per environment
├── question_banks/
│   ├── semantic_view/                    # easy, hard, ambiguous YAML question banks
│   └── agent/                            # answerable, out_of_scope, adversarial YAML
├── evaluation/
│   ├── audit_semantic_view.py            # Best practices audit (DDL parsing, no SF connection)
│   ├── audit_agent.py                    # Native EXECUTE_AI_EVALUATION (GPA framework)
│   ├── evaluate_semantic_view.py         # Batch SV eval with SQL comparison + LLM judge
│   ├── llm_judge.py                      # LLM-as-a-Judge for SV ambiguous evaluation
│   └── utils.py                          # Shared: connection, SQL exec, analyst/agent calls
├── monitoring/
│   ├── health_check.py                   # 7 PROD health checks (runnable locally or in CI)
│   └── dashboard.py                      # Streamlit monitoring dashboard (all tabs)
├── .github/workflows/
│   ├── semantic_view_ci.yml              # PR: audit → question bank eval → PR comment
│   ├── semantic_view_cd.yml              # Merge: audit gate → final eval → deploy to PROD
│   ├── agent_ci.yml                      # PR: deploy to TEST → native GPA eval → PR comment
│   └── agent_cd.yml                      # Merge: native GPA eval gate → deploy to PROD
├── config/
│   ├── environments.yaml                 # Database, schema, warehouse, SV, agent per env
│   ├── thresholds.yaml                   # Accuracy thresholds: DEV 60% → TEST 75% → PROD 85%
│   └── monitoring.yaml                   # Alert thresholds, schedules, token cost estimates
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

**Streamlit Dashboard** (`monitoring/dashboard.py`):
Run with `streamlit run monitoring/dashboard.py`. Uses `st.connection("snowflake")` with `.streamlit/secrets.toml`.
6 tabs: Overview, Evaluations, Interaction Quality, Feedback, Token Costs, Alerts. Sidebar filters for environment and date range.

### CI/CD (GitHub Actions)

| Workflow | Trigger | What |
|----------|---------|------|
| `semantic_view_ci.yml` | PR on `semantic_views/` | Audit → eval on DEV → PR comment |
| `semantic_view_cd.yml` | Merge to main | Audit gate → eval on DEV → deploy to PROD |
| `agent_ci.yml` | PR on `agents/` | Deploy to DEV → native GPA eval → PR comment |
| `agent_cd.yml` | Merge to main | Native GPA eval on DEV → deploy to PROD |

### Connection Pattern

Python scripts connect via named connection:
```python
import os, snowflake.connector
conn = snowflake.connector.connect(
    connection_name=os.getenv("SNOWFLAKE_CONNECTION_NAME") or "default"
)
```

### Native Agent Evaluation (GPA Framework)
- `CALL EXECUTE_AI_EVALUATION('START', OBJECT_CONSTRUCT('run_name', '...'), '@stage/config.yaml')` — start evaluation
- `CALL EXECUTE_AI_EVALUATION('STATUS', OBJECT_CONSTRUCT('run_name', '...'), '@stage/config.yaml')` — poll status
- `SNOWFLAKE.LOCAL.GET_AI_EVALUATION_DATA(db, schema, agent, 'CORTEX AGENT', run)` — get results
- `SNOWFLAKE.LOCAL.GET_AI_RECORD_TRACE(db, schema, agent, 'CORTEX AGENT', record_id)` — drill into individual records
- `SNOWFLAKE.LOCAL.GET_AI_OBSERVABILITY_LOGS(db, schema, agent, 'CORTEX AGENT')` — errors and warnings
- `snowflake.local.ai_observability_events` — raw trace data
- LLM judges auto-selected by Snowflake (cross-region inference)

### Configuration Files
- `config/environments.yaml` — per-env database, schema, warehouse, SV name, agent name, LLM model config (`llm.model`, `llm.judge_model`)
- `config/agent_evaluation_config.yaml` — reusable YAML config following Snowflake's Agent Evaluation YAML spec
- `config/thresholds.yaml` — graduated accuracy thresholds (DEV 60% → TEST 75% → PROD 85%)
- `config/monitoring.yaml` — alert thresholds, schedules, token cost estimates, notification settings

## GitHub Actions Secrets Required

| Secret | Description |
|--------|-------------|
| `SNOWFLAKE_ACCOUNT` | Snowflake account identifier |
| `SNOWFLAKE_USER` | Service account username |
| `SNOWFLAKE_PASSWORD` | Service account password |
| `SNOWFLAKE_CONNECTION_NAME` | Named connection (optional, defaults to `default`) |

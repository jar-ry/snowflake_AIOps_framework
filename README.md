# Snowflake AI Evaluation Framework

An end-to-end framework for developing, testing, and promoting **Semantic Views** and **Cortex Agents** in Snowflake with CI/CD-driven governance.

Built for data teams who want to **self-serve semantic view development** while maintaining production-grade quality gates.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        DEVELOPMENT WORKFLOW                         │
│                                                                     │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────────┐  │
│  │ Snowsight │    │  CoCo /  │    │   Git    │    │   GitHub     │  │
│  │  (Edit)   │───▶│  IDE     │───▶│ Commit   │───▶│   Actions    │  │
│  └──────────┘    └──────────┘    └──────────┘    └──────┬───────┘  │
│                                                          │          │
│                                                          ▼          │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                    CI PIPELINE (on PR)                        │   │
│  │                                                               │   │
│  │  ┌─────────────────────────────────────────────────────────┐  │   │
│  │  │ LAYER 1: AUDITS (structural quality gate)               │  │   │
│  │  │                                                         │  │   │
│  │  │  Semantic View Audit:                                   │  │   │
│  │  │  ├─ Documentation (descriptions, comments)              │  │   │
│  │  │  ├─ Naming conventions (casing, special chars)          │  │   │
│  │  │  ├─ Metadata completeness (VALUES, types)               │  │   │
│  │  │  ├─ Relationships (coverage, validity)                  │  │   │
│  │  │  ├─ Inconsistencies (conflicting definitions)           │  │   │
│  │  │  └─ Duplicates (redundant descriptions)                 │  │   │
│  │  │                                                         │  │   │
│  │  │  Agent Native Evaluation (EXECUTE_AI_EVALUATION):       │  │   │
│  │  │  ├─ answer_correctness (semantic match)                 │  │   │
│  │  │  ├─ logical_consistency (reasoning coherence)           │  │   │
│  │  │  └─ safety (custom LLM-judged metric)                   │  │   │
│  │  └─────────────────────────────────────────────────────────┘  │   │
│  │                              │                                 │   │
│  │                              ▼                                 │   │
│  │  ┌─────────────────────────────────────────────────────────┐  │   │
│  │  │ LAYER 2: QUESTION BANK EVALUATION (accuracy gate)       │  │   │
│  │  │                                                         │  │   │
│  │  │  Semantic View:                                         │  │   │
│  │  │  ┌────────┐  ┌──────────┐  ┌───────────┐               │  │   │
│  │  │  │  Easy  │  │   Hard   │  │ Ambiguous │               │  │   │
│  │  │  └────────┘  └──────────┘  └───────────┘               │  │   │
│  │  │                                                         │  │   │
│  │  │  Agent (Native GPA via EXECUTE_AI_EVALUATION):             │  │   │
│  │  │  ┌────────────┐  ┌─────────────┐  ┌─────────────┐      │  │   │
│  │  │  │ Answerable │  │Out of Scope │  │ Adversarial │      │  │   │
│  │  │  └────────────┘  └─────────────┘  └─────────────┘      │  │   │
│  │  └─────────────────────────────────────────────────────────┘  │   │
│  │                                                               │   │
│  │  Post combined results to PR comment                          │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                              │                                      │
│                    accuracy >= threshold?                            │
│                         │          │                                 │
│                        YES        NO ──▶ Block merge, iterate       │
│                         │                                           │
│                         ▼                                           │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                    CD PIPELINE (on merge)                     │   │
│  │  Audit gate ──▶ Final eval ──▶ Deploy to PROD ──▶ Log       │   │
│  └──────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                      SNOWFLAKE ENVIRONMENTS                         │
│                                                                     │
│  ┌──────────────┐   ┌──────────────┐                        │
│  │  RETAIL_AI   │   │  RETAIL_AI   │                        │
│  │    _DEV      │   │    _PROD     │                        │
│  │              │   │              │                        │
│  │  ANALYTICS   │   │  ANALYTICS   │                        │
│  │  ├─ CUSTOMERS│   │  ├─ CUSTOMERS│                        │
│  │  ├─ ORDERS   │   │  ├─ ORDERS   │                        │
│  │  ├─ PRODUCTS │   │  ├─ PRODUCTS │                        │
│  │  ├─ ORDER_.. │   │  ├─ ORDER_.. │                        │
│  │  ├─ RETURNS  │   │  ├─ RETURNS  │                        │
│  │  └─ STORES   │   │  └─ STORES   │                        │
│  │              │   │              │                        │
│  │  SEMANTIC    │   │  SEMANTIC    │                        │
│  │  ├─ SV (DDL) │   │  ├─ SV (DDL) │                        │
│  │  ├─ AGENT    │   │  ├─ AGENT    │                        │
│  │  └─ EVAL DS  │   │  └─ EVAL DS  │                        │
│  └──────────────┘   └──────────────┘                        │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  RETAIL_AI_EVAL (shared across envs)                         │   │
│  │  RESULTS.SEMANTIC_VIEW_EVAL_RUNS                             │   │
│  │  RESULTS.SEMANTIC_VIEW_EVAL_DETAILS                          │   │
│  │  RESULTS.AGENT_EVAL_RUNS                                     │   │
│  │  RESULTS.AGENT_EVAL_DETAILS                                  │   │
│  │  OBSERVABILITY views (over ai_observability_events)          │   │
│  │  MONITORING.* (feedback, usage, health, alerts, quality)    │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ROLES: RETAIL_AI_ANALYST ──▶ RETAIL_AI_REVIEWER ──▶ RETAIL_AI_ADMIN│
│                                RETAIL_AI_DEPLOYER ──▶ RETAIL_AI_ADMIN│
└─────────────────────────────────────────────────────────────────────┘
```

---

## Getting Started

### Prerequisites

- Python 3.11+
- A Snowflake account with Cortex AI features enabled
- A named connection in `~/.snowflake/connections.toml` (or env vars `SNOWFLAKE_ACCOUNT`, `SNOWFLAKE_USER`, `SNOWFLAKE_PASSWORD`)

### One-Command Setup

```bash
pip install -r requirements.txt

python setup/bootstrap.py
```

This single command will:

1. Create databases (`RETAIL_AI_DEV`, `RETAIL_AI_PROD`, `RETAIL_AI_EVAL`)
2. Create 6 retail tables and seed mock data (500 customers, 5K orders, 100 products, etc.)
3. Set up RBAC roles (`ANALYST`, `REVIEWER`, `DEPLOYER`, `ADMIN`)
4. Create observability views over `ai_observability_events`
5. Create evaluation datasets (15 ground truth questions)
6. Create monitoring tables, views, tasks (5 daily/weekly), and alerts (7)
7. Deploy the semantic view to DEV
8. Deploy the Cortex Agent to DEV
9. Run a first SV audit evaluation

After bootstrap completes, **one manual step** is required:

> **Set the agent warehouse in Snowsight:**
> Go to **AI & ML → Agents → RETAIL_AGENT → Edit → Tools → Cortex Analyst → Warehouse → `RETAIL_AI_EVAL_WH` → Save**
>
> This is a known Snowflake limitation — the warehouse cannot be set via `CREATE AGENT` SQL.

### Monitoring Dashboard (Streamlit in Snowflake)

The dashboard is deployed as a SiS app during bootstrap. Access it in Snowsight:

**Projects → Streamlit → AI_MONITORING_DASHBOARD**

Or deploy/redeploy manually:

```bash
cd monitoring
snow streamlit deploy --replace
```

The dashboard shows evaluation trends, feedback, token costs, health status, and alerts across 6 tabs.

### Run Evaluations Locally

```bash
# SV best practices audit (no Snowflake connection needed)
python evaluation/audit_semantic_view.py \
  --ddl-file semantic_views/dev/retail_analytics_sv.yaml \
  --output sv_audit.json

# SV question bank evaluation (requires Snowflake connection)
python evaluation/evaluate_semantic_view.py \
  --environment dev \
  --semantic-view RETAIL_AI_DEV.SEMANTIC.RETAIL_ANALYTICS_SV \
  --output sv_eval.json

# Agent native GPA evaluation (requires Snowflake connection)
python evaluation/audit_agent.py \
  --environment dev \
  --agent-name RETAIL_AI_DEV.SEMANTIC.RETAIL_AGENT \
  --metrics answer_correctness,logical_consistency,safety,groundedness,execution_efficiency \
  --output agent_eval.json
```

### Set Up CI/CD

```bash
# Push to GitHub
git init && git add -A && git commit -m "Initial commit"
gh repo create <repo-name> --private --source=. --push

# Add secrets (Settings → Secrets → Actions)
# SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER, SNOWFLAKE_PASSWORD
```

Then:
- **Open a PR** touching `semantic_views/` or `agents/` → CI deploys to DEV, evaluates, posts results as PR comment
- **Merge to main** → CD evaluates on DEV, then promotes to PROD if quality gates pass

### Bootstrap Options

```bash
python setup/bootstrap.py                # Full setup
python setup/bootstrap.py --skip-sql     # Skip SQL (if already run)
python setup/bootstrap.py --skip-deploy  # Skip SV/agent deployment
python setup/bootstrap.py --skip-eval    # Skip first evaluation
```

---

## Directory Structure

```
ai_evaluation_framework/
├── setup/                              # Snowflake environment setup
│   ├── bootstrap.py                   # One-command full setup script
│   ├── deploy_dev.py                  # Deploy SV + agent to DEV only
│   ├── 01_create_databases.sql        # DEV/PROD databases + eval tables
│   ├── 02_create_tables.sql           # Retail schema (customers, orders, etc.)
│   ├── 03_seed_data.sql               # 500 customers, 5000 orders, 100 products
│   ├── 04_rbac_setup.sql              # Analyst/Reviewer/Deployer/Admin roles
│   ├── 05_observability_setup.sql     # Views over ai_observability_events
│   ├── 06_eval_dataset_setup.sql      # Native eval datasets (OBJECT ground truth)
│   ├── 07_monitoring_tables.sql       # Feedback, usage, health, alert tables
│   ├── 08_monitoring_tasks.sql        # Scheduled Tasks (daily + weekly)
│   ├── 09_monitoring_views.sql        # Trend views for Snowsight dashboards
│   ├── 10_monitoring_alerts.sql       # Snowflake Alerts (7 alert types)
│   └── 11_interaction_quality_engine.sql # Rules-based interaction quality detection
├── semantic_views/                     # Semantic View YAML by environment
│   ├── dev/retail_analytics_sv.yaml
│   └── prod/retail_analytics_sv.yaml
├── agents/                             # Cortex Agent DDL by environment
│   ├── dev/retail_agent.sql
│   └── prod/retail_agent.sql
├── question_banks/                     # Test question banks
│   ├── semantic_view/
│   │   ├── easy_questions.yaml         # 10 simple queries + ground truth SQL
│   │   ├── hard_questions.yaml         # 10 complex queries + ground truth SQL
│   │   └── ambiguous_questions.yaml    # 10 ambiguous questions (LLM-judged)
│   └── agent/
│       ├── answerable_questions.yaml   # 15 questions (10 should answer, 5 should not)
│       ├── out_of_scope.yaml           # 10 out-of-scope questions
│       └── adversarial_questions.yaml  # 10 adversarial/safety tests
├── evaluation/                         # Evaluation engine
│   ├── audit_semantic_view.py          # Best practices audit (naming, docs, metadata)
│   ├── audit_agent.py                  # Native EXECUTE_AI_EVALUATION (GPA framework)
│   ├── evaluate_semantic_view.py       # Batch SV evaluation (SQL comparison + LLM judge)
│   ├── llm_judge.py                   # LLM-as-a-Judge for SV evaluation
│   └── utils.py                       # Shared helpers (connection, SQL exec, etc.)
├── monitoring/                         # Health check & monitoring
│   ├── dashboard.py                   # Streamlit in Snowflake (SiS) dashboard
│   ├── snowflake.yml                  # SiS deployment config
│   └── health_check.py               # PROD health checks (7 checks)
├── .github/workflows/                  # CI/CD pipelines
│   ├── semantic_view_ci.yml            # On PR: audit → evaluate → comment
│   ├── semantic_view_cd.yml            # On merge: audit gate → eval → promote
│   ├── agent_ci.yml                    # On PR: native GPA eval → comment
│   └── agent_cd.yml                   # On merge: native GPA eval gate → promote
├── config/
│   ├── environments.yaml              # Environment config + LLM model settings
│   ├── thresholds.yaml                # Accuracy thresholds per environment
│   ├── agent_evaluation_config.yaml   # Reusable GPA eval YAML config (Snowflake spec)
│   └── monitoring.yaml                # Alert thresholds & schedule config
├── requirements.txt                   # Python dependencies
├── AGENT.md                           # CoCo agent instructions
└── README.md                          # This file
```

---

## Evaluation Pipeline (Two Layers)

The evaluation pipeline runs two complementary layers for both semantic views and agents:

### Layer 1: Audits (Structural Quality)

**Semantic View Best Practices Audit** (`audit_semantic_view.py`):

Inspired by CoCo's semantic view audit skill, checks for:

| Check | Description | Severity |
|-------|-------------|----------|
| Documentation | All tables/columns have descriptions | WARNING |
| Naming | No special characters, consistent casing | WARNING/INFO |
| Metadata | VALUES on categorical columns, data types | WARNING |
| Relationships | Sufficient coverage for table count | ERROR/WARNING |
| Inconsistencies | Conflicting metric/filter definitions | CRITICAL/HIGH |
| Duplicates | Redundant descriptions across columns | MEDIUM |

Exit code: 0 (pass, no CRITICAL/ERROR findings) or 1 (fail).

**Agent Native Evaluation (GPA Framework)** (`audit_agent.py`):

Uses Snowflake's `EXECUTE_AI_EVALUATION` with the GPA (Goal-Plan-Action) framework:

| Metric | Type | GPA Alignment | Description |
|--------|------|---------------|-------------|
| `answer_correctness` | Built-in | Goal-Action | Semantic match against ground truth |
| `logical_consistency` | Built-in | GPA | Internal reasoning coherence (reference-free) |
| `safety` | Custom LLM-judged | — | Scope compliance, PII protection, prompt injection resistance |
| `groundedness` | Custom LLM-judged | Goal-Action | Claims supported by tool outputs and retrieved data |
| `execution_efficiency` | Custom LLM-judged | Plan-Action | Optimal tool selection and execution path |

Results are viewable in Snowsight's AI Observability dashboard.
LLM judges are auto-selected by Snowflake.

### Layer 2: Question Bank Evaluation (Accuracy)

**Semantic View** (`evaluate_semantic_view.py`):

| Category | Questions | Evaluation Method | Threshold (PROD) |
|----------|-----------|-------------------|-------------------|
| **Easy** | 10 | SQL result comparison + LLM judge | 95% |
| **Hard** | 10 | SQL result comparison + LLM judge | 75% |
| **Ambiguous** | 10 | LLM-as-a-Judge only | 60% |

**Agent** (native GPA evaluation via `audit_agent.py`):

| Metric | GPA Alignment | Description |
|--------|---------------|-------------|
| **Answer Correctness** | Goal-Action | Does the answer match ground truth? |
| **Logical Consistency** | GPA | Are planning, tool calls, and reasoning coherent? |
| **Safety** | Custom | Does the agent handle boundaries correctly? |
| **Groundedness** | Goal-Action | Are claims supported by retrieved data? |
| **Execution Efficiency** | Plan-Action | Was the tool selection and execution optimal? |

| Category | Questions | Focus |
|----------|-----------|-------|
| **Answerable** | 15 | Data queries + out-of-scope detection |
| **Out of Scope** | 10 | Boundary testing (wrong domain, destructive, sensitive) |
| **Adversarial** | 10 | Prompt injection, SQL injection, data exfiltration |

---

## CI/CD Pipeline Flow

### Semantic View (PR → Merge → PROD)

```
PR Opened
  │
  ├── Job 1: Best Practices Audit
  │   └── audit_semantic_view.py --ddl-file (structural checks)
  │
  └── Job 2: Question Bank Evaluation
      ├── Deploy SV to DEV
      ├── evaluate_semantic_view.py --environment dev
      └── Post combined results as PR comment
           │
   Merge to main
           │
           ├── audit_semantic_view.py (gate: fail = block deploy)
           ├── evaluate_semantic_view.py (gate: accuracy >= threshold)
           └── Deploy to PROD
```

### Agent (PR → Merge → PROD)

```
PR Opened
  │
  └── Job 1: Native Snowflake GPA Evaluation
      ├── Deploy agent to TEST
      └── audit_agent.py (EXECUTE_AI_EVALUATION with GPA metrics)
           │
      Post results as PR comment
           │
   Merge to main
           │
           ├── audit_agent.py (native GPA eval gate)
           └── Deploy to PROD
```

---

## Governance Model

### RBAC Roles

| Role | DEV | PROD | EVAL |
|------|-----|------|------|
| `RETAIL_AI_ANALYST` | Full (create SV) | Read | Read results |
| `RETAIL_AI_REVIEWER` | Inherits Analyst | Read | Read results |
| `RETAIL_AI_DEPLOYER` | Deploy SV/Agent | Deploy SV/Agent | Write results |
| `RETAIL_AI_ADMIN` | Full | Full | Full | Full |

### Promotion Flow

```
Analyst edits SV in DEV (via Snowsight or CoCo)
        │
        ▼
Commits DDL to Git (dev branch)
        │
        ▼
Opens PR to main ──▶ GitHub Actions triggers CI:
        │               1. Run SV best practices audit
        │               2. Deploy SV to TEST
        │               3. Run question bank evaluation
        │               4. Post combined audit + eval results to PR
        │
        ▼
Reviewer checks results:
        │
   ┌────┴────┐
   │ Passed  │   Failed
   │ (>= 85%)│   (iterate)
   └────┬────┘
        │
        ▼
Merge to main ──▶ GitHub Actions triggers CD:
                    1. Run audit gate (block on CRITICAL/ERROR)
                    2. Final evaluation on TEST
                    3. Deploy to PROD (if both pass)
                    4. Log results to RETAIL_AI_EVAL
```

---

## Self-Service Development Options

### Option 1: CoCo with Semantic View Skill (Recommended for creation)

Use Cortex Code's built-in semantic view skill for AI-assisted creation, optimization, and VQR generation:

```
CoCo> Create a new semantic view for the retail analytics tables in RETAIL_AI_DEV
```

The skill provides:
- AI-guided semantic view creation with proper structure
- VQR suggestion generation from query history
- Audit and debug modes for optimization
- Filter and metric suggestions

### Option 2: Snowsight (Recommended for validation)

Use Snowsight's native semantic view editor for:
- Interactive editing with built-in DDL validation
- Chat-based testing with Cortex Analyst
- AI Observability dashboards for monitoring evaluation results and agent traces

### Option 3: IDE + Git (Recommended for CI/CD)

Edit DDL files directly in your IDE, commit to Git, and let CI/CD handle evaluation:
- Full version control and review process
- Automated quality gates prevent regressions
- Audit trail of all changes

---

## Configuring Thresholds

Edit `config/thresholds.yaml` to adjust quality gates per environment:

```yaml
semantic_view:
  prod:
    accuracy_threshold: 85    # Overall accuracy gate
    easy_min_accuracy: 95     # Easy questions must be nearly perfect
    hard_min_accuracy: 75     # Hard questions more lenient
    ambiguous_min_accuracy: 60 # Ambiguous evaluated by LLM judge

agent:
  prod:
    accuracy_threshold: 85
    adversarial_min_accuracy: 98  # Near-perfect on safety tests
```

Thresholds increase from DEV → TEST → PROD to support iterative improvement.

---

## Extending the Framework

### Adding Questions

Add YAML entries to `question_banks/semantic_view/` or `question_banks/agent/`:

```yaml
- id: easy_011
  question: "What is the average shipping cost?"
  expected_sql: |
    SELECT AVG(SHIPPING_COST) AS avg_shipping_cost FROM ORDERS
  category: easy
```

### Adding to the Native Eval Dataset

Add rows to `setup/06_eval_dataset_setup.sql` (or use `audit_agent.py` which auto-populates from question banks):

```sql
INSERT INTO RETAIL_AI_DEV.SEMANTIC.RETAIL_AGENT_EVAL_DATASET (input_query, ground_truth)
VALUES ('My new question?', PARSE_JSON('{\"ground_truth_output\": \"Expected answer\"}'));
```

### Adding New Semantic Views

1. Create DDL files in `semantic_views/{dev,test,prod}/`
2. Add corresponding question banks
3. Update `config/environments.yaml`
4. CI/CD will automatically pick up changes

### Adding New Agents

1. Create agent SQL in `agents/{dev,test,prod}/`
2. Add question banks in `question_banks/agent/`
3. Update `config/environments.yaml`

---

## Monitoring & Observability

The framework includes a full monitoring layer for long-term tracking of agent health, accuracy trends, user feedback, and cost.

### Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                      MONITORING LAYER                             │
│                                                                  │
│  SNOWFLAKE TASKS (automated)                                    │
│  ┌──────────────────────────┐                                    │
│  │ Daily 02:00 Usage agg   │                                    │
│  │ Daily 02:15 Feedback    │                                    │
│  │ Daily 02:30 Interaction │                                    │
│  │      quality scan       │                                    │
│  │ Daily 06:00 Health check│                                    │
│  │ Weekly Sun  SV smoke    │                                    │
│  │ Weekly Sun  Agent smoke │                                    │
│  └──────────────────────────┘                                    │
│                │                                                 │
│                ▼                                                 │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │ MONITORING TABLES (RETAIL_AI_EVAL.MONITORING)                │ │
│  │  USER_FEEDBACK        │ USAGE_METRICS       │ ALERT_HISTORY  │ │
│  │  SCHEDULED_EVAL_RUNS  │ HEALTH_CHECK_RESULTS│ FEEDBACK_DAILY │ │
│  │  INTERACTION_QUALITY_DAILY                                    │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                │                                                 │
│                ▼                                                 │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │ TREND VIEWS (for Snowsight dashboards)                       │ │
│  │  V_EVAL_ACCURACY_TREND    │ V_FEEDBACK_TREND                 │ │
│  │  V_TOKEN_COST_TREND       │ V_AGENT_USAGE_PATTERNS           │ │
│  │  V_HEALTH_DASHBOARD       │ V_ACTIVE_ALERTS                  │ │
│  │  V_WEEKLY_EXECUTIVE_SUMMARY │ V_INTERACTION_QUALITY_DASHBOARD │ │
│  │  V_INTERACTION_QUALITY_FLAGS │ V_REQUEST_QUALITY_SIGNALS      │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                │                                                 │
│                ▼                                                 │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │ SNOWFLAKE ALERTS (fire on threshold breach)                  │ │
│  │  Negative feedback spike (>25% negative)                     │ │
│  │  Accuracy regression (>10% drop)                             │ │
│  │  Latency degradation (P95 > 30s)                             │ │
│  │  Cost anomaly (>2x 7-day average)                            │ │
│  │  Error spike (>10% error rate)                               │ │
│  │  Health check failure (any UNHEALTHY)                        │ │
│  │  Interaction quality (>20% flagged or CRITICAL)              │ │
│  └──────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────┘
```

### Automated Schedules

| Schedule | What | Where |
|----------|------|-------|
| Daily 02:00 UTC | Token usage & cost aggregation from event table | Snowflake Task |
| Daily 02:15 UTC | Feedback sentiment analysis (CORTEX.SENTIMENT) + daily rollup | Snowflake Task |
| Daily 02:30 UTC | Interaction quality scan (tool looping, abandonment, slow, etc.) | Snowflake Task |
| Daily 06:00 UTC | Health checks (SV exists, agent responds, error rate, latency) | Snowflake Task |
| Sunday 04:00 UTC | PROD semantic view smoke test | Snowflake Task |
| Sunday 05:00 UTC | PROD agent smoke test | Snowflake Task |

### Alerts

| Alert | Trigger | Severity |
|-------|---------|----------|
| **Negative Feedback Spike** | >25% negative feedback in a day (min 5 responses) | WARNING / CRITICAL (>50%) |
| **Accuracy Regression** | >10% accuracy drop between eval runs | WARNING / CRITICAL (>20%) |
| **Latency Degradation** | P95 latency > 30s | WARNING / CRITICAL (>60s) |
| **Cost Anomaly** | Daily cost > 2x 7-day average | WARNING / CRITICAL (>5x) |
| **Error Spike** | Error rate > 10% (min 10 requests) | WARNING / CRITICAL (>25%) |
| **Health Failure** | Any health check returns UNHEALTHY | CRITICAL |
| **Interaction Quality** | >20% flagged requests or any CRITICAL quality flags | WARNING / CRITICAL |

To enable email notifications, configure the notification integration in `setup/10_monitoring_alerts.sql`.

### Snowsight Dashboards

All trend views are in `RETAIL_AI_EVAL.MONITORING` and can be used directly in Snowsight dashboards:

```sql
-- Eval accuracy over time
SELECT * FROM RETAIL_AI_EVAL.MONITORING.V_EVAL_ACCURACY_TREND
WHERE environment = 'prod' ORDER BY eval_date;

-- Feedback sentiment trend
SELECT * FROM RETAIL_AI_EVAL.MONITORING.V_FEEDBACK_TREND
WHERE environment = 'prod' ORDER BY summary_date;

-- Token costs and usage
SELECT * FROM RETAIL_AI_EVAL.MONITORING.V_TOKEN_COST_TREND
WHERE environment = 'prod' ORDER BY metric_date;

-- Current health status
SELECT * FROM RETAIL_AI_EVAL.MONITORING.V_HEALTH_DASHBOARD;

-- Active alerts
SELECT * FROM RETAIL_AI_EVAL.MONITORING.V_ACTIVE_ALERTS;

-- Weekly executive summary
SELECT * FROM RETAIL_AI_EVAL.MONITORING.V_WEEKLY_EXECUTIVE_SUMMARY
WHERE environment = 'prod' ORDER BY week_start;
```

### User Feedback Collection

Analysts can submit feedback directly:

```sql
INSERT INTO RETAIL_AI_EVAL.MONITORING.USER_FEEDBACK
    (environment, source, agent_or_sv_name, user_query, agent_response,
     feedback_rating, feedback_text, feedback_category)
VALUES
    ('prod', 'agent', 'RETAIL_AI_PROD.SEMANTIC.RETAIL_AGENT',
     'What is our revenue by category?', '<response text>',
     2, 'Returned wrong categories', 'incorrect_answer');
```

Sentiment is auto-scored daily by `CORTEX.SENTIMENT`. Negative spikes trigger alerts.

### Health Check Script

Run manually or via CI:

```bash
python monitoring/health_check.py --environment prod --output health.json
```

Checks: SV exists, agent exists, analyst responds, agent responds, data freshness, error rate, active alerts.

### Interaction Quality Rules Engine

The framework includes a **rules-based quality engine** (`setup/11_interaction_quality_engine.sql`) that scans `snowflake.local.ai_observability_events` for problematic agent interactions — no LLM required:

| Flag | Detection Rule | Severity |
|------|---------------|----------|
| **Tool Looping** | Same tool called 3+ times in one request | WARNING (CRITICAL if + high token burn) |
| **Excessive Steps** | 4+ planning steps to resolve a query | WARNING |
| **Slow Request** | Total duration > 60 seconds | WARNING |
| **High Token Burn** | > 100k tokens in a single request | WARNING |
| **Planning Error** | Any step with `planning_status = 'ERROR'` | CRITICAL |
| **Abandoned Conversation** | 3+ turns in thread, no follow-up in 30 min | WARNING |
| **Rapid Rephrasing** | 3+ turns in under 5 minutes (user struggling) | WARNING (CRITICAL if + abandoned) |
| **Single-Turn Drop-off** | Thread with exactly 1 turn | INFO |

Runs daily at 02:30 UTC. Alerts fire if >20% of requests are flagged or any CRITICAL flags exist.

```sql
-- See all currently flagged interactions
SELECT * FROM RETAIL_AI_EVAL.MONITORING.V_INTERACTION_QUALITY_FLAGS
WHERE severity IN ('CRITICAL', 'WARNING')
ORDER BY event_time DESC;

-- Daily trend of interaction quality
SELECT * FROM RETAIL_AI_EVAL.MONITORING.V_INTERACTION_QUALITY_DASHBOARD
WHERE environment = 'RETAIL_AI_PROD'
ORDER BY summary_date;

-- Drill into a specific looping request
SELECT * FROM RETAIL_AI_EVAL.MONITORING.V_REQUEST_QUALITY_SIGNALS
WHERE flag_tool_looping = TRUE
ORDER BY max_same_tool_calls DESC;
```

### Streamlit Monitoring Dashboard

A unified Streamlit dashboard for all monitoring and alerting:

```bash
streamlit run monitoring/dashboard.py
```

**Tabs:**

| Tab | Data Source | What |
|-----|------------|------|
| **Overview** | `V_WEEKLY_EXECUTIVE_SUMMARY`, `V_HEALTH_DASHBOARD` | KPIs (requests, success rate, cost, latency), weekly trends, health status |
| **Evaluations** | `V_EVAL_ACCURACY_TREND` | Accuracy trends over time, eval history table |
| **Interaction Quality** | `V_INTERACTION_QUALITY_DASHBOARD`, `V_INTERACTION_QUALITY_FLAGS` | Flagged % trend, request/thread flag breakdown, flagged interaction details |
| **Feedback** | `V_FEEDBACK_TREND` | Avg rating, negative %, sentiment distribution stacked chart |
| **Token Costs** | `V_TOKEN_COST_TREND` | Cost by service, token volume, latency avg vs P95 |
| **Alerts** | `V_ACTIVE_ALERTS`, `ALERT_HISTORY` | Active alert cards with severity, full alert history table |

**Sidebar filters:** Environment (All/PROD/TEST/DEV), days back (7-90).

Configure Snowflake connection in `.streamlit/secrets.toml`:
```toml
[connections.snowflake]
connection_name = "default"
```

### Configuring Monitoring

Edit `config/monitoring.yaml` to adjust alert thresholds, schedules, and notification settings.

---

## GitHub Actions Secrets Required

| Secret | Description |
|--------|-------------|
| `SNOWFLAKE_ACCOUNT` | Snowflake account identifier |
| `SNOWFLAKE_USER` | Service account username |
| `SNOWFLAKE_PASSWORD` | Service account password |
| `SNOWFLAKE_CONNECTION_NAME` | Named connection (optional) |

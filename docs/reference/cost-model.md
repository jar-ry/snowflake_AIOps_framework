# Cost model

> Status: Stable | Last reviewed: 2026-05-26 | Audience: Engineers, solution architects, customers

**Purpose.** Explain how the framework's evaluation cost is computed, in Snowflake AI Credits, so teams can estimate and budget spend before adopting it.

## Canonical unit: Snowflake AI Credits

All cost in this framework is denominated in **Snowflake AI Credits**, not US dollars. The monitoring schema stores cost in the `estimated_credits` column ([setup/07_monitoring_tables.sql](../../setup/07_monitoring_tables.sql)), computed from real per-model token counts using the rate table in the `pricing:` block of [config/environments.yaml](../../config/environments.yaml).

Dollar cost depends on your Snowflake contract's credit price, which varies by edition, region, and commitment. This document therefore quotes credits. A single, clearly-flagged USD illustration is included at the end.

> Note: some demo materials loosely quote figures like "$5 per run" and "$1 per credit". Those are illustrative only and are not the canonical model. They are flagged for correction in the demo docs.

## Two loops, two cost profiles

The framework has two evaluation loops with very different cost characteristics:

| Loop | What it is | Cost driver | Approximate cost |
| --- | --- | --- | --- |
| Loop 1 (CI eval) | Agent run against a question bank, scored by an LLM judge | LLM tokens (agent + judge) | The subject of this document |
| Loop 2 (runtime monitoring) | Deterministic SQL rules over `ai_observability_events` | Warehouse compute only | No LLM tokens; cost is limited to short daily task runs on the configured warehouse |

Loop 2 is pure SQL aggregation on an XSMALL warehouse running short daily tasks. Its cost is negligible and not modeled here. The rest of this document is about Loop 1.

## How Loop 1 cost is computed

For each evaluation run, the framework:

1. Invokes the agent once per question in the bank (the agent plans, calls tools, generates SQL, and synthesizes an answer).
2. Invokes an LLM judge once per metric per question to score the answer.

So a single question with `M` metrics costs: one agent invocation plus `M` judge invocations.

### Token assumptions (illustrative)

These are planning estimates. Actual token counts are measured per request and written to `estimated_credits` in `USAGE_METRICS`. Always prefer measured actuals over these estimates.

| Component | Input tokens | Output tokens |
| --- | --- | --- |
| Agent invocation (per question) | ~6,000 | ~2,000 |
| Judge invocation (per metric per question) | ~1,200 | ~300 |

### Per-model rates

Credits are computed from the model's input and output rates (credits per million tokens) in [config/environments.yaml](../../config/environments.yaml). The default evaluation and judge model is `claude-opus-4-7`:

| Rate | Credits per million tokens |
| --- | --- |
| Input | 3.25 |
| Output | 16.26 |

### Per-question credit estimate

Using the assumptions above with `claude-opus-4-7` and the default five metrics (`answer_correctness`, `logical_consistency`, `safety`, `groundedness`, `execution_efficiency`):

- Agent: `6000/1e6 x 3.25 + 2000/1e6 x 16.26` = approximately `0.052` credits
- Judges (5): `5 x (1200/1e6 x 3.25 + 300/1e6 x 16.26)` = approximately `0.044` credits
- **Per question: approximately `0.096` credits**

## Lifecycle cost formula

An evaluation runs on every CI trigger that touches a watched path (`agents/`, `semantic_views/`, `question_banks/`, `evaluation/`, `config/thresholds.yaml`). Across a feature's life:

```text
E = number of promotion environments (e.g. DEV + STAGING + PROD = 3)

total_eval_runs = feature_branch_commits_touching_watched_paths
                + E   (one eval per promotion gate)

cost_credits = total_eval_runs
             x num_agents_changed
             x bank_size
             x per_question_credits
```

`per_question_credits` is approximately `0.096` for the default model and five metrics (see above). `num_agents_changed` is usually 1 (a PR typically changes one agent); multi-agent PRs multiply accordingly. `E` depends on how many environments your pipeline promotes through — a minimal setup has 2 (DEV + PROD), while enterprise setups may have 3 or more (DEV + STAGING + PROD).

## Worked examples

All figures are estimates in AI Credits, assuming `claude-opus-4-7`, five metrics, `per_question_credits` approximately `0.096`, one agent changed per PR, and `E = 2` environments (DEV + PROD). Scale `E` for your pipeline.

### Small team

- 1 agent, 20-question bank, ~3 commits per PR, 5 PRs per week
- Per run: `20 x 0.096` = approximately `1.9` credits
- Per PR: `(3 + E) runs x 1.9` = `(3 + 2) x 1.9` = approximately `9.6` credits
- **Per week: `5 x 9.6` = approximately 48 credits**

### Medium team

- 5 agents (1 changed per PR), 35-question bank, ~4 commits per PR, 50 PRs per week
- Per run: `35 x 0.096` = approximately `3.4` credits
- Per PR: `(4 + E) runs x 3.4` = `(4 + 2) x 3.4` = approximately `20` credits
- **Per week: `50 x 20` = approximately 1,000 credits**

### Large team

- 20 agents (1 changed per PR), 50-question bank, ~5 commits per PR, 200 PRs per week
- Per run: `50 x 0.096` = approximately `4.8` credits
- Per PR: `(5 + E) runs x 4.8` = `(5 + 2) x 4.8` = approximately `34` credits
- **Per week: `200 x 34` = approximately 6,720 credits**

## Levers to reduce cost

- **Pre-flight smoke check.** Run a 3-question smoke set before the full bank. A broken agent aborts at roughly `0.3` credits instead of running the full bank. This is the single biggest saver on iterative feature branches.
- **Tiered question banks.** Run a small subset on feature-branch commits (advisory) and the full bank only on merge to main. Cuts feature-branch cost by the ratio of the subsets.
- **Metric pruning.** Each metric is a judge call per question. Dropping a metric you do not need (for example `groundedness`) removes one judge call per question, reducing judge cost by roughly `1/M`.
- **Cheaper judge model.** The judge model is configurable. A less expensive model (for example a Haiku-class model) lowers judge cost substantially, at some loss of judging nuance.

## Architecture note: why per-record, not batched

The framework scores each (question, metric) pair as its own judge call. A batched alternative — one judge call scoring all answers for a metric — would cut judge tokens by roughly 30 percent. It was rejected because it loses per-question explainability (the `EVAL_CALLS` rationale per record), breaks the Snowsight Evaluations UI integration, and abandons the native `EXECUTE_AI_EVALUATION` API. The modest savings did not justify those losses.

## Measuring actuals

Estimates are for planning. To see real cost, query the monitoring schema, which aggregates `estimated_credits` from measured token counts:

```sql
SELECT metric_date, service_type, agent_or_sv_name, total_tokens, estimated_credits
FROM RETAIL_AI_EVAL.MONITORING.USAGE_METRICS
ORDER BY metric_date DESC;
```

The dashboard's Token Costs tab visualizes the same data over time.

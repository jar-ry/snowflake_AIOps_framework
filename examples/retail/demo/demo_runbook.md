# Demo Runbook: AIOps Agent Enforcement Framework

## Demo Objective
Prove feasibility of the Snowflake AIOps Agent Enforcement Framework to potential clients. Show that AI input governance is a real, working product — not a concept.

## Audience
- Technical decision-makers at Snowflake enterprise accounts
- Data platform leads evaluating agent observability options
- Solution architects considering AI governance frameworks

## Duration: 10-12 minutes (excludes Q&A)

---

## Pre-Demo Checklist (Day Before)

- [ ] Log into Snowsight, verify RETAIL_AI_DEV databases visible
- [ ] Resume warehouse: `ALTER WAREHOUSE RETAIL_AI_EVAL_WH RESUME;`
- [ ] Open agent in Snowsight chat, ask "How many customers?" — confirm it returns 500
- [ ] Open Streamlit dashboard, verify at least 3 tabs render with data
- [ ] Have architecture.html open locally as backup
- [ ] Have terminal ready with repo cloned (for live audit_semantic_view.py if needed)
- [ ] Prepare backup screenshots/video of each step in case of live failures

---

## The Story Arc

```
PROBLEM (1 min)
   |
   v
SOLUTION OVERVIEW (1 min)
   |
   v
LIVE: Agent working (2 min)
   |
   v
LIVE: Evaluation results + "caught our own bugs" moment (2 min)
   |
   v
LIVE: Monitoring dashboard (3 min)
   |
   v
DIFFERENTIATOR + ROADMAP (1 min)
   |
   v
Q&A
```

---

## Section 1: The Problem (1 min)

**Slide/verbal:**

"57% of enterprises now have AI agents in production. Only 33% are satisfied with their observability.

90+ companies sell agent monitoring — Langfuse, LangSmith, Arize, Datadog. They all do the same thing: monitor what the agent said after it said it.

Nobody asks: 'Is the semantic model the agent reads from actually any good? Are the joins correct? Are the metric definitions consistent? Is the documentation sufficient for the LLM to generate correct SQL?'

That's input governance. That's what we built."

---

## Section 2: Solution Overview (1 min)

**Show:** architecture.html or AGENT.md architecture diagram

**Key points (30 sec each):**
1. Pillar 1: Structural audit of semantic views (15+ rules, zero LLM cost)
2. Pillar 2: Accuracy evaluation via question banks + native EXECUTE_AI_EVALUATION
3. Pillar 3: Interaction quality rules engine (deterministic, zero LLM cost)
4. All enforced through CI/CD — merge is blocked if quality gates fail

---

## Section 3: LIVE — Agent in Action (2 min)

**See:** demo/snowsight_walkthrough.md Step 1

Ask 3-4 questions:
1. "How many customers?" (basic — proves data connection)
2. "Revenue by segment" (complex — shows chart generation)
3. "What is the meaning of life?" (safety — shows boundary enforcement)
4. Optional: "DROP TABLE CUSTOMERS" (destructive — shows refusal)

**Transition:** "That works well. But how do we KNOW it works well? We can't just demo 3 questions and declare victory. We need systematic evaluation."

---

## Section 4: LIVE — Evaluation Results (2 min)

**See:** demo/snowsight_walkthrough.md Step 3

Run the eval query. Walk through:
- 31/35 perfect scores
- 4 failures — drill into each one
- THE KEY MOMENT: "2 of these failures are bugs in OUR ground truth, not the agent. The framework caught our own mistakes."

**Transition:** "So the framework doesn't just evaluate the agent — it evaluates the quality of our evaluation itself. That's meta-governance."

---

## Section 5: LIVE — Monitoring Dashboard (3 min)

**See:** demo/snowsight_walkthrough.md Step 4

Speed-walk the 6 tabs:
- Overview (30 sec): executive metrics
- Evaluations (30 sec): accuracy trend with improvement story
- Interaction Quality (45 sec): THE DIFFERENTIATOR — zero LLM cost rules
- Feedback (15 sec): user sentiment
- Token Costs (15 sec): cost governance
- Alerts (30 sec): 3 active alerts, 7 alert types

**Transition:** "All of this runs on Snowflake Tasks — daily automation, no external orchestrator. The interaction quality engine costs zero in LLM tokens because it's pure SQL over native observability events."

---

## Section 6: Differentiator + Roadmap (1 min)

**Verbal (punchy):**

"What you just saw:
- Input governance: nobody else audits the objects agents depend on
- Zero-cost rules engine: 7 deterministic quality rules, no LLM
- CI/CD enforcement: merge blocked if below threshold
- Framework caught its own bugs: meta-validation
- One command setup: bootstrap.py, 5 minutes to production

What's next:
- Suggestion engine: failing questions auto-generate SV patches
- Auto-remediation: CI opens fix PRs
- Multi-agent governance: chain-of-agents support

This is open source. Bring your own semantic view, your own question bank. The framework is domain-agnostic."

---

## Anticipated Questions + Answers

| Question | Answer |
|----------|--------|
| "Is this just a wrapper around EXECUTE_AI_EVALUATION?" | Pillar 2 uses it, yes. Pillar 1 (structural audit) and Pillar 3 (interaction quality) are entirely custom — no Snowflake-native equivalent. |
| "What does this cost?" | Structural audit: free. Rules engine: free. Eval runs: ~9 AI Credits per 35-question batch (~0.26 credits/question, cache-aware, 5 metrics). Loop 2 runtime monitoring: no LLM tokens — just short daily XSMALL tasks. Dollar cost depends on your contract's credit price; see `docs/reference/cost-model.md`. |
| "How long to set up for my data?" | bootstrap.py does everything in 5 minutes. You bring your SV YAML + question bank. Framework is domain-agnostic. |
| "The 40% SV accuracy — doesn't that mean it doesn't work?" | That's SQL-path-matching, not answer accuracy. The agent gives correct answers 94.3% of the time via different (equally valid) SQL paths. |
| "Can I customize the audit rules?" | Yes — they're Python functions in audit_semantic_view.py. Add any rule, set any severity. |
| "Does this work with agents that don't use semantic views?" | The structural audit is SV-specific. The agent evaluation and interaction quality engine work with any Cortex Agent regardless of tools. |
| "What about multi-agent?" | On the roadmap. The interaction quality engine already works per-agent via the observability events filter. |

---

## If Things Go Wrong

| Failure | Recovery |
|---------|----------|
| Agent unresponsive | "Let me show you the evaluation results instead — this proves it was working earlier today." Run eval query. |
| Dashboard crash | Run `SELECT * FROM RETAIL_AI_EVAL.MONITORING.V_WEEKLY_EXECUTIVE_SUMMARY` in worksheet. Explain dashboard is SiS-deployed. |
| Dashboard empty | Change sidebar filter to "All" environments. If still empty: "The monitoring tasks aggregate daily — let me show the raw observability data instead." |
| Eval query fails | Show evaluation_report.md on screen. "Here are the documented results from our validation run." |
| Total Snowflake outage | Present architecture.html + evaluation_report.md + market_positioning.md locally. "Let me walk you through what we validated earlier this week." |

---

## Post-Demo Actions
- Share github.com/jar-ry/snowflake_AIOps_framework with interested parties
- Offer to run bootstrap.py on their account (5-min setup)
- Follow up with evaluation_report.md as the written proof
- Schedule deep-dive session for CI/CD workflow + customization discussion

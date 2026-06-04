# Market Positioning: Snowflake AIOps Agent Enforcement Framework

## The Problem

Organizations are deploying AI agents at scale but lack governance over the objects those agents depend on.

| Stat | Source |
|------|--------|
| 57% of enterprises have AI agents in production | Gartner 2025 |
| Only 33% are satisfied with their observability tooling | Deepak Gupta AI Agent Report 2025 |
| 90+ companies compete in agent observability/eval/governance | Market scan (see competitors below) |
| Average cost of a hallucinated agent answer in enterprise: $15K–$250K | Estimated from support escalation + rework costs |

The gap: Everyone monitors agent **output** after the fact. Nobody governs the **input objects** (semantic models, knowledge bases, tool configs) before they reach production.

---

## The Market Landscape

### Category Leaders (Output Monitoring)

| Company | Focus | Weakness |
|---------|-------|----------|
| Langfuse | Open-source LLM observability, tracing | No input governance, no Snowflake-native |
| LangSmith | LangChain-native eval + monitoring | Tied to LangChain ecosystem |
| Arize / Phoenix | ML observability + LLM traces | General-purpose, not agent-specific |
| Galileo | Hallucination detection + eval | No CI/CD integration |
| Braintrust | Eval framework + logging | Developer tool, no ops governance |
| AgentOps | Agent-specific monitoring | Early stage, no structural audit |
| Datadog LLM | APM-style LLM monitoring | Expensive, no semantic model awareness |

### Snowflake Native (Built-in)

| Feature | What it does | Our relationship to it |
|---------|-------------|----------------------|
| EXECUTE_AI_EVALUATION | LLM judge evaluation (GPA framework) | We wrap it with CI/CD gates + question banks |
| ai_observability_events | Raw span/trace telemetry | We build quality rules on top of it |
| Cortex Analyst | Text-to-SQL via semantic views | The object we audit and govern |
| Cortex Agents | Multi-tool orchestration agents | The runtime we evaluate |

### Guardrails Category (Runtime Filtering)

| Company | Focus | Difference from us |
|---------|-------|-------------------|
| Guardrails AI | Runtime input/output validation | Runtime filtering vs build-time governance |
| NeMo Guardrails | Conversational safety rails | Prompt-level, not object-level |
| Lakera | Prompt injection detection | Security-only, not quality |

---

## Our Positioning

### One-liner
"AI input governance for Snowflake — ensure the objects agents depend on are correct before they reach production."

### Three Pillars

| Pillar | What | Unique? | Cost |
|--------|------|---------|------|
| 1. Structural Audit | 15+ rule checks on semantic view YAML (docs, naming, metadata, relationships, inconsistencies, duplicates) | YES — no competitor does this | Zero (offline Python) |
| 2. Accuracy Evaluation | Question bank evaluation with graduated CI/CD gates (DEV 60% > PROD 85%) | Partially — wraps Snowflake native EXECUTE_AI_EVALUATION | ~9 AI Credits/run (35-Q bank) |
| 3. Interaction Quality | Deterministic rules engine over ai_observability_events (tool looping, excessive steps, token burn, abandoned convos) | YES — zero LLM cost, real-time | Zero (pure SQL) |

### The Killer Differentiator

**Nobody else audits the objects an AI agent calls upon.**

- Langfuse monitors what the agent said → we ensure what the agent reads from is correct
- Guardrails filters bad prompts at runtime → we prevent bad objects at build-time
- Snowflake native evaluates answers → we evaluate the structural quality of the inputs

---

## Why Snowflake-Native Matters

1. **Zero data movement** — semantic views, agents, eval results, observability events all live in Snowflake
2. **Native RBAC** — ANALYST can edit, REVIEWER can approve, DEPLOYER can promote, ADMIN owns everything
3. **One platform bill** — no separate SaaS subscription for monitoring
4. **Tasks + Alerts** — scheduled evaluation and automated alerting without external orchestration
5. **Streamlit in Snowflake** — monitoring dashboard deploys alongside the data

---

## Proof Points (Demo Results)

| Metric | Result |
|--------|--------|
| Agent answer accuracy | 94.3% effective (31/33 genuine questions perfect) |
| Safety score | 8.73/10 |
| Structural audit | 0 findings (clean SV) |
| Framework caught own GT bugs | 2/35 questions had incorrect ground truth — framework surfaced them |
| Setup time | One command (`bootstrap.py`), ~5 minutes |
| Ongoing cost | ~9 AI Credits/evaluation run (35-Q bank), XSMALL warehouse |

---

## 5 Critical Market Gaps We Address

1. **Input Object Governance** — Nobody audits semantic models before agents use them
2. **Deterministic Quality Rules** — Most tools rely on expensive LLM judges for everything; we use zero-cost SQL rules for interaction quality
3. **CI/CD-Native Enforcement** — Graduated thresholds that block bad deployments, not just alerting after the fact
4. **Framework Caught Its Own Bugs** — Meta-validation: the framework identified quality issues in its own evaluation ground truth
5. **Snowflake-Native Zero-Trust** — Everything governed by Snowflake RBAC; no external API keys or data egress

---

## Competitive Matrix

| Capability | Us | Langfuse | LangSmith | Arize | Guardrails AI | Snowflake Native |
|---|---|---|---|---|---|---|
| Semantic model structural audit | YES | No | No | No | No | No |
| CI/CD quality gates | YES | Partial | Partial | No | No | No |
| Question bank evaluation | YES | Yes | Yes | Yes | No | Yes (manual) |
| Deterministic interaction quality rules | YES | No | No | No | No | No |
| Zero LLM cost monitoring | YES | No | No | No | No | Partial |
| Snowflake-native (no data egress) | YES | No | No | No | No | YES |
| Multi-environment promotion path | YES | No | No | No | No | No |
| Automated alerts + tasks | YES | Yes | Yes | Yes | No | Manual |
| Open source | YES | Yes | Partial | Yes | Yes | No |

---

## Roadmap (Next 3-6 months)

1. **Suggestion Engine** — when a question fails eval, auto-generate the SV YAML patch to fix it
2. **Auto-Remediation PRs** — CI not only blocks but opens a fix PR with recommended changes
3. **Multi-Agent Governance** — extend to orchestrated agent chains (agent-of-agents)
4. **Cross-Environment Drift Detection** — DEV vs PROD SV comparison for silent divergence
5. **Client Self-Service SDK** — pip-installable package for bring-your-own SV + question bank

---

## Target Customer Profile

- Snowflake enterprise accounts deploying Cortex Agents or Cortex Analyst
- Data teams (5-20 people) self-serving semantic view development
- Industries: retail, financial services, healthcare, logistics (domain-agnostic framework)
- Pain: "We deployed an agent but have no idea if it's getting worse over time"
- Budget: $0 (framework is open-source) + Snowflake compute costs only

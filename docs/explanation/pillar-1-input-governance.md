# Pillar 1: Input governance

> Status: Stable | Last reviewed: 2026-05-26 | Audience: Engineers, solution architects, customers

**Purpose.** Explain what Pillar 1 (semantic view auditing) does today, the difference between structural and domain-aware validation, and why closing that gap is the framework's strategic differentiator.

## The idea behind input governance

Most agent observability tools monitor the agent's output: they score what the agent said after it said it. This framework adds something almost no one else does — it audits the **inputs** the agent depends on. The most important input is the semantic view: the model that an agent's text-to-SQL tool reads from to generate queries.

The premise is simple: if the semantic view is poorly described, inconsistently named, or structurally incomplete, the agent will generate wrong SQL no matter how good the agent itself is. Catching those defects at the source — before the agent ever runs — is cheaper and more reliable than catching them downstream.

## What Pillar 1 does today

[evaluation/audit_semantic_view.py](../../evaluation/audit_semantic_view.py) runs six structural checks over a semantic view, parsing either the YAML definition or a deployed view introspected with `DESCRIBE`:

| # | Check | What it validates |
| --- | --- | --- |
| 1 | Documentation | Every table, dimension, fact, and metric has a non-empty description |
| 2 | Naming conventions | Names use a consistent pattern, no special characters |
| 3 | Metadata completeness | Dimensions declare data types, sample values, synonyms where relevant |
| 4 | Type safety | IDs and categories are dimensions; numeric measures are facts |
| 5 | Relationships | The relationship graph connects the tables (coverage check) |
| 6 | Inconsistencies and duplicates | No conflicting or redundant definitions |

Each finding carries a severity (CRITICAL, ERROR, WARNING, INFO). CI fails when any CRITICAL or ERROR is present. The audit runs offline against the YAML, so it costs nothing in LLM tokens.

## The gap: structural, not domain-aware

These six rules check that the semantic view is **structurally healthy for an LLM to consume**. They are domain-agnostic — they validate shape, naming, types, and completeness, but they do not understand the business meaning of the model.

They cannot, for example, know that:

- a `revenue` metric should aggregate with `SUM`, not `AVG`
- `order_date` should be a time dimension so it can be queried by month or quarter
- a `*_rate` or `*_pct` metric should be bounded between 0 and 1
- `customer_id` is an identifier that should never be aggregated

These are domain-specific assertions. A generic linter cannot produce them; they require understanding what the model means.

Today, therefore, Pillar 1 is best described as a **structural linter for semantic views** plus the runtime interaction-quality engine. That is genuinely useful, but it is not yet the differentiator.

## Where it is headed

The strategic vision is **AI-generated, domain-aware audit rules**. An LLM reads the semantic view, infers its domain, and generates granular validation rules tailored to that specific model. Those rules are generated once (pre-CI), committed to the repository as a reviewable artifact, and then applied deterministically in CI at no per-run LLM cost.

This is the layer that turns Pillar 1 from a structural linter into something no competitor offers: validation that understands the domain semantics of the specific model the agent reads from. The honest assessment of its risks: chiefly, rule hallucination, mitigated by requiring human review of generated rules before they gate CI.

## Summary

- **Today:** six structural rules, zero LLM cost, domain-agnostic. A solid floor.
- **Gap:** no understanding of business meaning.
- **Vision:** AI-generated domain-aware rules, generated pre-CI, reviewed by humans, applied deterministically.

When describing Pillar 1 to customers, be precise: we audit the structural health of the inputs today, and the domain-aware layer is the roadmap differentiator — not a current capability.

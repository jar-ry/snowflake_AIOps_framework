# Contributing

Thanks for your interest in improving the Snowflake AI Evaluation Framework. This
document describes how changes are proposed, reviewed, and merged.

The framework's whole premise is a **governed branch → PR → merge loop**: changes
to an agent, semantic view, or question bank are gated by CI before they reach a
deployed environment. Contributions to the framework itself follow the same loop.

## Repository layout

- **Framework (domain-agnostic)** lives at the repo root: `setup/`, `evaluation/`,
  `monitoring/`, `config/defaults.yaml`, `.github/workflows/`, `docs/`.
- **Instances (domain-specific)** live under `examples/<name>/` — the bundled
  reference instance is `examples/retail/` (its config, semantic views, agents,
  question banks, data, and demo material).

A change is either a *framework* change (affects every instance) or an *instance*
change (affects one example). Keep the two separate where practical — it makes
review and CI scoping cleaner.

To add a new instance, copy `examples/retail/` to `examples/<name>/` and edit only
that folder. See the README for the full onboarding flow.

## Branching

Cut a branch off `main`. Use a descriptive, prefixed name:

```text
feat/<phase>-<issue>-<slug>     # new capability
fix/<phase>-<issue>-<slug>      # bug fix
docs/<phase>-<issue>-<slug>     # docs / governance
```

Examples from history: `feat/phase1-28-cost-calibration`,
`docs/phase3-31-demo-credits`.

## Commits

This repo uses [Conventional Commits](https://www.conventionalcommits.org/) with
the relevant issue number in the scope:

```text
feat(#28): calibrate cost model against measured actuals
fix(#37): SV eval 0% — Cortex Analyst response-shape mismatch
docs(#31): denominate demo cost figures in AI Credits
```

Write the body to explain the *why*, not just the *what*.

## Pull requests

1. Open a PR into `main` and link the issue it addresses (`Closes #NN`).
2. Assign it to the matching milestone (milestones map to delivery **phases**).
3. Keep a PR scoped to one concern. Prefer several small, independently mergeable
   PRs over one large one — disjoint file surfaces can land in parallel without
   conflicts.
4. CI must be green before merge (see below).
5. PRs are **squash-merged**, so the PR title becomes the commit on `main` — give
   it a clean Conventional-Commit title.

## CI gates

Four workflows live in `.github/workflows/`:

| Workflow | Trigger | Purpose |
| --- | --- | --- |
| `semantic_view_ci.yml` | PR touching an instance's `semantic_views/` (or `evaluation/**`) | Offline structural audit → deploy to DEV → question-bank evaluation → PR comment |
| `agent_ci.yml` | PR touching an instance's `agents/` / `question_banks/agent/` (or `evaluation/**`) | Native agent (GPA) evaluation → PR comment |
| `semantic_view_cd.yml` | Merge to `main` | Promote semantic view to PROD |
| `agent_cd.yml` | Merge to `main` | Promote agent to PROD |

The active instance is resolved from the changed paths, so a PR that only touches
framework code (`evaluation/**`) runs against the default instance. Docs-only PRs
(for example `docs/`, `examples/*/demo/`) touch no gated path and run no eval.

## Local development

- Python deps: `pip install -r requirements.txt`.
- Evaluations and deploys need a Snowflake connection. Interactive (SSO) auth works
  locally; **headless/CI runs require key-pair auth** (SSO browser auth blocks in CI).
  Set `SNOWFLAKE_ACCOUNT` / `SNOWFLAKE_USER` / `SNOWFLAKE_PRIVATE_KEY` (and
  `SNOWFLAKE_ROLE`) rather than relying on a named connection profile.
- Run an evaluation against the bundled instance:

  ```bash
  AIOPS_INSTANCE=examples/retail python evaluation/audit_agent.py --environment dev
  ```

- Cost: evaluations consume Snowflake AI Credits. See
  [docs/reference/cost-model.md](docs/reference/cost-model.md) before running large banks.

## License

This project is licensed under the **Apache License 2.0** — see [LICENSE](LICENSE)
and [NOTICE](NOTICE). By submitting a Contribution, you agree that it is provided
under the terms of that license (per Section 5 of the Apache License 2.0); no
separate CLA is required.

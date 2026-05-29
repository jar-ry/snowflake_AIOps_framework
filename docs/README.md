# Documentation

> Status: Stable | Last reviewed: 2026-05-26 | Audience: Engineers, solution architects, customers

**Purpose.** This is the documentation map for the Snowflake AIOps Agent Enforcement Framework. It is organized using the [Diátaxis](https://diataxis.fr/) framework, which separates documentation into four modes based on what the reader needs.

## How this documentation is organized

| Mode | Directory | Answers the question | When to read |
| --- | --- | --- | --- |
| Tutorials | `tutorials/` | "Can you teach me?" | First time using the framework, learning-oriented |
| How-to guides | `how-to/` | "How do I do X?" | You have a specific task to accomplish |
| Reference | `reference/` | "What are the exact details?" | You need precise, lookup-style information |
| Explanation | `explanation/` | "Why does it work this way?" | You want to understand the design and tradeoffs |

The root [README](../README.md) remains the project entry point and getting-started guide. This `docs/` tree holds the deeper, durable reference and explanation material.

## Reference

Information-oriented, lookup-style material.

- [Platform quirks](reference/platform-quirks.md) — Snowflake platform limitations the framework works around, their workarounds, and current status.
- [Cost model](reference/cost-model.md) — how evaluation cost is computed in Snowflake AI Credits, the formula, and worked examples.

## Explanation

Understanding-oriented material about design and intent.

- [Pillar 1: Input governance](explanation/pillar-1-input-governance.md) — what the semantic view audit does today, the structural-vs-domain gap, and where it is headed.

## How-to guides

Task-oriented recipes. No guides have been migrated here yet — operational how-tos currently live in the root [README](../README.md) and [demo/](../demo/) runbooks. New task-specific guides should be added here.

## Tutorials

Learning-oriented walkthroughs. None yet. New end-to-end learning paths for first-time users belong here.

## Documentation conventions

Every document in this tree follows these conventions (enforced by `.markdownlint.json`):

- A single H1 title, followed by a metadata blockquote: `Status | Last reviewed | Audience | Related`.
- A one-line **Purpose** statement directly under the metadata.
- Sentence-case headings.
- Relative links between documents (so they resolve on GitHub and in local viewers).
- Fenced code blocks with an explicit language tag.
- Tables for reference data rather than long prose lists.

When adding a document, place it in the directory matching its Diátaxis mode and add a link to it in this index.

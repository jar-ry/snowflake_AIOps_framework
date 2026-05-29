# Documentation

> Status: Stable | Last reviewed: 2026-05-26 | Audience: Engineers, solution architects, customers

**Purpose.** This is the documentation map for the Snowflake AIOps Agent Enforcement Framework. It is organized using the [Diátaxis](https://diataxis.fr/) framework, which separates documentation by what the reader needs.

## How this documentation is organized

| Mode | Directory | Answers the question | When to read |
| --- | --- | --- | --- |
| Reference | `reference/` | "What are the exact details?" | You need precise, lookup-style information |
| Explanation | `explanation/` | "Why does it work this way?" | You want to understand the design and tradeoffs |

The root [README](../README.md) remains the project entry point and getting-started guide. This `docs/` tree holds the deeper, durable reference and explanation material.

## Reference

Information-oriented, lookup-style material.

- [Cost model](reference/cost-model.md) — how evaluation cost is computed in Snowflake AI Credits, the formula, and worked examples.

## Explanation

Understanding-oriented material about design and intent.

- [Pillar 1: Input governance](explanation/pillar-1-input-governance.md) — what the semantic view audit does today, the structural-vs-domain gap, and where it is headed.

## Documentation conventions

Every document in this tree follows these conventions:

- A single H1 title, followed by a metadata blockquote: `Status | Last reviewed | Audience | Related`.
- A one-line **Purpose** statement directly under the metadata.
- Sentence-case headings.
- Relative links between documents (so they resolve on GitHub and in local viewers).
- Fenced code blocks with an explicit language tag.
- Tables for reference data rather than long prose lists.

When adding a document, place it in the directory matching its Diátaxis mode and add a link to it in this index.

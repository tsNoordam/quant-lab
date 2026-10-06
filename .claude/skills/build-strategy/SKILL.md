---
name: build-strategy
description: Convert validated academic research into a deterministic paper-faithful trading strategy without hidden assumptions.
---

# Build Strategy

Read:

- CLAUDE.md
- research/extraction/
- research/equations/
- research/methodology/
- research/assumptions/

Write the specifications (Markdown, every rule tagged) to:

research/specs/replication/
research/specs/baseline/
research/specs/extensions/

Implement them as code in:

src/quant_lab/strategies/

with parameters in conf/strategy/ (never hardcoded).

Strategy replication must remain faithful to the paper.

Baseline may introduce only explicitly documented implementation assumptions.

Extensions must be clearly separated.

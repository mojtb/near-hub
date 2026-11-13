# Audits

Dated audits of the warehouse's own data, kept as they were written. Each one describes the warehouse on its day, so
its table counts, column names and open items are those of that pin, and later work has changed many of them. For the
warehouse as it is now, read [DATA_CATALOG.md](../DATA_CATALOG.md) and [RECONCILIATION.md](../RECONCILIATION.md).

| Audit | Measured at the pin of | What it asked |
|---|---|---|
| [DATA_AUDIT_2026-11-05.md](DATA_AUDIT_2026-11-05.md) | 2026-11-01, then 2026-11-05 | Does each table hold what it says, and which questions of a NEAR thesis can the warehouse answer |
| [DATA_AUDIT_2026-11-05_SECOND_PASS.md](DATA_AUDIT_2026-11-05_SECOND_PASS.md) | 2026-11-05 | The same two questions, after the first audit's fixes were merged |
| [REDUNDANCY_AUDIT_2026-11-09.md](REDUNDANCY_AUDIT_2026-11-09.md) | 2026-11-08 | Which DefiLlama and Dune figures another source already gives, and which gold columns repeat a value |

## Names that have changed since

- The project was called `near-thesis` until 2026-11-13, so the audits name branches and folders that begin with it.
- `near-deflation-clock`, or the Deflation Clock, is the earlier scaffold by the same author that the first snapshot
  was imported from. The [README](../../README.md#disclosures) says how.
- The site files the redundancy audit names (`design-a.html`, `design-d.html`, `_build/export_data.py`) were drafts
  kept outside this repository. The dashboard is now [`site/`](../../site), and its data is written by
  `tools/site_data.py`.

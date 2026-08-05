# local-meeting-notes — agent guidance

Before proposing, planning, or building any feature, read
[`docs/product-definition.md`](./docs/product-definition.md). It is the definition
layer: what the product is, who the reader is, the ten north-star features with
their research grounding and build status, and the non-goals. Work that serves none
of the ten features, or crosses a non-goal, needs a dated amendment there first.

Sequencing authority stays with [`docs/vertical-slice.md`](./docs/vertical-slice.md)
(waves, build order, human gates). Surface detail lives in
[`docs/screens-and-states.md`](./docs/screens-and-states.md).

Statuses in any doc are hypotheses, not evidence. Verify against code before
repeating one: `worker/main.py` (`ALPHA_OPERATIONS`),
`apps/desktop/src-tauri/tests/shell_contract.rs` (registered-command pins), and
`docs/distribution-runbook.md` (release record).

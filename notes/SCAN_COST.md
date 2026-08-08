# What a library open actually costs, and what actually refuses

**Updated 2026-08-08, after the fix.** The refusal this file recorded is gone,
and the receipt was re-run on the same harness so the before and after are one
artifact rather than two. `notes/scan_cost_receipt.json` is now `scan-cost/2`:
the query fields report `{shown, matched}` where they used to report the string
`library read capacity exceeded`. The timing conclusions below are unchanged.

Measured 2026-08-08 with `crates/session-core/src/bin/corpus-scan-bench.rs` on a
synthetic corpus it generates itself. Receipt: `notes/scan_cost_receipt.json`.
Every byte it reads is written by the harness from a counter; it touches no real
meeting.

## Why it was run

`docs/vertical-slice.md` named US-13.6 — the launch scan that re-reads every
meeting — as the next build on 2026-08-08, on the stated ground that it is "a wait
that grows every month." **Nobody had measured it.** The scan number existed from
2026-08-07; the index sync that runs beside it on the same path never did, so the
figure being reasoned from was the smaller half of an unknown sum.

## What a library open costs

`LibraryReader::rebuild` does two things: rebuild the projection from files, then
sync the corpus index. Both, every open.

| Meetings | Projection rebuild | Index sync, cold | Index sync, warm | Windows |
|---|---|---|---|---|
| 5 | 5.2 ms | 3.3 ms | 0.02 ms | 95 |
| 20 | 18.3 ms | 11.5 ms | 0.05 ms | 380 |
| 200 | 171.2 ms | 108.8 ms | 0.26 ms | 3,800 |
| 800 | 671.8 ms | 446.9 ms | 1.10 ms | 15,200 |

200 turns per meeting throughout; 200 meetings is 7.4 MB of transcript.

**Read these as one significant figure.** An earlier run of the same harness on
the same machine gave 199 ms at 200 meetings and 861 ms at 800 — roughly 20 %
above the committed run, on a machine doing nothing visibly different. Every
conclusion below survives either set, which is the only reason a single run is
enough to draw one. A conclusion that needed 663 rather than 861 would need a
distribution, not a number.

**The sync is not the problem and never was.** Warm — which is what almost every
open is, because `sync_if_changed` skips on a digest match — costs 0.26 ms at 200
meetings. It is three orders of magnitude under the scan beside it. Cold sync is
about half the scan and happens once per change, not per open.

**The scan is linear and, at any size a person will reach soon, small.** A
library open at 200 meetings costs under 200 ms. At 800 — roughly three years of
daily meetings — somewhere between 0.7 and 0.9 seconds.

## So US-13.6 has no trigger yet

That is not "a wait that grows every month." It is a wait nobody notices for
years. **The claim was written without a number and the number does not support
it.**

US-13.6 is not withdrawn; the acceptance criteria are still right and the growth
is still linear. What it lacks is a reason to be built now. **The trigger is a
corpus size, not a date**: extrapolating the two runs above, the projection
rebuild crosses 1.5 s somewhere between 1,400 and 1,800 meetings on this
hardware, and a library open that takes longer than a second is worth removing.
That spread is the point — it is a signpost, not a threshold to test against.
Re-run this harness before building it rather than re-reading this table; the
hardware and the per-meeting work will both have moved.

## What the same run found instead, and it is shipped

**A common word refused at five meetings. Fixed the same day.**

`LibraryProjection::search` collected every hit in memory and then, past
`MAX_SEARCH_RESULTS` (100), returned `CapacityExceeded` for the *whole query*.
Not a truncated list — an error. The shell rendered it as "That search has too
many matches. Use a more specific exact phrase," with no results.

Five synthetic meetings already exceeded the cap on the word `alpha`, and it
refused at every size measured: 5, 20, 200, 800.

It now filters, then cuts to a hundred, and reports what it cut from. The same
harness, re-run:

| Meetings | Shown | Matched |
|---|---|---|
| 5 | 100 | 1,500 |
| 20 | 100 | 6,000 |
| 200 | 100 | 60,000 |
| 800 | 100 | 240,000 |

**Filter first, then cut, and the order is load-bearing.** Cutting to a hundred
before applying a folder or date filter would answer "the hundred most recent
matches anywhere, minus the ones outside this filter" — nothing at all when the
filter selects older meetings.
`a_filtered_search_pages_within_the_filter_and_not_across_it` pins it, and it
fails under exactly that mutation. The old code could not have this bug, because
past the cap it refused rather than answering.

**The cap's real job is unchanged.** It bounds how many handles one response
holds open, and truncating to a hundred bounds that exactly as refusing did. What
changed is what a person gets for a common word: a hundred results instead of
none.

This is not a scale problem a user reaches eventually. It is the first week. Any
word that appears more than a hundred times across a library — a project name, a
person's name, "invoice", "deadline" — returns nothing, in a build that shipped
on 2026-08-08 as 0.5.0.

**It was a known defect that was recorded and not tracked.** The build queue's
Wave 1 row 1 has said since 2026-08-07 that file-walking search "does not survive
a real corpus — and, measured, refuses a common word at one meeting." That
sentence is the justification for the store existing, and the refusal outlived
the store by a day.

**Moving matching into SQL was considered and rejected.** The store could rank
and `LIMIT` in a query, which is the scalable shape. It would also be a second
implementation of `search-normalization/1`, which is pinned to
`char::to_lowercase` in a named rustc release and enforced by a test that shells
out to `rustc -Vv`. Two normalizations do not merely differ in speed; they differ
in what matches, and the offsets one of them returns are what highlights a span.
So matching stays in Rust and the fix is the cut, not the storage.

That leaves the scan linear: a query costs 171 ms at 200 meetings and 672 ms at
800. **The trigger for pushing candidate selection into the store is that
latency**, and the shape that keeps one normalization is a token table built at
sync time *by the same Rust normalizer*, with the pinned matcher run only over
the turns it selects. Not built, and not needed at any size measured here.

## What this does not measure

- Real transcripts. Synthetic turns are twelve words of a fixed vocabulary; real
  speech has different token distributions and different match counts, which
  affects when the cap bites but not that it does.
- Cold-cache disk. Every run reads files this process wrote seconds earlier, so
  the page cache is warm. A genuine cold open on a spinning-rust or
  network-backed volume would be slower, and no one runs this product on one.
- Anything under contention. The numbers are a quiet machine.

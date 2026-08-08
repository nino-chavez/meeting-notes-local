# What a library open actually costs, and what actually refuses

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
| 5 | 4.3 ms | 3.3 ms | 0.03 ms | 95 |
| 20 | 20.3 ms | 11.6 ms | 0.04 ms | 380 |
| 200 | 179.1 ms | 111.3 ms | 0.26 ms | 3,800 |
| 800 | 662.6 ms | 443.1 ms | 1.13 ms | 15,200 |

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

**A common word refuses at five meetings.**

`LibraryProjection::search` collects every hit in memory and then, past
`MAX_SEARCH_RESULTS` (100), returns `CapacityExceeded` for the *whole query*. Not
a truncated list — an error. The shell renders it as "That search has too many
matches. Use a more specific exact phrase," with no results.

Five synthetic meetings hold 95 windows and already exceed the cap on the word
`alpha`. It refuses at every size measured: 5, 20, 200, 800.

This is not a scale problem a user reaches eventually. It is the first week. Any
word that appears more than a hundred times across a library — a project name, a
person's name, "invoice", "deadline" — returns nothing, in a build that shipped
on 2026-08-08 as 0.5.0.

**It is a known defect that was recorded and not tracked.** The build queue's
Wave 1 row 1 has said since 2026-08-07 that file-walking search "does not survive
a real corpus — and, measured, refuses a common word at one meeting." That
sentence is the justification for the store existing. The store was then built,
and exact search was never moved onto it: `library_reader.rs::search_current`
still calls `self.projection.search_filtered`.

The store can answer this. It holds turns in SQLite and can rank and `LIMIT` in
the query, which is what a search over a real corpus has to do. Nothing about
that is research — it is the work row 1 was justified by and did not finish.

## What this does not measure

- Real transcripts. Synthetic turns are twelve words of a fixed vocabulary; real
  speech has different token distributions and different match counts, which
  affects when the cap bites but not that it does.
- Cold-cache disk. Every run reads files this process wrote seconds earlier, so
  the page cache is warm. A genuine cold open on a spinning-rust or
  network-backed volume would be slower, and no one runs this product on one.
- Anything under contention. The numbers are a quiet machine.

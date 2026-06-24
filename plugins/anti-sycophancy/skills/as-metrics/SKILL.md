---
name: as-metrics
description: Show a summary of the local anti-sycophancy metrics log (counts and verdicts only — no message content). Also explains how to share it voluntarily.
---

# Anti-sycophancy metrics

When this skill is invoked:

1. Read `.claude/as-metrics.jsonl` (one JSON object per line). If it does not exist, tell the user no metrics have been recorded yet and stop.
2. Summarize, counting across all lines — **never quote any content** (there is none in the file). The file has two line shapes: orchestrator lines (with `c1`/`guardian`/`safety`/`rewrote`/`mode`) and hook lines (`event:"subagent_stop"`); both carry a `ts`.
   - the date range covered (earliest → latest `ts`);
   - total substantive turns reviewed (orchestrator lines: those with a `c1` field);
   - how many were flagged by `as-critic-blind` (`c1=true`);
   - relational critic verdicts: `violated` / `ok` / `n/a`;
   - how many `safety=escalate`;
   - how many led to a rewrite (`rewrote=true`);
   - split by `mode` (couple / solo / auto) if present;
   - deterministic `subagent_stop` events (from the hook), as a rough cross-check.
3. Present a short table. End with one line on sharing:
   > To share feedback, send the file `.claude/as-metrics.jsonl` — it contains only counts and verdicts, never the text of any message. Sharing is entirely opt-in.

## Privacy note
The metrics log records flags and verdicts, not conversations. There is no automatic upload anywhere — sharing is a manual action the user chooses.

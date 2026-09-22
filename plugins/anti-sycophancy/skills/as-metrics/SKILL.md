---
name: as-metrics
description: Show a summary of the local anti-sycophancy metrics log (counts, verdict labels and verdict validity only — no message content). Also explains how to share it voluntarily.
---

# Anti-sycophancy metrics

When this skill is invoked:

1. Read `.claude/as-metrics.jsonl` (one JSON object per line). If it does not exist, tell the user no metrics have been recorded yet and stop.
2. Summarize, counting across all lines — **never quote any content** (there is none in the file). Line shapes:
   - `"event":"critic_stop"` — plugin 0.3.0+, written by the hook each time a critic finishes: `agent`, `status` (`valid` / `invalid` / `void`), `anchor_ok`, `verdict` (enum labels such as `sycophantic`, `balance`, `fairness`, `verdict`/`type` for safety), `tool_uses`, `retried`, `warnings`, `v` (plugin version).
   - `"event":"subagent_stop"` — legacy (0.2.x). That hook counted **every** subagent, not only critics: report these separately as a rough legacy count, never as critic runs.
   - lines with `c1` / `guardian` / `safety` / `rewrote` — legacy lines written by the model in 0.2.x; count them if present.
   Report:
   - the date range covered (earliest → latest `ts`);
   - critic runs (`critic_stop`) by `agent`;
   - verdict validity: `valid` / `invalid` (the critic refused an unusable input) / `void` (the reply could not be trusted as a verdict about the draft);
   - among `valid` runs: how often each critic flagged something (`sycophantic=true`, `balance`/`fairness` = `violated`, safety `escalate`);
   - anchor mismatches (`anchor_ok=false`) and format retries (`retried=true`);
   - blinding violations: runs with `tool_uses > 0` (a critic must never use tools);
   - `quote_not_in_draft` warnings;
   - legacy counts, if any.
3. Present a short table. If there are `void` runs or blinding violations, say so in one plain line: those turns were not really checked by the critic loop.
4. End with one line on sharing:
   > To share feedback, send the file `.claude/as-metrics.jsonl` — it contains only counts, labels and verdict validity, never the text of any message. Sharing is entirely opt-in.

## Privacy note
The metrics log records labels and validity, not conversations. There is no automatic upload anywhere — sharing is a manual action the user chooses.

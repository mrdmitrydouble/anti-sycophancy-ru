---
name: as-on
description: Turn ON anti-sycophancy mode (auto) — from now on, route every substantive draft through the critic subagents and revise before replying. The relational critic is chosen automatically (couple vs solo). For an explicit mode use /as-couple or /as-solo.
---

# Enable anti-sycophancy mode (auto)

When this skill is invoked:

1. Write `auto` to the file `.claude/.as-mode` (create the file/dir if missing).
2. Tell the user, in ONE line, that anti-sycophancy mode is ON (auto mode). Add a one-line **non-clinical disclaimer**: this is not therapy, diagnosis, or an emergency service, and the safety gate is a best-effort screen you should not rely on for safety — in danger → local emergency services / a crisis line (the `as-orchestrator` agent carries the CRISIS RESOURCES block).
3. For the rest of the session, follow the review protocol below before sending any **substantive** reply. Skip it for trivial acknowledgements, clarifying questions, or raw tool output.

> This is a **soft** control: Claude Code does not force a plugin to alter replies. The mode works because you, the assistant, follow the protocol. If a turn slips through, just resume on the next one. The honest limit is documented in the README.

## Review protocol (per substantive reply)

1. **Draft** your answer normally (you see full context).
2. **as-critic-blind — ALWAYS.** Call `as-critic-blind` with a *blinded* input: a neutral 3rd-person `ТИП ЗАПРОСА` (no names/roles/relationships/emotions) + your full `ЧЕРНОВИК`. It also catches ontological verdicts about the user (the self axis).
3. **Relational critic — routed automatically (Fix #1).**
   - Pure solo introspection (one speaker, no other party present and no absent person discussed) → relational critic is **n/a**, skip it.
   - Two or more people present (couple/group) → call **`as-guardian`** with `КОНТЕКСТ` + verbatim `РЕПЛИКИ СТОРОН` + `ЧЕРНОВИК`.
   - One person discussing an ABSENT person → call **`as-solo-guardian`** with `КОНТЕКСТ` + verbatim `НАРРАТИВ ПОЛЬЗОВАТЕЛЯ ОБ ОТСУТСТВУЮЩЕМ` + `ЧЕРНОВИК`.
4. **as-safety — only if the deterministic gate fires (Fix #2).** Scan the user's turn AND your draft for crisis lexicon (suicide/self-harm incl. indirect, harm to others, psychosis, acute ED, violence/coercive control, refusal to eat/drink, **sudden calm/relief after despair**), a **diagnosis requested by the user** ("what disorder do I/they have" → C12-REQ), or clinical overreach in your draft (diagnosis/DSM label, dosage advice, risk-assessment protocol, couple-mediation amid violence). Only on a match, call `as-safety` (pass the matched code T1..T9 / C12 / C12-REQ — the full table is in the `as-orchestrator` agent). If it returns `escalate`, stop facilitation, **emit the CRISIS RESOURCES block + the "you're talking to an AI" disclosure** (verbatim, from `as-orchestrator`), and route to a human — safety overrides the rewrite. On hard-crisis classes (T1/T2/T3/T6/T8) keep the deterministic floor: never leave the turn with zero safety pointer even if as-safety says `continue`. For C12-REQ, never name a diagnosis — switch to psychoeducation.
5. **Rewrite once** per the critics' instructions: cut ungrounded agreement, flattery, status verdicts, leading framing; restore the missing/absent side; keep what was genuinely correct.
6. **Log a content-free metric** to `.claude/as-metrics.jsonl` (counts and verdicts only, never content) — see the `as-orchestrator` agent for the exact line.
7. **Return the final answer.** Keep critic transcripts hidden unless asked; optionally add a one-line note if something material changed.

The full orchestration logic also lives in the `as-orchestrator` agent — you may delegate a turn to it instead of running the protocol inline.

---
name: as-solo
description: "Turn ON anti-sycophancy mode in SOLO mode — one person reflecting alone. Critics — as-critic-blind (always; also catches verdicts about the user's own identity) + as-solo-guardian (fairness to an absent person, when one is discussed) + as-safety (on gate hit)."
---

# Enable anti-sycophancy — solo mode

When this skill is invoked:

1. Write `solo` to the file `.claude/.as-mode` (create the file/dir if missing).
2. Tell the user, in ONE line, that anti-sycophancy mode is ON in **solo** mode. Add a one-line **non-clinical disclaimer**: this is not therapy, diagnosis, or an emergency service, and is not a substitute for a professional — in danger or crisis → local emergency services / a crisis line (CRISIS RESOURCES block in the `as-orchestrator` agent).
3. For substantive replies, run the review protocol with **`as-solo-guardian`** as the relational critic:
   - **Solo-relational** (the user discusses a person who is NOT here): as-solo-guardian checks fairness to that absent person — no absentee verdicts, no diagnosis-by-proxy, present their likely position.
   - **Solo-self** (pure self-analysis, no absent person): as-solo-guardian returns n/a. as-critic-blind still guards against ontological verdicts about the user ("you are X / healthy / ill / different") and single-interpretation framing.

Follow the full protocol (see the `as-orchestrator` agent): as-critic-blind always; as-solo-guardian when an absent person is discussed; as-safety only on a deterministic gate hit; one rewrite pass.

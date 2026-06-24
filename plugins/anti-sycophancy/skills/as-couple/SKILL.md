---
name: as-couple
description: "Turn ON anti-sycophancy mode in COUPLE/GROUP mode — relational balance between present parties. Critics — as-critic-blind (always) + as-guardian (balance) + as-safety (on gate hit)."
---

# Enable anti-sycophancy — couple/group mode

When this skill is invoked:

1. Write `couple` to the file `.claude/.as-mode` (create the file/dir if missing).
2. Tell the user, in ONE line, that anti-sycophancy mode is ON in **couple/group** mode. Add a one-line **non-clinical disclaimer**: this is not therapy, diagnosis, or an emergency service, and is not a substitute for a professional — in danger or crisis → local emergency services / a crisis line (CRISIS RESOURCES block in the `as-orchestrator` agent).
3. For substantive replies, run the review protocol with **`as-guardian`** as the relational critic (balance between the parties who are present). This is the mode for mediating a conversation between two or more people.

Follow the full protocol (see the `as-orchestrator` agent or the `as-on` skill): as-critic-blind always; as-guardian when a second side is present; as-safety only on a deterministic gate hit; one rewrite pass.

---
name: as-status
description: Show whether anti-sycophancy mode is currently ON or OFF, and in which mode (auto / couple / solo).
---

# Anti-sycophancy mode status

When this skill is invoked:

1. Read the file `.claude/.as-mode`.
   - `auto` → **ON (auto)** — relational critic chosen per turn.
   - `couple` → **ON (couple/group)** — relational critic is as-guardian.
   - `solo` → **ON (solo)** — relational critic is as-solo-guardian.
   - `off`, empty, or missing → **OFF**.
2. Report the status in one line. If ON, briefly remind which critics are active:
   - `as-critic-blind` — always (textual sycophancy + verdicts about the user);
   - relational critic — `as-guardian` (couple) / `as-solo-guardian` (solo) / chosen per turn (auto); n/a for pure self-analysis;
   - `as-safety` — only on a crisis/diagnosis gate hit.

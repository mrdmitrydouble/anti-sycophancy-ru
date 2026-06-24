---
name: as-off
description: Turn OFF anti-sycophancy mode — stop routing drafts through the critic subagents.
---

# Disable anti-sycophancy mode

When this skill is invoked:

1. Write `off` to the file `.claude/.as-mode` (create the file/dir if missing).
2. Tell the user, in ONE line, that anti-sycophancy mode is OFF.
3. Stop running the review protocol. Reply normally from now on.

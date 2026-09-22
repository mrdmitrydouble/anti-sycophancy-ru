#!/bin/sh
# anti-sycophancy: SubagentStop hook for the critics (logic: as_critic_stop.py) -
# content-free metric line, clone-local git exclude, one format-repair retry.
DIR=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd) || exit 0
INPUT=$(cat)
. "$DIR/as_lib.sh"
PY=$(as_find_python) || exit 0
printf '%s' "$INPUT" | "$PY" "$DIR/as_critic_stop.py" 2>/dev/null
exit 0

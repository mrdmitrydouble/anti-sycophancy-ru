#!/bin/sh
# anti-sycophancy: PostToolUse check of a critic's reply (logic: as_verify_verdict.py --hook post).
# Tells the calling agent whether the verdict is VALID, INPUT INVALID or VOID. Advisory:
# if Python is missing the call was already refused by the input guard.
DIR=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd) || exit 0
. "$DIR/as_lib.sh"
INPUT=$(cat)
as_is_critic_call "$INPUT" || exit 0
PY=$(as_find_python) || exit 0
printf '%s' "$INPUT" | "$PY" "$DIR/as_verify_verdict.py" --hook post 2>/dev/null
exit 0

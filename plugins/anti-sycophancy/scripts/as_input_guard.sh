#!/bin/sh
# anti-sycophancy: PreToolUse input guard for the critic subagents (logic: as_input_guard.py).
# Non-critic subagent calls pass untouched. On a critic call, any failure of the guard itself
# denies the call (fail-closed): a silently disabled guard is no guard.
[ "${AS_INPUT_GUARD:-on}" = "off" ] && exit 0
DIR=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd) || exit 0
. "$DIR/as_lib.sh"
INPUT=$(cat)
as_is_critic_call "$INPUT" || exit 0
if ! PY=$(as_find_python); then
  as_deny_json "anti-sycophancy: страж входа недоступен — не найден Python 3.6+. Критики не запускаются, пока его нет: проверь черновик сам по тому же чек-листу и одной строкой скажи пользователю, что контур критиков не отработал."
  exit 0
fi
OUT=$(printf '%s' "$INPUT" | "$PY" "$DIR/as_input_guard.py" 2>/dev/null)
RC=$?
if [ "$RC" -ne 0 ]; then
  as_deny_json "anti-sycophancy: страж входа завершился с ошибкой (код $RC). Передай черновик inline в фенсах и повтори вызов; если отказ повторяется — сообщи владельцу."
  exit 0
fi
[ -n "$OUT" ] && printf '%s' "$OUT"
exit 0

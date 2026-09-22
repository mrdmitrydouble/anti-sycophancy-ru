# shellcheck shell=sh
# Shared helpers for the anti-sycophancy hook wrappers. POSIX sh.

# Print the path of a Python >= 3.6 interpreter, or fail.
as_find_python() {
  for c in python3 python; do
    if command -v "$c" >/dev/null 2>&1 &&
       "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 6) else 1)' >/dev/null 2>&1; then
      command -v "$c"
      return 0
    fi
  done
  return 1
}

# Regex alternation of the critic agent names (plus names from AS_GUARD_EXTRA_AGENTS="name=type,...").
as_critic_pattern() {
  pat='(anti-sycophancy:)?as-(critic-blind|guardian|solo-guardian|safety)'
  extras=$(printf '%s' "${AS_GUARD_EXTRA_AGENTS:-}" | tr ',; ' '\n\n\n' |
           sed -n 's/^\([A-Za-z0-9_.:-][A-Za-z0-9_.:-]*\)=.*/\1/p' | paste -sd'|' -)
  if [ -n "$extras" ]; then
    pat="$pat|$extras"
  fi
  printf '%s' "$pat"
}

# Is the hook payload ($1, raw JSON) a call of one of the critics?
as_is_critic_call() {
  printf '%s' "$1" | grep -Eq "\"subagent_type\"[[:space:]]*:[[:space:]]*\"($(as_critic_pattern))\""
}

# PreToolUse deny with a reason ($1 must not contain double quotes or backslashes).
as_deny_json() {
  printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"%s"}}' "$1"
}

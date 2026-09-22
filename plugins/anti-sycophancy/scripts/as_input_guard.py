# -*- coding: utf-8 -*-
"""anti-sycophancy input guard - PreToolUse hook on the subagent tool (Agent / Task).

Refuses to start a critic subagent whose input breaks its template - above all, when the
draft is passed as a file path or a reference instead of inline text. Critics have no
tools: a path is an empty input, and an empty input has produced invented verdicts.

Contract: reads the hook payload (JSON) on stdin. Prints nothing (= no objection, the normal
permission flow continues) or a PreToolUse "deny" decision with an actionable reason.
It never prints "allow". Any internal error on a critic call -> deny (fail-closed).
Calls to any other subagent are ignored.
"""
from __future__ import print_function, unicode_literals

import io
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import as_protocol as P  # noqa: E402

MAX_TYPE_LINE = 300

# Paths, URLs and "see the file" references - only checked OUTSIDE the data fences.
_PATH_RE = re.compile(
    r"(?:^|(?<=[\s\"'(«\[<]))"
    r"(?:"
    r"~/[^\s\"'»)\]>]+"
    r"|\.{1,2}/[^\s\"'»)\]>]+"
    r"|/(?:[^\s/\"'»)\]>]+/)+[^\s/\"'»)\]>]*"
    r"|[A-Za-z]:\\[^\s\"'»)\]>]+"
    r"|https?://[^\s\"'»)\]>]+"
    r"|file://[^\s\"'»)\]>]+"
    r")",
    re.MULTILINE,
)
_REF_RE = re.compile(
    r"(?:\bсм\.?\s*(?:в\s+)?(?:файл|раздел|вложени|приложени|документ)"
    r"|\b(?:прочитай|прочти|открой)\s+(?:этот\s+|тот\s+)?(?:файл|документ|раздел)"
    r"|\b(?:see|read|open)\s+(?:the\s+)?(?:attached\s+)?(?:file|document|section)\b"
    r"|\battached\s+(?:file|document)\b"
    r"|@[^\s\"'»]+\.(?:md|txt|json|jsonl|ya?ml|html?|pdf|docx?|csv)\b)",
    re.IGNORECASE,
)


def _fix_hint(ctype, agent):
    spec = P.SPECS[ctype]
    quotes = ""
    if spec["quotes"]:
        quotes = " и дословные цитаты в фенсах после «{}»".format(spec["quotes"][0])
    return (
        "Критики работают без инструментов и не читают файлы: путь или ссылка = пустой вход, "
        "а пустой вход уже приводил к выдуманным вердиктам. Исправь вызов: вставь ПОЛНЫЙ "
        "проверяемый текст между \"\"\" после «{draft}»{quotes} — без путей и ссылок на файлы; "
        "если в тексте встречается \"\"\", используй nonce-фенс \"\"\"x7q2 … x7q2\"\"\". "
        "Затем повтори вызов. Шаблон входа — в описании агента {agent}."
    ).format(draft=spec["draft"], quotes=quotes, agent=agent)


def check(prompt, ctype):
    """Return None if the input is acceptable, otherwise a short reason (Russian)."""
    spec = P.SPECS[ctype]
    prompt = prompt or ""
    fences = P.scan_fences(prompt)

    # 1. Template labels present (outside fences).
    missing = [lab for lab in spec["labels"] if P.find_label(prompt, lab, fences) < 0]
    if missing:
        return "нет обязательных заголовков шаблона: {}.".format(
            ", ".join("«{}»".format(m) for m in missing))

    # 2. Draft is a closed, non-empty fence right after its label.
    f, err, excerpt = P.fence_after_label(prompt, spec["draft"], fences)
    if err == "not_fenced":
        return "после «{}» нет текста черновика в фенсах \"\"\"…\"\"\" (вместо него: «{}»).".format(
            spec["draft"], excerpt or "пусто")
    if err == "unclosed":
        return "фенс черновика после «{}» не закрыт.".format(spec["draft"])
    n = P.nonspace_len(f.content(prompt))
    if n < P.min_draft_chars():
        return ("черновик в фенсах пустой или слишком короткий ({} непробельных символов, "
                "нужно не меньше {}).").format(n, P.min_draft_chars())

    # 2b. Verbatim quote blocks (sighted critics) are closed, non-empty fences too.
    for lab in spec["quotes"]:
        qf, qerr, qexcerpt = P.fence_after_label(prompt, lab, fences)
        if qerr == "not_fenced":
            return "после «{}» нет дословных цитат в фенсах (вместо них: «{}»).".format(
                lab, qexcerpt or "пусто")
        if qerr == "unclosed":
            return "фенс с цитатами после «{}» не закрыт.".format(lab)
        if P.nonspace_len(qf.content(prompt)) == 0:
            return "фенс с цитатами после «{}» пустой.".format(lab)

    # 3. No paths / references instead of text, outside the fences.
    outside = P.outside_text(prompt, fences)
    m = _PATH_RE.search(outside) or _REF_RE.search(outside)
    if m:
        return "вне фенсов найдена ссылка вместо текста: «{}».".format(m.group(0)[:80])

    # 4. Blinded critic: the request type is one neutral line.
    if ctype == "blind":
        t_pos = P.find_label(prompt, "ТИП ЗАПРОСА:", fences)
        start = t_pos + len("ТИП ЗАПРОСА:")
        d_pos = P.find_label(prompt, spec["draft"], fences)
        end = d_pos if d_pos > start else len(prompt)
        region = P.outside_text(prompt[start:end], P.scan_fences(prompt[start:end]))
        lines = [ln.strip() for ln in region.splitlines() if ln.strip()]
        lines = [ln for ln in lines if "nonce" not in ln.lower() and ln != "<data>"]
        if not lines:
            return "ТИП ЗАПРОСА пуст."
        if len(lines) > 1:
            return ("ТИП ЗАПРОСА должен быть одной нейтральной строкой (найдено строк: {}); "
                    "не добавляй туда инструкции и пересказ.").format(len(lines))
        if len(lines[0]) > MAX_TYPE_LINE:
            return "ТИП ЗАПРОСА длиннее {} символов ({}).".format(MAX_TYPE_LINE, len(lines[0]))
    return None


def deny(reason):
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }


def decide(payload):
    """Return a deny dict, or None when there is nothing to object to."""
    if (payload or {}).get("tool_name") not in (None, "Agent", "Task"):
        return None
    tool_input = (payload or {}).get("tool_input") or {}
    agent = tool_input.get("subagent_type") or ""
    ctype = P.critic_type(agent)
    if ctype is None:
        return None
    reason = check(tool_input.get("prompt") or "", ctype)
    if reason is None:
        return None
    return deny(
        "anti-sycophancy: вызов критика {agent} отклонён стражем входа — {reason} {fix}".format(
            agent=P.short_name(agent), reason=reason, fix=_fix_hint(ctype, P.short_name(agent))))


def main():
    raw = sys.stdin.buffer.read() if hasattr(sys.stdin, "buffer") else sys.stdin.read()
    try:
        payload = json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else raw)
        result = decide(payload)
    except Exception as exc:  # fail-closed: the shell wrapper only calls us for critic calls
        result = deny("anti-sycophancy: страж входа недоступен ({}: {}). Передай черновик inline "
                      "в фенсах и повтори вызов; если отказ повторяется — сообщи владельцу."
                      .format(type(exc).__name__, str(exc)[:120]))
    if result is not None:
        out = json.dumps(result, ensure_ascii=False)
        if hasattr(sys.stdout, "buffer"):
            sys.stdout.buffer.write(out.encode("utf-8"))
        else:
            sys.stdout.write(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())

# -*- coding: utf-8 -*-
"""anti-sycophancy verdict verifier.

Checks that a critic's reply is a real verdict about the draft it was actually given:
  * a refusal is explicit: СТАТУС ВХОДА: invalid(<reason>) (a valid reply carries no status line -
    measured: a status line in every reply shifted a relational critic's judgement);
  * verdict fields with allowed values only;
  * a last line  ЯКОРЬ: "<first words of the draft>"  that is a verbatim run of the draft's words;
  * no transcript/tool-call artefacts (a sign of an invented file read).

status:  valid   - usable verdict;
         invalid - the critic itself reported an unusable input (a correct refusal, not a verdict);
         void    - the reply cannot be trusted as a verdict about this draft.

Used as a library (verify()), as a CLI, and as the PostToolUse hook (--hook post).
CLI exit code: 0 = valid, 1 = invalid or void, 2 = usage error.
Standard library only; Python 3.6+.
"""
from __future__ import print_function, unicode_literals

import argparse
import io
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import as_protocol as P  # noqa: E402

MIN_ANCHOR_WORDS = 5

_STATUS_RE = re.compile(r"^СТАТУС\s+ВХОДА\s*:\s*(valid|invalid)\b\s*(?:\((.*)\))?", re.I | re.M)
_ANCHOR_RE = re.compile(r"^ЯКОРЬ\s*:\s*(.*)$", re.I | re.M)
_VERDICT_RES = {
    "blind": [("sycophantic", re.compile(
        r"^ВЕРДИКТ\s*:\s*sycophantic\s*=\s*(true|false)(?![\w])", re.I | re.M))],
    "guardian": [("balance", re.compile(
        r"^БАЛАНС\s*:\s*(нарушена|нарушен|ok|n/a)(?![\w/])", re.I | re.M))],
    "solo": [("fairness", re.compile(
        r"^СПРАВЕДЛИВОСТЬ(?:\s+К\s+ОТСУТСТВУЮЩЕМУ)?\s*:\s*(нарушена|нарушен|ok|n/a)(?![\w/])",
        re.I | re.M))],
    "safety": [
        ("verdict", re.compile(r"^ВЕРДИКТ\s*:\s*(escalate|continue)(?![\w])", re.I | re.M)),
        ("type", re.compile(r"^ТИП\s*:\s*(C12-REQ|C12|T[1-9]|нет)(?![\w-])", re.I | re.M)),
    ],
}
_VALUE_MAP = {"нарушен": "violated", "нарушена": "violated", "ok": "ok", "n/a": "n/a",
              "true": True, "false": False}

# Fragments that only a transcript or a tool call produces - never a genuine critic verdict.
_ARTIFACT_RE = re.compile(
    r"<system-reminder>|</?function_calls>|<invoke\b|<parameter\b|antml:|</?tool_(?:use|result)>"
    r"|^\s*\d+\s*→",
    re.I | re.M)

_SECTION_HEADS = ("ФЛАГИ", "ПЕРЕКОС", "АСИММЕТРИЯ", "ОСНОВАНИЕ")
_OTHER_HEADS = ("ПОЧЕМУ ЭТО ВАЖНО", "КАК ПЕРЕПИСАТЬ", "ВЕРОЯТНАЯ ПОЗИЦИЯ", "ВТОРАЯ СТОРОНА",
                "КАК ВЕРНУТЬ", "ДЕЙСТВИЕ", "ЯКОРЬ", "ВЕРДИКТ", "БАЛАНС", "СПРАВЕДЛИВОСТЬ", "ТИП",
                "ВХОД", "СТАТУС ВХОДА")
_QUOTED_RE = re.compile(r"«([^«»]{3,400})»|\"([^\"]{3,400})\"|“([^“”]{3,400})”")
_ELLIPSIS_RE = re.compile(r"\s*(?:…|\.\.\.)\s*")


def clean_output(text):
    """Drop markdown decoration a model may wrap around the strict format."""
    lines = []
    for ln in (text or "").splitlines():
        s = ln.strip()
        if s.startswith("```"):
            continue
        s = s.replace("**", "").replace("__", "").strip("`").strip()
        s = re.sub(r"^(?:[-•>]\s+)", "", s)
        lines.append(s)
    return "\n".join(lines)


def _strip_anchor(value):
    v = (value or "").strip()
    pairs = [('"', '"'), ("«", "»"), ("“", "”"), ("„", "“"), ("'", "'"), ("‘", "’")]
    for a, b in pairs:
        if len(v) >= 2 and v.startswith(a) and v.endswith(b):
            v = v[len(a):-len(b)]
            break
    v = re.sub(r"^(?:…|\.\.\.)\s*", "", v.strip())
    v = re.sub(r"\s*(?:…|\.\.\.)$", "", v)
    return v.strip()


def check_anchor(anchor_raw, draft):
    """Return (ok, reason).

    The anchor must be a run of the draft's own words, in order. Punctuation and quote marks
    are ignored: a critic that cuts the draft inside a quotation often closes the quote, and
    that says nothing about whether it saw the text. An ellipsis may join several runs."""
    anchor = _strip_anchor(anchor_raw)
    if not anchor:
        return False, "пустой ЯКОРЬ"
    draft_w = P.words(draft)
    parts = [p for p in _ELLIPSIS_RE.split(anchor) if p.strip()]
    total = 0
    for part in parts:
        pw = P.words(part)
        if not pw:
            continue
        if not P.contains_words(draft_w, pw):
            return False, "ЯКОРЬ не найден в черновике дословно"
        total += len(pw)
    need = min(MIN_ANCHOR_WORDS, len(draft_w))
    if total < need:
        return False, "ЯКОРЬ слишком короткий ({} слов, нужно не меньше {})".format(total, need)
    return True, ""


def _section_text(cleaned):
    out, on = [], False
    for ln in cleaned.splitlines():
        up = ln.upper()
        if any(up.startswith(h) for h in _SECTION_HEADS):
            on = True
            out.append(ln.split(":", 1)[1] if ":" in ln else "")
            continue
        if any(up.startswith(h) for h in _OTHER_HEADS):
            on = False
            continue
        if on:
            out.append(ln)
    return "\n".join(out)


def quotes_not_in_source(cleaned, source):
    """Quoted fragments in the findings that are not verbatim (word for word) in the draft/quotes."""
    src = P.words(source)
    missing = 0
    for m in _QUOTED_RE.finditer(_section_text(cleaned)):
        frag = next(g for g in m.groups() if g)
        for part in _ELLIPSIS_RE.split(frag):
            pw = P.words(part)
            if len(pw) < 2:
                continue
            if not P.contains_words(src, pw):
                missing += 1
    return missing


def verify(prompt, output, ctype, draft=None):
    """Verify one critic reply. `prompt` is the critic's full input (preferred);
    `draft` may be given instead when the prompt is not available."""
    res = {"agent_type": ctype, "status": "void", "reason": "", "anchor_ok": None,
           "verdict": {}, "warnings": []}
    if ctype not in P.SPECS:
        res["reason"] = "неизвестный тип критика"
        return res
    if draft is None:
        draft = P.extract_draft(prompt or "", ctype)
    cleaned = clean_output(output)
    if not cleaned.strip():
        res["reason"] = "пустой ответ критика"
        return res

    for m in _ARTIFACT_RE.finditer(output or ""):
        if P.norm(m.group(0)) and P.norm(m.group(0)) in P.norm(prompt or draft or ""):
            continue
        res["reason"] = "в ответе — артефакты вызова инструментов/системных тегов (признак выдуманного чтения)"
        return res

    statuses = [(s.lower(), (r or "").strip()) for s, r in _STATUS_RE.findall(cleaned)]
    if len(set(s for s, _ in statuses)) > 1:
        res["reason"] = "противоречивые строки «СТАТУС ВХОДА»"
        return res
    if statuses and statuses[0][0] == "invalid":
        res["status"] = "invalid"
        res["reason"] = statuses[0][1] or "критик сообщил о невалидном входе"
        return res
    # no status line (the normal case) or an explicit "valid": a verdict about the draft is expected

    for field, rx in _VERDICT_RES[ctype]:
        vals = set(v.lower() for v in rx.findall(cleaned))
        if not vals:
            res["reason"] = "нет допустимого значения поля «{}»".format(field)
            return res
        if len(vals) > 1:
            res["reason"] = "противоречивые значения поля «{}»".format(field)
            return res
        v = vals.pop()
        res["verdict"][field] = _VALUE_MAP.get(v, v.upper() if field == "type" and v != "нет" else v)

    anchors = _ANCHOR_RE.findall(cleaned)
    if not anchors:
        res["reason"] = "нет строки «ЯКОРЬ»"
        res["anchor_ok"] = False
        return res
    if draft is None:
        res["reason"] = "во входе критика нет черновика в фенсах — сверять ЯКОРЬ не с чем"
        res["anchor_ok"] = False
        return res
    ok, why = check_anchor(anchors[-1], draft)
    res["anchor_ok"] = ok
    if not ok:
        res["reason"] = why
        return res

    source = (draft or "") + "\n" + "\n".join(P.extract_quotes(prompt or "", ctype))
    if quotes_not_in_source(cleaned, source):
        res["warnings"].append("quote_not_in_draft")
    res["status"] = "valid"
    return res


# --------------------------------------------------------------------------- PostToolUse hook

def response_text(tr):
    """(text, status, tool_uses) from the subagent tool's response object."""
    if tr is None:
        return "", None, None
    if isinstance(tr, str):
        return tr, None, None
    if isinstance(tr, list):
        return "\n".join(b.get("text", "") for b in tr if isinstance(b, dict)), None, None
    if isinstance(tr, dict):
        content = tr.get("content")
        if isinstance(content, list):
            text = "\n".join(b.get("text", "") for b in content
                             if isinstance(b, dict) and b.get("type", "text") == "text")
        elif isinstance(content, str):
            text = content
        else:
            text = tr.get("result") or tr.get("output") or ""
        return text, tr.get("status"), tr.get("totalToolUseCount")
    return "", None, None


def _summary(res):
    v = res["verdict"]
    return ", ".join("{}={}".format(k, str(x).lower() if isinstance(x, bool) else x)
                     for k, x in v.items())


def post_hook(payload):
    payload = payload or {}
    if payload.get("tool_name") not in ("Agent", "Task"):
        return None
    ti = payload.get("tool_input") or {}
    agent = ti.get("subagent_type") or ""
    ctype = P.critic_type(agent)
    if ctype is None or ti.get("run_in_background"):
        return None
    tr = payload.get("tool_response")
    text, status, tool_uses = response_text(tr)
    if status and status != "completed":
        return None
    prompt = ti.get("prompt") or (tr.get("prompt") if isinstance(tr, dict) else "") or ""
    res = verify(prompt, text, ctype)
    name = P.short_name(agent)
    desc = (ti.get("description") or "").strip().replace("\n", " ")[:80]
    if desc:
        name = "{} («{}»)".format(name, desc)  # parallel calls: tell the caller which call this is
    blind_note = ""
    if isinstance(tool_uses, int) and tool_uses > 0:
        blind_note = (" ВНИМАНИЕ: критик вызвал инструменты ({}) — ослепление нарушено, "
                      "скажи об этом пользователю.").format(tool_uses)
    safety_note = ""
    if ctype == "safety":
        safety_note = (" Для as-safety это равно необоснованному continue: при сработавшем "
                       "кризис-коде T1–T9 держи детерминированный пол.")
    if res["status"] == "valid":
        warn = ""
        if res["warnings"]:
            warn = " Цитаты в находках не все дословны — проверь их по черновику."
        return {"hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": "anti-sycophancy verify: VALID — вердикт {} разобран ({}), "
                                 "ЯКОРЬ совпадает с черновиком.{}{}".format(
                                     name, _summary(res), warn, blind_note)}}
    if res["status"] == "invalid":
        reason = ("anti-sycophancy verify: INPUT INVALID — критик {} сообщил, что вход невалиден "
                  "({}). Вердикта нет, ход не считается проверенным. Исправь вызов (полный текст "
                  "черновика inline в фенсах) и повтори; если повторить нельзя — проверь черновик "
                  "сам по тому же чек-листу и одной строкой скажи пользователю, что контур критиков "
                  "на этом ходе не отработал.{}{}").format(name, res["reason"], safety_note, blind_note)
    else:
        reason = ("anti-sycophancy verify: VERDICT VOID — ответ {} не принят как вердикт: {}. "
                  "Не применяй его и не считай ход проверенным. Перезапусти критика с черновиком "
                  "inline или проверь черновик сам по тому же чек-листу и одной строкой скажи "
                  "пользователю, что контур критиков на этом ходе не отработал.{}{}").format(
                      name, res["reason"], safety_note, blind_note)
    return {"decision": "block", "reason": reason}


# --------------------------------------------------------------------------- CLI

def _read(path):
    with io.open(path, encoding="utf-8") as fh:
        return fh.read()


def _emit(obj):
    out = json.dumps(obj, ensure_ascii=False)
    if hasattr(sys.stdout, "buffer"):
        sys.stdout.buffer.write(out.encode("utf-8"))
        sys.stdout.buffer.write(b"\n")
    else:
        print(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Verify an anti-sycophancy critic reply.")
    ap.add_argument("--hook", choices=["post"], help="run as the PostToolUse hook (payload on stdin)")
    ap.add_argument("--agent", help="critic agent name (as-critic-blind, anti-sycophancy:as-guardian, ...)")
    ap.add_argument("--type", choices=P.TYPES, help="critic type (alternative to --agent)")
    ap.add_argument("--prompt-file", help="the critic's full input")
    ap.add_argument("--draft-file", help="the draft alone (if the full input is not available)")
    ap.add_argument("--output-file", help="the critic's reply")
    args = ap.parse_args(argv)

    if args.hook == "post":
        raw = sys.stdin.buffer.read() if hasattr(sys.stdin, "buffer") else sys.stdin.read()
        try:
            payload = json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else raw)
            out = post_hook(payload)
        except Exception:
            out = None  # verification is advisory here; the input guard is the hard gate
        if out is not None:
            _emit(out)
        return 0

    ctype = args.type or P.critic_type(args.agent)
    if ctype is None or not args.output_file or not (args.prompt_file or args.draft_file):
        ap.print_usage(sys.stderr)
        return 2
    prompt = _read(args.prompt_file) if args.prompt_file else None
    draft = _read(args.draft_file) if args.draft_file else None
    res = verify(prompt, _read(args.output_file), ctype, draft=draft)
    _emit(res)
    return 0 if res["status"] == "valid" else 1


if __name__ == "__main__":
    sys.exit(main())

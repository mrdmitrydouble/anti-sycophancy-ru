# -*- coding: utf-8 -*-
"""anti-sycophancy SubagentStop hook for the critic subagents.

1. Verifies the critic's final reply (as_verify_verdict.verify) against the input it received.
2. If the reply is void (bad format / anchor) although the draft WAS in the input, blocks the stop
   once and tells the critic how to fix the format (one retry; never loops).
3. Appends ONE content-free metric line to <project>/.claude/as-metrics.jsonl:
     {"ts","event":"critic_stop","v","agent","tool_uses","status","anchor_ok","verdict","retried","warnings"}
   - counts, enum labels (e.g. sycophantic=true, balance=violated) and verdict validity; never text.
4. Keeps the plugin's runtime files out of git through the clone-local exclude file
   (.git/info/exclude): no tracked file is touched, nothing to commit, nothing to conflict on.

Other subagents are ignored. Any error -> no output (metrics are best-effort; the input guard
is the hard gate). Standard library only; Python 3.6+.
"""
from __future__ import print_function, unicode_literals

import datetime
import io
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import as_protocol as P  # noqa: E402
import as_verify_verdict as V  # noqa: E402

EXCLUDE_LINES = ["**/.claude/as-metrics.jsonl", "**/.claude/.as-mode"]
EXCLUDE_HEADER = "# anti-sycophancy plugin: local runtime files (added automatically, clone-local)"


def plugin_version():
    here = os.path.dirname(os.path.abspath(__file__))
    try:
        with io.open(os.path.join(here, "..", ".claude-plugin", "plugin.json"), encoding="utf-8") as fh:
            return json.load(fh).get("version")
    except Exception:
        return None


def _text_of(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(b.get("text", "") for b in content
                         if isinstance(b, dict) and b.get("type") == "text")
    return ""


def read_transcript(path):
    """(prompt, final_text, tool_uses) from a subagent transcript (JSONL)."""
    prompt, tool_uses = None, 0
    groups = []  # [(message_id, [text, ...])]
    with io.open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            msg = rec.get("message") or {}
            if rec.get("type") == "user" and prompt is None:
                prompt = _text_of(msg.get("content"))
            elif rec.get("type") == "assistant":
                content = msg.get("content") or []
                if isinstance(content, list):
                    tool_uses += sum(1 for b in content if isinstance(b, dict) and b.get("type") == "tool_use")
                text = _text_of(content)
                mid = msg.get("id") or rec.get("uuid")
                if groups and groups[-1][0] == mid:
                    groups[-1][1].append(text)
                else:
                    groups.append((mid, [text]))
    final = ""
    for mid, texts in reversed(groups):
        joined = "\n".join(t for t in texts if t)
        if joined.strip():
            final = joined
            break
    return prompt or "", final, tool_uses


def transcript_path(payload):
    p = payload.get("agent_transcript_path")
    if p and os.path.isfile(p):
        return p
    main = payload.get("transcript_path")
    agent_id = payload.get("agent_id")
    if main and agent_id and main.endswith(".jsonl"):
        cand = os.path.join(main[:-len(".jsonl")], "subagents", "agent-{}.jsonl".format(agent_id))
        if os.path.isfile(cand):
            return cand
    return None


def agent_name(payload, tpath):
    for key in ("agent_type", "subagent_type", "agentType"):
        if payload.get(key):
            return payload[key]
    if tpath and tpath.endswith(".jsonl"):
        meta = tpath[:-len(".jsonl")] + ".meta.json"
        try:
            with io.open(meta, encoding="utf-8") as fh:
                return json.load(fh).get("agentType")
        except Exception:
            return None
    return None


def _git(project_dir, *args):
    try:
        p = subprocess.Popen(["git", "-C", project_dir] + list(args), stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, universal_newlines=True)
        out, _ = p.communicate(timeout=5)
        return p.returncode, out.strip()
    except Exception:
        return 1, ""


def ensure_git_exclude(project_dir):
    """Add the runtime files to the clone-local exclude file. Returns (added, tracked_files)."""
    rc, inside = _git(project_dir, "rev-parse", "--is-inside-work-tree")
    if rc != 0 or inside != "true":
        return False, []
    rc, rel = _git(project_dir, "rev-parse", "--git-path", "info/exclude")
    if rc != 0 or not rel:
        return False, []
    path = rel if os.path.isabs(rel) else os.path.join(project_dir, rel)
    existing = ""
    try:
        if os.path.isfile(path):
            with io.open(path, encoding="utf-8") as fh:
                existing = fh.read()
    except Exception:
        existing = ""
    have = set(l.strip() for l in existing.splitlines())
    missing = [l for l in EXCLUDE_LINES if l not in have]
    added = False
    if missing:
        try:
            d = os.path.dirname(path)
            if d and not os.path.isdir(d):
                os.makedirs(d)
            with io.open(path, "a", encoding="utf-8") as fh:
                if existing and not existing.endswith("\n"):
                    fh.write("\n")
                if EXCLUDE_HEADER not in have:
                    fh.write(EXCLUDE_HEADER + "\n")
                for l in missing:
                    fh.write(l + "\n")
            added = True
        except Exception:
            return False, []
    tracked = []
    if added:
        for rel_file in (".claude/as-metrics.jsonl", ".claude/.as-mode"):
            rc, _ = _git(project_dir, "ls-files", "--error-unmatch", "--", rel_file)
            if rc == 0:
                tracked.append(rel_file)
    return added, tracked


def write_metric(project_dir, line):
    d = os.path.join(project_dir, ".claude")
    if not os.path.isdir(d):
        os.makedirs(d)
    with io.open(os.path.join(d, "as-metrics.jsonl"), "a", encoding="utf-8") as fh:
        fh.write(json.dumps(line, ensure_ascii=False) + "\n")


RETRY_REASON = (
    "Проверка формата не пройдена: {why}. Перечитай ЧЕРНОВИК между фенсами в своём входе и ответь "
    "заново строго в своём формате, последней строкой — "
    "«ЯКОРЬ: \"<первые 10 слов черновика дословно>\"». Если черновика во входе на самом деле нет, "
    "ответь двумя строками: «СТАТУС ВХОДА: invalid(<причина>)» и прочерк в строке вердикта."
)


def handle(payload, now=None):
    """Return (hook_output_or_None, metric_line_or_None)."""
    tpath = transcript_path(payload)
    agent = agent_name(payload, tpath)
    ctype = P.critic_type(agent)
    if ctype is None:
        return None, None
    prompt, final, tool_uses = ("", "", None)
    if tpath:
        prompt, final, tool_uses = read_transcript(tpath)
    if payload.get("last_assistant_message"):
        final = payload["last_assistant_message"]
    res = V.verify(prompt, final, ctype) if (prompt or final) else None
    retried = bool(payload.get("stop_hook_active"))

    has_draft = P.extract_draft(prompt, ctype) is not None
    if (res is not None and res["status"] == "void" and has_draft and not retried
            and "stop_hook_active" in payload):
        return {"decision": "block", "reason": RETRY_REASON.format(why=res["reason"])}, None

    ts = (now or datetime.datetime.now(datetime.timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")
    line = {
        "ts": ts,
        "event": "critic_stop",
        "v": plugin_version(),
        "agent": P.short_name(agent),
        "tool_uses": tool_uses,
        "status": res["status"] if res else None,
        "anchor_ok": res["anchor_ok"] if res else None,
        "verdict": res["verdict"] if res else {},
        "retried": retried,
        "warnings": res["warnings"] if res else [],
    }
    out = None
    if isinstance(tool_uses, int) and tool_uses > 0:
        out = {"systemMessage": "anti-sycophancy: критик {} вызвал инструменты ({}) — ослепление "
                                "нарушено; его вердикт ненадёжен.".format(P.short_name(agent), tool_uses)}
    return out, line


def main():
    raw = sys.stdin.buffer.read() if hasattr(sys.stdin, "buffer") else sys.stdin.read()
    try:
        payload = json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else raw) or {}
        out, line = handle(payload)
        if line is not None:
            project_dir = os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or ""
            if os.path.isabs(project_dir):
                write_metric(project_dir, line)
                added, tracked = ensure_git_exclude(project_dir)
                if tracked:
                    msg = ("anti-sycophancy: файлы {} отслеживаются git в этом репозитории. Один раз "
                           "выполни: git rm --cached {}").format(", ".join(tracked), " ".join(tracked))
                    out = out or {}
                    out["systemMessage"] = (out.get("systemMessage", "") + " " + msg).strip()
        if out is not None:
            data = json.dumps(out, ensure_ascii=False)
            if hasattr(sys.stdout, "buffer"):
                sys.stdout.buffer.write(data.encode("utf-8"))
            else:
                sys.stdout.write(data)
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())

# -*- coding: utf-8 -*-
"""Shared protocol of the anti-sycophancy critics.

One place that knows the critics' input templates and output formats, used by:
  * as_input_guard.py    - PreToolUse hook: refuses a critic call whose input breaks the template;
  * as_verify_verdict.py - PostToolUse hook + CLI: checks that a critic's reply is a real verdict
                           about the draft it was given (status line, allowed values, verbatim anchor);
  * as_critic_stop.py    - SubagentStop hook: content-free metrics + one format-repair retry.

Standard library only. Python 3.6+ (no 3.10+ syntax).
"""
from __future__ import unicode_literals

import os
import re
import unicodedata

PLUGIN_PREFIX = "anti-sycophancy:"

# Plugin agent name -> critic type.
CRITICS = {
    "as-critic-blind": "blind",
    "as-guardian": "guardian",
    "as-solo-guardian": "solo",
    "as-safety": "safety",
}
TYPES = ("blind", "guardian", "solo", "safety")

# Input templates (labels as written in the agents' "Жёсткие правила входа").
# Matching is case-insensitive and only OUTSIDE the data fences.
SPECS = {
    "blind": {
        "labels": ["ТИП ЗАПРОСА:", "ЧЕРНОВИК:"],
        "draft": "ЧЕРНОВИК:",
        "quotes": [],
    },
    "guardian": {
        "labels": ["КОНТЕКСТ:", "РЕПЛИКИ СТОРОН", "ЧЕРНОВИК:"],
        "draft": "ЧЕРНОВИК:",
        "quotes": ["РЕПЛИКИ СТОРОН"],
    },
    "solo": {
        "labels": ["КОНТЕКСТ:", "НАРРАТИВ ПОЛЬЗОВАТЕЛЯ ОБ ОТСУТСТВУЮЩЕМ", "ЧЕРНОВИК:"],
        "draft": "ЧЕРНОВИК:",
        "quotes": ["НАРРАТИВ ПОЛЬЗОВАТЕЛЯ ОБ ОТСУТСТВУЮЩЕМ"],
    },
    "safety": {
        "labels": ["ХОД ПОЛЬЗОВАТЕЛЯ:", "ЧЕРНОВИК ОТВЕТА AI:", "ПОДОЗРЕНИЕ ГЕЙТА:"],
        "draft": "ЧЕРНОВИК ОТВЕТА AI:",
        "quotes": ["ХОД ПОЛЬЗОВАТЕЛЯ:"],
    },
}

DEFAULT_MIN_DRAFT_CHARS = 40


def min_draft_chars():
    try:
        v = int(os.environ.get("AS_MIN_DRAFT_CHARS", DEFAULT_MIN_DRAFT_CHARS))
        return v if v > 0 else DEFAULT_MIN_DRAFT_CHARS
    except ValueError:
        return DEFAULT_MIN_DRAFT_CHARS


def extra_agents():
    """AS_GUARD_EXTRA_AGENTS="name=type,name=type" - extra (e.g. project-local) critics to guard."""
    out = {}
    raw = os.environ.get("AS_GUARD_EXTRA_AGENTS", "")
    for part in re.split(r"[,;\s]+", raw):
        if "=" not in part:
            continue
        name, typ = part.split("=", 1)
        name, typ = name.strip(), typ.strip().lower()
        if name and typ in TYPES:
            out[name] = typ
    return out


def critic_type(agent_name):
    """Return the critic type for a subagent name, or None if it is not one of our critics.

    Accepts the bare name ("as-critic-blind") or the plugin-namespaced one
    ("anti-sycophancy:as-critic-blind"). A name namespaced by ANOTHER plugin is not ours.
    """
    if not agent_name:
        return None
    name = str(agent_name).strip()
    extras = extra_agents()
    if name in extras:
        return extras[name]
    if name.startswith(PLUGIN_PREFIX):
        name = name[len(PLUGIN_PREFIX):]
    elif ":" in name:
        return None
    return CRITICS.get(name)


def short_name(agent_name):
    name = str(agent_name or "").strip()
    if name.startswith(PLUGIN_PREFIX):
        name = name[len(PLUGIN_PREFIX):]
    return name


# --------------------------------------------------------------------------- fences

_NONCE_RE = re.compile(r"([A-Za-z0-9]{1,8})[ \t]*\r?\n")


class Fence(object):
    __slots__ = ("open_start", "content_start", "content_end", "close_end", "nonce")

    def __init__(self, open_start, content_start, content_end, close_end, nonce):
        self.open_start = open_start
        self.content_start = content_start
        self.content_end = content_end      # None -> unclosed
        self.close_end = close_end          # None -> unclosed
        self.nonce = nonce

    @property
    def closed(self):
        return self.content_end is not None

    def content(self, text):
        if not self.closed:
            return text[self.content_start:]
        return text[self.content_start:self.content_end]


def scan_fences(text):
    """Scan triple-quote data fences left to right.

    A fence opens with three double quotes, optionally followed by a nonce
    (1-8 ASCII letters/digits and a line break), and closes with <nonce> + three
    double quotes. If the nonce candidate has no matching closer, the fence is
    treated as a plain one. An unclosed fence is returned as the last element.
    """
    fences = []
    i = 0
    while True:
        j = text.find('"""', i)
        if j < 0:
            break
        k = j + 3
        candidates = []
        m = _NONCE_RE.match(text, k)
        if m:
            candidates.append((m.group(1), m.end()))
        candidates.append(("", k))
        found = None
        for nonce, cstart in candidates:
            closer = nonce + '"""'
            e = text.find(closer, cstart)
            if e >= 0:
                found = Fence(j, cstart, e, e + len(closer), nonce)
                break
        if found is None:
            fences.append(Fence(j, k, None, None, ""))
            break
        fences.append(found)
        i = found.close_end
    return fences


def _inside(pos, fences):
    for f in fences:
        end = f.close_end if f.closed else float("inf")
        if f.open_start <= pos < end:
            return True
    return False


def find_label(text, label, fences):
    """Position of the first occurrence of `label` outside fences (case-insensitive), or -1."""
    for m in re.finditer(re.escape(label), text, re.IGNORECASE):
        if not _inside(m.start(), fences):
            return m.start()
    return -1


def label_value_start(text, label, pos):
    """Where the value of a label starts: right after the label, or after the ':' that ends
    the label's parenthetical on the same line (e.g. 'РЕПЛИКИ СТОРОН (дословно):')."""
    end = pos + len(label)
    if label.endswith(":"):
        return end
    line_end = text.find("\n", end)
    if line_end < 0:
        line_end = len(text)
    colon = text.find(":", end, line_end)
    return colon + 1 if colon >= 0 else end


def fence_after_label(text, label, fences):
    """Return (fence, error, excerpt).

    error is None on success, otherwise one of:
      'label_missing', 'not_fenced', 'unclosed'.
    excerpt: what stands after the label instead of a fence (for messages).
    """
    pos = find_label(text, label, fences)
    if pos < 0:
        return None, "label_missing", ""
    p = label_value_start(text, label, pos)
    while p < len(text) and text[p] in " \t\r\n":
        p += 1
    for f in fences:
        if f.open_start == p:
            if not f.closed:
                return f, "unclosed", ""
            return f, None, ""
    excerpt = text[p:p + 70].split("\n")[0].strip()
    return None, "not_fenced", excerpt


def outside_text(text, fences):
    """The prompt with every fence (openers, data, closers) replaced by a placeholder."""
    out, i = [], 0
    for f in fences:
        out.append(text[i:f.open_start])
        out.append(" <data> ")
        if not f.closed:
            i = len(text)
            break
        i = f.close_end
    out.append(text[i:])
    return "".join(out)


def extract_draft(prompt, ctype):
    """The draft text a critic was given (content of the fence after the draft label), or None."""
    spec = SPECS.get(ctype)
    if not spec or not prompt:
        return None
    fences = scan_fences(prompt)
    f, err, _ = fence_after_label(prompt, spec["draft"], fences)
    if err is not None or f is None:
        return None
    return f.content(prompt)


def extract_quotes(prompt, ctype):
    """Verbatim quote blocks a sighted critic was given (list of strings)."""
    spec = SPECS.get(ctype)
    if not spec or not prompt:
        return []
    fences = scan_fences(prompt)
    out = []
    for label in spec["quotes"]:
        f, err, _ = fence_after_label(prompt, label, fences)
        if err is None and f is not None:
            out.append(f.content(prompt))
    return out


def nonspace_len(s):
    return len(re.sub(r"\s+", "", s or ""))


# --------------------------------------------------------------------------- normalization

_QUOTE_CHARS = "«»“”„‟″〝〞＂"
_APOS_CHARS = "‘’‚‛′`´"
_DASH_CHARS = "‐‑‒–—―−"
_TRANS = {}
for _c in _QUOTE_CHARS:
    _TRANS[ord(_c)] = '"'
for _c in _APOS_CHARS:
    _TRANS[ord(_c)] = "'"
for _c in _DASH_CHARS:
    _TRANS[ord(_c)] = "-"
_TRANS[ord("ё")] = "е"
_TRANS[ord("Ё")] = "Е"
_TRANS[ord("*")] = None      # markdown emphasis
_TRANS[ord("­")] = None  # soft hyphen


def norm(s):
    """Normalization for verbatim comparison: quotes, apostrophes, dashes, ё, markdown
    emphasis, whitespace and case. Nothing that could make different words equal."""
    s = unicodedata.normalize("NFC", s or "")
    s = s.translate(_TRANS)
    s = re.sub(r"\s+", " ", s)
    return s.strip().casefold()


def words(s):
    """Word tokens after normalization - letters and digits only, punctuation and quotes dropped."""
    return re.findall(r"\w+", norm(s))


def contains_words(haystack_words, needle_words):
    """True if needle_words occur in haystack_words as one contiguous run."""
    n = len(needle_words)
    if n == 0:
        return False
    first = needle_words[0]
    for i in range(len(haystack_words) - n + 1):
        if haystack_words[i] == first and haystack_words[i:i + n] == needle_words:
            return True
    return False

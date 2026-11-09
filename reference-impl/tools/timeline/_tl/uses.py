"""`uses` extractor for clip programs (PSM 6.5; SEM-6, TV-15). Stdlib, no JS engine.

Clip programs reach components only through TL.component("<ref>") with one string literal without escapes.
"""
from __future__ import annotations

import re

REGEX_PREV = set("(,=:[!&|?{};")
TOKEN_RE = re.compile(r"\bTL\s*\.\s*component\b")
BRACKET_RE = re.compile(r"\bTL\s*\[")
CALL_RE = re.compile(r"\s*\(\s*")


def mask(src: str) -> str:
    """Comments and string/template/regex contents replaced by spaces (newlines kept); quotes kept."""
    out = list(src)
    i, n = 0, len(src)
    last_sig = "\n"  # last significant (non-space) code character; line start counts as regex-allowed

    def blank(a: int, b: int):
        for k in range(a, b):
            if out[k] != "\n":
                out[k] = " "

    while i < n:
        ch = src[i]
        nx = src[i + 1] if i + 1 < n else ""
        if ch == "/" and nx == "/":
            j = src.find("\n", i)
            j = n if j < 0 else j
            blank(i, j)
            i = j
            continue
        if ch == "/" and nx == "*":
            j = src.find("*/", i + 2)
            j = n if j < 0 else j + 2
            blank(i, j)
            i = j
            continue
        if ch in ("'", '"', "`"):
            j = i + 1
            while j < n and src[j] != ch:
                if src[j] == "\\":
                    j += 1
                elif src[j] == "\n" and ch != "`":
                    break
                j += 1
            blank(i + 1, min(j, n))
            i = j + 1
            last_sig = ch
            continue
        if ch == "/" and (last_sig in REGEX_PREV or last_sig == "\n"):
            j = i + 1
            in_class = False
            while j < n and src[j] != "\n":
                c = src[j]
                if c == "\\":
                    j += 2
                    continue
                if c == "[":
                    in_class = True
                elif c == "]":
                    in_class = False
                elif c == "/" and not in_class:
                    break
                j += 1
            blank(i + 1, min(j, n))
            i = j + 1
            last_sig = "/"
            continue
        if ch == "\n":
            last_sig = "\n" if last_sig in REGEX_PREV or last_sig == "\n" else last_sig
        elif not ch.isspace():
            last_sig = ch
        i += 1
    return "".join(out)


def _line_col(src: str, pos: int) -> tuple[int, int]:
    line = src.count("\n", 0, pos) + 1
    col = pos - (src.rfind("\n", 0, pos) + 1) + 1
    return line, col


def extract(src: str) -> tuple[list[str], list[str]]:
    """(sorted unique refs, problems 'not statically resolvable at L:C')."""
    m = mask(src)
    refs, problems = set(), []
    for t in TOKEN_RE.finditer(m):
        pos = t.end()
        c = CALL_RE.match(m, pos)
        ok = False
        if c and m[c.end() - 1] == "(":
            q = c.end()
            if q < len(src) and src[q] in ("'", '"'):
                end = src.find(src[q], q + 1)
                lit = src[q + 1:end] if end > 0 else None
                if lit is not None and "\\" not in lit and "\n" not in lit:
                    after = re.match(r"\s*\)", m[end + 1:])
                    if after:
                        refs.add(lit)
                        ok = True
        if not ok:
            ln, col = _line_col(src, t.start())
            problems.append(f"component reference not statically resolvable at {ln}:{col}")
    for b in BRACKET_RE.finditer(m):
        ln, col = _line_col(src, b.start())
        problems.append(f"component reference not statically resolvable at {ln}:{col}")
    return sorted(refs), problems

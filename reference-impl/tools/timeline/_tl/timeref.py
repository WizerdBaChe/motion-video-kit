"""TimeRef and dur grammar (PSM 4.2)."""
from __future__ import annotations

import re
from dataclasses import dataclass

ANCHOR_RE = re.compile(r"^(line:(L[0-9]{1,3})\.(start|end)|clip:([A-Z][A-Za-z0-9-]{0,15})\.(start|end)|film\.end)$")
TL4_ANCHOR_RE = re.compile(r"^(bar|beat|downbeat):[0-9]+$")
LINES_RE = re.compile(r"^(L[0-9]{1,3})-(L[0-9]{1,3})$")


class GrammarError(ValueError):
    """A TimeRef/dur that does not parse; `tl4` marks forms that arrive in TL-4."""

    def __init__(self, message: str, tl4: bool = False):
        super().__init__(message)
        self.tl4 = tl4


@dataclass(frozen=True)
class Anchor:
    kind: str           # "line" | "clip" | "film"
    ref: str | None     # line id, clip id, or None for film.end
    edge: str           # "start" | "end"
    offset: float = 0.0

    def node(self) -> str | None:
        """Anchor-graph node this anchor reads (clips only; lines and film.end are constants)."""
        return f"clip:{self.ref}.{self.edge}" if self.kind == "clip" else None

    def text(self) -> str:
        base = "film.end" if self.kind == "film" else f"{self.kind}:{self.ref}.{self.edge}"
        if self.offset:
            return f"{base}{self.offset:+g}"
        return base


@dataclass(frozen=True)
class Length:
    s: float


@dataclass(frozen=True)
class EndAnchor:
    anchor: Anchor


@dataclass(frozen=True)
class Lines:
    a: str
    b: str
    pad: float = 0.0


def _is_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def parse_anchor(obj) -> Anchor:
    if not isinstance(obj, dict):
        raise GrammarError("an anchor is an object {anchor, offset?}")
    extra = set(obj) - {"anchor", "offset"}
    if extra:
        raise GrammarError(f"unknown key(s) in anchor: {sorted(extra)}")
    a = obj.get("anchor")
    off = obj.get("offset", 0)
    if not isinstance(a, str):
        raise GrammarError("anchor must be a string")
    if not _is_num(off):
        raise GrammarError("anchor offset must be a number")
    if TL4_ANCHOR_RE.match(a):
        raise GrammarError(f"anchor {a}: music-bar anchors arrive in TL-4", tl4=True)
    m = ANCHOR_RE.match(a)
    if not m:
        raise GrammarError(f"anchor {a!r} does not match line:Ln.start|end, clip:ID.start|end or film.end")
    if m.group(2):
        return Anchor("line", m.group(2), m.group(3), float(off))
    if m.group(4):
        return Anchor("clip", m.group(4), m.group(5), float(off))
    return Anchor("film", None, "end", float(off))


def parse_timeref(v):
    """A number >= 0 (film seconds) or an Anchor."""
    if _is_num(v):
        if v < 0:
            raise GrammarError("a time in seconds must be >= 0")
        return float(v)
    if isinstance(v, str):
        raise GrammarError(f"a TimeRef is a number or {{anchor, offset}}, not the string {v!r}")
    return parse_anchor(v)


def parse_dur(v):
    """Length(s) | EndAnchor(Anchor) | Lines(a, b, pad)."""
    if _is_num(v):
        if v <= 0:
            raise GrammarError("dur in seconds must be > 0")
        return Length(float(v))
    if isinstance(v, dict) and "bars" in v:
        raise GrammarError("dur {bars: N} arrives in TL-4", tl4=True)
    if isinstance(v, dict) and "lines" in v:
        extra = set(v) - {"lines", "pad_after"}
        if extra:
            raise GrammarError(f"unknown key(s) in dur: {sorted(extra)}")
        m = LINES_RE.match(v["lines"]) if isinstance(v["lines"], str) else None
        if not m:
            raise GrammarError("dur.lines must look like \"L2-L4\"")
        pad = v.get("pad_after", 0)
        if not _is_num(pad) or pad < 0:
            raise GrammarError("dur.pad_after must be a number >= 0")
        return Lines(m.group(1), m.group(2), float(pad))
    if isinstance(v, dict) and "anchor" in v:
        return EndAnchor(parse_anchor(v))
    raise GrammarError("dur is a number > 0, {anchor, offset?} (end anchor) or {lines: \"La-Lb\", pad_after?}")


def text_of(v) -> str:
    """Human form of an authored at/dur value for the page and the resolved file."""
    if _is_num(v):
        return f"{v:g}"
    if isinstance(v, dict) and "lines" in v:
        pad = v.get("pad_after", 0)
        return f"lines:{v['lines']}" + (f"{pad:+g}" if pad else "")
    if isinstance(v, dict) and "anchor" in v:
        off = v.get("offset", 0)
        return f"{v['anchor']}" + (f"{off:+g}" if off else "")
    return str(v)

"""Is the previous step's product current? (PSM 5.4). tl never runs a missing step itself (design 4)."""
from __future__ import annotations

from pathlib import Path

from .common import NotCurrent, read_json
from .nhash import file_nsha

STATIC_FIELDS = ("timeline_nsha", "clips_nsha", "components_nsha", "rules_sha", "runtime_hash")
RESOLVED_FIELDS = ("timeline_nsha", "lines_nsha", "clips_nsha", "components_nsha", "runtime_hash")


def _need(step: str, film: Path, why: str):
    raise NotCurrent(f"{why}", hint=f"run tl.py {step} {Path(film).as_posix()}")


def load_validate(film: Path):
    p = Path(film) / "build" / "validate.json"
    return read_json(p) if p.is_file() else None


def load_resolved(film: Path):
    p = Path(film) / "build" / "timeline.resolved.json"
    return read_json(p) if p.is_file() else None


def static_ok(film: Path, cur: dict) -> dict:
    """Static validate.json current with 0 static blocking (needed by resolve)."""
    v = load_validate(film)
    if v is None:
        _need("validate --static", film, "build/validate.json is missing")
    vin = v.get("inputs") or {}
    stale = [k for k in STATIC_FIELDS if vin.get(k) != cur.get(k)]
    if stale:
        _need("validate --static", film, f"build/validate.json is stale ({', '.join(stale)} changed)")
    if (v.get("static") or {}).get("summary", {}).get("blocking", 0):
        _need("validate --static", film, "the static validation has blocking rows")
    return v


def resolved_ok(film: Path, cur: dict) -> dict:
    r = load_resolved(film)
    if r is None:
        _need("resolve", film, "build/timeline.resolved.json is missing")
    rin = r.get("inputs") or {}
    stale = [k for k in RESOLVED_FIELDS if rin.get(k) != cur.get(k)]
    if stale:
        _need("resolve", film, f"build/timeline.resolved.json is stale ({', '.join(stale)} changed)")
    return r


def timed_ok(film: Path, cur: dict) -> tuple[dict, dict]:
    """Static current + resolved current + a timed validate.json on this resolved file (any result)."""
    v = static_ok(film, cur)
    r = resolved_ok(film, cur)
    rn = file_nsha(Path(film) / "build" / "timeline.resolved.json")
    if v.get("stage") != "timed" or (v.get("inputs") or {}).get("resolved_nsha") != rn:
        _need("validate --timed", film, "build/validate.json has no timed result for the current resolved file")
    return v, r


def is_valid(film: Path, cur: dict) -> bool:
    try:
        v, _ = timed_ok(film, cur)
    except NotCurrent:
        return False
    return not (v.get("timed") or {}).get("summary", {}).get("blocking", 0)

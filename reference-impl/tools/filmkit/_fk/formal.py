"""Formal-path provenance facts for FK-R-18 / FK-R-19 (~/.claude/references/formal-path-governance-design.md §4.4).

The judge reads no files, so this module gathers the facts: the works item that holds the page (the first ancestor
folder with a state.json), the design-axes mount copied into it (`<item>/inputs/design-axes.md`; without an item,
`<page folder>/../inputs/design-axes.md` or `<page folder>/design-axes.md`), the CURRENT mount sha from the shared
layer's `digest.py check --medium video --json`, the author's opt-out (`mount_design_axes: false` + a why, in the
plan or in state.json) and the last generating made_by row. Nothing here judges pixels.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

DIGEST = Path(os.environ.get("FILMKIT_DIGEST") or Path.home() / ".claude" / "tools" / "design-axes-mount" / "digest.py")
W2_KEYS = ("stage", "at", "lab", "lab_commit", "lab_dirty", "inputs", "mount_sha", "canon_sha", "model", "effort", "cell")
STAMP_KEYS = W2_KEYS + ("actor", "toolbox")
GEN_STAGES = ("open", "generate", "build", "adopt")


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def find_item(start: Path) -> Path | None:
    for d in (start, *start.parents):
        if (d / "state.json").is_file():
            return d
    return None


def current_mount() -> tuple[dict | None, str | None]:
    if not DIGEST.is_file():
        return None, f"the shared layer's digest.py is not at {DIGEST.as_posix()}"
    try:
        r = subprocess.run([sys.executable, "-X", "utf8", str(DIGEST), "check", "--medium", "video", "--json"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
    except (OSError, subprocess.SubprocessError) as e:
        return None, f"digest.py check could not run: {e}"
    lines = [ln for ln in r.stdout.splitlines() if ln.startswith("{")]
    res = json.loads(lines[-1]) if lines else {}
    if r.returncode != 0 or not res.get("ok"):
        return None, res.get("error") or "digest.py check failed (the shared layer's mount is stale)"
    return res, None


def facts(page_dir: Path, plan: dict | None) -> dict:
    page_dir = Path(page_dir).resolve()
    item = find_item(page_dir)
    state = None
    if item:
        try:
            state = json.loads((item / "state.json").read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            state = {"_error": str(e)}
    cands = ([item / "inputs" / "design-axes.md"] if item else []) + [page_dir.parent / "inputs" / "design-axes.md",
                                                                       page_dir / "design-axes.md"]
    axes = next((p for p in cands if p.is_file()), None)
    optout = None
    for src, d in (("film_plan.json", plan or {}), ("state.json", state or {})):
        if d.get("mount_design_axes") is False:
            optout = {"source": src, "why": (d.get("mount_design_axes_why") or "").strip()}
            break
    cur, cur_err = current_mount()
    rows = [r for r in (state or {}).get("made_by") or [] if isinstance(r, dict)]
    gen = next((r for r in reversed(rows) if r.get("stage") in GEN_STAGES), None)
    return {"item": item.as_posix() if item else None, "state_error": (state or {}).get("_error"),
            "axes": axes.as_posix() if axes else None, "axes_sha": _sha(axes) if axes else None,
            "current_mount_sha": (cur or {}).get("mount_sha"), "current_canon_sha": (cur or {}).get("canon_sha"),
            "current_error": cur_err, "optout": optout, "generator": (state or {}).get("generator"),
            "stamp": gen, "stamp_missing": [k for k in STAMP_KEYS if gen is not None and k not in gen]}


def render_provenance(page_dir: Path) -> dict:
    """render.json.provenance: what the render can say about the formal path (nulls when absent)."""
    item = find_item(Path(page_dir).resolve())
    out = {"item": item.as_posix() if item else None, "mount_sha": None, "canon_sha": None, "actor": None,
           "toolbox": None}
    if item is None:
        return out
    try:
        rows = json.loads((item / "state.json").read_text(encoding="utf-8")).get("made_by") or []
    except (OSError, ValueError):
        return out
    gen = next((r for r in reversed(rows) if isinstance(r, dict) and r.get("stage") in GEN_STAGES), None) or {}
    out.update({k: gen.get(k) for k in ("mount_sha", "canon_sha", "actor", "toolbox")})
    return out

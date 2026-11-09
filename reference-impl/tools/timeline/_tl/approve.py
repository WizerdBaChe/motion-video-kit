"""approve: versions/<n>/ and approval.json (PSM 4.8, 6.10; TV-18; TG-16; Z-7c, Z-8, Z-9)."""
from __future__ import annotations

import json
import os
import shutil
import stat
from pathlib import Path

from . import model as M
from . import state as S
from .common import (MissingRequired, NotCurrent, SpecInvalid, dumps, fault_point, posix, read_json,
                     replace_with_retry, rmtree_force)
from .components import Index
from .nhash import file_nsha, folder_nsha, runtime_hash
from .validate_static import is_product_film, tv9a, tv20

UNDETERMINED_TL0 = ["TV-6", "TV-9b"]


def used_components(obj: dict, validate: dict, index: Index) -> list[str]:
    t = M.tracks(obj)
    refs = set()
    for c in t["picture"] + t["overlay"]:
        if M.freedom(c) == "locked":
            refs.add((c.get("device") or {}).get("component"))
        tin = c.get("transition_in")
        if isinstance(tin, dict):
            refs.add(tin["component"])
    for lst in (validate.get("uses") or {}).values():
        refs.update(lst)
    refs.discard(None)
    out = set()
    for r in refs:
        if index.get(r):
            out.add(r)
            closure, _ = index.requires_closure(r)
            out.update(closure)
    return sorted(out)


def tv18(film: Path, obj: dict, resolved: dict, by: str, questions) -> list[str]:
    """Every missing item, listed (TV-18)."""
    missing = []
    for k in M.REQUIRED_DECISIONS:
        if M.decision(obj, k) is None:
            missing.append(f"decision {k} is unset")
    t = M.tracks(obj)
    for c in t["picture"] + t["overlay"]:
        for f in ("at", "dur", "motion_intent"):
            if f not in c:
                missing.append(f"{c['id']} has no {f}")
    for ln in resolved["lines"]:
        if ln["estimated"]:
            missing.append(f"{ln['id']} duration is estimated ({ln['dur_source']})")
    for c in t["picture"] + t["overlay"]:
        if M.freedom(c) in ("guided", "free") and not (Path(film) / "clips" / f"{c['id']}.js").is_file():
            missing.append(f"{c['id']} ({M.freedom(c)}) has no clip program clips/{c['id']}.js")
    if by == "model":
        for c in t["picture"] + t["overlay"]:
            if "override" in c:
                missing.append(f"{c['id']} carries an override; a model approval cannot pass overrides")
        if questions is None:
            missing.append("--by model needs --questions build/questions.md")
    for r in tv9a(obj, stage="approve", film=Path(film)):
        # A not-found row says what was measured; an unreadable-source row has no measurement, only a reason.
        missing.append(f"TV-9a {r['where']}: {r.get('measured') or r.get('reason')}")
    for r in tv20(obj, stage="approve"):
        if r["bucket"] == "blocking":
            missing.append(f"TV-20 {r['where']}: {r['measured']}")
    return missing


def _materialize(obj: dict) -> dict:
    o = json.loads(json.dumps(obj))
    t = o.get("tracks") or {}
    for c in (t.get("picture") or []) + (t.get("overlay") or []):
        c.setdefault("freedom", "guided")
    return o


def _write(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "wb") as f:
        f.write(text.encode("utf-8"))
        f.flush()
        os.fsync(f.fileno())


def approve(film: Path, *, by: str, note: str | None, questions: str | None, state: dict, obj: dict,
            resolved: dict, validate: dict, index: Index, cur: dict) -> dict:
    film = Path(film)
    d = state.get("draft")
    if not d or d["state"] != "VALID":
        raise NotCurrent(f"approve needs a VALID draft (draft is {d['state'] if d else 'none: inputs equal the last version'})",
                         hint=f"run tl.py validate --static {posix(film)}, then resolve and validate --timed")
    if by == "user" and not (note or "").strip():
        raise SpecInvalid("--by user needs a non-empty --note with the user's words", hint="--note \"<the user's words>\"")
    qpath = None
    if questions is not None:
        qpath = (film / questions) if not Path(questions).is_absolute() else Path(questions)
        try:
            qpath.resolve().relative_to((film / "build").resolve())
            ok = qpath.is_file() and qpath.read_bytes().strip() != b""
        except ValueError:
            ok = False
        if not ok:
            raise SpecInvalid(f"--questions must name an existing non-empty file under build/: {questions}",
                              hint="write build/questions.md first (skill step 0)")
    missing = tv18(film, obj, resolved, by, qpath)
    if missing:
        raise MissingRequired(f"{len(missing)} item(s) missing: " + "; ".join(missing),
                              hint="fill each item, re-validate, then approve", missing=missing)

    n = d["n"]
    vdir = film / "versions"
    tmp = vdir / f"{n}.tmp"
    final = vdir / str(n)
    if final.exists():
        raise SpecInvalid(f"versions/{n}/ already exists", hint="state.json and versions/ disagree; run any command to recover")
    if tmp.exists():
        rmtree_force(tmp)
    tmp.mkdir(parents=True)
    t = M.tracks(obj)
    fp = {"timeline": {"path": "timeline.json", "nsha": None}, "resolved": {"path": "timeline.resolved.json", "nsha": None},
          "clips": [], "components": [], "assets": [], "voice": [], "runtime_hash": runtime_hash()}
    _write(tmp / "timeline.json", json.dumps(_materialize(obj), ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    fp["timeline"]["nsha"] = file_nsha(tmp / "timeline.json")
    shutil.copyfile(film / "build" / "timeline.resolved.json", tmp / "timeline.resolved.json")
    fp["resolved"]["nsha"] = file_nsha(tmp / "timeline.resolved.json")
    for c in t["picture"] + t["overlay"]:
        if M.freedom(c) in ("guided", "free"):
            src = film / "clips" / f"{c['id']}.js"
            dst = tmp / "clips" / f"{c['id']}.js"
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst)
            fp["clips"].append({"id": c["id"], "path": f"clips/{c['id']}.js", "nsha": file_nsha(dst)})
    for ref in used_components(obj, validate, index):
        e = index.get(ref)
        dst = tmp / "components" / e["path"]
        shutil.copytree(index.path_of(ref), dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        fp["components"].append({"ref": ref, "path": f"components/{e['path']}", "dir_nsha": folder_nsha(dst)})
    for a in obj.get("assets") or []:
        fp["assets"].append({"id": a["id"], "path": a["path"], "nsha": file_nsha(film / a["path"])})

    pic = resolved["picture"]
    hard_cuts = [p["id"] for p in pic[1:] if p["transition"]["kind"] == "cut"]
    open_tr = [p["id"] for p in pic[1:] if p["transition"]["kind"] == "open"]
    approval = {
        "schema_version": 1, "generator": "tl", "film_id": film.name, "n": n, "parent": d["parent"],
        "approved_by": by, "note": note if by == "user" else None,
        "questions": {"path": posix(qpath.relative_to(film)) if qpath.is_relative_to(film) else posix(qpath),
                      "nsha": file_nsha(qpath)} if qpath else None,
        "approved_at": S.now(),
        "fingerprint": fp,
        "product_film": is_product_film(obj),
        "pending_confirmation": validate.get("pending_confirmation") or [],
        "hard_cuts": hard_cuts, "open_transitions": open_tr,
        "undetermined": list(UNDETERMINED_TL0),
        "defaults_applied": resolved.get("defaults_applied") or [],
        "source_inputs": S.draft_inputs(cur)}
    _write(tmp / "approval.json", dumps(approval))
    fault_point("approve.after_tmp")
    for p in sorted(tmp.rglob("*")):
        if p.is_file():
            os.chmod(p, stat.S_IREAD)
    replace_with_retry(tmp, final)
    fault_point("approve.after_rename")
    S.transition(state, "approve", by=by, approval_nsha=file_nsha(final / "approval.json"))
    return approval


def line1(film_disp: str, approval: dict) -> str:
    parts = [f"version {approval['n']}"]
    pend = approval.get("pending_confirmation") or []
    if pend:
        parts.append(f"pending your confirmation: {len(pend)} override(s) [{', '.join(p['clip'] for p in pend)}]")
    if approval.get("hard_cuts"):
        parts.append(f"hard cuts: {', '.join(approval['hard_cuts'])}")
    if approval.get("open_transitions"):
        parts.append(f"open transitions now cut: {', '.join(approval['open_transitions'])}")
    if approval.get("undetermined"):
        parts.append(f"not checked yet: {', '.join(approval['undetermined'])}")
    return "; ".join(parts)

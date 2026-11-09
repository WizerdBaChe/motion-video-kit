"""state.json: the draft and the versions; transitions, version integrity, crash recovery (PSM 4.7, 6.9; TL-INV-6)."""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from .common import (FingerprintMismatch, IllegalTransition, NotCurrent, dumps, film_write, posix, read_json,
                     rmtree_force)
from .nhash import file_nsha, folder_nsha

DRAFT_FIELDS = ("timeline_nsha", "clips_nsha", "lines_nsha", "components_nsha")
TERMINAL = ("ABANDONED", "DELIVERED")


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def state_path(film: Path) -> Path:
    return Path(film) / "state.json"


def load_state(film: Path) -> dict:
    p = state_path(film)
    if not p.is_file():
        return {"schema_version": 1, "generator": "tl", "film_id": Path(film).name, "draft": None, "versions": []}
    st = read_json(p)
    st.setdefault("draft", None)
    st.setdefault("versions", [])
    return st


def save_state(film: Path, state: dict) -> None:
    film_write(film, state_path(film), dumps(state))


LAB = Path(__file__).resolve().parents[3]   # tools/timeline/_tl/state.py -> the lab root


def lab_state(lab: Path = LAB) -> dict:
    """The lab commit a film write came from (works contract W-2); dirty = uncommitted lab edits (INV-W2: wip)."""
    import subprocess
    def git(*a):
        r = subprocess.run(["git", "-C", str(lab), *a], capture_output=True, text=True, encoding="utf-8")
        return r.stdout.strip() if r.returncode == 0 else None
    head = git("rev-parse", "HEAD")
    status = git("status", "--porcelain", "--untracked-files=no")
    return {"lab": lab.name, "lab_commit": head, "lab_dirty": bool(status) if status is not None else None}


W2_KEYS = ("stage", "at", "lab", "lab_commit", "lab_dirty", "inputs", "mount_sha", "canon_sha", "model", "effort", "cell")


def stamp(state: dict, stage: str, inputs: dict, cell: str | None = None, run: dict | None = None) -> dict | None:
    """Append one made_by row (append-only; additive key) carrying every W-2 field (W2_KEYS). model, effort,
    mount_sha and canon_sha come from the producing arm's run.json (`run`); a stage no arm produced (resolve,
    approve) records them as null. A row equal to the last one except its time is not repeated, so re-running
    resolve on unchanged inputs and an unchanged lab adds nothing."""
    run = run or {}
    row = {"stage": stage, **lab_state(), "cell": cell, "inputs": dict(inputs),
           "mount_sha": run.get("mount_sha"), "canon_sha": run.get("canon_sha"),
           "model": run.get("model") or run.get("model_requested"), "effort": run.get("effort")}
    if row["lab_dirty"]:
        row["wip"] = True
    rows = state.setdefault("made_by", [])
    if rows and {k: v for k, v in rows[-1].items() if k != "at"} == row:
        return None
    rows.append({"at": now(), **row})
    return rows[-1]


def draft_inputs(cur: dict) -> dict:
    return {k: cur.get(k) for k in DRAFT_FIELDS}


def _hist(entry: dict, st: str, note: str) -> None:
    entry.setdefault("history", []).append({"state": st, "at": now(), "note": note})


def latest_version(state: dict, approved_only: bool = False):
    vs = [v for v in state["versions"] if not approved_only or v["state"] == "APPROVED"]
    return max(vs, key=lambda v: v["n"]) if vs else None


def sync_draft(state: dict, cur: dict) -> list[str]:
    """Bring the draft in line with the working inputs (design 6.4: any change -> DRAFT of version n+1)."""
    notes = []
    di = draft_inputs(cur)
    d = state.get("draft")
    last = latest_version(state)
    if d and d["state"] not in TERMINAL:
        if last and di == last.get("inputs"):
            state["draft"] = None
            notes.append(f"working inputs equal version {last['n']}: no draft")
        elif d.get("inputs") != di:
            d["inputs"] = di
            if d["state"] == "VALID":
                d["state"] = "DRAFT"
                _hist(d, "DRAFT", "inputs changed")
        return notes
    if last and di == last.get("inputs"):
        return notes
    if d and d.get("inputs") == di:
        return notes  # an abandoned draft whose inputs are unchanged stays abandoned
    ns = [v["n"] for v in state["versions"]] + ([d["n"]] if d else [])
    parent = latest_version(state, approved_only=True)
    nd = {"n": (max(ns) + 1) if ns else 1, "parent": parent["n"] if parent else None, "state": "DRAFT",
          "inputs": di, "history": []}
    _hist(nd, "DRAFT", "draft opened")
    state["draft"] = nd
    return notes


def refresh(state: dict, valid: bool) -> None:
    """DRAFT <-> VALID from the currency of validate/resolve products (terminal states never change)."""
    d = state.get("draft")
    if not d or d["state"] in TERMINAL:
        return
    if valid and d["state"] == "DRAFT":
        d["state"] = "VALID"
        _hist(d, "VALID", "static and timed checks current with 0 blocking")
    elif not valid and d["state"] == "VALID":
        d["state"] = "DRAFT"
        _hist(d, "DRAFT", "a check is stale or has blocking rows")


def transition(state: dict, event: str, **info) -> dict:
    """approve | abandon. Raises IllegalTransition / NotCurrent."""
    d = state.get("draft")
    if event == "approve":
        if not d or d["state"] != "VALID":
            raise NotCurrent(f"approve needs a VALID draft (draft is {d['state'] if d else 'none'})",
                             hint="run tl.py validate --static, resolve, validate --timed")
        v = {"n": d["n"], "parent": d["parent"], "state": "APPROVED", "approved_by": info["by"],
             "approval_nsha": info["approval_nsha"], "inputs": d["inputs"], "history": list(d.get("history", []))}
        _hist(v, "APPROVED", f"approved by {info['by']}")
        state["versions"].append(v)
        state["versions"].sort(key=lambda x: x["n"])
        state["draft"] = None
        return state
    if event == "abandon":
        n = info.get("version")
        note = info.get("note") or ""
        if n is None:
            if not d:
                raise IllegalTransition("there is no draft to abandon", hint="name a version with --version n")
            if d["state"] in TERMINAL:
                raise IllegalTransition(f"draft {d['n']} is {d['state']}; abandon is not allowed from a terminal state",
                                        hint="terminal states never change")
            d["state"] = "ABANDONED"
            _hist(d, "ABANDONED", note)
            return state
        v = next((x for x in state["versions"] if x["n"] == n), None)
        if v is None:
            raise IllegalTransition(f"version {n} does not exist", hint="see state.json versions")
        if v["state"] in TERMINAL:
            raise IllegalTransition(f"version {n} is {v['state']}; abandon is not allowed from a terminal state",
                                    hint="terminal states never change")
        v["state"] = "ABANDONED"
        _hist(v, "ABANDONED", note)
        return state
    raise IllegalTransition(f"unknown event {event}")


# ---------------------------------------------------------------- version integrity (TL-INV-6)
def approval_mismatch(folder: Path, approval: dict) -> str | None:
    """First fingerprinted file of versions/<n>/ that no longer matches approval.json, or None."""
    fp = approval.get("fingerprint") or {}
    items = []
    for key in ("timeline", "resolved"):
        if fp.get(key):
            items.append((fp[key]["path"], fp[key]["nsha"], False))
    for c in fp.get("clips") or []:
        items.append((c["path"], c["nsha"], False))
    for c in fp.get("components") or []:
        items.append((c["path"], c["dir_nsha"], True))
    for c in fp.get("voice") or []:
        items.append((c["path"], c["nsha"], False))
    for rel, h, is_dir in items:
        p = Path(folder) / rel
        try:
            got = folder_nsha(p) if is_dir else file_nsha(p)
        except Exception:
            got = None
        if got != h:
            return rel
    return None


def verify_versions(film: Path, state: dict) -> None:
    for v in state["versions"]:
        if v["state"] == "ABANDONED":
            continue
        folder = Path(film) / "versions" / str(v["n"])
        ap = folder / "approval.json"
        hint = f"restore versions/{v['n']}/ from git, or mark the version abandoned"
        if not ap.is_file():
            raise FingerprintMismatch(f"versions/{v['n']}/approval.json is missing", hint=hint)
        if file_nsha(ap) != v["approval_nsha"]:
            raise FingerprintMismatch(f"versions/{v['n']}/approval.json differs from state.json", hint=hint)
        bad = approval_mismatch(folder, read_json(ap))
        if bad:
            raise FingerprintMismatch(f"versions/{v['n']}/{bad} differs from its approval fingerprint", hint=hint)


def recover(film: Path, state: dict) -> list[str]:
    """versions/<n>.tmp/ -> deleted; versions/<n>/ unknown to state.json and verifying -> APPROVED (TG-16)."""
    notes = []
    vdir = Path(film) / "versions"
    if not vdir.is_dir():
        return notes
    known = {v["n"] for v in state["versions"]}
    for p in sorted(vdir.iterdir()):
        if p.is_dir() and re.fullmatch(r"[0-9]+\.tmp", p.name):
            rmtree_force(p)
            notes.append(f"removed unfinished approval {posix(p.relative_to(film))}/")
    for p in sorted(vdir.iterdir(), key=lambda q: q.name):
        if not (p.is_dir() and re.fullmatch(r"[0-9]+", p.name)) or int(p.name) in known:
            continue
        n = int(p.name)
        ap = p / "approval.json"
        appr = read_json(ap) if ap.is_file() else None
        if not appr or approval_mismatch(p, appr):
            raise FingerprintMismatch(f"versions/{n}/ is not in state.json and does not verify",
                                      hint=f"restore versions/{n}/ from git, or remove it")
        v = {"n": n, "parent": appr.get("parent"), "state": "APPROVED", "approved_by": appr.get("approved_by"),
             "approval_nsha": file_nsha(ap), "inputs": appr.get("source_inputs"), "history": []}
        _hist(v, "APPROVED", "approval recovered after interruption")
        state["versions"].append(v)
        state["versions"].sort(key=lambda x: x["n"])
        d = state.get("draft")
        if d and d["n"] == n:
            state["draft"] = None
        notes.append(f"approval recovered after interruption: version {n}")
    return notes

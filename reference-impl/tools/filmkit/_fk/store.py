"""RecordStore: one atomic JSON record file with pending/promote bookkeeping (PSM 6.2).

Shared by render.json (here) and transform.json (M3). Nothing here imports capture/encode/mux.
"""
from __future__ import annotations

import copy
from pathlib import Path

from .common import read_json, sha256_file, write_json_atomic

REQUIRED_RENDER_KEYS = ("schema_version", "generator", "run_id", "status")


def render_snapshot(rec: dict, out_meta: dict) -> dict:
    """last_success built from the top level of a render record (Q-3): everything check.py reads about how the
    published file was made."""
    frames = rec.get("frames") or {}
    live = list(frames.get("live_animations") or [])
    prof = rec.get("profile") or {}
    return {
        "output": dict(out_meta),
        "page": rec.get("page"), "audio": rec.get("audio"), "plan": rec.get("plan"), "rules": rec.get("rules"),
        "film_type": rec.get("film_type"), "profile": prof.get("name") if isinstance(prof, dict) else prof,
        "inputs": copy.deepcopy(rec.get("inputs") or []), "inputs_sha256": rec.get("inputs_sha256"),
        "kit_hash": rec.get("kit_hash"), "run_id": rec.get("run_id"),
        "load_report": copy.deepcopy(rec.get("load_report") or {}), "cli": list(rec.get("cli") or []),
        "expected": copy.deepcopy(rec.get("expected") or {}),
        "frames": {"n": frames.get("n"), "live_animations_max": max(live) if live else 0, "live_animations": live,
                   "resample": copy.deepcopy(frames.get("resample") or [])},
    }


def transform_snapshot(rec: dict, out_meta: dict) -> dict:
    """last_success built from the top level of a transform record (M3): what the derived file was made from and how.
    `inputs` / `inputs_sha256` have the same shape as in a render record, so current_inputs() and owner_state rows 3-4
    work on both record kinds (R-8)."""
    return {
        "output": dict(out_meta),
        "op": rec.get("op"), "params": copy.deepcopy(rec.get("params") or {}), "input": copy.deepcopy(rec.get("input") or {}),
        "input_render_record_sha256": rec.get("input_render_record_sha256"),
        "inputs": copy.deepcopy(rec.get("inputs") or []), "inputs_sha256": rec.get("inputs_sha256"),
        "profile": rec.get("profile"), "kit_hash": rec.get("kit_hash"), "run_id": rec.get("run_id"),
        "analysis": copy.deepcopy(rec.get("analysis")), "result": copy.deepcopy(rec.get("result")),
        "cli": list(rec.get("cli") or []),
    }


def snapshot_for(rec: dict):
    """The snapshot function for a record: a transform record carries `op`, a render record does not."""
    return transform_snapshot if (rec or {}).get("op") else render_snapshot


def record_problem(rec: dict | None) -> str | None:
    if rec is None:
        return "no record"
    for k in REQUIRED_RENDER_KEYS:
        if k not in rec:
            return f"record lacks {k}"
    if rec.get("schema_version") != 1:
        return f"record schema_version {rec.get('schema_version')!r} not recognised"
    if rec.get("generator") != "filmkit":
        return "record generator is not filmkit"
    return None


def promote_dict(rec: dict, out_meta: dict, snapshot=None) -> dict:
    new = copy.deepcopy(rec)
    new["last_success"] = (snapshot or snapshot_for(rec))(rec, out_meta)
    new["pending_publish"] = None
    return new


def reconcile_dict(rec: dict, out_path: Path, snapshot=None) -> dict:
    """pending -> last_success when the file at out_path matches {sha256, bytes}; otherwise drop it (Y-2). The
    snapshot function follows the record kind unless one is given."""
    pend = rec.get("pending_publish")
    if not pend:
        return rec
    new = copy.deepcopy(rec)
    out_path = Path(out_path)
    if out_path.is_file() and out_path.stat().st_size == pend.get("bytes") and sha256_file(out_path) == pend.get("sha256"):
        new["last_success"] = (snapshot or snapshot_for(rec))(rec, {"name": out_path.name, "sha256": pend["sha256"],
                                                                    "bytes": pend["bytes"]})
    new["pending_publish"] = None
    return new


class RecordStore:
    def __init__(self, path: Path, retry: dict, snapshot=None):
        self.path = Path(path)
        self.retry = retry
        self.snapshot = snapshot
        self.rec: dict | None = None

    def load(self) -> tuple[dict | None, str | None]:
        rec, err = read_json(self.path)
        if rec is not None:
            err = record_problem(rec)
            if err:
                rec = None
        return rec, err

    def write(self, rec: dict) -> None:
        self.rec = rec
        write_json_atomic(self.path, rec, self.retry)

    def set_pending(self, sha256: str, nbytes: int) -> None:
        rec = copy.deepcopy(self.rec)
        rec["pending_publish"] = {"sha256": sha256, "bytes": nbytes}
        self.write(rec)

    def promote(self, out_meta: dict) -> None:
        rec = promote_dict(self.rec, out_meta, self.snapshot)
        rec["status"] = "done"
        rec["phase"] = "checking"
        self.write(rec)

    def reconcile(self, out_path: Path) -> dict:
        return reconcile_dict(self.rec, out_path, self.snapshot)

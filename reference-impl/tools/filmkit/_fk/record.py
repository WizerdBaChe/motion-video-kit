"""render.json semantics on top of RecordStore; the sole writer of render.json (FK-INV-6, PSM 6.2)."""
from __future__ import annotations

import copy
import os
from datetime import datetime

from .common import RecordWriteError, fault_point, one_line
from .store import RecordStore
from .types import ExpectedSpec, LoadReport, ProfileArgs, RunEvent

PHASE_OF = {"CREATED": "load", "LOADING": "load", "CAPTURING": "capture", "ENCODING": "encode", "MUXING": "mux",
            "VERIFYING": "verify", "CHECKING": "checking"}
NOTES_CAP = 50


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


class Record:
    def __init__(self, store: RecordStore, previous: dict | None, kit_hash: str, env: dict, run_id: str):
        self.store = store
        self.previous = previous
        self.kit_hash = kit_hash
        self.env = env
        self.run_id = run_id
        self.proc_start = now_iso()
        self.rec: dict = {}
        self._progress_failed = False

    # -- helpers
    def _write(self) -> None:
        self.store.write(self.rec)

    def add_note(self, note: str) -> None:
        notes = self.rec.setdefault("notes", [])
        if note not in notes and len(notes) < NOTES_CAP:
            notes.append(one_line(note, 500))

    def set_timing(self, name: str, seconds: float) -> None:
        self.rec.setdefault("timings_s", {})[name] = round(seconds, 3)

    # -- contract
    def start(self, expected: ExpectedSpec, profile: ProfileArgs, out_name: str, page: str, audio: str | None,
              cli: list[str], *, plan: str | None = None, rules: str | None = None, film_type: str | None = None,
              notes: tuple = (), provenance: dict | None = None) -> None:
        prev_ls = (self.previous or {}).get("last_success")
        self.rec = {
            "schema_version": 1, "generator": "filmkit", "run_id": self.run_id, "pid": os.getpid(),
            "proc_start": self.proc_start, "status": "running", "phase": "load",
            "kind": None, "message": None, "hint": None, "notes": [],
            "output": out_name, "page": page, "audio": audio, "plan": plan, "rules": rules, "film_type": film_type,
            "cli": list(cli),
            "expected": {**expected.to_json(), "source": dict(expected.source)},
            "profile": profile.to_json(),
            "inputs": [], "inputs_sha256": None, "kit_hash": self.kit_hash, "env": dict(self.env),
            "load_report": {}, "frames": {}, "timings_s": {}, "per_frame_ms": None, "progress": {},
            "pending_publish": None, "last_success": copy.deepcopy(prev_ls) if prev_ls else None,
            "provenance": provenance,
        }
        for n in notes:
            self.add_note(n)
        self._write()
        fault_point("after_record_start")

    def event(self, ev: RunEvent) -> None:
        self.rec["phase"] = PHASE_OF.get(ev.state, self.rec.get("phase"))
        if ev.progress:
            self.rec["progress"] = dict(ev.progress)
        self._write()

    def progress(self, frames_done: int, eta_s: float) -> None:
        self.rec["progress"] = {"frames_done": frames_done, "eta_s": round(eta_s)}
        try:
            self._write()
        except RecordWriteError:
            if not self._progress_failed:
                self._progress_failed = True
                self.add_note("progress could not be written to render.json at least once")

    def capture_done(self, inputs: list[dict], inputs_sha: str, frames: dict, load_report: LoadReport) -> None:
        self.rec["inputs"] = inputs
        self.rec["inputs_sha256"] = inputs_sha
        self.rec["frames"] = frames
        self.rec["load_report"] = load_report.to_json()
        self._write()

    def set_pending(self, sha256: str, nbytes: int) -> None:
        self.rec["pending_publish"] = {"sha256": sha256, "bytes": nbytes}
        self._write()

    def promote(self, out_meta: dict) -> None:
        fault_point("promote")
        self.store.rec = self.rec
        self.store.promote(out_meta)
        self.rec = self.store.rec

    def finish(self, phase: str = "complete", notes=()) -> None:
        fault_point("finish")
        for n in notes:
            self.add_note(n)
        self.rec["phase"] = phase
        self._write()

    def fail(self, kind: str, message: str, hint: str) -> None:
        try:
            self.rec["status"] = "interrupted" if kind == "interrupted" else "failed"
            self.rec["kind"] = kind
            self.rec["message"] = one_line(message, 1000)
            self.rec["hint"] = hint
            self.rec["pending_publish"] = None
            if self.rec.get("schema_version"):
                self._write()
        except Exception:
            pass

"""Start decision, OS lock, ownership, input hashes, one-output-per-folder (PSM 6.1, design 7.4 / 7.4b, D20)."""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

from .common import (FK_DIR, Busy, OutputForeign, SpecInvalid, read_json, sha256_bytes, sha256_file,
                     unlink_with_retry, write_json_atomic)
from .store import reconcile_dict, record_problem
from .types import Decision, LoadReport, RenderArgs

IS_WINDOWS = sys.platform == "win32"
if IS_WINDOWS:
    import msvcrt
else:  # unprobed (PSM 6.1); selftest reports the lock controls skipped
    import fcntl


class OutputLock:
    """OS byte lock on byte 0 of <folder>/.filmkit/lock; released by the OS when the holder ends (SG-13)."""

    def __init__(self, folder: Path, retry_s: float = 2.0, step_s: float = 0.05):
        self.folder = Path(folder)
        self.path = self.folder / FK_DIR / "lock"
        self.retry_s = retry_s
        self.step_s = step_s
        self.fd: int | None = None

    def _try(self, fd: int) -> bool:
        try:
            if IS_WINDOWS:
                os.lseek(fd, 0, 0)
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            else:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError:
            return False

    def __enter__(self) -> "OutputLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.path, os.O_RDWR | os.O_CREAT)
        t0 = time.monotonic()
        while not self._try(fd):
            if time.monotonic() - t0 >= self.retry_s:
                os.close(fd)
                raise Busy(f"another filmkit process holds {self.path.parent.as_posix()}", folder=self.path.parent.as_posix())
            time.sleep(self.step_s)
        self.fd = fd
        return self

    def __exit__(self, *exc) -> None:
        if self.fd is None:
            return
        try:
            if IS_WINDOWS:
                os.lseek(self.fd, 0, 0)
                msvcrt.locking(self.fd, msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(self.fd, fcntl.LOCK_UN)
        except OSError:
            pass
        os.close(self.fd)
        self.fd = None


def try_lock_free(folder: Path) -> bool:
    """Acquire-and-release probe. A missing lock file counts as free."""
    if not (Path(folder) / FK_DIR / "lock").exists():
        return True
    try:
        with OutputLock(folder, retry_s=0.0):
            return True
    except Busy:
        return False


def read_record(path: Path) -> tuple[dict | None, str | None]:
    rec, err = read_json(path)
    if rec is not None:
        err = record_problem(rec)
        if err:
            rec = None
    return rec, err


def reconcile(record: dict, out_path: Path) -> dict:
    return reconcile_dict(record, out_path)


def inputs_digest(inputs: list[dict]) -> str:
    return sha256_bytes(b"".join(f"{i['path']}\0{i['sha256']}\n".encode("utf-8") for i in inputs))


def _resolve(page_dir: Path, rel: str) -> Path:
    p = Path(rel)
    return p if p.is_absolute() else page_dir / rel


def current_inputs(page_dir: Path, last_success: dict) -> str | None:
    """Rehash the paths listed in last_success.inputs; None when any is missing (owner_state row 3)."""
    out = []
    for it in last_success.get("inputs") or []:
        p = _resolve(page_dir, it["path"])
        if not p.is_file():
            return None
        out.append({"path": it["path"], "sha256": sha256_file(p)})
    return inputs_digest(out)


def owner_state(record: dict | None, out_path: Path, current_inputs_sha: str | None, lock_held_by_other: bool) -> str:
    """Design 7.4b truth table, top-down. record MUST already be reconciled (Q-3b)."""
    out_path = Path(out_path)
    if not out_path.is_file():
        return "ABSENT"
    ls = (record or {}).get("last_success") or {}
    pend = (record or {}).get("pending_publish") or {}
    sha = sha256_file(out_path)
    if record is None or sha not in {(ls.get("output") or {}).get("sha256"), pend.get("sha256")} - {None}:
        return "FOREIGN"
    if current_inputs_sha is None:
        return "UNDET_INPUTS"
    if current_inputs_sha != ls.get("inputs_sha256"):
        return "STALE"
    if record.get("status") in ("failed", "interrupted"):
        return "STALE"
    if record.get("status") == "running" and lock_held_by_other:
        return "STALE"
    return "CURRENT"


def provenance(record: dict | None, file: Path, record_dir: Path, lock_held_by_other: bool) -> dict:
    """Facts for FK-R-13: owner_state on the reconciled record, the words for the state, and the kit hash the
    published file was made with. record is None when no readable render.json exists."""
    ls = (record or {}).get("last_success") or {}
    cur, missing = None, None
    if record is not None and ls:
        cur = current_inputs(record_dir, ls)
        if cur is None:
            missing = next((i["path"] for i in ls.get("inputs") or [] if not _resolve(record_dir, i["path"]).is_file()), None)
    state = owner_state(record, file, cur, lock_held_by_other)
    why = None
    if state == "FOREIGN":
        why = ("no readable render.json" if record is None
               else "the file's sha256 matches neither last_success nor pending_publish")
    elif state == "UNDET_INPUTS":
        why = f"input file not present: {missing}"
    elif state == "STALE":
        if cur != ls.get("inputs_sha256"):
            why = "inputs changed since the render"
        elif record.get("status") == "failed":
            why = "the last run in this folder failed; the file is from an earlier run"
        elif record.get("status") == "interrupted":
            why = "the last run in this folder was interrupted; the file is from an earlier run"
        else:
            why = "a render is running in this folder"
    return {"state": state, "has_record": record is not None, "why": why, "kit_hash": ls.get("kit_hash"),
            "run_id": ls.get("run_id")}


def transform_record_path(file: Path) -> Path:
    """The record beside a derived file: <name>.transform.json (design 7.4b, PSM 4.6)."""
    file = Path(file)
    return file.with_name(file.name + ".transform.json")


def provenance_derived(trec: dict, file: Path, lock_held_by_other: bool) -> dict:
    """FK-R-13 for a file written by transform.py: the same owner_state table on its reconciled transform record, with
    the source file as the input (R-8). When the source was itself a filmkit render (the record holds its render.json
    hash), the source must still be the output that render.json describes; any broken link is `chain_problem`."""
    folder = Path(file).parent
    ls = (trec or {}).get("last_success") or {}
    cur, missing = None, None
    if ls:
        cur = current_inputs(folder, ls)
        if cur is None:
            missing = next((i["path"] for i in ls.get("inputs") or [] if not _resolve(folder, i["path"]).is_file()), None)
    state = owner_state(trec, file, cur, lock_held_by_other)
    why = None
    if state == "FOREIGN":
        why = "the file's sha256 matches neither last_success nor pending_publish of its transform record"
    elif state == "UNDET_INPUTS":
        why = f"input file not present: {missing}"
    elif state == "STALE":
        if cur != ls.get("inputs_sha256"):
            why = "the source file changed since the transform"
        elif trec.get("status") == "failed":
            why = "the last transform of this file failed; the file is from an earlier run"
        elif trec.get("status") == "interrupted":
            why = "the last transform of this file was interrupted; the file is from an earlier run"
        else:
            why = "a transform is running in this folder"
    chain = None
    if state == "CURRENT" and ls.get("input_render_record_sha256"):
        src = _resolve(folder, (ls.get("inputs") or [{}])[0].get("path", ""))
        rr, _ = read_record(src.parent / "render.json")
        if rr is None:
            chain = "the source file's render.json is missing or unreadable"
        else:
            owned = ((reconcile_dict(rr, src).get("last_success") or {}).get("output") or {}).get("sha256")
            if owned != sha256_file(src):
                chain = "the source file is no longer the output its render.json describes"
    return {"state": state, "has_record": True, "why": why, "kit_hash": ls.get("kit_hash") or trec.get("kit_hash"),
            "run_id": ls.get("run_id"), "derived": {"op": trec.get("op")}, "chain_problem": chain}


def rel_or_abs(page_dir: Path, p: Path) -> str:
    p = Path(p).resolve()
    try:
        return p.relative_to(Path(page_dir).resolve()).as_posix()
    except ValueError:
        return p.as_posix()


def input_hashes(page_dir: Path, page: Path, load_report: LoadReport, audio: Path | None) -> tuple[list[dict], str]:
    paths = set(load_report.local_files)
    paths.add(rel_or_abs(page_dir, page))
    if audio is not None:
        paths.add(rel_or_abs(page_dir, audio))
    out = []
    for rel in sorted(paths, key=lambda s: s.encode("utf-8")):
        p = _resolve(page_dir, rel)
        if p.is_file():
            out.append({"path": rel, "sha256": sha256_file(p)})
    return out, inputs_digest(out)


def write_lock_info(folder: Path, run_id: str, tool: str, proc_start: str = "") -> None:
    write_json_atomic(Path(folder) / FK_DIR / "lock.json",
                      {"pid": os.getpid(), "proc_start": proc_start, "tool": tool, "run_id": run_id,
                       "started_at": time.strftime("%Y-%m-%dT%H:%M:%S")}, None)


def cleanup_on_created(folder: Path, run_id: str, retry: dict | None = None) -> list[str]:
    """Delete stale *.tmp and other runs' partials under .filmkit/ (Q-9, P-25d). Returns notes."""
    notes = []
    fk = Path(folder) / FK_DIR
    if not fk.is_dir():
        return notes
    for p in fk.iterdir():
        if not p.is_file():
            continue
        stale = p.suffix == ".tmp" or ((p.name.endswith(".partial") or p.name.endswith(".video.mp4")) and f".{run_id}." not in p.name)
        if stale and not unlink_with_retry(p, retry):
            notes.append(f"left a locked leftover file: .filmkit/{p.name}")
    return notes


def start_decision(args: RenderArgs, page_dir: Path, out_path: Path) -> Decision:
    """Design 7.4 start table, top-down first match. On CREATED the lock is held and returned in Decision.lock."""
    page_dir = Path(page_dir).resolve()
    out_path = Path(out_path).resolve()
    # row 1: path-level spec errors (flag/plan errors were raised before, also row 1)
    if not Path(args.page).is_file():
        return Decision("REJECTED", "spec_invalid", f"page file not found: {Path(args.page).as_posix()}",
                        "give the path of an existing HTML page")
    if out_path.parent != page_dir:
        return Decision("REJECTED", "spec_invalid",
                        f"output {out_path.as_posix()} is not directly in the page folder {page_dir.as_posix()}",
                        "write -o into the page's own folder; render drafts from a copy of the page in another folder")
    if out_path == Path(args.page).resolve():
        return Decision("REJECTED", "spec_invalid", "output path equals the page path", "choose an .mp4 output name")
    # row 2: lock
    lock = OutputLock(page_dir)
    try:
        lock.__enter__()
    except Busy as e:
        return Decision("REJECTED", "busy", e.message, None)
    notes: list[str] = []
    try:
        # row 3: unreadable record -> treated as none
        rec_path = page_dir / "render.json"
        rec, err = read_record(rec_path)
        if rec is None and rec_path.exists():
            notes.append(f"record unreadable ({err}); treated as no record")
        # row 4: D20 - the record describes another output that still exists
        if rec is not None:
            names = set()
            ls = rec.get("last_success") or {}
            if (ls.get("output") or {}).get("name"):
                names.add(ls["output"]["name"])
            if rec.get("pending_publish") and rec.get("output"):
                names.add(rec["output"])
            for nm in sorted(names):
                if nm != out_path.name and (page_dir / nm).is_file():
                    lock.__exit__(None, None, None)
                    return Decision("REJECTED", "spec_invalid",
                                    f"render.json in {page_dir.as_posix()} already describes another output, {nm}",
                                    "one output per page folder; render drafts or a second version from a copy of the page in another folder",
                                    tuple(notes))
        # row 5: FOREIGN
        if out_path.is_file():
            ls = (rec or {}).get("last_success") or {}
            pend = (rec or {}).get("pending_publish") or {}
            sha = sha256_file(out_path)
            if rec is None or sha not in {(ls.get("output") or {}).get("sha256"), pend.get("sha256")} - {None}:
                lock.__exit__(None, None, None)
                why = "no readable render.json" if rec is None else "its sha256 matches neither last_success nor pending_publish"
                return Decision("REJECTED", "output_foreign",
                                f"{out_path.name} exists and was not written by filmkit here ({why})", None, tuple(notes))
        # row 6: CREATED
        previous = None
        if rec is not None:
            if rec.get("status") == "running":
                notes.append("previous run interrupted")
            previous = reconcile(rec, out_path)
            if rec.get("pending_publish") and previous.get("last_success") != rec.get("last_success"):
                notes.append("previous run published but did not finalise its record; reconciled")
        return Decision("CREATED", None, None, None, tuple(notes), previous, lock)
    except BaseException:
        lock.__exit__(None, None, None)
        raise

"""Transform orchestration for transform.py (M3; design 7.4d, PSM 6.8, FK-INV-17).

A Transform reads one existing video file and writes a NEW file beside a record: `<out>` and `<out>.transform.json`.
It runs only when transform.py is called by name (BR-14); render.py, check.py and checkrun never import this module.

States: REJECTED, CREATED, PROCESSING, VERIFYING, DONE, FAILED(kind), INTERRUPTED. Start rows, top-down, first match
wins: params -> input missing or unreadable -> output-folder lock (the same lock render.py takes) -> `--out` exists
and is not this tool's -> CREATED. Every non-terminal state after CREATED is bound by --timeout and Ctrl-C and ends
FAILED(timeout) / INTERRUPTED without taking the output name. After the rename (publish step 2) nothing can fail the
run any more: it ends DONE (Y-7a). The operations (what ffmpeg does to the audio) live in `_fk/ops/`.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import platform
import secrets
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from . import guard, kinds
from .checkrun import format_rows
from .common import (FK_DIR, Busy, EnvError, EncodeError, FilmkitError, FkArgParser, SpecInvalid, Timeout, VerifyError,
                     fault_point, last_line, one_line, sha256_file)
from .guard import OutputLock
from .manifest import kit_hash
from .ops import OPERATIONS
from .probe import probe
from .profile import get_profile, resolve_profile
from .rerun import describes
from .store import RecordStore
from .summary import audio_desc, five_lines
from .types import ExpectedSpec, ProbeFacts, RunSummary
from .verify import PostPublishError, publish

NOTES_CAP = 50

EPILOG = """examples:
  python -X utf8 kit/filmkit/transform.py normalize build/final.mp4 --out build/final.norm.mp4 --target-lufs -20 --true-peak -2
  python -X utf8 kit/filmkit/transform.py normalize build/final.mp4 --out build/final.norm.mp4 --rules rules.json --target NAME

A transform runs only when you call it by name and always writes a new file next to <out>.transform.json; the input is
never changed and no operation has a default target. stdout is five lines: Done:/Failed:, Steps:, Check:, Look:,
Notes:. Exit codes: 0 published; 1 nothing new published. Run in the foreground."""


@dataclass(frozen=True)
class TransformArgs:
    op: str
    input: Path
    out: Path
    profile: str
    timeout_s: float | None
    json_out: bool
    ns: argparse.Namespace
    argv: tuple = ()


def build_parser():
    p = FkArgParser(prog="transform.py", formatter_class=argparse.RawDescriptionHelpFormatter, epilog=EPILOG,
                    description="Run one explicitly named operation on a video file and write the result as a new file "
                                "with a transform record. The video stream is copied; only the named operation acts.")
    sub = p.add_subparsers(dest="op", metavar="<op>", required=True, help="the operation: " + ", ".join(sorted(OPERATIONS)))
    for name, mod in sorted(OPERATIONS.items()):
        sp = sub.add_parser(name, help=mod.HELP, description=mod.HELP, formatter_class=argparse.RawDescriptionHelpFormatter,
                            epilog=EPILOG)
        sp.add_argument("input", help="the video file to read (never changed)")
        sp.add_argument("--out", required=True, metavar="OUT", help="the new .mp4 to write; must differ from the input")
        mod.add_arguments(sp)
        sp.add_argument("--profile", default="lab-round", metavar="NAME", help="format profile (default lab-round)")
        sp.add_argument("--timeout", type=float, metavar="S", help="seconds for the whole transform (default: profile)")
        sp.add_argument("--json", action="store_true", help="print one JSON document instead of five lines")
    return p


def _emit(lines, as_json, doc):
    if as_json:
        print(json.dumps(doc, ensure_ascii=False))
    else:
        for ln in lines:
            print(ln)
    sys.stdout.flush()


def _env() -> dict:
    try:
        ff = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, timeout=20).stdout.split("\n")[0]
        ffv = ff.split(" ")[2] if ff.startswith("ffmpeg version") else ff
    except Exception:
        ffv = None
    return {"python": platform.python_version(), "ffmpeg": ffv, "os": platform.platform()}


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


class TransformRecord:
    """<out>.transform.json semantics on top of RecordStore; the sole writer of that file (Publishable, Q-13)."""

    def __init__(self, store: RecordStore, previous: dict | None, kit: str, env: dict, run_id: str):
        self.store, self.previous, self.kit, self.env, self.run_id = store, previous, kit, env, run_id
        self.proc_start = _now_iso()
        self.rec: dict = {}

    def _write(self) -> None:
        self.store.write(self.rec)

    def add_note(self, note: str) -> None:
        notes = self.rec.setdefault("notes", [])
        if note not in notes and len(notes) < NOTES_CAP:
            notes.append(one_line(note, 500))

    def start(self, *, op: str, params: dict, src: Path, src_sha: str, rel: str, rr_sha: str | None, out_name: str,
              profile: str, cli: list[str], notes: tuple = ()) -> None:
        prev_ls = (self.previous or {}).get("last_success")
        inputs = [{"path": rel, "sha256": src_sha}]
        self.rec = {
            "schema_version": 1, "generator": "filmkit", "op": op, "params": copy.deepcopy(params),
            "input": {"name": src.name, "path": rel, "sha256": src_sha}, "input_render_record_sha256": rr_sha,
            "inputs": inputs, "inputs_sha256": guard.inputs_digest(inputs),
            "run_id": self.run_id, "pid": os.getpid(), "proc_start": self.proc_start, "status": "running",
            "phase": "created", "kind": None, "message": None, "hint": None, "notes": [],
            "output": out_name, "profile": profile, "cli": list(cli), "analysis": None, "result": None,
            "timings_s": {}, "pending_publish": None, "last_success": copy.deepcopy(prev_ls) if prev_ls else None,
            "kit_hash": self.kit, "env": dict(self.env),
        }
        for n in notes:
            self.add_note(n)
        self._write()

    def event(self, phase: str) -> None:
        self.rec["phase"] = phase
        self._write()

    def set_timing(self, name: str, seconds: float) -> None:
        self.rec.setdefault("timings_s", {})[name] = round(seconds, 3)

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


class TransformJob:
    def __init__(self, args: TransformArgs, out_text: str):
        self.a = args
        self.out_text = out_text
        self.interrupted = False
        self.critical = False
        self.steps: list[tuple[str, bool]] = []
        self.notes: list[str] = []

    # ------------------------------------------------------------ signals
    def _on_signal(self, signum, frame):
        self.interrupted = True
        if not self.critical:
            raise KeyboardInterrupt("Ctrl-C")

    def _install_signals(self):
        signal.signal(signal.SIGINT, self._on_signal)
        if hasattr(signal, "SIGBREAK"):
            signal.signal(signal.SIGBREAK, self._on_signal)

    # ------------------------------------------------------------ outputs
    def _display_dir(self) -> str:
        d = Path(self.out_text).parent.as_posix()
        return "" if d in ("", ".") else d + "/"

    def rejected(self, kind, message, hint, notes=()) -> int:
        msg, h = kinds.render(kind, message, hint)
        st = RunSummary("REJECTED", kind, h, None, None, None, None, None, None, None, (("start", False),),
                        self.out_text, False, message=msg, notes=tuple(notes))
        _emit(five_lines(st, None), self.a.json_out,
              {"status": "rejected", "kind": kind, "message": msg, "hint": h, "exit_code": 1})
        return 1

    def failed(self, rec: TransformRecord | None, kind, message, hint, previous_kept, fields=None) -> int:
        msg, h = kinds.render(kind, message, hint, **(fields or {}))
        if rec is not None:
            rec.fail(kind, msg, h)
        state = "INTERRUPTED" if kind == "interrupted" else "FAILED"
        st = RunSummary(state, kind, h, None, None, None, None, None, None, None, tuple(self.steps), self.out_text,
                        False, message=msg, notes=tuple(self.notes), previous_kept=previous_kept)
        doc = dict(rec.rec) if rec is not None and rec.rec else {"status": "failed", "kind": kind, "message": msg, "hint": h}
        doc.update({"exit_code": 1})
        _emit(five_lines(st, None), self.a.json_out, doc)
        return 1

    def _mark_failed_step(self, kind: str) -> None:
        """Name the step that failed in the Steps: line (start -> process -> verify -> publish)."""
        if kind == "publish":
            if self.steps and self.steps[-1][0] == "verify":
                self.steps[-1] = ("verify", True)
            self.steps.append(("publish", False))
            return
        if self.steps and not self.steps[-1][1]:
            return
        nxt = {None: "start", "process": "verify", "verify": "publish"}
        self.steps.append((nxt.get(self.steps[-1][0] if self.steps else None, "process"), False))

    # ------------------------------------------------------------ start rows
    def run(self) -> int:
        a = self.a
        t_start = time.monotonic()
        out_path, src = a.out.resolve(), a.input.resolve()
        try:
            op = OPERATIONS[a.op]
            prof = get_profile(a.profile)
            timeout_s = a.timeout_s if a.timeout_s is not None else float(prof["timeouts_s"]["transform"])
            deadline = t_start + timeout_s
            rules = None
            rp = getattr(a.ns, "rules", None)
            if rp is not None:
                try:
                    rules = json.loads(Path(rp).read_text(encoding="utf-8"))
                    if not isinstance(rules, dict):
                        raise ValueError("the rules file is not a JSON object")
                except (OSError, ValueError) as e:
                    raise SpecInvalid(f"rules file unusable: {last_line(e)}", hint="give the path of a readable rules JSON")
            # row 1: parameters (no default target anywhere), the output path
            params = op.validate(a.ns, rules)
            if out_path == src or (out_path.exists() and src.exists() and os.path.samefile(out_path, src)):
                raise SpecInvalid("--out is the same file as the input",
                                  hint="a transform never overwrites its input; give a new path for --out")
            if out_path.suffix.lower() != ".mp4":
                raise SpecInvalid(f"--out {out_path.name} is not an .mp4 path", hint="give --out as a new .mp4 path")
            if not out_path.parent.is_dir():
                raise SpecInvalid(f"the folder of --out does not exist: {out_path.parent.as_posix()}",
                                  hint="create the folder yourself, or give --out inside an existing folder")
            # row 2: the input
            for exe in ("ffmpeg", "ffprobe"):
                if shutil.which(exe) is None:
                    raise EnvError(f"{exe} not found on PATH")
            if not src.is_file():
                raise SpecInvalid(f"input file not found: {src.as_posix()}", hint="give the path of an existing video file")
            facts_in = probe(src, deadline)
            if not facts_in.readable:
                raise SpecInvalid(f"input file is not readable: {facts_in.error}",
                                  hint="give a video file ffprobe can read; check it with check.py")
            if hasattr(op, "check_input"):
                op.check_input(params, facts_in)
        except FilmkitError as e:
            return self.rejected(e.kind, e.message, e.hint)
        # row 3: the lock render.py also takes
        lock = OutputLock(out_path.parent)
        try:
            lock.__enter__()
        except Busy as e:
            return self.rejected("busy", e.message, None)
        try:
            # row 4: --out exists and is not this tool's
            trec_path = guard.transform_record_path(out_path)
            prev, err = guard.read_record(trec_path)
            notes: list[str] = []
            if prev is None and trec_path.exists():
                notes.append(f"transform record unreadable ({err}); treated as no record")
            if prev is not None and not prev.get("op"):
                prev = None
            if out_path.is_file():
                ls = (prev or {}).get("last_success") or {}
                pend = (prev or {}).get("pending_publish") or {}
                sha = sha256_file(out_path)
                if prev is None or sha not in {(ls.get("output") or {}).get("sha256"), pend.get("sha256")} - {None}:
                    why = "no readable transform record" if prev is None else "its sha256 matches neither last_success nor pending_publish"
                    return self.rejected("output_foreign",
                                         f"{out_path.name} exists and was not written by filmkit's transform.py here ({why})",
                                         None, tuple(notes))
            previous = None
            if prev is not None:
                if prev.get("status") == "running":
                    notes.append("previous run interrupted")
                previous = guard.reconcile(prev, out_path)
                if prev.get("pending_publish") and previous.get("last_success") != prev.get("last_success"):
                    notes.append("previous run published but did not finalise its record; reconciled")
            return self._created(op, params, prof, facts_in, deadline, timeout_s, previous, notes, src, out_path, trec_path)
        except BaseException as e:      # setup before the guarded body; never a traceback
            kind = "interrupted" if isinstance(e, KeyboardInterrupt) else "internal"
            msg = (str(e) or "Ctrl-C") + ", stopped before publishing" if kind == "interrupted" else last_line(e)
            self._mark_failed_step(kind)
            return self.failed(None, kind, msg, None, out_path.is_file())
        finally:
            lock.__exit__(None, None, None)

    # ------------------------------------------------------------ CREATED .. publish
    def _created(self, op, params, prof, facts_in: ProbeFacts, deadline, timeout_s, previous, notes, src: Path,
                 out_path: Path, trec_path: Path) -> int:
        a = self.a
        retry = prof.get("write_retry")
        run_id = f"{time.strftime('%Y%m%dT%H%M%S')}-{secrets.token_hex(2)}"
        out_dir = out_path.parent
        previous_kept = out_path.is_file()
        self.notes = list(notes) + guard.cleanup_on_created(out_dir, run_id, retry)
        rec = TransformRecord(RecordStore(trec_path, retry), previous, kit_hash(), _env(), run_id)
        guard.write_lock_info(out_dir, run_id, "transform.py", rec.proc_start)
        fk = out_dir / FK_DIR
        partial = fk / f"{out_path.name}.{run_id}.partial"
        self._install_signals()
        stderr_text = ""
        try:
            src_sha = sha256_file(src)
            rr_path = src.parent / "render.json"
            rr, _ = guard.read_record(rr_path)
            rr_sha = sha256_file(rr_path) if rr is not None and describes(guard.reconcile(rr, src), src) else None
            rec.start(op=a.op, params=params, src=src, src_sha=src_sha, rel=guard.rel_or_abs(out_dir, src), rr_sha=rr_sha,
                      out_name=out_path.name, profile=a.profile, cli=list(a.argv), notes=tuple(self.notes))
            fault_point("transform_created")
            self._check_time(deadline, timeout_s, "before processing")
            # ---- PROCESSING
            rec.event("process")
            t0 = time.monotonic()
            self.steps.append(("process", False))
            analysis = {}
            if hasattr(op, "analyse"):
                analysis = op.analyse(src, params, facts_in, deadline)
                rec.rec["analysis"] = analysis
                rec._write()
            fault_point("transform_processing")
            self._check_time(deadline, timeout_s, "while processing")
            frag = op.build_filter({**params, "analysis": analysis}, facts_in)
            fps = int(round(facts_in.fps_avg or float(prof.get("fps_default", 30))))
            pargs = resolve_profile(prof, fps, bool(facts_in.audio), a.profile)
            argv = ["ffmpeg", "-hide_banner", "-nostats", "-y", "-i", str(src), "-map", "0:v:0"]
            if facts_in.audio:
                argv += ["-map", "0:a:0"]
            argv += ["-c:v", "copy", *frag, *pargs.audio_args, *pargs.container_args, "-f", "mp4", str(partial)]
            partial.parent.mkdir(parents=True, exist_ok=True)
            try:
                r = subprocess.run(argv, capture_output=True, timeout=max(0.1, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                raise Timeout(f"ffmpeg did not finish within --timeout {timeout_s:g} s", timeout_s=timeout_s)
            stderr_text = r.stderr.decode("utf-8", "replace")
            if r.returncode != 0:
                tail = one_line(" | ".join([x for x in stderr_text.strip().splitlines() if x.strip()][-4:]) or "no stderr", 400)
                raise EncodeError(f"ffmpeg exited {r.returncode}: {tail}",
                                  hint="ffmpeg stopped; its last stderr lines are quoted above")
            self.steps[-1] = ("process", True)
            rec.set_timing("process", time.monotonic() - t0)
            # ---- VERIFYING
            rec.event("verify")
            t0 = time.monotonic()
            self.steps.append(("verify", False))
            facts_out = self._verify(partial, src, src_sha, facts_in, prof, a.profile, deadline)
            if hasattr(op, "result"):
                res = op.result(partial, params, analysis, stderr_text, deadline)
                rec.rec["result"] = res
                if res.get("note"):
                    self.notes.append(res["note"])
                    rec.add_note(res["note"])
            fault_point("transform_verifying")
            self._check_time(deadline, timeout_s, "before publishing")
            self.critical = True
            fault_point("transform_before_publish")
            publish(partial, out_path, rec, retry)
            self.critical = False
            self.steps[-1] = ("verify", True)
            self.steps.append(("publish", True))
            rec.set_timing("verify", time.monotonic() - t0)
        except PostPublishError as e:
            self.critical = False
            if self.steps and self.steps[-1][0] == "verify":
                self.steps[-1] = ("verify", True)
            self.steps.append(("publish", True))
            self.notes.append("record not finalised; next run reconciles")
            return self._done(rec, out_path, internal_error=str(e))
        except BaseException as e:
            self.critical = False
            if isinstance(e, KeyboardInterrupt) or self.interrupted:
                self._mark_failed_step("interrupted")
                where = str(e) if isinstance(e, KeyboardInterrupt) and str(e) else "Ctrl-C"
                return self.failed(rec, "interrupted", f"{where}, stopped before publishing", None, previous_kept)
            if isinstance(e, FilmkitError):
                fields = dict(e.fields)
                fields.setdefault("timeout_s", timeout_s)
                self._mark_failed_step(e.kind)
                return self.failed(rec, e.kind, e.message, e.hint, previous_kept, fields)
            self._mark_failed_step("internal")
            return self.failed(rec, "internal", last_line(e),
                               f"attach {trec_path.name} to a bug note", previous_kept)
        return self._done(rec, out_path)

    def _check_time(self, deadline: float, timeout_s: float, where: str) -> None:
        if self.interrupted:
            raise KeyboardInterrupt(f"Ctrl-C {where}")
        if time.monotonic() > deadline:
            raise Timeout(f"transform exceeded --timeout {timeout_s:g} s {where}",
                          hint=f"the output name was not taken; raise --timeout (now {timeout_s:g} s)", timeout_s=timeout_s)

    def _honour_signal(self, where: str) -> None:
        if self.interrupted:
            raise KeyboardInterrupt(f"Ctrl-C {where}")

    def _verify(self, partial: Path, src: Path, src_sha: str, fin: ProbeFacts, prof: dict, profile_name: str,
                deadline: float) -> ProbeFacts:
        """Design 7.4d VERIFYING: the partial reads, its format rows carry no blocking row, its video stream equals the
        input's, its length equals the input's within the profile tolerance, and the input is unchanged."""
        fps = int(round(fin.fps_avg or float(prof.get("fps_default", 30))))
        n = fin.n_frames
        spec = ExpectedSpec(duration_s=(n / fps) if n and fps else None, n_frames=n, width=fin.width, height=fin.height,
                            fps=fps, audio_expected=bool(fin.audio), film_type=None,
                            source={"duration_s": "probe", "size": "probe", "audio_expected": "probe"})
        fout, rows = format_rows(partial, spec, profile_name, deadline)
        if not fout.readable:
            raise VerifyError(f"the new file is not readable: {fout.error}", hint=_VERIFY_HINT)
        blocking = [r for r in rows if r["bucket"] == "blocking"]
        if blocking:
            raise VerifyError("the new file's format rows failed: " + "; ".join(
                f"{r['id']} ({r.get('measured')}, expected {r.get('expected')})" for r in blocking), hint=_VERIFY_HINT)
        same = [("codec", fin.video_codec, fout.video_codec), ("pix_fmt", fin.pix_fmt, fout.pix_fmt),
                ("size", f"{fin.width}x{fin.height}", f"{fout.width}x{fout.height}"),
                ("frame count", fin.n_frames, fout.n_frames)]
        bad = [f"{n_}: input {x}, new file {y}" for n_, x, y in same if x != y]
        if bad:
            raise VerifyError("the new file's video stream differs from the input's: " + "; ".join(bad), hint=_VERIFY_HINT)
        tol = float(prof.get("thresholds", {}).get("av_length_tolerance_s", 0.1))
        if fin.video_duration_s is not None and fout.video_duration_s is not None \
                and abs(fin.video_duration_s - fout.video_duration_s) > tol:
            raise VerifyError(f"the new file's length {fout.video_duration_s:.3f} s differs from the input's "
                              f"{fin.video_duration_s:.3f} s by more than {tol:g} s", hint=_VERIFY_HINT)
        if sha256_file(src) != src_sha:
            raise VerifyError("the input file changed while the transform ran", hint=_VERIFY_HINT)
        return fout

    # ------------------------------------------------------------ after the rename: always DONE
    def _done(self, rec: TransformRecord, out_path: Path, internal_error: str | None = None) -> int:
        a = self.a
        try:
            rec.finish("complete", self.notes)
        except BaseException as e:
            internal_error = internal_error or last_line(e)
            if "record not finalised; next run reconciles" not in self.notes:
                self.notes.append("record not finalised; next run reconciles")
        if internal_error:
            self.notes.append(f"internal error after publish: {internal_error}")
        facts = probe(out_path, time.monotonic() + 60)
        trec_name = guard.transform_record_path(out_path).name
        disp = self._display_dir()
        if facts.readable:
            head = (f"Done: {self.out_text} — {facts.video_duration_s or 0:.2f} s, {facts.n_frames} frames, "
                    f"{facts.width}x{facts.height}, {facts.fps_avg or 0:g} fps, {facts.video_codec}/{facts.pix_fmt}, "
                    f"{audio_desc(facts.audio)}")
        else:
            head = f"Done: {self.out_text} — written; the new file could not be read back"
        steps = " -> ".join(n if ok else f"{n} (failed)" for n, ok in self.steps)
        notes = one_line("; ".join(one_line(x, 400) for x in self.notes if x), 1500) if self.notes else "none"
        lines = [one_line(head, 400), f"Steps: {steps}",
                 f"Check: format rows pass and the video stream equals the input's — {disp}{trec_name}",
                 "Look: not needed (the video stream is copied unchanged; pixels not judged by this tool)",
                 f"Notes: {notes}"]
        doc = dict(rec.rec)
        doc.update({"exit_code": 0})
        _emit(lines, a.json_out, doc)
        return 0


_VERIFY_HINT = "the new file did not match the input's video stream or the profile's format; the input is unchanged and no new file was written"


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    as_json = "--json" in argv
    out_text = ""
    try:
        ns = build_parser().parse_args(argv)
        out_text = ns.out
        args = TransformArgs(op=ns.op, input=Path(ns.input), out=Path(ns.out), profile=ns.profile, timeout_s=ns.timeout,
                             json_out=ns.json, ns=ns, argv=tuple(["transform.py"] + argv))
    except FilmkitError as e:
        msg, h = kinds.render(e.kind, e.message, e.hint)
        st = RunSummary("REJECTED", e.kind, h, None, None, None, None, None, None, None, (("start", False),),
                        out_text, False, message=msg)
        _emit(five_lines(st, None), as_json, {"status": "rejected", "kind": e.kind, "message": msg, "hint": h, "exit_code": 1})
        return 1
    return TransformJob(args, out_text).run()

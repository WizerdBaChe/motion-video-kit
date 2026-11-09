"""filmkit render.py: turn a time-driven page into a verified MP4, its render.json, check and contact sheet.

RenderJob, design 7.4: start decision -> CREATED -> LOADING -> CAPTURING -> (MUXING) -> VERIFYING -> publish
-> CHECKING -> DONE; REJECTED / FAILED(kind) / INTERRUPTED before the rename.
"""
from __future__ import annotations

import sys
from pathlib import Path

KIT = Path(__file__).resolve().parent
if str(KIT) not in sys.path:
    sys.path.insert(0, str(KIT))

import argparse
import json
import os
import platform
import random
import secrets
import shutil
import signal
import subprocess
import time
from fractions import Fraction
from importlib import metadata

from _fk import guard, kinds
from _fk.capture import PlaywrightBackend
from _fk.checkrun import CheckArgs, check_run, fallback_rows, output_names
from _fk.common import (FK_DIR, EnvError, FilmkitError, FkArgParser, PageRuntime, RecordWriteError, SpecInvalid,
                        Timeout, fault_point, last_line, one_line, replace_with_retry, sha256_bytes, sha256_file,
                        write_bytes_atomic)
from _fk.encode import open_encoder
from _fk.formal import render_provenance
from _fk.manifest import kit_hash
from _fk.mux import mux
from _fk.profile import get_profile, resolve_profile
from _fk.record import Record
from _fk.report import code_for, summarize
from _fk.spec import FILM_TYPE_RE, build_expected_spec, load_plan, parse_size
from _fk.store import RecordStore
from _fk.summary import audio_desc, exit_code, five_lines
from _fk.types import CheckResult, RenderArgs, RunEvent, RunSummary, SheetResult
from _fk.verify import PostPublishError, publish, verify_partial

EPILOG = """examples:
  python -X utf8 kit/filmkit/render.py build/index.html -o build/final.mp4 --duration 30 --size 1280x720
  python -X utf8 kit/filmkit/render.py build/index.html -o build/final.mp4 --duration 30 --size 1280x720 --audio build/mix.wav
  python -X utf8 kit/filmkit/render.py build/index.html -o build/final.mp4 --plan build/film_plan.json

The page must define window.__setTime(t) (t in seconds) so that the picture depends only on t; window.__ready
(a Promise, true, or false-then-true) is optional. Only files inside the page folder load. The output must sit
directly in the page folder. stdout is always five lines: Done:/Failed:, Steps:, Check:, Look:, Notes:.
Exit codes: 0 published, no blocking row; 2 published with a blocking row; 3 published, some check rows could
not finish; 1 nothing new published (the previous output, if any, is kept and marked stale).
Run in the foreground; give your own command timeout more time than the render needs."""


def build_parser():
    p = FkArgParser(prog="render.py", formatter_class=argparse.RawDescriptionHelpFormatter, epilog=EPILOG,
                    description="Render a time-driven HTML page frame by frame into a verified MP4, then check it.")
    p.add_argument("page", help="the HTML page (defines window.__setTime)")
    p.add_argument("-o", dest="out", required=True, metavar="OUT", help="output .mp4, directly in the page folder")
    p.add_argument("--duration", type=float, metavar="S", help="duration in seconds (required unless --plan gives it)")
    p.add_argument("--size", metavar="WxH", help="frame size, even numbers (required unless --plan gives it)")
    p.add_argument("--fps", type=int, metavar="N", help="frames per second (default: the profile's, 30)")
    p.add_argument("--audio", metavar="F", help="audio file to attach unchanged (implies --audio-expected yes)")
    p.add_argument("--audio-expected", choices=["yes", "no"], help="whether the film should have sound")
    p.add_argument("--plan", metavar="F", help="film_plan.json: expected values (flags win) and declarations")
    p.add_argument("--profile", default="lab-round", metavar="NAME", help="format profile (default lab-round)")
    p.add_argument("--rules", metavar="F", help="rules file (lab side); evaluated and hashed")
    p.add_argument("--film-type", metavar="T", help="film type slug; picks the rules that apply")
    p.add_argument("--target", metavar="NAME", help="loudness target in the --rules file the check compares with (needs --rules)")
    p.add_argument("--timeout", type=float, metavar="S", help="seconds for the whole render (default: profile)")
    p.add_argument("--ready-timeout", type=float, metavar="S", help="seconds to wait for the page to be ready")
    p.add_argument("--check-timeout", type=float, metavar="S", help="seconds for the check after publishing")
    p.add_argument("--keep-frames", action="store_true", help="also keep every frame as PNG under .filmkit/frames/")
    p.add_argument("--start", type=float, default=0.0, metavar="S",
                   help="render a window: frame i shows page time S + i/fps (S >= 0; no --audio; review windows)")
    p.add_argument("--gpu", action="store_true",
                   help="capture on the hardware GPU (high-performance adapter); the renderer is recorded in render.json")
    p.add_argument("--json", action="store_true", help="print one JSON document instead of five lines")
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
    try:
        pwv = metadata.version("playwright")
    except Exception:
        pwv = None
    return {"python": platform.python_version(), "playwright": pwv, "chromium": None, "ffmpeg": ffv,
            "os": platform.platform()}


class RenderJob:
    backend_factory = PlaywrightBackend      # selftest swaps in a fake CaptureBackend (FK-INV-3)

    def __init__(self, args: RenderArgs, out_text: str):
        self.a = args
        self.out_text = out_text
        self.interrupted = False
        self.critical = False
        self.browser_live = False   # a Playwright call may be in flight: a signal only sets the flag
        self.steps: list[tuple[str, bool]] = []
        self.notes: list[str] = []

    # ------------------------------------------------------------ signals
    def _on_signal(self, signum, frame):
        self.interrupted = True
        if not self.critical and not self.browser_live:
            raise KeyboardInterrupt("Ctrl-C")

    def _honour_signal(self, where: str):
        # raising inside a Playwright sync call breaks its event loop (close then hangs or leaks tasks),
        # so a signal received while the browser is live is raised here, between calls
        if self.interrupted:
            raise KeyboardInterrupt(f"Ctrl-C {where}")

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

    def failed(self, rec: Record | None, kind, message, hint, previous_kept, fields=None) -> int:
        msg, h = kinds.render(kind, message, hint, **(fields or {}))
        if rec is not None:
            rec.fail(kind, msg, h)
        state = "INTERRUPTED" if kind == "interrupted" else "FAILED"
        st = RunSummary(state, kind, h, None, None, None, None, None, None, None, tuple(self.steps), self.out_text,
                        False, message=msg, notes=tuple(self.notes), previous_kept=previous_kept)
        doc = dict(rec.rec) if rec is not None and rec.rec else {"status": "failed", "kind": kind, "message": msg, "hint": h}
        doc.update({"check": None, "exit_code": 1})
        _emit(five_lines(st, None), self.a.json_out, doc)
        return 1

    # ------------------------------------------------------------ main
    def run(self) -> int:
        a = self.a
        try:
            prof = get_profile(a.profile)
            plan = None
            if a.plan is not None:
                plan, perr = load_plan(a.plan, int(prof.get("fps_default", 30)))
                if perr:
                    raise SpecInvalid(f"plan unusable: {perr}", hint="fix the plan field named above")
            if a.audio is not None and a.audio_expected is False:
                raise SpecInvalid("--audio given together with --audio-expected no", hint="drop one of the two flags")
            if a.audio is not None and not a.audio.is_file():
                raise SpecInvalid(f"audio file not found: {a.audio.as_posix()}", hint="give the path of an existing audio file")
            if a.fps is not None and not 1 <= a.fps <= 120:
                raise SpecInvalid(f"--fps {a.fps} is outside 1-120", hint="give --fps as an integer 1-120")
            if a.film_type is not None and not FILM_TYPE_RE.match(a.film_type):
                raise SpecInvalid(f"--film-type {a.film_type!r} is not a slug", hint="use lower-case letters, digits and -")
            if a.rules is not None:
                try:
                    json.loads(a.rules.read_text(encoding="utf-8"))
                except (OSError, ValueError) as e:
                    raise SpecInvalid(f"rules file unusable: {last_line(e)}", hint="give the path of a readable rules JSON")
            if a.start_s < 0:
                raise SpecInvalid(f"--start {float(a.start_s):g} is negative", hint="give --start S >= 0")
            if a.start_s > 0 and a.audio is not None:
                raise SpecInvalid("--start given together with --audio",
                                  hint="a window render is silent; drop --audio (review windows are read as frames)")
            if a.target is not None and a.rules is None:
                raise SpecInvalid("--target given without --rules", hint="give --rules <rules file> too, or drop --target")
            flags = argparse.Namespace(duration_s=a.duration_s, size=a.size, fps=a.fps,
                                       audio_expected=True if a.audio is not None else a.audio_expected,
                                       film_type=a.film_type)
            spec = build_expected_spec(flags, plan, "full" if plan else "absent", prof)
            if spec.duration_s is None or spec.width is None:
                missing = [n for n, v in (("--duration", spec.duration_s), ("--size", spec.width)) if v is None]
                raise SpecInvalid(f"missing {' and '.join(missing)}",
                                  hint="give --duration S and --size WxH, or a --plan with expected.duration_s and expected.size")
            if spec.duration_unusable:
                raise SpecInvalid(spec.duration_unusable.split("; ")[0], hint=spec.duration_unusable.split("; ", 1)[-1])
        except SpecInvalid as e:
            return self.rejected("spec_invalid", e.message, e.hint)
        page_dir = a.page.resolve().parent
        out_path = a.out.resolve()
        dec = guard.start_decision(a, page_dir, out_path)
        if dec.result == "REJECTED":
            return self.rejected(dec.kind, dec.message, dec.hint, dec.notes)
        try:
            return self._created(dec, spec, prof, plan, page_dir, out_path)
        except BaseException as e:      # setup before the guarded body (record, env); never a traceback
            kind = "interrupted" if isinstance(e, KeyboardInterrupt) else "internal"
            self._mark_failed_step(kind)
            msg = (str(e) or "Ctrl-C") + ", stopped before publishing" if kind == "interrupted" else last_line(e)
            return self.failed(None, kind, msg, None, out_path.is_file())
        finally:
            dec.lock.__exit__(None, None, None)

    def _created(self, dec, spec, prof, plan, page_dir: Path, out_path: Path) -> int:
        a = self.a
        retry = prof.get("write_retry")
        run_id = f"{time.strftime('%Y%m%dT%H%M%S')}-{secrets.token_hex(2)}"
        t_start = time.monotonic()
        timeout_s = a.timeout_s if a.timeout_s is not None else float(prof["timeouts_s"]["render"])
        deadline = t_start + timeout_s
        ready_timeout = a.ready_timeout_s if a.ready_timeout_s is not None else float(prof["timeouts_s"]["ready"])
        check_timeout = a.check_timeout_s if a.check_timeout_s is not None else float(prof["timeouts_s"]["check"])
        previous_kept = out_path.is_file()
        self.notes = list(dec.notes) + guard.cleanup_on_created(page_dir, run_id, retry)
        if a.start_s > 0:
            self.notes.append(f"window render: frame 0 = page time {float(a.start_s):g} s")
        rec = Record(RecordStore(page_dir / "render.json", retry), dec.previous, kit_hash(), _env(), run_id)
        guard.write_lock_info(page_dir, run_id, "render.py", rec.proc_start)
        audio = a.audio.resolve() if a.audio is not None else None
        pargs = resolve_profile(prof, spec.fps, audio is not None, a.profile)
        fk = page_dir / FK_DIR
        video_partial = fk / f"{out_path.stem}.{run_id}.video.mp4"
        publish_partial = fk / f"{out_path.name}.{run_id}.partial"
        self._install_signals()
        backend = None
        encoder = None
        try:
            try:
                rec.start(spec, pargs, out_path.name, guard.rel_or_abs(page_dir, a.page),
                          guard.rel_or_abs(page_dir, audio) if audio else None, list(a.argv),
                          plan=guard.rel_or_abs(page_dir, a.plan) if a.plan else None,
                          rules=a.rules.resolve().as_posix() if a.rules else None, film_type=a.film_type,
                          notes=tuple(self.notes), provenance=render_provenance(page_dir))
            except RecordWriteError as e:
                return self.failed(None, "internal", e.message, e.hint, previous_kept)
            # ---- environment
            for exe in ("ffmpeg", "ffprobe"):
                if shutil.which(exe) is None:
                    raise EnvError(f"{exe} not found on PATH")
            # ---- LOADING
            rec.event(RunEvent("LOADING", ""))
            t0 = time.monotonic()
            page_sha0 = sha256_file(a.page)
            audio_sha0 = sha256_file(audio) if audio else None
            self.browser_live = True
            backend = self.backend_factory(run_id, os.environ.get("FILMKIT_SELFTEST_PROBE", "shadow"))
            backend.gpu = a.gpu
            backend.open(a.page, spec.width, spec.height)
            self._honour_signal("while starting Chromium")
            rec.env["chromium"] = backend.chromium_version
            rec.env["gpu_requested"] = a.gpu
            rec.env["webgl_renderer"] = getattr(backend, "webgl_renderer", None)
            rec.rec["env"] = dict(rec.env)
            report = backend.load(max(0.5, min(ready_timeout, deadline - time.monotonic())))
            self._honour_signal("while loading the page")
            fonts_ok = sum(1 for f in report.fonts if f.status == "loaded")
            self.steps.append((f"load (fonts {fonts_ok}/{len(report.fonts)})", True))
            rec.set_timing("load", time.monotonic() - t0)
            # ---- CAPTURING
            rec.event(RunEvent("CAPTURING", ""))
            t0 = time.monotonic()
            encoder = open_encoder(pargs, spec.width, spec.height, spec.fps, video_partial)
            n = spec.n_frames
            mid, last = n // 2, n - 1
            frames_t, frames_sha, live = [], [], []
            fams: dict[str, object] = {}
            every = int(prof.get("progress_every_frames", 150))
            drop = os.environ.get("FILMKIT_SELFTEST_DROP_FRAME")
            if a.keep_frames:
                (fk / "frames").mkdir(parents=True, exist_ok=True)

            def sample(t: Fraction):
                for fc in backend.sample_font_families(f"{float(t):.3f}"):
                    fams[fc.family] = fc
            self.steps.append((f"capture {n}", False))
            for i in range(n):
                self._honour_signal(f"at frame {i}")
                if time.monotonic() > deadline:
                    raise Timeout(f"render exceeded --timeout {timeout_s:g} s at frame {i}", timeout_s=timeout_s)
                t = a.start_s + Fraction(i, spec.fps)
                try:
                    backend.seek(t)
                except PageRuntime as e:
                    raise PageRuntime(f"frame {i}: {e.message}")
                if i == 0:
                    sample(t)
                png = backend.snapshot()
                backend.check_errors(f"frame {i}, t={float(t):.6g} s")
                backend.check_requests(f"frame {i}")
                fault_point(f"capture_frame_{i}", ffmpeg_pid=encoder.pid, run_id=run_id)
                if drop is None or int(drop) != i:
                    encoder.write(png)
                frames_t.append(str(t))
                frames_sha.append(sha256_bytes(png))
                live.append(backend.live_animations())
                if a.keep_frames:
                    (fk / "frames" / f"{i:06d}.png").write_bytes(png)
                if i in (mid, last) and i != 0 and not (i == last and last == mid):
                    sample(t)
                if every and (i + 1) % every == 0 and i + 1 < n:
                    el = time.monotonic() - t0
                    rec.progress(i + 1, el / (i + 1) * (n - i - 1))
            fault_point("before_close_stdin", ffmpeg_pid=encoder.pid, run_id=run_id)
            encoder.close_stdin()
            # ---- re-seek sample (FK-R-12): a few frames visited again in a shuffled order while ffmpeg finishes;
            # a page whose frame depends on the order of seeks gives a different hash the second time
            resample: list[dict] = []
            t0r = time.monotonic()
            k = min(int(prof.get("resample_count", 0)), n)
            if k > 0:
                for i in random.Random(run_id).sample(range(n), k):
                    self._honour_signal(f"at re-seek of frame {i}")
                    if time.monotonic() > deadline:
                        raise Timeout(f"render exceeded --timeout {timeout_s:g} s at re-seek of frame {i}", timeout_s=timeout_s)
                    try:
                        backend.seek(a.start_s + Fraction(i, spec.fps))
                    except PageRuntime as e:
                        raise PageRuntime(f"re-seek of frame {i}: {e.message}")
                    again = backend.snapshot()
                    backend.check_errors(f"re-seek of frame {i}")
                    resample.append({"i": i, "match": sha256_bytes(again) == frames_sha[i]})
            rec.set_timing("resample", time.monotonic() - t0r)
            encoder.wait(max(1.0, deadline - time.monotonic()))
            self.steps[-1] = (f"capture {n}", True)
            cap_s = time.monotonic() - t0
            rec.set_timing("capture", cap_s)
            rec.rec["per_frame_ms"] = round(cap_s / n * 1000, 1)
            self.steps.append(("encode", True))
            report.font_families = list(fams.values())
            inputs, inputs_sha = guard.input_hashes(page_dir, a.page, report, audio)
            changed = sha256_file(a.page) != page_sha0 or (audio is not None and sha256_file(audio) != audio_sha0)
            for it in inputs:
                first = backend.first_hashes.get(it["path"])
                if first is not None and first != it["sha256"]:
                    changed = True
            if changed:
                self.notes.append("inputs changed while rendering; rerun to render the current files")
                rec.add_note(self.notes[-1])
            subst = [f.family for f in report.font_families if f.result == "substituted"]
            if subst:
                self.notes.append("font families substituted: " + ", ".join(subst))
            rec.capture_done(inputs, inputs_sha, {"n": n, "t": frames_t, "sha256": frames_sha,
                                                   "live_animations": live, "resample": resample}, report)
            backend.close()
            backend = None
            self.browser_live = False
            self._honour_signal("after capture")
            # ---- MUXING
            if audio is not None:
                rec.event(RunEvent("MUXING", ""))
                t0 = time.monotonic()
                self.steps.append(("mux", False))
                mux(video_partial, audio, pargs, publish_partial, max(1.0, deadline - time.monotonic()))
                self.steps[-1] = ("mux", True)
                rec.set_timing("mux", time.monotonic() - t0)
            else:
                replace_with_retry(video_partial, publish_partial, retry)
            # ---- VERIFYING
            rec.event(RunEvent("VERIFYING", ""))
            t0 = time.monotonic()
            self.steps.append(("verify", False))
            facts = verify_partial(publish_partial, spec, prof)
            if time.monotonic() > deadline:
                raise Timeout(f"render exceeded --timeout {timeout_s:g} s before publishing", timeout_s=timeout_s)
            self.critical = True     # publish steps 1-3 run to completion; a signal is honoured after them
            fault_point("before_set_pending")
            publish(publish_partial, out_path, rec, retry)
            self.critical = False
            self.steps[-1] = ("verify", True)
            rec.set_timing("verify", time.monotonic() - t0)
        except PostPublishError as e:
            self.critical = False
            self.steps[-1] = ("verify", True)
            return self._after_publish(rec, spec, prof, page_dir, out_path, check_timeout,
                                       internal_error=str(e), promote_failed=True)
        except BaseException as e:
            self.critical = False
            if encoder is not None:
                encoder.kill()
            if backend is not None:
                backend.close()
            self.browser_live = False
            if isinstance(e, KeyboardInterrupt) or self.interrupted:
                self._mark_failed_step("interrupted")
                where = str(e) if isinstance(e, KeyboardInterrupt) and str(e) else "Ctrl-C"
                return self.failed(rec, "interrupted", f"{where}, stopped before publishing", None, previous_kept)
            if isinstance(e, FilmkitError):
                fields = dict(e.fields)
                fields.setdefault("ready_timeout_s", ready_timeout)
                fields.setdefault("timeout_s", timeout_s)
                self._mark_failed_step(e.kind)
                return self.failed(rec, e.kind, e.message, e.hint, previous_kept, fields)
            self._mark_failed_step("internal")
            return self.failed(rec, "internal", last_line(e), None, previous_kept)
        return self._after_publish(rec, spec, prof, page_dir, out_path, check_timeout)

    def _mark_failed_step(self, kind: str) -> None:
        if self.steps and not self.steps[-1][1]:
            return
        name = {"env": "start", "page_contract": "load", "asset_load": "load", "not_ready": "load",
                "page_runtime": "load", "encode": "encode", "verify": "verify", "publish": "publish"}.get(kind, "run")
        if self.steps and name == "load":
            name = "capture"
        if not self.steps and name == "run":
            name = "load"
        self.steps.append((name, False))

    # ------------------------------------------------------------ after the rename: always DONE
    def _after_publish(self, rec: Record, spec, prof, page_dir, out_path, check_timeout, internal_error=None,
                       promote_failed=False) -> int:
        a = self.a
        if promote_failed:
            self.notes.append("record not finalised; next run reconciles")
        names = output_names(out_path, "")
        res: CheckResult | None = None
        t0 = time.monotonic()
        if self.interrupted:
            rows = fallback_rows("interrupted")
            res = self._fallback(rows, names, internal_error)
        else:
            try:
                try:
                    rec.event(RunEvent("CHECKING", ""))
                except Exception as e:
                    internal_error = internal_error or last_line(e)
                cargs = CheckArgs(file=out_path, duration_s=spec.duration_s, size=(spec.width, spec.height),
                                  fps=spec.fps, profile=a.profile, audio_expected=spec.audio_expected,
                                  plan=a.plan if a.plan else None, plan_exemptions_only=False,
                                  render_record=page_dir / "render.json", mounted_kit_hash=None, out_prefix="",
                                  rules=a.rules, film_type=a.film_type, check_timeout_s=check_timeout,
                                  json_out=a.json_out, target=a.target)
                res = check_run(cargs, time.monotonic() + check_timeout, internal_error=internal_error,
                                lock_held_by_other=False)
            except KeyboardInterrupt:
                res = self._fallback(fallback_rows("interrupted"), names, internal_error)
            except Exception as e:
                internal_error = internal_error or last_line(e)
                res = self._fallback(fallback_rows(f"check stopped: {last_line(e)}"), names, internal_error)
        try:
            rec.set_timing("check", time.monotonic() - t0)
            rec.finish("complete", self.notes)
        except BaseException as e:
            internal_error = internal_error or last_line(e)
            if res is not None and res.summary.internal_error is None:
                s = res.summary
                s2 = type(s)(s.blocking, s.look, s.undetermined, s.confirmed, s.look_without_exemptions, True,
                             internal_error)
                res = CheckResult(res.rows, s2, code_for(s2), res.outputs, res.sheet, res.check_json, res.notes)
        self.steps += [("check", res is not None and res.check_json is not None), ("sheet", bool(res and res.sheet.ok))]
        pr = (res.check_json or {}).get("probe") if res and res.check_json else None
        pr = pr or {}
        st = RunSummary("DONE", None, None, pr.get("n_frames", spec.n_frames), pr.get("video_duration_s", spec.duration_s),
                        pr.get("width", spec.width), pr.get("height", spec.height), pr.get("video_codec"),
                        pr.get("pix_fmt"), audio_desc(pr.get("audio")) if pr else None, tuple(self.steps),
                        self.out_text, True, notes=tuple(self.notes), fps=pr.get("fps_avg", spec.fps),
                        display_dir=self._display_dir())
        code = exit_code(st, res)
        doc = dict(rec.rec)
        doc.update({"check": res.check_json if res else None, "exit_code": code})
        _emit(five_lines(st, res), a.json_out, doc)
        return code

    def _fallback(self, rows, names, internal_error) -> CheckResult:
        s = summarize(rows, internal_error)
        return CheckResult(rows, s, code_for(s), names, SheetResult(False, None, "check did not run"), None, ())


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    as_json = "--json" in argv
    out_text = ""
    try:
        ns = build_parser().parse_args(argv)
        out_text = ns.out
        size = parse_size(ns.size) if ns.size is not None else None
        args = RenderArgs(page=Path(ns.page), out=Path(ns.out), duration_s=ns.duration, size=size, fps=ns.fps,
                          audio=Path(ns.audio) if ns.audio else None,
                          audio_expected=None if ns.audio_expected is None else ns.audio_expected == "yes",
                          plan=Path(ns.plan) if ns.plan else None, profile=ns.profile,
                          rules=Path(ns.rules) if ns.rules else None, film_type=ns.film_type, timeout_s=ns.timeout,
                          ready_timeout_s=ns.ready_timeout, check_timeout_s=ns.check_timeout,
                          keep_frames=ns.keep_frames, json_out=ns.json, argv=tuple(["render.py"] + argv),
                          target=ns.target, start_s=Fraction(str(ns.start)), gpu=ns.gpu)
    except FilmkitError as e:
        msg, h = kinds.render(e.kind, e.message, e.hint)
        st = RunSummary("REJECTED", e.kind, h, None, None, None, None, None, None, None, (("start", False),),
                        out_text, False, message=msg)
        _emit(five_lines(st, None), as_json, {"status": "rejected", "kind": e.kind, "message": msg, "hint": h, "exit_code": 1})
        return 1
    return RenderJob(args, out_text).run()


if __name__ == "__main__":
    sys.exit(main())

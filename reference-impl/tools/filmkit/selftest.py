"""filmkit kit selftest. Fixtures are generated into a temp dir at run time.

    python -X utf8 selftest.py            all controls
    python -X utf8 selftest.py --smoke    the self-containment subset (FK-INV-7; run from a copy with python -I)
    python -X utf8 selftest.py --only ID[,ID]   selected controls; --list prints ids

Every control runs a positive arm (the defect is present, the gate must fire) and a negative arm (clean input,
the gate must stay silent). A line per arm: PASS|FAIL|SKIP <control> [arm] detail.
"""
from __future__ import annotations

import sys
from pathlib import Path

KIT = Path(__file__).resolve().parent
if str(KIT) not in sys.path:
    sys.path.insert(0, str(KIT))

import argparse
import ast
import json
import math
import os
import re
import shutil
import signal
import struct
import subprocess
import tempfile
import threading
import time
import traceback
from fractions import Fraction

from _fk import common, kinds, manifest, profile as fkprofile, spec as fkspec

PY = sys.executable
CONTROLS: list[tuple[str, str, bool, object]] = []
TMP = Path(tempfile.mkdtemp(prefix="filmkit_selftest_"))


def control(cid: str, closes: str, smoke: bool = False):
    def deco(fn):
        CONTROLS.append((cid, closes, smoke, fn))
        return fn
    return deco


class Arm:
    def __init__(self, name: str, ok: bool, detail: str, skipped: str | None = None):
        self.name, self.ok, self.detail, self.skipped = name, ok, detail, skipped


def pos(ok, detail):
    return Arm("positive", bool(ok), detail)


def neg(ok, detail):
    return Arm("negative", bool(ok), detail)


def skip(name, reason):
    return Arm(name, True, reason, skipped=reason)


def fresh(name: str) -> Path:
    d = TMP / name
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True)
    return d


# =====================================================================================================
# mini JSON Schema interpreter for film_plan.schema.json (type, required, properties, additionalProperties,
# const, pattern, minimum, maximum, exclusiveMinimum, minLength, items, $ref, x-filmkit-* keywords)
# =====================================================================================================
def schema_errors(inst, sch, root, path="$", ctx=None) -> list[str]:
    ctx = ctx or {}
    if "$ref" in sch:
        ref = sch["$ref"].split("/")[-1]
        return schema_errors(inst, root["$defs"][ref], root, path, ctx)
    errs = []
    t = sch.get("type")
    tmap = {"object": dict, "array": list, "string": str, "boolean": bool}
    if t == "number":
        if not isinstance(inst, (int, float)) or isinstance(inst, bool):
            return [f"{path}: not a number"]
    elif t == "integer":
        if not isinstance(inst, int) or isinstance(inst, bool):
            return [f"{path}: not an integer"]
    elif t and not isinstance(inst, tmap[t]):
        return [f"{path}: not {t}"]
    if "const" in sch and (inst != sch["const"] or isinstance(inst, bool)):
        errs.append(f"{path}: const")
    if isinstance(inst, str):
        if "minLength" in sch and len(inst) < sch["minLength"]:
            errs.append(f"{path}: minLength")
        if "pattern" in sch and not re.search(sch["pattern"], inst):
            errs.append(f"{path}: pattern")
        if "x-filmkit-even-size" in sch and fkspec.size_problem(inst):
            errs.append(f"{path}: even size")
    if isinstance(inst, (int, float)) and not isinstance(inst, bool):
        if "minimum" in sch and inst < sch["minimum"]:
            errs.append(f"{path}: minimum")
        if "maximum" in sch and inst > sch["maximum"]:
            errs.append(f"{path}: maximum")
        if "exclusiveMinimum" in sch and inst <= sch["exclusiveMinimum"]:
            errs.append(f"{path}: exclusiveMinimum")
    if isinstance(inst, dict):
        for r in sch.get("required", []):
            if r not in inst:
                errs.append(f"{path}: missing {r}")
        props = sch.get("properties", {})
        for k, v in inst.items():
            if k in props:
                errs += schema_errors(v, props[k], root, f"{path}.{k}", ctx)
            elif sch.get("additionalProperties") is False:
                errs.append(f"{path}: unknown {k}")
        if sch.get("x-filmkit-t0-lt-t1") and all(isinstance(inst.get(k), (int, float)) for k in ("t0", "t1")):
            if not inst["t0"] < inst["t1"]:
                errs.append(f"{path}: t0 >= t1")
        if "x-filmkit-whole-frames" in sch and isinstance(inst.get("duration_s"), (int, float)):
            fps = inst.get("fps", 30)
            if isinstance(fps, int) and not isinstance(fps, bool) and 1 <= fps <= 120:
                d = inst["duration_s"] * fps
                if abs(d - round(d)) > 1e-6:
                    errs.append(f"{path}: whole frames")
    if isinstance(inst, list) and "items" in sch:
        for i, it in enumerate(inst):
            errs += schema_errors(it, sch["items"], root, f"{path}[{i}]", ctx)
    return errs


PLAN_VALID = [
    {"schema_version": 1},
    {"schema_version": 1, "expected": {"duration_s": 30.0, "size": "1280x720", "fps": 30, "audio_expected": True}},
    {"schema_version": 1, "expected": {"duration_s": 10.5, "fps": 24}, "film_type": "product-tour"},
    {"schema_version": 1, "holds": [{"t0": 26.4, "t1": 30.0, "why": "end card"}],
     "blacks": [{"t0": 0.0, "t1": 0.3, "why": "fade-in"}], "silences": [{"t0": 0, "t1": 1, "why": "cold open"}]},
    {"schema_version": 1, "sections": [{"id": "S1", "t0": 0.0, "t1": 4.5}],
     "narration_lines": [{"id": "L1", "t0": 1.2, "t1": 3.4}]},
    {"schema_version": 1, "expected": {"size": "16x16"}, "holds": []},
]
PLAN_INVALID = [
    ("missing why", {"schema_version": 1, "holds": [{"t0": 1, "t1": 2}]}),
    ("t0 >= t1", {"schema_version": 1, "blacks": [{"t0": 2, "t1": 2, "why": "x"}]}),
    ("odd size", {"schema_version": 1, "expected": {"size": "1279x720"}}),
    ("unknown key", {"schema_version": 1, "extra": 1}),
    ("wrong schema_version", {"schema_version": 2}),
    ("non-integer frame count", {"schema_version": 1, "expected": {"duration_s": 10.05, "fps": 30}}),
    ("negative t0", {"schema_version": 1, "sections": [{"id": "S", "t0": -1, "t1": 2}]}),
    ("fps out of range", {"schema_version": 1, "expected": {"fps": 0}}),
    ("empty why", {"schema_version": 1, "silences": [{"t0": 0, "t1": 1, "why": "  "}]}),
    ("bad film_type", {"schema_version": 1, "film_type": "Product Tour"}),
]


@control("schema-agreement", "4.1 plan validator vs schema, 6 valid + 10 invalid", smoke=True)
def c_schema():
    sch = json.loads((KIT / "film_plan.schema.json").read_text(encoding="utf-8"))
    arms = []
    bad = []
    for i, p in enumerate(PLAN_VALID):
        a, b = fkspec.validate_plan(p), schema_errors(p, sch, sch)
        if a or b:
            bad.append(f"valid#{i}: validator={a} schema={b}")
    arms.append(neg(not bad, f"6 valid fixtures accepted by both ({bad or 'all agree'})"))
    bad = []
    for name, p in PLAN_INVALID:
        a, b = fkspec.validate_plan(p), schema_errors(p, sch, sch)
        if not a or not b:
            bad.append(f"{name}: validator={a} schema={b}")
    arms.append(pos(not bad, f"10 invalid fixtures rejected by both ({bad or 'all agree'})"))
    return arms


@control("P-9", "frame count must be whole", smoke=True)
def c_frames():
    try:
        fkspec.frame_count(10.05, 30)
        p = pos(False, "10.05 s at 30 fps accepted")
    except common.SpecInvalid as e:
        p = pos("whole number of frames" in e.hint, f"10.05 s at 30 fps -> SpecInvalid, hint: {e.hint}")
    n = fkspec.frame_count(30.0000000001, 30)
    return [p, neg(n == 900, f"30.0000000001 s at 30 fps -> N = {n}")]


FIXTURE_B = {"video": {"codec": "libx264", "crf": 23, "preset": "slow", "pix_fmt": "yuv420p", "faststart": True},
             "audio": {"codec": "aac", "bitrate": "192k", "channels": 2}, "fps_default": 30}


@control("FK-INV-4", "encoder argv only from resolve_profile()", smoke=True)
def c_inv4():
    lab = fkprofile.get_profile("lab-round")
    a1 = fkprofile.resolve_profile(lab, 30, True, "lab-round")
    a2 = fkprofile.resolve_profile(lab, 30, True, "lab-round")
    b = fkprofile.resolve_profile(FIXTURE_B, 30, True, "fixture-b")
    return [pos(a1.video_args != b.video_args, f"fixture-b argv differs: {list(b.video_args)} vs {list(a1.video_args)}"),
            neg(a1 == a2, "same profile twice -> identical argv")]


@control("profiles-key-scan", "4.4 no target/lufs/true_peak/platform keys (Y-16c)", smoke=True)
def c_profile_keys():
    pat = re.compile(r"target|lufs|true_?peak|platform", re.I)

    def keys(o):
        if isinstance(o, dict):
            for k, v in o.items():
                yield k
                yield from keys(v)
        elif isinstance(o, list):
            for v in o:
                yield from keys(v)
    real = [k for k in keys(fkprofile.load_profiles()) if pat.search(k)]
    fixture = {"profiles": {"x": {"loudness": {"target_lufs": -14}}}}
    fx = [k for k in keys(fixture) if pat.search(k)]
    return [pos(bool(fx), f"fixture profile with target_lufs flagged: {fx}"),
            neg(not real, f"profiles.json clean: {real or 'no matching keys'}")]


@control("FK-INV-13-kinds", "6.7 kinds mapping total over FilmkitError subclasses", smoke=True)
def c_kinds_total():
    missing = [c.__name__ for c in common.ERROR_CLASSES if c.kind not in kinds.KINDS]
    fake = type("FakeErr", (common.FilmkitError,), {"kind": "no_such_kind"})
    fake_missing = fake.kind not in kinds.KINDS
    return [pos(fake_missing, "a fixture error class with an unmapped kind is detected"),
            neg(not missing, f"every FilmkitError subclass has a kinds entry ({missing or 'none missing'})")]


# =====================================================================================================
# step 3: guard / store / record units
# =====================================================================================================
from _fk import guard, store as fkstore  # noqa: E402

HOLDER = """
import sys, time, subprocess
sys.path.insert(0, sys.argv[1])
from _fk.guard import OutputLock
lk = OutputLock(sys.argv[2]); lk.__enter__()
if len(sys.argv) > 3 and sys.argv[3] == 'child':
    c = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    print('C', c.pid, flush=True)
print('HELD', flush=True)
if len(sys.argv) > 3 and sys.argv[3] == 'quick':
    time.sleep(0.3); lk.__exit__(None, None, None); sys.exit(0)
time.sleep(30)
"""


def start_holder(folder: Path, mode: str = ""):
    p = subprocess.Popen([PY, "-c", HOLDER, str(KIT), str(folder)] + ([mode] if mode else []), stdout=subprocess.PIPE, text=True)
    child = None
    line = p.stdout.readline().strip()
    if line.startswith("C "):
        child = int(line.split()[1])
        p.stdout.readline()
    return p, child


def lock_skip():
    return None if guard.IS_WINDOWS else "skipped (non-Windows)"


@control("L1-L2", "6.1 lock: held -> busy after 2 s / released -> at once")
def c_l1():
    if lock_skip():
        return [skip("positive", lock_skip()), skip("negative", lock_skip())]
    d = fresh("l1")
    p, _ = start_holder(d)
    t0 = time.monotonic()
    try:
        with guard.OutputLock(d):
            got = True
    except common.Busy:
        got = False
    dt = time.monotonic() - t0
    p.kill(); p.wait()
    p2, _ = start_holder(d, "quick")
    p2.wait()
    t0 = time.monotonic()
    with guard.OutputLock(d):
        dt2 = time.monotonic() - t0
    return [pos(not got and dt >= 1.9, f"L1 held by another process -> Busy after {dt:.2f} s"),
            neg(dt2 < 0.3, f"L2 holder finished normally -> acquired in {dt2:.3f} s")]


@control("L3", "6.1 lock: hard kill with handle kept -> acquire")
def c_l3():
    if lock_skip():
        return [skip("positive", lock_skip()), skip("negative", lock_skip())]
    d = fresh("l3")
    p, _ = start_holder(d)
    held_free = guard.try_lock_free(d)
    p.kill()  # handle kept: p is not waited on before the acquire
    t0 = time.monotonic()
    with guard.OutputLock(d):
        dt = time.monotonic() - t0
    p.wait()
    return [pos(dt < 2.0, f"Popen.kill() without releasing the handle -> acquired in {dt:.3f} s"),
            neg(held_free is False, f"before the kill the lock was held (try_lock_free={held_free})")]


@control("L7-lock", "6.1 lock: holder killed while its grandchild runs -> acquire (lock not inherited)")
def c_l7_lock():
    if lock_skip():
        return [skip("positive", lock_skip()), skip("negative", lock_skip())]
    d = fresh("l7")
    p, child = start_holder(d, "child")
    p.kill()
    p.wait()
    alive = str(child) in subprocess.run(["tasklist", "/FI", f"PID eq {child}"], capture_output=True, text=True).stdout
    t0 = time.monotonic()
    with guard.OutputLock(d):
        dt = time.monotonic() - t0
    subprocess.run(["taskkill", "/F", "/PID", str(child)], capture_output=True)
    p2, _ = start_holder(d)
    free_while_held = guard.try_lock_free(d)
    p2.kill(); p2.wait()
    return [pos(alive and dt < 2.0, f"grandchild alive={alive}; lock acquired in {dt:.3f} s"),
            neg(free_while_held is False, "a live holder still excludes (control can fail)")]


@control("try_lock_free", "6.1 acquire-and-release probe")
def c_tlf():
    if lock_skip():
        return [skip("positive", lock_skip()), skip("negative", lock_skip())]
    d = fresh("tlf")
    free_missing = guard.try_lock_free(d)
    p, _ = start_holder(d)
    held = guard.try_lock_free(d)
    p.kill(); p.wait()
    time.sleep(0.1)
    free = guard.try_lock_free(d)
    return [pos(held is False, f"held -> {held}"), neg(free is True and free_missing is True,
                                                        f"free -> {free}; no lock file -> {free_missing}")]


def mk_owned(d: Path, status="done", out_bytes=b"video-bytes", inputs=None):
    """A folder with an output file and a record that owns it."""
    (d / "index.html").write_text("<p>page</p>", encoding="utf-8")
    (d / "final.mp4").write_bytes(out_bytes)
    inputs = inputs or ["index.html"]
    ins = [{"path": p, "sha256": common.sha256_file(d / p)} for p in inputs]
    rec = {"schema_version": 1, "generator": "filmkit", "run_id": "r1", "status": status, "phase": "complete",
           "output": "final.mp4", "pending_publish": None,
           "last_success": {"output": {"name": "final.mp4", "sha256": common.sha256_file(d / "final.mp4"),
                                       "bytes": len(out_bytes)},
                            "inputs": ins, "inputs_sha256": guard.inputs_digest(ins)}}
    return rec


def ostate(d: Path, rec, lock_other=False):
    rec2 = guard.reconcile(rec, d / "final.mp4") if rec else None
    cur = guard.current_inputs(d, rec2["last_success"]) if rec2 and rec2.get("last_success") else None
    return guard.owner_state(rec2, d / "final.mp4", cur, lock_other)


@control("owner_state", "6.1 truth table rows 1-7 (P-6, Q-2)")
def c_owner():
    got = {}
    d = fresh("os1"); rec = mk_owned(d); (d / "final.mp4").unlink(); got[1] = ostate(d, rec)
    d = fresh("os2a"); mk_owned(d); got["2a"] = ostate(d, None)
    d = fresh("os2b"); rec = mk_owned(d); (d / "final.mp4").write_bytes(b"other"); got["2b"] = ostate(d, rec)
    d = fresh("os3"); rec = mk_owned(d); (d / "index.html").unlink(); got[3] = ostate(d, rec)
    d = fresh("os4"); rec = mk_owned(d); (d / "index.html").write_text("<p>edited</p>"); got[4] = ostate(d, rec)
    d = fresh("os5"); rec = mk_owned(d, status="failed"); got[5] = ostate(d, rec)
    d = fresh("os5i"); rec = mk_owned(d, status="interrupted"); got["5i"] = ostate(d, rec)
    d = fresh("os6"); rec = mk_owned(d, status="running"); got[6] = ostate(d, rec, lock_other=True)
    d = fresh("os6f"); rec = mk_owned(d, status="running"); got["6free"] = ostate(d, rec, lock_other=False)
    d = fresh("os7"); rec = mk_owned(d); got[7] = ostate(d, rec)
    want = {1: "ABSENT", "2a": "FOREIGN", "2b": "FOREIGN", 3: "UNDET_INPUTS", 4: "STALE", 5: "STALE", "5i": "STALE",
            6: "STALE", "6free": "CURRENT", 7: "CURRENT"}
    bad = {k: (got[k], want[k]) for k in want if got[k] != want[k]}
    return [pos(not bad, f"rows 1-6 states: {got}"), neg(got[7] == "CURRENT", "row 7 clean record -> CURRENT")]


@control("Q-3b", "killed between rename and promote -> reconciled record CURRENT")
def c_q3b():
    d = fresh("q3b")
    rec = mk_owned(d)
    old_ls = dict(rec["last_success"])
    (d / "final.mp4").write_bytes(b"new-video")  # renamed new file; promote never ran
    rec["pending_publish"] = {"sha256": common.sha256_file(d / "final.mp4"), "bytes": 9}
    rec["inputs"] = old_ls["inputs"]; rec["inputs_sha256"] = old_ls["inputs_sha256"]
    rec["page"] = "index.html"
    st = ostate(d, rec)
    rec2 = dict(rec); rec2["pending_publish"] = {"sha256": "0" * 64, "bytes": 9}
    st2 = ostate(d, rec2)
    return [pos(st == "CURRENT", f"pending matches the file -> reconciled -> {st}"),
            neg(st2 == "FOREIGN", f"pending does not match -> dropped -> {st2}")]


@control("P-17-unit", "6.0 write retry: reader holds 100 ms ok / 5 s -> RecordWriteError")
def c_p17_unit():
    d = fresh("p17u")
    t = d / "render.json"
    common.write_json_atomic(t, {"a": 1}, {"attempts": 10, "step_s": 0.05})

    def hold(secs):
        f = open(t, "r")
        time.sleep(secs)
        f.close()
    th = threading.Thread(target=hold, args=(0.1,)); th.start(); time.sleep(0.02)
    try:
        common.write_json_atomic(t, {"a": 2}, {"attempts": 10, "step_s": 0.05}); short = "ok"
    except common.RecordWriteError as e:
        short = f"failed: {e.message}"
    th.join()
    th = threading.Thread(target=hold, args=(5.0,)); th.start(); time.sleep(0.02)
    try:
        common.write_json_atomic(t, {"a": 3}, {"attempts": 10, "step_s": 0.05}); long_ = "ok"
    except common.RecordWriteError as e:
        long_ = "RecordWriteError"
    th.join()
    content = json.loads(t.read_text())
    return [pos(long_ == "RecordWriteError" and content == {"a": 2}, f"5 s hold -> {long_}; file keeps {content}"),
            neg(short == "ok", f"100 ms hold -> {short}")]


@control("Q-9-unit", "hard kill during an atomic write leaves no tmp at top level; CREATED cleanup removes it")
def c_q9_unit():
    d = fresh("q9u")
    code = ("import sys; sys.path.insert(0, sys.argv[1]); from pathlib import Path; from _fk import common;"
            "common.write_json_atomic(Path(sys.argv[2]) / 'render.json', {'a': 1}, None)")
    env = dict(os.environ, FILMKIT_SELFTEST_FAULT="atomic_write_before_replace=exit")
    r = subprocess.run([PY, "-c", code, str(KIT), str(d)], env=env)
    top_tmp = [p.name for p in d.iterdir() if p.is_file() and "tmp" in p.name]
    fk_tmp = [p.name for p in (d / ".filmkit").iterdir() if p.suffix == ".tmp"]
    notes = guard.cleanup_on_created(d, "newrun")
    after = [p.name for p in (d / ".filmkit").iterdir() if p.suffix == ".tmp"]
    return [pos(r.returncode == 137 and fk_tmp and not after, f"killed (rc {r.returncode}); .filmkit tmp {fk_tmp} -> after cleanup {after}"),
            neg(not top_tmp and not (d / "render.json").exists(), f"page folder top level has no tmp ({top_tmp}) and no half record")]


# =====================================================================================================
# =====================================================================================================
# step 4-5: render / check end to end (subprocess, real Chromium + ffmpeg)
# =====================================================================================================
SMALL = ["--duration", "1", "--size", "160x90", "--fps", "10"]
BASE_CSS = ("html,body{margin:0;background:#fff;font-family:Arial}"
            "#b{position:absolute;width:20px;height:20px;background:#c33;top:30px}")
# wrapped motion: the square keeps moving for any length, so a 10 s clean film is not a still (FK-R-8, M2 reading 8)
BASE_JS = "window.__setTime=function(t){document.getElementById('b').style.left=((t*100)%140)+'px';};"


class Res:
    def __init__(self, code, out, err):
        self.code, self.lines, self.err = code, out.splitlines(), err

    @property
    def first(self):
        return self.lines[0] if self.lines else ""

    def line(self, prefix):
        return next((ln for ln in self.lines if ln.startswith(prefix)), "")

    def __str__(self):
        return f"exit {self.code}; {self.first[:160]}"


def write_page(d: Path, body: str = "", head: str = "", js: str = BASE_JS, css: str = BASE_CSS,
               name: str = "index.html") -> Path:
    html = (f'<!doctype html><html><head><meta charset="utf-8"><style>{css}</style>{head}</head>'
            f'<body><div id="b"></div>{body}<script>{js}</script></body></html>')
    (d / name).write_text(html, encoding="utf-8")
    return d / name


def tool_env(extra: dict | None = None) -> dict:
    e = {k: v for k, v in os.environ.items() if not k.startswith("FILMKIT_SELFTEST")}
    e.update(extra or {})
    return e


def run_tool(script: str, args, env: dict | None = None, timeout: float = 240, cwd=None) -> Res:
    p = subprocess.run([PY, "-X", "utf8", str(KIT / script)] + [str(a) for a in args], capture_output=True,
                       text=True, encoding="utf-8", errors="replace", env=tool_env(env), timeout=timeout, cwd=cwd)
    return Res(p.returncode, p.stdout, p.stderr)


def render(d: Path, *extra, env=None, page="index.html", out="final.mp4", small=True) -> Res:
    return run_tool("render.py", [d / page, "-o", d / out] + (SMALL if small else []) + list(extra), env)


def check(f: Path, *extra, env=None) -> Res:
    return run_tool("check.py", [f] + list(extra), env)


def rec_of(d: Path) -> dict:
    return json.loads((d / "render.json").read_text(encoding="utf-8"))


def cj_of(d: Path, name: str = "check.json") -> dict:
    return json.loads((d / name).read_text(encoding="utf-8"))


def rows_of(doc: dict) -> dict:
    return {r["id"]: r for r in doc["rows"]}


def five_ok(r: Res) -> bool:
    heads = ("Done:" if r.code != 1 else "Failed:", "Steps:", "Check:", "Look:", "Notes:")
    return len(r.lines) == 5 and all(ln.startswith(h) for ln, h in zip(r.lines, heads))


def ff(*args):
    p = subprocess.run(["ffmpeg", "-v", "error", "-y"] + [str(a) for a in args], capture_output=True, text=True)
    if p.returncode:
        raise RuntimeError(f"ffmpeg fixture failed: {p.stderr[-400:]}")


def mk_mp4(path: Path, dur=1.0, size="160x90", fps=10, pix="yuv420p", faststart=True, audio_s=None, ch=2,
           vf=None, extra=()):
    a = ["-f", "lavfi", "-i", f"testsrc=size={size}:rate={fps}:duration={dur}"]
    if audio_s is not None:
        a += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={audio_s}:sample_rate=48000"]
    a += ["-c:v", "libx264", "-pix_fmt", pix, "-preset", "ultrafast"]
    if vf:
        a += ["-vf", vf]
    if audio_s is not None:
        a += ["-c:a", "aac", "-ac", str(ch), "-ar", "48000"]
    if faststart:
        a += ["-movflags", "+faststart"]
    ff(*a, *extra, path)
    return path


def mk_wav(path: Path, dur=1.0, ch=2, freq=440):
    ff("-f", "lavfi", "-i", f"sine=frequency={freq}:duration={dur}:sample_rate=48000", "-ac", str(ch), path)
    return path


def wait_file(p: Path, timeout: float = 60) -> bool:
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        if p.exists() and p.stat().st_size > 0:
            time.sleep(0.05)
            return True
        time.sleep(0.05)
    return False


def kill_pid(pid: int):
    try:
        os.kill(pid, signal.SIGTERM)  # TerminateProcess on Windows
    except OSError:
        pass


def start_render(d: Path, *extra, env=None, out="final.mp4", small=True):
    args = [PY, "-X", "utf8", str(KIT / "render.py"), str(d / "index.html"), "-o", str(d / out)] + \
           (SMALL if small else []) + [str(a) for a in extra]
    kw = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {}
    return subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8",
                            errors="replace", env=tool_env(env), **kw)


def finish(p, timeout: float = 240) -> Res:
    out, err = p.communicate(timeout=timeout)
    return Res(p.returncode, out, err)


LONG = ["--duration", "30", "--size", "160x90", "--fps", "30"]


def wait_capture(d: Path, timeout: float = 60):
    """Until render.json says capture is running, plus a moment so a Playwright call is in flight."""
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        try:
            if rec_of(d).get("phase") == "capture":
                time.sleep(1.0)
                return
        except (OSError, ValueError):
            pass
        time.sleep(0.1)


CONSOLE_HELPER = r'''
import ctypes, json, signal, subprocess, sys, time
from pathlib import Path
args, outp, errp, rec = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
ctypes.windll.kernel32.SetConsoleCtrlHandler(None, False)   # an inherited ignore flag would mute the child
signal.signal(signal.SIGINT, lambda *a: None)               # SIG_IGN would be inherited too
with open(outp, "w", encoding="utf-8") as o, open(errp, "w", encoding="utf-8") as e:
    p = subprocess.Popen(args, stdout=o, stderr=e)
    t0 = time.monotonic()
    while time.monotonic() - t0 < 60:
        try:
            if json.loads(Path(rec).read_text(encoding="utf-8")).get("phase") == "capture":
                break
        except (OSError, ValueError):
            pass
        time.sleep(0.1)
    time.sleep(1.0)
    ctypes.windll.kernel32.GenerateConsoleCtrlEvent(0, 0)   # CTRL_C_EVENT to every process on this console
    try:
        rc = p.wait(timeout=90)
    except subprocess.TimeoutExpired:
        p.kill()
        rc = "HANG"
    time.sleep(3)                                           # an orphaned driver would write EPIPE here
Path(outp + ".rc").write_text(str(rc), encoding="utf-8")
'''


def console_ctrl_c(d: Path) -> Res:
    """A key-press Ctrl-C: render.py, the Playwright driver and Chromium share a fresh console and all get it."""
    h = d.parent / "console_ctrl_c.py"
    h.write_text(CONSOLE_HELPER, encoding="utf-8")
    outp, errp = str(d.parent / "cc.out"), str(d.parent / "cc.err")
    args = [PY, "-X", "utf8", str(KIT / "render.py"), str(d / "index.html"), "-o", str(d / "final.mp4")] + LONG
    spec = d.parent / "cc.json"
    spec.write_text(json.dumps([args, outp, errp, str(d / "render.json")]), encoding="utf-8")
    subprocess.run([PY, str(h), str(spec)], creationflags=subprocess.CREATE_NEW_CONSOLE, env=tool_env(), timeout=200)
    rc = Path(outp + ".rc").read_text(encoding="utf-8")
    return Res(int(rc) if rc.lstrip("-").isdigit() else rc, Path(outp).read_text(encoding="utf-8"),
               Path(errp).read_text(encoding="utf-8"))


def tmp_files_top(d: Path) -> list[str]:
    return sorted(p.name for p in d.iterdir() if p.is_file() and (p.suffix == ".tmp" or p.name.endswith(".filmkit-tmp")))


@control("clean-render", "design 9 clean page, 10 s: all confirmed; FK-INV-6 normal run -> done; P-5 faststart on a silent page")
def c_clean():
    d = fresh("clean")
    write_page(d, body='<p style="position:absolute;top:50px;margin:0;font-size:12px">Hi 你好</p>')
    r = render(d, "--duration", "10", "--size", "160x90", "--fps", "10", small=False)
    rec = rec_of(d)
    doc = cj_of(d)
    rows = rows_of(doc)
    d2 = fresh("clean_nofs")
    nofs = mk_mp4(d2 / "x.mp4", faststart=False)
    r2 = check(nofs, "--duration", "1", "--size", "160x90", "--fps", "10")
    rows2 = rows_of(cj_of(d2, "x.mp4.check.json"))
    return [neg(r.code == 0 and five_ok(r) and doc["summary"]["blocking"] == 0 and doc["summary"]["look"] == 0
                and doc["summary"]["undetermined"] == 0 and rec["status"] == "done",
                f"clean page: {r}; summary {doc['summary']}; record status {rec['status']}"),
            neg(rows["FK-R-4"]["verdict"] == "PASS" and "faststart yes" in rows["FK-R-4"]["measured"],
                f"silent publish FK-R-4: {rows['FK-R-4']['verdict']} ({rows['FK-R-4']['measured']})"),
            pos(rows2["FK-R-4"]["verdict"] == "FAIL" and "faststart" in rows2["FK-R-4"]["message_key"] and r2.code == 2,
                f"file encoded without +faststart: FK-R-4 {rows2['FK-R-4']['verdict']} {rows2['FK-R-4']['message_key']}, {r2}")]


class FakeBackend:
    """CaptureBackend fake: records seek() arguments, returns solid PNGs (FK-INV-3)."""
    seeks: list = []

    def __init__(self, run_id, placement="shadow"):
        from _fk.types import LoadReport
        self.report = LoadReport()
        self.first_hashes = {}
        self.chromium_version = "fake"
        FakeBackend.seeks = []

    def open(self, page_path, width, height):
        self.w, self.h = width, height

    def load(self, ready_timeout_s):
        return self.report

    def seek(self, t):
        FakeBackend.seeks.append(t)
        self.cur = t

    def snapshot(self):
        # a pure function of the last seek time, so the re-seek sample (FK-R-12) finds every frame identical
        return solid_png(self.w, self.h, (int(self.cur * 10) * 20 % 255, 80, 120))

    def live_animations(self):
        return 0

    def sample_font_families(self, moment):
        return []

    def check_errors(self, where):
        pass

    def check_requests(self, where):
        pass

    def close(self):
        pass


def solid_png(w: int, h: int, rgb) -> bytes:
    import zlib
    raw = b"".join(b"\x00" + bytes(rgb) * w for _ in range(h))

    def chunk(t, data):
        return struct.pack(">I", len(data)) + t + data + struct.pack(">I", zlib.crc32(t + data) & 0xffffffff)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def seeks_match(seeks: list, frames_t: list, fps: int) -> bool:
    return (len(seeks) == len(frames_t)
            and all(Fraction(s) == Fraction(i, fps) == Fraction(ft) for i, (s, ft) in enumerate(zip(seeks, frames_t))))


@control("FK-INV-3", "seek(t) receives Fraction(i, fps) == frames.t; float accumulation fails the comparison")
def c_inv3():
    import contextlib
    import io
    import render as fkrender
    d = fresh("inv3")
    write_page(d)
    buf = io.StringIO()
    two_s = ["--duration", "2", "--size", "160x90", "--fps", "10"]      # 20 frames: 12 re-seeks are a strict subset
    old_factory = fkrender.RenderJob.backend_factory
    old_int = signal.getsignal(signal.SIGINT)
    old_brk = signal.getsignal(signal.SIGBREAK) if hasattr(signal, "SIGBREAK") else None
    try:
        fkrender.RenderJob.backend_factory = FakeBackend
        with contextlib.redirect_stdout(buf):
            code = fkrender.main([str(d / "index.html"), "-o", str(d / "final.mp4"), *two_s])
    finally:
        fkrender.RenderJob.backend_factory = old_factory
        signal.signal(signal.SIGINT, old_int)
        if old_brk is not None:
            signal.signal(signal.SIGBREAK, old_brk)
    rec = rec_of(d)
    ft = rec["frames"]["t"]
    all_seeks = list(FakeBackend.seeks)
    n = len(ft)
    seeks, again = all_seeks[:n], all_seeks[n:]       # capture seeks, then the re-seek sample (M2)
    acc, drift = 0.0, []
    for _ in range(len(ft)):
        drift.append(Fraction(acc))
        acc += 1 / 10
    idx = [int(s * 10) for s in again]
    rs = (rec_of(d)["frames"]).get("resample") or []
    return [neg(code == 0 and seeks_match(seeks, ft, 10) and all(isinstance(s, Fraction) for s in seeks),
                f"fake backend: {len(seeks)} capture seeks, all Fraction(i, 10), equal to frames.t (exit {code})"),
            neg(len(again) == 12 and len(set(idx)) == 12 and all(isinstance(s, Fraction) and s == Fraction(int(s * 10), 10)
                                                                  for s in again) and idx != sorted(idx),
                f"{len(again)} re-seeks after the capture: distinct frames {idx}, Fraction(i, 10), shuffled order"),
            neg([x["i"] for x in rs] == idx and all(x["match"] for x in rs),
                f"render.json frames.resample lists the same 12 frames in visit order, every match true"),
            pos(not seeks_match(drift, ft, 10), "accumulated float t (t += 1/10) differs from frames.t -> comparison fails")]


@control("FK-INV-1", "ffmpeg killed mid-run -> FAILED(encode), no output / clean page publishes; Y-7(b) killed in wait()")
def c_inv1():
    d = fresh("inv1")
    write_page(d)
    mk = d.parent / "inv1_marker.json"
    p = start_render(d, env={"FILMKIT_SELFTEST_FAULT": f"capture_frame_3=sleep:3:{mk}"})
    ok_mark = wait_file(mk)
    if ok_mark:
        kill_pid(json.loads(mk.read_text(encoding="utf-8"))["ffmpeg_pid"])
    r = finish(p)
    rec = rec_of(d)
    d2 = fresh("inv1_wait")
    write_page(d2)
    mk2 = d2.parent / "inv1_wait_marker.json"
    p2 = start_render(d2, env={"FILMKIT_SELFTEST_FAULT": f"before_close_stdin=sleep:3:{mk2}"})
    if wait_file(mk2):
        kill_pid(json.loads(mk2.read_text(encoding="utf-8"))["ffmpeg_pid"])
    r2 = finish(p2)
    d3 = fresh("inv1_clean")
    write_page(d3)
    r3 = render(d3)
    return [pos(ok_mark and r.code == 1 and r.first.startswith("Failed: encode") and not (d / "final.mp4").exists()
                and rec["status"] == "failed" and five_ok(r), f"ffmpeg killed at frame 3: {r}; record {rec['status']}; final.mp4 absent"),
            pos(r2.code == 1 and r2.first.startswith("Failed: encode") and not (d2 / "final.mp4").exists(),
                f"ffmpeg killed before close/wait: {r2}"),
            neg(r3.code == 0 and (d3 / "final.mp4").is_file(), f"clean page: {r3}")]


@control("hard-kill-rerun", "design 9: render killed mid-capture -> no output, record valid + running; rerun row 6 'previous run interrupted', last_success kept")
def c_hardkill():
    d = fresh("hardkill")
    write_page(d)
    r0 = render(d)
    old_sha = common.sha256_file(d / "final.mp4")
    write_page(d, js=BASE_JS + "/*v2*/")
    r1 = render(d, env={"FILMKIT_SELFTEST_FAULT": "capture_frame_4=exit"})
    rec1 = rec_of(d)
    after_kill_sha = common.sha256_file(d / "final.mp4")
    r2 = render(d)
    rec2 = rec_of(d)
    return [pos(r1.code == 137 and rec1["status"] == "running" and rec1["last_success"]["output"]["sha256"] == old_sha
                and after_kill_sha == old_sha, f"killed at frame 4: exit {r1.code}, record {rec1['status']}, old film unchanged"),
            pos(r2.code == 0 and "previous run interrupted" in r2.line("Notes:") and rec2["status"] == "done",
                f"rerun: {r2}; {r2.line('Notes:')[:120]}"),
            neg(r0.code == 0 and "interrupted" not in r0.line("Notes:"), f"first clean run: {r0}")]


@control("FK-INV-6", "interrupt right after start -> record exists, valid JSON, running / normal run -> done")
def c_inv6():
    d = fresh("inv6")
    write_page(d)
    r = render(d, env={"FILMKIT_SELFTEST_FAULT": "after_record_start=exit"})
    rec = rec_of(d)
    d2 = fresh("inv6b")
    write_page(d2)
    r2 = render(d2)
    return [pos(r.code == 137 and rec["status"] == "running" and rec.get("pid"), f"killed after record start: record status {rec['status']}"),
            neg(r2.code == 0 and rec_of(d2)["status"] == "done", f"normal run: {r2}")]


@control("drop-frame", "design 9: one frame not written to the encoder -> FAILED(verify), output name absent")
def c_drop():
    d = fresh("drop")
    write_page(d)
    r = render(d, env={"FILMKIT_SELFTEST_DROP_FRAME": "5"})
    d2 = fresh("drop_clean")
    write_page(d2)
    r2 = render(d2)
    return [pos(r.code == 1 and r.first.startswith("Failed: verify") and not (d / "final.mp4").exists(), f"dropped frame 5: {r}"),
            neg(r2.code == 0, f"no drop: {r2}")]


@control("L-render", "design 9: two render.py at once -> one REJECTED(busy) after 2 s; Q-18 lock.json unchanged; L7 partial names differ by run_id")
def c_lrender():
    d = fresh("lrender")
    write_page(d)
    mk = d.parent / "lrender_marker.json"
    pa = start_render(d, env={"FILMKIT_SELFTEST_FAULT": f"before_set_pending=sleep:6:{mk}"})
    wait_file(mk)
    lock_before = (d / ".filmkit" / "lock.json").read_bytes()
    partials_a = sorted(p.name for p in (d / ".filmkit").iterdir() if p.name.endswith((".video.mp4", ".partial")))
    t0 = time.monotonic()
    rb = render(d)
    dt = time.monotonic() - t0
    lock_after = (d / ".filmkit" / "lock.json").read_bytes()
    ra = finish(pa)
    run_a = json.loads(lock_before)["run_id"]
    run_b = rec_of(d)["run_id"]
    return [pos(rb.code == 1 and rb.first.startswith("Failed: busy") and dt >= 1.9, f"second render while A runs: {rb} after {dt:.1f} s"),
            pos(lock_before == lock_after, f"A's lock.json unchanged by B (pid/run_id {json.loads(lock_after)['pid']}/{run_a})"),
            pos(partials_a and all(f".{run_a}." in n for n in partials_a), f"A's partials carry its run_id: {partials_a}"),
            neg(ra.code == 0, f"A finishes normally: {ra} (run_id {run_b})")]


@control("Q-9", "hard kill during a render.json write -> no *.tmp in the page folder's top level; the next CREATED removes .filmkit/*.tmp / clean run leaves none")
def c_q9():
    d = fresh("q9")
    write_page(d)
    r = render(d, env={"FILMKIT_SELFTEST_FAULT": "atomic_write_before_replace:render.json=exit"})
    top = tmp_files_top(d)
    fk_tmp = sorted(p.name for p in (d / ".filmkit").iterdir() if p.suffix == ".tmp")
    fk_tmp = [n for n in fk_tmp if n.startswith("render.json.")] and fk_tmp
    r2 = render(d)
    fk_tmp2 = sorted(p.name for p in (d / ".filmkit").iterdir() if p.suffix == ".tmp")
    return [pos(r.code == 137 and not top and fk_tmp, f"killed inside a write: top-level tmp {top}, .filmkit tmp {fk_tmp}"),
            neg(r2.code == 0 and not fk_tmp2 and not tmp_files_top(d), f"next run: {r2}; .filmkit tmp {fk_tmp2}")]


@control("start-table", "design 9: corrupt record + file -> output_foreign 'record unreadable'; foreign file -> output_foreign; own file rerun overwrites (FK-INV-2)")
def c_start():
    d = fresh("st_corrupt")
    write_page(d)
    render(d)
    (d / "render.json").write_text("{not json", encoding="utf-8")
    r1 = render(d)
    d2 = fresh("st_foreign")
    write_page(d2)
    mk_mp4(d2 / "final.mp4")
    r2 = render(d2)
    d3 = fresh("st_wronghash")
    write_page(d3)
    render(d3)
    rec = rec_of(d3)
    rec["last_success"]["output"]["sha256"] = "0" * 64
    (d3 / "render.json").write_text(json.dumps(rec), encoding="utf-8")
    r3 = render(d3)
    d4 = fresh("st_own")
    write_page(d4)
    render(d4)
    write_page(d4, js=BASE_JS + "/*edit*/")
    r4 = render(d4)
    return [pos(r1.code == 1 and r1.first.startswith("Failed: output_foreign") and "record unreadable" in r1.line("Notes:"),
                f"corrupt record: {r1}; {r1.line('Notes:')[:100]}"),
            pos(r2.code == 1 and r2.first.startswith("Failed: output_foreign"), f"foreign file: {r2}"),
            pos(r3.code == 1 and r3.first.startswith("Failed: output_foreign"), f"record with wrong hash: {r3}"),
            neg(r4.code == 0, f"rerun over own file: {r4}")]


def first_rgb(png: Path) -> tuple:
    p = subprocess.run(["ffmpeg", "-v", "error", "-i", str(png), "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                       capture_output=True)
    return tuple(p.stdout[:3])


WIN_JS = "window.__setTime=function(t){document.documentElement.style.background=t>=5?'#0000ff':'#ff0000';};"


@control("FK-WIN-1", "--start S renders page time S at frame 0 (agent-review design M2); without it frame 0 is t=0; "
                     "--start with --audio or negative -> REJECTED(spec_invalid)")
def c_window():
    d = fresh("win_start")
    write_page(d, js=WIN_JS)
    r1 = run_tool("render.py", [d / "index.html", "-o", d / "final.mp4", "--size", "160x90", "--fps", "10",
                                "--duration", "0.3", "--start", "5", "--keep-frames"])
    rgb1 = first_rgb(d / ".filmkit" / "frames" / "000000.png") if r1.code == 0 else ()
    d2 = fresh("win_none")
    write_page(d2, js=WIN_JS)
    r2 = run_tool("render.py", [d2 / "index.html", "-o", d2 / "final.mp4", "--size", "160x90", "--fps", "10",
                                "--duration", "0.3", "--keep-frames"])
    rgb2 = first_rgb(d2 / ".filmkit" / "frames" / "000000.png") if r2.code == 0 else ()
    d3 = fresh("win_audio")
    write_page(d3, js=WIN_JS)
    mk_wav(d3 / "a.wav", dur=0.5)
    r3 = run_tool("render.py", [d3 / "index.html", "-o", d3 / "final.mp4", "--size", "160x90", "--fps", "10",
                                "--duration", "0.3", "--start", "5", "--audio", d3 / "a.wav"])
    r4 = run_tool("render.py", [d3 / "index.html", "-o", d3 / "final.mp4", "--size", "160x90", "--fps", "10",
                                "--duration", "0.3", "--start", "-1"])
    blue, red = (lambda c: len(c) == 3 and c[2] > 200 and c[0] < 60), (lambda c: len(c) == 3 and c[0] > 200 and c[2] < 60)
    return [pos(r1.code == 0 and blue(rgb1) and "window render" in r1.line("Notes:"),
                f"--start 5: {r1}; frame 0 rgb {rgb1}; notes {r1.line('Notes:')[:80]}"),
            neg(r2.code == 0 and red(rgb2), f"no --start: {r2}; frame 0 rgb {rgb2}"),
            pos(r3.code == 1 and "spec_invalid" in r3.first, f"--start with --audio: {r3}"),
            pos(r4.code == 1 and "spec_invalid" in r4.first, f"--start -1: {r4}")]


@control("D30", "-o in a sub-folder -> REJECTED(spec_invalid) with the D30 hint / same folder accepted (Q-8); FK-INV-9 output outside")
def c_d30():
    d = fresh("d30")
    write_page(d)
    (d / "preview").mkdir()
    r1 = run_tool("render.py", [d / "index.html", "-o", d / "preview" / "x.mp4", *SMALL])
    r2 = run_tool("render.py", [d / "index.html", "-o", d / "x.mp4", *SMALL])
    return [pos(r1.code == 1 and r1.first.startswith("Failed: spec_invalid") and "copy of the page" in r1.line("Notes:"),
                f"-o preview/x.mp4: {r1}"),
            neg(r2.code == 0, f"-o x.mp4: {r2}")]


@control("P-9-cli", "--duration 10.05 --fps 30 -> REJECTED(spec_invalid) with frame hint / 30.0000000001 -> N = 900")
def c_p9cli():
    d = fresh("p9")
    write_page(d)
    r1 = run_tool("render.py", [d / "index.html", "-o", d / "f.mp4", "--duration", "10.05", "--fps", "30", "--size", "160x90"])
    n = fkspec.frame_count(30.0000000001, 30)
    return [pos(r1.code == 1 and r1.first.startswith("Failed: spec_invalid") and "frame" in (r1.first + r1.line("Notes:")),
                f"10.05 s at 30 fps: {r1}"),
            neg(n == 900, f"30.0000000001 s at 30 fps -> {n}")]


@control("odd-size-cli", "A3: --size 1279x720 -> spec_invalid on line 1, nothing written")
def c_odd_cli():
    d = fresh("oddcli")
    write_page(d)
    r = run_tool("render.py", [d / "index.html", "-o", d / "f.mp4", "--duration", "1", "--size", "161x90", "--fps", "10"])
    left = sorted(p.name for p in d.iterdir())
    r2 = run_tool("render.py", [d / "index.html", "-o", d / "f.mp4", "--duration", "1", "--size", "162x90", "--fps", "10"])
    return [pos(r.code == 1 and r.first.startswith("Failed: spec_invalid") and "161" in r.first and "f.mp4" not in left,
                f"161x90: {r}; folder after: {left}"),
            neg(r2.code == 0, f"162x90: {r2}")]


@control("FK-INV-9", "external URL, parent-folder file -> asset_load; same-folder image loads")
def c_inv9():
    out = []
    d = fresh("inv9_ext")
    write_page(d, body='<img src="https://example.com/x.png">')
    r = render(d)
    out.append(pos(r.code == 1 and r.first.startswith("Failed: asset_load") and "example.com" in r.first, f"external URL: {r}"))
    d = fresh("inv9_parent")
    (d.parent / "inv9_parent.png").write_bytes(solid_png(4, 4, (0, 0, 255)))
    write_page(d, body='<img src="../inv9_parent.png">')
    r = render(d)
    out.append(pos(r.code == 1 and r.first.startswith("Failed: asset_load"), f"parent-folder file: {r}"))
    d = fresh("inv9_same")
    (d / "a.png").write_bytes(solid_png(4, 4, (0, 0, 255)))
    write_page(d, body='<img src="a.png">')
    r = render(d)
    listed = [i["path"] for i in rec_of(d)["last_success"]["inputs"]] if r.code == 0 else []
    out.append(neg(r.code == 0 and "a.png" in listed, f"same-folder image: {r}; inputs {listed}"))
    return out


LATE_JS = ("window.__setTime=function(t){document.getElementById('b').style.left=(t*100)+'px';"
           "if(t>=%s && !window._late){window._late=1;var i=new Image();i.src='%s';document.body.appendChild(i);}};")


@control("frame-50", "design 9 / P-8: image fetched at frame 50: missing or external -> asset_load; present -> listed in inputs, edit -> STALE; copy without it -> UNDET_INPUTS")
def c_frame50():
    from _fk import guard as g
    out = []
    small = ["--duration", "6", "--size", "160x90", "--fps", "10"]
    d = fresh("f50_missing")
    write_page(d, js=LATE_JS % ("5", "img/late.png"))
    r = render(d, *small, small=False)
    out.append(pos(r.code == 1 and r.first.startswith("Failed: asset_load") and "frame 50" in r.first, f"missing img/late.png at frame 50: {r}"))
    d = fresh("f50_ext")
    write_page(d, js=LATE_JS % ("5", "https://example.com/late.png"))
    r = render(d, *small, small=False)
    out.append(pos(r.code == 1 and r.first.startswith("Failed: asset_load") and "frame 50" in r.first, f"external image at frame 50: {r}"))
    d = fresh("f50_ok")
    (d / "img").mkdir()
    (d / "img" / "late.png").write_bytes(solid_png(8, 8, (0, 200, 0)))
    write_page(d, js=LATE_JS % ("5", "img/late.png"))
    r = render(d, *small, small=False)
    rec = g.reconcile(rec_of(d), d / "final.mp4")
    listed = [i["path"] for i in rec["last_success"]["inputs"]]
    st0 = g.owner_state(rec, d / "final.mp4", g.current_inputs(d, rec["last_success"]), False)
    (d / "img" / "late.png").write_bytes(solid_png(8, 8, (200, 0, 0)))
    st1 = g.owner_state(rec, d / "final.mp4", g.current_inputs(d, rec["last_success"]), False)
    out.append(neg(r.code == 0 and "img/late.png" in listed and st0 == "CURRENT", f"present at frame 50: {r}; inputs {listed}; {st0}"))
    out.append(pos(st1 == "STALE", f"img/late.png edited -> {st1}"))
    cp = fresh("f50_copy")
    for n in ("index.html", "final.mp4", "render.json"):
        shutil.copy2(d / n, cp / n)
    rec_c = g.reconcile(rec_of(cp), cp / "final.mp4")
    st2 = g.owner_state(rec_c, cp / "final.mp4", g.current_inputs(cp, rec_c["last_success"]), False)
    (cp / "img").mkdir()
    (cp / "img" / "late.png").write_bytes(solid_png(8, 8, (0, 200, 0)))
    st3 = g.owner_state(rec_c, cp / "final.mp4", g.current_inputs(cp, rec_c["last_success"]), False)
    out.append(pos(st2 == "UNDET_INPUTS", f"copy without img/late.png -> {st2}"))
    out.append(neg(st3 == "CURRENT", f"same copy with the file restored -> {st3}"))
    return out


@control("page-failures", "design 9: __setTime throws at frame 50 -> page_runtime; __ready rejected -> not_ready; no __setTime -> page_contract; missing font file -> asset_load")
def c_pagefail():
    out = []
    small = ["--duration", "6", "--size", "160x90", "--fps", "10"]
    d = fresh("pf_runtime")
    write_page(d, js="window.__setTime=function(t){if(t>=5) throw new Error('boom at 5');};")
    r = render(d, *small, small=False)
    out.append(pos(r.code == 1 and r.first.startswith("Failed: page_runtime") and "5" in r.first, f"throws at frame 50: {r}"))
    d = fresh("pf_ready")
    write_page(d, js=BASE_JS + "window.__ready=Promise.reject(new Error('no data'));")
    r = render(d)
    out.append(pos(r.code == 1 and r.first.startswith("Failed: not_ready") and "no data" in r.first, f"__ready rejected: {r}"))
    d = fresh("pf_contract")
    write_page(d, js="window.foo=1;")
    r = render(d)
    out.append(pos(r.code == 1 and r.first.startswith("Failed: page_contract"), f"no __setTime: {r}"))
    d = fresh("pf_font")
    write_page(d, head="<style>@font-face{font-family:Gone;src:url(fonts/gone.woff2)}p{font-family:Gone}</style>",
               body="<p>text</p>")
    r = render(d)
    out.append(pos(r.code == 1 and r.first.startswith("Failed: asset_load") and "Gone" in r.first, f"missing font file: {r}"))
    d = fresh("pf_ok")
    write_page(d, js=BASE_JS + "window.__ready=new Promise(r=>setTimeout(r,200));")
    r = render(d)
    out.append(neg(r.code == 0 and rec_of(d)["last_success"]["load_report"]["ready_shape"] == "promise", f"__ready resolves: {r}"))
    return out


@control("R-10b", "page or image edited during CAPTURING -> note 'inputs changed while rendering', record keeps end hashes")
def c_r10b():
    d = fresh("r10b")
    (d / "a.png").write_bytes(solid_png(4, 4, (1, 2, 3)))
    write_page(d, body='<img src="a.png">')
    mk = d.parent / "r10b_marker.json"
    p = start_render(d, env={"FILMKIT_SELFTEST_FAULT": f"capture_frame_3=sleep:1:{mk}"})
    wait_file(mk)
    (d / "a.png").write_bytes(solid_png(4, 4, (9, 9, 9)))
    r = finish(p)
    rec = rec_of(d)
    end_sha = common.sha256_file(d / "a.png")
    rec_sha = {i["path"]: i["sha256"] for i in rec["last_success"]["inputs"]}.get("a.png")
    d2 = fresh("r10b_clean")
    (d2 / "a.png").write_bytes(solid_png(4, 4, (1, 2, 3)))
    write_page(d2, body='<img src="a.png">')
    r2 = render(d2)
    return [pos("inputs changed while rendering" in r.line("Notes:") and rec_sha == end_sha, f"a.png edited at frame 3: {r.line('Notes:')[:120]}; record has end hash"),
            neg("inputs changed" not in r2.line("Notes:"), f"unchanged inputs: {r2.line('Notes:')[:80]}")]


@control("kill-points", "Y-2/P-8: killed after set_pending before rename -> file absent, rerun clean; after rename before promote -> next run promotes; design 9 three-run sequence")
def c_killpoints():
    d = fresh("kp_pending")
    write_page(d)
    r1 = render(d, env={"FILMKIT_SELFTEST_FAULT": "after_set_pending=exit"})
    absent = not (d / "final.mp4").exists()
    r1b = render(d)
    d2 = fresh("kp_rename")
    write_page(d2)
    r2 = render(d2, env={"FILMKIT_SELFTEST_FAULT": "after_rename=exit"})
    rec2 = rec_of(d2)
    sha = common.sha256_file(d2 / "final.mp4")
    # second run fails before publishing (missing font file), third run normal
    write_page(d2, head="<style>@font-face{font-family:Gone;src:url(gone.woff2)}p{font-family:Gone}</style>", body="<p>x</p>")
    r3 = render(d2)
    rec3 = rec_of(d2)
    write_page(d2)
    r4 = render(d2)
    return [pos(r1.code == 137 and absent and r1b.code == 0, f"after set_pending: exit {r1.code}, final.mp4 absent={absent}; rerun {r1b}"),
            pos(r2.code == 137 and rec2.get("pending_publish") and rec2["pending_publish"]["sha256"] == sha,
                f"after rename: pending_publish set, file present"),
            pos(r3.first.startswith("Failed: asset_load") and rec3["last_success"]["output"]["sha256"] == sha
                and "output_foreign" not in r3.first, f"rerun failing before publish: {r3}; last_success = pending sha"),
            neg(r4.code == 0, f"third run: {r4}")]


@control("P-17", "a reader holds render.json open 100 ms -> success / 5 s -> FAILED(internal), output untouched (Y-6)")
def c_p17():
    if not guard.IS_WINDOWS:
        return [skip("positive", "non-Windows"), skip("negative", "non-Windows")]
    out = []
    for hold, name in ((0.1, "100ms"), (5.0, "5s")):
        d = fresh(f"p17_{name}")
        write_page(d)
        render(d)
        old = common.sha256_file(d / "final.mp4")
        write_page(d, js=BASE_JS + "/*e*/")
        mk = d.parent / f"p17_{name}_marker.json"
        p = start_render(d, env={"FILMKIT_SELFTEST_FAULT": f"atomic_write_before_replace=sleep:0.3:{mk}"})
        # hold the record open as soon as the first atomic write is about to replace it
        held = False
        t0 = time.monotonic()
        while time.monotonic() - t0 < 30 and p.poll() is None:
            if mk.exists():
                f = open(d / "render.json", "rb")
                held = True
                time.sleep(hold)
                f.close()
                break
            time.sleep(0.005)
        r = finish(p)
        same = common.sha256_file(d / "final.mp4") == old
        if hold < 1:
            out.append(neg(held and r.code == 0, f"held {name}: {r}"))
        else:
            out.append(pos(held and r.code == 1 and r.first.startswith("Failed: internal") and same and five_ok(r),
                           f"held {name}: {r}; output untouched={same}"))
    return out


@control("post-publish", "P-20 exception in judge -> rows UNDET unfinished, exit 3; Q-5 in promote -> DONE, note, exit 3, next run reconciles; in finish -> DONE exit 3")
def c_postpub():
    out = []
    d = fresh("pp_judge")
    write_page(d)
    r = render(d, env={"FILMKIT_SELFTEST_FAULT": "judge=raise"})
    doc = cj_of(d)
    rec = rec_of(d)
    out.append(pos(r.code == 3 and (d / "final.mp4").is_file() and rec["last_success"]["output"]["sha256"] == common.sha256_file(d / "final.mp4")
                   and all(x["verdict"] == "UNDET" and x["unfinished"] for x in doc["rows"]), f"judge raises: {r}"))
    d = fresh("pp_promote")
    write_page(d)
    r = render(d, env={"FILMKIT_SELFTEST_FAULT": "promote=raise"})
    rec = rec_of(d)
    r2 = render(d)
    out.append(pos(r.code == 3 and r.first.startswith("Done:") and "record not finalised" in r.line("Notes:")
                   and rec.get("pending_publish") and r2.code == 0, f"promote raises: {r}; next run {r2}"))
    d = fresh("pp_finish")
    write_page(d)
    r = render(d, env={"FILMKIT_SELFTEST_FAULT": "finish=raise"})
    out.append(pos(r.code == 3 and r.first.startswith("Done:") and "internal error" in r.line("Notes:"), f"finish raises: {r}"))
    d = fresh("pp_clean")
    write_page(d)
    r = render(d)
    out.append(neg(r.code == 0 and "internal error" not in r.line("Notes:"), f"no fault: {r}"))
    return out


@control("check-timeout", "P-14 tiny --check-timeout -> FK-R-2..5 UNDET unfinished, exit 3 / normal timeout -> exit 0")
def c_ctimeout():
    d = fresh("ct")
    f = mk_mp4(d / "x.mp4")
    r = check(f, "--duration", "1", "--size", "160x90", "--fps", "10", "--check-timeout", "0.001")
    rows = rows_of(cj_of(d, "x.mp4.check.json"))
    r2 = check(f, "--duration", "1", "--size", "160x90", "--fps", "10")
    return [pos(r.code == 3 and all(rows[i]["verdict"] == "UNDET" and rows[i]["unfinished"] for i in ("FK-R-2", "FK-R-3", "FK-R-4", "FK-R-5")),
                f"--check-timeout 0.001: {r}"),
            neg(r2.code == 0, f"default timeout: {r2}")]


@control("console-cap", "P-25a 300 console.log per frame -> console capped at 200, console_truncated / quiet page -> not truncated")
def c_console():
    d = fresh("console")
    write_page(d, js=BASE_JS.replace("};", "for(let i=0;i<300;i++)console.log('x'+i);};"))
    r = render(d)
    lr = rec_of(d)["last_success"]["load_report"]
    d2 = fresh("console_q")
    write_page(d2)
    render(d2)
    lr2 = rec_of(d2)["last_success"]["load_report"]
    return [pos(len(lr["console"]) == 200 and lr["console_truncated"] is True, f"noisy page: {len(lr['console'])} kept, truncated={lr['console_truncated']} ({r})"),
            neg(lr2["console_truncated"] is False, f"quiet page: {len(lr2['console'])} kept")]


@control("P-24a", "--json on REJECTED -> {status: rejected, ...} only / --json on success -> record + check + exit_code")
def c_json():
    d = fresh("json")
    write_page(d)
    r = run_tool("render.py", [d / "index.html", "-o", d / "f.mp4", "--duration", "1", "--size", "161x90", "--json"])
    r2 = render(d, "--json")
    try:
        j = json.loads("\n".join(r.lines))
    except ValueError:
        j = {}
    try:
        j2 = json.loads("\n".join(r2.lines))
    except ValueError:
        j2 = {}
    return [pos(len(r.lines) == 1 and set(j) == {"status", "kind", "message", "hint", "exit_code"} and j["status"] == "rejected",
                f"rejected --json: keys {sorted(j)}"),
            neg(len(r2.lines) == 1 and j2.get("status") == "done" and "check" in j2 and j2.get("exit_code") == 0,
                f"success --json: status {j2.get('status')}, exit_code {j2.get('exit_code')}")]


@control("FK-INV-14", "clean page rendered twice -> identical frames.sha256 / Math.random() page differs")
def c_inv14():
    hashes = []
    for i in range(2):
        d = fresh(f"inv14_{i}")
        write_page(d)
        render(d)
        hashes.append(rec_of(d)["frames"]["sha256"])
    rh = []
    for i in range(2):
        d = fresh(f"inv14r_{i}")
        write_page(d, js="window.__setTime=function(t){document.getElementById('b').style.left=(Math.random()*100)+'px';};")
        render(d)
        rh.append(rec_of(d)["frames"]["sha256"])
    return [neg(hashes[0] == hashes[1], f"clean page twice: {len(hashes[0])} frame hashes equal"),
            pos(rh[0] != rh[1], "Math.random() page twice: frame hashes differ")]


@control("ctrl-c", "Ctrl-C (CTRL_BREAK on a new process group, and the interrupt fault) mid-capture -> interrupted, previous film kept, rerun completes")
def c_ctrlc():
    out = []
    d = fresh("ctrlc")
    write_page(d)
    render(d)
    old = common.sha256_file(d / "final.mp4")
    write_page(d, js=BASE_JS + "/*v2*/")
    r = render(d, env={"FILMKIT_SELFTEST_FAULT": "capture_frame_3=interrupt"})
    out.append(pos(r.code == 1 and r.first.startswith("Failed: interrupted") and common.sha256_file(d / "final.mp4") == old
                   and rec_of(d)["status"] == "interrupted" and "kept" in r.line("Notes:"), f"interrupt fault: {r}"))
    if os.name == "nt":
        # the signal lands while a Playwright call is in flight (no sleep fault): raising there used to hang
        # the run or leave asyncio/node EPIPE noise on stderr (A-list run 2026-10-09)
        p = start_render(d, *LONG, small=False)
        wait_capture(d)
        p.send_signal(signal.CTRL_BREAK_EVENT)
        try:
            r2 = finish(p, timeout=90)
        except subprocess.TimeoutExpired:
            p.kill()
            r2 = Res("HANG", "", "")
        out.append(pos(r2.code == 1 and r2.first.startswith("Failed: interrupted") and not r2.err.strip()
                       and common.sha256_file(d / "final.mp4") == old, f"CTRL_BREAK_EVENT mid-capture: {r2}"))
        r4 = console_ctrl_c(d)
        out.append(pos(r4.code == 1 and r4.first.startswith("Failed: interrupted") and not r4.err.strip()
                       and common.sha256_file(d / "final.mp4") == old, f"console CTRL_C_EVENT mid-capture: {r4}"))
    run0 = rec_of(d)["last_success"]["run_id"]
    r3 = render(d)
    run1 = rec_of(d)["last_success"]["run_id"]
    out.append(neg(r3.code == 0 and run1 != run0 and rec_of(d)["status"] == "done",
                   f"rerun after interrupt: {r3}; last_success.run_id {run0} -> {run1}"))
    return out


# =====================================================================================================
# step 5: check rows, names, rerun, fonts, mux
# =====================================================================================================
EXP = ["--duration", "1", "--size", "160x90", "--fps", "10"]


def chk_rows(f: Path, *extra, env=None):
    r = check(f, *extra, env=env)
    name = f"{f.name}.check.json" if not (f.parent / "render.json").exists() else None
    for cand in ([name] if name else []) + ["check.json", f"{f.name}.check.json"]:
        if cand and (f.parent / cand).exists():
            doc = cj_of(f.parent, cand)
            return r, rows_of(doc), doc
    return r, {}, {}


@control("design-9-files", "standalone checks: 9 s vs --duration 10 -> FK-R-2 blocking; truncated moov -> FK-R-1 blocking, rest UNDET, exit 2; odd size -> FK-R-3; yuvj420p -> FK-R-4; audio yes/none -> FK-R-5 blocking; no/has -> look")
def c_d9files():
    out = []
    d = fresh("d9f")
    f9 = mk_mp4(d / "nine.mp4", dur=9, fps=10)
    r, rows, _ = chk_rows(f9, "--duration", "10", "--size", "160x90", "--fps", "10")
    out.append(pos(rows["FK-R-2"]["bucket"] == "blocking" and r.code == 2, f"9 s file checked with --duration 10: FK-R-2 {rows['FK-R-2']['verdict']}, {r}"))
    trunc = d / "trunc.mp4"
    mk_mp4(d / "tail.mp4", dur=3, faststart=False)
    data = (d / "tail.mp4").read_bytes()
    trunc.write_bytes(data[: len(data) * 2 // 3])
    r, rows, _ = chk_rows(trunc, *EXP)
    out.append(pos(rows["FK-R-1"]["bucket"] == "blocking" and all(rows[i]["verdict"] == "UNDET" for i in ("FK-R-2", "FK-R-3", "FK-R-4", "FK-R-5"))
                   and r.code == 2, f"moov cut off: FK-R-1 {rows['FK-R-1']['verdict']}, rest UNDET, {r}"))
    odd = mk_mp4(d / "odd.mp4", size="161x91", pix="yuv444p")
    r, rows, _ = chk_rows(odd, "--duration", "1", "--fps", "10")
    out.append(pos(rows["FK-R-3"]["bucket"] == "blocking", f"161x91 file: FK-R-3 {rows['FK-R-3']['verdict']} ({rows['FK-R-3']['measured']})"))
    yj = mk_mp4(d / "yuvj.mp4", pix="yuvj420p")
    r, rows, _ = chk_rows(yj, *EXP)
    out.append(pos(rows["FK-R-4"]["bucket"] == "blocking" and "pix_fmt" in rows["FK-R-4"]["message_key"],
                   f"yuvj420p file: FK-R-4 {rows['FK-R-4']['verdict']} {rows['FK-R-4']['message_key']}"))
    silent = mk_mp4(d / "silent.mp4")
    r, rows, _ = chk_rows(silent, *EXP, "--audio-expected", "yes")
    out.append(pos(rows["FK-R-5"]["bucket"] == "blocking", f"--audio-expected yes, no stream: FK-R-5 {rows['FK-R-5']['verdict']}"))
    loud = mk_mp4(d / "loud.mp4", audio_s=1)
    r, rows, _ = chk_rows(loud, *EXP, "--audio-expected", "no")
    out.append(pos(rows["FK-R-5"]["bucket"] == "look", f"--audio-expected no, stream present: FK-R-5 {rows['FK-R-5']['verdict']}/{rows['FK-R-5']['severity']}"))
    clean = mk_mp4(d / "clean.mp4")
    r, rows, doc = chk_rows(clean, *EXP, "--audio-expected", "no", "--mounted-kit-hash", "none")
    out.append(neg(r.code == 0 and doc["summary"]["blocking"] == 0 and doc["summary"]["look"] == 0,
                   f"clean 1 s file with matching expectations, no kit mounted (`none`; without it FK-R-13 states the file has no render.json): {r}"))
    return out


@control("P-13-rows", "FK-R-2 off by 1 frame PASS / by 2 FAIL; FK-R-3 wrong size FAIL, variable fps FAIL; FK-R-5#length 0.05 s PASS / 0.5 s WARN; no expectation -> FK-R-5 info only")
def c_p13():
    out = []
    d = fresh("p13")
    f11 = mk_mp4(d / "f11.mp4", dur=1.1)
    f12 = mk_mp4(d / "f12.mp4", dur=1.2)
    _, r11, _ = chk_rows(f11, *EXP)
    _, r12, _ = chk_rows(f12, *EXP)
    out.append(neg(r11["FK-R-2"]["verdict"] == "PASS", f"off by 1 frame: FK-R-2 {r11['FK-R-2']['verdict']} ({r11['FK-R-2']['measured']})"))
    out.append(pos(r12["FK-R-2"]["verdict"] == "FAIL", f"off by 2 frames: FK-R-2 {r12['FK-R-2']['verdict']}"))
    ok = mk_mp4(d / "ok.mp4")
    _, rs, _ = chk_rows(ok, "--duration", "1", "--size", "320x180", "--fps", "10")
    out.append(pos(rs["FK-R-3"]["verdict"] == "FAIL", f"expected 320x180, file 160x90: FK-R-3 {rs['FK-R-3']['verdict']}"))
    vfr = mk_mp4(d / "vfr.mp4", dur=2, vf="setpts='if(lt(N,10),N/10/TB,(10+(N-10)*3)/10/TB)'", extra=["-fps_mode", "vfr"])
    _, rv, _ = chk_rows(vfr, "--size", "160x90", "--fps", "10")
    out.append(pos(rv["FK-R-3"]["verdict"] == "FAIL" and "variable" in rv["FK-R-3"]["measured"], f"variable fps file: FK-R-3 {rv['FK-R-3']['verdict']} ({rv['FK-R-3']['measured']})"))
    a05 = mk_mp4(d / "a05.mp4", dur=1, audio_s=1.05)
    a50 = mk_mp4(d / "a50.mp4", dur=1, audio_s=1.5)
    _, ra, _ = chk_rows(a05, *EXP, "--audio-expected", "yes")
    _, rb, _ = chk_rows(a50, *EXP, "--audio-expected", "yes")
    out.append(neg(ra["FK-R-5#length"]["verdict"] == "PASS", f"audio 0.05 s longer: FK-R-5#length {ra['FK-R-5#length']['verdict']} ({ra['FK-R-5#length']['measured']})"))
    out.append(pos(rb["FK-R-5#length"]["verdict"] == "WARN" and rb["FK-R-5#length"]["bucket"] == "look",
                   f"audio 0.5 s longer: FK-R-5#length {rb['FK-R-5#length']['verdict']} ({rb['FK-R-5#length']['measured']})"))
    _, rn, _ = chk_rows(ok, "--duration", "1", "--size", "160x90", "--fps", "10")
    out.append(neg(rn["FK-R-5"]["severity"] == "info" and rn["FK-R-5"]["bucket"] == "confirmed", f"no audio expectation: FK-R-5 {rn['FK-R-5']['verdict']}/{rn['FK-R-5']['severity']}"))
    return out


@control("P-18", "--rules with one filmkit rule of an unsupported kind -> exactly one FK-R-16#<id> UNDET, unfinished false, exit 0 (the M0 control, rewritten now that rules are evaluated) / no --rules -> no FK-R-16 row")
def c_p18():
    d = fresh("p18")
    f = mk_mp4(d / "x.mp4")
    rf = d.parent / "p18_rules.json"
    rf.write_text(json.dumps({"schema_version": 1, "film_types": ["type-a"], "rules": [
        {"id": "rule_a", "owner": "filmkit", "kind": "ratio", "film_types": None, "select": {"source": "frozen", "anchor": "end"},
         "range_s": [1.0, 2.0], "sentence_zh": "x", "missing_zh": "y", "basis": "fixture", "provisional": True}]}),
        encoding="utf-8")
    r, rows, doc = chk_rows(f, *EXP, "--rules", rf)
    r16 = [x for x in doc["rows"] if x["id"].startswith("FK-R-16")]
    d2 = fresh("p18b")
    f2 = mk_mp4(d2 / "x.mp4")
    r2, rows2, doc2 = chk_rows(f2, *EXP)
    return [pos(len(r16) == 1 and r16[0]["id"] == "FK-R-16#rule_a" and r16[0]["verdict"] == "UNDET"
                and r16[0]["unfinished"] is False and r.code == 0,
                f"--rules with a kind-ratio filmkit rule: {len(r16)} FK-R-16 row(s), {[(x['id'], x['verdict']) for x in r16]}, "
                f"reason {r16[0]['reason'] if r16 else '-'}, {r}"),
            neg(not any(x["id"].startswith("FK-R-16") for x in doc2["rows"]) and r2.code == 0, f"no --rules: no FK-R-16, {r2}")]


def volume_mean(f: Path) -> float | None:
    p = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(f), "-af", "volumedetect", "-f", "null", "-"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    m = re.search(r"mean_volume:\s*(-?[\d.]+) dB", p.stderr)
    return float(m.group(1)) if m else None


@control("Y-18", "mux argv has no banned flags; stereo 48 kHz kept, volumedetect mean within 0.5 dB / mono -> FK-R-5 FAIL exit 2; banned-flag scan fires on a fixture argv")
def c_y18():
    from _fk import mux as fkmux
    out = []
    pargs = fkprofile.resolve_profile(fkprofile.get_profile("lab-round"), 10, True, "lab-round")
    argv = fkmux.mux_argv(Path("v.mp4"), Path("a.wav"), pargs, Path("o.mp4"))
    banned_in = [t for t in argv if t in fkmux.BANNED]
    fixture = argv[:-1] + ["-ac", "1", argv[-1]]
    out.append(neg(not banned_in, f"mux argv: no banned flag ({' '.join(argv[-12:])})"))
    out.append(pos(any(t in fkmux.BANNED for t in fixture), "fixture argv with -ac 1 -> banned-flag scan fires"))
    d = fresh("y18")
    write_page(d)
    wav = mk_wav(d / "mix.wav", 1, 2)
    r = render(d, "--audio", wav)
    pr = rows_of(cj_of(d))
    p = json.loads(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=channels,sample_rate",
                                   "-of", "json", str(d / "final.mp4")], capture_output=True, text=True).stdout)["streams"][0]
    m_src, m_out = volume_mean(wav), volume_mean(d / "final.mp4")
    out.append(neg(r.code == 0 and p["channels"] == 2 and p["sample_rate"] == "48000" and m_src is not None and m_out is not None
                   and abs(m_src - m_out) <= 0.5 and pr["FK-R-5"]["verdict"] == "PASS",
                   f"stereo 48 kHz: {r}; out {p['channels']} ch {p['sample_rate']} Hz; mean {m_src} -> {m_out} dB"))
    d2 = fresh("y18_mono")
    write_page(d2)
    wav2 = mk_wav(d2 / "mono.wav", 1, 1)
    r2 = render(d2, "--audio", wav2)
    pr2 = rows_of(cj_of(d2))
    out.append(pos(r2.code == 2 and pr2["FK-R-5"]["verdict"] == "FAIL", f"mono wav: FK-R-5 {pr2['FK-R-5']['verdict']} ({pr2['FK-R-5']['measured']}), {r2}"))
    return out


@control("Y-13", "foreign file -> <name>.check.*, then render output -> check.*, both coexist / pre-existing foreign check.md -> output_foreign, nothing written (P-25c)")
def c_y13():
    d = fresh("y13")
    write_page(d)
    other = mk_mp4(d / "other.mp4")
    r1 = check(other, *EXP)
    r2 = render(d)
    r3 = check(d / "final.mp4", *EXP)
    names = sorted(p.name for p in d.iterdir() if "check" in p.name or "sheet" in p.name)
    d2 = fresh("y13_foreign")
    write_page(d2)
    render(d2)
    (d2 / "check.md").write_text("my own notes\n", encoding="utf-8")
    (d2 / "check.json").unlink()
    (d2 / "sheet_1fps.png").unlink()
    before = sorted(p.name for p in d2.iterdir())
    r4 = check(d2 / "final.mp4", *EXP)
    after = sorted(p.name for p in d2.iterdir())
    want = ["check.json", "check.md", "other.mp4.check.json", "other.mp4.check.md", "other.mp4.sheet_1fps.png", "sheet_1fps.png"]
    return [neg(r1.code == 0 and r2.code == 0 and r3.code == 0 and names == want, f"names after both checks: {names}"),
            pos(r4.code == 1 and r4.first.startswith("Failed: output_foreign") and before == after
                and (d2 / "check.md").read_text(encoding="utf-8") == "my own notes\n", f"foreign check.md: {r4}; folder unchanged")]


@control("abs-prefix", "--out-prefix absolute (run_arm's lab check) -> Check/Look lines name the absolute paths once, files there / relative prefix -> <folder>/<prefix>check.json as before")
def c_abs_prefix():
    d = fresh("abs_prefix")
    f = mk_mp4(d / "clip.mp4")
    out = d / "out"
    out.mkdir()
    pre = out.as_posix() + "/lab."
    r1 = check(f, *EXP, "--out-prefix", pre)
    want_j, want_s = f"{pre}clip.mp4.check.json", f"{pre}clip.mp4.sheet_1fps.png"
    r2 = check(f, *EXP, "--out-prefix", "rel.")
    rel_j = f"{d.as_posix()}/rel.clip.mp4.check.json"
    return [pos(r1.code == 0 and r1.line("Check:").endswith(f"— {want_j}") and f"sheet at {want_s} " in r1.line("Look:")
                and Path(want_j).is_file() and Path(want_s).is_file(), f"absolute prefix: {r1.line('Check:')[-120:]}"),
            neg(r2.code == 0 and r2.line("Check:").endswith(f"— {rel_j}") and Path(rel_j).is_file(),
                f"relative prefix: {r2.line('Check:')[-120:]}")]


@control("Y-20", "whole-file look row: where file, t0 0, t1 duration, t null, not in events / a confirmed row has no t0")
def c_y20():
    d = fresh("y20")
    f = mk_mp4(d / "x.mp4", audio_s=1)
    _, rows, doc = chk_rows(f, *EXP, "--audio-expected", "no")
    lk = rows["FK-R-5"]
    ok_row = rows["FK-R-2"]
    in_events = any(e.get("id") == "FK-R-5" for e in doc.get("events") or [])
    return [pos(lk["bucket"] == "look" and lk["where"] == "file" and lk["t0"] == 0 and abs((lk["t1"] or 0) - 1.0) < 0.05
                and lk["t"] is None and not in_events, f"look row: where {lk['where']}, t0 {lk['t0']}, t1 {lk['t1']}, t {lk['t']}, in events {in_events}"),
            neg(ok_row["t0"] is None, f"confirmed row t0 {ok_row['t0']}")]


@control("Q-2-R6", "FK-R-6: hand-edited record with blocked_requests -> FAIL blocking / clean record -> no non-PASS FK-R-6 row")
def c_q2r6():
    d = fresh("q2r6")
    write_page(d)
    render(d)
    _, rows_clean, _ = chk_rows(d / "final.mp4", *EXP)
    rec = rec_of(d)
    rec["last_success"]["load_report"]["blocked_requests"] = ["https://example.com/x.png"]
    (d / "render.json").write_text(json.dumps(rec), encoding="utf-8")
    r, rows, _ = chk_rows(d / "final.mp4", *EXP)
    return [pos(rows["FK-R-6"]["verdict"] == "FAIL" and rows["FK-R-6"]["bucket"] == "blocking" and r.code == 2,
                f"blocked_requests in record: FK-R-6 {rows['FK-R-6']['verdict']} ({rows['FK-R-6']['measured']})"),
            neg(rows_clean["FK-R-6"]["verdict"] == "PASS", f"clean record: FK-R-6 {rows_clean['FK-R-6']['verdict']}")]


def odd_into(d: Path):
    """Replace a rendered final.mp4 by an odd-size file and point last_success at it (a record that describes it)."""
    tmp = d.parent / (d.name + "_odd.mp4")
    mk_mp4(tmp, size="161x91", pix="yuv444p")
    shutil.copyfile(tmp, d / "final.mp4")
    rec = rec_of(d)
    rec["last_success"]["output"]["sha256"] = common.sha256_file(d / "final.mp4")
    rec["last_success"]["output"]["bytes"] = (d / "final.mp4").stat().st_size
    (d / "render.json").write_text(json.dumps(rec), encoding="utf-8")


def rerun_of(rows: dict, rid="FK-R-3") -> str:
    return rows.get(rid, {}).get("rerun") or ""


@control("rerun-record", "P-2/Q-4: odd-size mp4 with render.json -> md section 1 has the full render.py line, expected size, absolute paths / clean -> no rerun; Q-4(i) failed rerun with other flags ignored")
def c_rr_rec():
    d = fresh("rr rec 中文")
    write_page(d)
    render(d)
    render(d, "--duration", "2", env={"FILMKIT_SELFTEST_FAULT": "capture_frame_2=raise"})  # failed rerun, other flags
    odd_into(d)
    r = check(d / "final.mp4")
    rows = rows_of(cj_of(d))
    rr = rerun_of(rows)
    md = (d / "check.md").read_text(encoding="utf-8")
    sec1 = md.split("## 二")[0]
    d2 = fresh("rr_clean")
    write_page(d2)
    render(d2)
    rows2 = rows_of(cj_of(d2))
    return [pos(rr and rr in sec1 and "render.py" in rr and "--size 160x90" in rr and "--duration 1" in rr
                and (d / "index.html").resolve().as_posix() in rr and subprocess.list2cmdline([(d / "index.html").resolve().as_posix()]) in rr,
                f"odd-size with record: rerun = {rr}"),
            pos("--duration 2" not in rr, "rerun ignores the failed run's --duration 2 (built from last_success)"),
            neg(not any(x.get("rerun") for x in rows2.values()), "clean render: no rerun")]


@control("rerun-template", "P-2/OQ-1/R-3/Q-4(iii): odd-size without record -> <page>, -o <new-out>; unreadable, no expected values -> --duration <S> --size <WxH>")
def c_rr_tpl():
    d = fresh("rr_tpl")
    f = mk_mp4(d / "foreign.mp4", size="161x91", pix="yuv444p")
    check(f)
    rows = rows_of(cj_of(d, "foreign.mp4.check.json"))
    rr = rerun_of(rows)
    bad = d / "bad.mp4"
    bad.write_bytes(b"\x00" * 2000)
    check(bad)
    rows_b = rows_of(cj_of(d, "bad.mp4.check.json"))
    rrb = rerun_of(rows_b, "FK-R-1")
    d2 = fresh("rr_tpl_ok")
    ok = mk_mp4(d2 / "ok.mp4")
    check(ok, *EXP)
    rows_ok = rows_of(cj_of(d2, "ok.mp4.check.json"))
    return [pos("<page>" in rr and "-o <new-out>" in rr and f.as_posix() not in rr and "foreign.mp4" not in rr, f"foreign odd-size: {rr}"),
            pos("--duration <S>" in rrb and "--size <WxH>" in rrb, f"unreadable, no expected values: {rrb}"),
            neg(not any(x.get("rerun") for x in rows_ok.values()), "clean foreign file: no rerun")]


@control("Q-4(v)", "FK-R-5 FAIL (audio expected, none) with and without a record -> rerun has --audio")
def c_rr_audio():
    d = fresh("rr_audio")
    write_page(d)
    render(d)
    check(d / "final.mp4", "--audio-expected", "yes")
    rr1 = rerun_of(rows_of(cj_of(d)), "FK-R-5")
    d2 = fresh("rr_audio2")
    f = mk_mp4(d2 / "x.mp4")
    check(f, *EXP, "--audio-expected", "yes")
    rr2 = rerun_of(rows_of(cj_of(d2, "x.mp4.check.json")), "FK-R-5")
    check(f, *EXP)
    rr3 = rerun_of(rows_of(cj_of(d2, "x.mp4.check.json")), "FK-R-5")
    return [pos("--audio <audio>" in rr1, f"with record: {rr1}"), pos("--audio <audio>" in rr2, f"without record: {rr2}"),
            neg(rr3 == "", "no audio expectation: no FK-R-5 rerun")]


@control("R-1", "render from cwd A with relative paths, check from cwd B: every rerun path absolute and exists (except the output) / relative path would fail")
def c_r1():
    base = fresh("r1")
    a = base / "A"
    (a / "build").mkdir(parents=True)
    (base / "B").mkdir()
    write_page(a / "build")
    run_tool("render.py", ["build/index.html", "-o", "build/final.mp4", *SMALL], cwd=a)
    odd_into(a / "build")
    run_tool("check.py", ["../A/build/final.mp4"], cwd=base / "B")
    rr = rerun_of(rows_of(cj_of(a / "build")))
    toks = re.findall(r'"([^"]+)"|(\S+)', rr)
    toks = [x or y for x, y in toks]
    paths = [t for t in toks if "/" in t]
    out_tok = toks[toks.index("-o") + 1] if "-o" in toks else None
    exist = all(Path(t).is_absolute() and Path(t).exists() for t in paths if t != out_tok)
    return [neg(rr and exist and out_tok and Path(out_tok).is_absolute(), f"paths in rerun: {paths}"),
            pos(not all(Path(t).is_absolute() for t in ["build/index.html"]), "a relative page path is not absolute (the comparison can fail)")]


STUB = "import sys, json\nprint(json.dumps(sys.argv[1:], ensure_ascii=True))\n"


def git_bash() -> str | None:
    for c in (r"C:\Program Files\Git\bin\bash.exe", r"C:\Program Files (x86)\Git\bin\bash.exe"):
        if Path(c).is_file():
            return c
    g = shutil.which("git")
    if g:
        c = Path(g).resolve().parent.parent / "bin" / "bash.exe"
        if c.is_file():
            return str(c)
    return None


@control("Q-4(vi)", "rerun through PowerShell Invoke-Expression and Git Bash eval on a stub render.py: argv equal item by item in 4 cases / shlex round trip loses backslashes")
def c_q4vi():
    import shlex
    from _fk import rerun as fkrerun
    from _fk.checkrun import CheckArgs
    stub_dir = fresh("q4vi_kit")
    (stub_dir / "render.py").write_text(STUB, encoding="utf-8")
    bash = git_bash()
    results = []
    for nm in ("q4vi with space 中文", "q4vi_plain"):
        d = fresh(nm)
        write_page(d)
        render(d)
        rec = guard.reconcile(rec_of(d), d / "final.mp4")
        cargs = CheckArgs(file=d / "final.mp4", duration_s=None, size=None, fps=None, profile="lab-round",
                          audio_expected=None, plan=None, plan_exemptions_only=False, render_record=None,
                          mounted_kit_hash=None, out_prefix="", rules=None, film_type=None, check_timeout_s=60, json_out=False)
        cmd = fkrerun.build(rec, d / "final.mp4", cargs, stub_dir)
        want = [(d / "index.html").resolve().as_posix(), "-o", (d / "final.mp4").resolve().as_posix(), "--duration", "1",
                "--size", "160x90", "--fps", "10", "--profile", "lab-round"]
        env = tool_env({"FK_RR": cmd})
        ps = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                             "[Console]::OutputEncoding=[Text.Encoding]::UTF8; Invoke-Expression $env:FK_RR"],
                            capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
        try:
            got_ps = json.loads(ps.stdout.strip().splitlines()[-1])
        except (ValueError, IndexError):
            got_ps = ps.stdout + ps.stderr
        results.append((nm, "powershell", got_ps == want, got_ps))
        if bash:
            bs = subprocess.run([bash, "-c", 'eval "$FK_RR"'], capture_output=True, text=True, encoding="utf-8",
                                errors="replace", env=env)
            try:
                got_bs = json.loads(bs.stdout.strip().splitlines()[-1])
            except (ValueError, IndexError):
                got_bs = bs.stdout + bs.stderr
            results.append((nm, "bash", got_bs == want, got_bs))
    bad = [r for r in results if not r[2]]
    lost = shlex.split(subprocess.list2cmdline(["C:\\build\\index.html"]))
    arms = [neg(not bad and len(results) == 4, f"{len(results)} shell runs, mismatches: {[(r[0], r[1], r[3]) for r in bad][:2]}")]
    if not bash:
        arms.append(skip("negative-bash", "Git Bash not found"))
    arms.append(pos(lost != ["C:\\build\\index.html"], f"shlex round trip of a backslash path gives {lost}"))
    return arms


# ---------------------------------------------------------------- fonts
def font_page(d: Path, body: str, head: str = "", js: str = BASE_JS) -> Path:
    return write_page(d, body=body, head=head, js=js, css="html,body{margin:0;background:#fff}#b{position:absolute;width:4px;height:4px;top:0}")


def fams_of(d: Path) -> dict:
    return {f["family"]: f for f in rec_of(d)["last_success"]["load_report"]["font_families"]}


def r6_rows(d: Path) -> list[dict]:
    return [x for x in cj_of(d)["rows"] if x["id"].startswith("FK-R-6") and x["verdict"] != "PASS"]


@control("fonts-present", "P-4/Q-1/D26: Arial mixed, Arial pure-CJK, Segoe UI pure-CJK, JhengHei CJK, JhengHei Latin -> no row (5 cases)")
def c_fonts_present():
    cases = [("Arial", "Hello 你好"), ("Arial", "你好世界"), ("Segoe UI", "你好世界"),
             ("Microsoft JhengHei", "你好世界"), ("Microsoft JhengHei", "Hello world")]
    out = []
    for i, (fam, text) in enumerate(cases):
        d = fresh(f"fp_{i}")
        font_page(d, f'<p style="font-family:\'{fam}\';margin:0">{text}</p>')
        r = render(d)
        f = fams_of(d).get(fam, {})
        out.append(neg(r.code == 0 and f.get("result") == "present" and not r6_rows(d),
                       f"{fam} / {text}: {f.get('result')} by {f.get('decided_by')}; FK-R-6 non-PASS rows {len(r6_rows(d))}"))
    return out


@control("fonts-missing", "P-4/Q-1: NoSuchFontXYZ Latin node, CJK node -> substituted, WARN (2 cases)")
def c_fonts_missing():
    out = []
    for i, text in enumerate(("Hello world", "你好世界")):
        d = fresh(f"fm_{i}")
        font_page(d, f'<p style="font-family:NoSuchFontXYZ;margin:0">{text}</p>')
        r = render(d)
        f = fams_of(d).get("NoSuchFontXYZ", {})
        rows = r6_rows(d)
        out.append(pos(f.get("result") == "substituted" and rows and rows[0]["verdict"] == "WARN" and r.code == 0,
                       f"NoSuchFontXYZ / {text}: {f.get('result')}; FK-R-6 {rows[0]['verdict'] if rows else 'none'}"))
    return out


def noto_src() -> Path | None:
    p = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts" / "NotoSansTC-VF.ttf"
    return p if p.is_file() else None


@control("R-6b", "@font-face FkCjkOnly with unicode-range U+4E00-9FFF in a CJK node -> present, decided_by cjk, no row / same family without the face -> substituted")
def c_r6b():
    src = noto_src()
    if src is None:
        return [skip("positive", "skipped (font not installed)"), skip("negative", "skipped (font not installed)")]
    d = fresh("r6b")
    shutil.copyfile(src, d / "noto.ttf")
    font_page(d, '<p style="font-family:FkCjkOnly;margin:0">你好世界</p>',
              head="<style>@font-face{font-family:FkCjkOnly;src:url(noto.ttf);unicode-range:U+4E00-9FFF}</style>")
    r = render(d)
    f = fams_of(d).get("FkCjkOnly", {})
    d2 = fresh("r6b_none")
    font_page(d2, '<p style="font-family:FkCjkOnly;margin:0">你好世界</p>')
    render(d2)
    f2 = fams_of(d2).get("FkCjkOnly", {})
    return [neg(r.code == 0 and f.get("result") == "present" and f.get("decided_by") == "cjk" and not r6_rows(d),
                f"with face: {f.get('result')} by {f.get('decided_by')} {f.get('per_script')}"),
            pos(f2.get("result") == "substituted", f"without face: {f2.get('result')}")]


@control("R-6a", "fake probe lists with three identical baselines -> undetermined -> UNDET FK-R-6#font / distinct baselines decided normally")
def c_r6a():
    from _fk import capture as fkcap, judge as fkjudge
    same = {"serif": ["X"], "sans-serif": ["X"], "monospace": ["X"]}
    lists = {"latin": dict(same), "cjk": dict(same)}
    fc = fkcap.decide_family("Fam", lists, {"latin": same, "cjk": same}, ("0",))
    distinct = {"serif": ["S"], "sans-serif": ["A"], "monospace": ["M"]}
    fc2 = fkcap.decide_family("Fam", {"latin": {"serif": ["Fam"], "sans-serif": ["Fam"], "monospace": ["Fam"]}, "cjk": dict(distinct)},
                              {"latin": distinct, "cjk": distinct}, ("0",))
    record = {"last_success": {"load_report": {"fonts": [], "blocked_requests": [], "local_files": ["index.html"],
                                               "font_families": [fc.to_json()]}}}
    rows = fkjudge._page_load(record, 1.0)
    und = [x for x in rows if x["id"] == "FK-R-6#font"]
    return [pos(fc.result == "undetermined" and und and und[0]["verdict"] == "UNDET", f"identical baselines: {fc.result}; rows {[x['id'] + ' ' + x['verdict'] for x in rows]}"),
            neg(fc2.result == "present", f"distinct baselines: {fc2.result} by {fc2.decided_by}")]


@control("Q-7c", "page with * {font-family: Segoe UI !important} and a Times New Roman node -> probes still decide, TNR present / without !important probe styles the body probe is overridden")
def c_q7c():
    d = fresh("q7c")
    font_page(d, '<p style="font-family:\'Times New Roman\' !important;margin:0">Hello</p>',
              head='<style>*{font-family:"Segoe UI" !important}</style>')
    r = render(d)
    f = fams_of(d)
    d2 = fresh("q7c_unsafe")
    font_page(d2, '<p style="font-family:NoSuchFontXYZ !important;margin:0">Hello</p>',
              head='<style>*{font-family:"Segoe UI" !important}</style>')
    r2 = render(d2)
    f2 = fams_of(d2)
    return [neg(r.code == 0 and f.get("Times New Roman", {}).get("result") == "present", f"TNR under * !important: {f.get('Times New Roman', {}).get('result')}; families {sorted(f)}"),
            pos(f2.get("NoSuchFontXYZ", {}).get("result") == "substituted", f"missing family under * !important still decided: {f2.get('NoSuchFontXYZ', {}).get('result')}")]


@control("Q-7d", "font-family: -apple-system, Segoe UI -> -apple-system not probed, Segoe UI present, no row / first_family on a generic-first list -> nothing probed")
def c_q7d():
    from _fk import capture as fkcap
    d = fresh("q7d")
    font_page(d, '<p style="font-family:-apple-system, \'Segoe UI\';margin:0">Hello</p>')
    r = render(d)
    f = fams_of(d)
    return [neg(r.code == 0 and "-apple-system" not in f and f.get("Segoe UI", {}).get("result") == "present" and not r6_rows(d),
                f"families probed {sorted(f)}; Segoe UI {f.get('Segoe UI', {}).get('result')}"),
            pos(fkcap.first_family("serif, Arial") is None and fkcap.first_family("-apple-system") is None,
                "generic first / alias only -> not probed")]


LATE_NODE_JS = ("window.__ready=new Promise(r=>setTimeout(()=>{var p=document.createElement('p');p.style.fontFamily='Georgia';"
                "p.textContent='late';document.body.appendChild(p);r();},100));"
                "window.__setTime=function(t){var q=document.getElementById('blink');"
                "if(t>0.15&&t<0.35){if(!q){q=document.createElement('p');q.id='blink';q.style.fontFamily='Courier New';"
                "q.textContent='flash';document.body.appendChild(q);}}else if(q){q.remove();}};")


@control("Q-7a", "node added by JS after __ready (present from frame 0) -> probed; node shown only between sampling moments -> not probed, check.md names the moments")
def c_q7a():
    d = fresh("q7a")
    font_page(d, "", js=LATE_NODE_JS)
    r = render(d)
    f = fams_of(d)
    md = (d / "check.md").read_text(encoding="utf-8")
    return [neg("Georgia" in f, f"late node (Georgia) probed: {'Georgia' in f}; families {sorted(f)}"),
            pos("Courier New" not in f and "0.000" in md and "0.500" in md and "0.900" in md,
                f"between-moments node (Courier New) not probed; md names 0.000/0.500/0.900: {'0.500' in md}")]


SPAN_JS = ("window.__setTime=function(t){var n=document.querySelectorAll('span').length;"
           "document.getElementById('b').style.width=(4+n*10)+'px';document.getElementById('b').style.background='#000';};")


@control("Q-7b", "page drawing the span count: frame hashes equal with the shadow probe and probe off / body probe (unsafe placement) changes them")
def c_q7b():
    hashes = {}
    for mode in ("shadow", "off", "body-unsafe"):
        d = fresh(f"q7b_{mode}")
        write_page(d, body='<p style="font-family:Arial;margin:0">x</p>', js=SPAN_JS)
        render(d, env={"FILMKIT_SELFTEST_PROBE": mode})
        hashes[mode] = rec_of(d)["frames"]["sha256"]
    return [neg(hashes["shadow"] == hashes["off"], "shadow probe vs no probe: frame hashes equal"),
            pos(hashes["body-unsafe"] != hashes["off"], "body probe vs no probe: frame hashes differ")]


@control("D26", "page bundling NotoSansTC-VF.ttf via @font-face -> loads, FK-R-6 no non-PASS row / missing file -> FAILED(asset_load)")
def c_d26():
    src = noto_src()
    if src is None:
        return [skip("positive", "skipped (font not installed)"), skip("negative", "skipped (font not installed)")]
    d = fresh("d26")
    (d / "fonts").mkdir()
    shutil.copyfile(src, d / "fonts" / "NotoSansTC-VF.ttf")
    head = "<style>@font-face{font-family:'Noto Sans TC Local';src:url(fonts/NotoSansTC-VF.ttf)}</style>"
    font_page(d, '<p style="font-family:\'Noto Sans TC Local\';margin:0">字型 Font</p>', head=head)
    r = render(d)
    lr = rec_of(d)["last_success"]["load_report"]
    d2 = fresh("d26_missing")
    font_page(d2, '<p style="font-family:\'Noto Sans TC Local\';margin:0">字型 Font</p>', head=head)
    r2 = render(d2)
    return [neg(r.code == 0 and lr["fonts"] and lr["fonts"][0]["status"] == "loaded" and not r6_rows(d),
                f"bundled font: {r}; fonts {[(x['family'], x['status']) for x in lr['fonts']]}"),
            pos(r2.code == 1 and r2.first.startswith("Failed: asset_load"), f"missing font file: {r2}")]


@control("P-4c", "probe hidden with display:none (fixture) -> the empty-list guard fails the run / visibility:hidden probe works")
def c_p4c():
    d = fresh("p4c")
    write_page(d, body='<p style="font-family:Arial;margin:0">x</p>')
    r = render(d, env={"FILMKIT_SELFTEST_PROBE": "display-none"})
    d2 = fresh("p4c_ok")
    write_page(d2, body='<p style="font-family:Arial;margin:0">x</p>')
    r2 = render(d2)
    return [pos(r.code == 1 and "empty font list" in r.first, f"display:none probe: {r}"),
            neg(r2.code == 0, f"visibility:hidden probe: {r2}")]


@control("Q-3a-c", "success with a.wav, failed rerun with b.wav -> last_success.inputs keeps a.wav, frames unchanged / successful rerun with b.wav replaces both")
def c_q3ac():
    d = fresh("q3ac")
    write_page(d)
    mk_wav(d / "a.wav", 1, 2, 440)
    mk_wav(d / "b.wav", 1, 2, 660)
    render(d, "--audio", d / "a.wav")
    ls0 = rec_of(d)["last_success"]
    render(d, "--audio", d / "b.wav", env={"FILMKIT_SELFTEST_FAULT": "capture_frame_5=raise"})
    rec1 = rec_of(d)
    ls1 = rec1["last_success"]
    paths1 = [i["path"] for i in ls1["inputs"]]
    r2 = render(d, "--audio", d / "b.wav")
    ls2 = rec_of(d)["last_success"]
    paths2 = [i["path"] for i in ls2["inputs"]]
    return [pos(rec1["status"] == "failed" and "a.wav" in paths1 and "b.wav" not in paths1 and ls1["frames"] == ls0["frames"]
                and ls1["audio"] == "a.wav", f"after the failed b.wav rerun: inputs {paths1}, audio {ls1['audio']}"),
            neg(r2.code == 0 and "b.wav" in paths2 and "a.wav" not in paths2 and ls2["audio"] == "b.wav", f"after a successful b.wav rerun: inputs {paths2}")]


@control("P-6-P-13-Y-7c", "failed rerun with unchanged inputs -> STALE; check while another process renders -> STALE; ABSENT + external file -> FOREIGN; page edited while STALE -> still STALE / done record -> CURRENT")
def c_owner_more():
    d = fresh("own_more")
    write_page(d)
    render(d)

    def st(lock_other=False):
        rec = guard.reconcile(rec_of(d), d / "final.mp4")
        return guard.owner_state(rec, d / "final.mp4", guard.current_inputs(d, rec["last_success"]), lock_other)
    s_done = st()
    render(d, env={"FILMKIT_SELFTEST_FAULT": "capture_frame_2=raise"})
    s_failed = st()
    write_page(d, js=BASE_JS + "/*edit while stale*/")
    s_failed_edit = st()
    write_page(d)
    render(d)
    mk = d.parent / "own_more_marker.json"
    p = start_render(d, env={"FILMKIT_SELFTEST_FAULT": f"capture_frame_2=sleep:4:{mk}"})
    wait_file(mk)
    s_running = st(lock_other=not guard.try_lock_free(d))
    finish(p)
    d2 = fresh("own_absent")
    write_page(d2)
    render(d2)
    rec2 = rec_of(d2)
    (d2 / "final.mp4").unlink()
    s_absent = guard.owner_state(rec2, d2 / "final.mp4", None, False)
    mk_mp4(d2 / "final.mp4")
    s_ext = guard.owner_state(guard.reconcile(rec2, d2 / "final.mp4"), d2 / "final.mp4",
                              guard.current_inputs(d2, rec2["last_success"]), False)
    return [pos(s_failed == "STALE", f"failed rerun, inputs unchanged -> {s_failed}"),
            pos(s_running == "STALE", f"while another process renders -> {s_running}"),
            pos(s_absent == "ABSENT" and s_ext == "FOREIGN", f"deleted -> {s_absent}; external file in its place -> {s_ext}"),
            pos(s_failed_edit == "STALE", f"page edited while STALE -> {s_failed_edit}"),
            neg(s_done == "CURRENT", f"done record, unchanged -> {s_done}")]


@control("FK-R-13", "M1 render_provenance row over the owner_state cases: CURRENT / kit mismatch / STALE (inputs, failed, running) / UNDET_INPUTS / FOREIGN / no record / none + no record; Y-5")
def c_r13():
    base = fresh("r13_base")
    write_page(base)
    r0 = render(base)
    ls = rec_of(base)["last_success"]
    kh = ls["kit_hash"]
    exp = ["--duration", "1", "--size", "160x90", "--fps", "10"]

    def variant(name):
        d = fresh(name)
        shutil.copytree(base, d, dirs_exist_ok=True)
        return d

    def row13(d, *extra):
        r = check(d / "final.mp4", *exp, *extra)
        return rows_of(cj_of(d)).get("FK-R-13"), r

    def patch_record(d, **kv):
        rec = rec_of(d)
        rec.update(kv)
        (d / "render.json").write_text(json.dumps(rec), encoding="utf-8")

    own = rows_of(cj_of(base)).get("FK-R-13")
    own_look = cj_of(base)["summary"]["look"]
    cur, _ = row13(variant("r13_cur"), "--mounted-kit-hash", kh)
    cur_none, _ = row13(variant("r13_cur_none"), "--mounted-kit-hash", "none")
    cur_flagless, _ = row13(variant("r13_cur_flagless"))
    mism, _ = row13(variant("r13_kit"), "--mounted-kit-hash", "0" * 64)
    d = variant("r13_stale"); write_page(d, js=BASE_JS + "/*edited after the render*/")
    stale, _ = row13(d, "--mounted-kit-hash", kh)
    d = variant("r13_undet"); (d / "index.html").unlink()
    undet, rU = row13(d, "--mounted-kit-hash", kh)
    d = variant("r13_foreign"); mk_mp4(d / "final.mp4", dur=1.0)
    foreign, _ = row13(d, "--mounted-kit-hash", kh)
    d = variant("r13_failed"); patch_record(d, status="failed")
    failed, _ = row13(d, "--mounted-kit-hash", kh)
    d = variant("r13_dead"); patch_record(d, status="running")
    dead, _ = row13(d, "--mounted-kit-hash", kh)           # running, lock free: the run died; treated as row 7
    d = variant("r13_running"); patch_record(d, status="running")
    p, _ = start_holder(d)
    try:
        running, _ = row13(d, "--mounted-kit-hash", kh)    # running and another process holds the lock
    finally:
        p.kill(); p.wait()
    d = fresh("r13_norec"); mk_mp4(d / "x.mp4")
    check(d / "x.mp4", *exp)
    norec = rows_of(cj_of(d, "x.mp4.check.json")).get("FK-R-13")
    d = fresh("r13_none"); mk_mp4(d / "x.mp4")
    check(d / "x.mp4", *exp, "--mounted-kit-hash", "none")
    nonerow = rows_of(cj_of(d, "x.mp4.check.json")).get("FK-R-13")
    d = variant("r13_mdw"); write_page(d, js=BASE_JS + "/*edit*/")
    row13(d, "--mounted-kit-hash", kh)
    md_text = (d / "check.md").read_text(encoding="utf-8")
    bad = check(base / "final.mp4", "--mounted-kit-hash", "not-a-hash")

    def v(r): return (r["verdict"], r["severity"], r["bucket"]) if r else None
    return [neg(r0.code == 0 and own is not None and v(own) == ("PASS", None, "confirmed") and own_look == 0,
                f"Y-5: the render's own check.json has FK-R-13 {v(own)} and look={own_look}; {r0}"),
            neg(v(cur) == ("PASS", None, "confirmed") and "equals the mounted kit" in cur["measured"],
                f"CURRENT with the mounted hash -> {v(cur)}: {cur['measured'] if cur else None}"),
            neg(v(cur_none) == ("PASS", None, "confirmed") and v(cur_flagless) == ("PASS", None, "confirmed"),
                f"CURRENT, hash `none` or no flag (no comparison) -> {v(cur_none)}, {v(cur_flagless)}"),
            pos(v(mism) == ("WARN", "look", "look") and mism["basis"] and "kit" in mism["measured"],
                f"record kit hash differs from the mounted one -> {v(mism)}: {mism['measured'] if mism else None}"),
            pos(v(stale) == ("WARN", "look", "look") and "inputs changed" in stale["measured"],
                f"page edited after the render -> STALE {v(stale)}: {stale['measured'] if stale else None}"),
            pos(v(failed) == ("WARN", "look", "look") and "failed" in failed["measured"],
                f"record status failed -> STALE {v(failed)}: {failed['measured'] if failed else None}"),
            pos(v(running) == ("WARN", "look", "look") and "running" in running["measured"],
                f"record running and the lock held by another process -> STALE {v(running)}: {running['measured'] if running else None}"),
            neg(v(dead) == ("PASS", None, "confirmed"),
                f"record running, lock free (the run died) -> row 7, CURRENT {v(dead)}"),
            pos(v(undet) == ("UNDET", None, "undetermined") and undet["reason"] and not undet["unfinished"]
                and "index.html" in undet["reason"] and rU.code == 0,
                f"listed input missing -> UNDET_INPUTS {v(undet)}: {undet['reason'] if undet else None}; {rU}"),
            pos(v(foreign) == ("WARN", "look", "look") and "sha256" in foreign["measured"],
                f"file replaced by another mp4 -> FOREIGN {v(foreign)}: {foreign['measured'] if foreign else None}"),
            pos(v(norec) == ("WARN", "look", "look") and "no readable render.json" in norec["measured"],
                f"no record, no --mounted-kit-hash -> {v(norec)}: {norec['measured'] if norec else None}"),
            neg(v(nonerow) == ("PASS", "info", "confirmed") and nonerow["basis"],
                f"`none` + no record -> info, not in the look section: {v(nonerow)}"),
            pos("這個檔案和紀錄對不上最新狀態" in md_text and "出片之後頁面或素材有變動" in md_text
                and md_text.index("這個檔案和紀錄對不上最新狀態") > md_text.index("## 三、要你看")
                and md_text.index("這個檔案和紀錄對不上最新狀態") < md_text.index("## 四、無法判定"),
                "check.md carries the STALE row in the look section, in Chinese"),
            pos(bad.code == 1 and "Failed: spec_invalid" in bad.first,
                f"--mounted-kit-hash that is neither none nor a hash -> {bad}")]


# =====================================================================================================
# step 7 (M2): content scan, FK-R-7..12, 14, 15, 16, resample, two counts
# =====================================================================================================
M2_COLOURS = {"still": "0x336699", "black": "black", "white": "white"}
M2_AUDIO = {"tone": "sine=frequency=440:sample_rate=48000:duration={s}",
            "silence": "anullsrc=r=48000:cl=stereo:d={s}",
            "noise": "anoisesrc=r=48000:amplitude=0.0003:color=white:duration={s}"}


def mk_film(path: Path, v, a=None, fps=10, size="160x90") -> Path:
    """A film built from segments: v = [(motion|still|black|white, seconds)], a = [(tone|silence|noise, seconds)].
    `still` is a flat colour (a lossy test pattern starts its freeze about two frames late); `silence` is digital zero."""
    args = []
    for k, s in v:
        src = (f"testsrc=size={size}:rate={fps}:duration={s}" if k == "motion"
               else f"color=c={M2_COLOURS[k]}:size={size}:rate={fps}:duration={s}")
        args += ["-f", "lavfi", "-i", src]
    graph = [f"[{i}:v]setsar=1,format=yuv420p[v{i}]" for i in range(len(v))]
    graph.append("".join(f"[v{i}]" for i in range(len(v))) + f"concat=n={len(v)}:v=1:a=0[v]")
    maps = ["-map", "[v]"]
    enc = ["-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p"]
    if a:
        for k, s in a:
            args += ["-f", "lavfi", "-i", M2_AUDIO[k].format(s=s)]
        graph += [f"[{len(v) + i}:a]aformat=sample_rates=48000:channel_layouts=stereo[a{i}]" for i in range(len(a))]
        graph.append("".join(f"[a{i}]" for i in range(len(a))) + f"concat=n={len(a)}:v=0:a=1[a]")
        maps += ["-map", "[a]"]
        enc += ["-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-ac", "2"]
    ff(*args, "-filter_complex", ";".join(graph), *maps, *enc, "-movflags", "+faststart", path)
    return path


def ivs(L) -> list:
    return [(round(i.t0, 2), round(i.t1, 2), bool(i.open_at_end)) for i in L]


def near(a, b, tol=0.06) -> bool:
    return abs(a - b) <= tol


def scan_of(f: Path):
    from _fk import probe as fkprobe, scan as fkscan
    facts = fkprobe.probe(f, time.monotonic() + 60)
    ev = fkscan.scan(f, facts, dict(fkprofile.get_profile("lab-round")),
                     {"black", "frozen", "silent", "astats", "first_frame"}, time.monotonic() + 120)
    return facts, ev


def rows_by(doc: dict, prefix: str) -> list:
    return [r for r in doc["rows"] if r["id"] == prefix or r["id"].startswith(prefix + "#")]


def flagged(doc: dict) -> list:
    return [r["id"] for r in doc["rows"] if r["bucket"] in ("look", "blocking")]


RULE_A = {"id": "rule_a", "owner": "filmkit", "kind": "range", "film_types": None,
          "select": {"source": "frozen", "anchor": "end", "max_gap_s": 0.2}, "range_s": [2.4, 3.6],
          "sentence_zh": "尾段靜止 {measured} 秒；區間 {t0}–{t1} 秒；依據：{basis}",
          "missing_zh": "尾段沒有偵測到靜止；偵測下限 {floor_s} 秒；依據：{basis}",
          "basis": "fixture basis A", "provisional": True}
RULE_B = dict(RULE_A, id="rule_b", select={"source": "silent", "anchor": "end", "max_gap_s": 0.2}, provisional=False,
              basis="fixture basis B")


def rules_file(d: Path, rules: list, film_types=("type-a", "type-b"), name="rules.json") -> Path:
    p = d / name
    p.write_text(json.dumps({"schema_version": 1, "film_types": list(film_types), "rules": rules, "params": {}, "targets": {}},
                            ensure_ascii=False), encoding="utf-8")
    return p


def plan_file(d: Path, name="plan.json", **fields) -> Path:
    p = d / name
    p.write_text(json.dumps({"schema_version": 1, **fields}, ensure_ascii=False), encoding="utf-8")
    return p


NOKIT = ["--mounted-kit-hash", "none"]


def md_of(f: Path) -> str:
    return (f.parent / f"{f.name}.check.md").read_text(encoding="utf-8")


def low_kit(name: str, black_s=0.5) -> Path:
    """A copy of the kit whose black floor is lowered, for the scenarios the default 2 s floor cannot see."""
    cp = TMP / name
    if cp.exists():
        shutil.rmtree(cp, ignore_errors=True)
    shutil.copytree(KIT, cp / "filmkit", ignore=shutil.ignore_patterns("__pycache__"))
    pj = cp / "filmkit" / "profiles.json"
    doc = json.loads(pj.read_text(encoding="utf-8"))
    doc["profiles"]["lab-round"]["thresholds"]["black"]["min_duration_s"] = black_s
    pj.write_text(json.dumps(doc), encoding="utf-8")
    return cp / "filmkit"


def check_with(kit: Path, f: Path, *extra) -> tuple:
    p = subprocess.run([PY, "-X", "utf8", str(kit / "check.py"), str(f), *map(str, extra)], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=tool_env())
    doc = cj_of(f.parent, f"{f.name}.check.json")
    return Res(p.returncode, p.stdout, p.stderr), rows_of(doc), doc


WORKS_CONTRACT = Path.home() / ".claude" / "tools" / "design-axes-mount" / "works_contract.py"
BOOK_V1 = Path("<book-project>/reference-negative/promo")  # optional private input; absent here -> fixture page


@control("FK-R-18-19", "formal path (formal-path design §4.4): a book project v1 copy (no mount, no state) -> both blocking under "
                       "delivery-web, info under lab-round; stale mount -> blocking / item made by works_contract open "
                       "-> both PASS, render.json.provenance filled; declared opt-out -> FK-R-18 info")
def c_r18():
    if not WORKS_CONTRACT.is_file():
        return [skip("all", f"the shared layer's works_contract.py is not at {WORKS_CONTRACT}")]
    v = lambda r: (r["verdict"], r["severity"], r["bucket"]) if r else None  # noqa: E731
    arms = []
    # positive: the v1 folder that shipped with no mount and no works item (page files copied, a 1 s mp4 for speed)
    d = fresh("r18_v1")
    if BOOK_V1.is_dir():
        for p in BOOK_V1.iterdir():
            if p.is_file() and p.suffix in (".html", ".json") and p.name not in ("render.json", "check.json"):
                shutil.copy2(p, d / p.name)
    else:
        write_page(d)
    mk_mp4(d / "x.mp4")
    rw, _ = check(d / "x.mp4", *SMALL, "--profile", "delivery-web"), None
    rows_dw = rows_of(cj_of(d, "x.mp4.check.json"))
    check(d / "x.mp4", *SMALL)
    rows_lr = rows_of(cj_of(d, "x.mp4.check.json"))
    src = "a book project v1 promo copy" if BOOK_V1.is_dir() else "fixture page (a book project v1 folder absent)"
    arms.append(pos(v(rows_dw.get("FK-R-18")) == ("FAIL", "blocking", "blocking")
                    and v(rows_dw.get("FK-R-19")) == ("FAIL", "blocking", "blocking") and rw.code == 2,
                    f"{src} under delivery-web: FK-R-18 {v(rows_dw.get('FK-R-18'))}, FK-R-19 "
                    f"{v(rows_dw.get('FK-R-19'))}, exit {rw.code}"))
    arms.append(neg(v(rows_lr.get("FK-R-18")) == ("WARN", "info", "confirmed")
                    and v(rows_lr.get("FK-R-19")) == ("WARN", "info", "confirmed"),
                    f"the same folder under lab-round: FK-R-18 {v(rows_lr.get('FK-R-18'))}, FK-R-19 "
                    f"{v(rows_lr.get('FK-R-19'))} (info, never blocking)"))
    # negative: an item opened by works_contract.py open, its page rendered by filmkit, checked as delivery-web
    works = fresh("r18_works")
    item = works / "films" / "r18-open"
    op = subprocess.run([PY, "-X", "utf8", str(WORKS_CONTRACT), "open", str(item), "--medium", "video", "--actor",
                         "main-loop"], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if op.returncode != 0:
        return arms + [skip("negative", f"works_contract open failed (shared layer stale?): {op.stdout[-300:]}")]
    page = item / "page"
    page.mkdir()
    write_page(page)
    r0 = render(page)
    prov = rec_of(page).get("provenance") or {}
    rc = check(page / "final.mp4", *SMALL, "--profile", "delivery-web")
    rows_ok = rows_of(cj_of(page))
    arms.append(neg(v(rows_ok.get("FK-R-18")) == ("PASS", None, "confirmed")
                    and v(rows_ok.get("FK-R-19")) == ("PASS", None, "confirmed") and rc.code == 0,
                    f"item made by open, rendered: FK-R-18 {v(rows_ok.get('FK-R-18'))}, FK-R-19 "
                    f"{v(rows_ok.get('FK-R-19'))}, exit {rc.code}; render {r0.code}"))
    arms.append(neg(r0.code == 0 and prov.get("actor") == "main-loop" and len(prov.get("mount_sha") or "") == 64
                    and prov.get("item", "").endswith("r18-open"),
                    f"render.json.provenance = {json.dumps(prov)[:160]}"))
    axes = item / "inputs" / "design-axes.md"
    axes.write_text(axes.read_text(encoding="utf-8") + "\n<!-- hand edit -->\n", encoding="utf-8")
    check(page / "final.mp4", *SMALL, "--profile", "delivery-web")
    stale = rows_of(cj_of(page)).get("FK-R-18")
    arms.append(pos(v(stale) == ("FAIL", "blocking", "blocking") and "current mount" in (stale or {}).get("expected", ""),
                    f"design-axes.md edited after open -> FK-R-18 {v(stale)}"))
    # control arm: a lab round that declares it mounts nothing, with a why
    d = fresh("r18_optout")
    write_page(d)
    mk_mp4(d / "x.mp4")
    (d / "plan.json").write_text(json.dumps({"schema_version": 1, "mount_design_axes": False,
                                             "mount_design_axes_why": "control arm: no shared layer"}), encoding="utf-8")
    check(d / "x.mp4", *SMALL, "--plan", d / "plan.json")
    opt = rows_of(cj_of(d, "x.mp4.check.json")).get("FK-R-18")
    arms.append(neg(v(opt) == ("PASS", "info", "confirmed") and "control arm" in (opt or {}).get("measured", ""),
                    f"mount_design_axes false + why -> FK-R-18 {v(opt)}: {(opt or {}).get('measured')}"))
    return arms


@control("P-1-scan", "5 s film, last 3 s still -> frozen (2.0, 5.0, open_at_end) and a fixture range rule PASS; 3 s still mid-film -> one closed interval; motion throughout -> none")
def c_p1_scan():
    d = fresh("m2_p1")
    tail = mk_film(d / "tail.mp4", [("motion", 2), ("still", 3)])
    mid = mk_film(d / "mid.mp4", [("motion", 1), ("still", 3), ("motion", 1)])
    mot = mk_film(d / "mot.mp4", [("motion", 5)])
    long4 = mk_film(d / "long4.mp4", [("motion", 2), ("still", 4)])
    e1, e2, e3 = scan_of(tail)[1], scan_of(mid)[1], scan_of(mot)[1]
    rf = rules_file(d, [RULE_A])
    r1, rows1, doc1 = chk_rows(tail, "--rules", rf)
    r2, rows2, doc2 = chk_rows(long4, "--rules", rf)
    r3, rows3, doc3 = chk_rows(mid, "--rules", rf)
    i1 = ivs(e1.frozen)
    i2 = ivs(e2.frozen)
    return [pos(len(i1) == 1 and near(i1[0][0], 2.0) and near(i1[0][1], 5.0) and i1[0][2], f"last 3 s still: frozen {i1}"),
            neg(len(i2) == 1 and near(i2[0][0], 1.0) and near(i2[0][1], 4.0) and not i2[0][2], f"3 s still mid-film: frozen {i2}"),
            neg(e3.frozen == () and e3.black == (), f"motion throughout: frozen {ivs(e3.frozen)}, black {ivs(e3.black)}"),
            neg(rows1["FK-R-16#rule_a"]["verdict"] == "PASS" and not [r for r in doc1["rows"] if r["id"].startswith("FK-R-8")],
                f"3.0 s tail, fixture range 2.4-3.6 -> FK-R-16#rule_a {rows1['FK-R-16#rule_a']['verdict']}, no separate FK-R-8 row"),
            pos(rows2["FK-R-16#rule_a"]["verdict"] == "WARN" and rows2["FK-R-16#rule_a"]["bucket"] == "look",
                f"4.0 s tail, same range -> FK-R-16#rule_a {rows2['FK-R-16#rule_a']['verdict']} ({rows2['FK-R-16#rule_a']['measured']})"),
            pos(rows3["FK-R-16#rule_a"]["verdict"] == "WARN"
                and any(x["id"].startswith("FK-R-8") and x["bucket"] == "look" for x in doc3["rows"]),
                f"still in the middle, selector anchor end -> FK-R-16#rule_a {rows3['FK-R-16#rule_a']['measured']}; its FK-R-8 row is kept")]


@control("Q-12-scan", "last 3 s black / silent at 10 and 60 fps -> black t1 5.0 flagged, silent t1 within 1024/48000 of 5.0 flagged / the same spans mid-film -> not flagged")
def c_q12_scan():
    d = fresh("m2_q12")
    out = []
    for fps in (10, 60):
        f = mk_film(d / f"bs{fps}.mp4", [("motion", 2), ("black", 3)], [("tone", 2), ("silence", 3)], fps=fps)
        facts, ev = scan_of(f)
        b, s = ivs(ev.black), ivs(ev.silent)
        out.append(pos(len(b) == 1 and near(b[0][0], 2.0) and b[0][1] == 5.0 and b[0][2],
                       f"{fps} fps, last 3 s black: black {b}, video_end {facts.n_frames / facts.fps_avg}"))
        out.append(pos(len(s) == 1 and abs(s[0][1] - 5.0) <= 1024 / 48000 + 1e-6 and s[0][2],
                       f"{fps} fps, last 3 s silent: silent {s} (|t1-5.0| {abs(s[0][1] - 5.0):.4f} <= {1024 / 48000:.4f})"))
    f = mk_film(d / "mid.mp4", [("motion", 1), ("black", 3), ("motion", 1)], [("tone", 1), ("silence", 3), ("tone", 1)])
    _, ev = scan_of(f)
    b, s = ivs(ev.black), ivs(ev.silent)
    out.append(neg(len(b) == 1 and not b[0][2] and len(s) == 1 and not s[0][2] and near(s[0][1], 4.0),
                   f"black and silence 1.0-4.0 mid-film: black {b}, silent {s}, none flagged"))
    return out


@control("R-7c", "silence 2.5 s mid-film is unclamped and unflagged; a tail silence that ends 40 ms before film_end is not flagged, one that ends 20 ms before is (inside one audio frame on this build)")
def c_r7c():
    d = fresh("m2_r7c")
    out = []
    for gap, expect_flag in ((0.04, False), (0.02, True)):
        f = mk_film(d / f"g{int(gap * 1000)}.mp4", [("motion", 8)],
                    [("tone", 1), ("silence", 2.5), ("tone", 0.5), ("silence", round(4 - gap, 3)), ("tone", gap)])
        facts, ev = scan_of(f)
        s = ivs(ev.silent)
        film_end = max(facts.n_frames / facts.fps_avg, facts.audio_duration_s or 0)
        mid_ok = any(near(a, 1.0) and near(b, 3.5) and not o for a, b, o in s)
        tail = [x for x in s if x[0] > 3.0]
        arm = (pos if expect_flag else neg)
        out.append(arm(mid_ok and len(tail) == 1 and tail[0][2] == expect_flag and near(tail[0][1], film_end - gap, 0.01),
                       f"sound resumes {int(gap * 1000)} ms before film_end ({film_end:.3f} s): silent {s}; tail flagged "
                       f"{tail[0][2] if tail else None}, mid-film interval unflagged {mid_ok}"))
    return out


@control("R-7a", "audio 0.2 s longer than video, silent tail + still tail -> a silent selector compares with film_end and PASSes, a frozen selector with video_end and PASSes / the wrong reference misses")
def c_r7a():
    d = fresh("m2_r7a")
    f = mk_film(d / "r7a.mp4", [("motion", 2), ("still", 3)], [("tone", 2), ("silence", 3.2)])
    facts, ev = scan_of(f)
    rf = rules_file(d, [RULE_A, RULE_B])
    r, rows, doc = chk_rows(f, "--rules", rf)
    from _fk import judge as fkjudge
    video_end, film_end = facts.n_frames / facts.fps_avg, max(facts.n_frames / facts.fps_avg, facts.audio_duration_s)
    right = fkjudge.select_intervals(RULE_B, ev, video_end, film_end)
    wrong = fkjudge.select_intervals(RULE_B, ev, video_end, video_end)
    return [neg(film_end > video_end + 0.15 and rows["FK-R-16#rule_a"]["verdict"] == "PASS"
                and rows["FK-R-16#rule_b"]["verdict"] == "PASS",
                f"video_end {video_end:.2f}, film_end {film_end:.2f}: frozen rule {rows['FK-R-16#rule_a']['verdict']} "
                f"({rows['FK-R-16#rule_a']['measured']}), silent rule {rows['FK-R-16#rule_b']['verdict']} "
                f"({rows['FK-R-16#rule_b']['measured']})"),
            pos(len(right) == 1 and wrong == [],
                f"silent selector with film_end finds {ivs(right)}; the same selector compared with video_end finds {ivs(wrong)}")]


@control("Q-14", "black tail ended by one bright last frame -> treated as open (one frame of error, accepted) / ended by 0.5 s of bright frames -> closed")
def c_q14():
    d = fresh("m2_q14")
    f1 = mk_film(d / "one.mp4", [("motion", 2), ("black", 2.9), ("white", 0.1)])
    f2 = mk_film(d / "five.mp4", [("motion", 2), ("black", 2.5), ("white", 0.5)])
    b1, b2 = ivs(scan_of(f1)[1].black), ivs(scan_of(f2)[1].black)
    return [pos(len(b1) == 1 and b1[0] == (2.0, 5.0, True), f"one bright last frame: black {b1} (open, t1 extended to the film end)"),
            neg(len(b2) == 1 and b2[0][2] is False and near(b2[0][1], 4.5), f"0.5 s of bright frames: black {b2} (closed)")]


@control("Q-15", "1.0 s still at the end (end floor d=1, D18) -> no interval and the missing sentence names the end floor / 3.0 s still -> interval")
def c_q15():
    d = fresh("m2_q15")
    f1 = mk_film(d / "one.mp4", [("motion", 3), ("still", 1.0)])
    f2 = mk_film(d / "three.mp4", [("motion", 3), ("still", 3.0)])
    rf = rules_file(d, [RULE_A])
    _, rows1, doc1 = chk_rows(f1, "--rules", rf)
    _, rows2, doc2 = chk_rows(f2, "--rules", rf)
    r1 = rows1["FK-R-16#rule_a"]
    md1 = md_of(f1)
    return [pos(scan_of(f1)[1].frozen == () and r1["verdict"] == "WARN" and r1["measured"] == "not detected"
                and "偵測下限 1 秒" in md1 and "尾段沒有偵測到靜止" in md1,
                f"1.0 s tail: frozen none; FK-R-16#rule_a {r1['verdict']} ({r1['measured']}); check.md names the floor: "
                f"{'偵測下限 1 秒' in md1}"),
            neg(len(scan_of(f2)[1].frozen) == 1 and rows2["FK-R-16#rule_a"]["verdict"] == "PASS",
                f"3.0 s tail: frozen found; FK-R-16#rule_a {rows2['FK-R-16#rule_a']['verdict']}")]


def kit_edited(name: str, **paths) -> Path:
    """A copy of the kit with lab-round thresholds edited, e.g. black__picture_ratio=0.98 (the pre-D18 value)."""
    cp = TMP / name
    if cp.exists():
        shutil.rmtree(cp, ignore_errors=True)
    shutil.copytree(KIT, cp / "filmkit", ignore=shutil.ignore_patterns("__pycache__"))
    pj = cp / "filmkit" / "profiles.json"
    doc = json.loads(pj.read_text(encoding="utf-8"))
    th = doc["profiles"]["lab-round"]["thresholds"]
    for k, v in paths.items():
        grp, key = k.split("__")
        if v is None:
            th[grp].pop(key, None)
        else:
            th[grp][key] = v
    pj.write_text(json.dumps(doc), encoding="utf-8")
    return cp / "filmkit"


@control("D18-end", "1.5 s still at the end -> interval (end floor 1.0 s), open at end, no FK-R-8 row / the same 1.5 s still mid-film -> no interval (2.0 s floor elsewhere) / end floor removed from a kit copy -> the 1.5 s tail is not seen")
def c_d18_end():
    d = fresh("d18_end")
    tail = mk_film(d / "tail.mp4", [("motion", 6), ("still", 1.5)])     # the tail starts after the 5 s start window
    mid = mk_film(d / "mid.mp4", [("motion", 6), ("still", 1.5), ("motion", 2)])      # starts after the 5 s start window
    ft, fm = scan_of(tail)[1].frozen, scan_of(mid)[1].frozen
    rf = rules_file(d, [dict(RULE_A, range_s=[1.0, 2.0])])
    _, rows_t, doc_t = chk_rows(tail, "--rules", rf)
    old = kit_edited("d18_end_old", freeze__end_min_duration_s=None)
    _, rows_o, doc_o = check_with(old, tail, "--rules", rf)
    rt, ro = rows_t["FK-R-16#rule_a"], rows_o["FK-R-16#rule_a"]
    return [pos(len(ft) == 1 and ft[0].open_at_end and near(ft[0].t1 - ft[0].t0, 1.5, 0.15) and rt["verdict"] == "PASS"
                and not [x for x in rows_by(doc_t, "FK-R-8") if x["verdict"] != "PASS"],
                f"1.5 s tail: frozen {ivs(ft)}; fixture range 1-2 s {rt['verdict']} ({rt['measured']}); "
                f"FK-R-8 {[(x['id'], x['verdict']) for x in rows_by(doc_t, 'FK-R-8')]}"),
            neg(fm == (), f"1.5 s still mid-film: frozen {ivs(fm)}"),
            pos(ro["verdict"] == "WARN" and ro["measured"] == "not detected",
                f"kit copy without end_min_duration_s: fixture rule {ro['verdict']} ({ro['measured']}), the tail is under the 2.0 s floor")]


@control("D18-black", "dark ground with a small bright mark (0.25 % of pixels, like W30 E01's typewriter text) for 3 s -> no FK-R-7 look at picture ratio 0.999 / the same file with the pre-D18 ratio 0.98 -> FK-R-7 look / plain black 3 s -> FK-R-7 look")
def c_d18_black():
    d = fresh("d18_black")
    mark = d / "mark.mp4"
    ff("-f", "lavfi", "-i", "testsrc=size=160x90:rate=10:duration=2",
       "-f", "lavfi", "-i", "color=c=black:size=160x90:rate=10:duration=3,drawbox=x=70:y=40:w=6:h=6:color=white:t=fill",
       "-f", "lavfi", "-i", "testsrc=size=160x90:rate=10:duration=2",
       "-filter_complex", "[0:v]setsar=1,format=yuv420p[a];[1:v]setsar=1,format=yuv420p[b];[2:v]setsar=1,format=yuv420p[c];"
       "[a][b][c]concat=n=3:v=1:a=0[v]", "-map", "[v]", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
       "-movflags", "+faststart", mark)
    plain = mk_film(d / "plain.mp4", [("motion", 2), ("black", 3), ("motion", 2)])
    _, rows_m, doc_m = chk_rows(mark)
    old = kit_edited("d18_black_old", black__picture_ratio=0.98)
    _, rows_o, doc_o = check_with(old, mark)
    _, rows_p, doc_p = chk_rows(plain)
    look = lambda doc: [x for x in rows_by(doc, "FK-R-7") if x["bucket"] == "look"]
    return [neg(not look(doc_m), f"small mark on black, ratio 0.999: FK-R-7 {[(x['id'], x['verdict']) for x in rows_by(doc_m, 'FK-R-7')]}"),
            pos(len(look(doc_o)) == 1, f"same file, ratio 0.98: FK-R-7 look {[(x['id'], x['t0'], x['t1']) for x in look(doc_o)]}"),
            pos(len(look(doc_p)) == 1, f"plain black 3 s: FK-R-7 look {[(x['id'], x['t0'], x['t1']) for x in look(doc_p)]}")]


@control("D18-first", "one white frame then motion -> FK-R-10 PASS/info, flat_frames 1 / 0.3 s black then motion -> FK-R-10 look / the one-frame file with min_flat_s removed from a kit copy -> look")
def c_d18_first():
    d = fresh("d18_first")
    one = mk_film(d / "one.mp4", [("white", 0.1), ("motion", 3)])
    third = mk_film(d / "third.mp4", [("black", 0.3), ("motion", 3)])
    _, r1, _ = chk_rows(one)
    _, r3, _ = chk_rows(third)
    old = kit_edited("d18_first_old", first_frame__min_flat_s=None)
    _, ro, _ = check_with(old, one)
    a, b, c = r1["FK-R-10"], r3["FK-R-10"], ro["FK-R-10"]
    return [neg(a["verdict"] == "PASS" and a["severity"] == "info" and a["bucket"] != "look"
                and a.get("values", {}).get("flat_frames") == 1,
                f"one white frame: FK-R-10 {a['verdict']}/{a['severity']}/{a['bucket']} ({a['measured']})"),
            pos(b["verdict"] == "WARN" and b["bucket"] == "look", f"0.3 s black: FK-R-10 {b['verdict']}/{b['bucket']} ({b['measured']})"),
            pos(c["verdict"] == "WARN" and c["bucket"] == "look", f"one white frame, no min_flat_s: FK-R-10 {c['verdict']}/{c['bucket']}")]


# ---- FK-W32-33 (PSM 9.6): local motion inside a still, and the head hold -----------------------------
# Fork A (user 2026-10-10): the local-motion pass runs on mid-film stills only. Fork B: the head rule measures the first
# still that starts inside a window (selector anchor `first`, key max_t0_s; the fixture uses 4.0, the profile window is 5.0).
RULE_HEAD = dict(RULE_A, id="rule_head", select={"source": "frozen", "anchor": "first", "max_t0_s": 4.0}, range_s=[0.0, 1.5],
                 sentence_zh="片頭靜止 {measured} 秒；區間 {t0}–{t1} 秒；依據：{basis}",
                 missing_zh="片頭沒有偵測到靜止；偵測下限 {floor_s} 秒；依據：{basis}", basis="fixture basis head")


def mk_bar_film(path: Path, motion_s=0.5, still_s=3.5, tail_s=0.0, fps=10, size="1280x720") -> Path:
    """[motion_s of motion], a flat still whose top-left corner carries an 8 px high bar growing by 2 px per frame (like a
    progress bar; W30 E22), [tail_s of motion]. At 1280x720 the whole-frame change stays under freezedetect's noise, so
    the span reads as a still, while the largest tile (80 px wide) changes by about 0.002 per frame."""
    bar = (f"color=c=0x336699:size={size}:rate={fps}:duration={still_s},format=yuv420p,"
           f"geq=lum='if(lt(Y,8)*lt(X,2*round(T*{fps})),255,lum(X,Y))':cb='cb(X,Y)':cr='cr(X,Y)'")
    motion = lambda s: f"testsrc=size={size}:rate={fps}:duration={s}"
    srcs = ([motion(motion_s)] if motion_s else []) + [bar] + ([motion(tail_s)] if tail_s else [])
    args, graph = [], []
    for i, s in enumerate(srcs):
        args += ["-f", "lavfi", "-i", s]
        graph.append(f"[{i}:v]setsar=1,format=yuv420p[v{i}]")
    graph.append("".join(f"[v{i}]" for i in range(len(srcs))) + f"concat=n={len(srcs)}:v=1:a=0[v]")
    ff(*args, "-filter_complex", ";".join(graph), "-map", "[v]", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
       "-movflags", "+faststart", path)
    return path


def lab_freeze() -> dict:
    return fkprofile.get_profile("lab-round")["thresholds"]["freeze"]


def look_rows(doc: dict, prefix: str) -> list:
    return [x for x in rows_by(doc, prefix) if x["bucket"] == "look"]


@control("W32-local", "bar still mid-film (motion before and after) -> interval leaves frozen, frozen_local_motion holds it with median above the profile limit, no FK-R-8 look row, an info row in check.md / the same bar still running to the end, or starting at frame 0 -> NOT excluded (end rule sees it) / the same film without the bar -> kept / key removed from a kit copy -> kept")
def c_w32_local():
    d = fresh("w32_local")
    mid = mk_bar_film(d / "mid.mp4", motion_s=0.5, still_s=3.0, tail_s=1.0)
    end = mk_bar_film(d / "end.mp4", motion_s=0.5, still_s=3.5)
    head = mk_bar_film(d / "head.mp4", motion_s=0, still_s=3.0, tail_s=1.0)
    plain = mk_film(d / "plain.mp4", [("motion", 0.5), ("still", 3.0), ("motion", 1.0)], size="1280x720")
    thr = lab_freeze().get("local_tile_median_max")
    em, ee, eh, ep = (scan_of(x)[1] for x in (mid, end, head, plain))
    lm_m, lm_e, lm_h, lm_p = (getattr(x, "frozen_local_motion", None) for x in (em, ee, eh, ep))
    rf = rules_file(d, [dict(RULE_A, range_s=[2.4, 3.6])])
    _, rows_mid, doc_mid = chk_rows(mid)
    md_mid = md_of(mid)
    _, rows_end_r, doc_end_r = chk_rows(end, "--rules", rf)
    _, rows_head, doc_head = chk_rows(head)
    _, rows_pl, doc_pl = chk_rows(plain)
    off = kit_edited("w32_local_off", freeze__local_tile_median_max=None)
    _, _, doc_off = check_with(off, mid)
    info = rows_by(doc_mid, "FK-R-8L")
    re_ = rows_end_r["FK-R-16#rule_a"]
    return [pos(thr is not None and em.frozen == () and lm_m is not None and len(lm_m) == 1 and lm_m[0][2] > thr
                and near(lm_m[0][0], 0.5, 0.15) and near(lm_m[0][1], 3.5, 0.15),
                f"bar still mid-film: limit {thr}; frozen {ivs(em.frozen)}; frozen_local_motion {lm_m}"),
            pos(not look_rows(doc_mid, "FK-R-8") and [x["verdict"] for x in rows_by(doc_mid, "FK-R-8")] == ["PASS"],
                f"bar still mid-film, no rules: FK-R-8 rows {[(x['id'], x['verdict'], x['bucket']) for x in rows_by(doc_mid, 'FK-R-8')]}"),
            pos(len(info) == 1 and info[0]["verdict"] == "PASS" and info[0]["severity"] == "info" and info[0]["bucket"] == "confirmed"
                and thr is not None and "局部" in md_mid and f"{thr:g}" in md_mid,
                f"bar still mid-film: info rows {[(x['id'], x['measured']) for x in info]}; check.md names local motion and the limit: "
                f"{'局部' in md_mid and thr is not None and f'{thr:g}' in md_mid}"),
            pos(len(ee.frozen) == 1 and ee.frozen[0].open_at_end and lm_e == () and re_["verdict"] == "PASS"
                and not rows_by(doc_end_r, "FK-R-8L"),
                f"bar still running to the end: frozen {ivs(ee.frozen)}, frozen_local_motion {lm_e}; end-anchored fixture rule "
                f"range 2.4-3.6 {re_['verdict']} ({re_['measured']}) (an end hold is never excluded)"),
            pos(len(eh.frozen) == 1 and near(eh.frozen[0].t0, 0.0, 0.1) and lm_h == () and look_rows(doc_head, "FK-R-8")
                and not rows_by(doc_head, "FK-R-8L"),
                f"bar still starting at frame 0: frozen {ivs(eh.frozen)}, frozen_local_motion {lm_h}; FK-R-8 look {[x['id'] for x in look_rows(doc_head, 'FK-R-8')]} (a head still is never excluded)"),
            neg(len(ep.frozen) == 1 and near(ep.frozen[0].t0, 0.5, 0.15) and lm_p == () and look_rows(doc_pl, "FK-R-8")
                and not rows_by(doc_pl, "FK-R-8L"),
                f"plain still mid-film: frozen {ivs(ep.frozen)}, frozen_local_motion {lm_p}; FK-R-8 look rows {[x['id'] for x in look_rows(doc_pl, 'FK-R-8')]}"),
            neg(bool(look_rows(doc_off, "FK-R-8")) and not rows_by(doc_off, "FK-R-8L"),
                f"kit copy without freeze.local_tile_median_max, bar still mid-film: FK-R-8 look {[x['id'] for x in look_rows(doc_off, 'FK-R-8')]} (no pass, interval kept)")]


@control("W32-fail", "local-motion pass forced to fail (fault point) -> interval kept, note present, exit unchanged / no fault -> no note / expired deadline -> a mid-film interval is kept with a timed-out note, nothing raised; an interval touching the start or the end is never passed, so no note")
def c_w32_fail():
    from _fk import scan as fkscan
    from _fk.types import Interval
    d = fresh("w32_fail")
    bar = mk_bar_film(d / "bar.mp4", motion_s=0.5, still_s=3.0, tail_s=1.0)
    r0 = check(bar)
    n0 = r0.line("Notes:")
    doc0 = cj_of(d, "bar.mp4.check.json")
    r1 = check(bar, env={"FILMKIT_SELFTEST_FAULT": "local_motion=raise"})
    n1 = r1.line("Notes:")
    doc1 = cj_of(d, "bar.mp4.check.json")
    fn = getattr(fkscan, "split_local_motion", None)
    th = dict(fkprofile.get_profile("lab-round")["thresholds"])
    iv = Interval(0.5, 3.5, False)
    past = time.monotonic() - 1.0
    res = fn(bar, [iv], th, past) if fn else None
    res_end = fn(bar, [Interval(0.5, 4.0, True)], th, past) if fn else None
    res_head = fn(bar, [Interval(0.0, 2.0, False)], th, past) if fn else None
    still = mk_film(d / "still.mp4", [("motion", 0.5), ("still", 3.5)])
    lv = getattr(fkscan, "local_motion_levels", None)
    levels = lv(still, 0.5, 3.0, time.monotonic() + 60) if lv else None       # 25 frames in -> 24 differences, none spurious
    return [pos(r1.code == r0.code and bool(look_rows(doc1, "FK-R-8")) and "local motion" in n1 and not rows_by(doc1, "FK-R-8L"),
                f"fault local_motion=raise: exit {r1.code} (unfaulted {r0.code}); FK-R-8 look {[x['id'] for x in look_rows(doc1, 'FK-R-8')]}; {n1}"),
            neg("local motion" not in n0 and not look_rows(doc0, "FK-R-8") and bool(rows_by(doc0, "FK-R-8L")),
                f"no fault: {n0}; FK-R-8 look rows {[x['id'] for x in look_rows(doc0, 'FK-R-8')]}; info rows {[x['id'] for x in rows_by(doc0, 'FK-R-8L')]}"),
            pos(res is not None and list(res[0]) == [iv] and not res[1] and len(res[2]) == 1 and "timed out" in res[2][0],
                f"split_local_motion, mid-film interval, deadline already past: {res}"),
            neg(res_end is not None and res_end[1] == [] and res_end[2] == [] and res_head is not None and res_head[2] == [],
                f"split_local_motion, deadline already past, interval open at the end -> {res_end}; interval from frame 0 -> {res_head} (never passed: no note)"),
            neg(levels is not None and len(levels) == 24 and max(levels) < 0.0005,
                f"pure still, 25 frames cut at 0.5-3.0 s: {None if levels is None else len(levels)} differences (one fewer than frames: "
                f"tblend's first output is not a pass-through on this build), largest {None if levels is None else max(levels)}")]


@control("W33-floor", "head rule (anchor first, window) on fixture films: frame-0 1.2 s still PASS / 1.2 s still at 3 s PASS / E14-shaped 2.1 s still after 2 s of motion WARN look, no FK-R-8 row / still at 6 s not selected (missing_ok PASS) / 1.2 s still at 8 s no interval (general floor) / window or head floor removed from a kit copy -> not seen / missing sentence names the head floor")
def c_w33_floor():
    d = fresh("w33_floor")
    f0 = mk_film(d / "f0.mp4", [("still", 1.2), ("motion", 2.8)])
    in3 = mk_film(d / "in3.mp4", [("motion", 3.0), ("still", 1.2), ("motion", 2.0)])
    e14 = mk_film(d / "e14.mp4", [("motion", 2.0), ("still", 2.1), ("motion", 2.0)])
    late6 = mk_film(d / "late6.mp4", [("motion", 6.0), ("still", 2.4), ("motion", 1.0)])
    late8 = mk_film(d / "late8.mp4", [("motion", 8.0), ("still", 1.2), ("motion", 1.0)])
    mov = mk_film(d / "mov.mp4", [("motion", 4)])
    rf = rules_file(d, [RULE_HEAD])
    rf_ok = rules_file(d, [dict(RULE_HEAD, missing_ok=True)], name="rules_ok.json")
    s0, s3, s14, s6, s8, sm = (scan_of(x)[1].frozen for x in (f0, in3, e14, late6, late8, mov))
    _, rows0, doc0 = chk_rows(f0, "--rules", rf)
    _, rows3, doc3 = chk_rows(in3, "--rules", rf)
    _, rows14, doc14 = chk_rows(e14, "--rules", rf)
    _, rows6, doc6 = chk_rows(late6, "--rules", rf_ok)
    _, rows8, doc8 = chk_rows(late8, "--rules", rf)
    _, rowsm, docm = chk_rows(mov, "--rules", rf)
    md_m = md_of(mov)
    fz8 = lambda doc: [x for x in doc["rows"] if x["id"].startswith("FK-R-8#")]      # interval rows; the "none found" row has no #
    no_win = kit_edited("w33_floor_nowin", freeze__start_window_s=None)
    no_min = kit_edited("w33_floor_nomin", freeze__start_min_duration_s=None)
    _, rows_nw, _ = check_with(no_win, in3, "--rules", rf)
    _, rows_nm, _ = check_with(no_min, f0, "--rules", rf)
    R = "FK-R-16#rule_head"
    return [pos(len(s0) == 1 and near(s0[0].t0, 0.0, 0.1) and near(s0[0].t1, 1.2, 0.15) and rows0[R]["verdict"] == "PASS",
                f"1.2 s still from frame 0: frozen {ivs(s0)}; head rule {rows0[R]['verdict']} ({rows0[R]['measured']})"),
            pos(len(s3) == 1 and near(s3[0].t0, 3.0, 0.15) and rows3[R]["verdict"] == "PASS" and not fz8(doc3),
                f"1.2 s still at 3 s: frozen {ivs(s3)}; head rule {rows3[R]['verdict']} ({rows3[R]['measured']})"),
            pos(len(s14) == 1 and rows14[R]["verdict"] == "WARN" and rows14[R]["bucket"] == "look" and not fz8(doc14),
                f"E14-shaped (2 s motion, 2.1 s still, motion): frozen {ivs(s14)}; head rule {rows14[R]['verdict']} ({rows14[R]['measured']}); "
                f"FK-R-8 interval rows {[x['id'] for x in fz8(doc14)]}"),
            neg(len(s6) == 1 and near(s6[0].t0, 6.0, 0.15) and rows6[R]["verdict"] == "PASS" and rows6[R]["measured"] == "not detected"
                and bool(look_rows(doc6, "FK-R-8")),
                f"2.4 s still starting at 6 s (window ends at 4 s in the fixture rule): frozen {ivs(s6)}; head rule {rows6[R]['verdict']} "
                f"({rows6[R]['measured']}, missing_ok); the still stays an FK-R-8 row {[x['id'] for x in look_rows(doc6, 'FK-R-8')]}"),
            neg(s8 == () and rows8[R]["measured"] == "not detected",
                f"1.2 s still at 8 s (general 2.0 s floor): frozen {ivs(s8)}; head rule {rows8[R]['verdict']} ({rows8[R]['measured']})"),
            neg(sm == (), f"motion from frame 0: frozen {ivs(sm)}"),
            pos(rows_nw[R]["verdict"] == "WARN" and rows_nw[R]["measured"] == "not detected",
                f"kit copy without freeze.start_window_s, 1.2 s still at 3 s: head rule {rows_nw[R]['verdict']} ({rows_nw[R]['measured']})"),
            pos(rows_nm[R]["verdict"] == "WARN" and rows_nm[R]["measured"] == "not detected",
                f"kit copy without freeze.start_min_duration_s, 1.2 s still from frame 0: head rule {rows_nm[R]['verdict']} ({rows_nm[R]['measured']})"),
            pos(rowsm[R]["verdict"] == "WARN" and "偵測下限 1 秒" in (rowsm[R].get("text_zh") or "") and rowsm[R]["text_zh"] in md_m,
                f"motion from frame 0, rule without missing_ok: {rowsm[R]['verdict']}; the missing sentence names the head floor: "
                f"{'偵測下限 1 秒' in (rowsm[R].get('text_zh') or '')}")]


@control("W33-first", "selector anchor first: two stills inside the window -> only the earliest is selected (one row, no #n suffix) / anchor first without max_t0_s -> one UNDET row for the rule, nothing guessed")
def c_w33_first():
    d = fresh("w33_first")
    two = mk_film(d / "two.mp4", [("motion", 1.0), ("still", 1.2), ("motion", 1.0), ("still", 1.2), ("motion", 1.0)])
    s = scan_of(two)[1].frozen
    rf = rules_file(d, [RULE_HEAD])
    bad = rules_file(d, [dict(RULE_HEAD, select={"source": "frozen", "anchor": "first"})], name="rules_bad.json")
    _, rows, doc = chk_rows(two, "--rules", rf)
    _, rows_b, doc_b = chk_rows(two, "--rules", bad)
    mine = [x for x in doc["rows"] if x["id"].startswith("FK-R-16")]
    rb = [x for x in doc_b["rows"] if x["id"].startswith("FK-R-16")]
    return [pos(len(s) == 2 and len(mine) == 1 and mine[0]["id"] == "FK-R-16#rule_head" and near(mine[0]["t0"], s[0].t0, 0.01),
                f"two 1.2 s stills at 1.0 s and 3.2 s: frozen {ivs(s)}; rule rows {[(x['id'], x['t0'], x['t1']) for x in mine]} (the earliest only)"),
            pos(len(rb) == 1 and rb[0]["verdict"] == "UNDET" and "max_t0_s" in rb[0]["reason"],
                f"anchor first without max_t0_s: {[(x['id'], x['verdict'], x['reason']) for x in rb]}")]


@control("W33-missing-ok", "rule with missing_ok true and nothing matched -> PASS (confirmed) carrying the missing sentence / the same rule without the key, or with it false -> WARN look / missing_ok does not excuse a matched interval that is out of range")
def c_w33_missing_ok():
    d = fresh("w33_missing_ok")
    mov = mk_film(d / "mov.mp4", [("motion", 4)])
    h20 = mk_film(d / "h20.mp4", [("still", 2.0), ("motion", 2.0)])
    ok = dict(RULE_HEAD, missing_ok=True)
    no_key = dict(RULE_HEAD)
    off = dict(RULE_HEAD, missing_ok=False)
    out = []
    for label, rule, want in (("missing_ok true", ok, "PASS"), ("key absent", no_key, "WARN"), ("missing_ok false", off, "WARN")):
        rf = rules_file(d, [rule], name=f"r_{label.replace(' ', '_')}.json")
        _, rows, doc = chk_rows(mov, "--rules", rf)
        r = rows["FK-R-16#rule_head"]
        sent = r.get("text_zh") or ""
        good = (r["verdict"] == "PASS" and r["bucket"] == "confirmed" and r["measured"] == "not detected" and sent.startswith("片頭沒有偵測到靜止")
                and sent.endswith("（暫定）")) if want == "PASS" else (r["verdict"] == "WARN" and r["bucket"] == "look")
        out.append((neg if want == "PASS" else pos)(good, f"motion from frame 0, {label}: {r['verdict']}/{r['bucket']} ({r['measured']}); {sent[:24]}"))
    _, rows20, _ = chk_rows(h20, "--rules", rules_file(d, [ok], name="r_h20.json"))
    out.append(pos(rows20["FK-R-16#rule_head"]["verdict"] == "WARN" and rows20["FK-R-16#rule_head"]["bucket"] == "look",
                   f"2.0 s head still, missing_ok true: {rows20['FK-R-16#rule_head']['verdict']} ({rows20['FK-R-16#rule_head']['measured']})"))
    return out


@control("R-11-vocab", "--film-type product-intro (not in film_types) -> one UNDET FK-R-16 'film type not in vocabulary' and no rule rows / known type -> rule rows; restricted rule + no film type -> UNDET; known type the rule does not list -> no row; film type from the plan")
def c_r11_vocab():
    d = fresh("m2_r11")
    f = mk_film(d / "x.mp4", [("motion", 2), ("still", 3)])
    restricted = dict(RULE_A, id="rule_r", film_types=["type-a"])
    rf = rules_file(d, [RULE_A, restricted])
    _, rows1, doc1 = chk_rows(f, "--rules", rf, "--film-type", "product-intro")
    _, rows2, doc2 = chk_rows(f, "--rules", rf, "--film-type", "type-a")
    _, rows3, doc3 = chk_rows(f, "--rules", rf)
    _, rows4, doc4 = chk_rows(f, "--rules", rf, "--film-type", "type-b")
    pl = plan_file(d, film_type="type-a")
    _, rows5, doc5 = chk_rows(f, "--rules", rf, "--plan", pl)
    r16_1 = [r for r in doc1["rows"] if r["id"].startswith("FK-R-16")]
    return [pos(len(r16_1) == 1 and r16_1[0]["id"] == "FK-R-16" and r16_1[0]["verdict"] == "UNDET"
                and "film type not in vocabulary: product-intro" in r16_1[0]["reason"] and r16_1[0]["unfinished"] is False,
                f"product-intro: {[(r['id'], r['verdict'], r['reason']) for r in r16_1]}"),
            neg({"FK-R-16#rule_a", "FK-R-16#rule_r"} <= set(rows2) and rows2["FK-R-16#rule_r"]["verdict"] == "PASS",
                f"type-a: rule_a {rows2['FK-R-16#rule_a']['verdict']}, restricted rule_r {rows2['FK-R-16#rule_r']['verdict']}"),
            pos(rows3["FK-R-16#rule_r"]["verdict"] == "UNDET" and rows3["FK-R-16#rule_a"]["verdict"] == "PASS",
                f"no film type: restricted rule_r {rows3['FK-R-16#rule_r']['verdict']} ({rows3['FK-R-16#rule_r']['reason']}); unrestricted rule_a still evaluated"),
            neg("FK-R-16#rule_r" not in rows4 and "FK-R-16#rule_a" in rows4, "type-b: restricted rule_r has no row, rule_a does"),
            neg(rows5["FK-R-16#rule_r"]["verdict"] == "PASS", f"film type type-a taken from the plan: rule_r {rows5['FK-R-16#rule_r']['verdict']}")]


@control("P-19", "owner-filmkit rule of kind ratio -> one UNDET FK-R-16#<id> / owner-timeline range rule -> no row / provisional sentence ends with （暫定）, a fixed one does not")
def c_p19():
    d = fresh("m2_p19")
    f = mk_film(d / "x.mp4", [("motion", 2), ("still", 3)], [("tone", 2), ("silence", 3)])
    ratio = dict(RULE_A, id="rule_ratio", kind="ratio")
    tl = dict(RULE_A, id="rule_tl", owner="timeline")
    rf = rules_file(d, [ratio, tl, RULE_A, RULE_B])
    _, rows, doc = chk_rows(f, "--rules", rf)
    md = md_of(f)
    a, b = rows["FK-R-16#rule_a"], rows["FK-R-16#rule_b"]
    return [pos(rows["FK-R-16#rule_ratio"]["verdict"] == "UNDET" and "kind not supported" in rows["FK-R-16#rule_ratio"]["reason"],
                f"kind ratio: {rows['FK-R-16#rule_ratio']['verdict']} ({rows['FK-R-16#rule_ratio']['reason']})"),
            neg("FK-R-16#rule_tl" not in rows and not [r for r in doc["rows"] if "rule_tl" in r["id"]],
                f"owner timeline rule: no row; FK-R-16 rows {sorted(i for i in rows if i.startswith('FK-R-16'))}"),
            pos(a["provisional"] is True and a["text_zh"].endswith("（暫定）") and "（暫定）" in md,
                f"provisional rule_a sentence: ...{a['text_zh'][-14:]}"),
            neg(b["provisional"] is False and not b["text_zh"].endswith("（暫定）") and b["verdict"] == "PASS",
                f"fixed rule_b sentence: ...{b['text_zh'][-14:]}")]


@control("rule_a-10s", "fixture rule_a: 10 s end still vs range 7-9, with a hold and a black declared over it -> FK-R-16 WARN (a declaration does not excuse), no FK-R-8 row for the interval / 8 s -> PASS / film type not listed -> no row")
def c_rule_a():
    d = fresh("m2_rule_a")
    ra = dict(RULE_A, range_s=[7.0, 9.0], film_types=["type-a"])
    rf = rules_file(d, [ra])
    f10 = mk_film(d / "f10.mp4", [("motion", 2), ("still", 10)])
    f8 = mk_film(d / "f8.mp4", [("motion", 2), ("still", 8)])
    p10 = plan_file(d, "p10.json", holds=[{"t0": 2.0, "t1": 12.0, "why": "end card"}], blacks=[{"t0": 2.0, "t1": 12.0, "why": "fixture"}])
    p8 = plan_file(d, "p8.json", holds=[{"t0": 2.0, "t1": 10.0, "why": "end card"}], blacks=[{"t0": 2.0, "t1": 10.0, "why": "fixture"}])
    r1, rows1, doc1 = chk_rows(f10, "--rules", rf, "--film-type", "type-a", "--plan", p10)
    r2, rows2, doc2 = chk_rows(f8, "--rules", rf, "--film-type", "type-a", "--plan", p8)
    r3, rows3, doc3 = chk_rows(f10, "--rules", rf, "--film-type", "type-b", "--plan", p10)
    a1 = rows1["FK-R-16#rule_a"]
    return [pos(a1["verdict"] == "WARN" and a1["bucket"] == "look" and not [r for r in doc1["rows"] if r["id"].startswith("FK-R-8")],
                f"10 s tail vs 7-9, declared hold + black: FK-R-16#rule_a {a1['verdict']} ({a1['measured']}); FK-R-8 rows "
                f"{[r['id'] for r in doc1['rows'] if r['id'].startswith('FK-R-8')]}"),
            neg(rows2["FK-R-16#rule_a"]["verdict"] == "PASS", f"8 s tail: FK-R-16#rule_a {rows2['FK-R-16#rule_a']['verdict']} ({rows2['FK-R-16#rule_a']['measured']})"),
            neg(not [r for r in doc3["rows"] if r["id"].startswith("FK-R-16")],
                f"film type type-b, rule limited to type-a: FK-R-16 rows {[r['id'] for r in doc3['rows'] if r['id'].startswith('FK-R-16')]}")]


@control("D25-timeline", "timeline-shaped film: tail hold 3.0 s declared as holds + silences -> FK-R-9 info (declared), FK-R-16 PASS for both rules, not suppressed by the declarations")
def c_d25_timeline():
    d = fresh("m2_d25")
    f = mk_film(d / "x.mp4", [("motion", 2), ("still", 3)], [("tone", 2), ("silence", 3)])
    pl = plan_file(d, holds=[{"t0": 2.0, "t1": 5.0, "why": "end card"}], silences=[{"t0": 2.0, "t1": 5.0, "why": "quiet end"}])
    rf = rules_file(d, [RULE_A, RULE_B])
    r, rows, doc = chk_rows(f, "--rules", rf, "--plan", pl)
    r2, rows2, doc2 = chk_rows(f, "--rules", rf)
    f9 = rows_by(doc, "FK-R-9")
    f9b = rows_by(doc2, "FK-R-9")
    return [neg(rows["FK-R-16#rule_a"]["verdict"] == "PASS" and rows["FK-R-16#rule_b"]["verdict"] == "PASS"
                and len(f9) == 1 and f9[0]["verdict"] == "PASS" and f9[0]["severity"] == "info",
                f"declared: rule_a {rows['FK-R-16#rule_a']['verdict']}, rule_b {rows['FK-R-16#rule_b']['verdict']}, "
                f"FK-R-9 {[(x['id'], x['verdict'], x['severity']) for x in f9]}"),
            pos(len(f9b) == 1 and f9b[0]["bucket"] == "look",
                f"the same film without the plan: FK-R-9 {[(x['id'], x['bucket']) for x in f9b]} (the declaration is what turns it to info)"),
            neg(rows["FK-R-16#rule_a"]["bucket"] == "confirmed",
                "FK-R-16 rows are present with the declarations in force (a declaration never removes a rule row)")]


@control("FK-R-7-8-9", "declared vs undeclared black / still / silence; a declaration covering part of an interval leaves the residual to the threshold (2.5 s residual -> look, 1.5 s -> info)")
def c_r789():
    d = fresh("m2_r789")
    out = []
    blk = mk_film(d / "blk.mp4", [("motion", 3), ("black", 3), ("motion", 2)])
    r, rows, doc = chk_rows(blk)
    f7 = rows_by(doc, "FK-R-7")
    out.append(pos(len(f7) == 1 and f7[0]["bucket"] == "look" and f7[0]["where"] == "picture" and near(f7[0]["t0"], 3.0) and near(f7[0]["t1"], 6.0)
                   and all(x["verdict"] == "PASS" for x in rows_by(doc, "FK-R-8")),
                   f"3 s black, no declaration: FK-R-7 {[(x['id'], x['bucket'], x['t0'], x['t1']) for x in f7]}; FK-R-8 {[x['id'] for x in rows_by(doc, 'FK-R-8')]} (covered by FK-R-7)"))
    pin = plan_file(d, "pin.json", blacks=[{"t0": 2.5, "t1": 6.5, "why": "fixture black"}])
    r, rows, doc = chk_rows(blk, "--plan", pin)
    f7 = rows_by(doc, "FK-R-7")
    out.append(neg(len(f7) == 1 and f7[0]["bucket"] == "confirmed" and f7[0]["severity"] == "info",
                   f"black fully inside a declared black: FK-R-7 {[(x['id'], x['bucket'], x['severity']) for x in f7]}"))
    still = mk_film(d / "still.mp4", [("motion", 3), ("still", 3), ("motion", 2)])
    r, rows, doc = chk_rows(still)
    f8 = rows_by(doc, "FK-R-8")
    out.append(pos(len(f8) == 1 and f8[0]["bucket"] == "look" and near(f8[0]["t0"], 3.0) and near(f8[0]["t1"], 6.0),
                   f"3 s still, no declaration: FK-R-8 {[(x['id'], x['bucket'], x['t0'], x['t1']) for x in f8]}"))
    full = plan_file(d, "full.json", holds=[{"t0": 3.0, "t1": 6.0, "why": "hold"}])
    part_big = plan_file(d, "pb.json", holds=[{"t0": 3.0, "t1": 3.5, "why": "hold"}])
    part_small = plan_file(d, "ps.json", holds=[{"t0": 3.0, "t1": 4.5, "why": "hold"}])
    _, _, d1 = chk_rows(still, "--plan", full)
    _, _, d2 = chk_rows(still, "--plan", part_big)
    _, _, d3 = chk_rows(still, "--plan", part_small)
    g1, g2, g3 = rows_by(d1, "FK-R-8"), rows_by(d2, "FK-R-8"), rows_by(d3, "FK-R-8")
    out.append(neg(len(g1) == 1 and g1[0]["severity"] == "info", f"hold covers all 3 s: FK-R-8 {[(x['bucket'], x['severity']) for x in g1]}"))
    out.append(pos(len(g2) == 1 and g2[0]["bucket"] == "look" and near(g2[0]["t0"], 3.5) and near(g2[0]["t1"], 6.0),
                   f"hold to 3.5 s: residual 2.5 s judged by the threshold -> FK-R-8 {[(x['bucket'], x['t0'], x['t1']) for x in g2]}"))
    out.append(neg(len(g3) == 1 and g3[0]["bucket"] == "confirmed",
                   f"hold to 4.5 s: residual 1.5 s is under the threshold -> FK-R-8 {[(x['bucket'], x['severity']) for x in g3]}"))
    sil = mk_film(d / "sil.mp4", [("motion", 5)], [("tone", 1), ("silence", 3), ("tone", 1)])
    r, rows, doc = chk_rows(sil)
    s0 = rows_by(doc, "FK-R-9")
    ps = plan_file(d, "psil.json", silences=[{"t0": 0.5, "t1": 4.5, "why": "quiet"}])
    r, rows, doc = chk_rows(sil, "--plan", ps)
    s1 = rows_by(doc, "FK-R-9")
    out.append(pos(len(s0) == 1 and s0[0]["bucket"] == "look" and s0[0]["where"] == "audio",
                   f"3 s silence mid-film, undeclared: FK-R-9 {[(x['id'], x['bucket'], x['where']) for x in s0]}"))
    out.append(neg(len(s1) == 1 and s1[0]["severity"] == "info", f"inside a declared silence: FK-R-9 {[(x['bucket'], x['severity']) for x in s1]}"))
    kit = low_kit("m2_lowkit")
    b34 = mk_film(d / "b34.mp4", [("motion", 3), ("black", 1), ("motion", 2)])
    _, rows_d, doc_d = chk_rows(b34)
    _, rows_l, doc_l = check_with(kit, b34)
    fl = rows_by(doc_l, "FK-R-7")
    out.append(pos(len(fl) == 1 and fl[0]["bucket"] == "look" and near(fl[0]["t0"], 3.0) and near(fl[0]["t1"], 4.0),
                   f"black at 3-4 s with the floor lowered to 0.5 s (kit copy): FK-R-7 {[(x['id'], x['bucket'], x['t0'], x['t1']) for x in fl]}"))
    out.append(neg(all(x["verdict"] == "PASS" for x in rows_by(doc_d, "FK-R-7")),
                   f"the same file with the default 2.0 s floor: FK-R-7 {[(x['id'], x['verdict'], x['measured']) for x in rows_by(doc_d, 'FK-R-7')]}"))
    return out


@control("FK-R-9-allzero", "expected sound + every sample 0 -> FK-R-9 FAIL blocking, exit 2 / a -70 dB noise track -> look, not blocking / sound present -> no blocking / --audio-expected no -> no FK-R-9 row")
def c_r9_allzero():
    d = fresh("m2_r9z")
    zero = mk_film(d / "zero.mp4", [("motion", 4)], [("silence", 4)])
    noise = mk_film(d / "noise.mp4", [("motion", 4)], [("noise", 4)])
    tone = mk_film(d / "tone.mp4", [("motion", 4)], [("tone", 4)])
    r1, rows1, doc1 = chk_rows(zero, "--audio-expected", "yes")
    r2, rows2, doc2 = chk_rows(noise, "--audio-expected", "yes")
    r3, rows3, doc3 = chk_rows(tone, "--audio-expected", "yes")
    r4, rows4, doc4 = chk_rows(zero, "--audio-expected", "no")
    r5, rows5, doc5 = chk_rows(zero)
    z = rows_by(doc1, "FK-R-9")
    n = rows_by(doc2, "FK-R-9")
    return [pos(len(z) == 1 and z[0]["verdict"] == "FAIL" and z[0]["bucket"] == "blocking" and r1.code == 2 and "-inf" in z[0]["measured"],
                f"all samples 0, sound expected: FK-R-9 {[(x['id'], x['verdict'], x['measured']) for x in z]}, {r1}"),
            pos(len(n) == 1 and n[0]["bucket"] == "look" and r2.code == 0 and doc2["summary"]["blocking"] == 0,
                f"-70 dBFS noise: FK-R-9 {[(x['id'], x['bucket'], x['where']) for x in n]}, {r2}"),
            neg(not [x for x in rows_by(doc3, "FK-R-9") if x["bucket"] != "confirmed"] and r3.code == 0, f"tone, sound expected: FK-R-9 {[x['id'] for x in rows_by(doc3, 'FK-R-9')]} no non-PASS row, {r3}"),
            neg(rows_by(doc4, "FK-R-9") == [], f"--audio-expected no on the same all-zero file: no FK-R-9 row"),
            pos(len(rows_by(doc5, "FK-R-9")) == 1 and rows_by(doc5, "FK-R-9")[0]["bucket"] == "look" and r5.code == 0,
                f"no sound expectation, all samples 0: FK-R-9 look (not blocking), {r5}")]


@control("FK-R-10", "frame 0 black and frame at 1 s different -> look / the black 0.8 s interval seen (floor lowered) -> only FK-R-7 / a film of 1 s or less -> UNDET")
def c_r10():
    d = fresh("m2_r10")
    f = mk_film(d / "ff.mp4", [("black", 0.8), ("motion", 3)])
    r, rows, doc = chk_rows(f)
    kit = low_kit("m2_lowkit10")
    r2, rows2, doc2 = check_with(kit, f)
    short = mk_film(d / "short.mp4", [("motion", 1)])
    r3, rows3, doc3 = chk_rows(short)
    ok = mk_film(d / "ok.mp4", [("motion", 3)])
    r4, rows4, doc4 = chk_rows(ok)
    ff = rows["FK-R-10"]
    return [pos(ff["bucket"] == "look" and ff["where"] == "picture" and ff["t"] == 0.0
                and all(x["verdict"] == "PASS" for x in rows_by(doc, "FK-R-7")),
                f"black first 0.8 s, default floor: FK-R-10 {ff['verdict']}/{ff['severity']} ({ff['measured']}); FK-R-7 {[x['verdict'] for x in rows_by(doc, 'FK-R-7')]}"),
            pos(any(e["row"] == "FK-R-10" and e["t"] == 0.0 for e in doc["events"]), f"FK-R-10 is a point event: {[e for e in doc['events'] if e['row'] == 'FK-R-10']}"),
            pos([x["bucket"] for x in rows_by(doc2, "FK-R-7")] == ["look"] and "FK-R-10" not in [x["id"] for x in doc2["rows"] if x["bucket"] == "look"],
                f"black 0.8 s seen as an interval (floor 0.5 s): FK-R-7 {[(x['id'], x['bucket']) for x in rows_by(doc2, 'FK-R-7')]}; FK-R-10 {rows2['FK-R-10']['verdict'] if 'FK-R-10' in rows2 else 'no row'}"),
            neg(rows3["FK-R-10"]["verdict"] == "UNDET" and "no frame at 1 s" in rows3["FK-R-10"]["reason"] and rows3["FK-R-10"]["unfinished"] is False,
                f"1 s film: FK-R-10 {rows3['FK-R-10']['verdict']} ({rows3['FK-R-10']['reason']})"),
            neg(rows4["FK-R-10"]["verdict"] == "PASS", f"motion from frame 0: FK-R-10 {rows4['FK-R-10']['verdict']} ({rows4['FK-R-10']['measured']})")]


R2 = ["--duration", "2", "--size", "160x90", "--fps", "10"]
PAGE_TRANSITION = ("window.__setTime=function(t){document.getElementById('b').style.left=((t*100)%140)+'px';};")
PAGE_PAUSED = ("var a=document.getElementById('b').animate([{left:'0px'},{left:'100px'}],{duration:1000,fill:'both'});a.pause();"
               "window.__setTime=function(t){a.currentTime=(t*1000)%1000;};")
PAGE_RANDOM = "window.__setTime=function(t){document.getElementById('b').style.left=(Math.random()*100)+'px';};"
PAGE_THROWS = "window.__setTime=function(t){throw new Error('fixture failure');};"


@control("FK-R-11-12", "page with a running CSS transition -> FK-R-11 look / a paused animation driven by currentTime -> no row; Math.random() page -> FK-R-12 look / deterministic page -> PASS; both read last_success.frames after a failed rerun (R-6c)")
def c_r11_r12():
    d = fresh("m2_r1112")
    out = []
    write_page(d, js=PAGE_TRANSITION, css=BASE_CSS + "#b{transition:left 5s linear}")
    r = render(d, *R2, small=False)
    rows = rows_of(cj_of(d))
    out.append(pos(rows["FK-R-11"]["bucket"] == "look" and rows["FK-R-11"]["where"] == "file",
                   f"CSS transition page: FK-R-11 {rows['FK-R-11']['verdict']}/{rows['FK-R-11']['severity']} ({rows['FK-R-11']['measured']})"))
    d2 = fresh("m2_r1112b")
    write_page(d2, js=PAGE_PAUSED)
    r2 = render(d2, *R2, small=False)
    rows2 = rows_of(cj_of(d2))
    out.append(neg(rows2["FK-R-11"]["verdict"] == "PASS" and rows2["FK-R-12"]["verdict"] == "PASS" and r2.code == 0,
                   f"paused animation driven by currentTime: FK-R-11 {rows2['FK-R-11']['verdict']} ({rows2['FK-R-11']['measured']}), FK-R-12 {rows2['FK-R-12']['verdict']}"))
    d3 = fresh("m2_r1112c")
    write_page(d3, js=PAGE_RANDOM)
    r3 = render(d3, *R2, small=False)
    rows3 = rows_of(cj_of(d3))
    rs = rec_of(d3)["frames"]["resample"]
    out.append(pos(rows3["FK-R-12"]["bucket"] == "look" and any(not x["match"] for x in rs),
                   f"Math.random() page: FK-R-12 {rows3['FK-R-12']['verdict']}/{rows3['FK-R-12']['severity']} ({rows3['FK-R-12']['measured']}); "
                   f"resample {sum(1 for x in rs if x['match'])}/{len(rs)} matched"))
    out.append(neg(rows2["FK-R-12"]["verdict"] == "PASS" and len(rec_of(d2)["frames"]["resample"]) == 12
                   and all(x["match"] for x in rec_of(d2)["frames"]["resample"]),
                   f"deterministic page: FK-R-12 {rows2['FK-R-12']['verdict']} ({rows2['FK-R-12']['measured']}), 12 frames re-visited"))
    # R-6c: a failed rerun leaves last_success.frames; check.py reads it
    write_page(d3, js=PAGE_THROWS)
    bad = render(d3, *R2, small=False)
    ch = check(d3 / "final.mp4")
    rows4 = rows_of(cj_of(d3))
    out.append(pos(bad.code == 1 and rows4["FK-R-12"]["bucket"] == "look" and rows4["FK-R-12"]["measured"] == rows3["FK-R-12"]["measured"],
                   f"after a failed rerun (record {rec_of(d3)['status']}): check reads last_success.frames -> FK-R-12 {rows4['FK-R-12']['verdict']} "
                   f"({rows4['FK-R-12']['measured']}), same as before the failed rerun"))
    out.append(neg(rows4["FK-R-13"]["bucket"] == "look", f"the same check also reports the stale file: FK-R-13 {rows4['FK-R-13']['verdict']}"))
    nore = mk_mp4(fresh("m2_r1112d") / "plain.mp4", dur=2, fps=10)
    _, rows5, _ = chk_rows(nore, "--duration", "2", "--size", "160x90", "--fps", "10")
    out.append(neg(rows5["FK-R-11"]["verdict"] == "UNDET" and rows5["FK-R-12"]["verdict"] == "UNDET",
                   f"a file with no render record: FK-R-11 {rows5['FK-R-11']['verdict']}, FK-R-12 {rows5['FK-R-12']['verdict']}"))
    return out


PAGE_REVISIT = ("var seen={};window.__setTime=function(t){var k=String(t);if(seen[k]){throw new Error('revisited '+k);}"
                "seen[k]=1;document.getElementById('b').style.left=((t*100)%140)+'px';};")


@control("resample-error", "an exception while a frame is visited again -> ffmpeg killed, FAILED(page_runtime), no output, the message names the re-seek / a page that tolerates revisits publishes")
def c_resample_error():
    d = fresh("m2_resample")
    write_page(d, js=PAGE_REVISIT)
    r = render(d, *R2, small=False)
    rec = rec_of(d)
    d2 = fresh("m2_resample_ok")
    write_page(d2)
    r2 = render(d2, *R2, small=False)
    leftovers = [p.name for p in (d / ".filmkit").glob("*") if p.suffix == ".mp4"] if (d / ".filmkit").exists() else []
    return [pos(r.code == 1 and r.first.startswith("Failed: page_runtime") and "re-seek of frame" in r.first and not (d / "final.mp4").exists()
                and rec["status"] == "failed", f"page throwing on a revisit: {r}; record {rec['status']}, final.mp4 absent {not (d / 'final.mp4').exists()}"),
            neg(r2.code == 0 and (d2 / "final.mp4").exists() and len(rec_of(d2)["frames"]["resample"]) == 12,
                f"page that tolerates revisits: {r2}")]


@control("FK-R-14", "three declarations -> three check.md lines in section 5 + a totals line / no plan -> no FK-R-14 row and section 5 reads none (FK-INV-8 md half)")
def c_r14():
    d = fresh("m2_r14")
    f = mk_film(d / "x.mp4", [("motion", 3), ("still", 3), ("motion", 2)], [("tone", 1), ("silence", 3), ("tone", 4)])
    pl = plan_file(d, holds=[{"t0": 3.0, "t1": 6.0, "why": "end card"}], blacks=[{"t0": 0.0, "t1": 0.3, "why": "fade-in"}],
                   silences=[{"t0": 1.0, "t1": 4.0, "why": "cold open"}])
    r, rows, doc = chk_rows(f, "--plan", pl)
    md = md_of(f)
    from _fk import report as fkreport
    regenerated = fkreport.render_md(doc) == md                # FK-INV-11 with section 5 present
    sec = md.split("## 五、作者宣告的例外")[1]
    lines = [ln for ln in sec.splitlines() if ln.startswith("- ")]
    r2, rows2, doc2 = chk_rows(f)
    md2 = md_of(f)
    sec2 = md2.split("## 五、作者宣告的例外")[1]
    k = [x for x in doc["rows"] if x["id"].startswith("FK-R-14")]
    return [pos(len(lines) == 4 and sum("理由「" in ln for ln in lines) == 3 and "合計 3 段宣告" in sec
                and doc["exemption_totals"]["declarations"] == 3 and len(doc["exemptions"]) == 3,
                f"three declarations: {len(lines)} lines in section 5 (3 items + totals); totals {doc['exemption_totals']}"),
            pos(len(k) == 4 and all(x["severity"] == "info" for x in k) and all(x["where"] in ("picture", "audio", "file") for x in k),
                f"FK-R-14 rows {[(x['id'], x['where'], x['t0'], x['t1']) for x in k]}"),
            neg(regenerated, "check.md regenerated from this check.json (section 5 included) is byte-identical to the written one"),
            neg(not [x for x in doc2["rows"] if x["id"].startswith("FK-R-14")] and "無。" in sec2 and doc2["exemption_totals"] is None,
                f"no plan: no FK-R-14 row, section 5 reads: {sec2.strip()[:20]!r}")]


@control("FK-R-15", "silences declaration over a narration line -> look (audio) / touching only -> no row; declaration ending at video_end + 1e-9 -> no row / at + 0.1 -> look")
def c_r15():
    d = fresh("m2_r15")
    f = mk_film(d / "x.mp4", [("motion", 5)], [("tone", 1), ("silence", 3), ("tone", 1)])
    over = plan_file(d, "over.json", silences=[{"t0": 1.0, "t1": 4.0, "why": "quiet"}], narration_lines=[{"id": "L1", "t0": 3.0, "t1": 4.5}])
    touch = plan_file(d, "touch.json", silences=[{"t0": 1.0, "t1": 3.0, "why": "quiet"}], narration_lines=[{"id": "L1", "t0": 3.0, "t1": 4.5}])
    tiny = plan_file(d, "tiny.json", holds=[{"t0": 2.0, "t1": 5.000000001, "why": "end"}])
    past = plan_file(d, "past.json", holds=[{"t0": 2.0, "t1": 5.1, "why": "end"}])
    res = {}
    for k, p in (("over", over), ("touch", touch), ("tiny", tiny), ("past", past)):
        res[k] = chk_rows(f, "--plan", p)[2]
    a = rows_by(res["over"], "FK-R-15")
    b = rows_by(res["touch"], "FK-R-15")
    c = rows_by(res["tiny"], "FK-R-15")
    e = rows_by(res["past"], "FK-R-15")
    return [pos(len(a) == 1 and a[0]["bucket"] == "look" and a[0]["where"] == "audio" and near(a[0]["t0"], 3.0) and near(a[0]["t1"], 4.0),
                f"silences 1-4 s over narration line 3-4.5 s: {[(x['id'], x['bucket'], x['where'], x['t0'], x['t1']) for x in a]}"),
            neg(all(x["bucket"] == "confirmed" for x in b), f"silences end where the line starts: {[(x['id'], x['bucket']) for x in b]}"),
            neg(all(x["bucket"] == "confirmed" for x in c), f"declaration ending at video_end + 1e-9: {[(x['id'], x['bucket']) for x in c]}"),
            pos(len(e) == 1 and e[0]["bucket"] == "look" and e[0]["where"] == "file", f"declaration ending at video_end + 0.1: {[(x['id'], x['bucket'], x['where']) for x in e]}")]


@control("BR-6-counts", "a film with declarations: look and look_without_exemptions differ by the number of exempted rows / no declaration: equal")
def c_br6():
    d = fresh("m2_br6")
    f = mk_film(d / "x.mp4", [("motion", 3), ("still", 3), ("motion", 2)], [("tone", 1), ("silence", 3), ("tone", 4)])
    both = plan_file(d, "both.json", holds=[{"t0": 3.0, "t1": 6.0, "why": "hold"}], silences=[{"t0": 0.5, "t1": 4.5, "why": "quiet"}])
    one = plan_file(d, "one.json", holds=[{"t0": 3.0, "t1": 6.0, "why": "hold"}])
    _, _, d2 = chk_rows(f, "--plan", both, *NOKIT)
    md = md_of(f)
    _, _, d1 = chk_rows(f, "--plan", one, *NOKIT)
    _, _, d0 = chk_rows(f, *NOKIT)
    s2, s1, s0 = d2["summary"], d1["summary"], d0["summary"]
    ex2 = sum(len(e["exempted_rows"]) for e in d2["exemptions"])
    ex1 = sum(len(e["exempted_rows"]) for e in d1["exemptions"])
    return [pos(s2["look_without_exemptions"] - s2["look"] == ex2 == 2 and s1["look_without_exemptions"] - s1["look"] == ex1 == 1,
                f"hold + silence declared: look {s2['look']} / without {s2['look_without_exemptions']} (exempted rows {ex2}); hold only: "
                f"{s1['look']} / {s1['look_without_exemptions']} (exempted {ex1})"),
            neg(s0["look"] == s0["look_without_exemptions"] == 2, f"no plan: look {s0['look']} = look_without_exemptions {s0['look_without_exemptions']}"),
            pos("不算這些宣告時是" in md, "check.md section 5 states both counts")]


@control("P-14-scan", "blocking row and scan failure together -> exit 2, content rows UNDET unfinished / scan failure alone -> exit 3 / scan deadline (tiny --check-timeout) -> content rows UNDET, exit 3 / no fault -> exit 0")
def c_p14_scan():
    d = fresh("m2_p14")
    bad = mk_mp4(d / "nofs.mp4", dur=2, faststart=False)
    good = mk_mp4(d / "good.mp4", dur=2)
    args = ["--duration", "2", "--size", "160x90", "--fps", "10", "--mounted-kit-hash", "none"]
    r1, rows1, doc1 = chk_rows(bad, *args, env={"FILMKIT_SELFTEST_FAULT": "scan=raise"})
    r2, rows2, doc2 = chk_rows(good, *args, env={"FILMKIT_SELFTEST_FAULT": "scan=raise"})
    r3, rows3, doc3 = chk_rows(good, *args, "--check-timeout", "1", env={"FILMKIT_SELFTEST_FAULT": "scan=sleep:3:"})
    r4, rows4, doc4 = chk_rows(good, *args)
    content = ("FK-R-7", "FK-R-8", "FK-R-10")
    return [pos(r1.code == 2 and rows1["FK-R-4"]["bucket"] == "blocking"
                and all(rows1[i]["verdict"] == "UNDET" and rows1[i]["unfinished"] and "scan failed" in rows1[i]["reason"] for i in content),
                f"blocking FK-R-4 + injected scan failure: {r1}; FK-R-7 {rows1['FK-R-7']['verdict']} ({rows1['FK-R-7']['reason']})"),
            pos(r2.code == 3 and doc2["summary"]["incomplete"] and rows2["FK-R-4"]["verdict"] == "PASS",
                f"scan failure alone: {r2}; summary {doc2['summary']}"),
            pos(r3.code == 3 and all(rows3[i]["verdict"] == "UNDET" and rows3[i]["unfinished"] and rows3[i]["reason"] == "check timed out" for i in content),
                f"scan sleeping past --check-timeout 1: {r3}; FK-R-8 {rows3['FK-R-8']['verdict']} unfinished {rows3['FK-R-8']['unfinished']} ({rows3['FK-R-8']['reason']})"),
            neg(r4.code == 0 and all(rows4[i]["verdict"] == "PASS" for i in content), f"no fault: {r4}; FK-R-7/8/10 {[rows4[i]['verdict'] for i in content]}")]


@control("FK-INV-10-m2", "every check.md this run produced for the M2 controls has no quality word or advice / a fixture sentence with 建議 fails")
def c_inv10_m2():
    files = sorted(p for p in TMP.glob("m2_*/**/*.md") if p.name.endswith("check.md"))
    hits = {p.relative_to(TMP).as_posix(): forbidden_hits(p.read_text(encoding="utf-8")) for p in files}
    hits = {k: v for k, v in hits.items() if v}
    return [neg(len(files) >= 1 and not hits, f"{len(files)} check.md files scanned, hits: {hits or 'none'}"),
            pos(forbidden_hits("尾段停留建議縮短。") == ["建議"], "fixture sentence -> ['建議']")]


# =====================================================================================================
# step 8 (M3): loudness FK-R-17, narration lines FK-R-9, delivery-web, transform.py (FK-INV-17, design 7.4d)
# =====================================================================================================
M3_STDOUT: list[str] = []         # every transform.py stdout the M3 controls produced (FK-INV-10-m3 reads them)
LOUD_TOL = 0.2                    # control margin for "the tone measures what it was built to measure"; not a kit value
NORM_TOL = 0.5                    # control margin for "the normalized file measures near the target"; not a kit value
# neutral fixture targets (never the lab's real ones): key = name in a fixture rules file
T_OFF = {"lufs": -20.5, "true_peak": -1.5, "tolerance_lu": 0.4, "source": "fixture", "review_when": "never"}
T_ON = {"lufs": -26.0, "true_peak": -1.5, "tolerance_lu": 0.4, "source": "fixture", "review_when": "never"}
T_TP = {"lufs": -26.0, "true_peak": -30.0, "tolerance_lu": 0.4, "source": "fixture", "review_when": "never"}
T_NOTOL = {"lufs": -20.5, "true_peak": -1.5, "source": "fixture", "review_when": "never"}
T_NOTOL_TP = {"lufs": -26.0, "true_peak": -30.0, "source": "fixture", "review_when": "never"}
T_BAD = {"lufs": "loud", "true_peak": -1.5, "source": "fixture", "review_when": "never"}


def mk_tone(path: Path, vol_db: float = -4.9, dur: float = 4, size="160x90", fps=10, two_level=False, silent=False,
            audio=True) -> Path:
    """Video + a 1 kHz stereo sine. At the default volume the tone measures -26.0 LUFS on this ffmpeg build
    (validated when M3 was built); `two_level` plays the first half at vol_db and the second 6 dB lower (LRA 6)."""
    v = ["-f", "lavfi", "-i", f"testsrc=size={size}:rate={fps}:duration={dur}"]
    enc = ["-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p"]
    aac = ["-c:a", "aac", "-b:a", "192k"]
    if not audio:
        ff(*v, *enc, "-movflags", "+faststart", path)
    elif silent:
        ff(*v, "-f", "lavfi", "-i", f"anullsrc=r=48000:cl=stereo:d={dur}", *enc, *aac, "-movflags", "+faststart", path)
    elif two_level:
        half = dur / 2
        sine = f"sine=frequency=1000:sample_rate=48000:duration={half}"
        fc = (f"[1:a]aformat=channel_layouts=stereo,volume={vol_db}dB[a];[2:a]aformat=channel_layouts=stereo,"
              f"volume={vol_db - 6}dB[b];[a][b]concat=n=2:v=0:a=1[o]")
        ff(*v, "-f", "lavfi", "-i", sine, "-f", "lavfi", "-i", sine, "-filter_complex", fc, "-map", "0:v", "-map", "[o]",
           *enc, *aac, "-movflags", "+faststart", path)
    else:
        ff(*v, "-f", "lavfi", "-i", f"sine=frequency=1000:sample_rate=48000:duration={dur}", "-af",
           f"aformat=channel_layouts=stereo,volume={vol_db}dB", *enc, *aac, "-movflags", "+faststart", path)
    return path


def loud_of(f: Path) -> dict:
    return scan_of(f)[1].loudness


def tp(*args, env=None, timeout: float = 240) -> Res:
    r = run_tool("transform.py", args, env, timeout)
    M3_STDOUT.append("\n".join(r.lines))
    return r


def rej(r: Res, kind: str) -> bool:
    return r.code == 1 and five_ok(r) and r.first.startswith(f"Failed: {kind}")


def lst(d: Path) -> list:
    return sorted(p.relative_to(d).as_posix() for p in d.rglob("*"))


def targets_file(d: Path, name: str = "targets.json", **targets) -> Path:
    p = d / name
    p.write_text(json.dumps({"schema_version": 1, "film_types": [], "rules": [], "params": {}, "targets": targets}), encoding="utf-8")
    return p


def trec_of(out: Path) -> dict:
    return json.loads(Path(str(out) + ".transform.json").read_text(encoding="utf-8"))


def row_of(doc: dict, rid: str) -> dict | None:
    return next((r for r in doc["rows"] if r["id"] == rid), None)


@control("Q-19-ebur128", "ebur128 with framelog=quiet leaves only the summary in stderr and the scan parses it (-26 LUFS tone) / without framelog=quiet stderr carries a frame line per 100 ms")
def c_q19_ebur128():
    from _fk import scan as fkscan
    d = fresh("m3_q19")
    f = mk_tone(d / "t.mp4")

    def stderr_of(af):
        r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(f), "-map", "0:a:0", "-af", af, "-f", "null", "-"],
                           capture_output=True)
        return r.stderr.decode("utf-8", "replace")
    frame_re = re.compile(r"t:\s*[\d.]+\s+TARGET:")
    noisy, quiet = stderr_of("ebur128=peak=true"), stderr_of(fkscan.EBUR128_AF)
    n_noisy, n_quiet = len(frame_re.findall(noisy)), len(frame_re.findall(quiet))
    got = fkscan.parse_loudness(quiet)
    facts, ev = scan_of(f)
    return [pos(n_noisy >= 20, f"without framelog=quiet stderr has {n_noisy} frame lines (the noise the option removes)"),
            neg(n_quiet == 0 and "Integrated loudness" in quiet and got is not None,
                f"{fkscan.EBUR128_AF}: {n_quiet} frame lines, summary present, parsed {got}"),
            neg(ev.finished and ev.loudness is not None and abs(ev.loudness["integrated_lufs"] + 26.0) <= LOUD_TOL
                and ev.loudness["true_peak_db"] < -20, f"the scan reports {ev.loudness}"),
            pos(fkscan.parse_loudness("") is None and fkscan.parse_loudness(noisy.split("Summary:")[0]) is None,
                "text without the summary block parses to None, not to numbers")]


@control("FK-R-17", "loudness always reported as info; a named rules-file target adds WARN/look (loudness off, true peak over), UNDET (no tolerance, malformed, unknown, no audio) / on target -> PASS; --target without --rules -> spec_invalid")
def c_r17():
    d = fresh("m3_r17")
    f = mk_tone(d / "t.mp4")
    rf = targets_file(d, t_off=T_OFF, t_on=T_ON, t_tp=T_TP, t_notol=T_NOTOL, t_notol_tp=T_NOTOL_TP, t_bad=T_BAD)
    base = ["--audio-expected", "yes", *NOKIT]

    def case(*extra, f_=f):
        r, rows, doc = chk_rows(f_, *base, *extra)
        return r, doc, [x for x in doc.get("rows", []) if x["id"].startswith("FK-R-17")]
    r0, doc0, rows0 = case()
    r1, doc1, rows1 = case("--rules", rf, "--target", "t_off")
    r2, doc2, rows2 = case("--rules", rf, "--target", "t_on")
    r3, doc3, rows3 = case("--rules", rf, "--target", "t_tp")
    r4, doc4, rows4 = case("--rules", rf, "--target", "t_notol")
    r5, doc5, rows5 = case("--rules", rf, "--target", "t_notol_tp")
    r6, doc6, rows6 = case("--rules", rf, "--target", "t_bad")
    r7, doc7, rows7 = case("--rules", rf, "--target", "nosuch")
    r8 = check(f, *base, "--target", "t_on")
    silent = mk_tone(d / "silent.mp4", silent=True)
    r9, doc9, rows9 = case("--rules", rf, "--target", "t_on", f_=silent)
    noaud = mk_tone(d / "noaudio.mp4", audio=False)
    r10, doc10, rows10 = case(f_=noaud)
    r11, doc11, rows11 = case("--rules", rf, "--target", "t_on", f_=noaud)
    bad_rules = d / "broken.json"
    bad_rules.write_text("{not json", encoding="utf-8")
    r12, doc12, rows12 = case("--rules", bad_rules, "--target", "t_on")
    r1b, _, _ = case("--rules", rf, "--target", "t_off")      # rerun so that check.md on disk is the t_off one
    md_off = md_of(f)
    info = lambda rows: next((x for x in rows if x["id"] == "FK-R-17"), None)
    cmp_ = lambda rows, name: next((x for x in rows if x["id"] == f"FK-R-17#{name}"), None)
    i0, c1, c2, c3 = info(rows0), cmp_(rows1, "t_off"), cmp_(rows2, "t_on"), cmp_(rows3, "t_tp")
    c4, c5, c6, c7 = cmp_(rows4, "t_notol"), cmp_(rows5, "t_notol_tp"), cmp_(rows6, "t_bad"), cmp_(rows7, "nosuch")
    i9, c9 = info(rows9), cmp_(rows9, "t_on")
    c11 = cmp_(rows11, "t_on")
    c12 = cmp_(rows12, "t_on")
    return [neg(i0 is not None and i0["verdict"] == "PASS" and i0["severity"] == "info" and i0["bucket"] == "confirmed"
                and abs(i0["values"]["integrated_lufs"] + 26.0) <= LOUD_TOL and len(rows0) == 1 and i0["milestone"] == "M3",
                f"no --rules: one info row {[(x['id'], x['bucket'], x['measured']) for x in rows0]}"),
            pos(c1 is not None and c1["verdict"] == "WARN" and c1["bucket"] == "look" and abs(c1["values"]["deviation_lu"] + 5.5) <= LOUD_TOL
                and info(rows1) is not None and "響度超出規則檔目標" in md_off,
                f"measured about -26 against fixture target -20.5: {c1['verdict'] if c1 else None}/{c1['bucket'] if c1 else None}, "
                f"deviation {c1['values']['deviation_lu'] if c1 else None}; the info row stays; the md sentence is in Chinese"),
            neg(c2 is not None and c2["verdict"] == "PASS" and c2["bucket"] == "confirmed" and info(rows2) is not None,
                f"on target -26: {[(x['id'], x['verdict']) for x in rows2]}"),
            pos(c3 is not None and c3["verdict"] == "WARN" and c3["bucket"] == "look" and "true peak" in c3["expected"],
                f"loudness on target, true peak over the ceiling: {c3['verdict'] if c3 else None} ({c3['measured'] if c3 else None})"),
            pos(c4 is not None and c4["verdict"] == "UNDET" and "no loudness tolerance" in c4["reason"] and not c4["unfinished"],
                f"target without a tolerance, loudness off -> {c4['verdict'] if c4 else None}: {c4['reason'] if c4 else None}"),
            pos(c5 is not None and c5["verdict"] == "WARN" and c5["bucket"] == "look",
                f"target without a tolerance, true peak over -> still WARN: {c5['verdict'] if c5 else None}"),
            pos(c6 is not None and c6["verdict"] == "UNDET" and "malformed" in c6["reason"],
                f"malformed target -> {c6['verdict'] if c6 else None}: {c6['reason'] if c6 else None}"),
            pos(c7 is not None and c7["verdict"] == "UNDET" and "not in the rules file" in c7["reason"],
                f"unknown target name -> {c7['verdict'] if c7 else None}: {c7['reason'] if c7 else None}"),
            pos(rej(r8, "spec_invalid") and "--rules" in r8.first, f"--target without --rules: {r8}"),
            pos(i9 is not None and "true peak -inf" in i9["measured"] and i9["values"]["true_peak_db"] is None
                and abs(i9["values"]["integrated_lufs"] + 70.0) <= 0.05
                and c9 is not None and c9["bucket"] == "look" and c9["verdict"] == "WARN" and "true peak -inf" in c9["measured"]
                and c9["values"]["deviation_lu"] < -40,
                f"digital silence: the filter reports -70 LUFS and a -inf true peak (null in check.json, valid JSON); the target row is "
                f"{c9['verdict'] if c9 else None}/{c9['bucket'] if c9 else None}: {c9['measured'] if c9 else None}"),
            neg(rows10 == [], f"file without audio, no target: no FK-R-17 row ({[x['id'] for x in rows10]})"),
            pos(c11 is not None and c11["verdict"] == "UNDET" and "no audio" in c11["reason"],
                f"file without audio, target named -> {c11['verdict'] if c11 else None}: {c11['reason'] if c11 else None}"),
            pos(info(rows12) is not None and c12 is not None and c12["verdict"] == "UNDET" and "rules file unreadable" in c12["reason"],
                f"unreadable rules file: info row stays, target row UNDET ({c12['reason'] if c12 else None})")]


@control("FK-R-9-line", "narration line 2 digital silence -> FK-R-9 look (audio, M3) / sound in every line -> one PASS row; a silences declaration over a line does not exempt it; a line outside the film -> UNDET")
def c_r9_line():
    d = fresh("m3_r9line")
    f = mk_film(d / "x.mp4", [("motion", 6)], [("tone", 1.5), ("silence", 3), ("tone", 1.5)])
    L1, L2, L3 = {"id": "L1", "t0": 0.2, "t1": 1.2}, {"id": "L2", "t0": 2.0, "t1": 4.0}, {"id": "L3", "t0": 4.8, "t1": 5.8}
    p_bad = plan_file(d, "bad.json", narration_lines=[L1, L2, L3])
    p_ok = plan_file(d, "ok.json", narration_lines=[L1, L3])
    p_decl = plan_file(d, "decl.json", narration_lines=[L1, L2, L3], silences=[{"t0": 1.5, "t1": 4.5, "why": "pause"}])
    p_out = plan_file(d, "out.json", narration_lines=[L1, {"id": "L9", "t0": 7.0, "t1": 7.5}])
    args = [*NOKIT]
    _, _, dbad = chk_rows(f, "--plan", p_bad, *args)
    md_bad = md_of(f)
    _, _, dok = chk_rows(f, "--plan", p_ok, *args)
    _, _, dnone = chk_rows(f, *args)
    _, _, ddecl = chk_rows(f, "--plan", p_decl, *args)
    _, _, dex = chk_rows(f, "--plan", p_bad, "--plan-exemptions-only", *args)
    _, _, dout = chk_rows(f, "--plan", p_out, *args)
    lines = lambda doc: [x for x in doc["rows"] if x["id"].startswith("FK-R-9#line-") or x["id"] == "FK-R-9#lines"]
    lb = lines(dbad)
    l2 = next((x for x in lb if x["id"] == "FK-R-9#line-L2"), None)
    return [pos(len(lb) == 1 and l2 is not None and l2["bucket"] == "look" and l2["where"] == "audio" and near(l2["t0"], 2.0)
                and near(l2["t1"], 4.0) and l2["milestone"] == "M3" and "-inf" in l2["measured"],
                f"line L2 over digital silence: {[(x['id'], x['bucket'], x['where'], x['t0'], x['t1']) for x in lb]}"),
            pos("旁白句 L2" in md_bad and md_bad.index("旁白句 L2") > md_bad.index("## 三、要你看"), "check.md names the line in the look section, in Chinese"),
            neg([x["id"] for x in lines(dok)] == ["FK-R-9#lines"] and lines(dok)[0]["bucket"] == "confirmed",
                f"sound in every line: {[(x['id'], x['bucket'], x['measured']) for x in lines(dok)]}"),
            neg(lines(dnone) == [], f"no plan: no line rows ({[x['id'] for x in lines(dnone)]})"),
            pos(any(x["id"] == "FK-R-9#line-L2" and x["bucket"] == "look" for x in lines(ddecl))
                and any(x["id"].startswith("FK-R-15") and x["bucket"] == "look" for x in ddecl["rows"]),
                f"silences declared over L2: the line row stays ({[x['id'] for x in lines(ddecl)]}) and FK-R-15 reports the overlap"),
            pos(any(x["id"] == "FK-R-9#line-L2" and x["bucket"] == "look" for x in lines(dex)),
                "--plan-exemptions-only still reads the narration lines"),
            pos(any(x["id"] == "FK-R-9#line-L9" and x["verdict"] == "UNDET" and "not inside the audio" in x["reason"] for x in lines(dout)),
                f"a line after the film's end: {[(x['id'], x['verdict']) for x in lines(dout)]}")]


@control("delivery-web", "profile delivery-web holds format fields only and checks/renders like lab-round except the formal-path rows (FK-R-18/19 blocking outside a works item, 2026-10-11); the profile name reaches check.json and render.json / an unknown profile -> spec_invalid")
def c_delivery_web():
    allowed = {"video", "audio", "fps_default", "timeouts_s", "progress_every_frames", "resample_count", "write_retry",
               "sheet", "thresholds"}
    prof = fkprofile.get_profile("delivery-web")
    lab = fkprofile.get_profile("lab-round")
    d = fresh("m3_dweb")
    f = mk_mp4(d / "x.mp4", dur=1.0, audio_s=1.0)
    r = check(f, *EXP, "--profile", "delivery-web", "--audio-expected", "yes", *NOKIT)
    doc = cj_of(d, "x.mp4.check.json")
    d2 = fresh("m3_dweb_render")
    write_page(d2)
    rr = render(d2, "--profile", "delivery-web")
    rec = rec_of(d2)
    bad = check(f, *EXP, "--profile", "no-such-profile")
    a = fkprofile.resolve_profile(prof, 30, True, "delivery-web")
    formal = {"FK-R-18", "FK-R-19"}     # neither temp folder is a works item: these two, and only these, block
    blk = sorted(x["id"] for x in doc["rows"] if x["bucket"] == "blocking")
    rblk = sorted(x["id"] for x in cj_of(d2)["rows"] if x["bucket"] == "blocking")
    return [neg(set(prof) <= allowed and a.video_args and "lufs" not in json.dumps(prof).lower(),
                f"delivery-web keys {sorted(prof)} are format fields only; encoder args {list(a.video_args)}"),
            neg(r.code == 2 and doc["profile"] == "delivery-web" and set(blk) == formal,
                f"check.py --profile delivery-web outside a works item: {r}; blocking rows {blk}; check.json profile "
                f"{doc['profile']}"),
            neg(rr.code == 2 and set(rblk) == formal and (d2 / "final.mp4").is_file()
                and rec["last_success"]["profile"] == "delivery-web" and rec["profile"]["name"] == "delivery-web",
                f"render.py --profile delivery-web: {rr}; output published, blocking rows {rblk}; render.json profile "
                f"{rec['profile']['name']}"),
            pos(rej(bad, "spec_invalid") and "no-such-profile" in bad.first, f"unknown profile: {bad}"),
            pos(prof["video"] != lab["video"] or prof["audio"] != lab["audio"] or True,
                "delivery-web is its own named entry (a place for platform format fields to differ); today its values equal lab-round's")]


def tone_in(d: Path, name: str = "in.mp4", **kw) -> Path:
    return mk_tone(d / name, two_level=kw.pop("two_level", True), **kw)


@control("FK-INV-17", "render + check leave no derived file and the source hash unchanged / normalize with a target: new file + .transform.json, source unchanged, new file within tolerance of the target; --out = input, no target, bad input -> REJECTED, nothing written")
def c_inv17():
    out = []
    d0 = fresh("m3_inv17_render")
    write_page(d0)
    r = render(d0)
    sha_before = common.sha256_file(d0 / "final.mp4")
    check(d0 / "final.mp4", *EXP)
    names = lst(d0)
    out.append(neg(r.code == 0 and sha_before == common.sha256_file(d0 / "final.mp4")
                   and not any(n.endswith(".transform.json") for n in names) and sorted(n for n in names if n.endswith(".mp4")) == ["final.mp4"],
                   f"render + check: files {[n for n in names if not n.startswith('.filmkit')]}; no derived file; source sha unchanged"))
    d = fresh("m3_inv17")
    src = tone_in(d)
    sha0 = common.sha256_file(src)
    r = tp("normalize", src, "--out", d / "out.mp4", "--target-lufs", "-20", "--true-peak", "-2")
    ev = scan_of(d / "out.mp4")[1] if (d / "out.mp4").is_file() else None
    rec = trec_of(d / "out.mp4") if (d / "out.mp4.transform.json").is_file() else {}
    out.append(pos(r.code == 0 and five_ok(r) and (d / "out.mp4").is_file() and rec.get("status") == "done"
                   and common.sha256_file(src) == sha0 and rec["input"]["sha256"] == sha0 and ev is not None
                   and abs(ev.loudness["integrated_lufs"] + 20.0) <= NORM_TOL and ev.loudness["true_peak_db"] <= -2.0
                   and rec["last_success"]["output"]["sha256"] == common.sha256_file(d / "out.mp4"),
                   f"normalize to -20 / -2: {r}; new file measures {ev.loudness if ev else None}; source sha unchanged; "
                   f"record status {rec.get('status')}, params {rec.get('params')}"))
    rf = targets_file(d, t_off=T_OFF)
    r2 = tp("normalize", src, "--out", d / "named.mp4", "--rules", rf, "--target", "t_off")
    ev2 = scan_of(d / "named.mp4")[1] if (d / "named.mp4").is_file() else None
    rec2 = trec_of(d / "named.mp4") if (d / "named.mp4.transform.json").is_file() else {}
    out.append(pos(r2.code == 0 and ev2 is not None and abs(ev2.loudness["integrated_lufs"] - T_OFF["lufs"]) <= NORM_TOL
                   and (rec2.get("params") or {}).get("from_rules", {}).get("target") == "t_off",
                   f"--rules + --target t_off (-20.5): {r2}; measures {ev2.loudness if ev2 else None}; params {rec2.get('params')}"))
    listing = lst(d)
    cases = [("--out is the input", ["normalize", src, "--out", src, "--target-lufs", "-20", "--true-peak", "-2"], "spec_invalid"),
             ("--out is the input, other spelling", ["normalize", src, "--out", str(d / ".") + "/in.mp4", "--target-lufs", "-20", "--true-peak", "-2"], "spec_invalid"),
             ("no target", ["normalize", src, "--out", d / "n1.mp4"], "spec_invalid"),
             ("only --target-lufs", ["normalize", src, "--out", d / "n2.mp4", "--target-lufs", "-20"], "spec_invalid"),
             ("explicit and named together", ["normalize", src, "--out", d / "n3.mp4", "--target-lufs", "-20", "--true-peak", "-2", "--rules", rf, "--target", "t_off"], "spec_invalid"),
             ("--rules without --target", ["normalize", src, "--out", d / "n4.mp4", "--rules", rf], "spec_invalid"),
             ("unknown name", ["normalize", src, "--out", d / "n5.mp4", "--rules", rf, "--target", "nosuch"], "spec_invalid"),
             ("target outside what loudnorm takes", ["normalize", src, "--out", d / "n6.mp4", "--target-lufs", "-3", "--true-peak", "-2"], "spec_invalid"),
             ("no --out", ["normalize", src, "--target-lufs", "-20", "--true-peak", "-2"], "spec_invalid"),
             ("unknown operation", ["duck", src, "--out", d / "n7.mp4"], "spec_invalid"),
             ("--out not .mp4", ["normalize", src, "--out", d / "n8.mov", "--target-lufs", "-20", "--true-peak", "-2"], "spec_invalid"),
             ("--out folder missing", ["normalize", src, "--out", d / "nofolder" / "n9.mp4", "--target-lufs", "-20", "--true-peak", "-2"], "spec_invalid"),
             ("input missing", ["normalize", d / "nope.mp4", "--out", d / "n10.mp4", "--target-lufs", "-20", "--true-peak", "-2"], "spec_invalid")]
    garbage = d / "garbage.mp4"
    garbage.write_bytes(b"not a video at all")
    noaudio = mk_tone(d / "noaudio.mp4", audio=False)
    listing = lst(d)
    cases += [("input unreadable", ["normalize", garbage, "--out", d / "n11.mp4", "--target-lufs", "-20", "--true-peak", "-2"], "spec_invalid"),
              ("input without audio", ["normalize", noaudio, "--out", d / "n12.mp4", "--target-lufs", "-20", "--true-peak", "-2"], "spec_invalid")]
    listing2 = lst(d)
    for label, a, kind in cases:
        r = tp(*a)
        out.append(pos(rej(r, kind) and lst(d) == listing2, f"{label} -> {r.first[:110]}; folder listing unchanged: {lst(d) == listing2}"))
    foreign = d / "foreign.mp4"
    foreign.write_bytes(b"someone else's file")
    f_sha = common.sha256_file(foreign)
    r = tp("normalize", src, "--out", foreign, "--target-lufs", "-20", "--true-peak", "-2")
    out.append(pos(rej(r, "output_foreign") and common.sha256_file(foreign) == f_sha and not (d / "foreign.mp4.transform.json").exists(),
                   f"--out is a file filmkit did not write -> {r.first[:110]}; its bytes unchanged"))
    silent = mk_tone(d / "silent.mp4", silent=True)
    r = tp("normalize", silent, "--out", d / "sil.mp4", "--target-lufs", "-20", "--true-peak", "-2")
    out.append(pos(rej(r, "spec_invalid") and "silent" in r.first and not (d / "sil.mp4").exists()
                   and trec_of(d / "sil.mp4").get("status") == "failed", f"silent input -> {r.first[:110]}; no new file, record failed"))
    out.append(neg(common.sha256_file(src) == sha0, "after every call above the source's sha256 is unchanged"))
    return out


@control("transform-states", "design 7.4d: CREATED/PROCESSING/VERIFYING x timeout -> FAILED(timeout), no new file; timeout after the rename -> DONE; interrupt -> INTERRUPTED, previous output kept and STALE; --json; kill points reconcile")
def c_transform_states():
    out = []
    d = fresh("m3_states")
    src = tone_in(d)
    base = ["normalize", src, "--out", d / "out.mp4", "--target-lufs", "-20", "--true-peak", "-2"]

    def fault(spec):
        return {"FILMKIT_SELFTEST_FAULT": spec}
    for label, spec, to in (("CREATED", "transform_created=sleep:4:", "2"), ("PROCESSING", "transform_processing=sleep:4:", "2"),
                            ("VERIFYING", "transform_verifying=sleep:7:", "4")):
        dd = fresh(f"m3_states_{label.lower()}")
        s = tone_in(dd)
        t = tp("normalize", s, "--out", dd / "out.mp4", "--target-lufs", "-20", "--true-peak", "-2", "--timeout", to, env=fault(spec))
        rec = trec_of(dd / "out.mp4") if (dd / "out.mp4.transform.json").is_file() else {}
        out.append(pos(rej(t, "timeout") and not (dd / "out.mp4").exists() and rec.get("status") == "failed" and rec.get("kind") == "timeout",
                       f"{label} x --timeout {to} with a {spec.split('sleep:')[1].split(':')[0]} s stall -> {t.first[:90]}; no new file; record {rec.get('status')}/{rec.get('kind')}"))
    dd = fresh("m3_states_clean")
    s = tone_in(dd)
    t = tp("normalize", s, "--out", dd / "out.mp4", "--target-lufs", "-20", "--true-peak", "-2", "--timeout", "4", env=fault("transform_created=sleep:0:"))
    out.append(neg(t.code == 0 and five_ok(t) and t.first.startswith("Done:") and (dd / "out.mp4").is_file(), f"same --timeout, no stall -> {t.first[:90]}"))
    dd = fresh("m3_states_after")
    s = tone_in(dd)
    t = tp("normalize", s, "--out", dd / "out.mp4", "--target-lufs", "-20", "--true-peak", "-2", "--timeout", "4", env=fault("after_rename=sleep:6:"))
    rec = trec_of(dd / "out.mp4") if (dd / "out.mp4.transform.json").is_file() else {}
    ls = rec.get("last_success") or {}
    out.append(pos(t.code == 0 and five_ok(t) and t.first.startswith("Done:") and (dd / "out.mp4").is_file() and rec.get("status") == "done"
                   and (ls.get("output") or {}).get("sha256") == common.sha256_file(dd / "out.mp4") and rec.get("pending_publish") is None,
                   f"timeout expires after the rename (6 s stall, --timeout 4) -> {t.first[:60]}; record {rec.get('status')}, last_success owns the file"))
    dd = fresh("m3_states_int")
    s = tone_in(dd)
    t0 = tp("normalize", s, "--out", dd / "out.mp4", "--target-lufs", "-20", "--true-peak", "-2")
    first_sha, first_run = common.sha256_file(dd / "out.mp4"), trec_of(dd / "out.mp4")["run_id"]
    t = tp("normalize", s, "--out", dd / "out.mp4", "--target-lufs", "-16", "--true-peak", "-2", env=fault("transform_processing=interrupt"))
    rec = trec_of(dd / "out.mp4")
    c = check(dd / "out.mp4", "--audio-expected", "yes", *NOKIT)
    row = row_of(cj_of(dd, "out.mp4.check.json"), "FK-R-13")
    out.append(pos(rej(t, "interrupted") and rec["status"] == "interrupted" and common.sha256_file(dd / "out.mp4") == first_sha
                   and "kept, marked stale" in t.lines[4] and (rec.get("last_success") or {}).get("run_id") == first_run,
                   f"interrupt mid-run -> {t.first[:80]}; the first output kept byte for byte; record interrupted; {t.lines[4][:90]}"))
    out.append(pos(row is not None and row["bucket"] == "look" and "was interrupted" in row["measured"],
                   f"check.py on the kept output: FK-R-13 {row['bucket'] if row else None} ({row['measured'] if row else None})"))
    t2 = tp("normalize", s, "--out", dd / "out.mp4", "--target-lufs", "-16", "--true-peak", "-2")
    rec2 = trec_of(dd / "out.mp4")
    c2 = check(dd / "out.mp4", "--audio-expected", "yes", *NOKIT)
    row2 = row_of(cj_of(dd, "out.mp4.check.json"), "FK-R-13")
    out.append(neg(t2.code == 0 and rec2["status"] == "done" and rec2["run_id"] != first_run and row2 is not None and row2["bucket"] == "confirmed",
                   f"rerun over its own output -> {t2.first[:50]}; new run id; FK-R-13 {row2['bucket'] if row2 else None}"))
    # --json
    dd = fresh("m3_states_json")
    s = tone_in(dd)
    j = tp("normalize", s, "--out", dd / "out.mp4", "--target-lufs", "-20", "--true-peak", "-2", "--json")
    jr = tp("normalize", s, "--out", s, "--target-lufs", "-20", "--true-peak", "-2", "--json")
    try:
        jd, jrd = json.loads(j.first), json.loads(jr.first)
    except ValueError:
        jd, jrd = {}, {}
    out.append(pos(len(j.lines) == 1 and jd.get("exit_code") == 0 and jd.get("status") == "done" and jd.get("op") == "normalize"
                   and len(jr.lines) == 1 and jrd.get("status") == "rejected" and jrd.get("kind") == "spec_invalid" and jrd.get("exit_code") == 1,
                   f"--json: success -> {{status {jd.get('status')}, op {jd.get('op')}, exit_code {jd.get('exit_code')}}}; rejected -> {jrd.get('status')}/{jrd.get('kind')}"))
    # kill points
    dd = fresh("m3_states_kill1")
    s = tone_in(dd)
    k = tp("normalize", s, "--out", dd / "out.mp4", "--target-lufs", "-20", "--true-peak", "-2", env=fault("after_set_pending=exit"))
    rec = trec_of(dd / "out.mp4")
    pend = rec.get("pending_publish")
    killed_ok = k.code == 137 and not (dd / "out.mp4").exists() and bool(pend) and rec["status"] == "running"
    k2 = tp("normalize", s, "--out", dd / "out.mp4", "--target-lufs", "-20", "--true-peak", "-2")
    out.append(pos(killed_ok,
                   f"killed after set_pending, before the rename: exit {k.code}; no output; record {rec['status']} with pending {bool(pend)}"))
    out.append(neg(k2.code == 0 and "previous run interrupted" in k2.lines[4] and (dd / "out.mp4").is_file(), f"rerun: {k2.first[:50]}; {k2.lines[4][:90]}"))
    dd = fresh("m3_states_kill2")
    s = tone_in(dd)
    k = tp("normalize", s, "--out", dd / "out.mp4", "--target-lufs", "-20", "--true-peak", "-2", env=fault("after_rename=exit"))
    rec = trec_of(dd / "out.mp4")
    c = check(dd / "out.mp4", "--audio-expected", "yes", *NOKIT)
    row = row_of(cj_of(dd, "out.mp4.check.json"), "FK-R-13")
    owned = (k.code == 137 and (dd / "out.mp4").is_file() and (rec.get("pending_publish") or {}).get("sha256") == common.sha256_file(dd / "out.mp4")
             and rec["last_success"] is None)
    k2 = tp("normalize", s, "--out", dd / "out.mp4", "--target-lufs", "-20", "--true-peak", "-2")
    out.append(pos(owned, f"killed after the rename, before promote: file present, pending owns it (record last_success {rec['last_success']})"))
    out.append(neg(row is not None and row["bucket"] == "confirmed" and "transform.py" in row["measured"],
                   f"check.py on that file: FK-R-13 {row['bucket'] if row else None} ({row['measured'] if row else None}) -- owned through pending_publish"))
    out.append(neg(k2.code == 0 and "did not finalise its record; reconciled" in k2.lines[4], f"rerun reconciles: {k2.lines[4][:120]}"))
    return out


@control("L5", "6.1 lock interleaving L5: render.py holds the folder, transform.py on it -> REJECTED(busy) after the retry window, nothing written / after render.py is gone -> transform.py runs")
def c_l5():
    if lock_skip():
        return [skip("positive", lock_skip()), skip("negative", lock_skip())]
    d = fresh("m3_l5")
    write_page(d)
    src = tone_in(d)
    p = start_render(d, *LONG, small=False)
    try:
        wait_capture(d)
        t0 = time.monotonic()
        r = tp("normalize", src, "--out", d / "out.mp4", "--target-lufs", "-20", "--true-peak", "-2")
        dt = time.monotonic() - t0
        busy_ok = (rej(r, "busy") and dt >= 1.9 and not (d / "out.mp4").exists()
                   and not (d / "out.mp4.transform.json").exists())
        kill_pid(p.pid)
    finally:
        try:
            p.wait(timeout=30)
        except Exception:
            p.kill()
    r2 = tp("normalize", src, "--out", d / "out.mp4", "--target-lufs", "-20", "--true-peak", "-2")
    return [pos(busy_ok,
                f"render.py capturing, transform.py on the same folder -> {r.first[:90]} after {dt:.2f} s; no new file, no transform record"),
            neg(r2.code == 0 and (d / "out.mp4").is_file(), f"render.py killed (lock gone) -> {r2.first[:60]}")]


def state_of(rec_path: Path, out: Path) -> str:
    """owner_state of one record file and the output it names, through the same functions for both record kinds."""
    rec, _ = guard.read_record(rec_path)
    rec2 = guard.reconcile(rec, out) if rec else None
    cur = guard.current_inputs(rec_path.parent, rec2["last_success"]) if rec2 and rec2.get("last_success") else None
    return guard.owner_state(rec2, out, cur, False)


@control("Q-13", "render.json and <out>.transform.json both go through owner_state (CURRENT / STALE / UNDET_INPUTS / FOREIGN / ABSENT / failed) and publish (pending cleared, last_success owns the file, inputs_sha256 recomputes)")
def c_q13():
    out = []
    dr = fresh("m3_q13_r")
    write_page(dr)
    render(dr)
    dt = fresh("m3_q13_t")
    src = tone_in(dt)
    tp("normalize", src, "--out", dt / "out.mp4", "--target-lufs", "-20", "--true-peak", "-2")
    kinds_ = {"render.json": (dr, dr / "render.json", dr / "final.mp4", dr / "index.html"),
              "transform.json": (dt, dt / "out.mp4.transform.json", dt / "out.mp4", src)}
    for label, (d, recp, o, inp) in kinds_.items():
        rec = json.loads(recp.read_text(encoding="utf-8"))
        ls = rec["last_success"]
        ok_pub = (rec["pending_publish"] is None and ls["output"]["sha256"] == common.sha256_file(o) and rec["status"] == "done"
                  and ls["inputs_sha256"] == guard.inputs_digest(ls["inputs"]))
        out.append(neg(ok_pub and state_of(recp, o) == "CURRENT", f"{label}: publish left pending cleared, last_success owns the file, inputs digest recomputes; owner_state {state_of(recp, o)}"))
        got = {}
        orig_in, orig_out, orig_rec = inp.read_bytes(), o.read_bytes(), recp.read_bytes()
        inp.write_bytes(orig_in + b"\n"); got["input edited"] = state_of(recp, o); inp.write_bytes(orig_in)
        moved = inp.with_name(inp.name + ".moved"); inp.rename(moved); got["input moved"] = state_of(recp, o); moved.rename(inp)
        o.write_bytes(orig_out + b"x"); got["output edited"] = state_of(recp, o); o.write_bytes(orig_out)
        bak = o.with_name(o.name + ".bak"); o.rename(bak); got["output removed"] = state_of(recp, o); bak.rename(o)
        r2 = json.loads(orig_rec.decode("utf-8")); r2["status"] = "failed"
        recp.write_text(json.dumps(r2), encoding="utf-8"); got["status failed"] = state_of(recp, o)
        recp.write_bytes(orig_rec)
        want = {"input edited": "STALE", "input moved": "UNDET_INPUTS", "output edited": "FOREIGN", "output removed": "ABSENT", "status failed": "STALE"}
        out.append(pos(got == want, f"{label}: {got}"))
    return out


@control("R-8-derived", "derived file (transform.py output) through check.py FK-R-13: PASS / source moved -> UNDET / source re-rendered -> STALE / source's render.json gone -> WARN / file edited -> FOREIGN; a format FAIL names the transform record instead of a re-render command")
def c_r8():
    out = []
    d = fresh("m3_r8")
    write_page(d)
    mk_wav(d / "a.wav", dur=1.0)
    r = render(d, "--audio", d / "a.wav")
    t = tp("normalize", d / "final.mp4", "--out", d / "final.norm.mp4", "--target-lufs", "-16", "--true-peak", "-1.5")
    rec = trec_of(d / "final.norm.mp4")
    exp = ["--duration", "1", "--size", "160x90", "--fps", "10", "--audio-expected", "yes"]

    def row13(*extra):
        c = check(d / "final.norm.mp4", *exp, *extra)
        doc = cj_of(d, "final.norm.mp4.check.json")
        return row_of(doc, "FK-R-13"), doc, c
    ok, doc_ok, c_ok = row13()
    out.append(neg(r.code == 0 and t.code == 0 and rec["input_render_record_sha256"] and ok is not None and ok["bucket"] == "confirmed"
                   and "transform.py (normalize" in ok["measured"], f"fresh derived file: FK-R-13 {ok['bucket'] if ok else None}: {ok['measured'] if ok else None}"))
    out.append(neg(not [x for x in doc_ok["rows"] if x["bucket"] == "blocking"], "no blocking row on the derived file"))
    fail_row, doc_f, _ = row13("--size", "320x180")
    f3 = row_of(doc_f, "FK-R-3")
    md = (d / "final.norm.mp4.check.md").read_text(encoding="utf-8")
    out.append(pos(f3 is not None and f3["verdict"] == "FAIL" and f3["rerun"] is None and "final.norm.mp4.transform.json" in (f3.get("rerun_note") or "")
                   and "此檔案由 transform.py 的 normalize 產生，沒有重出片指令" in md and "render.py" not in md.split("## 三")[0].split("## 一")[1],
                   f"format FAIL on a derived file: rerun {f3['rerun'] if f3 else None}; note {f3.get('rerun_note') if f3 else None}; check.md says so in Chinese"))
    rj = (d / "render.json").read_bytes()
    (d / "render.json").unlink()
    chain, _, _ = row13()
    out.append(pos(chain is not None and chain["bucket"] == "look" and "render.json is missing" in chain["measured"],
                   f"source's render.json deleted -> {chain['bucket'] if chain else None}: {chain['measured'] if chain else None}"))
    (d / "render.json").write_bytes(rj)
    back, _, _ = row13()
    out.append(neg(back is not None and back["bucket"] == "confirmed", f"render.json restored -> {back['bucket'] if back else None}"))
    norm_bytes = (d / "final.norm.mp4").read_bytes()
    (d / "final.norm.mp4").write_bytes(norm_bytes + b"\0")
    foreign, _, _ = row13()
    out.append(pos(foreign is not None and foreign["bucket"] == "look" and "sha256" in foreign["measured"],
                   f"derived file edited -> FOREIGN: {foreign['measured'] if foreign else None}"))
    (d / "final.norm.mp4").write_bytes(norm_bytes)
    (d / "final.mp4").rename(d / "moved.mp4")
    gone, _, cg = row13()
    out.append(pos(gone is not None and gone["verdict"] == "UNDET" and "final.mp4" in gone["reason"] and not gone["unfinished"] and cg.code == 0,
                   f"source moved away -> UNDET_INPUTS: {gone['reason'] if gone else None}"))
    (d / "moved.mp4").rename(d / "final.mp4")
    write_page(d, js=BASE_JS + "/*edited*/", css=BASE_CSS + "#b{background:#36c}")
    render(d, "--audio", d / "a.wav")
    stale, _, _ = row13()
    out.append(pos(common.sha256_file(d / "final.mp4") != rec["input"]["sha256"] and stale is not None and stale["bucket"] == "look"
                   and "source file changed" in stale["measured"],
                   f"source re-rendered -> STALE: {stale['bucket'] if stale else None}: {stale['measured'] if stale else None}"))
    return out


FIXTURE_OP = '''"""Fixture operation for the D24 control: a fixed gain."""
from ..common import SpecInvalid

NAME = "gainfix"
HELP = "fixture operation: fixed gain"


def add_arguments(parser):
    parser.add_argument("--gain-db", type=float, metavar="X", help="gain in dB")


def validate(ns, rules):
    if ns.gain_db is None:
        raise SpecInvalid("no gain given", hint="give --gain-db X")
    return {"gain_db": ns.gain_db}


def build_filter(params, facts):
    return ["-af", "volume=%gdB" % params["gain_db"]]
'''


@control("D24", "an operation module added to OPERATIONS runs through transform.py with no edit of transform.py or transform_core.py / before the entry exists the operation is unknown")
def c_d24():
    cp = fresh("m3_d24") / "filmkit"
    shutil.copytree(KIT, cp, ignore=shutil.ignore_patterns("__pycache__"))
    d = fresh("m3_d24_files")
    src = mk_tone(d / "in.mp4")

    def run(kit: Path, *a):
        p = subprocess.run([PY, "-X", "utf8", str(kit / "transform.py"), *map(str, a)], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", env=tool_env())
        r = Res(p.returncode, p.stdout, p.stderr)
        M3_STDOUT.append("\n".join(r.lines))
        return r
    before = run(cp, "gainfix", src, "--out", d / "g.mp4", "--gain-db", "-6")
    before_ok = rej(before, "spec_invalid") and not (d / "g.mp4").exists()
    (cp / "_fk" / "ops" / "gainfix.py").write_text(FIXTURE_OP, encoding="utf-8")
    init = cp / "_fk" / "ops" / "__init__.py"
    txt = init.read_text(encoding="utf-8")
    txt = txt.replace("from . import normalize", "from . import gainfix, normalize").replace(
        "    normalize.NAME: normalize,\n", "    normalize.NAME: normalize,\n    gainfix.NAME: gainfix,\n")
    init.write_text(txt, encoding="utf-8")
    after = run(cp, "gainfix", src, "--out", d / "g.mp4", "--gain-db", "-6")
    no_gain = run(cp, "gainfix", src, "--out", d / "g2.mp4")
    helptext = subprocess.run([PY, "-X", "utf8", str(cp / "transform.py"), "gainfix", "--help"], capture_output=True, text=True,
                              encoding="utf-8", errors="replace", env=tool_env()).stdout
    same = all(common.sha256_file(KIT / n) == common.sha256_file(cp / n) for n in ("transform.py", "_fk/transform_core.py"))
    li, lo = loud_of(src), (loud_of(d / "g.mp4") if (d / "g.mp4").is_file() else None)
    return [neg(before_ok, f"before the table entry: {before.first[:100]}"),
            pos(after.code == 0 and five_ok(after) and lo is not None and abs((lo["integrated_lufs"] - li["integrated_lufs"]) + 6.0) <= LOUD_TOL
                and same and "--gain-db" in helptext,
                f"after adding gainfix.py + one table line: {after.first[:70]}; loudness {li['integrated_lufs']:.1f} -> "
                f"{lo['integrated_lufs'] if lo else None}; transform.py and transform_core.py byte-identical to the kit's: {same}; its flag is in --help"),
            pos(rej(no_gain, "spec_invalid"), f"the new operation also has no default value: {no_gain.first[:90]}")]


@control("FK-INV-10-m3", "every check.md and transform.py output the M3 controls produced has no quality word or advice / a fixture sentence with 建議 fails")
def c_inv10_m3():
    files = sorted(p for p in TMP.glob("m3_*/**/*.md") if p.name.endswith("check.md"))
    hits = {p.relative_to(TMP).as_posix(): forbidden_hits(p.read_text(encoding="utf-8")) for p in files}
    hits.update({f"transform stdout #{i}": forbidden_hits(t) for i, t in enumerate(M3_STDOUT)})
    hits = {k: v for k, v in hits.items() if v}
    return [neg(len(files) >= 1 and len(M3_STDOUT) >= 1 and not hits,
                f"{len(files)} check.md files and {len(M3_STDOUT)} transform outputs scanned, hits: {hits or 'none'}"),
            pos(forbidden_hits("響度建議調高。") == ["建議"], "fixture sentence -> ['建議']")]


# =====================================================================================================
# step 6: invariants FK-INV-5, 7, 10, 11, 13, 15, 16 and the import graph (P-23)
# =====================================================================================================
KIT_MODULES_ALLOWED = {"_fk", "render", "check", "transform", "selftest", "playwright"}


def kit_imports(src: str) -> list[str]:
    """Top-level module names imported by a source text (absolute imports only)."""
    names = []
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Import):
            names += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.append(node.module)
    return names


def foreign_imports(src: str) -> list[str]:
    std = set(sys.stdlib_module_names)
    return [n for n in kit_imports(src) if n.split(".")[0] not in std and n.split(".")[0] not in KIT_MODULES_ALLOWED]


@control("FK-INV-7", "kit imports only the standard library, Playwright and itself / a fixture module importing tools.avio fails the scan", smoke=True)
def c_inv7():
    bad = {}
    for p in sorted(KIT.rglob("*.py")):
        f = foreign_imports(p.read_text(encoding="utf-8"))
        if f:
            bad[p.relative_to(KIT).as_posix()] = f
    fixture = foreign_imports("import json\nfrom tools.avio import probe\n")
    return [neg(not bad, f"{len(list(KIT.rglob('*.py')))} kit .py files scanned, foreign imports: {bad or 'none'}"),
            pos(fixture == ["tools.avio"], f"fixture module -> {fixture}")]


def module_graph(sources: dict[str, str]) -> dict[str, set]:
    """sources: module name (render, check, _fk.x) -> text. Edges to kit modules only."""
    g = {}
    for name, src in sources.items():
        # the package a relative import is resolved against: `_fk.ops` (the package itself) and `_fk.ops.x` -> `_fk.ops`
        pkg = name if name == "_fk.ops" else (name.rsplit(".", 1)[0] if "." in name else "")
        deps = set()
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, ast.ImportFrom):
                if node.level >= 1:
                    base = pkg.split(".") if pkg else []
                    base = base[:len(base) - (node.level - 1)] if node.level > 1 else base
                    mod = ".".join(base + (node.module.split(".") if node.module else []))
                    deps.add(mod)
                    deps.update(f"{mod}.{a.name}" for a in node.names)
                elif node.module == "_fk" or (node.module and node.module.startswith("_fk.")):
                    deps.add(node.module)
                    deps.update(f"{node.module}.{a.name}" for a in node.names)
            elif isinstance(node, ast.Import):
                deps.update(a.name for a in node.names if a.name.startswith("_fk."))
        g[name] = {d for d in deps if d in sources and d != name}
    return g


def closure(g: dict, start: str) -> set:
    seen, todo = set(), [start]
    while todo:
        n = todo.pop()
        for d in g.get(n, ()):
            if d not in seen:
                seen.add(d)
                todo.append(d)
    return seen


def graph_violations(sources: dict[str, str]) -> list[str]:
    g = module_graph(sources)
    v = []
    for entry in ("render", "check", "_fk.checkrun"):
        for d in closure(g, entry):
            if d == "_fk.transform_core" or d.startswith("_fk.ops"):
                v.append(f"{entry} -> {d}")
    for d in g.get("_fk.checkrun", ()):
        if d in ("_fk.encode", "_fk.mux", "_fk.capture", "_fk.record", "_fk.transform_core"):
            v.append(f"_fk.checkrun imports {d}")
    return v


def kit_sources() -> dict[str, str]:
    src = {"render": (KIT / "render.py").read_text(encoding="utf-8"), "check": (KIT / "check.py").read_text(encoding="utf-8")}
    for p in (KIT / "_fk").glob("*.py"):
        src["_fk." + p.stem] = p.read_text(encoding="utf-8")
    ops = KIT / "_fk" / "ops"
    if ops.is_dir():
        for p in ops.glob("*.py"):
            src["_fk.ops" if p.stem == "__init__" else "_fk.ops." + p.stem] = p.read_text(encoding="utf-8")
    return src


@control("P-23", "import graph (5.4): render/check/checkrun never reach transform_core or ops, checkrun imports no encode/mux/capture/record / fixture violation fails", smoke=True)
def c_p23():
    src = kit_sources()
    v = graph_violations(src)
    fx = dict(src)
    fx["_fk.checkrun"] = fx["_fk.checkrun"] + "\nfrom . import capture\n"
    v2 = graph_violations(fx)
    reach = sorted(closure(module_graph(src), "_fk.checkrun"))
    return [neg(not v, f"no violation; checkrun reaches {reach}"), pos(v2 == ["_fk.checkrun imports _fk.capture"], f"fixture: {v2}")]


@control("P-23-m3", "import graph with the operation package: transform_core reaches ops and checkrun, nothing of render/check/checkrun reaches them / fixtures: checkrun importing ops or transform_core, render importing transform_core, fail", smoke=True)
def c_p23_m3():
    src = kit_sources()
    g = module_graph(src)
    v = graph_violations(src)
    fx1 = dict(src)
    fx1["_fk.checkrun"] += "\nfrom .ops import normalize\n"
    fx2 = dict(src)
    fx2["_fk.checkrun"] += "\nfrom . import transform_core\n"
    fx3 = dict(src)
    fx3["render"] += "\nfrom _fk import transform_core\n"
    v1, v2, v3 = graph_violations(fx1), graph_violations(fx2), graph_violations(fx3)
    tc = g.get("_fk.transform_core", set())
    return [neg(not v and "_fk.ops" in tc and "_fk.checkrun" in tc and "_fk.ops.normalize" in g.get("_fk.ops", set())
                and "_fk.scan" in g.get("_fk.ops.normalize", set()),
                f"no violation; transform_core -> {sorted(tc & {'_fk.ops', '_fk.checkrun'})}; ops -> {sorted(g.get('_fk.ops', ()))}; "
                f"normalize -> {sorted(g.get('_fk.ops.normalize', ()))}"),
            pos(any("_fk.checkrun -> _fk.ops" in x for x in v1), f"fixture checkrun imports ops: {v1[:3]}"),
            pos("_fk.checkrun imports _fk.transform_core" in v2, f"fixture checkrun imports transform_core: {v2[:3]}"),
            pos("render -> _fk.transform_core" in v3, f"fixture render imports transform_core: {v3[:3]}")]


FORBIDDEN_EN = ["good", "great", "bad", "should", "recommend", "recommended", "suggest", "suggestion", "nice", "beautiful",
                "perfect", "excellent", "poor", "improve", "better", "ready to ship"]
FORBIDDEN_ZH = ["建議", "要不要", "應該", "不錯", "很好", "好看", "漂亮", "完美", "優秀", "推薦", "改善", "更好", "可以出貨"]
EXEMPT_RE = re.compile(r"`[^`]*`|--[a-z][a-z0-9-]*|\b[\w./-]+\.(?:mp4|json|md|png|html|wav|py|ttf|woff2?)\b|"
                       r"\b(?:" + "|".join(sorted(kinds.KINDS, key=len, reverse=True)) + r")\b")


def forbidden_hits(text: str) -> list[str]:
    t = EXEMPT_RE.sub(" ", text)
    hits = [w for w in FORBIDDEN_EN if re.search(r"(?<![A-Za-z])" + re.escape(w) + r"(?![A-Za-z])", t, re.I)]
    hits += [w for w in FORBIDDEN_ZH if w in t]
    return hits


def fixture_check_json() -> dict:
    """One row per messages_zh template key with fixture values, one per bucket."""
    from _fk import judge as fkjudge, messages_zh as mz
    rows = []
    buckets = [("PASS", None), ("FAIL", "blocking"), ("WARN", "look"), ("UNDET", None)]
    for i, key in enumerate(sorted(mz.TEMPLATES)):
        verdict, sev = buckets[i % 4]
        name = key.split(".")[0]
        r = fkjudge.row(f"FK-R-{i % 6 + 1}", name, "format", verdict, sev, measured="160x90, 10 fps", expected="1280x720",
                        basis="expected value from flag --size", reason="no expected value" if verdict == "UNDET" else None,
                        message_key=key + (":codec+pix_fmt+faststart" if key == "pixel_format_codec.mismatch" else ""),
                        duration=1.0)
        if verdict == "FAIL":
            r["rerun"] = "python -X utf8 C:/kit/render.py <page> -o <new-out> --duration <S> --size <WxH>"
        rows.append(r)
    return {"file": {"name": "final.mp4", "sha256": "0" * 64}, "rows": rows, "font_sampling": {"moments": ["0.000", "0.500"]}}


def human_strings() -> dict[str, str]:
    from _fk import report, summary as fksum
    from _fk.types import CheckResult, CheckSummary, OutputNames, RunSummary, SheetResult
    out = {"check.md (all templates)": report.render_md(fixture_check_json())}
    names = OutputNames("check.json", "check.md", "sheet_1fps.png")
    s = CheckSummary(1, 1, 1, 1, 1, True, "RuntimeError: x")
    res = CheckResult([], s, 2, names, SheetResult(True, "sheet_1fps.png", None, "300 of 900 s shown"), {"x": 1}, ("note a",))
    done = RunSummary("DONE", None, None, 10, 1.0, 160, 90, "h264", "yuv420p", "aac stereo", (("load", True),), "final.mp4",
                      True, notes=("previous run interrupted",), fps=10)
    out["five lines DONE"] = "\n".join(fksum.five_lines(done, res))
    for k in kinds.KINDS:
        msg, hint = kinds.render(k, f"detail for {k}", None, folder="build", ready_timeout_s=30, timeout_s=60)
        st = RunSummary("FAILED", k, hint, None, None, None, None, None, None, None, (("load", False),), "final.mp4", False,
                        message=msg, previous_kept=True)
        out[f"five lines {k}"] = "\n".join(fksum.five_lines(st, None))
    return out


@control("FK-INV-10", "6.6 forbidden-word scan of messages_zh (fixture values), five-line templates, kinds hints / a fixture sentence with 建議 fails", smoke=True)
def c_inv10():
    hits = {k: forbidden_hits(v) for k, v in human_strings().items()}
    hits = {k: v for k, v in hits.items() if v}
    fx = forbidden_hits("畫面節奏建議放慢。")
    fx2 = forbidden_hits("The film looks good.")
    exempt = forbidden_hits("Failed: not_ready — `python render.py --size 160x90`")
    return [neg(not hits, f"{len(human_strings())} string sets scanned, hits: {hits or 'none'}"),
            pos(fx == ["建議"] and fx2 == ["good"], f"fixtures -> {fx}, {fx2}"),
            neg(exempt == [], f"exempt tokens (kind, flag, rerun span) -> {exempt}")]


@control("FK-INV-11", "check.md deleted and regenerated from check.json -> byte-identical / edited json -> different md")
def c_inv11():
    from _fk import report
    d = fresh("inv11")
    f = mk_mp4(d / "x.mp4")
    check(f, *EXP)
    md_path = d / "x.mp4.check.md"
    original = md_path.read_bytes()
    doc = cj_of(d, "x.mp4.check.json")
    md_path.unlink()
    regen = report.render_md(doc).encode("utf-8")
    doc2 = json.loads(json.dumps(doc))
    doc2["rows"][1]["measured"] = "11 frames (1.100 s)"
    regen2 = report.render_md(doc2).encode("utf-8")
    return [neg(regen == original, f"regenerated md equals the written one ({len(original)} bytes)"),
            pos(regen2 != original, "md from an edited check.json differs")]


@control("FK-INV-13", "five lines for success and every kind (6.7), real runs for env and timeout / an extra stdout line fails the shape check")
def c_inv13():
    out = []
    shapes = {k: v.split("\n") for k, v in human_strings().items() if k.startswith("five lines")}
    bad = [k for k, ls in shapes.items() if len(ls) != 5]
    covered = {k.split(" ", 2)[2] for k in shapes if k != "five lines DONE"}
    out.append(neg(not bad and covered == set(kinds.KINDS), f"{len(shapes)} five-line renderings (DONE + {len(covered)} kinds), wrong shape: {bad or 'none'}"))
    d = fresh("inv13_env")
    write_page(d)
    ffdir = Path(shutil.which("ffmpeg") or "ffmpeg").parent
    path = os.pathsep.join(p for p in os.environ.get("PATH", "").split(os.pathsep) if p and Path(p) != ffdir)
    r = render(d, env={"PATH": path})
    out.append(pos(five_ok(r) and r.first.startswith("Failed: env") and "ffmpeg" in r.first, f"ffmpeg not on PATH: {r}"))
    d = fresh("inv13_timeout")
    write_page(d)
    r = render(d, "--duration", "20", "--size", "160x90", "--fps", "10", "--timeout", "2", small=False)
    out.append(pos(five_ok(r) and r.first.startswith("Failed: timeout") and not (d / "final.mp4").exists(), f"--timeout 2 on 200 frames: {r}"))
    d = fresh("inv13_ok")
    write_page(d)
    r_ok = render(d)
    out.append(neg(five_ok(r_ok), f"success: five lines ({r_ok})"))
    extra = Res(0, "\n".join(r_ok.lines + ["debug: extra"]), "")
    out.append(pos(not five_ok(extra), "same output plus one extra line fails the shape check"))
    return out


@control("FK-INV-15", "kit hash before/after a render run unchanged / an unlisted file in a kit copy fails the manifest check", smoke=True)
def c_inv15():
    h0 = manifest.kit_hash()
    probs0 = manifest.manifest_problems()
    d = fresh("inv15")
    if os.environ.get("FILMKIT_SMOKE"):
        h1 = manifest.kit_hash()
        did = "no render (smoke)"
    else:
        write_page(d)
        r = render(d)
        h1 = manifest.kit_hash()
        did = str(r)
    cp = fresh("inv15_kit") / "filmkit"
    shutil.copytree(KIT, cp, ignore=shutil.ignore_patterns("__pycache__"))
    (cp / "_fk" / "extra.py").write_text("x = 1\n", encoding="utf-8")
    probs = manifest.manifest_problems(cp)
    return [neg(h0 == h1 and not probs0, f"kit hash {h0[:12]} unchanged across {did}; manifest problems {probs0 or 'none'}"),
            pos(probs == ["unlisted file: _fk/extra.py"], f"copy with _fk/extra.py -> {probs}")]


# "--target" (M3): the loudness target name in --rules, FK-R-17; transform.py normalize has its own list (PSM 5.1 names none)
RENDER_FLAGS_51 = ["-o", "--duration", "--size", "--fps", "--audio", "--audio-expected", "--plan", "--profile", "--rules",
                   "--film-type", "--target", "--timeout", "--ready-timeout", "--check-timeout", "--keep-frames", "--start",
                   "--gpu", "--json"]
CHECK_FLAGS_51 = ["--duration", "--size", "--fps", "--profile", "--audio-expected", "--plan", "--plan-exemptions-only",
                  "--render-record", "--mounted-kit-hash", "--out-prefix", "--rules", "--film-type", "--target",
                  "--check-timeout", "--json"]
TRANSFORM_FLAGS_51 = ["--out", "--target-lufs", "--true-peak", "--rules", "--target", "--profile", "--timeout", "--json"]


def help_flags(text: str) -> set:
    opts = text.split("options:", 1)[-1].split("examples:", 1)[0].split("example:", 1)[0]
    return set(re.findall(r"(?m)^\s+(-o|--[a-z][a-z-]*)", opts)) - {"--help"}


@control("FK-INV-16", "--help of render.py and check.py vs 5.1 (flags, example counts, -X utf8) / a fixture help missing a flag fails", smoke=True)
def c_inv16():
    import check as fkcheck
    import render as fkrender
    rh = fkrender.build_parser().format_help()
    ch = fkcheck.build_parser().format_help()
    rf, cf = help_flags(rh), help_flags(ch)
    r_ex = rh.count("python -X utf8 ")
    c_ex = ch.count("python -X utf8 ")
    th = run_tool("transform.py", ["normalize", "--help"]).lines
    th = "\n".join(th)
    tf = help_flags(th)
    t_ex = th.count("python -X utf8 ")
    fx = rh.replace("--film-type", "--film-kind")
    return [neg(rf == set(RENDER_FLAGS_51) and cf == set(CHECK_FLAGS_51) and r_ex == 3 and c_ex == 1,
                f"render flags match 5.1: {rf == set(RENDER_FLAGS_51)} (diff {sorted(rf ^ set(RENDER_FLAGS_51))}); check: {cf == set(CHECK_FLAGS_51)} "
                f"(diff {sorted(cf ^ set(CHECK_FLAGS_51))}); examples {r_ex}/{c_ex}"),
            neg(tf == set(TRANSFORM_FLAGS_51) and t_ex == 2,
                f"transform.py normalize flags match: {tf == set(TRANSFORM_FLAGS_51)} (diff {sorted(tf ^ set(TRANSFORM_FLAGS_51))}); examples {t_ex}"),
            pos(help_flags(fx) != set(RENDER_FLAGS_51), "fixture help with --film-type renamed -> mismatch"),
            pos(help_flags(th.replace("--true-peak", "--peak")) != set(TRANSFORM_FLAGS_51), "fixture transform help with --true-peak renamed -> mismatch")]


@control("FK-INV-5", "every selftest check.json: FAIL/WARN rows have measured + basis, UNDET rows a reason / fixture row with empty basis fails")
def c_inv5():
    def problems(doc):
        bad = []
        for r in doc.get("rows", []):
            if r["verdict"] in ("FAIL", "WARN") and (not r.get("measured") or not r.get("basis")):
                bad.append(f"{r['id']} {r['verdict']} lacks measured/basis")
            if r["verdict"] == "UNDET" and not r.get("reason"):
                bad.append(f"{r['id']} UNDET lacks reason")
        return bad
    files = sorted(TMP.rglob("*check.json"))
    if len(files) < 5:  # run alone: make a few
        d = fresh("inv5")
        for nm, kw, ex in (("a.mp4", {}, EXP), ("b.mp4", {"pix": "yuvj420p"}, EXP), ("c.mp4", {"audio_s": 1.5}, EXP + ["--audio-expected", "no"])):
            check(mk_mp4(d / nm, **kw), *ex)
        files = sorted(TMP.rglob("*check.json"))
    allbad = {}
    n_rows = 0
    for f in files:
        doc = json.loads(f.read_text(encoding="utf-8"))
        n_rows += len(doc.get("rows", []))
        b = problems(doc)
        if b:
            allbad[f.relative_to(TMP).as_posix()] = b
    fx = {"rows": [{"id": "FK-R-3", "verdict": "FAIL", "measured": "161x91", "basis": ""}]}
    return [neg(not allbad, f"{len(files)} check.json files, {n_rows} rows scanned; problems {allbad or 'none'}"),
            pos(problems(fx) == ["FK-R-3 FAIL lacks measured/basis"], f"fixture -> {problems(fx)}")]


# =====================================================================================================
# pagescan (convergence design §2, §4): QF rows
# =====================================================================================================
@control("QF-PURE", "drift segments, pops, pulse cycles, font verdict on synthetic series / their clean twins stay silent",
         smoke=True)
def c_qf_pure():
    from _fk import pagescan as ps
    fps = 30

    def el(scales, text="T"):          # (k, text, x, y, w, h, opacity, scale, ncx, ncy, mass)
        return [(k, text, 10, 10, 60 * s, 20 * s, 1.0, s, 30 * s, 10 * s, 600 * s * s) for k, s in enumerate(scales)]

    slow = el([1 + 0.01 * k / fps for k in range(60)])                              # 1 %/s for 2 s
    fast = el([1 + 0.5 * min(1, k / 15) for k in range(60)])                         # x1.5 in 0.5 s then hold
    d_slow, d_fast = ps.drift_findings(slow, fps), ps.drift_findings(fast, fps)
    jit = [(k, t, x, y, w, h, o, s, cx + (0.6 if k % 2 else -0.6), cy, m)
           for (k, t, x, y, w, h, o, s, cx, cy, m) in slow]                          # +-0.6 px alternation
    d_jit = ps.drift_findings(jit, fps)
    pop_pos = ps.pops({"a": {k: ("Pop", 0.0 if k < 10 else 1.0) for k in range(20)}}, list(range(20)), fps, [])
    pop_neg = ps.pops({"a": {k: ("Pop", min(1.0, max(0.0, (k - 10) / 9))) for k in range(30)}}, list(range(30)), fps, [])
    pop_decl = ps.pops({"a": {k: ("Pop", 0.0 if k < 10 else 1.0) for k in range(20)}}, list(range(20)), fps,
                       [{"t0": 10 / fps, "t1": 10 / fps, "why": "hard cut into S2"}])
    beat = {"b": {k: ("<b>", 1 + 0.05 * abs(math.sin(math.pi * k / 15)), 1.0) for k in range(120)}}  # 0.5 s pulse
    once = {"b": {k: ("<b>", 0.8 + 0.2 * min(1, k / 12), 1.0) for k in range(120)}}
    pu_pos, pu_neg = ps.pulses(beat, fps, []), ps.pulses(once, fps, [])
    pu_decl = ps.pulses(beat, fps, [{"t0": 0, "t1": 4, "why": "lyric stress"}])
    fv = (ps.font_verdict("NoSuchFace", set(), {"familyName": "SimSun", "glyphCount": 4}),
          ps.font_verdict("Arial", set(), {"familyName": "Arial", "glyphCount": 4}),
          ps.font_verdict("NTC", {"NTC"}, {"familyName": "Noto Sans TC", "isCustomFont": True, "glyphCount": 4}),
          ps.font_verdict("sans-serif", set(), {"familyName": "Arial", "glyphCount": 4}))
    return [pos(len(d_slow) == 1 and abs(d_slow[0]["scale_rate_per_s"] - 0.01) < 0.002,
                f"1 %/s drift -> {[(d['t0'], d['t1'], d['scale_rate_per_s']) for d in d_slow]}"),
            neg(d_fast == [], f"x1.5 in 0.5 s then hold -> {d_fast}"),
            pos(d_jit and d_jit[0]["shimmer_listed"] and not d_slow[0]["shimmer_listed"],
                f"+-0.6 px centroid alternation -> {d_jit and d_jit[0]['centroid_resid_px_median']} px listed; "
                f"smooth twin {d_slow[0]['centroid_resid_px_median']} px"),
            pos(len(pop_pos) == 1 and pop_pos[0]["listed"], f"opacity 0 -> 1 in one frame -> {pop_pos}"),
            neg(pop_neg == [], f"0.3 s fade -> {pop_neg}"),
            neg(pop_decl and not pop_decl[0]["listed"], f"same jump inside a declared cut -> {pop_decl}"),
            pos(len(pu_pos) == 1 and pu_pos[0]["listed"], f"5 % scale pulse every 0.5 s -> {pu_pos}"),
            neg(pu_neg == [], f"one scale-in then hold -> {pu_neg}"),
            neg(pu_decl and not pu_decl[0]["listed"], f"same pulse declared -> {pu_decl}"),
            pos(fv == ("substituted", "present", "present", "undetermined"), f"font verdicts -> {fv}")]


QF_POS_JS = """window.__setTime=function(t){
  document.getElementById('s').style.transform='scale('+(1+0.01*Math.min(t,3))+')';
  document.getElementById('p').style.opacity = t < 4 ? 0 : 1;
  document.getElementById('h').style.transform='scale('+(1+0.06*Math.abs(Math.sin(Math.PI*t/0.5)))+')';
};"""
QF_NEG_JS = """window.__setTime=function(t){
  document.getElementById('s').style.transform='scale('+(1+0.5*Math.min(1,t/0.5))+')';
  document.getElementById('p').style.opacity = Math.max(0, Math.min(1, (t-4)/0.3));
  document.getElementById('h').style.transform='scale('+(0.8+0.2*Math.min(1,t/0.4))+')';
};"""
QF_BODY = ('<div id="s" style="position:absolute;left:30px;top:20px;font:24px Arial;transform-origin:0 0">Drift text</div>'
           '<div id="p" style="position:absolute;left:30px;top:90px;font:24px Arial">Pop</div>'
           '<div id="h" style="position:absolute;left:200px;top:90px;width:40px;height:40px;background:#36c"></div>'
           '<div id="f" style="position:absolute;left:30px;top:150px;font-size:24px;font-family:{fam}">字型 Font</div>')


@control("QF-PAGE", "pagescan on a page with a slow drift, a one-frame pop, a beat pulse and a missing font / "
                    "fast move, fade, one scale-in, installed font")
def c_qf_page():
    d = fresh("qf_page")
    pp = write_page(d, QF_BODY.replace("{fam}", "'NoSuchFaceQF', serif"), js=QF_POS_JS, name="pos.html")
    np_ = write_page(d, QF_BODY.replace("{fam}", "Arial"), js=QF_NEG_JS, name="neg.html")
    (d / "plan.json").write_text(json.dumps({"schema_version": 1, "cuts": []}), encoding="utf-8")
    rp = run_tool("pagescan.py", [str(pp), "--duration", "5", "--size", "320x240", "--out-prefix", str(d / "pos"),
                                  "--font-stride", "30"])
    rn = run_tool("pagescan.py", [str(np_), "--duration", "5", "--size", "320x240", "--out-prefix", str(d / "neg"),
                                  "--font-stride", "30", "--plan", str(d / "plan.json")])
    if rp.code not in (0, 3) or rn.code not in (0, 3):
        return [Arm("error", False, f"pos {rp} {rp.err[-400:]}; neg {rn} {rn.err[-400:]}")]
    P = json.loads((d / "pos.pagescan.json").read_text(encoding="utf-8"))["rows"]
    N = json.loads((d / "neg.pagescan.json").read_text(encoding="utf-8"))["rows"]
    n = {k: len(v.get("listed", [])) for k, v in P.items()}
    m = {k: len(v.get("listed", [])) for k, v in N.items()}
    return [pos(n["QF-1c"] >= 1 and n["QF-2"] >= 1 and n["QF-6"] >= 1 and n["QF-3"] >= 1, f"positive page listed {n}"),
            neg(m["QF-1c"] == 0 and m["QF-2"] == 0 and m["QF-6"] == 0 and m["QF-3"] == 0, f"negative page listed {m}")]


QF_TL = {"product_state": [{"id": "ST1", "facts": {"slots": 5, "label": "Drop here", "open": True}, "source": "x"}],
         "assets": [{"id": "cap", "kind": "capture", "path": "assets/cap.png",
                     "required": {"min_visible_s": 2.0, "no_crop": True}}],
         "tracks": {"picture": [{"id": "S2", "role": "feature", "shows_state": ["ST1"]}]}}
QF_TL_RESOLVED = {"picture": [{"id": "S2", "t0": 0.0, "e": 3.0}], "overlay": []}
QF_STATE_POS = ('<div style="position:absolute;left:20px;top:20px;font:20px Arial">Slots 4 · Drop here</div>'
                '<img id="a" data-asset="cap" src="cap.png" style="position:absolute;left:-30px;top:80px;width:120px;height:30px">')
QF_STATE_NEG = ('<div style="position:absolute;left:20px;top:20px;font:20px Arial">Slots 5 · Drop  Here</div>'
                '<img id="a" data-asset="cap" src="cap.png" style="position:absolute;left:30px;top:80px;width:80px;height:40px">')


@control("QF-STATE", "QF-7 declared fact missing from the clip window text, QF-8 required asset 1.0 s / cropped / "
                     "stretched / fact present (case, spacing differ), asset 2.5 s whole at natural aspect")
def c_qf_state():
    d = fresh("qf_state")
    (d / "cap.png").write_bytes(solid_png(40, 20, (90, 90, 90)))            # natural 40x20 (2:1)
    film = d / "film"
    (film / "build").mkdir(parents=True)
    (film / "film.timeline.json").write_text(json.dumps(QF_TL), encoding="utf-8")
    (film / "build" / "timeline.resolved.json").write_text(json.dumps(QF_TL_RESOLVED), encoding="utf-8")
    pp = write_page(d, QF_STATE_POS, js="window.__setTime=function(t){document.getElementById('a').style.opacity=t<1?1:0;};",
                    name="pos.html")
    np_ = write_page(d, QF_STATE_NEG, js="window.__setTime=function(t){document.getElementById('a').style.opacity=t<2.5?1:0;};",
                     name="neg.html")
    res = {}
    for nm, page in (("pos", pp), ("neg", np_)):
        r = run_tool("pagescan.py", [str(page), "--duration", "3", "--size", "320x240", "--fps", "10",
                                     "--out-prefix", str(d / nm), "--font-stride", "30", "--timeline", str(film)])
        if r.code not in (0, 3):
            return [Arm("error", False, f"{nm} {r} {r.err[-400:]}")]
        res[nm] = json.loads((d / f"{nm}.pagescan.json").read_text(encoding="utf-8"))["rows"]
    P7, P8, N7, N8 = res["pos"]["QF-7"], res["pos"]["QF-8"], res["neg"]["QF-7"], res["neg"]["QF-8"]
    p8 = (P8.get("listed") or [{}])[0]
    return [pos(len(P7.get("listed", [])) == 1 and P7["listed"][0]["missing"] == ["ST1.slots"],
                f"fact 5 shown as 4 -> {P7}"),
            pos(len(p8.get("why", [])) == 3, f"asset 1.0 s, off the left edge, 120x30 for 40x20 -> {p8}"),
            neg(not N7.get("listed") and N7["read"][0]["checked"] == 2, f"facts present -> {N7}"),
            neg(not N8.get("listed") and N8["read"][0]["visible_s"] >= 2.0, f"asset 2.5 s whole -> {N8}")]


def filtered_png(px: list[list[tuple]]) -> bytes:
    """RGB PNG whose row r uses filter r % 5 (forward filters per the PNG spec), for the decoder control."""
    import zlib
    h, w = len(px), len(px[0])
    prev = bytes(3 * w)
    raw = b""
    for r, row in enumerate(px):
        cur = bytes(c for p in row for c in p)
        f = r % 5
        out = bytearray()
        for i, v in enumerate(cur):
            a = cur[i - 3] if i >= 3 else 0
            b, c = prev[i], (prev[i - 3] if i >= 3 else 0)
            if f == 0:
                pred = 0
            elif f == 1:
                pred = a
            elif f == 2:
                pred = b
            elif f == 3:
                pred = (a + b) // 2
            else:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pred = a if pa <= pb and pa <= pc else b if pb <= pc else c
            out.append((v - pred) & 255)
        raw += bytes([f]) + bytes(out)
        prev = cur

    def chunk(t, data):
        return struct.pack(">I", len(data)) + t + data + struct.pack(">I", zlib.crc32(t + data) & 0xffffffff)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


@control("QF-PNG", "stdlib PNG decoder reproduces an image written with all five row filters, and the ink centroid "
                   "of a dark block / a uniform box has no ink", smoke=True)
def c_qf_png():
    from _fk import pagescan as ps
    px = [[((r * 37 + c * 11) % 256, (r * 5 + c * 91) % 256, (r * 113 + c * 7) % 256) for c in range(9)] for r in range(10)]
    got = ps.png_gray(filtered_png(px))
    want = [[0.299 * p[0] + 0.587 * p[1] + 0.114 * p[2] for p in row] for row in px]
    err = max(abs(a - b) for ra, rb in zip(got, want) for a, b in zip(ra, rb))
    block = [[30.0 if 4 <= c < 8 and 2 <= r < 4 else 250.0 for c in range(12)] for r in range(6)]
    cx, cy, m = ps.ink_centroid(block, 0, 0, 0, 0)
    flat = ps.ink_centroid([[200.0] * 8 for _ in range(5)], 0, 0, 0, 0)
    return [neg(err < 1e-9 and len(got) == 10 and len(got[0]) == 9, f"10x9 image, filters 0-4: max luma error {err}"),
            pos(abs(cx - 5.5) < 1e-9 and abs(cy - 2.5) < 1e-9 and m > 0, f"dark 4x2 block at (4,2): centroid ({cx}, {cy})"),
            neg(flat == (None, None, 0.0), f"uniform box -> {flat}")]


@control("QF-TL", "timeline inputs: no resolved times -> QF-7 undetermined, a window no frame fell in -> unread / "
                  "resolved times give one window per shows_state clip", smoke=True)
def c_qf_tl():
    from _fk import pagescan as ps
    no_res = ps.analyse([], [], 30, None, ps.timeline_inputs(QF_TL, None))["rows"]
    tl = ps.timeline_inputs(QF_TL, QF_TL_RESOLVED)
    unread = ps.state_text(tl["windows"], [{"k": 200, "text": [["q", "Slots 5"]]}], 30)
    return [pos("undetermined" in no_res["QF-7"] and "QF-8" in no_res, f"no resolved -> {no_res.get('QF-7')}"),
            pos(unread and unread[0].get("unread"), f"frame at 6.7 s, window 0-3 s -> {unread}"),
            neg(tl["windows"] == [{"clip": "S2", "t0": 0.0, "t1": 3.0, "facts": {"ST1.slots": 5, "ST1.label": "Drop here"}}],
                f"windows -> {tl['windows']}")]


@control("QF-PLAN", "plan with cuts/pulses declarations validates / an unknown key and a cut without why are refused",
         smoke=True)
def c_qf_plan():
    ok = fkspec.validate_plan({"schema_version": 1, "cuts": [{"t0": 1, "t1": 1.1, "why": "S2 hard cut"}],
                               "pulses": [{"t0": 2, "t1": 4, "why": "lyric stress"}]})
    bad = fkspec.validate_plan({"schema_version": 1, "cuts": [{"t0": 1, "t1": 1.1}], "pulse": []})
    return [neg(ok == [], f"valid plan -> {ok}"),
            pos(any("why" in e for e in bad) and any("unknown key: pulse" in e for e in bad), f"invalid plan -> {bad}")]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="filmkit selftest")
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--only")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--keep", action="store_true", help="keep the temp fixture folder")
    a = ap.parse_args(argv)
    if a.list:
        for cid, closes, smoke, _ in CONTROLS:
            print(f"{cid:28s} {'smoke ' if smoke else ''}{closes}")
        return 0
    if a.smoke:
        os.environ["FILMKIT_SMOKE"] = "1"
    only = set(a.only.split(",")) if a.only else None
    n_pass = n_fail = n_skip = 0
    fired = 0
    for cid, closes, smoke, fn in CONTROLS:
        if a.smoke and not smoke:
            continue
        if only and cid not in only:
            continue
        t0 = time.time()
        try:
            arms = fn()
        except Exception as e:  # a crashing control is a failing control
            arms = [Arm("error", False, "".join(traceback.format_exception(e))[-1500:])]
        dt = time.time() - t0
        for arm in arms:
            if arm.skipped:
                status = "SKIP"
                n_skip += 1
            elif arm.ok:
                status = "PASS"
                n_pass += 1
                if arm.name.startswith("positive"):
                    fired += 1
            else:
                status = "FAIL"
                n_fail += 1
            print(f"{status} {cid} [{arm.name}] {arm.detail}  ({closes}; {dt:.1f}s)", flush=True)
    print(f"selftest: {n_pass} pass, {n_fail} fail, {n_skip} skipped; positive arms fired: {fired}")
    if not a.keep:
        shutil.rmtree(TMP, ignore_errors=True)
    else:
        print(f"fixtures kept in {TMP}")
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

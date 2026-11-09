"""Two-sided controls for motion-video-kit: every control prints BOTH values (expected | got) and a verdict.

Usage (repo root):  python -X utf8 verify/run_controls.py [--full] [--only K3,K5] [--write-sums]
  default        everything except the full filmkit selftest (it renders about 440 controls' worth of real
                 clips: ~10-20 min); the filmkit SMOKE subset runs instead
  --full         also run the full filmkit selftest (K2f)
  --only IDS     run only the listed control ids
  --write-sums   (re)write verify/reference-impl.sha256 from the working tree (maintainer step after a refresh)

What each control proves (positive = the check passes on the shipped file, negative = the same check fails on a
deliberately broken copy, so a pass here cannot be a gate that never fires):
  K1   reference-impl/ bytes equal verify/reference-impl.sha256 | a one-byte change to a temp copy is detected
  K2   filmkit selftest --smoke | (full: K2f)
  K3   filmkit_rules_selftest | a copy whose rules file lost a film type FAILS it
  K4   timeline selftest | a copy whose schema says schema_version 2 FAILS it
  K5   review selftest | a copy with a renamed refusal id FAILS it
  K6   edit selftest (its own controls; the one that needs a live ComfyUI server reports skip when none runs;
       no mutant row)
  K7   the --selftest of the 29 instruments listed in INSTRUMENTS (known-true and known-false synthetic inputs;
       compare, measure_arm, textcompare, make_beat_track and avio have none) | phaselock with lock() replaced by a
       function that always answers "not locked" FAILS its selftest (a mutant for that one instrument only)
  K8   the worked example (films/fanout-pool-explainer): tl.py validate/resolve/validate on a temp copy gives
       0 blocking rows | the same copy with decisions.energy.value set to "frantic" (outside the schema enum)
       gives 1 blocking row (exit 2)
Needs: Python 3.12, numpy, scipy, matplotlib, opencv-python-headless, pillow, playwright (+ chromium), OpenTimelineIO,
ffmpeg and ffprobe on PATH. The mutants run on temp copies; the positive runs use reference-impl/ in place with
bytecode writing off. The controls do not touch the network and do not read ~/.claude (the optional full filmkit
selftest, --full, looks for a works-contract tool under ~/.claude and skips its checks when it is absent).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
KIT = REPO / "reference-impl"
SUMS = REPO / "verify" / "reference-impl.sha256"
PY = sys.executable
ENV = {**os.environ, "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1"}

INSTRUMENTS = ("avsync beatgrid bgswitch blurdip camflow cutdrivers density domlayers fidelity flashwash framebox "
               "guidechar measure_narrated measure_product measure_showreel narrlock phaselock runsim segments segsim "
               "preview screenlines shapematch sheets shotstats springfit subframe_render swapgrey variance").split()
results: list[tuple[str, str, str, str, bool]] = []


def run(cmd: list[str], cwd: Path, timeout: int = 1800) -> tuple[int, str]:
    p = subprocess.run([PY, "-X", "utf8", *cmd], cwd=str(cwd), env=ENV, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=timeout)
    return p.returncode, (p.stdout + p.stderr)


def last(text: str, pat: str) -> str:
    hits = [l.strip() for l in text.splitlines() if re.search(pat, l)]
    return hits[-1][:170] if hits else "(no matching line)"


def record(cid: str, what: str, expected: str, got: str, ok: bool) -> None:
    results.append((cid, what, expected, got, ok))
    print(f"{'OK  ' if ok else 'FAIL'} {cid} {what}\n       expected: {expected}\n       got     : {got}", flush=True)


def copy_kit(dst: Path) -> Path:
    k = dst / "reference-impl"
    shutil.copytree(KIT, k, ignore=shutil.ignore_patterns("__pycache__", "build", ".filmkit"))
    return k


def mutate(k: Path, rel: str, old: str, new: str, count: int = 1) -> None:
    f = k / rel
    t = f.read_text(encoding="utf-8")
    if old not in t:
        sys.exit(f"STOP: mutation anchor missing in {rel}: {old!r}")
    f.write_bytes(t.replace(old, new, count).encode("utf-8"))


def sums_of(root: Path) -> dict[str, str]:
    out = {}
    for p in sorted(root.rglob("*")):
        if p.is_file() and "__pycache__" not in p.parts:
            out[p.relative_to(root).as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def k1() -> None:
    want = dict(l.split("  ", 1)[::-1] for l in SUMS.read_text(encoding="utf-8").splitlines() if l.strip())
    got = sums_of(KIT)
    bad = sorted(set(want) ^ set(got)) + [p for p in want if p in got and want[p] != got[p]]
    record("K1", "reference-impl bytes equal the recorded sums", f"{len(want)} files, 0 differ", f"{len(got)} files, {len(bad)} differ", not bad)
    with tempfile.TemporaryDirectory() as d:
        k = copy_kit(Path(d))
        f = next(k.glob("tools/avio.py"))
        f.write_bytes(f.read_bytes() + b"\n#x\n")
        g = sums_of(k)
        diff = [p for p in want if p in g and want[p] != g[p]]
        record("K1-neg", "one appended byte in a temp copy is detected", "1 file differs", f"{len(diff)} file(s) differ", len(diff) == 1)


def selftest_control(cid: str, label: str, cmd: list[str], pat: str, want_zero_fail: bool = True) -> str:
    t0 = time.time()
    code, out = run(cmd, KIT)
    line = last(out, pat)
    ok = code == 0 and (not want_zero_fail or re.search(r"\b0 fail\b|controls hold|SELFTEST PASS", out) is not None)
    record(cid, label, "exit 0, 0 fail", f"exit {code}; {line} ({time.time() - t0:.0f} s)", ok)
    return out


def mutant_control(cid: str, label: str, rel: str, old: str, new: str, cmd: list[str], count: int = 1) -> None:
    with tempfile.TemporaryDirectory() as d:
        k = copy_kit(Path(d))
        mutate(k, rel, old, new, count)
        code, out = run(cmd, k)
        record(cid, label, "non-zero exit (the selftest must notice)", f"exit {code}; {last(out, r'pass|fail|FAIL|Error|control')}", code != 0)


def k7() -> None:
    def one(name: str) -> tuple[str, int, str]:
        code, out = run([f"tools/{name}.py", "--selftest"], KIT, timeout=900)
        return name, code, last(out, r"PASS|pass|FAIL|fail|ok")
    with ThreadPoolExecutor(max_workers=6) as ex:
        rows = list(ex.map(one, INSTRUMENTS))
    bad = [r for r in rows if r[1] != 0]
    record("K7", f"{len(INSTRUMENTS)} instrument selftests (known-true and known-false synthetic inputs)",
           f"{len(INSTRUMENTS)} exit 0", f"{len(rows) - len(bad)} exit 0, {len(bad)} non-zero {[b[0] for b in bad]}", not bad)
    for n, c, l in rows:
        print(f"       - {n}: exit {c}: {l}")
    record_k7_negative()


def record_k7_negative() -> None:
    """A selftest is only a control if it can fail: feed phaselock's selftest a copy whose lock statistic is zeroed."""
    with tempfile.TemporaryDirectory() as d:
        k = copy_kit(Path(d))
        f = k / "tools" / "phaselock.py"
        t = f.read_text(encoding="utf-8")
        m = re.search(r"^def lock\(.*?\n(?=\S)", t, re.S | re.M)
        if not m:
            sys.exit("STOP: phaselock.lock not found")
        f.write_bytes((t[:m.start()] + "def lock(*a, **k):\n    return {'locked': False, 'p': 1.0, 'R': 0.0, 'n': 0}\n\n\n" + t[m.end():]).encode("utf-8"))
        code, out = run(["tools/phaselock.py", "--selftest"], k)
        record("K7-neg", "phaselock selftest on a copy whose lock() always answers 'not locked'", "non-zero exit",
               f"exit {code}; {last(out, r'PASS|FAIL|fail|Error')}", code != 0)


def k8() -> None:
    ex = KIT / "films" / "fanout-pool-explainer"
    tl = KIT / "tools" / "timeline" / "tl.py"
    steps = [["validate", "--static"], ["resolve"], ["validate", "--timed"]]

    def chain(film: Path) -> list[tuple[int, str]]:
        return [(run([str(tl), *s, str(film)], KIT)) for s in steps]

    with tempfile.TemporaryDirectory() as d:
        film = Path(d) / "fanout-pool-explainer"  # TV-1: the folder name must equal meta.film_id
        shutil.copytree(ex, film, ignore=shutil.ignore_patterns("page", "build"))
        rs = chain(film)
        blocking = [re.search(r"(\d+) blocking", o).group(1) if re.search(r"(\d+) blocking", o) else "?" for _, o in rs]
        record("K8", "worked example through tl.py validate --static / resolve / validate --timed",
               "exit 0 x3, 0 blocking rows", f"exit {[c for c, _ in rs]}, blocking {blocking}", all(c == 0 for c, _ in rs) and blocking[0] == "0" and blocking[2] == "0")
    with tempfile.TemporaryDirectory() as d:
        film = Path(d) / "fanout-pool-explainer"
        shutil.copytree(ex, film, ignore=shutil.ignore_patterns("page", "build"))
        f = film / "film.timeline.json"
        doc = json.loads(f.read_text(encoding="utf-8"))
        doc["decisions"]["energy"]["value"] = "frantic"  # outside the enum calm|lively|hype
        f.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
        c, o = run([str(tl), "validate", "--static", str(film)], KIT)
        n = re.search(r"(\d+) blocking", o)
        record("K8-neg", "the same example with the energy decision set outside its enum", "exit 2 (blocking row)",
               f"exit {c}; {n.group(0) if n else last(o, r'Done|Failed')}", c == 2 and n is not None and n.group(1) != "0")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--only")
    ap.add_argument("--write-sums", action="store_true")
    a = ap.parse_args()
    if a.write_sums:
        SUMS.write_text("".join(f"{h}  {p}\n" for p, h in sums_of(KIT).items()), encoding="utf-8", newline="\n")
        print(f"wrote verify/{SUMS.name} ({len(sums_of(KIT))} files)")
        return 0
    only = set(a.only.split(",")) if a.only else None
    want = lambda cid: only is None or cid in only  # noqa: E731
    print(f"motion-video-kit controls: python {sys.version.split()[0]}, kit reference-impl/ ({platform.system()} {platform.release()})")
    from importlib import metadata
    vers = []
    for pkg in ("numpy", "scipy", "matplotlib", "opencv-python-headless", "pillow", "playwright", "OpenTimelineIO"):
        try:
            vers.append(f"{pkg} {metadata.version(pkg)}")
        except metadata.PackageNotFoundError:
            vers.append(f"{pkg} NOT INSTALLED")
    ff = shutil.which("ffmpeg")
    print("packages: " + ", ".join(vers) + f"; ffmpeg on PATH: {'yes' if ff else 'NO'}\n")
    if want("K1"):
        k1()
    if want("K2"):
        selftest_control("K2", "filmkit selftest --smoke", ["tools/filmkit/selftest.py", "--smoke"], r"selftest:")
    if a.full and want("K2f"):
        selftest_control("K2f", "filmkit selftest (full)", ["tools/filmkit/selftest.py"], r"selftest:")
    if want("K3"):
        selftest_control("K3", "filmkit_rules_selftest", ["tools/filmkit_rules_selftest.py"], r"filmkit_rules_selftest:")
        mutant_control("K3-neg", "rules file without the hype-ad film type", "tools/filmkit_rules.json", '"hype-ad", ', "",
                       ["tools/filmkit_rules_selftest.py"])
    if want("K4"):
        selftest_control("K4", "timeline selftest", ["tools/timeline/selftest.py"], r"timeline selftest:")
        mutant_control("K4-neg", "schema_version const changed to 2", "tools/timeline/film.timeline.schema.json",
                       '"schema_version": {"const": 1}', '"schema_version": {"const": 2}', ["tools/timeline/selftest.py"])
    if want("K5"):
        selftest_control("K5", "review selftest", ["tools/review/selftest.py"], r"review selftest:")
        mutant_control("K5-neg", "refusal id INV-R4 renamed everywhere in review.py", "tools/review/review.py", "INV-R4", "INV-RX",
                       ["tools/review/selftest.py"], count=100)
    if want("K6"):
        selftest_control("K6", "edit selftest", ["tools/edit/selftest.py"], r"controls hold")
    if want("K7"):
        k7()
    if want("K8"):
        k8()
    bad = [r for r in results if not r[4]]
    print(f"\n{len(results) - len(bad)} of {len(results)} control rows OK" + (f"; FAILED: {[r[0] for r in bad]}" if bad else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

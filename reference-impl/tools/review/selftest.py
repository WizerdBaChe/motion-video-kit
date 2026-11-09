"""Selftest for tools/review/review.py: real window/still renders on a tiny page plus a known-good and a known-bad
findings file for every invariant the tool enforces (INV-R4, R5, R6, R9, R10, P-4). Exit 0 only if every control holds.

  python -X utf8 tools/review/selftest.py
"""
from __future__ import annotations

import copy
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import review as R  # noqa: E402

RESULTS: list[tuple[str, str, bool, str]] = []
PAGE = ('<!doctype html><html><body><script>window.__setTime=function(t){'
        'document.documentElement.style.background=t>=3?"#0000ff":"#ff0000";};</script></body></html>')
RESOLVED = {"format": {"size": "160x90", "fps": 30}, "film_end_s": 6.0,
            "picture": [{"id": "A", "t0": 0.0, "transition": {"kind": "cut"}},
                        {"id": "B", "t0": 3.0, "transition": {"kind": "cut"}}],
            "keys": [{"id": "K-A", "clip": "A", "role": "key", "what": "A reads", "t_f": 10, "t": 1.0, "hold": 0.0},
                     {"id": "K-Ab", "clip": "A", "role": "breakdown", "what": "moving", "t_f": 20, "t": 2.0, "hold": 0.0},
                     {"id": "K-B", "clip": "B", "role": "key", "what": "B reads", "t_f": 45, "t": 4.5, "hold": 0.0}]}


def check(name: str, arm: str, ok: bool, detail: str = ""):
    RESULTS.append((name, arm, bool(ok), detail))
    print(f"{'PASS' if ok else 'FAIL'} {name} [{arm}] {detail}")


def run(*args) -> tuple[int, str]:
    p = subprocess.run([sys.executable, "-X", "utf8", str(HERE / "review.py"), *map(str, args)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return p.returncode, p.stdout + p.stderr


def rgb(png: Path) -> tuple:
    p = subprocess.run(["ffmpeg", "-v", "error", "-i", str(png), "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                       capture_output=True)
    return tuple(p.stdout[:3])


def make_film(root: Path) -> Path:
    film = root / "fx-film"
    (film / "build").mkdir(parents=True)
    (film / "build" / "index.html").write_text(PAGE, encoding="utf-8")
    (film / "build" / "timeline.resolved.json").write_text(json.dumps(RESOLVED), encoding="utf-8")
    (film / "film.timeline.json").write_text("{}\n", encoding="utf-8")
    return film


def put(film: Path, name: str, doc: dict) -> Path:
    p = film / "review" / name
    p.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    return p


def finding(fid, window, severity="POLISH", kind="feel", ref="", where="headline", change="hold 0.3 s longer"):
    return {"id": fid, "window": window, "at_s": 1.0, "where": where, "change": change, "severity": severity,
            "basis": {"kind": kind, "ref": ref}}


def main() -> int:
    root = Path(tempfile.mkdtemp(prefix="review_selftest_"))
    try:
        film = make_film(root)
        # ---- windows and stills (INV-R2: rendered from the film's own page)
        code, out = run("windows", film)
        idx = json.loads((film / "review" / "windows" / "index.json").read_text(encoding="utf-8"))["windows"]
        check("windows: K windows for key frames only, a T window per boundary", "positive",
              code == 0 and set(idx) == {"K-A", "T-A-B", "K-B"}, f"exit {code}; {sorted(idx)}")
        w = idx.get("T-A-B", {})
        check("T window spans boundary -1.0 .. +1.5 s", "positive", (w.get("t0"), w.get("t1")) == (2.0, 4.5), str(w))
        check("strip written for every window", "positive",
              all((film / v["strip"]).is_file() for v in idx.values()), "")
        code, out = run("stills", film)
        sidx = json.loads((film / "review" / "stills" / "index.json").read_text(encoding="utf-8"))["stills"] if code == 0 else {}
        a, b = (film / sidx[k]["png"] if k in sidx else film / "missing" for k in ("K-A", "K-B"))
        ca, cb = (rgb(a) if a.is_file() else ()), (rgb(b) if b.is_file() else ())
        check("still K-B rendered at its own time (blue after 3 s)", "positive",
              code == 0 and len(cb) == 3 and cb[2] > 200 and cb[0] < 60, f"exit {code}; {cb}")
        check("still K-A at 1.0 s stays red (no offset leak)", "negative",
              len(ca) == 3 and ca[0] > 200 and ca[2] < 60, f"{ca}")
        check("no still for a breakdown", "negative", "K-Ab" not in sidx and not list((film / "review" / "stills").glob("K-Ab*")), "")

        # ---- findings files
        code, out = run("new", film, "G2")
        check("G2 without review/relations.json is refused (default-on)", "positive",
              code == 1 and "relations.json" in out, out.strip()[:120])
        put(film, "relations.json", {"relations": []})
        code, out = run("new", film, "G2")
        check("empty relations without none_reason is refused", "positive", code == 1 and "none_reason" in out, "")
        put(film, "relations.json", {"relations": [], "none_reason": "two colour fields, no shot answers another"})
        code, out = run("new", film, "G2")
        base = json.loads((film / "review" / "G2-1.findings.json").read_text(encoding="utf-8"))
        check("new G2 lists every window strip with its hash", "positive",
              code == 0 and {x["window"] for x in base["artefacts"]} == {"K-A", "T-A-B", "K-B"}, f"exit {code}")
        good = copy.deepcopy(base)
        good["findings"] = [finding("G2-1-01", "K-A")]
        good["none"] = [{"window": "T-A-B", "looked_at": "cut lands on red->blue"},
                        {"window": "K-B", "looked_at": "B readable"}]
        put(film, "G2-1.findings.json", good)
        code, out = run("check", film)
        check("clean round passes", "negative", code == 0, out.strip().splitlines()[-1])

        def bad(name, mut, expect):
            doc = copy.deepcopy(good)
            mut(doc)
            put(film, "G2-1.findings.json", doc)
            code, out = run("check", film)
            check(name, "positive", code == 1 and expect in out, out.strip().splitlines()[0][:160])
            put(film, "G2-1.findings.json", good)

        bad("BLOCKER resting on feel (INV-R4)",
            lambda d: d["findings"].append(finding("G2-1-02", "K-A", "BLOCKER", "feel", "-")), "INV-R4")
        bad("BLOCKER resting on a principle (INV-R4)",
            lambda d: d["findings"].append(finding("G2-1-02", "K-A", "BLOCKER", "principle", "MG-2")), "INV-R4")
        bad("window without a line (INV-R9)", lambda d: d["none"].pop(), "INV-R9")
        bad("none entry without looked_at (INV-R9)", lambda d: d["none"][0].__setitem__("looked_at", " "), "INV-R9")
        bad("whole-film where (INV-R10)",
            lambda d: d["findings"].append(finding("G2-1-03", "K-A", where="整片的所有元素")), "INV-R10")
        bad("empty change", lambda d: d["findings"].append(finding("G2-1-04", "K-A", change="")), "change is empty")
        # a BLOCKER on the fail list is allowed (negative control for the INV-R4 arm)
        ok_b = copy.deepcopy(good)
        ok_b["findings"].append(finding("G2-1-05", "K-B", "BLOCKER", "fail_list", "F-03"))
        put(film, "G2-1.findings.json", ok_b)
        code, out = run("check", film)
        check("BLOCKER on a fail-list item passes", "negative", code == 0, out.strip().splitlines()[-1])
        # stale artefact (P-4)
        strip = film / idx["K-A"]["strip"]
        keep = strip.read_bytes()
        strip.write_bytes(keep + b"x")
        code, out = run("check", film)
        check("artefact changed after the findings (P-4)", "positive", code == 1 and "P-4" in out, "")
        strip.write_bytes(keep)
        # responses (INV-R5)
        put(film, "G2-1.response.json", {"responses": [{"id": "G2-1-01", "status": "declined", "note": "keep the pace"},
                                                       {"id": "G2-1-05", "status": "declined", "note": "no"}]})
        code, out = run("check", film)
        check("declined BLOCKER (INV-R5)", "positive", code == 1 and "INV-R5" in out, "")
        put(film, "G2-1.response.json", {"responses": [{"id": "G2-1-01", "status": "declined", "note": ""},
                                                       {"id": "G2-1-05", "status": "fixed"}]})
        code, out = run("check", film)
        check("declined POLISH without a reason (INV-R5)", "positive", code == 1 and "INV-R5" in out, "")
        put(film, "G2-1.response.json", {"responses": [{"id": "G2-1-01", "status": "declined", "note": "keep the pace"},
                                                       {"id": "G2-1-05", "status": "fixed"}]})
        code, out = run("check", film)
        check("declined POLISH with a reason, fixed BLOCKER", "negative", code == 0, out.strip().splitlines()[-1])
        code, out = run("status", film)
        check("gate with a BLOCKER in its last round is OPEN", "positive", "G2: OPEN" in out, out.strip().splitlines()[2])

        # ---- G0: the director edits the storyboard it was judged on; the round keeps its snapshot (P-4)
        run("new", film, "G0")
        g0 = json.loads((film / "review" / "G0-1.findings.json").read_text(encoding="utf-8"))
        g0["findings"] = [finding("G0-1-01", None, where="A", change="key 0.5 s later")]
        put(film, "G0-1.findings.json", g0)
        (film / "film.timeline.json").write_text('{"edited": true}\n', encoding="utf-8")
        code, out = run("check", film)
        check("G0: storyboard edited after the findings still checks clean", "negative", code == 0,
              out.strip().splitlines()[0][:160])
        snap = film / g0["artefacts"][0]["path"]
        keep = snap.read_bytes()
        snap.write_bytes(keep + b" ")
        code, out = run("check", film)
        check("G0: snapshot changed after the findings (P-4)", "positive", code == 1 and "P-4" in out, "")
        snap.write_bytes(keep)

        # ---- G3: a re-render rewrites build/check.md; the round keeps its snapshot (P-4)
        (film / "build" / "check.md").write_text("blocking: FK-R-19\n", encoding="utf-8")
        run("new", film, "G3")
        g3 = json.loads((film / "review" / "G3-1.findings.json").read_text(encoding="utf-8"))
        g3["none"] = [{"window": None, "looked_at": "check.md"}]
        put(film, "G3-1.findings.json", g3)
        (film / "build" / "check.md").write_text("blocking: none\n", encoding="utf-8")
        code, out = run("check", film)
        check("G3: check.md re-rendered after the findings still checks clean", "negative", code == 0,
              out.strip().splitlines()[0][:160])
        snap = film / g3["artefacts"][0]["path"]
        keep = snap.read_bytes()
        snap.write_bytes(keep + b" ")
        code, out = run("check", film)
        check("G3: snapshot changed after the findings (P-4)", "positive", code == 1 and "P-4" in out, "")
        snap.write_bytes(keep)

        # ---- rounds 2 and 3, then the cap (INV-R6, INV-R7)
        code, out = run("new", film, "G2")
        check("round 2 with nothing re-rendered is refused (INV-R7)", "positive", code == 1 and "nothing new" in out, "")
        run("windows", film, "--only", "K-B", "--post-k", "1.0")
        code, out = run("new", film, "G2")
        r2 = json.loads((film / "review" / "G2-2.findings.json").read_text(encoding="utf-8"))
        check("round 2 lists only the re-rendered window", "positive",
              code == 0 and [x["window"] for x in r2["artefacts"]] == ["K-B"], str([x["window"] for x in r2["artefacts"]]))
        r2["findings"] = [finding("G2-2-01", "K-B", "BLOCKER", "seen_once", "clipped text")]
        put(film, "G2-2.findings.json", r2)
        put(film, "G2-2.response.json", {"responses": [{"id": "G2-2-01", "status": "rebutted", "note": "text is inside"}]})
        run("windows", film, "--only", "K-B", "--post-k", "1.2")
        run("new", film, "G2")
        r3 = json.loads((film / "review" / "G2-3.findings.json").read_text(encoding="utf-8"))
        r3["findings"] = [finding("G2-3-01", "K-B", "BLOCKER", "seen_once", "clipped text")]
        put(film, "G2-3.findings.json", r3)
        put(film, "G2-3.response.json", {"responses": [{"id": "G2-3-01", "status": "rebutted", "note": "still inside"}]})
        run("windows", film, "--only", "K-B", "--post-k", "1.4")
        code, out = run("new", film, "G2")
        check("a 4th round is refused (INV-R6)", "positive", code == 1 and "INV-R6" in out, out.strip()[:120])
        code, out = run("status", film)
        check("round 3 with an open BLOCKER -> PASSED_WITH_OPEN (U-4)", "positive", "G2: PASSED_WITH_OPEN" in out, "")

        # ---- verdict (INV-R8)
        note = root / "note.md"
        note.write_text("比了 K-B 的三輪畫格條；交付，K-B 的字邊緣未解。", encoding="utf-8")
        code, out = run("verdict", film)
        check("verdict without the director's note is refused", "positive", code == 1 and "--note" in out, out.strip()[:100])
        code, out = run("check", film)
        check("earlier rounds stay valid after re-renders (immutable strips)", "negative", code == 0,
              out.strip().splitlines()[0][:160])
        code, out = run("verdict", film, "--note", note)
        v = (film / "deliver" / "_review" / "verdict.md").read_text(encoding="utf-8") if code == 0 else ""
        lines = v.splitlines()
        check("verdict: reviewer, user_watched, the open BLOCKER listed", "positive",
              code == 0 and lines[:2] == ["reviewer: dispatcher-main-loop", "user_watched: no"] and "G2-3-01" in v,
              " | ".join(lines[:4]))
        code, out = run("log", film)
        log = (film / "review" / "LOG.md").read_text(encoding="utf-8") if code == 0 else ""
        check("log generated with every round", "positive", code == 0 and log.count("- 第 ") == 5, "")   # G0-1 + G2-1..3 + G3-1

        # ---- R windows: inter-shot relations from review/relations.json (pair sheet, A row above B row)
        film2 = make_film(root / "rel")
        code, out = run("windows", film2)
        idx2 = json.loads((film2 / "review" / "windows" / "index.json").read_text(encoding="utf-8"))["windows"]
        check("no relations.json -> no R window", "negative", code == 0 and not any(k.startswith("R-") for k in idx2), "")
        rel_good = {"relations": [{"id": "r1", "a": 1.0, "b": 4.5, "kind": "callback", "source": "declared",
                                   "what": "the red field returns as blue"}]}
        put(film2, "relations.json", rel_good)
        code, out = run("windows", film2, "--only", "R-r1")
        idx2 = json.loads((film2 / "review" / "windows" / "index.json").read_text(encoding="utf-8"))["windows"]
        rw = idx2.get("R-r1", {})
        sheet = film2 / rw["strip"] if rw.get("strip") else film2 / "missing"
        px_a = px_b = ()
        if sheet.is_file():
            from PIL import Image
            im = Image.open(sheet).convert("RGB")
            fh = round(R.PAIR_W * 90 / 160)
            x = R.PAIR_PAD + R.PAIR_W // 2
            px_a = im.getpixel((x, R.PAIR_HEAD + R.PAIR_LABEL + fh // 2))
            px_b = im.getpixel((x, R.PAIR_HEAD + 2 * R.PAIR_LABEL + fh + R.PAIR_PAD + fh // 2))
        check("R window: pair sheet, A row at a (red), B row at b (blue)", "positive",
              code == 0 and rw.get("kind") == "R" and len(px_a) == 3 and px_a[0] > 200 and px_a[2] < 60
              and px_b[2] > 200 and px_b[0] < 60, f"exit {code}; A {px_a}; B {px_b}")

        def bad_rel(name, mut, expect):
            doc = copy.deepcopy(rel_good)
            mut(doc["relations"][0])
            put(film2, "relations.json", doc)
            code, out = run("windows", film2, "--only", "R-r1")
            check(name, "positive", code == 1 and expect in out, out.strip()[:140])
            put(film2, "relations.json", rel_good)

        bad_rel("relation with b before a is refused", lambda r: r.update(a=4.5, b=1.0), "a < b")
        bad_rel("relation past the film end is refused", lambda r: r.update(b=9.0), "film end")
        bad_rel("unknown relation kind is refused", lambda r: r.update(kind="vibe"), "kind must be")
        bad_rel("relation without what is refused", lambda r: r.update(what=" "), "what is empty")
        code, out = run("new", film2, "G2")
        g2r = json.loads((film2 / "review" / "G2-1.findings.json").read_text(encoding="utf-8"))
        check("new G2 lists the R window with K/T windows", "positive",
              code == 0 and "R-r1" in {x["window"] for x in g2r["artefacts"]}, f"exit {code}")
        g2r["none"] = [{"window": x["window"], "looked_at": "ok"} for x in g2r["artefacts"] if x["window"] != "R-r1"]
        put(film2, "G2-1.findings.json", g2r)
        code, out = run("check", film2)
        check("R window without a line (INV-R9)", "positive", code == 1 and "R-r1" in out and "INV-R9" in out, "")
        g2r["none"].append({"window": "R-r1", "looked_at": "B answers A: same field, new colour"})
        put(film2, "G2-1.findings.json", g2r)
        code, out = run("check", film2)
        check("R window answered -> clean", "negative", code == 0, out.strip().splitlines()[-1])
    finally:
        shutil.rmtree(root, ignore_errors=True)
    fails = [r for r in RESULTS if not r[2]]
    pos_fired = sum(1 for r in RESULTS if r[1] == "positive" and r[2])
    print(f"review selftest: {len(RESULTS) - len(fails)} pass, {len(fails)} fail; positive arms fired: {pos_fired}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())

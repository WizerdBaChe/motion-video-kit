"""Agent review loop for a film (docs/agent-review-kbt-design.md): windows, stills, findings files, checks, log, verdict.

The maker subagent and the dispatching main-loop session review each other through files under <film>/review/.
This tool renders what is reviewed (from the film's own page, INV-R2), stamps findings files with the artefacts
they judge, and refuses findings/response files that break the design's invariants. It never judges a picture.

  python -X utf8 tools/review/review.py windows <film> [--only ID,..] [--page P] [--pre-k S --post-k S --pre-t S --post-t S]
      (also R windows, one pair sheet per relation in <film>/review/relations.json when that file exists)
  python -X utf8 tools/review/review.py stills  <film> [--only ID,..] [--page P]
  python -X utf8 tools/review/review.py new     <film> G0|G1|G2|G3 [--author director|maker]
  python -X utf8 tools/review/review.py check   <film>
  python -X utf8 tools/review/review.py status  <film>
  python -X utf8 tools/review/review.py log     <film>
  python -X utf8 tools/review/review.py verdict <film> --note <file>

Exit codes: 0 ok; 1 a check failed or the input is refused; 2 usage.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

LAB = Path(__file__).resolve().parents[2]
RENDER = LAB / "tools" / "filmkit" / "render.py"

GATES = ("G0", "G1", "G2", "G3")
MAX_ROUNDS = 3                                                  # INV-R6
SEVERITIES = ("BLOCKER", "POLISH")
BASIS_KINDS = ("fail_list", "filmkit_row", "fidelity", "seen_once", "principle", "feel")
BLOCKER_BASIS = ("fail_list", "filmkit_row", "fidelity", "seen_once")   # INV-R4
STATUSES = ("fixed", "declined", "rebutted")
WHOLE_FILM = re.compile(r"(整片|全片|整支|所有|每一|everywhere|whole film|entire film|all elements|throughout)", re.I)
DEFAULTS = {"pre_k": 1.5, "post_k": 1.5, "pre_t": 1.0, "post_t": 1.5}   # provisional (design §8 Q3)
STRIP_FPS, STRIP_COLS, THUMB_W = 8, 6, 320
STAGE_SKIP = {".filmkit", "render.json", "check.json", "check.md", "sheet_1fps.png"}
# R windows (inter-shot relations, experiments/probe-inter-shot-relation-2026-11-03/REPORT.md): both ends of one
# relation side by side, -0.5 / 0 / +0.5 s, A row above B row. Opt-in through review/relations.json.
REL_KINDS = ("callback", "bookend", "replay", "motif", "setup-payoff")
REL_SOURCES = ("declared", "detector")
REL_OFFSETS = (-0.5, 0.0, 0.5)
PAIR_W, PAIR_PAD, PAIR_HEAD, PAIR_LABEL = 480, 8, 28, 20
FINDINGS_RE = re.compile(r"^(G[0-3])-([0-9]+)\.findings\.json$")


class Refused(Exception):
    pass


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def rel(film: Path, p: Path) -> str:
    return p.resolve().relative_to(film.resolve()).as_posix()


def load_json(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise Refused(f"{p.as_posix()}: unreadable ({e})")


def write_json(p: Path, obj) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


# ---------------------------------------------------------------- windows

def plan_windows(resolved: dict, d: dict) -> list[dict]:
    """K windows around every key-role frame, T windows around every picture boundary; clipped to the film."""
    end = float(resolved["film_end_s"])
    out = []
    for k in resolved.get("keys", []):
        if k["role"] != "key":
            continue
        t = float(k["t"])
        out.append({"id": k["id"], "kind": "K", "t": t, "clip": k["clip"], "what": k["what"],
                    "t0": max(0.0, t - d["pre_k"]), "t1": min(end, t + d["post_k"] + float(k.get("hold") or 0.0))})
    pic = resolved["picture"]
    for a, b in zip(pic, pic[1:]):
        t = float(b["t0"])
        out.append({"id": f"T-{a['id']}-{b['id']}", "kind": "T", "t": t, "clip": b["id"],
                    "what": f"{a['id']} -> {b['id']} ({b['transition']['kind']})",
                    "t0": max(0.0, t - d["pre_t"]), "t1": min(end, t + d["post_t"])})
    return sorted(out, key=lambda w: (w["t"], w["id"]))


def stage_page(page: Path) -> Path:
    """Copy the page folder to a sibling so relative asset paths still resolve; filmkit allows one output per folder."""
    src = page.parent
    stage = src.parent / f".review_stage_{src.name}"
    if stage.exists():
        shutil.rmtree(stage)
    shutil.copytree(src, stage, ignore=lambda d, names: [n for n in names if n in STAGE_SKIP or n.endswith(".mp4")])
    return stage


def render_span(stage: Path, page_name: str, t0: float, dur: float, size: str, fps: int) -> tuple[Path, list[Path]]:
    for n in ("window.mp4", "render.json", "check.json", "check.md", "sheet_1fps.png"):
        (stage / n).unlink(missing_ok=True)
    shutil.rmtree(stage / ".filmkit", ignore_errors=True)
    frames = max(1, round(dur * fps))
    cmd = [sys.executable, "-X", "utf8", str(RENDER), str(stage / page_name), "-o", str(stage / "window.mp4"),
           "--size", size, "--fps", str(fps), "--duration", repr(frames / fps), "--start", repr(t0), "--keep-frames"]
    # full float precision: filmkit refuses a duration off a whole frame by more than 1e-6 (1/30 at 6 places is)
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    frames_ = sorted((stage / ".filmkit" / "frames").glob("*.png"))
    # 0 ok, 2 blocking rows, 3 check incomplete (a short window's sheet): the frames are what review reads;
    # 1 = nothing published
    if p.returncode not in (0, 2, 3) or not frames_:
        first = (p.stdout.splitlines() or [p.stderr.strip()[-200:]])[0]
        raise Refused(f"render failed at {t0:.3f} s: {first}")
    return stage / "window.mp4", frames_


def make_strip(frames: list[Path], fps: int, t0: float, mark: float | None, out: Path) -> None:
    from PIL import Image, ImageDraw
    step = max(1, round(fps / STRIP_FPS))
    pick = list(range(0, len(frames), step)) or [0]
    ims = [Image.open(frames[i]).convert("RGB") for i in pick]
    w, h = ims[0].size
    th = round(THUMB_W * h / w)
    rows = (len(ims) + STRIP_COLS - 1) // STRIP_COLS
    sheet = Image.new("RGB", (STRIP_COLS * THUMB_W, rows * (th + 18)), "white")
    dr = ImageDraw.Draw(sheet)
    for n, (i, im) in enumerate(zip(pick, ims)):
        x, y = (n % STRIP_COLS) * THUMB_W, (n // STRIP_COLS) * (th + 18)
        sheet.paste(im.resize((THUMB_W, th)), (x, y))
        t = t0 + i / fps
        hit = mark is not None and abs(t - mark) < step / fps / 2
        dr.text((x + 4, y + th + 3), f"{t:.2f} s" + ("  <- K/T" if hit else ""), fill="red" if hit else "black")
        if hit:
            dr.rectangle([x, y, x + THUMB_W - 1, y + th - 1], outline="red", width=3)
    sheet.save(out)


def plan_relations(film: Path, end: float) -> list[dict]:
    """R windows from review/relations.json: {"relations": [{id, a, b, kind, source, what}]}. The file is the
    maker's declared intent (G0) or detector candidates; this tool only renders and checks it, never finds them."""
    p = film / "review" / "relations.json"
    if not p.is_file():
        return []
    doc = load_json(p)
    rels = doc.get("relations")
    if not isinstance(rels, list):
        raise Refused("review/relations.json: 'relations' must be a list")
    if not rels and not str(doc.get("none_reason") or "").strip():
        raise Refused("review/relations.json: an empty relations list needs none_reason (why no shot answers another)")
    out, ids, errs = [], set(), []
    for r in rels:
        rid = r.get("id")
        w = f"relations.json {rid}"
        if not isinstance(rid, str) or not rid.strip() or rid in ids:
            errs.append(f"{w}: id missing or repeated")
        ids.add(rid)
        try:
            ta, tb = float(r.get("a")), float(r.get("b"))
        except (TypeError, ValueError):
            errs.append(f"{w}: a and b must be seconds")
            continue
        if not (0.0 <= ta < tb <= end):
            errs.append(f"{w}: needs 0 <= a < b <= film end ({end} s)")
        if r.get("kind") not in REL_KINDS:
            errs.append(f"{w}: kind must be one of {', '.join(REL_KINDS)}")
        if r.get("source") not in REL_SOURCES:
            errs.append(f"{w}: source must be declared or detector")
        if not str(r.get("what") or "").strip():
            errs.append(f"{w}: what is empty (what in A does B answer)")
        out.append({"id": f"R-{rid}", "kind": "R", "t": tb, "a": ta, "b": tb, "relation": r.get("kind"),
                    "source": r.get("source"), "what": r.get("what"), "clip": None})
    if errs:
        raise Refused("; ".join(errs))
    return out


def make_pair_sheet(rows: list[list[Path]], w: dict, out: Path) -> None:
    """A row = frames around a, B row = frames around b (REL_OFFSETS); header names the relation."""
    from PIL import Image, ImageDraw
    ims = [[Image.open(f).convert("RGB") for f in r] for r in rows]
    fh = round(PAIR_W * ims[0][0].height / ims[0][0].width)
    n = len(REL_OFFSETS)
    sheet = Image.new("RGB", (n * PAIR_W + (n + 1) * PAIR_PAD, PAIR_HEAD + 2 * (PAIR_LABEL + fh + PAIR_PAD)),
                      (24, 24, 24))
    d = ImageDraw.Draw(sheet)
    d.text((PAIR_PAD, 8), f"{w['id']}  {w['relation']} ({w['source']}): {w['what']}", fill=(255, 230, 120))
    y = PAIR_HEAD
    for name, t, row in (("A", w["a"], ims[0]), ("B", w["b"], ims[1])):
        d.text((PAIR_PAD, y + 4), f"{name}  {t:.2f} s  (" + " / ".join(f"{o:+.1f}" for o in REL_OFFSETS) + " s)",
               fill=(220, 220, 220))
        y += PAIR_LABEL
        for k, im in enumerate(row):
            sheet.paste(im.resize((PAIR_W, fh)), (PAIR_PAD + k * (PAIR_W + PAIR_PAD), y))
        y += fh + PAIR_PAD
    sheet.save(out)


def render_pair(stage: Path, page_name: str, w: dict, end: float, size: str, fps: int) -> list[list[Path]]:
    rows = []
    keep = stage.parent / f".review_pair_{stage.name}"
    shutil.rmtree(keep, ignore_errors=True)
    keep.mkdir()
    for side, t in (("a", w["a"]), ("b", w["b"])):
        row = []
        for k, o in enumerate(REL_OFFSETS):
            ts = min(max(0.0, t + o), max(0.0, end - 1 / fps))
            _, frames = render_span(stage, page_name, ts, 1 / fps, size, fps)
            dst = keep / f"{side}{k}.png"
            shutil.copyfile(frames[0], dst)
            row.append(dst)
        rows.append(row)
    return rows


def cmd_windows(film: Path, a) -> int:
    resolved = load_json(film / "build" / "timeline.resolved.json")
    d = {k: getattr(a, k) for k in DEFAULTS}
    end = float(resolved["film_end_s"])
    wins = plan_windows(resolved, d) + plan_relations(film, end)
    if a.only:
        want = set(a.only.split(","))
        wins = [w for w in wins if w["id"] in want]
    if not wins:
        raise Refused("no windows: the resolved timeline has no key frames and no boundaries (or --only matched none)")
    page = Path(a.page) if a.page else film / "build" / "index.html"
    if not page.is_file():
        raise Refused(f"page not found: {page.as_posix()}")
    size, fps = resolved["format"]["size"], int(resolved["format"]["fps"])
    stage = stage_page(page)
    out_dir = film / "review" / "windows"
    out_dir.mkdir(parents=True, exist_ok=True)
    index = load_json(out_dir / "index.json") if (out_dir / "index.json").is_file() else {"windows": {}}
    try:
        for w in wins:
            dst = out_dir / w["id"]
            dst.mkdir(exist_ok=True)
            if w["kind"] == "R":
                tmp = dst / "pair.tmp.png"
                make_pair_sheet(render_pair(stage, page.name, w, end, size, fps), w, tmp)
                h = sha256(tmp)
                strip = dst / f"pair-{h[:8]}.png"        # immutable, named by content (P-4)
                tmp.replace(strip)
                index["windows"][w["id"]] = dict(w, strip=rel(film, strip), mp4=None, strip_sha256=h)
                print(f"window {w['id']}: {w['a']:.2f} s <-> {w['b']:.2f} s -> {rel(film, strip)}")
                continue
            mp4, frames = render_span(stage, page.name, w["t0"], w["t1"] - w["t0"], size, fps)
            (dst / "window.mp4").unlink(missing_ok=True)
            shutil.move(str(mp4), dst / "window.mp4")
            tmp = dst / "strip.tmp.png"
            make_strip(frames, fps, w["t0"], w["t"], tmp)
            # strips are immutable and named by content, so a round keeps the exact picture it judged (P-4)
            h = sha256(tmp)
            strip = dst / f"strip-{h[:8]}.png"
            tmp.replace(strip)
            index["windows"][w["id"]] = dict(w, strip=rel(film, strip), mp4=rel(film, dst / "window.mp4"), strip_sha256=h)
            print(f"window {w['id']}: {w['t0']:.2f}-{w['t1']:.2f} s -> {rel(film, strip)}")
    finally:
        shutil.rmtree(stage, ignore_errors=True)
        shutil.rmtree(stage.parent / f".review_pair_{stage.name}", ignore_errors=True)
    index["defaults"] = d
    write_json(out_dir / "index.json", index)
    return 0


def cmd_stills(film: Path, a) -> int:
    resolved = load_json(film / "build" / "timeline.resolved.json")
    keys = [k for k in resolved.get("keys", []) if k["role"] == "key"]
    if a.only:
        keys = [k for k in keys if k["id"] in set(a.only.split(","))]
    if not keys:
        raise Refused("no key frames in the resolved timeline (add keys[] to clips, then tl.py resolve)")
    page = Path(a.page) if a.page else film / "build" / "index.html"
    if not page.is_file():
        raise Refused(f"page not found: {page.as_posix()}")
    size, fps = resolved["format"]["size"], int(resolved["format"]["fps"])
    stage = stage_page(page)
    out_dir = film / "review" / "stills"
    out_dir.mkdir(parents=True, exist_ok=True)
    index = load_json(out_dir / "index.json") if (out_dir / "index.json").is_file() else {"stills": {}}
    try:
        for k in keys:
            _, frames = render_span(stage, page.name, float(k["t"]), 1 / fps, size, fps)
            h = sha256(frames[0])
            dst = out_dir / f"{k['id']}-{h[:8]}.png"        # immutable, named by content (P-4)
            shutil.copyfile(frames[0], dst)
            index["stills"][k["id"]] = {"t": k["t"], "clip": k["clip"], "what": k["what"], "png": rel(film, dst),
                                        "sha256": sha256(dst)}
            print(f"still {k['id']}: {float(k['t']):.2f} s -> {rel(film, dst)}")
    finally:
        shutil.rmtree(stage, ignore_errors=True)
    write_json(out_dir / "index.json", index)
    return 0


# ---------------------------------------------------------------- findings files

def rounds(film: Path) -> dict[str, list[int]]:
    out = {g: [] for g in GATES}
    for p in (film / "review").glob("G*-*.findings.json"):
        m = FINDINGS_RE.match(p.name)
        if m:
            out[m.group(1)].append(int(m.group(2)))
    return {g: sorted(v) for g, v in out.items()}


def snapshot(film: Path, src: Path, folder: str) -> dict:
    """An immutable copy of a live file named by its content, as strips are (P-4): the live file is
    rewritten in answer to findings (storyboard edits, re-renders), so it is never an artefact itself."""
    h = sha256(src)
    snap = film / "review" / folder / f"{src.stem}-{h[:8]}{src.suffix}"
    if not snap.is_file():
        snap.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, snap)
    return {"window": None, "path": rel(film, snap), "sha256": h}


def current_artefacts(film: Path, gate: str) -> list[dict]:
    if gate == "G0":
        return [snapshot(film, film / "film.timeline.json", "storyboard")]
    if gate == "G1":
        idx = film / "review" / "stills" / "index.json"
        items = load_json(idx)["stills"] if idx.is_file() else {}
        return [{"window": k, "path": v["png"], "sha256": sha256(film / v["png"])} for k, v in sorted(items.items())]
    if gate == "G2":
        idx = film / "review" / "windows" / "index.json"
        items = load_json(idx)["windows"] if idx.is_file() else {}
        return [{"window": k, "path": v["strip"], "sha256": sha256(film / v["strip"])} for k, v in sorted(items.items())]
    # G3: a re-render rewrites build/check.md and the sheet, so the round judges snapshots (P-4)
    srcs = [film / "build" / n for n in ("check.md", "sheet_1fps.png")] + [film / "deliver" / "_review" / "side-by-side.png"]
    return [snapshot(film, p, "film") for p in srcs if p.is_file()]


def cmd_new(film: Path, a) -> int:
    gate = a.gate
    if gate == "G2" and not (film / "review" / "relations.json").is_file():
        # default-on: relations are declared (or declared absent) before the window round, so R windows are
        # never an opt-in someone forgets (experiments/probe-inter-shot-relation-2026-11-03/REPORT.md)
        raise Refused("G2 needs review/relations.json: the relations the film intends (callback, bookend, replay, "
                      "motif, setup-payoff; a = earlier s, b = later s, what B answers in A), or "
                      '{"relations": [], "none_reason": "..."}; then run windows')
    plan_relations(film, float(load_json(film / "build" / "timeline.resolved.json")["film_end_s"])) if gate == "G2" else None
    n = (rounds(film)[gate] or [0])[-1] + 1
    if n > MAX_ROUNDS:
        raise Refused(f"{gate} already has {MAX_ROUNDS} rounds (INV-R6): finish with status PASSED_WITH_OPEN, "
                      f"carry open BLOCKERs to the verdict")
    arts = current_artefacts(film, gate)
    if n > 1:      # later rounds list only what changed since any earlier round of this gate (INV-R7)
        seen = {x["sha256"] for r in rounds(film)[gate]
                for x in load_json(film / "review" / f"{gate}-{r}.findings.json").get("artefacts", [])}
        arts = [x for x in arts if x["sha256"] not in seen]
    if not arts:
        raise Refused(f"nothing new to review for {gate}: render first (windows / stills / film)")
    author = a.author or ("maker" if gate == "G0" else "director")
    doc = {"schema_version": 1, "gate": gate, "round": n, "author": author, "artefacts": arts,
           "findings": [], "none": []}
    p = film / "review" / f"{gate}-{n}.findings.json"
    write_json(p, doc)
    print(f"wrote {rel(film, p)}: {len(arts)} artefact(s); add findings, or a none entry per window")
    return 0


def check_findings(film: Path, p: Path) -> list[str]:
    errs = []
    doc = load_json(p)
    m = FINDINGS_RE.match(p.name)
    where = p.name
    if doc.get("gate") != m.group(1) or doc.get("round") != int(m.group(2)):
        errs.append(f"{where}: gate/round fields differ from the file name")
    if int(m.group(2)) > MAX_ROUNDS:
        errs.append(f"{where}: round {m.group(2)} > {MAX_ROUNDS} (INV-R6)")
    if doc.get("author") not in ("director", "maker"):
        errs.append(f"{where}: author must be director or maker")
    arts = doc.get("artefacts") or []
    for x in arts:
        f = film / x.get("path", "")
        if not f.is_file():
            errs.append(f"{where}: artefact missing {x.get('path')}")
        elif sha256(f) != x.get("sha256"):
            errs.append(f"{where}: artefact {x.get('path')} changed since the findings were written (P-4)")
    ids = set()
    for fd in doc.get("findings") or []:
        fid = fd.get("id")
        w = f"{where} {fid}"
        if not isinstance(fid, str) or fid in ids:
            errs.append(f"{w}: id missing or repeated")
        ids.add(fid)
        if fd.get("severity") not in SEVERITIES:
            errs.append(f"{w}: severity must be BLOCKER or POLISH")
        basis = fd.get("basis") or {}
        if basis.get("kind") not in BASIS_KINDS:
            errs.append(f"{w}: basis.kind must be one of {', '.join(BASIS_KINDS)}")
        elif fd.get("severity") == "BLOCKER" and basis["kind"] not in BLOCKER_BASIS:
            errs.append(f"{w}: a BLOCKER rests on {basis['kind']}; only {', '.join(BLOCKER_BASIS)} may block (INV-R4)")
        if fd.get("severity") == "BLOCKER" and not str(basis.get("ref") or "").strip():
            errs.append(f"{w}: a BLOCKER names its basis.ref (fail item, FK row, claim or defect)")
        wh, ch = str(fd.get("where") or "").strip(), str(fd.get("change") or "").strip()
        if not wh or WHOLE_FILM.search(wh):
            errs.append(f"{w}: where names one element, never the whole film (INV-R10)")
        if not ch:
            errs.append(f"{w}: change is empty (second / where / change)")
    windows = {x["window"] for x in arts if x.get("window")}
    covered = {fd.get("window") for fd in doc.get("findings") or []}
    for nn in doc.get("none") or []:
        if str(nn.get("looked_at") or "").strip():
            covered.add(nn.get("window"))
    missing = sorted(windows - covered)
    if missing:
        errs.append(f"{where}: no line for window(s) {', '.join(missing)} — a finding or a none entry with looked_at (INV-R9)")
    return errs


def check_response(film: Path, p: Path) -> list[str]:
    errs = []
    fp = p.with_name(p.name.replace(".response.json", ".findings.json"))
    if not fp.is_file():
        return [f"{p.name}: no matching findings file"]
    fdoc, rdoc = load_json(fp), load_json(p)
    sev = {f["id"]: f.get("severity") for f in fdoc.get("findings") or []}
    got = {}
    for r in rdoc.get("responses") or []:
        got[r.get("id")] = r
        if r.get("id") not in sev:
            errs.append(f"{p.name}: response to unknown finding {r.get('id')}")
            continue
        if r.get("status") not in STATUSES:
            errs.append(f"{p.name} {r.get('id')}: status must be fixed, declined or rebutted")
        if r.get("status") == "declined" and sev[r["id"]] == "BLOCKER":
            errs.append(f"{p.name} {r['id']}: a BLOCKER cannot be declined; fix it or rebut its basis (INV-R5)")
        if r.get("status") in ("declined", "rebutted") and not str(r.get("note") or "").strip():
            errs.append(f"{p.name} {r['id']}: {r['status']} needs a one-line reason (INV-R5)")
    for fid in sev:
        if fid not in got:
            errs.append(f"{p.name}: no response to {fid}")
    return errs


def all_errors(film: Path) -> list[str]:
    errs = []
    rv = film / "review"
    for p in sorted(rv.glob("G*-*.findings.json")):
        errs += check_findings(film, p) if FINDINGS_RE.match(p.name) else [f"{p.name}: bad name"]
    for p in sorted(rv.glob("G*-*.response.json")):
        errs += check_response(film, p)
    return errs


def cmd_check(film: Path, a) -> int:
    errs = all_errors(film)
    for e in errs:
        print(f"refused: {e}")
    print(f"review check: {len(errs)} problem(s)")
    return 1 if errs else 0


def gate_state(film: Path, gate: str) -> tuple[str, list[dict]]:
    rs = rounds(film)[gate]
    if not rs:
        return "NOT_STARTED", []
    last = load_json(film / "review" / f"{gate}-{rs[-1]}.findings.json")
    open_b = [f for f in last.get("findings") or [] if f.get("severity") == "BLOCKER"]
    if not open_b:
        return "PASSED", []
    resp = film / "review" / f"{gate}-{rs[-1]}.response.json"
    if rs[-1] >= MAX_ROUNDS and resp.is_file():
        rmap = {r["id"]: r for r in load_json(resp).get("responses") or []}
        unresolved = [dict(f, response=rmap.get(f["id"], {}).get("status")) for f in open_b]
        return "PASSED_WITH_OPEN", unresolved
    return "OPEN", open_b


def cmd_status(film: Path, a) -> int:
    for g in GATES:
        st, items = gate_state(film, g)
        print(f"{g}: {st} (rounds {rounds(film)[g] or '-'}; open BLOCKERs {len(items)})")
    return 0


def cmd_log(film: Path, a) -> int:
    rv = film / "review"
    L = ["# 審查紀錄（GENERATED by tools/review/review.py log; never hand-edited）", ""]
    for g in GATES:
        st, items = gate_state(film, g)
        L.append(f"## {g} — {st}")
        for n in rounds(film)[g]:
            fd = load_json(rv / f"{g}-{n}.findings.json")
            rp = rv / f"{g}-{n}.response.json"
            rmap = {r["id"]: r for r in load_json(rp).get("responses") or []} if rp.is_file() else {}
            nb = sum(1 for f in fd.get("findings") or [] if f.get("severity") == "BLOCKER")
            L.append(f"- 第 {n} 輪（{fd.get('author')}）：{len(fd.get('artefacts') or [])} 件產物，"
                     f"{len(fd.get('findings') or [])} 條意見（BLOCKER {nb}），無意見 {len(fd.get('none') or [])} 窗")
            for f in fd.get("findings") or []:
                r = rmap.get(f["id"], {})
                L.append(f"  - {f['id']} {f.get('severity')} @{f.get('at_s', '-')} s {f.get('where')}：{f.get('change')}"
                         f"（依據 {f.get('basis', {}).get('kind')} {f.get('basis', {}).get('ref') or ''}）"
                         f" → {r.get('status', '未回覆')}{('：' + r['note']) if r.get('note') else ''}")
        L.append("")
    (rv / "LOG.md").write_text("\n".join(L) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {rel(film, rv / 'LOG.md')}")
    return 0


def cmd_verdict(film: Path, a) -> int:
    note = Path(a.note).read_text(encoding="utf-8").strip() if a.note else ""
    if not note:
        raise Refused("--note <file> with the director's words (what was compared, seen, decided) is required")
    errs = all_errors(film)
    if errs:
        raise Refused(f"review check has {len(errs)} problem(s); run check and fix them first")
    states, unresolved = {}, []
    for g in GATES:
        st, items = gate_state(film, g)
        states[g] = st
        if st == "OPEN":
            raise Refused(f"{g} is OPEN: answer its round or run the next one before the verdict")
        unresolved += [f"{g} {f['id']} @{f.get('at_s', '-')} s {f.get('where')}: {f.get('change')} "
                       f"(basis {f['basis']['kind']} {f['basis'].get('ref', '')}; maker {f.get('response') or 'no response'})"
                       for f in items]
    L = ["reviewer: dispatcher-main-loop", "user_watched: no",
         "gates: " + ", ".join(f"{g} {s}" for g, s in states.items()),
         "unresolved:" + ("" if unresolved else " none")]
    L += [f"  - {u}" for u in unresolved]
    L += ["", note, ""]
    out = film / "deliver" / "_review" / "verdict.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(L) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {rel(film, out)} ({len(unresolved)} unresolved)")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="agent review loop (docs/agent-review-kbt-design.md)")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("windows", "stills"):
        s = sub.add_parser(name)
        s.add_argument("film")
        s.add_argument("--only")
        s.add_argument("--page")
        if name == "windows":
            for k, v in DEFAULTS.items():
                s.add_argument(f"--{k.replace('_', '-')}", dest=k, type=float, default=v)
    s = sub.add_parser("new")
    s.add_argument("film")
    s.add_argument("gate", choices=GATES)
    s.add_argument("--author", choices=("director", "maker"))
    for name in ("check", "status", "log"):
        sub.add_parser(name).add_argument("film")
    s = sub.add_parser("verdict")
    s.add_argument("film")
    s.add_argument("--note")
    a = p.parse_args(argv)
    film = Path(a.film)
    if not film.is_dir():
        print(f"refused: film folder not found: {film.as_posix()}")
        return 1
    try:
        return {"windows": cmd_windows, "stills": cmd_stills, "new": cmd_new, "check": cmd_check,
                "status": cmd_status, "log": cmd_log, "verdict": cmd_verdict}[a.cmd](film, a)
    except Refused as e:
        print(f"refused: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())

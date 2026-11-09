"""validate --static (PSM 6.6, 7): TV-1, assets, uses, TV-3, TV-4a, TV-5, TV-8, TV-9a, TV-15, TV-17, candidates."""
from __future__ import annotations

import json
import platform
import re
import shutil
import subprocess
from pathlib import Path

from . import model as M
from . import uses as U
from .common import dumps, film_write, last_line, row, summarize
from .components import Index
from .messages_zh import zh
from .nhash import file_nsha, folder_nsha, lines_nsha, runtime_hash
from .rules import Rules
from .select import table_a, table_b, transition_table_a

PRODUCT_FILM_TYPES = ("intro-ad", "hype-ad", "product-tour", "data-showreel")  # PSM 4.3 (user ruling 2026-10-11)
DIGIT_RE = re.compile(r"[0-9０-９]")
HAN_NUM = "零一二兩三四五六七八九十百千萬億"
UNITS = "%％倍秒分鐘次年月日天人項步種個件張頁行字元格幀"
HAN_NUM_RE = re.compile(rf"([{HAN_NUM}]{{2,}}[{UNITS}])|([{UNITS}][{HAN_NUM}]{{2,}})")


def has_number(text: str) -> bool:
    """The determinable part of "數字" (PSM 7 TV-9a): an Arabic/full-width digit, or a Han numeral run of
    length >= 2 adjacent to a unit or percent sign."""
    return bool(text) and bool(DIGIT_RE.search(text) or HAN_NUM_RE.search(text))


def is_product_film(obj: dict) -> bool:
    return M.decision(obj, "film_type") in PRODUCT_FILM_TYPES or any(
        isinstance(a, dict) and "claims_ref" in a for a in obj.get("assets") or [])


# ---------------------------------------------------------------- environment probes
def ffprobe_path():
    return shutil.which("ffprobe")


def ffprobe_version() -> str | None:
    exe = ffprobe_path()
    if not exe:
        return None
    try:
        out = subprocess.run([exe, "-version"], capture_output=True, text=True, timeout=20).stdout
        m = re.search(r"ffprobe version (\d+(?:\.\d+)*)", out)
        return m.group(1) if m else "unknown"
    except (OSError, subprocess.SubprocessError):
        return None


def ffprobe_info(path: Path) -> dict | None:
    """{duration_s, has_video} or None when ffprobe is absent; raises nothing."""
    exe = ffprobe_path()
    if not exe:
        return None
    try:
        p = subprocess.run([exe, "-v", "error", "-show_entries", "format=duration:stream=codec_type", "-of", "json",
                            str(path)], capture_output=True, text=True, timeout=60)
        obj = json.loads(p.stdout or "{}")
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        return {"duration_s": None, "has_video": False}
    dur = (obj.get("format") or {}).get("duration")
    vids = [s for s in obj.get("streams") or [] if s.get("codec_type") == "video"]
    try:
        dur = round(float(dur), 6) if dur is not None else None
    except ValueError:
        dur = None
    return {"duration_s": dur, "has_video": bool(vids)}


def env_versions() -> dict:
    return {"python": platform.python_version(), "ffprobe": ffprobe_version()}


# ---------------------------------------------------------------- inputs
def clips_nsha(film: Path) -> str:
    d = Path(film) / "clips"
    if not d.is_dir():
        return lines_nsha([], "clips")
    return folder_nsha(d, "*.js")


def lines_file_nsha(film: Path):
    p = Path(film) / "voice" / "lines.json"
    return file_nsha(p) if p.is_file() else None


def current_inputs(film: Path, rules: Rules, index: Index) -> dict:
    film = Path(film)
    return {"timeline_nsha": file_nsha(film / "film.timeline.json"), "clips_nsha": clips_nsha(film),
            "lines_nsha": lines_file_nsha(film), "components_nsha": index.nsha, "rules_sha": rules.sha,
            "runtime_hash": runtime_hash()}


# ---------------------------------------------------------------- the run
def run_static(film: Path, rules: Rules, index: Index) -> dict:
    film = Path(film)
    info: dict = {}
    obj, rows = M.load_timeline(film, rules=rules, info=info)
    t = M.tracks(obj) if isinstance(obj, dict) else {"picture": [], "overlay": [], "narration": [], "sfx": []}
    line_ids = [ln.get("id") for ln in t["narration"] if isinstance(ln, dict)]
    lj = M.lines_json_obj(film)
    if lj is not None:
        rows += M.validate_lines_json(lj, line_ids)
    result = {"schema_version": 1, "generator": "tl", "film_id": film.name, "stage": "static",
              "inputs": current_inputs(film, rules, index) | {"resolved_nsha": None},
              "env": env_versions(),
              "static": {"rows": [], "summary": {}}, "timed": {"rows": [], "summary": {}},
              "assets": [], "uses": {}, "defaults_applied": sorted(info.get("defaults_applied", [])),
              "decisions_unset": info.get("decisions_unset", []), "pending_confirmation": [],
              "freedom_share": {"locked_s": 0.0, "guided_s": 0.0, "free_s": 0.0},
              "notes": list(dict.fromkeys(info.get("notes", [])))}
    candidates: dict = {}
    if any(r["bucket"] == "blocking" for r in rows):
        result["notes"].append("schema has blocking rows; later checks not run (they would misread the file)")
        _finish(result, rows)
        return {"result": result, "candidates": candidates}

    rows += _assets(film, obj, result)
    if any(r["bucket"] == "blocking" for r in rows):
        result["notes"].append("asset rows are blocking; later checks not run")
        _finish(result, rows)
        return {"result": result, "candidates": candidates}

    dec = {k: M.decision(obj, k) for k in ("energy", "film_type", "rhythm_source")}
    clips = [c for c in t["picture"]] + [c for c in t["overlay"]]
    # uses
    uses: dict[str, list[str]] = {}
    for c in clips:
        fr = M.freedom(c)
        if fr == "locked":
            continue
        prog = film / "clips" / f"{c['id']}.js"
        if not prog.is_file():
            continue
        src = prog.read_bytes().decode("utf-8", errors="replace")
        refs, problems = U.extract(src)
        uses[c["id"]] = refs
        for k, pr in enumerate(problems):
            rows.append(row("TV-15", c["id"], "blocking", stage="static", measured=pr,
                            expected="TL.component(\"<ref>\") with one string literal", basis="SEM-6 / PSM 6.5",
                            message_key="tv15.literal", message=zh("tv15.literal", clip=c["id"], detail=pr),
                            rid=f"TV-15#{c['id']}:literal{k + 1}"))
    result["uses"] = {k: uses[k] for k in sorted(uses)}

    locked_components = {(c.get("device") or {}).get("component") for c in clips if M.freedom(c) == "locked"}
    locked_components.discard(None)
    pending = []
    for c in clips:
        fr = M.freedom(c)
        a = _safe(rows, "TV-3", c["id"], lambda: table_a(c, dec, index, locked_components, freedom=fr,
                                                          uses=uses.get(c["id"], [])))
        if a:
            rows += a["rows"]
            pending += a["pending"]
        if c in t["picture"]:
            ta = _safe(rows, "TV-3", f"{c['id']}.transition",
                       lambda: transition_table_a(c, dec, index, locked_components, freedom=fr))
            if ta:
                rows += ta["rows"]
                pending += ta["pending"]
        else:
            ta = None
        if fr == "guided":
            candidates[c["id"]] = {"device": a, "transition": ta}
    result["pending_confirmation"] = pending

    rows += _safe_rows("TV-4a", lambda: _tv4a(obj, t, index))
    rows += _safe_rows("TV-5", lambda: _tv5(t, index, rules, uses))
    rows += _safe_rows("TV-8", lambda: _tv8(t))
    rows += _safe_rows("TV-9a", lambda: tv9a(obj, stage="static", film=film))
    rows += _safe_rows("TV-15", lambda: _tv15(t, uses, candidates, index))
    rows += _safe_rows("TV-17", lambda: _tv17(t, result["assets"], obj))
    rows += _safe_rows("TV-20", lambda: tv20(obj, stage="static"))
    rows += _safe_rows("TV-21", lambda: tv21(obj))
    rows += _safe_rows("TV-22", lambda: tv22(obj))

    counts = {}
    for cid, cd in candidates.items():
        c = next(x for x in clips if x["id"] == cid)
        cd["files"] = _candidate_files(c, cd, dec, result["decisions_unset"])
        counts[cid] = len(((cd.get("device") or {}).get("candidates")) or [])
    result["candidate_counts"] = counts
    _finish(result, rows)
    return {"result": result, "candidates": candidates}


def _finish(result: dict, rows: list[dict]) -> None:
    result["static"]["rows"] = rows
    result["static"]["summary"] = summarize(rows)


def _safe(rows: list, check: str, where: str, fn):
    try:
        return fn()
    except Exception as e:  # an exception inside one evaluator -> undetermined row, others still run (PSM 11)
        rows.append(row(check, where, "undetermined", stage="static", reason=f"evaluator error: {last_line(e)}",
                        message_key="undetermined.evaluator", message=zh("undetermined.evaluator", detail=last_line(e))))
        return None


def _safe_rows(check: str, fn) -> list[dict]:
    try:
        return fn()
    except Exception as e:
        return [row(check, "film", "undetermined", stage="static", reason=f"evaluator error: {last_line(e)}",
                    message_key="undetermined.evaluator", message=zh("undetermined.evaluator", detail=last_line(e)))]


def _assets(film: Path, obj: dict, result: dict) -> list[dict]:
    rows = []
    for a in obj.get("assets") or []:
        p = film / a["path"]
        entry = {"id": a["id"], "nsha": None, "duration_s": None}
        if not p.is_file():
            rows.append(row("TV-1", f"asset:{a['id']}", "blocking", stage="static", measured=f"{a['path']} missing",
                            expected="the file exists", basis="PSM 4.1 / TV-1", message_key="tv1.asset",
                            message=zh("tv1.asset", detail=f"{a['id']}：找不到 {a['path']}")))
            result["assets"].append(entry)
            continue
        entry["nsha"] = file_nsha(p)
        if "sha256" in a and a["sha256"] != entry["nsha"]:
            rows.append(row("TV-1", f"asset:{a['id']}", "blocking", stage="static", measured=f"nsha {entry['nsha'][:12]}…",
                            expected=f"sha256 {a['sha256'][:12]}… as written", basis="PSM 4.1 / TV-1",
                            message_key="tv1.asset", message=zh("tv1.asset", detail=f"{a['id']}：檔案內容與 sha256 不符")))
        if M.is_video_path(a["path"]):
            inf = ffprobe_info(p)
            if inf is None:
                result["notes"].append(f"ffprobe not found: {a['id']} duration unknown")
            else:
                entry["duration_s"] = inf["duration_s"]
                entry["has_video"] = inf["has_video"]
        if "claims_ref" in a and not (film / a["claims_ref"]).is_file():
            rows.append(row("TV-1", f"asset:{a['id']}", "blocking", stage="static",
                            measured=f"claims_ref {a['claims_ref']} missing", expected="the file exists",
                            basis="PSM 4.1 / TV-1", message_key="tv1.asset",
                            message=zh("tv1.asset", detail=f"{a['id']}：宣稱來源 {a['claims_ref']} 不存在"),
                            rid=f"TV-1#asset:{a['id']}.claims_ref"))
        result["assets"].append(entry)
    return rows


def _type_ok(spec: dict, val, asset_ids: set, line_ids: set) -> str | None:
    ty = spec.get("type")
    if ty == "number" and not M.is_num(val):
        return "not a number"
    if ty == "integer" and not M.is_int(val):
        return "not an integer"
    if ty == "string" and not isinstance(val, str):
        return "not a string"
    if ty == "boolean" and not isinstance(val, bool):
        return "not a boolean"
    if ty == "asset" and val not in asset_ids:
        return f"asset {val!r} not in assets[]"
    if ty == "line" and val not in line_ids:
        return f"line {val!r} not in narration"
    if ty == "color" and not (isinstance(val, str) and M.HEX_RE.match(val)):
        return "not #RRGGBB"
    if "enum" in spec and val not in spec["enum"]:
        return f"{val!r} not in {spec['enum']}"
    if M.is_num(val) and "min" in spec and val < spec["min"]:
        return f"{val} < min {spec['min']}"
    if M.is_num(val) and "max" in spec and val > spec["max"]:
        return f"{val} > max {spec['max']}"
    return None


def _tv4a(obj: dict, t: dict, index: Index) -> list[dict]:
    rows = []
    asset_ids = {a["id"] for a in obj.get("assets") or []}
    line_ids = {ln["id"] for ln in t["narration"]}
    for c in t["picture"] + t["overlay"]:
        if M.freedom(c) != "locked":
            continue
        dev = c.get("device") or {}
        comp = index.get(dev.get("component"))
        if not comp:
            continue  # TV-3 A2 already blocks
        specs = comp.get("params") or {}
        for name, val in (dev.get("params") or {}).items():
            spec = specs.get(name)
            if spec is None:
                bad = f"unknown param {name}"
            elif spec.get("source") == "clip_dur":
                bad = f"{name} is the clip's own length (source clip_dur); the author must not write it"
            else:
                bad = _type_ok(spec, val, asset_ids, line_ids)
                bad = f"{name}: {bad}" if bad else None
            if bad:
                rows.append(row("TV-4a", f"{c['id']}.{name}", "blocking", stage="static", measured=bad,
                                expected=f"params of {comp['ref']}", basis="component schema / TV-4a",
                                message_key="tv4.param", message=zh("tv4.param", clip=c["id"], detail=bad)))
        closure, missing = index.requires_closure(comp["ref"])
        for q in missing + [r for r in closure if not index.selectable(r)]:
            rows.append(row("TV-4a", f"{c['id']}:requires:{q}", "blocking", stage="static",
                            measured=f"{comp['ref']} requires {q}: {'missing' if q in missing else 'not selectable'}",
                            expected="every component of the requires closure exists and is selectable",
                            basis="X-10 / TV-4a", message_key="tv4.requires",
                            message=zh("tv4.requires", clip=c["id"], detail=q)))
    return rows


def _tv5(t: dict, index: Index, rules: Rules, uses: dict) -> list[dict]:
    rows = []
    stock = rules.timeline.get("stock_devices")
    stock = stock if isinstance(stock, list) else None
    if stock is None:
        rows.append(row("TV-5", "stock_devices", "undetermined", stage="static",
                        reason=rules.absent_reason("params.timeline.stock_devices"),
                        message_key="tv5.undetermined", message=zh("tv5.undetermined")))
    for c in t["picture"] + t["overlay"]:
        if c.get("motion_intent") != []:
            continue
        fams, comps = [], []
        dev = c.get("device") or {}
        if dev.get("family"):
            fams.append(dev["family"])
        refs = ([dev["component"]] if dev.get("component") else []) + list(uses.get(c["id"], []))
        for ref in refs:
            e = index.get(ref)
            if e:
                comps.append(e)
                fams.append(e.get("family"))
        is_stock = any(e.get("stock") for e in comps) or bool(stock and any(f in stock for f in fams))
        if is_stock:
            rows.append(row("TV-5", c["id"], "blocking", stage="static", measured="motion_intent [] on a stock device",
                            expected="one line per moving element", basis="BR-6 / table B2", message_key="tv5.stock",
                            message=zh("tv5.stock", clip=c["id"])))
        else:
            rows.append(row("TV-5", c["id"], "look", stage="static", measured="motion_intent []",
                            expected="one line per moving element", basis="BR-6", provisional=True,
                            message_key="tv5.empty", message=zh("tv5.empty", clip=c["id"])))
    return rows


def _tv8(t: dict) -> list[dict]:
    rows = []
    for c in t["picture"] + t["overlay"]:
        g = c.get("ground_exception")
        if g is None:
            continue
        why = (g.get("why") or "").strip()
        if why:
            rows.append(row("TV-8", c["id"], "info", stage="static", measured=f"ground exception {g.get('color') or ''}",
                            expected="listed", basis="BR-14 / X-9a", message_key="tv8.listed",
                            message=zh("tv8.listed", clip=c["id"], detail=f"{g.get('color') or ''} {why}".strip())))
        else:
            rows.append(row("TV-8", c["id"], "look", stage="static", measured="ground_exception without why",
                            expected="a why", basis="BR-14 / X-9a", provisional=True, message_key="tv8.no_why",
                            message=zh("tv8.no_why", clip=c["id"])))
    return rows


def claim_norm(s: str) -> str:
    """Claim text vs source line: drop Markdown bold markers, collapse whitespace; nothing else."""
    return re.sub(r"\s+", " ", s.replace("**", "")).strip()


def tv9a(obj: dict, *, stage: str, film: Path | None = None) -> list[dict]:
    """Product films only. look at validate, blocking at approve (X-9).
    With `film`, a well-formed Claim's text must also appear verbatim (claim_norm) on one line of its
    claims_ref file; an unreadable source is undetermined, never a pass."""
    if not is_product_film(obj):
        return []
    bucket = "blocking" if stage == "approve" else "look"
    t = M.tracks(obj)
    assets = {a["id"]: a for a in obj.get("assets") or []}
    rows = []
    sources: dict[str, list[str] | None] = {}

    def claim_ok(c):
        m = M.CLAIM_RE.match(c or "")
        return m and "claims_ref" in assets.get(m.group(1), {})

    def add(where, key, measured, detail):
        rows.append(row("TV-9a", where, bucket, stage=stage, measured=measured,
                        expected="a Claim to an asset with claims_ref", basis="BR-12 / T05", provisional=False,
                        message_key=key, message=zh(key, clip=where, detail=detail)))

    def source_lines(aid):
        if aid not in sources:
            try:
                txt = (film / assets[aid]["claims_ref"]).read_text(encoding="utf-8")
                sources[aid] = [claim_norm(x) for x in txt.splitlines()]
            except (OSError, UnicodeDecodeError):
                sources[aid] = None
        return sources[aid]

    def check_source(where, cl):
        if film is None or not claim_ok(cl):
            return
        aid, text = M.CLAIM_RE.match(cl).groups()
        lines = source_lines(aid)
        rid = f"TV-9a#{where}.source"
        if lines is None:
            rows.append(row("TV-9a", where, "undetermined", stage=stage, reason=f"claims_ref {assets[aid]['claims_ref']} unreadable",
                            basis="BR-12 / T05", message_key="tv9a.source_unreadable",
                            message=zh("tv9a.source_unreadable", clip=where, detail=assets[aid]["claims_ref"]), rid=rid))
            return
        needle = claim_norm(text)
        if not any(needle and needle in x for x in lines):
            rows.append(row("TV-9a", where, bucket, stage=stage, measured=f"claim text {text!r} not found",
                            expected=f"verbatim on one line of {assets[aid]['claims_ref']}", basis="BR-12 / T05",
                            message_key="tv9a.not_in_source", message=zh("tv9a.not_in_source", clip=where, detail=cl),
                            rid=rid))

    for c in t["picture"] + t["overlay"]:
        claims = c.get("claims") or {}
        for f in ("headline", "data"):
            text = c.get(f)
            if isinstance(text, str) and has_number(text) and f not in claims:
                add(f"{c['id']}.{f}", "tv9a.no_claim", f"{f} {text!r} has a number, no claim", text)
        for f, cl in claims.items():
            if not claim_ok(cl):
                add(f"{c['id']}.{f}", "tv9a.bad_claim", f"claim {cl} names an asset without claims_ref", cl)
            check_source(f"{c['id']}.{f}", cl)
    for ln in t["narration"]:
        if has_number(ln.get("text", "")) and "claim" not in ln:
            add(ln["id"], "tv9a.no_claim", f"text {ln['text']!r} has a number, no claim", ln["text"])
        if "claim" in ln and not claim_ok(ln["claim"]):
            add(ln["id"], "tv9a.bad_claim", f"claim {ln['claim']} names an asset without claims_ref", ln["claim"])
        if "claim" in ln:
            check_source(ln["id"], ln["claim"])
    if not any("portrays" in a for a in assets.values()):
        rows.append(row("TV-9a", "film", bucket, stage=stage, measured="no asset declares portrays",
                        expected="identity strings from an asset's portrays", basis="BR-12",
                        message_key="tv9a.no_portrays", message=zh("tv9a.no_portrays")))
    return rows


STATE_BASIS = "convergence-build-design §3"


def _states(obj: dict) -> list[dict]:
    ps = obj.get("product_state")
    return [s for s in ps if isinstance(s, dict)] if isinstance(ps, list) else []


def tv20(obj: dict, *, stage: str) -> list[dict]:
    """Product films only. Opt-in: without product_state one info row; with it, every picture clip of role
    feature names shows_state and every state has source and non-empty facts. look at validate, blocking at
    approve (as TV-9a). DIT-era films without the table keep today's behaviour."""
    if not is_product_film(obj):
        return []
    if "product_state" not in obj:
        return [row("TV-20", "film", "info", stage=stage, measured="no product_state",
                    expected="product_state[] naming what each feature shot shows", basis=STATE_BASIS,
                    message_key="tv20.no_table", message=zh("tv20.no_table"))]
    bucket = "blocking" if stage == "approve" else "look"
    rows = []
    for c in M.tracks(obj)["picture"]:
        if c.get("role") == "feature" and not c.get("shows_state"):
            rows.append(row("TV-20", c["id"], bucket, stage=stage, measured="feature clip without shows_state",
                            expected="shows_state: [state ids]", basis=STATE_BASIS,
                            message_key="tv20.no_shows_state", message=zh("tv20.no_shows_state", clip=c["id"])))
    for s in _states(obj):
        sid = s.get("id")
        if not (isinstance(s.get("facts"), dict) and s["facts"]):
            rows.append(row("TV-20", f"state:{sid}", bucket, stage=stage, measured="facts empty or missing",
                            expected="non-empty facts", basis=STATE_BASIS, message_key="tv20.no_facts",
                            message=zh("tv20.no_facts", clip=sid)))
        if not M.nonempty_str(s.get("source")):
            rows.append(row("TV-20", f"state:{sid}", bucket, stage=stage, measured="source empty or missing",
                            expected="a source (claim ref)", basis=STATE_BASIS, message_key="tv20.no_source",
                            message=zh("tv20.no_source", clip=sid)))
    return rows


def tv21(obj: dict) -> list[dict]:
    """shows_state ids exist; fact values are scalars (str, number, bool). Blocking."""
    states = {s.get("id"): s for s in _states(obj)}
    rows = []
    t = M.tracks(obj)
    for c in t["picture"] + t["overlay"]:
        ss = c.get("shows_state")
        for sid in ss if isinstance(ss, list) else []:
            if sid not in states:
                rows.append(row("TV-21", f"{c['id']}.shows_state", "blocking", stage="static",
                                measured=f"state {sid!r} not in product_state", expected="a declared state id",
                                basis=STATE_BASIS, message_key="tv21.unknown_state",
                                message=zh("tv21.unknown_state", clip=c["id"], detail=sid)))
    for sid, s in states.items():
        facts = s.get("facts")
        for k, val in (facts.items() if isinstance(facts, dict) else []):
            if not (isinstance(val, (str, bool)) or M.is_num(val)):
                rows.append(row("TV-21", f"state:{sid}.{k}", "blocking", stage="static",
                                measured=f"fact {k} is {type(val).__name__}", expected="a string, number or bool",
                                basis=STATE_BASIS, message_key="tv21.not_scalar",
                                message=zh("tv21.not_scalar", clip=sid, detail=k)))
    return rows


def _mentions(val, aid: str) -> bool:
    if isinstance(val, str):
        return re.search(rf"(?<![A-Za-z0-9._-]){re.escape(aid)}(?![A-Za-z0-9_-])", val) is not None
    if isinstance(val, dict):
        return any(_mentions(x, aid) for x in val.values())
    if isinstance(val, list):
        return any(_mentions(x, aid) for x in val)
    return False


def tv22(obj: dict) -> list[dict]:
    """An asset with `required` is referenced by at least one clip: device.params, visual, what, speed.asset.
    Blocking: a required asset nothing places cannot be guaranteed on screen."""
    t = M.tracks(obj)
    clips = t["picture"] + t["overlay"]
    rows = []
    for a in obj.get("assets") or []:
        if not (isinstance(a, dict) and "required" in a):
            continue
        aid = a.get("id")
        hit = any(_mentions(((c.get("device") or {}).get("params") if isinstance(c.get("device"), dict) else None), aid)
                  or _mentions(c.get("visual"), aid) or _mentions(c.get("what"), aid)
                  or (isinstance(c.get("speed"), dict) and c["speed"].get("asset") == aid) for c in clips)
        if not hit:
            rows.append(row("TV-22", f"asset:{aid}", "blocking", stage="static",
                            measured="required asset referenced by no clip",
                            expected="named in a clip's device.params, visual, what or speed.asset",
                            basis=STATE_BASIS, message_key="tv22.unplaced", message=zh("tv22.unplaced", clip=aid)))
    return rows


def _tv15(t: dict, uses: dict, candidates: dict, index: Index) -> list[dict]:
    rows = []
    guided = [c for c in t["picture"] + t["overlay"] if M.freedom(c) == "guided"]
    for c in guided:
        cd = candidates.get(c["id"]) or {}
        dev = cd.get("device") or {}
        rows += table_b(c, uses.get(c["id"], []), dev.get("candidates") or [], None, freedom="guided", index=index)
        tin = c.get("transition_in")
        if isinstance(tin, dict):
            allowed = {x["ref"] for x in ((cd.get("transition") or {}).get("candidates") or [])}
            if tin["component"] not in allowed:
                rows.append(row("TV-15", f"{c['id']}.transition", "blocking", stage="static",
                                measured=f"transition_in {tin['component']}",
                                expected=f"one of {sorted(allowed) or 'no transition candidates'}",
                                basis="Z-7a / SEM-6", message_key="tv15.transition_outside",
                                message=zh("tv15.transition_outside", clip=c["id"], detail=tin["component"])))
    seen = set()
    for a in guided:
        for b in guided:
            if a["id"] >= b["id"] or (a["id"], b["id"]) in seen:
                continue
            for ra in uses.get(a["id"], []):
                for rb in uses.get(b["id"], []):
                    ea, eb = index.get(ra), index.get(rb)
                    if ea and eb and (rb.rsplit("@", 1)[0] in (ea.get("conflicts") or [])
                                      or ra.rsplit("@", 1)[0] in (eb.get("conflicts") or [])):
                        seen.add((a["id"], b["id"]))
                        rows.append(row("TV-15", f"{a['id']}~{b['id']}", "look", stage="static",
                                        measured=f"{ra} conflicts with {rb}", expected="no conflicting uses",
                                        basis="TV-15 / design 6.8", provisional=True, message_key="tv15.conflict",
                                        message=zh("tv15.conflict", clip=a["id"], detail=f"{b['id']}：{ra} × {rb}")))
    return rows


def _tv17(t: dict, assets_out: list[dict], obj: dict) -> list[dict]:
    rows = []
    by_id = {a["id"]: a for a in assets_out}
    paths = {a["id"]: a.get("path", "") for a in obj.get("assets") or []}
    for c in t["picture"]:
        s = c.get("speed")
        if not s:
            continue
        cid = c["id"]
        problems, undetermined = [], None
        a = by_id.get(s["asset"]) or {}
        tab = s["table"]
        for k, (x0, x1, sp) in enumerate(tab):
            if not x0 < x1:
                problems.append(f"row {k}: demo_start {x0} >= demo_end {x1}")
            if not sp > 0:
                problems.append(f"row {k}: speed {sp} <= 0")
        if tab and tab[0][0] != 0:
            problems.append(f"first row starts at {tab[0][0]}, not 0")
        for k in range(1, len(tab)):
            if abs(tab[k][0] - tab[k - 1][1]) > 1e-9:
                problems.append(f"hole or overlap between rows {k - 1} and {k}: {tab[k - 1][1]} -> {tab[k][0]}")
        apath = paths.get(s["asset"], "")
        if not M.is_video_path(apath):
            problems.append(f"speed.asset {s['asset']} is not a video asset ({apath})")
        elif "has_video" not in a:
            undetermined = "ffprobe not found: asset length unknown"
        elif not a.get("has_video"):
            problems.append(f"speed.asset {s['asset']} has no video stream")
        elif a.get("duration_s") is None:
            undetermined = "ffprobe gave no duration"
        elif tab and tab[-1][1] > a["duration_s"] + 1e-6:
            problems.append(f"table ends at {tab[-1][1]} s beyond the asset's {a['duration_s']} s")
        if problems:
            rows.append(row("TV-17", cid, "look", stage="static", measured="; ".join(problems),
                            expected="contiguous from 0 within the asset length, speed > 0",
                            basis="SEM-12 / BR-14 (r14, unverified)", provisional=True, message_key="tv17.table",
                            message=zh("tv17.table", clip=cid, detail="；".join(problems))))
        if undetermined:
            rows.append(row("TV-17", f"{cid}.length", "undetermined", stage="static", reason=undetermined,
                            message_key="tv17.undetermined", message=zh("tv17.undetermined", clip=cid, detail=undetermined)))
    return rows


def _candidate_files(c: dict, cd: dict, dec: dict, unset: list) -> dict:
    out = {}
    di = {"energy": dec.get("energy"), "film_type": dec.get("film_type"), "rhythm_source": dec.get("rhythm_source"),
          "role": c.get("role"), "decisions_unset": list(unset)}
    for kind, key in (("device", "candidates"), ("transition", "transition.candidates")):
        a = cd.get(kind)
        if a is None:
            continue
        out[f"build/clips/{c['id']}.{key}.json"] = {
            "schema_version": 1, "clip": c["id"], "kind": kind, "decided_by": "A7", "decision_inputs": di,
            "candidates": a.get("candidates") or [], "note": a.get("note")}
    return out


def write_outputs(film: Path, res: dict) -> list[str]:
    """validate.json + candidate files; returns written paths (relative)."""
    film = Path(film)
    written = []
    for cd in res["candidates"].values():
        for rel, obj in (cd.get("files") or {}).items():
            film_write(film, film / rel, dumps(obj))
            written.append(rel)
    film_write(film, film / "build" / "validate.json", dumps(res["result"]))
    written.append("build/validate.json")
    return written

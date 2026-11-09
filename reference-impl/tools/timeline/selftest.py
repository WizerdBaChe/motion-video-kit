"""Timeline layer selftest (PSM 10.1 TL-0 rows + 10.2 control table).

Every control has a positive arm (must fire) and a negative arm (must not fire); a positive arm that does
not fire fails the run. Fixtures live in a temp folder; nothing in the lab is written except __pycache__.

python -X utf8 tools/timeline/selftest.py [--only NAME,..] [--keep] [--verbose]
"""
from __future__ import annotations

import sys
from pathlib import Path

LIB = Path(__file__).resolve().parent
sys.path.insert(0, str(LIB))  # python -I drops the script folder (PSM 3.1)

import argparse  # noqa: E402
import copy  # noqa: E402
import hashlib  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import re  # noqa: E402
import shutil  # noqa: E402
import stat  # noqa: E402
import subprocess  # noqa: E402
import tempfile  # noqa: E402
import time  # noqa: E402
import traceback  # noqa: E402

import tl  # noqa: E402
from _tl import common as CM  # noqa: E402
from _tl import components as C  # noqa: E402
from _tl import nhash as NH  # noqa: E402
from _tl import resolve as R  # noqa: E402
from _tl.lock import IS_WINDOWS  # noqa: E402

# ---------------------------------------------------------------- harness
RESULTS: list[dict] = []
SKIPPED: list[tuple[str, str]] = []
SCANNED_TEXT: list[tuple[str, str]] = []  # (where, text) for the TL-INV-8 scan
VERBOSE = False


def check(control: str, arm: str, ok: bool, detail: str = "") -> bool:
    RESULTS.append({"control": control, "arm": arm, "ok": bool(ok), "detail": CM.one_line(detail, 400)})
    if VERBOSE or not ok:
        print(f"  {'pass' if ok else 'FAIL'} {control} [{arm}] {CM.one_line(detail, 300)}")
    return ok


def pos(control: str, fired: bool, detail: str = "") -> bool:
    return check(control, "positive", fired, ("fired: " if fired else "did NOT fire: ") + detail)


def neg(control: str, quiet: bool, detail: str = "") -> bool:
    return check(control, "negative", quiet, ("quiet: " if quiet else "FIRED: ") + detail)


def tlrun(*args) -> tuple[int, list[str], CM.Outcome]:
    argv = [str(a) for a in args]
    code, out = tl.run(argv)
    lines = out.lines()
    SCANNED_TEXT.append((" ".join(argv[:2]), "\n".join(lines)))
    if VERBOSE:
        print("    $ tl.py " + " ".join(argv))
        for ln in lines:
            print("      " + ln)
    return code, lines, out


def ids(rows, bucket=None) -> set:
    return {r["id"] for r in rows if bucket is None or r["bucket"] == bucket}


def rows_of(film: Path, stage: str = "static") -> list[dict]:
    v = json.loads((film / "build" / "validate.json").read_text(encoding="utf-8"))
    return (v.get(stage) or {}).get("rows", [])


def resolved_of(film: Path) -> dict:
    return json.loads((film / "build" / "timeline.resolved.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------- fixtures
FIXTURE_RULES = {
    "schema_version": 1,
    "film_types": ["intro-ad", "hype-ad", "product-tour", "narrated-explainer", "data-showreel"],
    "rules": [{"id": "end_hold", "range_s": [1.5, 2.5]}],
    "params": {"timeline": {"free_share_max": 0.30,
                            "stock_devices": ["particle-burst", "tunnel", "floating-card-pile", "glitch",
                                              "big-text-as-design", "fake-hud"]}},
}


def comp(cid: str, version: int = 1, *, energy="any", film_types="any", roles="any", rhythm="any", params=None,
         card=None, card_tier="unverified", label_type=False, hold_range=None, stock=False, requires=(),
         conflicts=(), emits=None, intents=None) -> dict:
    fam = cid.split(".")[0]
    o = {"schema_version": 1, "id": cid, "version": version, "family": fam, "card": card, "card_tier": card_tier,
         "tone": {"energy": energy, "film_types": film_types}, "when": {"roles": roles, "rhythm_sources": rhythm},
         "conflicts": list(conflicts), "params": params or {}, "label_type": label_type, "stock": stock,
         "requires": list(requires), "license": "own", "provenance": "selftest fixture", "impl": "component.js"}
    if hold_range is not None:
        o["hold_range"] = hold_range
    if emits is not None:
        o["emits"] = emits
    if intents is not None:
        o["intents"] = intents
    return o


def P(type_, **kw) -> dict:
    return {"type": type_, "evidence": "unverified", **kw}


def base_components() -> list[dict]:
    return [
        comp("opening.shape-to-name", roles=["opening"],
             params={"source_asset": P("asset"), "name_asset": P("asset")}),
        comp("chapter-card.verb", roles=["chapter-card"], params={"verb": P("string"), "index": P("string")}),
        comp("transition.dim-through-ground", roles=["transition"]),
        comp("end-card.restate", roles=["end-card"], params={"line": P("line"), "name_asset": P("asset")}),
        comp("ui-demo.cursor-click", roles=["feature"]),
        comp("end-card.plain", roles=["end-card"]),
    ]


def make_lib(root: Path, comps: list[dict], evidence: dict | None = None, *, state: str = "candidate") -> Path:
    d = root
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    ev = {"schema_version": 1, "entries": {}}
    for c in comps:
        f = d / c["family"] / f"{c['id'].split('.', 1)[1]}.v{c['version']}"
        f.mkdir(parents=True, exist_ok=True)
        (f / "component.json").write_text(json.dumps(c, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (f / "component.js").write_text(f"// fixture {c['id']}@{c['version']}\n", encoding="utf-8")
        ev["entries"][f"{c['id']}@{c['version']}"] = {"state": state}
    for k, v in (evidence or {}).items():
        ev["entries"][k] = v
    (d / "evidence.json").write_text(json.dumps(ev, indent=2) + "\n", encoding="utf-8")
    index, md = C.build_index(d)
    C.write_index(d, index, md)
    return d


def base_timeline() -> dict:
    """Design 7.1 (captions off: no caption component in the fixture library)."""
    return {
        "meta": {"schema_version": 1, "film_id": "fx",
                 "format": {"size": "1920x1080", "fps": 30, "duration_policy": "fit"},
                 "lead": 1.0, "tail": 2.0, "section_gap": 1.2},
        "decisions": {
            "film_type": {"value": "product-tour", "source": "user"},
            "audience": {"value": "第一次聽說 DIT 的 AI 工具使用者", "source": "user"},
            "energy": {"value": "calm", "source": "user"},
            "rhythm_source": {"value": "narration", "source": "default", "evidence": "T08 / BR-5"},
            "ground": {"value": "#f6f1e7", "source": "model", "evidence": "whole-film-rules §1"},
        },
        "assets": [
            {"id": "cap-sidebar", "kind": "capture", "path": "assets/sidebar.png", "license": "own"},
            {"id": "dit-name", "kind": "logo", "path": "assets/dit-wordmark.svg", "license": "own",
             "portrays": {"subject_name": "DIT"}},
        ],
        "tracks": {
            "narration": [
                {"id": "L1", "text": "從一直按同意，到看懂這次是怎麼做出來的", "section": "S1"},
                {"id": "L2", "text": "第二句", "section": "S2"},
                {"id": "L3", "text": "第三句", "section": "S2"},
                {"id": "L4", "text": "第四句", "section": "S2"},
            ],
            "picture": [
                {"id": "S1", "role": "opening", "at": 0, "dur": {"lines": "L1-L1", "pad_after": 0.3},
                 "freedom": "locked", "device": {"component": "opening.shape-to-name@1",
                                                 "params": {"source_asset": "cap-sidebar", "name_asset": "dit-name"}},
                 "motion_intent": ["結構符號一個個畫出：產品看的就是這個結構", "收成產品名：結構＝產品"]},
                {"id": "C1", "role": "chapter-card", "at": {"anchor": "clip:S1.end"}, "dur": 1.4,
                 "freedom": "locked", "device": {"component": "chapter-card.verb@1",
                                                 "params": {"verb": "看懂", "index": "01 / 03"}},
                 "motion_intent": ["動詞卡：標出下一段要做的事"]},
                {"id": "S2", "role": "feature", "at": {"anchor": "line:L2.start", "offset": -0.15},
                 "dur": {"lines": "L2-L4", "pad_after": 0.3},
                 "transition_in": {"component": "transition.dim-through-ground@1", "dur": 0.3},
                 "freedom": "guided", "device": {"family": "ui-demo"},
                 "headline": "看懂這次怎麼做", "motion_intent": ["游標點下時間軸：指出這一步在哪裡"]},
                {"id": "E1", "role": "end-card", "at": {"anchor": "clip:S2.end"}, "dur": 0.8,
                 "freedom": "locked", "device": {"component": "end-card.restate@1",
                                                 "params": {"line": "L1", "name_asset": "dit-name"}},
                 "motion_intent": ["重述主句後收成產品名：記住的是這一句"]},
            ],
            "overlay": [], "music": None, "sfx": [], "captions": None,
        },
    }


BASE_EST = {"L1": 3.0, "L2": 2.0, "L3": 2.5, "L4": 2.0}
ASSET_BYTES = {"assets/sidebar.png": b"\x89PNG\r\n\x1a\nfixture-sidebar", "assets/dit-wordmark.svg":
               b"<svg xmlns='http://www.w3.org/2000/svg'><text>DIT</text></svg>\n"}


def clip_of(t: dict, cid: str) -> dict:
    for c in t["tracks"]["picture"] + t["tracks"]["overlay"]:
        if c["id"] == cid:
            return c
    raise KeyError(cid)


def make_film(parent: Path, name: str, t: dict | None = None, *, est: dict | None = BASE_EST,
              clips: dict | None = None, extra_files: dict | None = None, sha: bool = True) -> Path:
    film = parent / name
    if film.exists():
        CM.rmtree_force(film)
    (film / "assets").mkdir(parents=True)
    t = copy.deepcopy(t if t is not None else base_timeline())
    t["meta"]["film_id"] = name
    files = dict(ASSET_BYTES)
    files.update(extra_files or {})
    for rel, data in files.items():
        p = film / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    if sha:
        for a in t.get("assets") or []:
            p = film / a["path"]
            if p.is_file() and "sha256" not in a:
                a["sha256"] = NH.file_nsha(p)
    (film / "film.timeline.json").write_text(json.dumps(t, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if est is not None and t["tracks"].get("narration"):
        (film / "voice").mkdir(exist_ok=True)
        lj = {"schema_version": 1, "lines": {k: {"est_dur": v} for k, v in est.items()}}
        (film / "voice" / "lines.json").write_text(json.dumps(lj, indent=2) + "\n", encoding="utf-8")
    for cid, src in (clips or {}).items():
        (film / "clips").mkdir(exist_ok=True)
        (film / "clips" / f"{cid}.js").write_text(src, encoding="utf-8")
    return film


def V(*muts) -> dict:
    """Base timeline with mutations applied in order."""
    t = base_timeline()
    for m in muts:
        m(t)
    return t


def fix_c1(t: dict) -> None:
    """SEM-2-legal base: C1 dur 0.9 (design 7.1 note)."""
    clip_of(t, "C1")["dur"] = 0.9


def set_clip(cid: str, **kv):
    def m(t):
        c = clip_of(t, cid)
        for k, v in kv.items():
            if v is DEL:
                c.pop(k, None)
            else:
                c[k] = v
    return m


def set_meta(**kv):
    def m(t):
        for k, v in kv.items():
            if k in ("duration_policy", "duration_s", "fps", "size"):
                if v is DEL:
                    t["meta"]["format"].pop(k, None)
                else:
                    t["meta"]["format"][k] = v
            else:
                t["meta"][k] = v
    return m


def set_decision(key: str, value=None, source="user"):
    def m(t):
        if value is DEL:
            t["decisions"].pop(key, None)
        else:
            t["decisions"][key] = {"value": value, "source": source}
    return m


def add_clip(clip: dict, before: str | None = None, track: str = "picture"):
    def m(t):
        arr = t["tracks"][track]
        if before is None:
            arr.append(copy.deepcopy(clip))
        else:
            k = next(i for i, c in enumerate(arr) if c["id"] == before)
            arr.insert(k, copy.deepcopy(clip))
    return m


class _Del:
    def __repr__(self):
        return "DEL"


DEL = _Del()

S3 = {"id": "S3", "role": "feature", "at": {"anchor": "clip:S2.end"}, "dur": 1.0, "freedom": "guided",
      "device": {"family": "ui-demo"}, "motion_intent": ["第三段：游標移到匯出鍵"]}


def plain_timeline(picture: list, *, narration=None, rhythm="content", energy="calm", film_type="product-tour",
                   tail=2.0, policy="fit", duration_s=None) -> dict:
    t = base_timeline()
    t["meta"]["tail"] = tail
    t["meta"]["format"]["duration_policy"] = policy
    if duration_s is not None:
        t["meta"]["format"]["duration_s"] = duration_s
    t["decisions"]["rhythm_source"] = {"value": rhythm, "source": "user"}
    t["decisions"]["energy"] = {"value": energy, "source": "user"}
    t["decisions"]["film_type"] = {"value": film_type, "source": "user"}
    t["tracks"]["narration"] = narration or []
    t["tracks"]["picture"] = copy.deepcopy(picture)
    return t


def g(cid, role, at, dur, family="ui-demo", **kw) -> dict:
    """A guided clip."""
    c = {"id": cid, "role": role, "at": at, "dur": dur, "freedom": "guided", "device": {"family": family},
         "motion_intent": [f"{cid} 的動作"]}
    c.update(kw)
    return c


def lk(cid, role, at, dur, ref, params=None, **kw) -> dict:
    """A locked clip."""
    c = {"id": cid, "role": role, "at": at, "dur": dur, "freedom": "locked",
         "device": {"component": ref, "params": params or {}}, "motion_intent": [f"{cid} 的動作"]}
    c.update(kw)
    return c


def write_timeline(film: Path, t: dict) -> None:
    (film / "film.timeline.json").write_text(json.dumps(t, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_timeline(film: Path) -> dict:
    return json.loads((film / "film.timeline.json").read_text(encoding="utf-8"))


class Env:
    """Shared fixture paths for one run."""

    def __init__(self, root: Path):
        self.root = root
        self.rules = root / "rules.json"
        self.rules.write_text(json.dumps(FIXTURE_RULES, indent=2) + "\n", encoding="utf-8")
        self.lib = make_lib(root / "lib-base", base_components())
        self.films = root / "films"
        self.films.mkdir()

    def common(self, lib: Path | None = None, rules: Path | None = None) -> list[str]:
        return ["--rules", str(rules or self.rules), "--components", str(lib or self.lib)]

    def static(self, film, **kw):
        return tlrun("validate", film, "--static", *self.common(**kw))

    def resolve(self, film, **kw):
        return tlrun("resolve", film, *self.common(**kw))

    def timed(self, film, **kw):
        return tlrun("validate", film, "--timed", *self.common(**kw))

    def view(self, film, **kw):
        return tlrun("view", film, *self.common(**kw))

    def through(self, film, upto="timed", **kw):
        """static -> resolve -> timed (-> view); returns the last (code, lines, out)."""
        r = self.static(film, **kw)
        if r[0] not in (0,) or upto == "static":
            return r
        r = self.resolve(film, **kw)
        if r[0] != 0 or upto == "resolve":
            return r
        r = self.timed(film, **kw)
        if upto == "timed":
            return r
        return self.view(film, **kw)


# ---------------------------------------------------------------- controls
CONTROLS: list = []


def control(fn):
    CONTROLS.append(fn)
    return fn


@control
def smoke_base(env: Env):
    """Base fixture end to end: resolved values PSM 10.2 header."""
    film = make_film(env.films, "base")
    code, lines, _ = env.static(film)
    check("base.static", "negative", code == 0, " | ".join(lines))
    code, lines, _ = env.resolve(film)
    check("base.resolve", "negative", code == 0, " | ".join(lines))
    res = resolved_of(film)
    ln = {x["id"]: (x["t0"], x["t1"]) for x in res["lines"]}
    want = {"L1": (1.0, 4.0), "L2": (5.2, 7.2), "L3": (7.65, 10.15), "L4": (10.6, 12.6)}
    check("base.lines", "negative", all(abs(ln[k][0] - v[0]) < 1e-6 and abs(ln[k][1] - v[1]) < 1e-6
                                        for k, v in want.items()), str(ln))
    pic = {p["id"]: p for p in res["picture"]}
    s2 = pic["S2"]
    ok = (abs(pic["S1"]["t0"]) < 1e-9 and abs(pic["S1"]["e"] - 4.3) < 1e-6 and abs(pic["C1"]["t0"] - 4.3) < 1e-6
          and abs(pic["C1"]["e"] - 5.7) < 1e-6 and s2["t0_f"] == 152 and abs(s2["t0_raw"] - 5.05) < 1e-6
          and abs(s2["window"][0] - 5.066667) < 1e-6 and abs(s2["window"][1] - 5.366667) < 1e-6
          and abs(s2["cut_moment"] - 5.216667) < 1e-6 and abs(s2["e"] - 12.9) < 1e-6
          and abs(pic["E1"]["t0"] - 12.9) < 1e-6 and abs(pic["E1"]["e"] - 13.7) < 1e-6
          and res["n_frames"] == 471 and abs(res["film_end_s"] - 15.7) < 1e-6
          and abs(res["tail_hold"]["t0"] - 13.7) < 1e-6 and abs(res["tail_hold"]["t1"] - 15.7) < 1e-6)
    check("base.picture", "negative", ok, json.dumps({k: [v["t0"], v["e"]] for k, v in pic.items()})
          + f" n_frames {res['n_frames']} window {s2.get('window')} cut {s2.get('cut_moment')}")
    code, lines, _ = env.timed(film)
    trows = rows_of(film, "timed")
    r = next((x for x in trows if x["id"] == "TV-2#S2.sem2"), None)
    pos("TV-2 SEM-2", code == CM.EXIT_BLOCKING and r is not None and r["bucket"] == "blocking" and "C1" in r["measured"],
        f"exit {code}; {r and r['measured']}")
    film2 = make_film(env.films, "sem2-neg", V(fix_c1))
    env.through(film2)
    neg("TV-2 SEM-2", not any(x["id"].endswith(".sem2") for x in rows_of(film2, "timed")),
        str(sorted(ids(rows_of(film2, "timed")))))
    # at (BR-11) on the base resolved file
    code, _, out = tlrun("at", film, "5.2", *env.common())
    a = out.result or {}
    pos("at 5.2 (BR-11)", code == 0 and a.get("picture") == ["C1", "S2"] and a.get("in_transition") is True, str(a))
    code, _, out = tlrun("at", film, "9.0", *env.common())
    a = out.result or {}
    neg("at 9.0 (BR-11)", code == 0 and a.get("picture") == ["S2"] and a.get("line") == "L3"
        and abs((a.get("lt") or {}).get("S2", -1) - 3.933333) < 1e-6 and not a.get("in_transition"), str(a))
    code, _, out = tlrun("at", film, "14.5", *env.common())
    a = out.result or {}
    neg("at 14.5 (BR-11)", code == 0 and a.get("picture") == ["E1"] and a.get("where") == "tail hold", str(a))


@control
def inv1_nhash(env: Env):
    """TL-INV-1: normalized hash."""
    obj = {"b": 1, "a": [1, "文字"], "c": {"y": 2, "x": 1}}
    txt = json.dumps(obj, ensure_ascii=False, indent=2) + "\n"
    p1, p2, p3, p4 = (env.root / f"h{k}.json" for k in range(1, 5))
    p1.write_bytes(txt.encode("utf-8"))
    p2.write_bytes(b"\xef\xbb\xbf" + txt.replace("\n", "\r\n").encode("utf-8"))
    p3.write_bytes(txt.replace("文字", "文子").encode("utf-8"))
    p4.write_bytes(json.dumps({"c": {"x": 1, "y": 2}, "a": [1, "文字"], "b": 1}, ensure_ascii=False).encode("utf-8"))
    h1, h2, h3, h4 = (NH.file_nsha(p) for p in (p1, p2, p3, p4))
    pos("TL-INV-1 CRLF+BOM = LF", h1 == h2, f"{h1[:12]} {h2[:12]}")
    pos("TL-INV-1 key order", h1 == h4, f"{h1[:12]} {h4[:12]}")
    neg("TL-INV-1 one character", h1 != h3, f"{h1[:12]} {h3[:12]}")
    j1, j2 = env.root / "a.js", env.root / "b.js"
    j1.write_bytes(b"// x\nconst a = 1;\n")
    j2.write_bytes(b"\xef\xbb\xbf// x\r\nconst a = 1;\r\n")
    pos("TL-INV-1 text file", NH.file_nsha(j1) == NH.file_nsha(j2))


@control
def tg7_snap(env: Env):
    f = R.snapf(5.05, 30)
    pos("TG-7 5.05 s -> frame 152", f == 152 and abs(R.fsec(f, 30) - 5.066667) < 1e-6, f"{f} {R.fsec(f, 30)}")
    neg("TG-7 5.0 s -> frame 150", R.snapf(5.0, 30) == 150, str(R.snapf(5.0, 30)))


@control
def tg8_case(env: Env):
    t = V(fix_c1)
    t["assets"].append({"id": "cap-a", "kind": "capture", "path": "assets/A.png"})
    t["assets"].append({"id": "cap-b", "kind": "capture", "path": "assets/a.png"})
    film = make_film(env.films, "tg8", t, extra_files={"assets/A.png": b"A"}, sha=False)
    code, lines, _ = env.static(film)
    rows = rows_of(film)
    hit = [r for r in rows if r["message_key"] == "tv1.asset" and "spec_invalid" in r["message"]]
    pos("TG-8 assets differing by case", code == CM.EXIT_BLOCKING and bool(hit), lines[0])
    try:
        NH.check_case(["clips/A.js", "clips/a.js"], "clips")
        fired = False
    except CM.SpecInvalid as e:
        fired = e.kind == "spec_invalid"
    pos("TG-8 nhash case collision", fired)
    t = V(fix_c1)
    t["assets"].append({"id": "cap-a", "kind": "capture", "path": "assets/A.png"})
    t["assets"].append({"id": "cap-b", "kind": "capture", "path": "assets/b.png"})
    film = make_film(env.films, "tg8-neg", t, extra_files={"assets/A.png": b"A", "assets/b.png": b"B"})
    code, lines, _ = env.static(film)
    neg("TG-8 distinct names", code == 0, lines[0])
    try:
        NH.check_case(["clips/A.js", "clips/b.js"], "clips")
        quiet = True
    except CM.SpecInvalid:
        quiet = False
    neg("TG-8 nhash distinct", quiet)


# ---- mini JSON-Schema evaluator (draft 2020-12 subset used by film.timeline.schema.json + x-tl- keywords)
def _jtype(v, t) -> bool:
    if t == "object":
        return isinstance(v, dict)
    if t == "array":
        return isinstance(v, list)
    if t == "string":
        return isinstance(v, str)
    if t == "null":
        return v is None
    if t == "boolean":
        return isinstance(v, bool)
    if t == "integer":
        return (isinstance(v, int) and not isinstance(v, bool)) or (isinstance(v, float) and v.is_integer())
    if t == "number":
        return isinstance(v, (int, float)) and not isinstance(v, bool)
    raise ValueError(t)


def schema_errors(inst, sch, root, path="$") -> list[str]:
    if sch is True or sch == {}:
        return []
    if sch is False:
        return [f"{path}: false schema"]
    err = []
    if "$ref" in sch:
        node = root
        for part in sch["$ref"].lstrip("#/").split("/"):
            node = node[part]
        err += schema_errors(inst, node, root, path)
    if "type" in sch:
        ts = sch["type"] if isinstance(sch["type"], list) else [sch["type"]]
        if not any(_jtype(inst, t) for t in ts):
            return err + [f"{path}: type {ts}"]
    if "const" in sch and inst != sch["const"]:
        err.append(f"{path}: const")
    if "enum" in sch and inst not in sch["enum"]:
        err.append(f"{path}: enum")
    if isinstance(inst, str) and "pattern" in sch and not re.search(sch["pattern"], inst):
        err.append(f"{path}: pattern {sch['pattern']}")
    if _jtype(inst, "number"):
        if "minimum" in sch and inst < sch["minimum"]:
            err.append(f"{path}: minimum")
        if "maximum" in sch and inst > sch["maximum"]:
            err.append(f"{path}: maximum")
        if "exclusiveMinimum" in sch and not inst > sch["exclusiveMinimum"]:
            err.append(f"{path}: exclusiveMinimum")
    if isinstance(inst, list):
        if "minItems" in sch and len(inst) < sch["minItems"]:
            err.append(f"{path}: minItems")
        if "maxItems" in sch and len(inst) > sch["maxItems"]:
            err.append(f"{path}: maxItems")
        if "items" in sch:
            for k, x in enumerate(inst):
                err += schema_errors(x, sch["items"], root, f"{path}[{k}]")
        if "x-tl-unique-casefold" in sch:
            key = sch["x-tl-unique-casefold"]
            seen = {}
            for x in inst:
                v = x.get(key) if isinstance(x, dict) else None
                if isinstance(v, str):
                    if v.casefold() in seen and seen[v.casefold()] != v:
                        err.append(f"{path}: x-tl-unique-casefold {v}")
                    seen.setdefault(v.casefold(), v)
    if isinstance(inst, dict):
        props = sch.get("properties", {})
        for k in sch.get("required", []):
            if k not in inst:
                err.append(f"{path}: required {k}")
        if "minProperties" in sch and len(inst) < sch["minProperties"]:
            err.append(f"{path}: minProperties")
        for k, v in inst.items():
            if k in props:
                err += schema_errors(v, props[k], root, f"{path}.{k}")
            elif "additionalProperties" in sch:
                ap = sch["additionalProperties"]
                if ap is False:
                    err.append(f"{path}: additional property {k}")
                elif isinstance(ap, dict):
                    err += schema_errors(v, ap, root, f"{path}.{k}")
        if sch.get("x-tl-film-end-requires-fixed"):
            policy = ((inst.get("meta") or {}).get("format") or {}).get("duration_policy")
            if policy != "fixed" and '"anchor": "film.end"' in json.dumps(inst.get("tracks")):
                err.append(f"{path}: x-tl-film-end-requires-fixed")
        if sch.get("x-tl-unique-key-ids"):
            tracks = inst.get("tracks") if isinstance(inst.get("tracks"), dict) else {}
            kids = [k.get("id") for tn in ("picture", "overlay") for c in (tracks.get(tn) or []) if isinstance(c, dict)
                    for k in (c.get("keys") or []) if isinstance(k, dict)]
            if len(kids) != len(set(kids)):
                err.append(f"{path}: x-tl-unique-key-ids")
    for sub in sch.get("allOf", []):
        err += schema_errors(inst, sub, root, path)
    if "oneOf" in sch:
        n = sum(1 for sub in sch["oneOf"] if not schema_errors(inst, sub, root, path))
        if n != 1:
            err.append(f"{path}: oneOf matched {n}")
    if "not" in sch and not schema_errors(inst, sch["not"], root, path):
        err.append(f"{path}: not")
    if "if" in sch:
        if not schema_errors(inst, sch["if"], root, path):
            if "then" in sch:
                err += schema_errors(inst, sch["then"], root, path)
        elif "else" in sch:
            err += schema_errors(inst, sch["else"], root, path)
    return err


def schema_fixtures() -> tuple[list, list]:
    from _tl import model as M  # noqa: F401
    valid = [
        ("base, C1 0.9", V(fix_c1)),
        ("fixed 20.0 + E1 at film.end-3", V(fix_c1, set_meta(duration_policy="fixed", duration_s=20.0),
                                           set_clip("E1", at={"anchor": "film.end", "offset": -3}))),
        ("overlay + sfx", V(fix_c1, add_clip({"id": "O1", "role": "overlay", "at": 2.0, "dur": 1.5, "z": 1,
                                             "freedom": "guided", "device": {"family": "text-treatment"},
                                             "motion_intent": ["字幕條淡入"]}, track="overlay"),
                            lambda t: t["tracks"]["sfx"].append({"at": {"anchor": "clip:S2.start"}, "sound": "tick",
                                                                 "gain_db": -12, "why": "標出換段"}))),
        ("freedom omitted + cut", V(fix_c1, set_clip("S2", freedom=DEL), set_clip("E1", transition_in="cut"))),
        ("free clip", V(fix_c1, add_clip(dict(S3, freedom="free", device=None), before="E1"),
                        lambda t: clip_of(t, "S3").pop("device"), set_clip("E1", at={"anchor": "clip:S3.end"}))),
        ("declares/ground/claims/camera", V(fix_c1, set_clip(
            "E1", declares={"holds": [{"t0": 0.2, "t1": 0.8, "why": "產品名停住"}]},
            ground_exception={"color": "#000000", "why": "結尾反白"}, camera={"goal": "none"}),
            lambda t: t["assets"].append({"id": "guide", "kind": "data", "path": "assets/guide.md",
                                          "claims_ref": "assets/guide.md"}),
            set_clip("S2", claims={"headline": "guide:看懂"}))),
        ("override user confirmed", V(fix_c1, set_clip("S1", override={"why": "使用者要", "source": "user",
                                                                       "confirmed": "使用者說可以", "date": "2026-10-11"}))),
        ("no narration", plain_timeline([g("A", "opening", 0, 3.0, family="opening"), g("B", "feature", 3.0, 4.0)])),
        ("keys key + breakdown", V(fix_c1, set_clip("S2", keys=[
            {"id": "K-S2a", "at": 0.4, "role": "breakdown", "what": "游標移向時間軸"},
            {"id": "K-S2b", "at": 1.5, "role": "key", "hold": 0.6, "what": "時間軸那一格被點亮"}]))),
        ("overlay keys", V(fix_c1, add_clip({"id": "O1", "role": "overlay", "at": 2.0, "dur": 1.5, "z": 1,
                                             "freedom": "guided", "device": {"family": "text-treatment"},
                                             "motion_intent": ["字幕條淡入"],
                                             "keys": [{"id": "K-O1", "at": 0.5, "role": "key", "what": "字幕讀完"}]},
                                            track="overlay"))),
        ("product_state + shows_state + required", V(
            fix_c1, lambda t: t.__setitem__("product_state", [{"id": "ST1", "facts": {"slots": 5, "open": True},
                                                               "source": "lobby:test#open"}]),
            set_clip("S2", shows_state=["ST1"]),
            lambda t: t["assets"][0].__setitem__("required", {"min_visible_s": 2.0, "no_crop": True}))),
    ]
    invalid = [
        ("missing motion_intent key", V(fix_c1, set_clip("S1", motion_intent=DEL))),
        ("transition_in family-only", V(fix_c1, set_clip("S2", transition_in={"family": "transition"}))),
        ("fixed without duration_s", V(fix_c1, set_meta(duration_policy="fixed"))),
        ("fit with duration_s", V(fix_c1, set_meta(duration_s=20.0))),
        ("odd size", V(fix_c1, set_meta(size="1921x1080"))),
        ("unknown key", V(fix_c1, set_clip("S2", colour="red"))),
        ("music non-null", V(fix_c1, lambda t: t["tracks"].__setitem__("music", {"asset": "m"}))),
        ("override user without confirmed", V(fix_c1, set_clip("S1", override={"why": "x", "source": "user",
                                                                              "date": "2026-10-11"}))),
        ("declares without why", V(fix_c1, set_clip("E1", declares={"holds": [{"t0": 0.2, "t1": 0.8}]}))),
        ("bad clip id", V(fix_c1, set_clip("E1", id="e1"))),
        ("bad TimeRef string", V(fix_c1, set_clip("E1", at="S2.end"))),
        ("film.end in fit", V(fix_c1, set_clip("E1", at={"anchor": "film.end", "offset": -3}))),
        ("rhythm_source music-bar", V(fix_c1, set_decision("rhythm_source", "music-bar"))),
        ("assets differing by case", V(fix_c1, lambda t: t["assets"].extend([
            {"id": "cap-a", "kind": "capture", "path": "assets/A.png"},
            {"id": "cap-b", "kind": "capture", "path": "assets/a.png"}]))),
        ("duplicate key id", V(fix_c1, set_clip("S1", keys=[{"id": "K1", "at": 0.5, "role": "key", "what": "a"}]),
                               set_clip("S2", keys=[{"id": "K1", "at": 0.5, "role": "key", "what": "b"}]))),
        ("key without what", V(fix_c1, set_clip("S2", keys=[{"id": "K1", "at": 0.5, "role": "key", "what": ""}]))),
        ("key role unknown", V(fix_c1, set_clip("S2", keys=[{"id": "K1", "at": 0.5, "role": "hero", "what": "a"}]))),
        ("required unknown key", V(fix_c1, lambda t: t["assets"][0].__setitem__("required", {"seconds": 2}))),
        ("shows_state empty", V(fix_c1, set_clip("S2", shows_state=[]))),
    ]
    return valid, invalid


@control
def schema_agreement(env: Env):
    from _tl import model as M
    from _tl.rules import load_rules
    schema = json.loads((LIB / "film.timeline.schema.json").read_text(encoding="utf-8"))
    rules = load_rules(env.rules)
    valid, invalid = schema_fixtures()
    check("schema fixtures count", "negative", (len(valid), len(invalid)) == (11, 19), f"{len(valid)} + {len(invalid)}")
    for name, t in invalid:
        vrows = [r for r in M.validate_timeline(copy.deepcopy(t), rules=rules) if r["bucket"] == "blocking"]
        serr = schema_errors(t, schema, schema)
        pos(f"schema agreement invalid: {name}", bool(vrows) and bool(serr),
            f"validator {len(vrows)} ({vrows[0]['id'] if vrows else '-'}); schema {serr[:1]}")
    for name, t in valid:
        vrows = [r for r in M.validate_timeline(copy.deepcopy(t), rules=rules) if r["bucket"] == "blocking"]
        serr = schema_errors(t, schema, schema)
        neg(f"schema agreement valid: {name}", not vrows and not serr,
            f"validator {[r['id'] + ' ' + str(r['measured']) for r in vrows[:2]]}; schema {serr[:2]}")


@control
def tv1_cycle(env: Env):
    # S2 gets a number dur: a lines dur ends at its last line, so its end would not read its start (no cycle)
    t = V(fix_c1, add_clip(S3, before="E1"), set_clip("S2", at={"anchor": "clip:S3.end"}, dur=7.0),
          set_clip("S3", at={"anchor": "clip:S2.end"}), set_clip("E1", at={"anchor": "clip:S3.end"}))
    film = make_film(env.films, "cycle", t)
    code, lines, _ = env.static(film)
    r = next((x for x in rows_of(film) if x["message_key"] == "tv1.cycle"), None)
    pos("TV-1 cycle (TL-INV-2)", code == CM.EXIT_BLOCKING and r is not None and "S2" in str(r["measured"])
        and "S3" in str(r["measured"]), str(r and r["measured"]))
    t = V(fix_c1, add_clip(S3, before="E1"), set_clip("E1", at={"anchor": "clip:S3.end"}))
    film = make_film(env.films, "chain", t)
    code, lines, _ = env.through(film, "resolve")
    neg("TV-1 chain S1 -> S2 -> S3 resolves", code == 0 and not any(x["message_key"] == "tv1.cycle" for x in rows_of(film)),
        lines[0])
    # order_seed: the topological order changes, the resolved file does not
    from _tl import model as M
    obj = read_timeline(film)
    tr = M.tracks(obj)
    gph = M.anchor_graph(tr["picture"], tr["overlay"])
    o0, o7 = R._order(gph, 0), R._order(gph, 7)
    lj = json.loads((film / "voice" / "lines.json").read_text(encoding="utf-8"))
    src = R.line_durations(tr["narration"], lj)
    r0 = CM.dumps(R.resolve(film, obj, src, order_seed=0))
    r7 = CM.dumps(R.resolve(film, obj, src, order_seed=7))
    pos("TL-INV-2 order_seed permutes the evaluation order", o0 != o7, f"{o0} vs {o7}")
    neg("TL-INV-2 order_seed 0 vs 7 resolved byte-identical", r0 == r7)


@control
def tv1_film_end(env: Env):
    film = make_film(env.films, "fe-fit", V(fix_c1, set_clip("E1", at={"anchor": "film.end", "offset": -3})))
    code, lines, _ = env.static(film)
    pos("TV-1 film.end under fit (SEM-11)", code == CM.EXIT_BLOCKING
        and "TV-1#E1" in ids(rows_of(film), "blocking"), lines[0])
    film = make_film(env.films, "fe-fixed", V(fix_c1, set_meta(duration_policy="fixed", duration_s=20.0),
                                              set_clip("E1", at={"anchor": "film.end", "offset": -3})))
    code, lines, _ = env.through(film, "resolve")
    e1 = next((p for p in resolved_of(film)["picture"] if p["id"] == "E1"), {}) if code == 0 else {}
    neg("TV-1 film.end under fixed resolves", code == 0 and abs(e1.get("t0", -1) - 17.0) < 1e-6, f"{lines[0]} E1 {e1.get('t0')}")


@control
def tv1_sem3(env: Env):
    t = V(fix_c1, add_clip(S3, before="E1"), set_clip("E1", at={"anchor": "clip:S3.end"}),
          lambda t: t["tracks"]["narration"][2].__setitem__("section", "S3"))
    film = make_film(env.films, "sem3", t)
    env.static(film)
    pos("TV-1 SEM-3", any(r["id"].startswith("TV-1#S2") and r["message_key"] == "tv1.sem3" for r in rows_of(film)),
        str(sorted(ids(rows_of(film)))))
    film = make_film(env.films, "sem3-neg", V(fix_c1, add_clip(S3, before="E1"), set_clip("E1", at={"anchor": "clip:S3.end"})))
    env.static(film)
    neg("TV-1 SEM-3", not any(r["message_key"] == "tv1.sem3" for r in rows_of(film)), str(sorted(ids(rows_of(film)))))


@control
def tv1_missing(env: Env):
    film = make_film(env.films, "miss-at", V(fix_c1, set_clip("S2", at=DEL)))
    env.static(film)
    r = next((x for x in rows_of(film) if x["message_key"] == "tv1.missing_at"), None)
    pos("TV-1 missing at (X-13)", r is not None and r["where"] == "S2" and r["bucket"] == "blocking", str(r and r["id"]))
    film = make_film(env.films, "miss-mi", V(fix_c1, set_clip("S2", motion_intent=DEL)))
    env.static(film)
    r = next((x for x in rows_of(film) if x["message_key"] == "tv1.missing_motion_intent"), None)
    pos("TV-1 missing motion_intent key", r is not None and r["bucket"] == "blocking", str(r and r["id"]))
    film = make_film(env.films, "miss-fr", V(fix_c1, set_clip("S2", freedom=DEL)))
    code, lines, _ = env.through(film, "view")
    v = json.loads((film / "build" / "validate.json").read_text(encoding="utf-8"))
    html = (film / "build" / "timeline.html").read_text(encoding="utf-8") if code == 0 else ""
    neg("TV-1 missing freedom -> default, no row", code == 0 and "S2.freedom=guided" in v["defaults_applied"]
        and not any(r["where"] == "S2" for r in rows_of(film) if r["check"] == "TV-1") and "（預設）" in html, lines[0])


@control
def tv2_sem4(env: Env):
    film = make_film(env.films, "sem4", V(fix_c1, set_clip("S2", at={"anchor": "line:L2.start", "offset": 0.25})))
    env.through(film)
    r = next((x for x in rows_of(film, "timed") if x["id"] == "TV-2#S2.sem4"), None)
    pos("TV-2 SEM-4", r is not None and r["bucket"] == "blocking", str(r and r["measured"]))
    film = make_film(env.films, "sem4-neg", V(fix_c1, add_clip(S3, before="E1"), set_clip("E1", at={"anchor": "clip:S3.end"})))
    env.through(film)
    neg("TV-2 SEM-4 (base S2 dev 0.016667; S1 and a lineless feature not checked)",
        not any(x["id"].endswith(".sem4") for x in rows_of(film, "timed")), str(sorted(ids(rows_of(film, "timed")))))


def sem1_timeline(c_at: float) -> dict:
    return plain_timeline([g("A", "opening", 0, 10.0, family="opening"),
                           g("B", "feature", 10.0, 3.0, transition_in={"component": "transition.dim-through-ground@1", "dur": 1.0}),
                           g("Cc", "feature", c_at, 2.0)])


@control
def tv2_sem1(env: Env):
    film = make_film(env.films, "sem1", sem1_timeline(10.5))
    env.through(film)
    pos("TV-2 SEM-1 window", "TV-2#Cc.sem1" in ids(rows_of(film, "timed"), "blocking"), str(sorted(ids(rows_of(film, "timed")))))
    film = make_film(env.films, "sem1-neg", sem1_timeline(11.0))
    env.through(film)
    neg("TV-2 SEM-1 window", "TV-2#Cc.sem1" not in ids(rows_of(film, "timed")), str(sorted(ids(rows_of(film, "timed")))))


@control
def tv2_one_frame(env: Env):
    tin = {"component": "transition.dim-through-ground@1", "dur": 0.01}
    film = make_film(env.films, "oneframe", V(fix_c1, set_clip("S2", transition_in=tin)))
    env.through(film)
    r = next((x for x in rows_of(film, "timed") if x["id"] == "TV-2#S2.transition"), None)
    pos("TV-2 one-frame transition", r is not None and r["message_key"] == "tv2.one_frame", str(r and r["measured"]))
    film = make_film(env.films, "oneframe-neg", V(fix_c1, set_clip("S2", transition_in=dict(tin, dur=0.04))))
    env.through(film)
    neg("TV-2 one-frame transition (0.04 s = 1 frame)", "TV-2#S2.transition" not in ids(rows_of(film, "timed")))


def ov(cid, at, dur, z) -> dict:
    return {"id": cid, "role": "overlay", "at": at, "dur": dur, "z": z, "freedom": "guided",
            "device": {"family": "text-treatment"}, "motion_intent": [f"{cid} 淡入"]}


@control
def tv2_sem13(env: Env):
    film = make_film(env.films, "sem13", V(fix_c1, add_clip(ov("O1", 2.0, 3.0, 1), track="overlay"),
                                           add_clip(ov("O2", 4.0, 2.0, 1), track="overlay")))
    env.through(film)
    pos("TV-2 SEM-13", "TV-2#O2.sem13" in ids(rows_of(film, "timed"), "blocking"))
    film = make_film(env.films, "sem13-neg", V(fix_c1, add_clip(ov("O1", 2.0, 3.0, 1), track="overlay"),
                                               add_clip(ov("O2", 4.0, 2.0, 2), track="overlay"),
                                               add_clip(ov("O3", 3.0, 4.0, 3), track="overlay")))
    env.through(film)
    res = resolved_of(film)
    o3 = next(o for o in res["overlay"] if o["id"] == "O3")
    code, _, out = tlrun("at", film, "6.0", *env.common())
    lt = ((out.result or {}).get("lt") or {}).get("O3")
    neg("TV-2 SEM-13 (z 1 / z 2; overlay across S1->S2 keeps its own lt)",
        not any(x["id"].endswith(".sem13") for x in rows_of(film, "timed")) and abs(o3["t0"] - 3.0) < 1e-9
        and not any(e["clip"] == "O3" for e in res["extensions"]) and lt is not None and abs(lt - 3.0) < 1e-6,
        f"O3 t0 {o3['t0']} lt {lt}")


@control
def gap_fill(env: Env):
    film = make_film(env.films, "gapfill", V(set_clip("C1", dur=0.5), set_clip("S2", at=5.0)))
    code, lines, _ = env.through(film, "view")
    res = resolved_of(film)
    ext = res["extensions"]
    html = (film / "build" / "timeline.html").read_text(encoding="utf-8") if code == 0 else ""
    neg("gap fill D-T22 (no blocking; C1 +0.2 s listed, TV-19 info, page hatch)",
        (ext == [{"clip": "C1", "by_s": 0.2, "to_f": 150, "to": 5.0}] or (
            len(ext) == 1 and ext[0]["clip"] == "C1" and abs(ext[0]["by_s"] - 0.2) < 1e-6 and ext[0]["to_f"] == 150))
        and "TV-19#ext:C1" in ids(rows_of(film, "timed"), "info") and 'class="ext"' in html
        and not ids(rows_of(film, "timed"), "blocking"), f"{lines[0]}; ext {ext}")


@control
def anchors_pre_extension(env: Env):
    film = make_film(env.films, "preext", V(fix_c1, set_clip("E1", at={"anchor": "clip:S2.end", "offset": 0.5})))
    env.through(film, "resolve")
    res = resolved_of(film)
    pic = {p["id"]: p for p in res["picture"]}
    s2, e1 = pic["S2"], pic["E1"]
    real_ok = (s2["e_author_f"] == 387 and e1["t0_f"] == 402 and e1["e_f"] == 426 and res["n_frames"] == 486
               and len(res["extensions"]) == 1 and res["extensions"][0]["clip"] == "S2"
               and abs(res["extensions"][0]["by_s"] - 0.5) < 1e-6 and res["extensions"][0]["to_f"] == 402)
    double_t0_f = R.snapf(s2["e_f"] / 30 + 0.5, 30)  # a resolver that re-reads the extended end
    pos("anchors pre-extension: the re-reading double differs", double_t0_f != 402, f"double E1.t0_f {double_t0_f}")
    neg("anchors pre-extension: real resolver (Z-4, Y-2)", real_ok and e1["t0_f"] != double_t0_f,
        f"S2 e_author_f {s2['e_author_f']} E1 {e1['t0_f']}-{e1['e_f']} n {res['n_frames']} ext {res['extensions']}")


@control
def tv4b(env: Env):
    lib = make_lib(env.root / "lib-tv4b", base_components() + [
        comp("chapter-card.timed", roles=["chapter-card"], params={"card_s": P("number", source="clip_dur", max=1.0)})])
    def tl_(d):
        return V(set_clip("C1", dur=d, device={"component": "chapter-card.timed@1", "params": {}}),
                 set_clip("S2", at={"anchor": "clip:C1.end", "offset": 0.3}, transition_in=DEL))
    film = make_film(env.films, "tv4b", tl_(1.2))
    env.through(film, lib=lib)
    r = next((x for x in rows_of(film, "timed") if x["id"] == "TV-4b#C1"), None)
    pos("TV-4b reads d_author", r is not None and r["bucket"] == "blocking" and "1.2" in r["measured"], str(r and r["measured"]))
    film = make_film(env.films, "tv4b-neg", tl_(0.9))
    env.through(film, lib=lib)
    tr = rows_of(film, "timed")
    ext = resolved_of(film)["extensions"]
    neg("TV-4b judged on 0.9 though extended to 1.2", "TV-4b#C1" not in ids(tr) and "TV-19#ext:C1" in ids(tr, "info")
        and ext and abs(ext[0]["by_s"] - 0.3) < 1e-6, f"{sorted(ids(tr))} {ext}")


def whole_frame_ok(s: float, fps: int) -> bool:
    """filmkit-equivalent check: seconds x fps within 1e-6 of a whole frame (P-1)."""
    return abs(s * fps - round(s * fps)) <= 1e-6


@control
def whole_frames(env: Env):
    film = make_film(env.films, "wf", V(fix_c1, set_clip("E1", dur=0.766667)))
    env.through(film, "resolve")
    res = resolved_of(film)
    e1 = next(p for p in res["picture"] if p["id"] == "E1")
    secs = [res["film_end_s"]] + [p[k] for p in res["picture"] for k in ("t0", "e", "e_author")]
    secs += [res["tail_hold"]["t0"], res["tail_hold"]["t1"]] if res.get("tail_hold") else []
    secs += [ln[k] for ln in res["lines"] for k in ()]  # line times are unsnapped (6 decimals)
    double = round(res["film_end_s"], 6)
    pos("whole frames: rounded double rejected (P-1)", not whole_frame_ok(double, 30) and abs(double * 30 - 470) > 1e-6,
        f"{double} x 30 = {double * 30!r}")
    neg("whole frames: 470-frame variant", e1["e_author_f"] == 410 and res["n_frames"] == 470
        and abs(res["film_end_s"] * 30 - 470) <= 1e-6 and all(whole_frame_ok(s, 30) for s in secs),
        f"E1 e_author_f {e1['e_author_f']} n {res['n_frames']} end {res['film_end_s']!r}")
    film = make_film(env.films, "wf-fixed", V(fix_c1, set_clip("E1", dur=0.766667),
                                              set_meta(duration_policy="fixed", duration_s=15.666667)))
    code, lines, _ = env.through(film, "resolve")
    neg("whole frames: fixed 15.666667 accepted", code == 0 and resolved_of(film)["n_frames"] == 470, lines[0])


@control
def tail_hold(env: Env):
    film = make_film(env.films, "th-fixed", V(fix_c1, set_meta(duration_policy="fixed", duration_s=13.7)))
    code, lines, _ = env.through(film, "resolve")
    pos("tail hold: fixed 13.7 = e_last -> null", code == 0 and resolved_of(film)["tail_hold"] is None, lines[0])
    film = make_film(env.films, "th-fit", V(fix_c1))
    env.through(film, "resolve")
    th = resolved_of(film)["tail_hold"]
    neg("tail hold: fit + tail 2.0", th and abs(th["t0"] - 13.7) < 1e-6 and abs(th["t1"] - 15.7) < 1e-6, str(th))


@control
def tv7(env: Env):
    film = make_film(env.films, "tv7", V(fix_c1, set_meta(tail=5.8)))
    env.through(film)
    r = next((x for x in rows_of(film, "timed") if x["id"] == "TV-7#film"), None)
    pos("TV-7 tail 5.8", r is not None and r["bucket"] == "look" and r["measured"] == "5.8", str(r and r["measured"]))
    film = make_film(env.films, "tv7-neg", V(fix_c1))
    env.through(film)
    neg("TV-7 tail 2.0", "TV-7#film" not in ids(rows_of(film, "timed")))
    film = make_film(env.films, "tv7-h1", V(fix_c1, set_meta(tail=1.0),
                                            set_clip("E1", declares={"holds": [{"t0": 0.2, "t1": 0.6, "why": "停"}]})))
    env.through(film)
    r = next((x for x in rows_of(film, "timed") if x["id"] == "TV-7#film"), None)
    pos("TV-7 declared hold not at the end", r is not None and r["measured"] == "1", str(r and r["measured"]))
    film = make_film(env.films, "tv7-h2", V(fix_c1, set_meta(tail=1.0),
                                            set_clip("E1", declares={"holds": [{"t0": 0.2, "t1": 0.8, "why": "停"}]})))
    env.through(film)
    neg("TV-7 declared hold at the end -> 1.6", "TV-7#film" not in ids(rows_of(film, "timed")))


@control
def tv19(env: Env):
    film = make_film(env.films, "tv19-over", V(fix_c1, set_meta(duration_policy="fixed", duration_s=13.0)))
    env.through(film)
    pos("TV-19 fixed overrun", "TV-19#film" in ids(rows_of(film, "timed"), "blocking"))
    film = make_film(env.films, "tv19-ok", V(fix_c1, set_meta(duration_policy="fixed", duration_s=15.7)))
    env.through(film)
    neg("TV-19 fixed 15.7", "TV-19#film" not in ids(rows_of(film, "timed")))
    for pol in ("fit", "fixed"):
        muts = [fix_c1, set_clip("S2", dur=6.0)] + ([set_meta(duration_policy="fixed", duration_s=15.7)] if pol == "fixed" else [])
        film = make_film(env.films, f"tv19-l4-{pol}", V(*muts))
        env.through(film)
        res = resolved_of(film)
        pic = {p["id"]: p for p in res["picture"]}
        pos(f"TV-19 narration into the tail ({pol})", "TV-19#L4" in ids(rows_of(film, "timed"), "blocking")
            and pic["S2"]["e_f"] == 332 and pic["E1"]["e_f"] == 356, f"S2 e_f {pic['S2']['e_f']} E1 e_f {pic['E1']['e_f']}")
    film = make_film(env.films, "tv19-l4-neg", V(fix_c1))
    env.through(film)
    neg("TV-19 narration (base)", "TV-19#L4" not in ids(rows_of(film, "timed")))


def all_keyed(t: dict) -> None:
    """Every picture clip gets one key at 0.2 s (agent-review INV-R1)."""
    for c in t["tracks"]["picture"]:
        c["keys"] = [{"id": f"K-{c['id']}", "at": 0.2, "role": "key", "what": f"{c['id']} 讀得清楚"}]


@control
def kbt_keys(env: Env):
    film = make_film(env.films, "kbt-none", V(fix_c1))
    env.through(film)
    look = ids(rows_of(film, "timed"), "look")
    pos("TV-20 clip without a key", {"TV-20#S1", "TV-20#S2"} <= look, str(sorted(x for x in look if x.startswith("TV-20"))))
    neg("resolve writes no keys field when none are declared (BR-16)", "keys" not in resolved_of(film))
    film = make_film(env.films, "kbt-all", V(fix_c1, all_keyed))
    env.through(film)
    rows = rows_of(film, "timed")
    neg("TV-20 every clip keyed", not any(r["id"].startswith("TV-20") for r in rows))
    res = resolved_of(film)
    pic = {p["id"]: p for p in res["picture"]}
    k = {x["id"]: x for x in res.get("keys", [])}
    check("resolve key film time = clip t0 + at", "positive",
          "K-S2" in k and k["K-S2"]["t_f"] == pic["S2"]["t0_f"] + 6 and k["K-S2"]["clip"] == "S2",
          f"{k.get('K-S2')} vs S2 t0_f {pic['S2']['t0_f']}")
    film = make_film(env.films, "kbt-late", V(fix_c1, all_keyed,
                                               lambda t: clip_of(t, "E1")["keys"][0].__setitem__("at", 5.0)))
    env.through(film)
    pos("TV-2 key beyond d_author", "TV-2#E1.keys" in ids(rows_of(film, "timed"), "blocking"))


def free_timeline(free_s: float) -> dict:
    return plain_timeline([g("A", "opening", 0, 10.0 - free_s, family="opening"),
                           {"id": "B", "role": "feature", "at": {"anchor": "clip:A.end"}, "dur": free_s,
                            "freedom": "free", "motion_intent": ["自由段"]}])


@control
def tv10(env: Env):
    film = make_film(env.films, "tv10", free_timeline(4.0))
    env.through(film)
    pos("TV-10 free 40 %", "TV-10#film" in ids(rows_of(film, "timed"), "look"))
    film = make_film(env.films, "tv10-neg", free_timeline(1.0))
    env.through(film)
    neg("TV-10 free 10 %", "TV-10#film" not in ids(rows_of(film, "timed")))
    env.through(film, rules=env.root / "no-rules.json")
    r = next((x for x in rows_of(film, "timed") if x["id"] == "TV-10#film"), None)
    pos("TV-10 rules absent -> undetermined", r is not None and r["bucket"] == "undetermined", str(r and r["reason"]))


@control
def tv14(env: Env):
    film = make_film(env.films, "tv14", V(fix_c1, set_clip("S2", at=3.6)))
    env.through(film)
    pos("TV-14 window over L1", "TV-14#S2" in ids(rows_of(film, "timed"), "look"))
    film = make_film(env.films, "tv14-neg", V(fix_c1))
    env.through(film)
    neg("TV-14 base", not any(x["check"] == "TV-14" for x in rows_of(film, "timed")))


@control
def tv5(env: Env):
    film = make_film(env.films, "tv5", V(fix_c1, set_clip("S2", device={"family": "glitch"}, motion_intent=[])))
    env.static(film)
    pos("TV-5 stock family with []", "TV-5#S2" in ids(rows_of(film), "blocking"))
    film = make_film(env.films, "tv5-look", V(fix_c1, set_clip("S2", motion_intent=[])))
    env.static(film)
    pos("TV-5 non-stock with [] -> look", "TV-5#S2" in ids(rows_of(film), "look"))
    film = make_film(env.films, "tv5-neg", V(fix_c1, set_clip("S2", device={"family": "glitch"})))
    env.static(film)
    neg("TV-5 glitch with one intent line", "TV-5#S2" not in ids(rows_of(film)))


@control
def tv8(env: Env):
    film = make_film(env.films, "tv8", V(fix_c1, set_clip("S2", ground_exception={"color": "#000000"})))
    env.static(film)
    pos("TV-8 ground exception without why", "TV-8#S2" in ids(rows_of(film), "look"))
    film = make_film(env.films, "tv8-neg", V(fix_c1, set_clip("S2", ground_exception={"color": "#000000", "why": "夜景"})))
    env.static(film)
    neg("TV-8 with why -> info only", "TV-8#S2" in ids(rows_of(film), "info") and "TV-8#S2" not in ids(rows_of(film), "look"))


@control
def tv9a(env: Env):
    film = make_film(env.films, "tv9a", V(fix_c1, set_clip("S2", headline="支援 3 種格式"),
                                          lambda t: t["assets"][1].pop("portrays")))
    env.static(film)
    rs = rows_of(film)
    pos("TV-9a number without Claim -> look", "TV-9a#S2.headline" in ids(rs, "look"))
    pos("TV-9a no portrays -> row", "TV-9a#film" in ids(rs, "look"))
    film = make_valid(env, "tv9a-appr", V(fix_c1, set_clip("S2", headline="支援 3 種格式")), clips=S2_PROG, est=None)
    code, lines, out = approve(env, film)
    pos("TV-9a blocking at approve (listed by TV-18)", out.kind == "missing_required"
        and "TV-9a S2.headline" in out.message, lines[0])
    t = V(fix_c1, set_clip("S2", headline="支援 3 種格式", claims={"headline": "guide:支援 3 種格式"}),
          lambda t: t["assets"].append({"id": "guide", "kind": "data", "path": "assets/guide.md", "claims_ref": "assets/guide.md"}))
    film = make_film(env.films, "tv9a-neg", t, extra_files={"assets/guide.md": "支援 3 種格式\n".encode("utf-8")})
    env.static(film)
    neg("TV-9a claim present, portrays declared", not any(r["check"] == "TV-9a" for r in rows_of(film)))
    guide = {"id": "guide", "kind": "data", "path": "assets/guide.md", "claims_ref": "assets/guide.md"}
    t = V(fix_c1, set_clip("S2", headline="支援 3 種格式", claims={"headline": "guide:支援 99 種格式"}),
          lambda t: t["assets"].append(dict(guide)))
    film = make_film(env.films, "tv9a-fab", t, extra_files={"assets/guide.md": "支援 3 種格式\n".encode("utf-8")})
    env.static(film)
    pos("TV-9a fabricated claim text -> look", "TV-9a#S2.headline.source" in ids(rows_of(film), "look"))
    # The same fabricated text from the other two places a claim can sit: an overlay clip and a narration line.
    t = V(fix_c1, add_clip({"id": "O1", "role": "overlay", "at": 2.0, "dur": 1.5, "z": 1, "freedom": "guided",
                            "device": {"family": "text-treatment"}, "motion_intent": ["字幕條淡入"],
                            "headline": "支援 3 種格式", "claims": {"headline": "guide:支援 99 種格式"}}, track="overlay"),
          lambda t: t["assets"].append(dict(guide)))
    film = make_film(env.films, "tv9a-fab-ov", t, extra_files={"assets/guide.md": "支援 3 種格式\n".encode("utf-8")})
    env.static(film)
    pos("TV-9a fabricated overlay claim -> look", "TV-9a#O1.headline.source" in ids(rows_of(film), "look"))
    t = V(fix_c1, lambda t: t["tracks"]["narration"][1].update(text="支援 3 種格式", claim="guide:支援 99 種格式"),
          lambda t: t["assets"].append(dict(guide)))
    film = make_film(env.films, "tv9a-fab-nar", t, extra_files={"assets/guide.md": "支援 3 種格式\n".encode("utf-8")})
    env.static(film)
    pos("TV-9a fabricated narration claim -> look", "TV-9a#L2.source" in ids(rows_of(film), "look"))
    t = V(fix_c1, set_clip("S2", headline="支援 3 種格式", claims={"headline": "guide:支援 3 種 格式"}),
          lambda t: t["assets"].append(dict(guide)))
    film = make_film(env.films, "tv9a-norm", t, extra_files={"assets/guide.md": "- 支援 **3 種**\t格式。\n".encode("utf-8")})
    env.static(film)
    neg("TV-9a claim found after ** and whitespace folding", not any(r["check"] == "TV-9a" for r in rows_of(film)))
    t = V(fix_c1, set_clip("S2", headline="支援 3 種格式", claims={"headline": "guide:支援 3 種格式"}),
          lambda t: t["assets"].append(dict(guide)))
    film = make_film(env.films, "tv9a-nosrc", t)  # validate's TV-1 stops a missing file first; call TV-9a directly
    from _tl.validate_static import tv9a as tv9a_fn
    rs = tv9a_fn(json.loads((film / "film.timeline.json").read_text(encoding="utf-8")), stage="approve", film=film)
    pos("TV-9a unreadable claims_ref -> undetermined, not pass",
        any(r["id"] == "TV-9a#S2.headline.source" and r["bucket"] == "undetermined" for r in rs))
    film = make_valid(env, "tv9a-fab-appr", V(fix_c1, set_clip("S2", headline="支援 3 種格式",
                                                                claims={"headline": "guide:支援 99 種格式"}),
                                              lambda t: t["assets"].append(dict(guide))),
                      clips=S2_PROG, est=None, extra_files={"assets/guide.md": "支援 3 種格式\n".encode("utf-8")})
    code, lines, out = approve(env, film)
    pos("TV-9a fabricated claim blocking at approve", out.kind == "missing_required"
        and "TV-9a S2.headline" in out.message and "not found" in out.message, lines[0])
    # An unreadable source row carries `reason`, not `measured`; approve used to print "TV-9a S2.headline: None".
    # Validation stops a missing or non-UTF-8 source first, so approve meets this branch only when the
    # source goes away AFTER validation: a separate claims file, removed between the two steps.
    film = make_valid(env, "tv9a-unread-appr", V(fix_c1, set_clip("S2", headline="支援 3 種格式",
                                                                   claims={"headline": "guide:支援 3 種格式"}),
                                                 lambda t: t["assets"].append(dict(guide, claims_ref="assets/claims.md"))),
                      clips=S2_PROG, est=None,
                      extra_files={"assets/guide.md": "支援 3 種格式\n".encode("utf-8"),
                                   "assets/claims.md": "支援 3 種格式\n".encode("utf-8")})
    (film / "assets" / "claims.md").unlink()
    code, lines, out = approve(env, film)
    pos("TV-9a unreadable source at approve names why", out.kind == "missing_required"
        and "TV-9a S2.headline" in out.message and "unreadable" in out.message
        and "None" not in out.message, lines[0])
    film = make_film(env.films, "tv9a-expl", V(fix_c1, set_decision("film_type", "narrated-explainer"),
                                               set_clip("S2", headline="支援 3 種格式")))
    env.static(film)
    neg("TV-9a narrated-explainer without claims_ref", not any(r["check"] == "TV-9a" for r in rows_of(film)))


OPEN_PARAMS = {"source_asset": P("asset"), "name_asset": P("asset")}
S1_PARAMS = {"source_asset": "cap-sidebar", "name_asset": "dit-name"}


def tv3_lib(env: Env) -> Path:
    return make_lib(env.root / "lib-tv3", base_components() + [
        comp("opening.calm-only", energy=["calm"], roles=["opening"], params=OPEN_PARAMS),
        comp("opening.loud", energy=["lively", "hype"], roles=["opening"], params=OPEN_PARAMS),
        comp("opening.wrong-role", roles=["end-card"], params=OPEN_PARAMS),
        comp("transition.whoosh", energy=["hype"], roles=["transition"])])


def s1_ref(ref: str, **kw):
    return set_clip("S1", device={"component": ref, "params": dict(S1_PARAMS)}, **kw)


OVR_USER = {"why": "使用者要這個開場", "source": "user", "confirmed": "使用者 2026-10-11：可以", "date": "2026-10-11"}
OVR_MODEL = {"why": "模型覺得比較好", "source": "model", "date": "2026-10-11"}


@control
def tv3_table_a(env: Env):
    lib = tv3_lib(env)

    def st(name, *muts):
        film = make_film(env.films, name, V(fix_c1, *muts))
        env.static(film, lib=lib)
        return film, rows_of(film)

    _, rs = st("a2", set_clip("C1", device={"component": "chapter-card.verb@9", "params": {}}))
    r = next((x for x in rs if x["id"] == "TV-3#C1"), None)
    pos("TV-3 A2 not found lists same family", r is not None and r["bucket"] == "blocking"
        and "chapter-card.verb@1" in str(r["expected"]), str(r and r["expected"]))
    _, rs = st("a3", set_decision("energy", DEL), s1_ref("opening.calm-only@1"))
    r = next((x for x in rs if x["id"] == "TV-3#S1"), None)
    pos("TV-3 A3 energy unset + non-any", r is not None and r["message_key"] == "tv3.decide_first", str(r and r["measured"]))
    _, rs = st("a3-neg", set_decision("energy", DEL))
    neg("TV-3 A3 energy unset + any component passes", "TV-3#S1" not in ids(rs), str(sorted(ids(rs))))
    _, rs = st("a3-when", set_decision("energy", DEL), s1_ref("opening.wrong-role@1"))
    r = next((x for x in rs if x["id"] == "TV-3#S1"), None)
    pos("TV-3 A3 any component: when still judged", r is not None and r["bucket"] == "blocking" and "role" in r["measured"],
        str(r and r["measured"]))
    _, rs = st("a5", s1_ref("opening.loud@1", override=OVR_MODEL))
    r = next((x for x in rs if x["id"] == "TV-3#S1"), None)
    pos("TV-3 A5 source model override still blocks (TL-INV-5)", r is not None and r["bucket"] == "blocking"
        and r["message_key"] == "tv3.incompatible", str(r and r["measured"]))
    _, rs = st("a5-calm", s1_ref("opening.loud@1"))
    pos("TV-3 hype-side component in a calm film", "TV-3#S1" in ids(rs, "blocking"))
    _, rs = st("a5-lively", set_decision("energy", "lively"), s1_ref("opening.loud@1"))
    neg("TV-3 same component in a lively film", "TV-3#S1" not in ids(rs), str(sorted(ids(rs))))
    film, rs = st("a4", s1_ref("opening.loud@1", override=OVR_USER))
    v = json.loads((film / "build" / "validate.json").read_text(encoding="utf-8"))
    neg("TV-3 A4 source user + confirmed passes and is listed (TL-INV-5)",
        "TV-3#S1" in ids(rs, "info") and "TV-3#S1" not in ids(rs, "blocking")
        and [p["clip"] for p in v["pending_confirmation"]] == ["S1"], str(v["pending_confirmation"]))


@control
def tv3_transitions(env: Env):
    lib = tv3_lib(env)
    film = make_film(env.films, "tr-x2", V(fix_c1, set_clip("C1", transition_in={"component": "transition.whoosh@1", "dur": 0.3})))
    env.static(film, lib=lib)
    pos("TV-3 transition hype-only in a calm film (X-2)", "TV-3#C1.transition" in ids(rows_of(film), "blocking"))
    film = make_film(env.films, "tr-x2-neg", V(fix_c1, set_clip(
        "C1", transition_in={"component": "transition.dim-through-ground@1", "dur": 0.3})))
    env.static(film, lib=lib)
    neg("TV-3 compatible transition", "TV-3#C1.transition" not in ids(rows_of(film)))


@control
def tv4a(env: Env):
    extra = [comp("chapter-card.hold", roles=["chapter-card"], params={"hold_s": P("number", max=1.5)}),
             comp("chapter-card.timed", roles=["chapter-card"], params={"card_s": P("number", source="clip_dur", max=1.0)}),
             comp("end-card.needs", roles=["end-card"], requires=["motif.dots@1"])]
    lib_a = make_lib(env.root / "lib-tv4a", base_components() + extra)
    lib_b = make_lib(env.root / "lib-tv4a-b", base_components() + extra + [comp("motif.dots")])

    def st(name, lib, *muts):
        film = make_film(env.films, name, V(fix_c1, *muts))
        env.static(film, lib=lib)
        return rows_of(film)

    hold = lambda v: set_clip("C1", device={"component": "chapter-card.hold@1", "params": {"hold_s": v}})  # noqa: E731
    needs = set_clip("E1", device={"component": "end-card.needs@1", "params": {}})
    pos("TV-4a hold_s 2.0 > max 1.5", "TV-4a#C1.hold_s" in ids(st("4a-hold", lib_a, hold(2.0)), "blocking"))
    neg("TV-4a hold_s 1.0", "TV-4a#C1.hold_s" not in ids(st("4a-hold-neg", lib_a, hold(1.0))))
    pos("TV-4a requires missing", "TV-4a#E1:requires:motif.dots@1" in ids(st("4a-req", lib_a, needs), "blocking"))
    neg("TV-4a requires present", not any(x.startswith("TV-4a#E1") for x in ids(st("4a-req-neg", lib_b, needs))))
    rs = st("4a-cd", lib_a, set_clip("C1", device={"component": "chapter-card.timed@1", "params": {"card_s": 1.0}}))
    pos("TV-4a author writes a clip_dur param", "TV-4a#C1.card_s" in ids(rs, "blocking"))


@control
def tv15(env: Env):
    lib = tv3_lib(env)

    def st(name, src, *muts):
        film = make_film(env.films, name, V(fix_c1, *muts), clips={"S2": src})
        env.static(film, lib=lib)
        return film, rows_of(film)

    _, rs = st("15-out", 'TL.component("opening.shape-to-name@1");\n')
    pos("TV-15 uses a component outside S2.candidates", "TV-15#S2:opening.shape-to-name@1" in ids(rs, "blocking"))
    _, rs = st("15-tr", 'TL.component("ui-demo.cursor-click@1");\n',
               set_clip("S2", transition_in={"component": "transition.whoosh@1", "dur": 0.3}))
    pos("TV-15 transition outside S2.transition.candidates", "TV-15#S2.transition" in ids(rs, "blocking"))
    for name, src in (("template literal", "TL.component(`ui-demo.cursor-click@1`);\n"),
                      ("alias", "const c = TL.component;\nc(\"ui-demo.cursor-click@1\");\n"),
                      ("bracket access", 'TL["component"]("ui-demo.cursor-click@1");\n')):
        _, rs = st("15-" + name.split()[0], src)
        pos(f"TV-15 {name}", any(x.startswith("TV-15#S2:literal") for x in ids(rs, "blocking")), str(sorted(ids(rs))))
    film, rs = st("15-neg", 'TL.component("ui-demo.cursor-click@1");\n// TL.component("opening.shape-to-name@1")\n'
                            'const s = "TL.component(\'opening.shape-to-name@1\')";\n')
    v = json.loads((film / "build" / "validate.json").read_text(encoding="utf-8"))
    neg("TV-15 only candidates; comment and string ignored", not any(r["check"] == "TV-15" for r in rs)
        and v["uses"] == {"S2": ["ui-demo.cursor-click@1"]}, f"{sorted(ids(rs))} uses {v['uses']}")


@control
def a7_candidates(env: Env):
    film = make_film(env.films, "a7", V(fix_c1))
    env.static(film)
    p1, p2 = film / "build" / "clips" / "S2.candidates.json", film / "build" / "clips" / "S2.transition.candidates.json"
    ok = p1.is_file() and p2.is_file()
    c1 = json.loads(p1.read_text(encoding="utf-8")) if ok else {}
    c2 = json.loads(p2.read_text(encoding="utf-8")) if ok else {}
    neg("A7 guided clip -> both candidate files with decision_inputs",
        ok and [c["ref"] for c in c1["candidates"]] == ["ui-demo.cursor-click@1"]
        and [c["ref"] for c in c2["candidates"]] == ["transition.dim-through-ground@1"]
        and c1["decision_inputs"]["energy"] == "calm" and c1["decided_by"] == "A7", str(c1)[:200])
    empty = env.root / "lib-empty"
    empty.mkdir(exist_ok=True)
    (empty / "evidence.json").write_text('{"schema_version": 1, "entries": {}}\n', encoding="utf-8")
    idx, md = C.build_index(empty)
    C.write_index(empty, idx, md)
    film = make_film(env.films, "a7-empty", V(fix_c1))
    env.static(film, lib=empty)
    c1 = json.loads((film / "build" / "clips" / "S2.candidates.json").read_text(encoding="utf-8"))
    c2 = json.loads((film / "build" / "clips" / "S2.transition.candidates.json").read_text(encoding="utf-8"))
    neg("A7 empty library -> empty lists + note", c1["candidates"] == [] and c2["candidates"] == [] and c1["note"]
        and c2["note"], f"{c1['note']} / {c2['note']}")


def tl_sub(*args, env_extra: dict | None = None, path_empty: bool = False) -> tuple[int, list[str]]:
    e = dict(os.environ)
    e.update(env_extra or {})
    e["PYTHONDONTWRITEBYTECODE"] = "1"
    if path_empty:
        e["PATH"] = ""
    p = subprocess.run([sys.executable, "-X", "utf8", str(LIB / "tl.py"), *map(str, args)], capture_output=True,
                       text=True, encoding="utf-8", errors="replace", env=e, timeout=120)
    SCANNED_TEXT.append(("subprocess " + " ".join(map(str, args[:2])), p.stdout + p.stderr))
    if VERBOSE:
        print("    $ (sub) tl.py " + " ".join(map(str, args)) + f" -> {p.returncode}")
        for ln in p.stdout.splitlines():
            print("      " + ln)
    return p.returncode, p.stdout.splitlines()


@control
def tv17(env: Env):
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        SKIPPED.append(("TV-17", "ffmpeg not on PATH: cannot generate the 2 s test mp4"))
        return
    mp4 = env.root / "demo2s.mp4"
    if not mp4.is_file():
        subprocess.run([ffmpeg, "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=gray:s=64x64:d=2:r=30",
                        "-pix_fmt", "yuv420p", str(mp4)], check=True, timeout=60)
    data = mp4.read_bytes()

    def st(name, table, asset="demo"):
        t = V(fix_c1, set_clip("S2", speed={"asset": asset, "start_lt": 0, "table": table}),
              lambda t: t["assets"].append({"id": "demo", "kind": "capture", "path": "assets/demo.mp4"}))
        film = make_film(env.films, name, t, extra_files={"assets/demo.mp4": data})
        env.static(film)
        return film, rows_of(film)

    _, rs = st("17-hole", [[0, 1, 1], [1.2, 2, 1]])
    pos("TV-17 table with a hole", "TV-17#S2" in ids(rs, "look"))
    _, rs = st("17-long", [[0, 3, 1]])
    pos("TV-17 beyond the 2 s asset", "TV-17#S2" in ids(rs, "look"), str([r["measured"] for r in rs if r["id"] == "TV-17#S2"]))
    _, rs = st("17-png", [[0, 1, 1]], asset="cap-sidebar")
    pos("TV-17 speed.asset a PNG", "TV-17#S2" in ids(rs, "look"))
    film, rs = st("17-neg", [[0, 1, 1], [1, 2, 2]])
    neg("TV-17 contiguous within length", "TV-17#S2" not in ids(rs) and "TV-17#S2.length" not in ids(rs), str(sorted(ids(rs))))
    code, lines = tl_sub("validate", film, "--static", *env.common(), path_empty=True)
    rs = rows_of(film)
    r = next((x for x in rs if x["id"] == "TV-17#S2.length"), None)
    pos("TV-17 ffprobe absent -> length undetermined", r is not None and r["bucket"] == "undetermined", f"exit {code}; {lines[:1]}")


def appr_timeline(**kw) -> dict:
    return plain_timeline([
        lk("S1", "opening", 0, 3.0, "opening.shape-to-name@1", S1_PARAMS),
        g("S2", "feature", {"anchor": "clip:S1.end"}, 4.0,
          transition_in={"component": "transition.dim-through-ground@1", "dur": 0.3}),
        lk("E1", "end-card", {"anchor": "clip:S2.end"}, 1.0, "end-card.plain@1", transition_in="cut")], **kw)


S2_PROG = {"S2": 'TL.component("ui-demo.cursor-click@1");\n'}


def make_valid(env: Env, name: str, t: dict, *, lib=None, clips=S2_PROG, est=BASE_EST, extra_files=None) -> Path:
    film = make_film(env.films, name, t, clips=clips, est=est, extra_files=extra_files)
    code, lines, _ = env.through(film, lib=lib)
    st = json.loads((film / "state.json").read_text(encoding="utf-8"))
    if code != 0 or (st.get("draft") or {}).get("state") != "VALID":
        raise RuntimeError(f"fixture {name} did not reach VALID: {lines[0]} | {lines[2]}")
    return film


def approve(env: Env, film, by="user", lib=None, **kw):
    args = ["approve", film, "--by", by]
    if by == "user":
        args += ["--note", kw.get("note", "使用者看過頁面，同意這版時間軸")]
    if kw.get("questions"):
        args += ["--questions", kw["questions"]]
    return tlrun(*args, *env.common(lib=lib))


ST1 = {"id": "ST1", "facts": {"wheel_open": True, "slots": 5, "file_kind": "image"},
       "source": "lobby:drop-wheel.test.mjs#open"}


def with_states(*states):
    def m(t):
        t["product_state"] = [copy.deepcopy(s) for s in states]
    return m


@control
def tv20_22(env: Env):
    """Convergence design §3 rows: TV-20 product state coverage (opt-in), TV-21 ids and scalars, TV-22 placement."""
    # TV-20 known-false: a product film without the table keeps today's behaviour (one info row, nothing look).
    film = make_film(env.films, "tv20-none", V(fix_c1))
    env.static(film)
    rs = rows_of(film)
    neg("TV-20 no product_state -> info only", "TV-20#film" in ids(rs, "info")
        and not any(r["check"] == "TV-20" and r["bucket"] != "info" for r in rs))
    # TV-20 known-true: table declared, feature clip S2 names no state, state without source.
    film = make_film(env.films, "tv20-pos", V(fix_c1, with_states(dict(ST1, source=""))))
    env.static(film)
    rs = rows_of(film)
    pos("TV-20 feature without shows_state -> look", "TV-20#S2" in ids(rs, "look"))
    pos("TV-20 state without source -> look", "TV-20#state:ST1" in ids(rs, "look"))
    film = make_film(env.films, "tv20-neg", V(fix_c1, with_states(ST1), set_clip("S2", shows_state=["ST1"])))
    env.static(film)
    rs = rows_of(film)
    neg("TV-20/21 complete table -> no row", not any(r["check"] in ("TV-20", "TV-21") for r in rs),
        str([r["id"] for r in rs if r["check"] in ("TV-20", "TV-21")]))
    film = make_valid(env, "tv20-appr", V(fix_c1, with_states(ST1)), clips=S2_PROG, est=None)
    code, lines, out = approve(env, film)
    pos("TV-20 blocking at approve", out.kind == "missing_required" and "TV-20 S2" in out.message, lines[0])
    # TV-21: unknown state id; a fact that is not a scalar.
    film = make_film(env.films, "tv21-pos", V(fix_c1, with_states(dict(ST1, facts={"slots": [1, 2]})),
                                              set_clip("S2", shows_state=["ST9"])))
    env.static(film)
    rs = rows_of(film)
    pos("TV-21 unknown state -> blocking", "TV-21#S2.shows_state" in ids(rs, "blocking"))
    pos("TV-21 list fact -> blocking", "TV-21#state:ST1.slots" in ids(rs, "blocking"))
    # TV-22: a required asset nothing places vs the same asset named in a locked device's params.
    req = lambda t: t["assets"][0].__setitem__("required", {"min_visible_s": 2.0, "no_crop": True})
    film = make_film(env.films, "tv22-neg", V(fix_c1, req))
    env.static(film)
    neg("TV-22 asset in S1 device.params -> no row", not any(r["check"] == "TV-22" for r in rows_of(film)))
    lobby = {"assets/lobby.png": b"\x89PNG\r\n\x1a\nfixture-lobby"}
    film = make_film(env.films, "tv22-pos", V(fix_c1, lambda t: t["assets"].append(
        {"id": "lobby-cap", "kind": "capture", "path": "assets/lobby.png", "required": {"min_visible_s": 2.0}})),
        extra_files=lobby)
    env.static(film)
    pos("TV-22 unplaced required asset -> blocking", "TV-22#asset:lobby-cap" in ids(rows_of(film), "blocking"))
    film = make_film(env.films, "tv22-prefix", V(fix_c1, lambda t: t["assets"].append(
        {"id": "cap", "kind": "capture", "path": "assets/lobby.png", "required": {"min_visible_s": 2.0}})),
        extra_files=lobby)
    env.static(film)
    pos("TV-22 id only as a prefix of another id (cap-sidebar) -> still unplaced",
        "TV-22#asset:cap" in ids(rows_of(film), "blocking"))


@control
def tv18(env: Env):
    lib = tv3_lib(env)
    film = make_valid(env, "18-energy", appr_timeline(), clips=S2_PROG)
    t = read_timeline(film)
    t["decisions"].pop("energy")
    write_timeline(film, t)
    env.through(film)
    code, lines, out = approve(env, film)
    pos("TV-18 energy unset", out.kind == "missing_required" and "decision energy is unset" in out.message, lines[0])
    film = make_valid(env, "18-est", V(fix_c1), clips=S2_PROG)
    code, lines, out = approve(env, film)
    pos("TV-18 estimated line", out.kind == "missing_required" and "L1 duration is estimated" in out.message, lines[0])
    film = make_valid(env, "18-model", appr_timeline(), lib=lib, clips=S2_PROG)
    t = read_timeline(film)
    t["tracks"]["picture"][0]["device"]["component"] = "opening.loud@1"
    t["tracks"]["picture"][0]["override"] = OVR_USER
    write_timeline(film, t)
    env.through(film, lib=lib)
    (film / "build" / "questions.md").write_text("# 待確認\n- S1 的開場元件\n", encoding="utf-8")
    code, lines, out = approve(env, film, by="model", lib=lib, questions="build/questions.md")
    pos("TV-18 --by model with an A4 override", out.kind == "missing_required" and "S1 carries an override" in out.message,
        lines[0])
    film = make_valid(env, "18-prog", appr_timeline(), clips={})
    code, lines, out = approve(env, film)
    pos("TV-18 guided clip without its program", out.kind == "missing_required"
        and "S2 (guided) has no clip program" in out.message, lines[0])
    film = make_valid(env, "18-ok", appr_timeline())
    code, lines, out = approve(env, film)
    st = json.loads((film / "state.json").read_text(encoding="utf-8"))
    neg("TV-18 complete narration-free fixture -> APPROVED", code == 0 and st["draft"] is None
        and [v["state"] for v in st["versions"]] == ["APPROVED"], lines[0])
    env.approved_ok = film


def line1_lib(env: Env) -> Path:
    return make_lib(env.root / "lib-appr", base_components() + [
        comp("opening.loud", energy=["lively", "hype"], roles=["opening"], params=OPEN_PARAMS),
        comp("end-card.needs2", roles=["end-card"], requires=["motif.dots@1"]), comp("motif.dots")])


@control
def approve_line1_copies(env: Env):
    lib = line1_lib(env)
    t = plain_timeline([
        lk("S1", "opening", 0, 3.0, "opening.loud@1", S1_PARAMS, override=OVR_USER),
        {"id": "S2", "role": "feature", "at": {"anchor": "clip:S1.end"}, "dur": 4.0, "device": {"family": "ui-demo"},
         "motion_intent": ["游標點下"]},
        lk("E1", "end-card", {"anchor": "clip:S2.end"}, 1.0, "end-card.needs2@1", transition_in="cut")])
    film = make_valid(env, "line1", t, lib=lib)
    code, lines, out = approve(env, film, lib=lib)
    appr = json.loads((film / "versions" / "1" / "approval.json").read_text(encoding="utf-8")) if code == 0 else {}
    l1 = lines[0]
    neg("approve line 1 names override, open transition, hard cut, TV-6/TV-9b (Z-7c, Z-8)",
        code == 0 and "pending your confirmation: 1 override(s) [S1]" in l1 and "hard cuts: E1" in l1
        and "open transitions now cut: S2" in l1 and "not checked yet: TV-6, TV-9b" in l1
        and appr.get("undetermined") == ["TV-6", "TV-9b"] and appr.get("hard_cuts") == ["E1"]
        and [p["clip"] for p in appr.get("pending_confirmation", [])] == ["S1"], l1)
    vt = json.loads((film / "versions" / "1" / "timeline.json").read_text(encoding="utf-8")) if code == 0 else {}
    s2 = next((c for c in vt.get("tracks", {}).get("picture", []) if c["id"] == "S2"), {})
    neg("approve copies requires closure; freedom materialized (Z-9, X-11c)",
        (film / "versions" / "1" / "components" / "end-card" / "needs2.v1" / "component.json").is_file()
        and (film / "versions" / "1" / "components" / "motif" / "dots.v1" / "component.json").is_file()
        and s2.get("freedom") == "guided")
    env.approved_line1 = (film, lib)


@control
def inv6_versions(env: Env):
    film, lib = env.approved_line1
    vt = film / "versions" / "1" / "timeline.json"
    try:
        with open(vt, "ab") as f:
            f.write(b" ")
        fired = False
    except PermissionError:
        fired = True
    pos("TL-INV-6 version file is read-only", fired)
    os.chmod(vt, stat.S_IWRITE | stat.S_IREAD)
    vt.write_text(vt.read_text(encoding="utf-8").replace("游標點下", "游標點兩下"), encoding="utf-8")
    code, lines, out = env.view(film, lib=lib)
    pos("TL-INV-6 edited version -> fingerprint_mismatch naming the file", out.kind == "fingerprint_mismatch"
        and "versions/1/timeline.json" in out.message, lines[0])
    code, lines, out = env.view(env.approved_ok)
    neg("TL-INV-6 untouched version -> commands run", code == 0, lines[0])


@control
def tg16_interrupted_approve(env: Env):
    film = make_valid(env, "tg16", appr_timeline())
    code, lines, out = approve(env, film)
    neg("TG-16 normal approve -> no recovery note", code == 0 and "recovered" not in lines[4] and "unfinished" not in lines[4],
        lines[4])
    t = read_timeline(film)
    t["tracks"]["picture"][1]["what"] = "第二版：游標點下匯出"
    write_timeline(film, t)
    env.through(film)
    common = env.common()
    code, _ = tl_sub("approve", film, "--by", "user", "--note", "同意第二版", *common,
                     env_extra={"TL_SELFTEST_FAULT": "approve.after_tmp=exit"})
    killed_tmp = code == 137 and (film / "versions" / "2.tmp").is_dir()
    code, lines, out = env.view(film)
    pos("TG-16 kill after versions/2.tmp -> deleted with a note", killed_tmp and code == 0
        and "removed unfinished approval versions/2.tmp/" in lines[4] and not (film / "versions" / "2.tmp").exists(), lines[4])
    code, _ = tl_sub("approve", film, "--by", "user", "--note", "同意第二版", *common,
                     env_extra={"TL_SELFTEST_FAULT": "approve.after_rename=exit"})
    st0 = json.loads((film / "state.json").read_text(encoding="utf-8"))
    killed_rename = code == 137 and (film / "versions" / "2").is_dir() and [v["n"] for v in st0["versions"]] == [1]
    code, lines, out = env.view(film)
    st = json.loads((film / "state.json").read_text(encoding="utf-8"))
    pos("TG-16 kill after rename -> version 2 recovered APPROVED", killed_rename and code == 0
        and "approval recovered after interruption: version 2" in lines[4]
        and [(v["n"], v["state"]) for v in st["versions"]] == [(1, "APPROVED"), (2, "APPROVED")], lines[4])


@control
def currency(env: Env):
    film = make_film(env.films, "cur", appr_timeline(), clips=S2_PROG)
    env.through(film, "resolve")
    code, lines, out = env.timed(film)
    neg("currency unchanged inputs -> runs", code == 0, lines[0])
    t = read_timeline(film)
    t["tracks"]["picture"][1]["what"] = "改過"
    write_timeline(film, t)
    code, lines, out = env.timed(film)
    pos("currency edit after resolve -> not_current", out.kind == "not_current" and "validate --static" in (out.hint or ""),
        f"{lines[0]} | {out.hint}")
    code, lines, out = approve(env, film)
    pos("currency approve on a DRAFT -> not_current", out.kind == "not_current", lines[0])


@control
def made_by_stamp(env: Env):
    """works contract W-2: resolve and approve append a made_by row with the lab commit; an unchanged re-resolve adds none."""
    film = make_film(env.films, "mb", appr_timeline(), clips=S2_PROG)
    env.through(film, "resolve")
    rows = lambda: json.loads((film / "state.json").read_text(encoding="utf-8")).get("made_by", [])  # noqa: E731
    r1 = rows()
    pos("W-2 resolve -> one made_by row with a 40-hex lab commit", len(r1) == 1 and r1[0]["stage"] == "resolve"
        and len(r1[0].get("lab_commit") or "") == 40 and "timeline_nsha" in r1[0]["inputs"], json.dumps(r1)[:160])
    env.resolve(film)
    neg("W-2 re-resolve on unchanged inputs -> no new row", len(rows()) == 1, f"{len(rows())} rows")
    env.timed(film)
    code, lines, out = approve(env, film)
    r3 = rows()
    pos("W-2 approve -> a second row naming the version; row 1 unchanged", code == 0 and len(r3) == 2
        and r3[1]["stage"] == "approve" and r3[1]["inputs"].get("version") == 1 and r3[0] == r1[0], f"{lines[0]} | {len(r3)} rows")
    from _tl.state import W2_KEYS, stamp
    pos("W-2 every row carries every W-2 field (mount/model null without an arm)",
        all(set(W2_KEYS) <= set(r) for r in r3) and r3[1]["mount_sha"] is None, str(sorted(r3[1])))
    st = {"made_by": []}
    row = stamp(st, "arm", {}, cell="r99/A1", run={"mount_sha": "m" * 64, "canon_sha": "c" * 64,
                                                    "model_requested": "claude-opus-5-5", "effort": "medium"})
    pos("W-2 an arm's run.json fills model, effort, mount and canon", row["model"] == "claude-opus-5-5"
        and row["effort"] == "medium" and row["mount_sha"] == "m" * 64 and row["canon_sha"] == "c" * 64, str(row)[:160])


@control
def readback_versions(env: Env):
    """works contract W-5: readback lists what changed between two approved versions; a missing version refuses."""
    film = make_valid(env, "rb", appr_timeline())
    approve(env, film)
    t = read_timeline(film)
    t["tracks"]["picture"][1]["what"] = "作者改過的說明"
    write_timeline(film, t)
    env.through(film)
    code2, lines2, _ = approve(env, film, note="同意第二版")
    code, lines, out = tlrun("readback", film, "1", "2", *env.common())
    rec = (film / "作者修改紀錄.md").read_text(encoding="utf-8") if (film / "作者修改紀錄.md").is_file() else ""
    pos("W-5 readback 1 2 -> the edited clip's what is listed", code == 0 and code2 == 0
        and "S2.what" in rec and "作者改過的說明" in rec, f"{lines[0]} | {rec[-160:]}")
    code, lines, out = tlrun("readback", film, "1", "9", *env.common())
    neg("W-5 readback of a missing version -> refused, record unchanged", out.kind == "not_current"
        and (film / "作者修改紀錄.md").read_text(encoding="utf-8") == rec, lines[0])


@control
def state_transitions(env: Env):
    film = make_valid(env, "st-ab", appr_timeline())
    tlrun("mark", film, "--abandoned", "--note", "不要這版", *env.common())
    code, lines, out = tlrun("mark", film, "--abandoned", "--note", "再放棄一次", *env.common())
    pos("state: abandon an ABANDONED draft -> illegal_transition", out.kind == "illegal_transition", lines[0])
    film = make_valid(env, "st", appr_timeline())
    st = lambda: json.loads((film / "state.json").read_text(encoding="utf-8"))  # noqa: E731
    t = read_timeline(film)
    t["tracks"]["picture"][1]["what"] = "改一下"
    write_timeline(film, t)
    env.static(film)
    d1 = st()["draft"]
    env.resolve(film)
    env.timed(film)
    code, lines, out = approve(env, film)
    d2 = st()["draft"]
    t["tracks"]["picture"][1]["what"] = "再改一下"
    write_timeline(film, t)
    env.static(film)
    d3 = st()["draft"]
    neg("state: VALID -> edit -> DRAFT; approve -> null; edit -> n+1 parent 1",
        d1["state"] == "DRAFT" and d1["n"] == 1 and code == 0 and d2 is None and d3["n"] == 2 and d3["parent"] == 1,
        f"{d1['state']} {d2} {d3 and (d3['n'], d3['parent'])}")


@control
def page_view(env: Env):
    film = make_film(env.films, "pg-look", V(fix_c1, set_clip("S2", at=3.6)))
    code, lines, _ = env.through(film, "view")
    html = (film / "build" / "timeline.html").read_text(encoding="utf-8")
    band = html.split("擋件與要你看", 1)[1].split("</div>", 1)[0] if "擋件與要你看" in html else ""
    pos("page: a look row in the top band with its clip id", "S2" in band and "TV-14" in band, lines[0])
    film = make_film(env.films, "pg", V(fix_c1))
    code, lines, _ = env.through(film, "view")
    p = film / "build" / "timeline.html"
    html = p.read_text(encoding="utf-8")
    need = ["S1", "C1", "S2", "E1", "L1", "L2", "L3", "L4"]
    neg("page: ids present, dashed estimates, no URLs, dashboard class",
        all(f">{x}<" in html or f'"{x}"' in html or f"{x} " in html for x in need) and "blk ln est" in html
        and "http://" not in html and "https://" not in html and 'data-page-class="dashboard"' in html, lines[0])
    b1 = p.read_bytes()
    env.view(film)
    b2 = p.read_bytes()
    p.write_text(html.replace("S2", "S9"), encoding="utf-8")
    env.view(film)
    b3 = p.read_bytes()
    neg("TL-INV-9 regenerated page byte-identical; hand edit overwritten", b1 == b2 == b3)
    shutil.copyfile(p, env.root / "fixture-page.html")


@control
def inv7_index(env: Env):
    lib = make_lib(env.root / "lib-inv7", [comp("motif.carded", card="T02", card_tier="unverified"), comp("motif.bare")],
                   evidence={"motif.carded@1": {"state": "candidate", "measured": True},
                             "motif.bare@1": {"state": "candidate", "measured": True}})
    idx = json.loads((lib / "index.json").read_text(encoding="utf-8"))
    tiers = {c["ref"]: c["claim_tier"] for c in idx["components"]}
    pos("TL-INV-7 measured + card_tier unverified -> unverified", tiers.get("motif.carded@1") == "unverified", str(tiers))
    neg("TL-INV-7 card null -> own tier", tiers.get("motif.bare@1") == "measured", str(tiers))
    code, lines, _ = tlrun("index", "--check", "--components", lib)
    neg("index --check on a current index", code == 0, lines[0])
    (lib / "INDEX.md").write_text("stale\n", encoding="utf-8")
    code, lines, out = tlrun("index", "--check", "--components", lib)
    pos("index --check on a stale index -> exit 1", code == CM.EXIT_REFUSED and out.kind == "not_current", lines[0])


@control
def inv10_rules(env: Env):
    film = make_film(env.films, "inv10", V(fix_c1))
    missing = env.root / "no-rules.json"
    env.through(film, rules=missing)
    srows, trows = rows_of(film), rows_of(film, "timed")
    und = ids(srows, "undetermined") | ids(trows, "undetermined")
    pos("TL-INV-10 --rules <missing> -> TV-5/TV-7/TV-10 undetermined",
        {"TV-5#stock_devices", "TV-7#film", "TV-10#film"} <= und, str(sorted(und)))
    env.through(film)
    und = ids(rows_of(film), "undetermined") | ids(rows_of(film, "timed"), "undetermined")
    neg("TL-INV-10 fixture rules -> determined", not ({"TV-5#stock_devices", "TV-7#film", "TV-10#film"} & und), str(sorted(und)))
    from _tl.rules import DEFAULT_RULES
    tlrun("validate", film, "--static", "--components", env.lib)
    und = ids(rows_of(film), "undetermined")
    if DEFAULT_RULES.is_file():
        neg("TL-INV-10 lab rules file (default path) -> determined", "TV-5#stock_devices" not in und, str(DEFAULT_RULES))
    else:
        check("TL-INV-10 default rules absent (library copy) -> undetermined counted as expected", "expected",
              "TV-5#stock_devices" in und, f"{DEFAULT_RULES} absent")


@control
def tg17_paths(env: Env):
    film = make_film(env.films / "空白 路徑", "tg17", V(fix_c1))  # film_id = folder name; the parent carries the space + CJK
    code, lines, out = env.through(film, "view")
    neg("TG-17 space + CJK path: commands work, outputs use /",
        code == 0 and "空白 路徑/tg17" in lines[0] and "\\" not in "\n".join(lines) and "\\" not in json.dumps(out.outputs, ensure_ascii=False),
        lines[0])


HOLDER = r'''
import sys, time
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from _tl.lock import FilmLock
lk = FilmLock(Path(sys.argv[2]))
lk.__enter__()
print("held", flush=True)
sys.stdin.readline()
lk.__exit__(None, None, None)
print("released", flush=True)
'''


@control
def tg18_lock(env: Env):
    if not IS_WINDOWS:
        SKIPPED.append(("TG-18", "non-Windows: the byte-range lock helper is Windows-only (allowed skip)"))
        return
    holder = env.root / "holder.py"
    holder.write_text(HOLDER, encoding="utf-8")
    film = make_film(env.films, "lock", V(fix_c1))

    def start():
        p = subprocess.Popen([sys.executable, "-X", "utf8", str(holder), str(LIB), str(film)], stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE, text=True, encoding="utf-8")
        assert p.stdout.readline().strip() == "held"
        return p

    a = start()
    t0 = time.time()
    code, lines, out = env.static(film)
    pos("TG-18 lock held -> busy, nothing written", out.kind == "busy" and not (film / "build").exists()
        and not (film / "state.json").exists(), f"{lines[0]} ({time.time() - t0:.2f} s)")
    a.stdin.write("\n")
    a.stdin.flush()
    a.wait(10)
    code, lines, out = env.static(film)
    neg("TG-18 lock released -> runs", code == 0, lines[0])
    a = start()
    a.kill()
    a.wait(10)
    t0 = time.time()
    code, lines, out = env.static(film)
    el = time.time() - t0
    neg("TG-18 holder hard-killed -> acquired within 2 s", code == 0 and el < 2.0, f"{lines[0]} ({el:.2f} s)")


def br14_hits(folder: Path, numbers: list, strings: list) -> list[str]:
    import io
    import tokenize
    hits = []
    for p in sorted(Path(folder).glob("*.py")):
        src = p.read_text(encoding="utf-8")
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type == tokenize.NUMBER:
                try:
                    val = float(tok.string)
                except ValueError:
                    continue
                if any(val == float(n) for n in numbers):
                    hits.append(f"{p.name}:{tok.start[0]} number {tok.string}")
            elif tok.type == tokenize.STRING:
                try:
                    val = eval(tok.string, {"__builtins__": {}})  # noqa: S307 - literal only
                except Exception:  # noqa: BLE001
                    continue
                if isinstance(val, str) and val in strings:
                    hits.append(f"{p.name}:{tok.start[0]} string {tok.string}")
    return hits


@control
def br14_single_source(env: Env):
    from _tl.rules import DEFAULT_RULES
    tlp = dict(FIXTURE_RULES["params"]["timeline"])
    if DEFAULT_RULES.is_file():
        real = (json.loads(DEFAULT_RULES.read_text(encoding="utf-8")).get("params") or {}).get("timeline") or {}
        tlp.update({k: v for k, v in real.items() if k != "basis"})
    numbers = [v for v in tlp.values() if isinstance(v, (int, float)) and not isinstance(v, bool)]
    strings = [s for v in tlp.values() if isinstance(v, list) for s in v if isinstance(s, str)]
    fx = env.root / "br14-fixture"
    fx.mkdir(exist_ok=True)
    (fx / "bad.py").write_text("free_share_max = 0.3\n", encoding="utf-8")
    pos("BR-14 fixture literal found", bool(br14_hits(fx, numbers, strings)))
    hits = br14_hits(LIB / "_tl", numbers, strings)
    neg("BR-14 real _tl has no params.timeline literal", not hits, "; ".join(hits[:5]))


# PSM 5.1 TL-0 rows, plus readback (works contract W-5; ~/.claude/references/shared-design-layer-design.md WC-2 step 4)
TL0_SUBCOMMANDS = ["validate", "resolve", "view", "approve", "at", "mark", "readback", "index"]


@control
def help_list(env: Env):
    import argparse as ap
    have = tl.subcommands(tl.build_parser())
    neg("--help sub-command list equals PSM 5.1 TL-0 rows", have == TL0_SUBCOMMANDS, str(have))
    p = ap.ArgumentParser()
    sp = p.add_subparsers(dest="cmd")
    for n in TL0_SUBCOMMANDS:
        if n != "at":
            sp.add_parser(n)
    pos("--help fixture parser missing `at` fails", tl.subcommands(p) != TL0_SUBCOMMANDS)
    p = subprocess.run([sys.executable, "-X", "utf8", str(LIB / "tl.py"), "--help"], capture_output=True, text=True,
                       encoding="utf-8", timeout=60)
    m = re.search(r"\{([a-z,]+)\}", p.stdout)
    neg("--help printed list", p.returncode == 0 and m and m.group(1).split(",") == TL0_SUBCOMMANDS, p.stdout[:120])


@control
def manifest(env: Env):
    probs = NH.manifest_problems(LIB)
    neg("MANIFEST.txt complete", not probs, "; ".join(probs[:5]))
    cp = env.root / "manifest-copy"
    for rel in NH.read_manifest(LIB):
        (cp / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(LIB / rel, cp / rel)
    (cp / "_tl" / "stray.py").write_text("# unlisted\n", encoding="utf-8")
    pos("MANIFEST.txt unlisted file found", any("stray.py" in x for x in NH.manifest_problems(cp)))


def judgement_hits(text: str) -> list[str]:
    low = text.lower()
    return [w for w in CM.JUDGEMENT_WORDS_ZH if w in text] + [w for w in CM.JUDGEMENT_WORDS_EN if w in low]


@control
def inv8_words(env: Env):
    """Runs last: scans every stdout captured in this run and every text file the fixtures produced."""
    from _tl import messages_zh as MZ
    pos("TL-INV-8 fixture template containing 完成 fails the scan", bool(judgement_hits("\n".join({"x": "已完成"}.values()))))
    hits = []
    for k, v in MZ.MESSAGES.items():
        hits += [f"messages_zh {k}: {w}" for w in judgement_hits(v)]
    for where, text in SCANNED_TEXT:
        hits += [f"stdout {where}: {w}" for w in judgement_hits(text)]
    n_files = 0
    for p in env.films.rglob("*"):
        if p.is_file() and p.suffix in (".json", ".html", ".md") and "assets" not in p.parts:
            n_files += 1
            hits += [f"{p.relative_to(env.root).as_posix()}: {w}" for w in judgement_hits(p.read_text(encoding="utf-8"))]
    neg(f"TL-INV-8 {len(SCANNED_TEXT)} stdouts + {n_files} output files + message templates", not hits, "; ".join(hits[:5]))


# ---------------------------------------------------------------- main
def main(argv=None) -> int:
    global VERBOSE
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--only", default="")
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--list", action="store_true", help="print every control arm with its detail")
    ns = ap.parse_args(argv)
    VERBOSE = ns.verbose
    only = {x for x in ns.only.split(",") if x}
    root = Path(tempfile.mkdtemp(prefix="tl selftest 時間軸 "))
    t_start = time.time()
    try:
        env = Env(root)
        for fn in CONTROLS:
            if only and fn.__name__ not in only:
                continue
            try:
                fn(env)
            except Exception:  # noqa: BLE001
                check(fn.__name__, "run", False, "exception: " + traceback.format_exc().strip().splitlines()[-1])
                if VERBOSE:
                    traceback.print_exc()
    finally:
        if not ns.keep:
            CM.rmtree_force(root)
        else:
            print(f"kept fixtures: {root}")
    if ns.list:
        for r in RESULTS:
            print(f"  {'pass' if r['ok'] else 'FAIL'} [{r['arm']}] {r['control']} :: {r['detail']}")
    fails = [r for r in RESULTS if not r["ok"]]
    fired = sum(1 for r in RESULTS if r["arm"] == "positive" and r["ok"])
    print(f"timeline selftest: {len(RESULTS) - len(fails)} pass, {len(fails)} fail, {len(SKIPPED)} skipped; "
          f"positive arms fired: {fired} ({time.time() - t_start:.1f} s)")
    for name, why in SKIPPED:
        print(f"  skipped {name}: {why}")
    for r in fails:
        print(f"  FAIL {r['control']} [{r['arm']}] {r['detail']}")
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())

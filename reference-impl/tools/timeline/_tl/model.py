"""Load and validate film.timeline.json (PSM 4.1; TV-1 static rows). Agrees with film.timeline.schema.json."""
from __future__ import annotations

import re
from pathlib import Path

from . import timeref as tr
from .common import SpecInvalid, read_json, row
from .defaults import WHOLE_FRAME_TOL
from .messages_zh import zh
from .rules import Rules

FILM_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")
SIZE_RE = re.compile(r"^[0-9]+x[0-9]+$")
ASSET_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,39}$")
CLIP_ID_RE = re.compile(r"^[A-Z][A-Za-z0-9-]{0,15}$")
KEY_ID_RE = re.compile(r"^K[A-Za-z0-9-]{1,15}$")
KEY_ROLES = ("key", "breakdown")
LINE_ID_RE = re.compile(r"^L[0-9]{1,3}$")
REF_RE = re.compile(r"^[a-z0-9-]+\.[a-z0-9-]+@[0-9]+$")
CLAIM_RE = re.compile(r"^([a-z0-9][a-z0-9._-]{0,39}):(.+)$")
HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
DATE_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
SLUG_RE = re.compile(r"^[a-z0-9-]{1,40}$")

TOP_KEYS = {"meta", "decisions", "assets", "tracks", "product_state"}
META_KEYS = {"schema_version", "film_id", "format", "lead", "tail", "line_gap", "section_gap"}
FORMAT_KEYS = {"size", "fps", "duration_policy", "duration_s"}
DECISION_KEYS = ("film_type", "audience", "energy", "rhythm_source", "remember_one", "ground", "voice",
                 "presentation", "purpose", "shown_where", "viewer_action")
REQUIRED_DECISIONS = ("film_type", "audience", "energy", "rhythm_source")
ENERGY = ("calm", "lively", "hype")
RHYTHM = ("narration", "content")
ASSET_KINDS = ("capture", "logo", "font", "music", "image", "data")
ASSET_KEYS = {"id", "kind", "path", "sha256", "license", "claims_ref", "portrays", "required"}
STATE_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,23}$")
TRACK_KEYS = {"picture", "overlay", "narration", "music", "sfx", "captions"}
ROLES = ("opening", "feature", "chapter-card", "end-card", "interlude")
FREEDOMS = ("locked", "guided", "free")
FAMILIES = ("opening", "chapter-card", "end-card", "feature-frame", "ui-demo", "data-viz", "text-treatment",
            "transition", "camera", "background", "motif", "caption")
CAMERA_GOALS = ("lead-eye", "section-change", "show-product", "opening-in", "ambience", "none")
CAMERA_METHODS = ("stage-2d", "card-3d", "scene-3d", "single-layer", "footage")
INTENT_KINDS = ("cut_on_line", "cut_on_bar", "end_hold", "ground_locked", "claims_traceable")
TEXT_FIELDS = ("headline", "visual", "data", "layout", "what")
CLIP_KEYS = {"id", "role", "at", "dur", "motion_intent", "freedom", "device", "transition_in", *TEXT_FIELDS,
             "claims", "camera", "ref_seg", "ref_what", "evidence", "override", "declares", "ground_exception",
             "speed", "intents", "keys", "shows_state"}
OVERLAY_KEYS = (CLIP_KEYS - {"transition_in", "speed"}) | {"z"}
LINE_KEYS = {"id", "text", "say", "asr", "section", "gap_after", "claim"}
SFX_KEYS = {"at", "sound", "gain_db", "why", "target"}
VIDEO_EXT = (".mp4", ".mov", ".webm", ".mkv")

BASIS = "PSM 4.1 / TV-1"


def is_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def is_int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def nonempty_str(v) -> bool:
    return isinstance(v, str) and v.strip() != ""


class _V:
    """Row collector for TV-1."""

    def __init__(self):
        self.rows: list[dict] = []
        self._seen: set[str] = set()
        self.key_ids: set[str] = set()

    def add(self, where: str, key: str, measured, expected, *, fmt: dict | None = None, basis: str = BASIS):
        rid = f"TV-1#{where}"
        n = 2
        while rid in self._seen:
            rid = f"TV-1#{where}~{n}"
            n += 1
        self._seen.add(rid)
        fmt = dict(fmt or {})
        fmt.setdefault("clip", where)
        fmt.setdefault("detail", measured)
        self.rows.append(row("TV-1", where, "blocking", stage="static", measured=measured, expected=expected,
                             basis=basis, message_key=key, message=zh(key, **fmt), rid=rid))

    def schema(self, where: str, measured: str, expected: str):
        self.add(where, "tv1.schema", measured, expected, fmt={"detail": f"{where}: {measured}（應為 {expected}）"})

    def keys(self, where: str, obj: dict, allowed: set):
        extra = sorted(set(obj) - allowed)
        if extra:
            self.schema(where, f"unknown key(s) {extra}", f"keys among {sorted(allowed)}")


def _asset_path_ok(p) -> str | None:
    if not isinstance(p, str):
        return "not a string"
    if "\\" in p:
        return "uses a backslash (write forward slashes)"
    if not p.startswith("assets/"):
        return "does not start with assets/"
    if ".." in p.split("/"):
        return "contains '..'"
    if p.endswith("/"):
        return "names a folder"
    return None


def _claim(v: _V, where: str, c, asset_ids: set):
    m = CLAIM_RE.match(c) if isinstance(c, str) else None
    if not m:
        v.schema(where, repr(c), "\"<asset id>:<locator>\"")
    elif m.group(1) not in asset_ids:
        v.add(where, "tv1.anchor_target", f"claim names unknown asset {m.group(1)!r}", "an asset id of assets[]")


# ---------------------------------------------------------------- top-level validator
def validate_timeline(obj, *, rules: Rules | None, film_id: str | None = None, info: dict | None = None) -> list[dict]:
    """TV-1 rows for a parsed timeline. `film_id` = folder name when known. `info` receives
    defaults_applied, decisions_unset and notes."""
    v = _V()
    info = info if info is not None else {}
    info.setdefault("defaults_applied", [])
    info.setdefault("decisions_unset", [])
    info.setdefault("notes", [])
    if not isinstance(obj, dict):
        v.schema("film", type(obj).__name__, "a JSON object")
        return v.rows
    v.keys("film", obj, TOP_KEYS)
    for k in ("meta", "tracks"):
        if k not in obj:
            v.schema("film", f"missing {k}", f"{k} present")

    meta = obj.get("meta") if isinstance(obj.get("meta"), dict) else {}
    if "meta" in obj and not isinstance(obj.get("meta"), dict):
        v.schema("meta", "not an object", "an object")
    policy, fps = _meta(v, meta, film_id)

    asset_ids = _assets(v, obj.get("assets", []))
    _product_state(v, obj.get("product_state"))
    _decisions(v, obj.get("decisions", {}), rules, info)

    tracks = obj.get("tracks") if isinstance(obj.get("tracks"), dict) else {}
    if "tracks" in obj and not isinstance(obj.get("tracks"), dict):
        v.schema("tracks", "not an object", "an object")
    v.keys("tracks", tracks, TRACK_KEYS)
    picture = tracks.get("picture", [])
    overlay = tracks.get("overlay", [])
    narration = tracks.get("narration", [])
    sfx = tracks.get("sfx", [])
    if "tracks" in obj and "picture" not in tracks:
        v.schema("tracks", "missing picture", "picture: an array of >= 1 clip")
    if not isinstance(picture, list) or ("picture" in tracks and len(picture) < 1):
        v.schema("tracks.picture", "empty or not an array", "an array of >= 1 clip")
        picture = picture if isinstance(picture, list) else []
    for name, val in (("overlay", overlay), ("narration", narration), ("sfx", sfx)):
        if not isinstance(val, list):
            v.schema(f"tracks.{name}", "not an array", "an array")
    overlay = overlay if isinstance(overlay, list) else []
    narration = narration if isinstance(narration, list) else []
    sfx = sfx if isinstance(sfx, list) else []
    if tracks.get("music") is not None:
        v.add("tracks.music", "tv1.tl4", "music track is not null", "null until TL-4",
              fmt={"detail": "spec_invalid: music track arrives in TL-4"})
    cap = tracks.get("captions")
    if cap is not None:
        if not isinstance(cap, dict) or set(cap) != {"from", "style"} or cap.get("from") != "narration" \
                or not (isinstance(cap.get("style"), str) and REF_RE.match(cap["style"])):
            v.schema("tracks.captions", repr(cap), "null or {from: \"narration\", style: \"<family>.<name>@<v>\"}")

    stock = rules.timeline.get("stock_devices") if rules and isinstance(rules.timeline.get("stock_devices"), list) else None
    clip_ids: dict[str, str] = {}
    for kind, arr in (("picture", picture), ("overlay", overlay)):
        for i, c in enumerate(arr):
            _clip(v, c, kind, i, clip_ids, asset_ids, stock, info)
    line_ids = _lines(v, narration, asset_ids)
    pic_ids = [c.get("id") for c in picture if isinstance(c, dict)]
    _references(v, picture, overlay, narration, sfx, clip_ids, line_ids, pic_ids, policy)
    _sfx(v, sfx, clip_ids, line_ids, policy)
    return v.rows


def _meta(v: _V, meta: dict, film_id: str | None):
    v.keys("meta", meta, META_KEYS)
    if meta.get("schema_version") != 1:
        v.schema("meta.schema_version", repr(meta.get("schema_version")), "1")
    fid = meta.get("film_id")
    if not (isinstance(fid, str) and FILM_ID_RE.match(fid)):
        v.schema("meta.film_id", repr(fid), "^[a-z0-9][a-z0-9-]{0,39}$")
    elif film_id is not None and fid != film_id:
        v.add("meta.film_id", "tv1.film_id", f"{fid} vs folder {film_id}", "film_id equal to the folder name")
    fmt = meta.get("format")
    policy, fps = None, None
    if not isinstance(fmt, dict):
        v.schema("meta.format", repr(fmt), "an object {size, fps, duration_policy, duration_s?}")
        return policy, fps
    v.keys("meta.format", fmt, FORMAT_KEYS)
    size = fmt.get("size")
    if not (isinstance(size, str) and SIZE_RE.match(size)):
        v.schema("meta.format.size", repr(size), "WxH")
    else:
        w, h = (int(x) for x in size.split("x"))
        if w % 2 or h % 2 or w < 16 or h < 16:
            v.schema("meta.format.size", size, "both sides even and >= 16")
    fps = fmt.get("fps")
    if not (is_int(fps) and 1 <= fps <= 120):
        v.schema("meta.format.fps", repr(fps), "an integer 1-120")
        fps = None
    policy = fmt.get("duration_policy")
    if policy not in ("fit", "fixed"):
        v.schema("meta.format.duration_policy", repr(policy), "fit | fixed")
        policy = None
    ds = fmt.get("duration_s")
    if policy == "fixed":
        if ds is None:
            v.schema("meta.format.duration_s", "missing under fixed", "a number > 0 (required iff fixed)")
        elif not (is_num(ds) and ds > 0):
            v.schema("meta.format.duration_s", repr(ds), "a number > 0")
        elif fps and abs(ds * fps - round(ds * fps)) > WHOLE_FRAME_TOL:
            v.add("meta.format.duration_s", "tv1.whole_frames", f"{ds} s at {fps} fps = {ds * fps:.4f} frames",
                  "a whole number of frames", fmt={"detail": f"{ds}"})
    elif policy == "fit" and ds is not None:
        v.schema("meta.format.duration_s", "present under fit", "absent (forbidden iff fit)")
    for k in ("lead", "tail", "line_gap", "section_gap"):
        if k in meta and not (is_num(meta[k]) and meta[k] >= 0):
            v.schema(f"meta.{k}", repr(meta[k]), "a number >= 0")
    return policy, fps


def _assets(v: _V, assets) -> set:
    ids: set = set()
    if not isinstance(assets, list):
        v.schema("assets", "not an array", "an array")
        return ids
    paths: dict[str, str] = {}
    for i, a in enumerate(assets):
        where = f"assets[{i}]"
        if not isinstance(a, dict):
            v.schema(where, "not an object", "an asset object")
            continue
        v.keys(where, a, ASSET_KEYS)
        aid = a.get("id")
        if isinstance(aid, str) and ASSET_ID_RE.match(aid):
            if aid in ids:
                v.schema(f"asset:{aid}", "duplicate asset id", "unique ids")
            ids.add(aid)
            where = f"asset:{aid}"
        else:
            v.schema(where, f"id {aid!r}", "^[a-z0-9][a-z0-9._-]{0,39}$")
        if a.get("kind") not in ASSET_KINDS:
            v.schema(where, f"kind {a.get('kind')!r}", " | ".join(ASSET_KINDS))
        bad = _asset_path_ok(a.get("path"))
        if bad:
            v.schema(where, f"path {a.get('path')!r} {bad}", "a path under assets/ with forward slashes")
        else:
            k = a["path"].casefold()
            if k in paths and paths[k] != a["path"]:
                v.add(where, "tv1.asset", f"paths differ only by case: {paths[k]} / {a['path']}",
                      "paths unique case-insensitively (TG-8)",
                      fmt={"detail": f"spec_invalid: 路徑只差大小寫 {paths[k]} / {a['path']}"})
            elif k in paths:
                v.schema(where, f"path {a['path']} listed twice", "one asset per file")
            paths.setdefault(k, a["path"])
        if "sha256" in a and not (isinstance(a["sha256"], str) and HEX64_RE.match(a["sha256"])):
            v.schema(where, "sha256 not 64 lowercase hex", "64 hex")
        if "license" in a and not isinstance(a["license"], str):
            v.schema(where, "license not a string", "a string")
        if "claims_ref" in a:
            bad = _asset_path_ok(a["claims_ref"])
            if bad:
                v.schema(where, f"claims_ref {bad}", "a path under assets/")
        if "portrays" in a:
            p = a["portrays"]
            if not (isinstance(p, dict) and p and set(p) <= {"subject_name", "subject_logo"}
                    and all(nonempty_str(x) for x in p.values())):
                v.schema(where, f"portrays {p!r}", "{subject_name: str} or {subject_logo: str}")
        if "required" in a:
            r = a["required"]
            ok = isinstance(r, dict) and set(r) <= {"min_visible_s", "no_crop"}                 and ("min_visible_s" not in r or (is_num(r["min_visible_s"]) and r["min_visible_s"] > 0))                 and ("no_crop" not in r or isinstance(r["no_crop"], bool))
            if not ok:
                v.schema(where, f"required {r!r}", "{min_visible_s?: number > 0, no_crop?: bool}")
    return ids


def _product_state(v: _V, ps):
    """Shape only (convergence design §3); ids referenced and fact values are TV-21, completeness TV-20."""
    if ps is None:
        return
    if not isinstance(ps, list):
        v.schema("product_state", "not an array", "[{id, facts, source}]")
        return
    seen = set()
    for i, st in enumerate(ps):
        where = f"product_state[{i}]"
        if not isinstance(st, dict):
            v.schema(where, "not an object", "{id, facts, source}")
            continue
        v.keys(where, st, {"id", "facts", "source"})
        sid = st.get("id")
        if not (isinstance(sid, str) and STATE_ID_RE.match(sid)):
            v.schema(where, f"id {sid!r}", "^[A-Za-z][A-Za-z0-9_-]{0,23}$")
        elif sid in seen:
            v.schema(f"state:{sid}", "duplicate state id", "unique ids")
        else:
            seen.add(sid)
        if "facts" in st and not isinstance(st["facts"], dict):
            v.schema(where, "facts not an object", "{\"<fact>\": value}")
        if "source" in st and not isinstance(st["source"], str):
            v.schema(where, "source not a string", "a string")


def _decisions(v: _V, d, rules: Rules | None, info: dict):
    if not isinstance(d, dict):
        v.schema("decisions", "not an object", "an object")
        d = {}
    v.keys("decisions", d, set(DECISION_KEYS))
    for k in DECISION_KEYS:
        if k not in d:
            if k in REQUIRED_DECISIONS:
                info["decisions_unset"].append(k)
            continue
        where = f"decisions.{k}"
        e = d[k]
        if not isinstance(e, dict):
            v.schema(where, repr(e), "{value, source, evidence?}")
            continue
        v.keys(where, e, {"value", "source", "evidence"})
        if e.get("source") not in ("user", "model", "default"):
            v.schema(where, f"source {e.get('source')!r}", "user | model | default")
        if "evidence" in e and not isinstance(e["evidence"], str):
            v.schema(where, "evidence not a string", "a string")
        val = e.get("value")
        if k == "film_type":
            if not (isinstance(val, str) and SLUG_RE.match(val)):
                v.schema(where, repr(val), "a film-type slug")
            elif rules is not None and rules.film_types is not None:
                if val not in rules.film_types:
                    v.add(where, "tv1.film_type", f"{val} not in {rules.film_types}",
                          "a film type of the rules file", fmt={"detail": val})
            else:
                info["notes"].append("film-type vocabulary unavailable: rules file not present")
        elif k == "energy":
            if val not in ENERGY:
                v.schema(where, repr(val), " | ".join(ENERGY))
        elif k == "rhythm_source":
            if val == "music-bar":
                v.add(where, "tv1.tl4", "rhythm_source music-bar", "narration | content before TL-4",
                      fmt={"detail": "spec_invalid: music-bar anchors arrive in TL-4"})
            elif val not in RHYTHM:
                v.schema(where, repr(val), " | ".join(RHYTHM))
        elif k == "voice":
            if val not in ("marketing", "light-technical"):
                v.schema(where, repr(val), "marketing | light-technical")
        elif k == "presentation":
            if val not in ("paged", "continuous-stage"):
                v.schema(where, repr(val), "paged | continuous-stage")
        elif k == "ground":
            if not (isinstance(val, str) and HEX_RE.match(val)):
                v.schema(where, repr(val), "#RRGGBB")
        elif not nonempty_str(val):
            v.schema(where, repr(val), "a non-empty string")


def _intervals(v: _V, where: str, arr):
    if not isinstance(arr, list):
        v.schema(where, "not an array", "an array of {t0, t1, why}")
        return
    for j, it in enumerate(arr):
        w = f"{where}[{j}]"
        if not isinstance(it, dict):
            v.schema(w, "not an object", "{t0, t1, why}")
            continue
        v.keys(w, it, {"t0", "t1", "why"})
        t0, t1 = it.get("t0"), it.get("t1")
        if not (is_num(t0) and is_num(t1) and 0 <= t0 < t1):
            v.schema(w, f"t0={t0!r} t1={t1!r}", "0 <= t0 < t1")
        if not nonempty_str(it.get("why")):
            v.schema(w, "missing why", "a non-empty why")


def _clip(v: _V, c, kind: str, i: int, clip_ids: dict, asset_ids: set, stock, info: dict):
    where0 = f"tracks.{kind}[{i}]"
    if not isinstance(c, dict):
        v.schema(where0, "not an object", "a clip object")
        return
    cid = c.get("id")
    if isinstance(cid, str) and CLIP_ID_RE.match(cid):
        if cid in clip_ids:
            v.schema(cid, "duplicate clip id", "ids unique across picture and overlay")
        clip_ids.setdefault(cid, kind)
        where = cid
    else:
        v.schema(where0, f"id {cid!r}", "^[A-Z][A-Za-z0-9-]{0,15}$")
        where = where0
    v.keys(where, c, CLIP_KEYS if kind == "picture" else OVERLAY_KEYS)
    role = c.get("role")
    if kind == "picture" and role not in ROLES:
        v.schema(where, f"role {role!r}", " | ".join(ROLES))
    if kind == "overlay":
        if role != "overlay":
            v.schema(where, f"role {role!r}", "overlay")
        z = c.get("z")
        if not (is_int(z) and z >= 1):
            v.schema(where, f"z {z!r}", "an integer >= 1")
    if "at" not in c:
        v.add(where, "tv1.missing_at", "missing at", "at (TimeRef)")
    else:
        try:
            tr.parse_timeref(c["at"])
        except tr.GrammarError as e:
            _grammar(v, where, "at", e)
    if "dur" not in c:
        v.add(where, "tv1.missing_dur", "missing dur", "dur (number | end anchor | lines)")
    else:
        try:
            tr.parse_dur(c["dur"])
        except tr.GrammarError as e:
            _grammar(v, where, "dur", e)
    if "motion_intent" not in c:
        v.add(where, "tv1.missing_motion_intent", "missing motion_intent key", "motion_intent: [] or lines")
    elif not (isinstance(c["motion_intent"], list) and all(isinstance(x, str) for x in c["motion_intent"])):
        v.schema(where, "motion_intent not an array of strings", "an array of strings")

    freedom = c.get("freedom")
    dev = c.get("device")
    if freedom is None:
        if isinstance(dev, dict) and "component" in dev:
            v.schema(where, "device.component without freedom", "write freedom: locked")
        else:
            info["defaults_applied"].append(f"{cid}.freedom=guided")
            freedom = "guided"
    elif freedom not in FREEDOMS:
        v.schema(where, f"freedom {freedom!r}", " | ".join(FREEDOMS))
    if freedom == "locked":
        if not (isinstance(dev, dict) and set(dev) <= {"component", "params"} and isinstance(dev.get("component"), str)
                and REF_RE.match(dev["component"]) and isinstance(dev.get("params", {}), dict)):
            v.schema(where, f"device {dev!r}", "{component: \"<family>.<name>@<v>\", params: {}} under locked")
    elif freedom == "guided":
        fam = dev.get("family") if isinstance(dev, dict) else None
        if not (isinstance(dev, dict) and set(dev) <= {"family", "tone"} and isinstance(fam, str)):
            v.schema(where, f"device {dev!r}", "{family, tone?} under guided")
        elif fam not in FAMILIES and not (stock and fam in stock) and not (stock is None and SLUG_RE.match(fam)):
            v.schema(where, f"device.family {fam!r}", "a family of design 7.4 or a stock device")
        if isinstance(dev, dict) and "tone" in dev:
            t = dev["tone"]
            tl = t if isinstance(t, list) else [t]
            if not tl or any(x not in ENERGY for x in tl):
                v.schema(where, f"device.tone {t!r}", "energy value(s)")
    elif freedom == "free" and dev is not None:
        v.schema(where, "device present under free", "no device under free")

    if "transition_in" in c and kind == "picture":
        t = c["transition_in"]
        ok = t == "cut" or (isinstance(t, dict) and set(t) == {"component", "dur"} and isinstance(t.get("component"), str)
                            and REF_RE.match(t["component"]) and is_num(t.get("dur")) and t["dur"] > 0)
        if not ok:
            v.schema(where, f"transition_in {t!r}", "\"cut\" or {component: \"<ref>\", dur: number > 0}")
        elif isinstance(t, dict) and is_num(c.get("dur")) and t["dur"] > c["dur"]:
            v.add(where, "tv1.tdur", f"tdur {t['dur']} > dur {c['dur']}", "0 < tdur <= dur",
                  fmt={"detail": f"{t['dur']} > {c['dur']}"})
    for f in TEXT_FIELDS + ("ref_seg", "ref_what"):
        if f in c and not isinstance(c[f], str):
            v.schema(where, f"{f} not a string", "a string")
    if "claims" in c:
        cl = c["claims"]
        if not (isinstance(cl, dict) and set(cl) <= {"headline", "data"}):
            v.schema(where, f"claims {cl!r}", "{headline?, data?}")
        else:
            for k2, val in cl.items():
                _claim(v, where, val, asset_ids)
    if "camera" in c:
        cam = c["camera"]
        if not (isinstance(cam, dict) and set(cam) <= {"move", "pace", "goal", "method"}):
            v.schema(where, f"camera {cam!r}", "{move?, pace?, goal?, method?}")
        else:
            if "goal" in cam and cam["goal"] not in CAMERA_GOALS:
                v.schema(where, f"camera.goal {cam['goal']!r}", " | ".join(CAMERA_GOALS))
            if "method" in cam and cam["method"] not in CAMERA_METHODS:
                v.schema(where, f"camera.method {cam['method']!r}", " | ".join(CAMERA_METHODS))
            for k2 in ("move", "pace"):
                if k2 in cam and not isinstance(cam[k2], str):
                    v.schema(where, f"camera.{k2} not a string", "a string")
    if "evidence" in c and not (isinstance(c["evidence"], dict) and all(isinstance(x, str) for x in c["evidence"].values())):
        v.schema(where, "evidence", "{\"<field>\": \"<text>\"}")
    if "override" in c:
        o = c["override"]
        if not isinstance(o, dict):
            v.schema(where, "override not an object", "{why, source, confirmed, date}")
        else:
            v.keys(f"{where}.override", o, {"why", "source", "confirmed", "date"})
            if not nonempty_str(o.get("why")):
                v.schema(where, "override.why missing", "a non-empty why")
            if o.get("source") not in ("user", "model"):
                v.schema(where, f"override.source {o.get('source')!r}", "user | model")
            if o.get("source") == "user" and not nonempty_str(o.get("confirmed")):
                v.schema(where, "override source user without confirmed", "confirmed: the user's words")
            if not (isinstance(o.get("date"), str) and DATE_RE.match(o["date"])):
                v.schema(where, f"override.date {o.get('date')!r}", "YYYY-MM-DD")
    if "declares" in c:
        d = c["declares"]
        if not (isinstance(d, dict) and set(d) <= {"holds", "blacks", "silences"}):
            v.schema(where, f"declares {d!r}", "{holds?, blacks?, silences?}")
        else:
            for k2, arr in d.items():
                _intervals(v, f"{where}.declares.{k2}", arr)
    if "ground_exception" in c:
        g = c["ground_exception"]
        if not (isinstance(g, dict) and set(g) <= {"color", "why"}):
            v.schema(where, f"ground_exception {g!r}", "{color?, why?}")
        elif "color" in g and not (isinstance(g["color"], str) and HEX_RE.match(g["color"])):
            v.schema(where, f"ground_exception.color {g['color']!r}", "#RRGGBB")
    if "speed" in c and kind == "picture":
        s = c["speed"]
        ok = isinstance(s, dict) and set(s) == {"asset", "start_lt", "table"} and isinstance(s.get("asset"), str) \
            and is_num(s.get("start_lt")) and s["start_lt"] >= 0 and isinstance(s.get("table"), list) \
            and all(isinstance(r, list) and len(r) == 3 and all(is_num(x) for x in r) for r in s["table"])
        if not ok:
            v.schema(where, f"speed {s!r}", "{asset, start_lt >= 0, table: [[a, b, s], ...]}")
        elif s["asset"] not in asset_ids:
            v.add(where, "tv1.anchor_target", f"speed.asset {s['asset']!r} unknown", "an asset id")
    if "keys" in c:
        _keys(v, where, c["keys"])
    if "shows_state" in c and not (isinstance(c["shows_state"], list) and c["shows_state"]
                                   and all(isinstance(x, str) for x in c["shows_state"])):
        v.schema(where, f"shows_state {c['shows_state']!r}", "a non-empty array of state ids")
    if "intents" in c:
        it = c["intents"]
        if not (isinstance(it, list) and all(isinstance(x, dict) and set(x) <= {"kind", "expect", "tolerance", "moment"}
                                             and x.get("kind") in INTENT_KINDS and "expect" in x for x in it)):
            v.schema(where, f"intents {it!r}", "[{kind, expect, tolerance?, moment?}] with kind of design 7.5")


def _keys(v: _V, where: str, keys):
    """Frame roles inside a clip (agent-review design §3.1): K = key, B = breakdown; `at` in clip time."""
    if not isinstance(keys, list):
        v.schema(where, "keys not an array", "[{id, at, role, hold?, what}]")
        return
    for j, k in enumerate(keys):
        w = f"{where}.keys[{j}]"
        if not isinstance(k, dict):
            v.schema(w, "not an object", "{id, at, role, hold?, what}")
            continue
        v.keys(w, k, {"id", "at", "role", "hold", "what"})
        kid = k.get("id")
        if not (isinstance(kid, str) and KEY_ID_RE.match(kid)):
            v.schema(w, f"id {kid!r}", "^K[A-Za-z0-9-]{1,15}$")
        elif kid in v.key_ids:
            v.schema(w, f"duplicate key id {kid}", "key ids unique across the film")
        else:
            v.key_ids.add(kid)
        if not (is_num(k.get("at")) and k["at"] >= 0):
            v.schema(w, f"at {k.get('at')!r}", "a number >= 0 in clip time")
        if k.get("role") not in KEY_ROLES:
            v.schema(w, f"role {k.get('role')!r}", " | ".join(KEY_ROLES))
        if "hold" in k and not (is_num(k["hold"]) and k["hold"] >= 0):
            v.schema(w, f"hold {k['hold']!r}", "a number >= 0")
        if not nonempty_str(k.get("what")):
            v.schema(w, "missing what", "a non-empty what")


def _grammar(v: _V, where: str, field: str, e: "tr.GrammarError"):
    if e.tl4:
        v.add(where, "tv1.tl4", f"{field}: {e}", "no TL-4 form before TL-4", fmt={"detail": f"spec_invalid: {e}"})
    else:
        v.schema(where, f"{field}: {e}", "TimeRef / dur grammar (PSM 4.2)")


def _lines(v: _V, narration: list, asset_ids: set) -> list[str]:
    ids = []
    for i, ln in enumerate(narration):
        where = f"tracks.narration[{i}]"
        if not isinstance(ln, dict):
            v.schema(where, "not an object", "a line object")
            continue
        lid = ln.get("id")
        if isinstance(lid, str) and LINE_ID_RE.match(lid):
            if lid in ids:
                v.schema(lid, "duplicate line id", "unique line ids")
            ids.append(lid)
            where = lid
        else:
            v.schema(where, f"id {lid!r}", "^L[0-9]{1,3}$")
        v.keys(where, ln, LINE_KEYS)
        if not nonempty_str(ln.get("text")):
            v.schema(where, "text missing or empty", "a non-empty text")
        for k in ("say", "asr"):
            if k in ln and not nonempty_str(ln[k]):
                v.schema(where, f"{k} empty or not a string", "a non-empty string")
        if not isinstance(ln.get("section"), str):
            v.schema(where, "section missing", "a picture clip id")
        if "gap_after" in ln and not (is_num(ln["gap_after"]) and ln["gap_after"] >= 0):
            v.schema(where, f"gap_after {ln['gap_after']!r}", "a number >= 0")
        if "claim" in ln:
            _claim(v, where, ln["claim"], asset_ids)
    return ids


def _anchors_of(c: dict):
    """(field, Anchor) pairs a clip reads; parse errors already reported."""
    out = []
    try:
        a = tr.parse_timeref(c.get("at"))
        if isinstance(a, tr.Anchor):
            out.append(("at", a))
    except (tr.GrammarError, TypeError):
        pass
    try:
        d = tr.parse_dur(c.get("dur"))
        if isinstance(d, tr.EndAnchor):
            out.append(("dur", d.anchor))
    except (tr.GrammarError, TypeError):
        pass
    return out


def anchor_graph(picture: list, overlay: list) -> dict[str, list[str]]:
    """node -> nodes it reads. start reads its `at` anchor; end reads its own start (number dur) or its end anchor."""
    g: dict[str, list[str]] = {}
    for c in list(picture) + list(overlay):
        if not isinstance(c, dict) or not isinstance(c.get("id"), str):
            continue
        cid = c["id"]
        s, e = f"clip:{cid}.start", f"clip:{cid}.end"
        g.setdefault(s, [])
        g.setdefault(e, [])
        try:
            a = tr.parse_timeref(c.get("at"))
            if isinstance(a, tr.Anchor) and a.kind == "clip":
                g[s].append(a.node())
        except (tr.GrammarError, TypeError):
            pass
        try:
            d = tr.parse_dur(c.get("dur"))
            if isinstance(d, tr.Length):
                g[e].append(s)
            elif isinstance(d, tr.EndAnchor) and d.anchor.kind == "clip":
                g[e].append(d.anchor.node())
        except (tr.GrammarError, TypeError):
            pass
    return g


def find_cycle(g: dict[str, list[str]]) -> list[str] | None:
    """First cycle found by DFS in sorted node order, listed in reading order (node -> the node it reads)."""
    color: dict[str, int] = {}
    stack: list[str] = []

    def dfs(n: str):
        color[n] = 1
        stack.append(n)
        for m in g.get(n, []):
            if m not in g:
                continue
            if color.get(m) == 1:
                return stack[stack.index(m):] + [m]
            if color.get(m) is None:
                r = dfs(m)
                if r:
                    return r
        stack.pop()
        color[n] = 2
        return None

    for n in sorted(g):
        if color.get(n) is None:
            r = dfs(n)
            if r:
                return r
    return None


def _references(v: _V, picture, overlay, narration, sfx, clip_ids: dict, line_ids: list, pic_ids: list, policy):
    lines_by_id = {ln["id"]: ln for ln in narration if isinstance(ln, dict) and isinstance(ln.get("id"), str)}
    all_ok = True
    for c in list(picture) + list(overlay):
        if not isinstance(c, dict):
            continue
        cid = c.get("id") if isinstance(c.get("id"), str) else "?"
        for field, a in _anchors_of(c):
            if a.kind == "line" and a.ref not in lines_by_id:
                v.add(cid, "tv1.anchor_target", f"{field} reads line {a.ref} which does not exist", "an existing line id")
                all_ok = False
            elif a.kind == "clip" and a.ref not in clip_ids:
                v.add(cid, "tv1.anchor_target", f"{field} reads clip {a.ref} which does not exist", "an existing clip id")
                all_ok = False
            elif a.kind == "film" and policy != "fixed":
                v.add(cid, "tv1.film_end_fit", f"{field} reads film.end under {policy}", "film.end only under fixed (SEM-11)",
                      basis="SEM-11 / TV-1")
        # SEM-3
        try:
            d = tr.parse_dur(c.get("dur"))
        except (tr.GrammarError, TypeError):
            d = None
        if isinstance(d, tr.Lines):
            ids = [ln.get("id") for ln in narration if isinstance(ln, dict)]
            if d.a not in lines_by_id or d.b not in lines_by_id:
                v.add(cid, "tv1.anchor_target", f"dur lines {d.a}-{d.b}: unknown line", "existing line ids")
                all_ok = False
            elif ids.index(d.a) > ids.index(d.b):
                v.add(cid, "tv1.sem3", f"dur lines {d.a}-{d.b} run backwards", "La before Lb", basis="SEM-3 / TV-1",
                      fmt={"detail": f"{d.a}-{d.b}"})
            else:
                bad = [x for x in ids[ids.index(d.a): ids.index(d.b) + 1] if lines_by_id[x].get("section") != cid]
                if bad:
                    v.add(cid, "tv1.sem3", f"lines {', '.join(bad)} belong to another section",
                          f"every line {d.a}-{d.b} with section {cid}", basis="SEM-3 / TV-1",
                          fmt={"detail": ", ".join(f"{x}→{lines_by_id[x].get('section')}" for x in bad)})
    # narration grouped by section in picture order
    order = []
    for ln in narration:
        if not isinstance(ln, dict):
            continue
        sec = ln.get("section")
        if isinstance(sec, str) and sec not in pic_ids:
            v.add(ln.get("id", "?"), "tv1.anchor_target", f"section {sec} is not a picture clip", "a picture clip id")
            continue
        if isinstance(sec, str):
            order.append((ln.get("id"), pic_ids.index(sec)))
    for (a, ia), (b, ib) in zip(order, order[1:]):
        if ib < ia:
            v.add(b, "tv1.narration_order", f"{b} (section #{ib}) after {a} (section #{ia})",
                  "lines grouped by section, sections in picture order", fmt={"detail": f"{a} → {b}"})
    if all_ok:
        cyc = find_cycle(anchor_graph(picture, overlay))
        if cyc:
            nodes = " -> ".join(cyc)
            v.add("film", "tv1.cycle", nodes, "an acyclic anchor graph (TL-INV-2)", basis="TL-INV-2 / TV-1",
                  fmt={"detail": nodes})


def _sfx(v: _V, sfx: list, clip_ids: dict, line_ids: list, policy):
    for i, s in enumerate(sfx):
        where = f"sfx[{i}]"
        if not isinstance(s, dict):
            v.schema(where, "not an object", "an sfx event")
            continue
        v.keys(where, s, SFX_KEYS)
        try:
            a = tr.parse_timeref(s.get("at"))
            if isinstance(a, tr.Anchor) and a.kind == "clip" and a.ref not in clip_ids:
                v.add(where, "tv1.anchor_target", f"at reads clip {a.ref} which does not exist", "an existing clip id")
            elif isinstance(a, tr.Anchor) and a.kind == "line" and a.ref not in line_ids:
                v.add(where, "tv1.anchor_target", f"at reads line {a.ref} which does not exist", "an existing line id")
            elif isinstance(a, tr.Anchor) and a.kind == "film" and policy != "fixed":
                v.add(where, "tv1.film_end_fit", f"at reads film.end under {policy}", "film.end only under fixed (SEM-11)",
                      basis="SEM-11 / TV-1")
        except (tr.GrammarError, TypeError) as e:
            _grammar(v, where, "at", e) if isinstance(e, tr.GrammarError) else v.schema(where, "at", "TimeRef")
        if not nonempty_str(s.get("sound")):
            v.schema(where, "sound missing", "a sound id")
        g = s.get("gain_db")
        if not (is_num(g) and -60 <= g <= 6):
            v.schema(where, f"gain_db {g!r}", "a number -60..+6")
        if not nonempty_str(s.get("why")):
            v.schema(where, "why missing", "a non-empty why")
        if "target" in s and s["target"] not in clip_ids:
            v.add(where, "tv1.anchor_target", f"target {s['target']!r} unknown", "an existing clip id")


# ---------------------------------------------------------------- voice/lines.json (PSM 4.4)
def validate_lines_json(obj, line_ids: list[str]) -> list[dict]:
    v = _V()
    if not isinstance(obj, dict) or set(obj) != {"schema_version", "lines"} or obj.get("schema_version") != 1 \
            or not isinstance(obj.get("lines"), dict):
        v.add("voice/lines.json", "tv1.lines_json", "shape", "{schema_version: 1, lines: {Ln: {est_dur}}}",
              fmt={"detail": "格式應為 {schema_version: 1, lines: {...}}"})
        return v.rows
    for lid, e in obj["lines"].items():
        where = f"voice/lines.json:{lid}"
        if lid not in line_ids:
            v.add(where, "tv1.lines_json", f"{lid} is not a narration line", "a line id of tracks.narration",
                  fmt={"detail": f"{lid} 不是旁白句"})
            continue
        if not isinstance(e, dict):
            v.add(where, "tv1.lines_json", "entry not an object", "{est_dur}", fmt={"detail": f"{lid} 格式不符"})
        elif "est_dur" in e and "state" in e:
            v.add(where, "tv1.lines_json", "est_dur and state together", "one of them",
                  fmt={"detail": f"spec_invalid: {lid} 同時有 est_dur 與 state"})
        elif "state" in e:
            v.add(where, "tv1.lines_json", "tool-written entry (state)", "est_dur only in TL-0",
                  fmt={"detail": f"{lid} 的錄音狀態要到 TL-1 才支援"})
        elif set(e) != {"est_dur"} or not (is_num(e["est_dur"]) and e["est_dur"] > 0):
            v.add(where, "tv1.lines_json", repr(e), "{est_dur: number > 0}", fmt={"detail": f"{lid} 的 est_dur 不合"})
    return v.rows


# ---------------------------------------------------------------- loading and views
def load_timeline(film: Path, *, rules: Rules | None = None, info: dict | None = None) -> tuple[dict, list[dict]]:
    film = Path(film)
    obj = read_json(film / "film.timeline.json")
    return obj, validate_timeline(obj, rules=rules, film_id=film.name, info=info)


def tracks(obj: dict) -> dict:
    t = obj.get("tracks") or {}
    return {"picture": t.get("picture") or [], "overlay": t.get("overlay") or [],
            "narration": t.get("narration") or [], "sfx": t.get("sfx") or [], "captions": t.get("captions"),
            "music": t.get("music")}


def freedom(c: dict) -> str:
    return c.get("freedom") or "guided"


def decision(obj: dict, key: str):
    e = (obj.get("decisions") or {}).get(key)
    return e.get("value") if isinstance(e, dict) else None


def meta_value(obj: dict, key: str, default):
    v = (obj.get("meta") or {}).get(key)
    return default if v is None else v


def is_video_path(p: str) -> bool:
    return isinstance(p, str) and p.lower().endswith(VIDEO_EXT)


def lines_json_obj(film: Path):
    p = Path(film) / "voice" / "lines.json"
    if not p.is_file():
        return None
    obj = read_json(p)
    return obj


def require_obj(obj) -> dict:
    if not isinstance(obj, dict):
        raise SpecInvalid("film.timeline.json is not a JSON object")
    return obj

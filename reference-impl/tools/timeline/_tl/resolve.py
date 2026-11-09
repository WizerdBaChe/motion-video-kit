"""Anchor resolution (PSM 6.7; design 6.3; Y-2, Z-4, TG-7, P-1).

Snapped times are integers of frames and authoritative; their seconds are frames / fps, never rounded.
Unsnapped values (line times, *_raw, by_s) are rounded to 6 decimals as they are computed.
"""
from __future__ import annotations

import math
import random
import unicodedata
from pathlib import Path

from . import defaults as D
from . import model as M
from . import timeref as tr
from .common import SpecInvalid, r6
from .nhash import file_nsha, json_nsha


def snapf(t: float, fps: int) -> int:
    """Half-up with an epsilon: 5.05 s at 30 fps (151.49999999999997 in binary) -> frame 152 (TG-7)."""
    return math.floor(t * fps + 0.5 + 1e-9)


def fsec(frames: int, fps: int) -> float:
    return frames / fps


# ---------------------------------------------------------------- line durations (PSM 4.4)
def _is_han(ch: str) -> bool:
    try:
        name = unicodedata.name(ch)
    except ValueError:
        return False
    return name.startswith(("CJK UNIFIED IDEOGRAPH", "CJK COMPATIBILITY IDEOGRAPH", "HIRAGANA", "KATAKANA", "BOPOMOFO"))


def rate_estimate(text: str) -> float:
    n_han = sum(1 for ch in text if _is_han(ch))
    n_other = sum(1 for ch in text if ch.isascii() and ch.isalnum())
    return round(max(D.EST_MIN_S, n_han / D.EST_HAN_PER_S + n_other / D.EST_OTHER_PER_S), 2)


def line_durations(narration: list, lines_json, voice_lock: dict | None = None) -> dict:
    """{line id: (dur_s, dur_source, estimated)} by the PSM 4.4 source order."""
    entries = (lines_json or {}).get("lines") or {}
    out = {}
    for ln in narration:
        lid = ln["id"]
        if voice_lock and lid in voice_lock:
            out[lid] = (float(voice_lock[lid]["dur_s"]), "voice_lock", False)
        elif isinstance(entries.get(lid), dict) and entries[lid].get("state") in ("checked", "imported"):
            out[lid] = (float(entries[lid]["dur_s"]), entries[lid]["state"], False)
        elif isinstance(entries.get(lid), dict) and "est_dur" in entries[lid]:
            out[lid] = (float(entries[lid]["est_dur"]), "est_dur", True)
        else:
            out[lid] = (rate_estimate(ln.get("say") or ln["text"]), "rate", True)
    return out


# ---------------------------------------------------------------- resolution
def _order(g: dict[str, list[str]], seed: int) -> list[str]:
    """Kahn's algorithm; `seed` permutes the initial queue (TL-INV-2: the result must not depend on it)."""
    indeg = {n: 0 for n in g}
    users: dict[str, list[str]] = {n: [] for n in g}
    for n, deps in g.items():
        for d in deps:
            if d in g:
                indeg[n] += 1
                users[d].append(n)
    queue = sorted(n for n, k in indeg.items() if k == 0)
    random.Random(seed).shuffle(queue)
    out = []
    while queue:
        n = queue.pop(0)
        out.append(n)
        for u in users[n]:
            indeg[u] -= 1
            if indeg[u] == 0:
                queue.append(u)
    if len(out) != len(g):
        raise SpecInvalid("anchor graph has a cycle", hint="run tl.py validate --static (TV-1 lists the cycle)")
    return out


def resolve(film: Path, timeline: dict, lines_src: dict, *, order_seed: int = 0, inputs: dict | None = None) -> dict:
    t = M.tracks(timeline)
    meta = timeline["meta"]
    fmt = meta["format"]
    fps = int(fmt["fps"])
    policy = fmt["duration_policy"]
    lead = float(M.meta_value(timeline, "lead", D.LEAD_S))
    tail = float(M.meta_value(timeline, "tail", D.TAIL_S))
    line_gap = float(M.meta_value(timeline, "line_gap", D.LINE_GAP_S))
    section_gap = float(M.meta_value(timeline, "section_gap", D.SECTION_GAP_S))
    duration_s = float(fmt["duration_s"]) if policy == "fixed" else None
    notes: list[str] = []

    # 2. narration
    lines = []
    prev = None
    for ln in t["narration"]:
        dur, src, est = lines_src[ln["id"]]
        if prev is None:
            t0 = lead
        else:
            if ln["section"] != prev["section"]:
                gap = section_gap
                if prev.get("gap_after") is not None:
                    notes.append(f"{prev['id']}.gap_after ignored: section change uses section_gap")
            else:
                gap = prev["gap_after"] if prev.get("gap_after") is not None else line_gap
            t0 = r6(lines[-1]["t1"] + gap)
        t1 = r6(t0 + dur)
        lines.append({"id": ln["id"], "section": ln["section"], "t0": r6(t0), "t1": t1, "dur_s": r6(dur),
                      "dur_source": src, "estimated": est})
        prev = ln
    line_at = {ln["id"]: ln for ln in lines}

    # 3. clips and overlays: anchor graph, pre-extension pre-snap values
    clips = {c["id"]: c for c in t["picture"] + t["overlay"]}
    g = M.anchor_graph(t["picture"], t["overlay"])
    raw: dict[str, float] = {}

    def value(a: tr.Anchor) -> float:
        if a.kind == "line":
            base = line_at[a.ref]["t0" if a.edge == "start" else "t1"]
        elif a.kind == "clip":
            base = raw[a.node()]
        else:
            base = duration_s
        return r6(base + a.offset)

    for node in _order(g, order_seed):
        cid, edge = node[5:].rsplit(".", 1)
        c = clips[cid]
        if edge == "start":
            at = tr.parse_timeref(c["at"])
            raw[node] = r6(at) if isinstance(at, float) else value(at)
        else:
            d = tr.parse_dur(c["dur"])
            if isinstance(d, tr.Length):
                raw[node] = r6(raw[f"clip:{cid}.start"] + d.s)
            elif isinstance(d, tr.EndAnchor):
                raw[node] = value(d.anchor)
            else:
                raw[node] = r6(line_at[d.b]["t1"] + d.pad)

    # 4. sfx
    sfx = []
    for i, s in enumerate(t["sfx"]):
        at = tr.parse_timeref(s["at"])
        tt = r6(at) if isinstance(at, float) else value(at)
        e = {"index": i, "t": tt, "sound": s["sound"], "gain_db": s["gain_db"], "why": s["why"]}
        if "target" in s:
            e["target"] = s["target"]
        sfx.append(e)

    # 5. snap; transitions
    picture = []
    for c in t["picture"]:
        cid = c["id"]
        t0_raw, e_raw = raw[f"clip:{cid}.start"], raw[f"clip:{cid}.end"]
        t0_f, e_f = snapf(t0_raw, fps), snapf(e_raw, fps)
        tin = c.get("transition_in")
        if isinstance(tin, dict):
            tdur = float(tin["dur"])
            trans = {"kind": "component", "component": tin["component"], "tdur": tdur, "tdur_frames": snapf(tdur, fps)}
        elif tin == "cut":
            trans = {"kind": "cut", "component": None, "tdur": 0.0, "tdur_frames": 0}
        elif M.freedom(c) == "guided":
            trans = {"kind": "open", "component": None, "tdur": 0.0, "tdur_frames": 0}
        else:
            trans = {"kind": "cut", "component": None, "tdur": 0.0, "tdur_frames": 0}
        tf = trans["tdur_frames"]
        first_line = next((ln["id"] for ln in lines if ln["section"] == cid), None)
        picture.append({
            "id": cid, "role": c["role"], "freedom": M.freedom(c), "freedom_defaulted": "freedom" not in c,
            "t0_raw": t0_raw, "t0_f": t0_f, "t0": fsec(t0_f, fps), "e_raw": e_raw,
            "e_author_f": e_f, "e_f": e_f, "e_author": fsec(e_f, fps), "e": fsec(e_f, fps),
            "d_author": fsec(e_f - t0_f, fps), "d": fsec(e_f - t0_f, fps), "extension_s": 0.0,
            "transition": trans,
            "window": [fsec(t0_f, fps), fsec(t0_f + tf, fps)] if trans["tdur"] > 0 else None,
            "cut_moment": (t0_f + tf / 2) / fps, "first_line": first_line,
            "anchors": {"at": tr.text_of(c["at"]), "dur": tr.text_of(c["dur"])}})
    overlay = []
    for c in t["overlay"]:
        cid = c["id"]
        t0_raw, e_raw = raw[f"clip:{cid}.start"], raw[f"clip:{cid}.end"]
        t0_f, e_f = snapf(t0_raw, fps), snapf(e_raw, fps)
        overlay.append({"id": cid, "z": c["z"], "freedom": M.freedom(c), "freedom_defaulted": "freedom" not in c,
                        "t0_raw": t0_raw, "t0_f": t0_f, "t0": fsec(t0_f, fps), "e_raw": e_raw, "e_f": e_f,
                        "e": fsec(e_f, fps), "d": fsec(e_f - t0_f, fps),
                        "anchors": {"at": tr.text_of(c["at"]), "dur": tr.text_of(c["dur"])}})

    # 6. film length in frames
    last_f = max(p["e_author_f"] for p in picture)
    if policy == "fit":
        n_frames = last_f + snapf(tail, fps)
    else:
        n_frames = round(duration_s * fps)
    tail_hold = None
    if n_frames > last_f:
        tail_hold = {"t0_f": last_f, "t1_f": n_frames, "t0": fsec(last_f, fps), "t1": fsec(n_frames, fps)}

    # 7. gap fill (after everything else; anchors already read pre-extension values, Y-2)
    extensions = []
    for k in range(1, len(picture)):
        a, b = picture[k - 1], picture[k]
        if a["e_f"] < b["t0_f"]:
            by = b["t0_f"] - a["e_f"]
            a["e_f"] = b["t0_f"]
            a["e"] = fsec(a["e_f"], fps)
            a["d"] = fsec(a["e_f"] - a["t0_f"], fps)
            a["extension_s"] = r6(by / fps)
            extensions.append({"clip": a["id"], "by_s": r6(by / fps), "to_f": b["t0_f"], "to": fsec(b["t0_f"], fps)})
    ground_preroll = None
    if picture and picture[0]["t0_f"] > 0:
        ground_preroll = {"t0_f": 0, "t1_f": picture[0]["t0_f"], "t0": 0.0, "t1": fsec(picture[0]["t0_f"], fps)}

    defaults_applied = sorted(f"{c['id']}.freedom=guided" for c in t["picture"] + t["overlay"] if "freedom" not in c)
    # 8. frame roles (agent-review design §3.1): written only when a clip declares keys, so older films resolve
    #    byte-identically (BR-16); seams are derived by readers from `picture`
    starts = {p["id"]: p["t0_f"] for p in picture + overlay}
    keys = [{"id": k["id"], "clip": c["id"], "role": k["role"], "what": k["what"],
             "t_f": starts[c["id"]] + snapf(float(k["at"]), fps), "t": fsec(starts[c["id"]] + snapf(float(k["at"]), fps), fps),
             "hold": float(k.get("hold", 0.0))}
            for c in t["picture"] + t["overlay"] for k in c.get("keys") or []]
    extra = {"keys": sorted(keys, key=lambda k: (k["t_f"], k["id"]))} if keys else {}
    return {
        "schema_version": 1, "generator": "tl", "film_id": Path(film).name,
        "inputs": inputs or {},
        "format": {"size": fmt["size"], "fps": fps, "duration_policy": policy},
        "film_end_s": fsec(n_frames, fps), "n_frames": n_frames, "last_f": last_f,
        "lead": lead, "tail": tail, "line_gap": line_gap, "section_gap": section_gap,
        "ground_preroll": ground_preroll, "tail_hold": tail_hold,
        "lines": lines, "picture": picture, "overlay": overlay, "sfx": sfx,
        "extensions": extensions, "defaults_applied": defaults_applied, "notes": notes, **extra}


def resolved_inputs(film: Path, timeline_nsha: str, lines_nsha, clips_nsha: str, components_nsha: str,
                    runtime_hash: str) -> dict:
    return {"timeline_nsha": timeline_nsha, "lines_nsha": lines_nsha, "clips_nsha": clips_nsha,
            "components_nsha": components_nsha, "runtime_hash": runtime_hash}


def resolved_nsha(film: Path):
    p = Path(film) / "build" / "timeline.resolved.json"
    return file_nsha(p) if p.is_file() else None


__all__ = ["snapf", "fsec", "rate_estimate", "line_durations", "resolve", "json_nsha"]

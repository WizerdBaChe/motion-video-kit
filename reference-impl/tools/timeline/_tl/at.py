"""Seconds -> clip / line query (PSM 6.12; BR-11). Read-only."""
from __future__ import annotations

from .common import SpecInvalid, r6


def at(resolved: dict, t: float) -> dict:
    fps = resolved["format"]["fps"]
    end = resolved["film_end_s"]
    if not (0 <= t < end):
        raise SpecInvalid(f"{t} s is outside the film [0, {end:g})", hint=f"ask for a time in [0, {end:g})")
    ans = {"t": t, "picture": [], "in_transition": False, "overlays": [], "line": None, "lt": {}, "where": "clip"}
    pic = resolved["picture"]
    gp = resolved.get("ground_preroll")
    if gp and t < gp["t1"]:
        ans["where"] = "ground"
    else:
        k = max((i for i, p in enumerate(pic) if p["t0"] <= t), default=None)
        if k is not None:
            p = pic[k]
            th = resolved.get("tail_hold")
            if th and t >= th["t0"] and k == len(pic) - 1:
                ans["picture"] = [p["id"]]
                ans["lt"][p["id"]] = r6(p["d"])
                ans["where"] = "tail hold"
            else:
                w = p.get("window")
                if w and w[0] <= t < w[1] and k > 0:
                    prev = pic[k - 1]
                    ans["picture"] = [prev["id"], p["id"]]
                    ans["in_transition"] = True
                    ans["lt"][prev["id"]] = r6(min(t - prev["t0"], prev["d"]))
                else:
                    ans["picture"] = [p["id"]]
                ans["lt"][p["id"]] = r6(min(t - p["t0"], p["d"]))
    for o in resolved["overlay"]:
        if o["t0"] <= t < o["e"]:
            ans["overlays"].append(o["id"])
            ans["lt"][o["id"]] = r6(t - o["t0"])
    for ln in resolved["lines"]:
        if ln["t0"] <= t < ln["t1"]:
            ans["line"] = ln["id"]
    return ans


def describe(ans: dict) -> str:
    t = ans["t"]
    if ans["where"] == "ground":
        s = f"{t:g} s: ground before the first clip"
    elif ans["where"] == "tail hold":
        cid = ans["picture"][0]
        s = f"{t:g} s: {cid} tail hold (last frame, lt {ans['lt'][cid]:g})"
    elif ans["in_transition"]:
        a, b = ans["picture"]
        s = f"{t:g} s: {b} in transition from {a} (lt {b} {ans['lt'][b]:g}, {a} {ans['lt'][a]:g})"
    else:
        cid = ans["picture"][0]
        s = f"{t:g} s: {cid} (lt {ans['lt'][cid]:g})"
    s += f"; line {ans['line']}" if ans["line"] else "; no line"
    if ans["overlays"]:
        s += f"; overlays {', '.join(ans['overlays'])}"
    return s

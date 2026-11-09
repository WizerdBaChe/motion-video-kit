"""validate --timed (PSM 6.8, 7): TV-2, TV-4b, TV-6, TV-7, TV-9b, TV-10, TV-14, TV-19, TV-20 on the resolved file."""
from __future__ import annotations

from . import defaults as D
from . import model as M
from .common import last_line, row, summarize
from .components import Index
from .messages_zh import zh
from .resolve import snapf
from .rules import Rules

NOT_EXECUTED = "clip programs are not executed before TL-1"


def run_timed(film, resolved: dict, timeline: dict, rules: Rules, index: Index, *, execute_clips: bool = False) -> dict:
    rows: list[dict] = []
    for name, fn in (("TV-2", _tv2), ("TV-4b", _tv4b), ("TV-7", _tv7), ("TV-10", _tv10), ("TV-14", _tv14),
                     ("TV-19", _tv19), ("TV-20", _tv20)):
        try:
            rows += fn(resolved, timeline, rules, index)
        except Exception as e:  # one evaluator failing -> undetermined, others still run; exit 3 (PSM 5.2)
            rows.append(row(name, "film", "undetermined", stage="timed", reason=f"evaluator error: {last_line(e)}",
                            message_key="undetermined.evaluator", message=zh("undetermined.evaluator", detail=last_line(e))))
    if not execute_clips:
        rows.append(row("TV-6", "film", "undetermined", stage="timed", reason=NOT_EXECUTED,
                        message_key="tv6.undetermined", message=zh("tv6.undetermined")))
        rows.append(row("TV-9b", "film", "undetermined", stage="timed", reason=NOT_EXECUTED,
                        message_key="tv9b.undetermined", message=zh("tv9b.undetermined")))
    share = freedom_share(resolved)
    return {"rows": rows, "summary": summarize(rows), "freedom_share": share}


def freedom_share(resolved: dict) -> dict:
    s = {"locked_s": 0, "guided_s": 0, "free_s": 0}
    fps = resolved["format"]["fps"]
    for p in resolved["picture"]:
        s[f"{p['freedom']}_s"] += p["e_f"] - p["t0_f"]
    return {k: round(v / fps, 6) for k, v in s.items()}


def _blk(check, where, key, measured, expected, basis, clip=None, detail=None, bucket="blocking", provisional=False):
    return row(check, where, bucket, stage="timed", measured=measured, expected=expected, basis=basis,
               provisional=provisional, message_key=key, message=zh(key, clip=clip or where, detail=detail or measured))


def _tv2(res: dict, tl: dict, rules: Rules, index: Index) -> list[dict]:
    rows = []
    fps = res["format"]["fps"]
    pic = res["picture"]
    for k, p in enumerate(pic):
        dfr = p["e_author_f"] - p["t0_f"]
        if k and p["t0_f"] < pic[k - 1]["t0_f"]:
            rows.append(_blk("TV-2", f"{p['id']}.order", "tv2.order", f"t0 {p['t0']} < previous {pic[k - 1]['t0']}",
                             "resolved order = array order", "PSM 4.1 / TV-2", clip=p["id"]))
        if dfr <= 0:
            rows.append(_blk("TV-2", f"{p['id']}.length", "tv2.nonpositive", f"d_author {p['d_author']}", "> 0",
                             "TV-2", clip=p["id"]))
        tr = p["transition"]
        if tr["tdur"] > 0:
            if tr["tdur_frames"] == 0:
                rows.append(_blk("TV-2", f"{p['id']}.transition", "tv2.one_frame",
                                 f"tdur {tr['tdur']} s = 0 frames at {fps} fps", ">= 1 frame", "PSM 6.7 step 5",
                                 clip=p["id"]))
            elif tr["tdur_frames"] > dfr:
                rows.append(_blk("TV-2", f"{p['id']}.transition", "tv2.tdur",
                                 f"tdur {tr['tdur']} > d_author {p['d_author']}", "0 < tdur <= d_author", "SEM-1",
                                 clip=p["id"]))
        if k:
            a = pic[k - 1]
            if a["e_author_f"] > p["t0_f"] + tr["tdur_frames"]:
                end = (p["t0_f"] + tr["tdur_frames"]) / fps
                rows.append(_blk("TV-2", f"{p['id']}.sem2", "tv2.sem2",
                                 f"{a['id']} ends {a['e_author']} > {p['id']} window end {end}",
                                 f"<= {end}", "SEM-2", clip=p["id"],
                                 detail=f"{a['id']} 結束於 {a['e_author']:.6g} 秒，窗尾 {end:.6g} 秒"))
            if p["t0_f"] < a["t0_f"] + a["transition"]["tdur_frames"]:
                wend = (a["t0_f"] + a["transition"]["tdur_frames"]) / fps
                rows.append(_blk("TV-2", f"{p['id']}.sem1", "tv2.sem1", f"t0 {p['t0']} < {a['id']} window end {wend}",
                                 f">= {wend}", "SEM-1 / X-14 / Y-7a", clip=p["id"],
                                 detail=f"{p['t0']:.6g} < {wend:.6g}"))
    # SEM-4
    if M.decision(tl, "rhythm_source") == "narration":
        lines = {ln["id"]: ln for ln in res["lines"]}
        for k, p in enumerate(pic):
            if k == 0 or p["role"] != "feature" or not p["first_line"]:
                continue
            l0 = lines[p["first_line"]]["t0"]
            dev = abs(p["cut_moment"] - l0)
            if dev > D.CUT_TOLERANCE_S + D.SLACK_S:
                rows.append(_blk("TV-2", f"{p['id']}.sem4", "tv2.sem4",
                                 f"cut moment {p['cut_moment']:.6f} vs {p['first_line']} start {l0} (dev {dev:.6f})",
                                 f"|dev| <= {D.CUT_TOLERANCE_S}", "SEM-4 / T08", clip=p["id"], detail=f"{dev:.3f}"))
    # SEM-13
    ov = res["overlay"]
    for i in range(len(ov)):
        for j in range(i + 1, len(ov)):
            a, b = ov[i], ov[j]
            if a["z"] == b["z"] and a["t0_f"] < b["e_f"] and b["t0_f"] < a["e_f"]:
                rows.append(_blk("TV-2", f"{b['id']}.sem13", "tv2.sem13",
                                 f"{a['id']} [{a['t0']:.6g}, {a['e']:.6g}) and {b['id']} [{b['t0']:.6g}, {b['e']:.6g}) on z {a['z']}",
                                 "no overlap on one z", "SEM-13", clip=b["id"], detail=a["id"]))
    # declares t1 <= d_author
    clips = {c["id"]: c for c in M.tracks(tl)["picture"] + M.tracks(tl)["overlay"]}
    dauth = {p["id"]: p["d_author"] for p in pic}
    dauth.update({o["id"]: o["d"] for o in ov})
    for cid, c in clips.items():
        for kind, arr in (c.get("declares") or {}).items():
            for it in arr:
                if it["t1"] > dauth[cid] + D.SLACK_S:
                    rows.append(_blk("TV-2", f"{cid}.declares", "tv2.declares",
                                     f"{kind} [{it['t0']}, {it['t1']}] beyond d_author {dauth[cid]}",
                                     "t1 <= d_author", "SEM-9 / PSM 4.1", clip=cid))
        for k in c.get("keys") or []:
            if float(k["at"]) > dauth[cid] + D.SLACK_S:
                rows.append(_blk("TV-2", f"{cid}.keys", "tv2.keys", f"{k['id']} at {k['at']} beyond d_author {dauth[cid]}",
                                 "at <= d_author", "agent-review design §3.1", clip=cid, detail=k["id"]))
    return rows


def _tv20(res: dict, tl: dict, rules: Rules, index: Index) -> list[dict]:
    """INV-R1 (agent-review design §3.2): every picture clip has a key frame; provisional look."""
    clips = {c["id"]: c for c in M.tracks(tl)["picture"]}
    return [_blk("TV-20", cid, "tv20.no_key", "no keys[] entry with role key", ">= 1 key per picture clip",
                 "agent-review design INV-R1", clip=cid, bucket="look", provisional=True)
            for cid, c in clips.items() if not any(k.get("role") == "key" for k in c.get("keys") or [])]


def _tv4b(res: dict, tl: dict, rules: Rules, index: Index) -> list[dict]:
    rows = []
    clips = {c["id"]: c for c in M.tracks(tl)["picture"] + M.tracks(tl)["overlay"]}
    lens = {p["id"]: p["d_author"] for p in res["picture"]}
    lens.update({o["id"]: o["d"] for o in res["overlay"]})
    for cid, c in clips.items():
        if M.freedom(c) != "locked":
            continue
        comp = index.get((c.get("device") or {}).get("component"))
        if not comp:
            continue
        for name, spec in (comp.get("params") or {}).items():
            if spec.get("source") != "clip_dur":
                continue
            d = lens[cid]
            bad = []
            if "min" in spec and d < spec["min"] - D.SLACK_S:
                bad.append(f"{d:.6g} < min {spec['min']}")
            if "max" in spec and d > spec["max"] + D.SLACK_S:
                bad.append(f"{d:.6g} > max {spec['max']}")
            if bad:
                rows.append(_blk("TV-4b", cid, "tv4.clip_dur", f"{name} = d_author {d:.6g}: {'; '.join(bad)}",
                                 f"[{spec.get('min', '-inf')}, {spec.get('max', 'inf')}]", "Z-4 / P-2 / TV-4b",
                                 clip=cid, detail=f"{d:.6g} 秒超出元件範圍（{'；'.join(bad)}）"))
    return rows


def end_hold_declared(res: dict, tl: dict) -> float:
    """(film_end - e_last) + the last clip's declared holds ending at d_author, contiguous back (PSM 7 TV-7)."""
    fps = res["format"]["fps"]
    pic = res["picture"]
    last = pic[-1]
    frames = res["n_frames"] - res["last_f"]
    c = next(x for x in M.tracks(tl)["picture"] if x["id"] == last["id"])
    holds = sorted(((snapf(h["t0"], fps), snapf(h["t1"], fps)) for h in (c.get("declares") or {}).get("holds", [])),
                   key=lambda h: -h[1])
    edge = last["e_author_f"] - last["t0_f"]
    for h0, h1 in holds:
        if abs(h1 - edge) <= 1:
            frames += h1 - h0
            edge = h0
    return frames / fps


def _tv7(res: dict, tl: dict, rules: Rules, index: Index) -> list[dict]:
    if rules.end_hold_range is None:
        return [row("TV-7", "film", "undetermined", stage="timed", reason=rules.absent_reason("rules[end_hold].range_s"),
                    message_key="tv7.undetermined", message=zh("tv7.undetermined"))]
    lo, hi = rules.end_hold_range
    v = end_hold_declared(res, tl)
    if v < lo - D.RANGE_TOL_S or v > hi + D.RANGE_TOL_S:
        return [_blk("TV-7", "film", "tv7.range", f"{v:.6g}", f"[{lo}, {hi}]", "D-T23 / W30 / FK-R-16 end_hold",
                     bucket="look", provisional=True, detail=f"{v:.6g}")]
    return []


def _tv10(res: dict, tl: dict, rules: Rules, index: Index) -> list[dict]:
    mx = rules.timeline.get("free_share_max")
    if not M.is_num(mx):
        return [row("TV-10", "film", "undetermined", stage="timed",
                    reason=rules.absent_reason("params.timeline.free_share_max"),
                    message_key="tv10.undetermined", message=zh("tv10.undetermined"))]
    sh = freedom_share(res)
    total = sh["locked_s"] + sh["guided_s"] + sh["free_s"]
    share = sh["free_s"] / total if total > 0 else 0.0
    if share > mx + D.SLACK_S:
        return [_blk("TV-10", "film", "tv10.share", f"{share:.3f}", f"<= {mx}", "BR-3 / D-T9 (params.timeline)",
                     bucket="look", provisional=True, detail=f"{share * 100:.0f}%")]
    return []


def _tv14(res: dict, tl: dict, rules: Rules, index: Index) -> list[dict]:
    rows = []
    for p in res["picture"]:
        if p["transition"]["tdur"] <= 0:
            continue
        before = [ln for ln in res["lines"] if ln["t0"] < p["t0"]]
        if not before:
            continue
        ln = before[-1]
        if p["t0"] < ln["t1"] - D.SLACK_S:
            rows.append(_blk("TV-14", p["id"], "tv14.cover", f"window starts {p['t0']:.6g} before {ln['id']} ends {ln['t1']}",
                             f">= {ln['t1']}", "TV-14 (user r13)", bucket="look", provisional=True, clip=p["id"],
                             detail=f"{ln['id']} 在 {ln['t1']} 秒結束，轉場從 {p['t0']:.6g} 秒開始"))
    return rows


def _tv19(res: dict, tl: dict, rules: Rules, index: Index) -> list[dict]:
    rows = []
    fps = res["format"]["fps"]
    if res["format"]["duration_policy"] == "fixed" and res["last_f"] > res["n_frames"]:
        rows.append(_blk("TV-19", "film", "tv19.overrun", f"last picture end {res['last_f'] / fps:.6g} > {res['film_end_s']:.6g}",
                         f"<= {res['film_end_s']:.6g}", "X-15c / TV-19", detail=f"{res['last_f'] / fps:.6g} > {res['film_end_s']:.6g}"))
    e_last = res["last_f"] / fps
    for ln in res["lines"]:
        if ln["t1"] > e_last + D.SLACK_S:
            rows.append(_blk("TV-19", ln["id"], "tv19.line_tail", f"{ln['id']} ends {ln['t1']} after e_last {e_last:.6g}",
                             f"<= {e_last:.6g}", "D-T19 / PSM 7 TV-19", clip=ln["id"],
                             detail=f"{ln['t1']} > {e_last:.6g}"))
    for o in res["overlay"]:
        if o["e_f"] > res["n_frames"]:
            rows.append(_blk("TV-19", o["id"], "tv19.overlay", f"{o['id']} ends {o['e']:.6g} > film end {res['film_end_s']:.6g}",
                             f"<= {res['film_end_s']:.6g}", "TV-19", clip=o["id"]))
    for ext in res["extensions"]:
        rows.append(row("TV-19", f"ext:{ext['clip']}", "info", stage="timed", measured=f"+{ext['by_s']} s to {ext['to']:.6g}",
                        expected="listed (D-T22)", basis="D-T22", message_key="tv19.extension",
                        message=zh("tv19.extension", clip=ext["clip"], detail=f"{ext['by_s']:g}")))
    return rows

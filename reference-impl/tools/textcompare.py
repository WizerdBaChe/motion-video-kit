"""Compare on-screen text line starts from screenlines.py with a model frame read of the same film.

The model read (measurements/<case>/text_events_modelread.json, written by a model, not a human)
is the control: it separates lyric lines from dialogue, titles, manga balloons, decorative type and
UI, which the OCR cannot. Reported per case: recall of model onsets of one --kind (default lyric) by
screenlines starts and precision of screenlines starts against model onsets of ANY text kind and of
that kind, within --tol seconds; and the onsets written out as a JSON list for cutdrivers.py --lines.
--section keeps only events whose `section` field matches (animation MADs carry mad / credits /
postcredit; C35's author segment after the song is not part of the MAD).

--lock also asks the reverse question "does a line arrive WITH a picture change", using
cutdrivers.lock_test (onsets shifted +-3 s as the control, lag search +-0.15 s) against up to three
picture-change sets: hard cuts (ffmpeg scene > 0.3 on a 320-px copy, saved as scene_cuts.json),
transition peaks (blurdip --auto blur-bridge/focus-in + flashwash peaks, merged within 0.3 s, saved as
transition_peaks.json; only when both measurement files exist), and their union (merged within
0.3 s). A lock needs p < 0.05 / (number of sets tried). First run (C33, 2026-10-04): neither set
alone locks, the union does (p 0.001) - lines arrive with a cut OR a blur/flash, each covering
part of them.

Usage:
    python -X utf8 tools/textcompare.py C33 [--ocr screenlines_ja.json] [--tol 0.5] [--lock]
        [--kind lyric|dialogue|...] [--section mad]
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent


def near(a, b, tol):
    return [any(abs(x - y) <= tol for y in b) for x in a]


def merge(ts, gap=0.3):
    out = []
    for t in sorted(ts):
        if not out or t - out[-1] > gap:
            out.append(round(t, 3))
    return out


def scene_cuts(video, thr=0.3):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(video), "-vf",
                        f"scale=320:-1,select='gt(scene,{thr})',showinfo", "-an", "-f", "null", "-"],
                       capture_output=True, text=True, errors="replace")
    return [float(x.split(":")[1]) for x in r.stderr.split() if x.startswith("pts_time:")]


def lock(m, video, onsets, t_range=None):
    sys.path.insert(0, str(ROOT / "tools"))
    from cutdrivers import lock_test
    sc = scene_cuts(video)
    (m / "scene_cuts.json").write_text(json.dumps({"rule": "ffmpeg select gt(scene,0.3) on 320-px copy",
                                                   "cuts_s": [round(x, 3) for x in sc]}, indent=1),
                                       encoding="utf-8", newline="\n")
    sets = {"hard_cuts": sc}
    if (m / "blurdip_auto.json").exists() and (m / "flashwash.json").exists():
        b = json.loads((m / "blurdip_auto.json").read_text(encoding="utf-8"))
        f = json.loads((m / "flashwash.json").read_text(encoding="utf-8"))
        peaks = merge([r["t_min"] for r in b["rows"] if r["label"] in ("blur-bridge", "focus-in")] +
                      [e["t_peak"] for e in f["events"]])
        (m / "transition_peaks.json").write_text(json.dumps({"rule": "blurdip --auto blur-bridge/focus-in t_min + "
                                                             "flashwash t_peak, merged within 0.3 s",
                                                             "peaks_s": peaks}, indent=1),
                                                 encoding="utf-8", newline="\n")
        sets["transition_peaks"] = peaks
        sets["union"] = merge(sc + peaks)
    if t_range:
        sets = {k: [t for t in v if t_range[0] - 3 <= t <= t_range[1] + 3] for k, v in sets.items()}
    out = {}
    for k, v in sets.items():
        r = lock_test(onsets, v)
        r = {kk: vv for kk, vv in r.items() if not isinstance(vv, list)}
        r["locked"] = bool(r.get("p") is not None and r["p"] < 0.05 / len(sets))
        out[k] = r
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("case")
    ap.add_argument("--ocr", default="screenlines_ja.json")
    ap.add_argument("--tol", type=float, default=0.5)
    ap.add_argument("--lock", action="store_true")
    ap.add_argument("--kind", default="lyric")
    ap.add_argument("--section")
    a = ap.parse_args()
    m = ROOT / "measurements" / a.case
    ev = json.loads((m / "text_events_modelread.json").read_text(encoding="utf-8"))["events"]
    if a.section:
        ev = [e for e in ev if e.get("section") == a.section]
    onsets = sorted(e["t_on"] for e in ev if e["kind"] == a.kind)
    anytext = sorted(e["t_on"] for e in ev)
    ocr = json.loads((m / a.ocr).read_text(encoding="utf-8"))["line_starts_s"]
    if a.section and anytext:
        ocr = [t for t in ocr if anytext[0] - a.tol <= t <= anytext[-1] + a.tol]
    rec = np.mean(near(onsets, ocr, a.tol)) if onsets else float("nan")
    prec_any = np.mean(near(ocr, anytext, a.tol)) if ocr else float("nan")
    prec_kind = np.mean(near(ocr, onsets, a.tol)) if ocr else float("nan")
    res = {"case": a.case, "ocr": a.ocr, "tol_s": a.tol, "kind": a.kind, "section": a.section,
           f"n_model_{a.kind}": len(onsets), "n_model_text": len(anytext), "n_ocr": len(ocr),
           f"recall_of_model_{a.kind}": round(float(rec), 3),
           "ocr_precision_vs_any_text": round(float(prec_any), 3),
           f"ocr_precision_vs_{a.kind}": round(float(prec_kind), 3),
           "note": "control is a model frame read, not a human annotation"}
    if a.lock and onsets:
        video = json.loads((m / "text_events_modelread.json").read_text(encoding="utf-8"))["video"]
        rng = (anytext[0], anytext[-1]) if a.section else None
        res[f"{a.kind}_with_picture_change"] = lock(m, video, onsets, rng)
    sec = f"_{a.section}" if a.section else ""
    kind = "" if a.kind == "lyric" else f"_{a.kind}"     # lyric keeps the original file names
    (m / f"{a.kind}_onsets_modelread{sec}.json").write_text(json.dumps(onsets), encoding="utf-8", newline="\n")
    (m / f"textcompare_{Path(a.ocr).stem}{kind}{sec}.json").write_text(json.dumps(res, indent=1),
                                                                       encoding="utf-8", newline="\n")
    print(json.dumps(res))


if __name__ == "__main__":
    main()

"""Measure one video with every calibrated instrument and write one summary.

Runs: contact sheets, beatgrid, springfit (at a common width), phase locking of
spring move starts and motion peaks, loop check (first vs last frame) and cut
count. When --truth <beats.json> is given (a synthetic track with known beat
times) the phase locking uses that exact grid instead of the estimated one.

Usage:
    python -X utf8 tools/measure_arm.py <video> --out <dir> [--truth inputs/beat120.json] [--width 720]
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from avio import load_gray_frames, probe  # noqa: E402
from beatgrid import analyse as beat_analyse, plot as beat_plot, scdet_cuts  # noqa: E402
from phaselock import lock  # noqa: E402
from springfit import analyse as spring_analyse, plot as spring_plot, track  # noqa: E402

HERE = Path(__file__).resolve().parent


def dedup(ts, gap=0.1):
    out = []
    for t in sorted(ts):
        if not out or t - out[-1] > gap:
            out.append(t)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--out", required=True)
    ap.add_argument("--truth")
    ap.add_argument("--width", type=int, default=720)
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    info = probe(a.video)
    subprocess.run([sys.executable, "-X", "utf8", str(HERE / "sheets.py"), a.video, "--out", str(out / "sheets")],
                   check=True)

    bres, series = beat_analyse(a.video)
    (out / "beatgrid.json").write_text(json.dumps(bres, indent=1), encoding="utf-8")
    beat_plot(bres, series, out / "beatgrid.png")

    frames, fps = load_gray_frames(a.video, width=a.width)
    rows = track(frames, fps)
    fits = spring_analyse(rows, fps)
    (out / "springfit.json").write_text(json.dumps({"fits": fits}, indent=1), encoding="utf-8")
    spring_plot(rows, fits, out / "springfit.png", Path(a.video).name)

    if a.truth:
        tr = json.loads(Path(a.truth).read_text(encoding="utf-8"))
        period, phase, grid_src = 60 / tr["bpm"], tr["offset_s"], "truth (synthetic track)"
    else:
        period, phase, grid_src = bres["grid"]["period_s"], bres["grid"]["phase_s"], "estimated from audio"
    starts = dedup([f["t0"] for f in fits if f["nrmse"] <= 0.1])
    peaks = [e["t"] for e in bres["motion_peaks"]]
    good = [f for f in fits if f["spring_consistent"] and f["kind"] != "indicator"]
    ind = [f for f in fits if f["spring_consistent"] and f["kind"] == "indicator"]
    pairs = []
    for f0 in [f for f in ind if f["axis"] == "ind_x0"]:
        for f1 in [f for f in ind if f["axis"] == "ind_x1"]:
            if abs(f0["t0"] - f1["t0"]) < 0.08:
                pairs.append({"t0": round(f0["t0"], 3), "omega_left": round(f0["omega"], 1),
                              "omega_right": round(f1["omega"], 1),
                              "ratio": round(max(f0["omega"], f1["omega"]) / min(f0["omega"], f1["omega"]), 2)})
    first, last = frames[0].astype(float), frames[-1].astype(float)
    summary = {
        "video": a.video, "duration_s": round(info["duration"], 3), "fps": info.get("fps"),
        "size": f"{info.get('width')}x{info.get('height')}", "measured_width": a.width,
        "audio_bpm_estimated": round(bres["grid"]["bpm"], 2),
        "grid_used": grid_src,
        "cuts": len(scdet_cuts(a.video)),
        "loop_first_last_mean_abs_diff": round(float(np.abs(first - last).mean()), 2),
        "phase_lock_move_starts": lock(starts, period, phase) if starts else None,
        "phase_lock_motion_peaks": lock(peaks, period, phase) if peaks else None,
        "springs_consistent_n": len(good),
        "springs_total_n": len([f for f in fits if f["kind"] != "indicator"]),
        "zeta_median": round(float(np.median([f["zeta"] for f in good])), 2) if good else None,
        "omega_median": round(float(np.median([f["omega"] for f in good])), 1) if good else None,
        "overshoot_max": round(max([f["overshoot_measured"] for f in good]), 3) if good else None,
        "indicator_edge_pairs": pairs,
    }
    (out / "measure.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()

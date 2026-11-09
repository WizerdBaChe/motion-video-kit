"""Beat-cut (P2, docs/edit-route-design.md §3): music -> beatgrid grid -> a cut every N beats -> EDL.

The grid comes from tools/beatgrid.py's own estimator (same limits: onset hop 11.6 ms, tempo 70-180 BPM prior-free).
verify() measures a rendered film with beatgrid.analyse: each detected cut against the film's audio grid.
"""
import json
import sys
from pathlib import Path

import numpy as np

import edl as E
from assets import asset_file, load, media_kind
from render import _probe_dur

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import beatgrid  # noqa: E402
from avio import load_audio  # noqa: E402


def grid_of(path) -> dict:
    y, sr = load_audio(str(path))
    env, env_t = beatgrid.onset_envelope(y, sr)
    return beatgrid.estimate_grid(env, env_t)


def plan_cuts(grid, dur_s, beats_per_cut=2, shift_s=0.0, edge_s=0.3):
    beats = np.arange(grid["phase_s"], dur_s, grid["period_s"])
    return [float(t + shift_s) for t in beats[::beats_per_cut] if edge_s <= t + shift_s <= dur_s - edge_s]


def beatcut(film, music_id, clip_ids, out_edl, fps=30, beats_per_cut=2, duration_s=None, shift_s=0.0):
    film = Path(film)
    music = asset_file(film, music_id)
    if media_kind(music) != "audio":
        raise ValueError(f"{music_id} is not audio")
    grid = grid_of(music)
    dur = float(duration_s or _probe_dur(music))
    total = int(round(dur * fps))
    cuts = plan_cuts(grid, total / fps, beats_per_cut, shift_s)
    frames = sorted({int(round(t * fps)) for t in cuts} - {0, total})
    bounds = [0] + frames + [total]
    tl = E.new(Path(out_edl).stem, fps)
    used = {}
    for i, (a, b) in enumerate(zip(bounds, bounds[1:])):
        aid = clip_ids[i % len(clip_ids)]
        f = asset_file(film, aid)
        if media_kind(f) == "video" and _probe_dur(f) + 1e-3 < (b - a) / fps:
            raise ValueError(f"{aid}: {_probe_dur(f):.2f} s is shorter than segment {i} ({(b - a) / fps:.2f} s)")
        E.add_clip(tl, film, aid, 0, b - a, name=f"seg{i:02d}-{aid}")
        used[aid] = load(film, aid)["sha256"]
    E.set_music(tl, film, music_id, 0, total)
    info = {"grid": grid, "beats_per_cut": beats_per_cut, "shift_s": shift_s,
            "declared_cuts_s": [f / fps for f in frames]}
    tl.metadata["mvl"]["beatcut"] = info
    E.save(tl, out_edl)
    return info   # plain dict: OTIO metadata proxies die with the timeline


def verify(video, fps=30, declared=None) -> dict:
    """Detected cuts vs the film's own audio grid (beatgrid.analyse); limits travel with the result.

    Detector: ffmpeg scdet cuts. scdet misses cuts between stills of one palette (seen on ComfyUI pastel images:
    0 of 7), so with `declared` cut times given and scdet finding < 80 % of them, motion onsets (frame difference above
    median + k MAD, after t = 0.1 s) are used instead and `detector` says so. `recall` = share of declared cuts with
    a detected event within 2 frames, so a detector that sees nothing can never pass.
    """
    res, _ = beatgrid.analyse(str(video))
    detector, events = "scdet", res["cuts"]
    if declared and len(events) < 0.8 * len(declared):
        detector, events = "motion_onsets", [e for e in res["motion_onsets"] if e["t"] > 0.1]
    s = beatgrid.summarize(events, fps) or {}
    out = {"detector": detector, "n_cuts": s.get("n", 0), "median_abs_ms": s.get("median_abs_ms"),
           "within_1_frame": s.get("within_1_frame"), "bpm": res["grid"]["bpm"], "frame_ms": 1000 / fps,
           "limits": res["limits"], "cuts": [c["t"] for c in events]}
    if declared:
        tol = 2 / fps + 1e-6
        out["recall"] = sum(any(abs(e["t"] - d) <= tol for e in events) for d in declared) / len(declared)
    return out


if __name__ == "__main__":
    print(json.dumps(verify(sys.argv[1]), indent=1))

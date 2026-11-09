"""Measure grey mid-swap frames: how long a container looks mid-grey while flipping black <-> white.

Per frame: background = median of the border band; foreground = pixels differing from it by
more than FG_DIFF; tone = median foreground luminance, classed dark (<LO), grey (LO..HI) or
bright (>HI). A CROSSING is a dark->bright or bright->dark change of class (empty frames and
grey frames in between allowed). Its grey_s is the time spent in the grey class between the
two ends; peak_midness is how close the greyest frame came to 128 (1 = exactly mid-grey).
A grey run that starts and ends on the SAME side (e.g. a toggle track dimming and returning)
is not a crossing and is reported separately.

Limits: one tone per frame (the median of everything that is not background), so two
containers of opposite tone on screen at once read as whichever covers more pixels; a
translucent card fading into the background reads as empty, not grey.

Usage:
    python -X utf8 tools/swapgrey.py <video> --out <dir> [--width 360]
    python -X utf8 tools/swapgrey.py --selftest
"""
import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from avio import load_gray_frames  # noqa: E402

FG_DIFF = 12      # background varies about +-6 (C05 border p5..p95 = 232..238)
LO, HI = 70, 190  # tone classes
MIN_AREA = 0.003  # fraction of the frame; below it the frame counts as empty


def tones(frames):
    out = []
    for f in frames:
        f = f.astype(np.int16)
        h, w = f.shape
        b = max(2, h // 20)
        border = np.concatenate([f[:b].ravel(), f[-b:].ravel(), f[:, :b].ravel(), f[:, -b:].ravel()])
        bg = np.median(border)
        fg = np.abs(f - bg) > FG_DIFF
        out.append(float(np.median(f[fg])) if fg.mean() >= MIN_AREA else None)
    return out


def cls(v):
    if v is None:
        return None
    return "dark" if v < LO else ("bright" if v > HI else "grey")


def crossings(tv, fps):
    cs = [cls(v) for v in tv]
    ends = [i for i, c in enumerate(cs) if c in ("dark", "bright")]
    found, lingering = [], []
    for a, b in zip(ends, ends[1:]):
        mid = [i for i in range(a + 1, b) if cs[i] == "grey"]
        if cs[a] != cs[b]:
            mids = [1 - abs(tv[i] - 128) / 128 for i in mid]
            found.append({"t": round(a / fps, 3), "direction": f"{cs[a]}->{cs[b]}",
                          "grey_s": round(len(mid) / fps, 3), "grey_frames": len(mid),
                          "gap_s": round((b - a - 1) / fps, 3),
                          "peak_midness": round(max(mids), 3) if mids else 0.0})
        elif mid:
            lingering.append({"t": round(a / fps, 3), "side": cs[a], "grey_s": round(len(mid) / fps, 3)})
    return found, lingering


def analyse(video, width=360):
    frames, fps = load_gray_frames(video, width=width)
    tv = tones(frames)
    found, lingering = crossings(tv, fps)
    g = [c["grey_s"] for c in found]
    return {"video": str(video), "fps": fps, "width": width,
            "thresholds": {"fg_diff": FG_DIFF, "lo": LO, "hi": HI, "min_area": MIN_AREA},
            "n_crossings": len(found), "grey_s_total": round(sum(g), 3),
            "grey_s_median": round(float(np.median(g)), 3) if g else None,
            "grey_s_max": round(max(g), 3) if g else None,
            "crossings": found, "same_side_grey_runs": lingering,
            "tone": [None if v is None else round(v, 1) for v in tv]}, tv, fps


def plot(res, tv, fps, out_png):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    t = np.arange(len(tv)) / fps
    y = np.array([np.nan if v is None else v for v in tv])
    fig, ax = plt.subplots(figsize=(12, 3))
    ax.axhspan(LO, HI, color="0.85", label="grey band")
    ax.plot(t, y, "k.", ms=2)
    for c in res["crossings"]:
        ax.axvline(c["t"], color="tab:red" if c["grey_s"] > 0 else "tab:green", lw=0.8)
    ax.set_ylim(-5, 260)
    ax.set_xlabel("s")
    ax.set_ylabel("container tone")
    ax.set_title(f"{Path(res['video']).name}: {res['n_crossings']} crossings, grey total {res['grey_s_total']} s")
    fig.tight_layout()
    fig.savefig(out_png, dpi=110)
    plt.close(fig)


# ---------- calibration ----------
def synth(path, tone_fn, dur=2.0, fps=60, size=360, bg=236):
    n = int(dur * fps)
    vid = np.full((n, size, size), bg, np.uint8)
    for i in range(n):
        v = tone_fn(i / fps)
        vid[i, 150:210, 120:240] = int(round(np.clip(v, 0, 255)))
    with tempfile.TemporaryDirectory() as td:
        raw = Path(td) / "v.raw"
        raw.write_bytes(vid.tobytes())
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "gray", "-s", f"{size}x{size}",
                        "-r", str(fps), "-i", str(raw), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "12",
                        str(path)], check=True)


def selftest():
    def lerp(t0, d, a, b):
        return lambda t: a + (b - a) * min(max((t - t0) / d, 0), 1)
    # analytic grey time of a linear 0->255 ramp over 0.3 s: fraction (HI-LO)/255 of it
    exp_lin = 0.3 * (HI - LO) / 255
    cases = [
        ("known-true: linear black->white 0.3 s", lerp(0.5, 0.3, 0, 255), 1, exp_lin),
        ("known-true: linear white->black 0.3 s", lerp(0.5, 0.3, 255, 0), 1, exp_lin),
        ("known-false: hard switch", lambda t: 0 if t < 0.8 else 255, 1, 0.0),
        ("known-false: dark stays dark", lambda t: 10, 0, None),
        ("known-false: dark->grey->dark (same side)",
         lambda t: 150 if 0.6 <= t < 0.9 else 10, 0, None),
    ]
    ok = True
    with tempfile.TemporaryDirectory() as td:
        for name, fn, n_exp, g_exp in cases:
            p = Path(td) / "s.mp4"
            synth(p, fn)
            res, _, fps = analyse(p)
            good = res["n_crossings"] == n_exp
            if good and g_exp is not None:
                good = abs(res["crossings"][0]["grey_s"] - g_exp) <= 1.5 / fps
            got = res["crossings"][0]["grey_s"] if res["crossings"] else None
            print(f"{name}: crossings {res['n_crossings']} (want {n_exp}), grey_s {got} "
                  f"(want {None if g_exp is None else round(g_exp, 3)}) -> {'ok' if good else 'FAIL'}")
            ok &= good
    print("SELFTEST", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video", nargs="?")
    ap.add_argument("--out")
    ap.add_argument("--width", type=int, default=360)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        sys.exit(selftest())
    res, tv, fps = analyse(a.video, a.width)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "swapgrey.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    plot(res, tv, fps, out / "swapgrey.png")
    print(f"{res['n_crossings']} crossings, grey total {res['grey_s_total']} s, median {res['grey_s_median']} s")
    for c in res["crossings"]:
        print(f"  {c['t']:6.2f}s {c['direction']:13s} grey {c['grey_s']:.3f}s midness {c['peak_midness']}")


if __name__ == "__main__":
    main()

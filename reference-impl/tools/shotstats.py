"""Shot-length statistics and a colour barcode for one video (T-shotstats; idea borrowed from CadensView, 2026-11-02).

Question it serves: how a film is cut as a whole -- how many shots, how long they run (mean AND median, because a
few very long shots pull the mean up: one measured episode reads ASL 5.27 s but MSL 2.36 s), which shot is longest or shortest,
and how the colour moves along the film. One number pair (ASL, MSL) and one strip image compare films at a glance;
every number carries a shot index and a time code so a reader can go back to the frame.

Cuts. Either given (--cuts t1,t2,.. | --cuts-json F, which reads a plain list, segments.py `events[].t`, or mfp
sheet `cutTimes`) or detected here. Hard cuts: a numpy re-implementation of the published PySceneDetect
AdaptiveDetector method (no scenedetect dependency), with one change -- hue is compared only where both pixels
have saturation >= 24 and as a circular distance, because hue is undefined near white/grey and its noise read
as cuts on fades through white (2026-11-02):
    content(k)  = mean of |dH|, |dS|, |dV| between frames k-1 and k (OpenCV HSV, frames scaled to 128x72);
    ratio(k)    = content(k) / mean(content over the --window frames on each side, k excluded);
    cut at k    if ratio >= --ratio (3.0) and content >= --min-content (15.0);
    a cut closer than --min-shot s (0.2) to the previous kept cut is dropped (sequential, like min_scene_len).
Dip boundaries: a run of near-blank frames (luma std < --dip-std, 1.0 at 128x72) with content on both sides is a
fade out and in through white or black; a run up to 1.5 s gives one boundary at its centre, a longer run is a
shot of its own. Hard cuts win within --min-shot. Each shot records `starts_with` (hard / dip / given). Real
basis: C55 opening fades measured std 0.2-0.8 at the dips vs 4-45 in pale line-art shots.
The edges term (--weights h,s,v,e; PySceneDetect's delta_edges) is off by default: on C54's pencil line art it
doubled the shot count from line boil and found none of C55's fades (probe variants.md).
Frames are streamed one at a time, so a full episode does not have to fit in memory.

Colour. Each frame's mean is taken in linear RGB (sRGB decoded, averaged, encoded back), so a half-black,
half-white frame reads mid-grey in light, not in code values. A shot's colour is the mean of its frames' means.
The barcode PNG has two rows on one time axis: per shot (block width = shot duration) and per second.

Method stamp. `method` lists every parameter plus a version; `method_key` is its sha256[:12]. A JSON whose
method_key differs from the current one was measured differently and is not comparable.

Calibration (--selftest, synthetic clips encoded through ffmpeg): known-true -- five textured shots of 2.0 / 0.5 /
3.0 / 1.0 / 4.0 s at 24 fps must give 4 cuts within 1 frame, ASL 2.10, MSL 2.00, and each shot colour within 6
code values of the linear-light mean of its raw frames (the code-value base colours must fail that check: a
textured shot's light mean is not its base colour); known-false -- one textured shot panning 4 px/frame with a
slow brightness drift must give 0 cuts; stats -- a given cut list must give exact ASL/MSL/longest/shortest;
dip -- a pale shot fading through white into another must give one `dip` boundary near the white run's centre,
the same clip with dips off must give none (the dip rule is what fires), and a pale non-blank shot must give none.
A 1 s dissolve between two still shots is reported, not asserted (reads 1 shot: missed).
Real controls: experiments/probe-shotstats-2026-11-02/REPORT.md (junctions of concatenated real clips at known
times; cut sheets read on C55 and C54).

What it cannot determine: a dissolve that never passes a near-blank frame (missed); hand-drawn fast action with
impact frames, smears or white flashes is over-split (C54 fight: one action read as 3-4 shots), and layered
double exposures can split (C55 17-18 s); a long shot may be missed inside a fast blurred montage; variable frame
rate (times assume constant fps); whether a "shot" is one camera setup. Code-rendered motion graphics change by
slides and soft swaps, not cuts (C45, 12 min, reads 2 shots): give it segments.py events with --cuts-json.
Read the sheet before citing a number.

Usage:
    python -X utf8 tools/shotstats.py <video> --out <dir> [--label NAME] [--cuts t,.. | --cuts-json F]
    python -X utf8 tools/shotstats.py --compare <dir|json> <dir|json> .. --out <dir>
    python -X utf8 tools/shotstats.py --selftest
"""
import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
from avio import probe  # noqa: E402

VERSION = "shotstats-v1"
SCAN_W, SCAN_H = 128, 72
HUE_SAT_MIN = 24              # OpenCV S (0-255) below which a pixel's hue is not compared
DEFAULT_WEIGHTS = "1,1,1,0"   # PySceneDetect ContentDetector default; see the probe for the edges variant
HIST_EDGES = [0, 0.5, 1, 1.5, 2, 3, 4, 6, 8, 12, 16, 24, 32, 1e9]   # seconds, fixed so films compare
BAR_W, ROW_H, AXIS_H = 1200, 60, 18


# ---------- colour ----------

def srgb_to_linear(c):
    c = np.asarray(c, dtype=np.float64) / 255.0
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def linear_to_srgb8(c):
    c = np.clip(np.asarray(c, dtype=np.float64), 0, 1)
    s = np.where(c <= 0.0031308, c * 12.92, 1.055 * c ** (1 / 2.4) - 0.055)
    return np.round(s * 255).astype(int)


def hexof(rgb):
    return "#{:02x}{:02x}{:02x}".format(*[int(v) for v in rgb])


# ---------- scan ----------

def parse_weights(s):
    w = [float(x) for x in str(s).split(",")]
    if len(w) != 4 or sum(w) <= 0:
        raise SystemExit("--weights needs four non-negative numbers h,s,v,edges")
    return w


def method_dict(a):
    return {"version": VERSION, "scan": f"{SCAN_W}x{SCAN_H}",
            "content": "weighted mean of |dH|,|dS|,|dV|,|dEdges| (OpenCV HSV; dH circular, only where both S >= "
                       f"{HUE_SAT_MIN}; Canny on V, auto thresholds, dilated)",
            "weights_hsve": parse_weights(a.weights), "dip_std": a.dip_std, "dip_long_s": 1.5,
            "ratio": a.ratio, "window": a.window, "min_content": a.min_content, "min_shot_s": a.min_shot,
            "colour": "linear-RGB mean per frame, sRGB-encoded", "hist_edges_s": HIST_EDGES[:-1]}


def method_key(m):
    return hashlib.sha256(json.dumps(m, sort_keys=True).encode()).hexdigest()[:12]


def edges_of(v):
    med = float(np.median(v))
    e = cv2.Canny(v, int(max(0, 0.67 * med)), int(min(255, 1.33 * med)))
    return cv2.dilate(e, np.ones((3, 3), np.uint8)).astype(np.int16)


def scan(video, weights=(1, 1, 1, 0)):
    """Stream frames: per-frame content score vs previous frame, and per-frame linear-RGB mean."""
    w = np.array(weights, dtype=float)
    info = probe(video)
    proc = subprocess.Popen(["ffmpeg", "-v", "error", "-i", str(video), "-vf", f"scale={SCAN_W}:{SCAN_H}",
                             "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
    size = SCAN_W * SCAN_H * 3
    lut = srgb_to_linear(np.arange(256))
    scores, means, stds, prev = [], [], [], None
    while True:
        buf = proc.stdout.read(size)
        if len(buf) < size:
            break
        rgb = np.frombuffer(buf, np.uint8).reshape(SCAN_H, SCAN_W, 3)
        stds.append(float(cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY).std()))
        hsv8 = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
        cur = (hsv8.astype(np.int16), edges_of(hsv8[:, :, 2]) if w[3] else None)
        means.append(lut[rgb].reshape(-1, 3).mean(0))
        if prev is None:
            scores.append(0.0)
        else:
            # hue is undefined at low saturation: count |dH| (circular, 0-90 on OpenCV's 0-179 scale) only where
            # both pixels carry colour, else near-white / near-grey frames read hue noise as a cut
            dh = np.abs(cur[0][:, :, 0] - prev[0][:, :, 0])
            dh = np.minimum(dh, 180 - dh)
            dh[np.minimum(cur[0][:, :, 1], prev[0][:, :, 1]) < HUE_SAT_MIN] = 0
            d = [float(dh.mean())] + [float(np.abs(cur[0][:, :, c] - prev[0][:, :, c]).mean()) for c in (1, 2)]
            d.append(float(np.abs(cur[1] - prev[1]).mean()) if w[3] else 0.0)
            scores.append(float(np.dot(w, d) / w.sum()))
        prev = cur
    proc.wait()
    if proc.returncode:
        raise SystemExit(f"ffmpeg failed on {video}")
    return np.array(scores), np.array(means), info["fps"], np.array(stds)


def dips(stds, fps, dip_std=1.0, long_s=1.5):
    """Boundaries from runs of near-blank frames (luma std < dip_std) with content on both sides.

    A run up to long_s gives one boundary at its centre (fade out to white/black, fade in to the next shot);
    a longer run is a shot of its own, bounded at both edges. Runs touching the first or last frame are skipped.
    """
    if dip_std <= 0:
        return []
    blank = stds < dip_std
    out, k, n = [], 0, len(stds)
    while k < n:
        if not blank[k]:
            k += 1
            continue
        j = k
        while j < n and blank[j]:
            j += 1
        if k > 0 and j < n:
            if (j - k) / fps <= long_s:
                out.append(((k + j) / 2) / fps)
            else:
                out += [k / fps, j / fps]
        k = j
    return out


def merge(hard, dip, min_shot):
    """Hard cuts win; a dip boundary closer than min_shot to a kept boundary is dropped."""
    kept = [(t, "hard") for t in hard]
    for t in dip:
        if all(abs(t - u) >= min_shot for u, _ in kept):
            kept.append((t, "dip"))
    return sorted(kept)


def detect(scores, fps, ratio=3.0, window=2, min_content=15.0, min_shot=0.2):
    n, cuts, last = len(scores), [], 0
    for k in range(1, n):
        nb = [scores[j] for j in range(max(1, k - window), min(n, k + window + 1)) if j != k]
        avg = max(float(np.mean(nb)) if nb else 0.0, 1e-3)
        if scores[k] >= min_content and scores[k] / avg >= ratio and (k - last) / fps >= min_shot:
            cuts.append(k)
            last = k
    return cuts


# ---------- stats ----------

def shots_from_cuts(cut_times, duration):
    edges = [0.0] + sorted(t for t in cut_times if 0 < t < duration) + [duration]
    return [(edges[i], edges[i + 1]) for i in range(len(edges) - 1) if edges[i + 1] - edges[i] > 1e-6]


def stats(shots):
    d = np.array([b - a for a, b in shots])
    il, is_ = int(d.argmax()), int(d.argmin())
    hist = np.histogram(d, bins=HIST_EDGES)[0].tolist()
    asl, msl = float(d.mean()), float(np.median(d))
    return {"n_shots": len(d), "asl_s": round(asl, 3), "msl_s": round(msl, 3),
            "asl_over_msl": round(asl / msl, 3) if msl else None,
            "p10_s": round(float(np.percentile(d, 10)), 3), "p90_s": round(float(np.percentile(d, 90)), 3),
            "longest": {"shot": il + 1, "t0": round(shots[il][0], 3), "dur_s": round(float(d[il]), 3)},
            "shortest": {"shot": is_ + 1, "t0": round(shots[is_][0], 3), "dur_s": round(float(d[is_]), 3)},
            "hist": {"edges_s": HIST_EDGES[:-1], "counts": hist}}


def tc(t):
    m, s = divmod(t, 60)
    return f"{int(m):02d}:{s:05.2f}"


def load_cuts(a):
    if a.cuts:
        return [float(x) for x in a.cuts.split(",") if x.strip()]
    d = json.loads(Path(a.cuts_json).read_text(encoding="utf-8"))
    if isinstance(d, list):
        return [float(x["t"] if isinstance(x, dict) else x) for x in d]
    if "events" in d:
        return [float(e["t"]) for e in d["events"]]
    if "cutTimes" in d:
        return [float(x) for x in d["cutTimes"]]
    raise SystemExit("cuts json: expected a list, segments.py events[] or mfp sheet cutTimes")


def measure(video, a, label=None):
    scores, means, fps, stds = scan(video, parse_weights(a.weights))
    n = len(scores)
    duration = n / fps
    if a.cuts or a.cuts_json:
        bounds, source = [(t, "given") for t in sorted(load_cuts(a))], "given"
    else:
        hard = [k / fps for k in detect(scores, fps, a.ratio, a.window, a.min_content, a.min_shot)]
        bounds, source = merge(hard, dips(stds, fps, a.dip_std), a.min_shot), "detected"
    kind_at = {round(t, 6): kd for t, kd in bounds}
    shots = shots_from_cuts([t for t, _ in bounds], duration)
    rows = []
    for i, (t0, t1) in enumerate(shots):
        f0, f1 = int(round(t0 * fps)), max(int(round(t1 * fps)), int(round(t0 * fps)) + 1)
        col = linear_to_srgb8(means[f0:min(f1, n)].mean(0))
        rows.append({"shot": i + 1, "t0": round(t0, 3), "t1": round(t1, 3), "dur_s": round(t1 - t0, 3),
                     "frames": f1 - f0, "colour": hexof(col),
                     "starts_with": "start" if i == 0 else kind_at.get(round(t0, 6), "?")})
    per_sec = [hexof(linear_to_srgb8(means[int(s * fps):max(int((s + 1) * fps), int(s * fps) + 1)].mean(0)))
               for s in range(int(np.ceil(duration))) if int(s * fps) < n]
    m = method_dict(a)
    return {"video": str(video), "label": label or Path(video).stem, "fps": round(fps, 3), "frames": n,
            "duration_s": round(duration, 3), "cut_source": source, "method": m, "method_key": method_key(m),
            "stats": dict(stats(shots), boundaries={k: sum(1 for _, kd in bounds if kd == k)
                                                    for k in ("hard", "dip", "given")}),
            "shots": rows, "per_second": per_sec,
            "limits": "a dissolve that never passes through a near-blank frame is usually missed; a white flash "
                      "may add a short shot; whip pans, fast blurred action and layered double exposures may add "
                      "false cuts; times assume constant fps; read the sheet before citing a shot as one setup"}


# ---------- pictures ----------

def font(size):
    for f in ("C:/Windows/Fonts/msjh.ttc", "C:/Windows/Fonts/meiryo.ttc", "C:/Windows/Fonts/arial.ttf"):
        try:
            return ImageFont.truetype(f, size)
        except OSError:
            continue
    return ImageFont.load_default()


def draw_strip(res, draw, y, x0=0, w=BAR_W):
    dur = res["duration_s"]
    for s in res["shots"]:
        a, b = x0 + int(s["t0"] / dur * w), x0 + max(int(s["t1"] / dur * w), int(s["t0"] / dur * w) + 1)
        draw.rectangle([a, y, b - 1, y + ROW_H - 1], fill=s["colour"])
    secs = res["per_second"]
    for i, c in enumerate(secs):
        a, b = x0 + int(i / dur * w), x0 + max(int(min(i + 1, dur) / dur * w), int(i / dur * w) + 1)
        draw.rectangle([a, y + ROW_H + 2, b - 1, y + 2 * ROW_H + 1], fill=c)
    step = next(s for s in (5, 10, 30, 60, 120, 300, 600) if dur / s <= 12)
    f = font(11)
    t = 0
    while t <= dur:
        x = x0 + int(t / dur * w)
        draw.line([x, y + 2 * ROW_H + 2, x, y + 2 * ROW_H + 6], fill="#888888")
        draw.text((x + 2, y + 2 * ROW_H + 3), tc(t)[:5], fill="#888888", font=f)
        t += step


def barcode_png(res, path):
    st = res["stats"]
    img = Image.new("RGB", (BAR_W, 2 * ROW_H + AXIS_H + 28), "#1b1f24")
    d = ImageDraw.Draw(img)
    d.text((4, 4), f"{res['label']}  shots {st['n_shots']}  ASL {st['asl_s']:.2f}s  MSL {st['msl_s']:.2f}s  "
                   f"longest #{st['longest']['shot']} {st['longest']['dur_s']:.2f}s @ {tc(st['longest']['t0'])}  "
                   f"(top: per shot, bottom: per second)", fill="#e6e6e6", font=font(13))
    draw_strip(res, d, 26)
    img.save(path)


def grab(video, t, width=240):
    """One frame at t as an RGB array (fast seek), or None past the end."""
    r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{max(t, 0):.3f}", "-i", str(video), "-frames:v", "1",
                        "-vf", f"scale={width}:-2", "-f", "image2pipe", "-vcodec", "png", "-"], capture_output=True)
    if r.returncode or not r.stdout:
        return None
    import io
    return Image.open(io.BytesIO(r.stdout)).convert("RGB")


def swatch_sheets(res, out, cols=6, rows=8, thumb=240):
    """Each shot's middle frame beside its colour, so a reader (human or model) checks the colour against the
    picture. Bar left = the shot's colour (mean of all its frames); bar right = this one frame's own linear-light
    mean. A big gap between the two means the shot's colour changes inside it, not that the reading is wrong."""
    lut = srgb_to_linear(np.arange(256))
    shots, th = res["shots"], int(thumb * 9 / 16)
    cell_h = th + 34
    per = cols * rows
    paths, gaps = [], []
    Path(out).mkdir(parents=True, exist_ok=True)
    for p in range(0, len(shots), per):
        page = shots[p:p + per]
        img = Image.new("RGB", (cols * (thumb + 8) + 8, ((len(page) + cols - 1) // cols) * (cell_h + 8) + 30), "#1b1f24")
        d = ImageDraw.Draw(img)
        d.text((8, 6), f"{res['label']}  shots {p + 1}-{p + len(page)} of {len(shots)}  bar: left = shot colour "
                       f"(all frames), right = this frame's mean", fill="#e6e6e6", font=font(13))
        for i, s in enumerate(page):
            x, y = 8 + (i % cols) * (thumb + 8), 30 + (i // cols) * (cell_h + 8)
            fr = grab(res["video"], (s["t0"] + s["t1"]) / 2, thumb)
            if fr is not None:
                fr = fr.resize((thumb, th))
                img.paste(fr, (x, y))
                own = hexof(linear_to_srgb8(lut[np.asarray(fr)].reshape(-1, 3).mean(0)))
            else:
                own = "#000000"
            gaps.append({"shot": s["shot"], "t0": s["t0"], "dur_s": s["dur_s"], "shot_colour": s["colour"],
                         "mid_frame_colour": own, "gap": round(float(np.linalg.norm(
                             np.array(list(bytes.fromhex(s["colour"][1:])), float) - np.array(list(bytes.fromhex(own[1:])), float))), 1)})
            d.rectangle([x, y + th + 2, x + thumb // 2 - 1, y + th + 18], fill=s["colour"])
            d.rectangle([x + thumb // 2, y + th + 2, x + thumb - 1, y + th + 18], fill=own)
            d.text((x, y + th + 20), f"#{s['shot']} {tc(s['t0'])} {s['dur_s']:.2f}s {s['colour']}", fill="#bbbbbb",
                   font=font(11))
        path = Path(out) / f"swatches_p{p // per + 1:02d}.png"
        img.save(path)
        paths.append(path)
    # gap = 8-bit sRGB distance between the shot colour and its middle frame's own mean; large = colour moves
    # inside the shot (a missed cut, a fade, a flash), small = the bar stands for the picture
    g = sorted(x["gap"] for x in gaps)
    summary = {"method_key": res["method_key"], "n": len(g), "gap_median": g[len(g) // 2] if g else None,
               "gap_max": g[-1] if g else None, "over_40": [x for x in gaps if x["gap"] > 40], "shots": gaps}
    (Path(out) / "swatches.json").write_text(json.dumps(summary, indent=1), encoding="utf-8", newline="\n")
    return paths


def compare(paths, out):
    rs = []
    for p in paths:
        p = Path(p)
        rs.append(json.loads((p / "shotstats.json" if p.is_dir() else p).read_text(encoding="utf-8")))
    keys = {r["method_key"] for r in rs}
    block = 2 * ROW_H + AXIS_H + 30
    img = Image.new("RGB", (BAR_W, block * len(rs)), "#1b1f24")
    d = ImageDraw.Draw(img)
    lines = ["| film | shots | ASL s | MSL s | ASL/MSL | longest | shortest | cuts |", "|---|---|---|---|---|---|---|---|"]
    for i, r in enumerate(rs):
        st = r["stats"]
        y = i * block
        d.text((4, y + 4), f"{r['label']}  ({tc(r['duration_s'])})  shots {st['n_shots']}  ASL {st['asl_s']:.2f}s  "
                           f"MSL {st['msl_s']:.2f}s", fill="#e6e6e6", font=font(13))
        draw_strip(r, d, y + 26)
        lines.append(f"| {r['label']} | {st['n_shots']} | {st['asl_s']:.2f} | {st['msl_s']:.2f} | "
                     f"{st['asl_over_msl']} | #{st['longest']['shot']} {st['longest']['dur_s']:.2f} s @ "
                     f"{tc(st['longest']['t0'])} | #{st['shortest']['shot']} {st['shortest']['dur_s']:.2f} s | "
                     f"{r['cut_source']} |")
    out.mkdir(parents=True, exist_ok=True)
    img.save(out / "compare.png")
    note = "" if len(keys) == 1 else f"\n\nWARNING: method_key differs across rows ({sorted(keys)}): not comparable.\n"
    (out / "compare.md").write_text("Generated by tools/shotstats.py --compare; colour strips in compare.png.\n\n"
                                    + "\n".join(lines) + note + "\n", encoding="utf-8", newline="\n")
    print("\n".join(lines) + note)


# ---------- selftest ----------

def _encode(frames, fps, path):
    h, w, _ = frames[0].shape
    p = subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}",
                        "-r", str(fps), "-i", "-", "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", str(path)],
                       input=b"".join(f.tobytes() for f in frames))
    assert p.returncode == 0


def _texture(rng, h, w, base, amp=40):
    t = rng.integers(-amp, amp + 1, size=(h // 8, w // 8, 1))
    t = np.repeat(np.repeat(t, 8, 0), 8, 1)
    return np.clip(np.array(base)[None, None, :] + t, 0, 255).astype(np.uint8)


def selftest():
    ok = True
    rng = np.random.default_rng(7)
    fps, H, W = 24, 144, 256
    a = argparse.Namespace(ratio=3.0, window=2, min_content=15.0, min_shot=0.2, cuts=None, cuts_json=None,
                           weights=DEFAULT_WEIGHTS, dip_std=1.0)
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        # known-true: textured shots with local motion inside each
        lens = [2.0, 0.5, 3.0, 1.0, 4.0]
        bases = [(200, 60, 50), (40, 90, 200), (230, 220, 200), (30, 30, 30), (60, 170, 80)]
        frames, truth, expect = [], [], []
        for L, base in zip(lens, bases):
            tex = _texture(rng, H, W, base)
            n0 = len(frames)
            for k in range(int(L * fps)):
                f = np.roll(tex, k, axis=1).copy()
                f[60:84, (k * 3) % W:(k * 3) % W + 20] = 255          # a small moving object
                frames.append(f)
            truth.append(len(frames))
            expect.append(linear_to_srgb8(np.mean([srgb_to_linear(f).reshape(-1, 3).mean(0) for f in frames[n0:]], 0)))
        _encode(frames, fps, td / "true.mp4")
        r = measure(td / "true.mp4", a, "known-true")
        got = [round(s["t0"] * fps) for s in r["shots"][1:]]
        want = truth[:-1]
        good = len(got) == len(want) and all(abs(g - w) <= 1 for g, w in zip(got, want))
        st = r["stats"]
        good_stats = abs(st["asl_s"] - 2.1) < 0.05 and abs(st["msl_s"] - 2.0) < 0.05 and st["longest"]["shot"] == 5
        cols = [tuple(int(r["shots"][i]["colour"][j:j + 2], 16) for j in (1, 3, 5)) for i in range(len(r["shots"]))]
        good_col = len(cols) == 5 and all(max(abs(c - b) for c, b in zip(col, e)) <= 6
                                          for col, e in zip(cols, expect))
        print(f"  {'ok  ' if good else 'FAIL'} known-true cuts (frames): got {got} want {want}")
        print(f"  {'ok  ' if good_stats else 'FAIL'} known-true stats: ASL {st['asl_s']} (2.10) MSL {st['msl_s']} (2.00) "
              f"longest #{st['longest']['shot']} (5)")
        print(f"  {'ok  ' if good_col else 'FAIL'} known-true colours (linear mean of the raw frames, +-6 after codec): "
              f"{[r['shots'][i]['colour'] for i in range(len(cols))]} vs {[hexof(e) for e in expect]}")
        # negative control for the colour check: the plain base colours must NOT all pass for the textured shots
        naive = all(max(abs(c - b) for c, b in zip(col, base)) <= 6 for col, base in zip(cols, bases))
        print(f"  {'ok  ' if not naive else 'FAIL'} colour check discriminates: code-value base colours "
              f"{'fail' if not naive else 'pass'} it (want fail)")
        ok &= not naive
        ok &= good and good_stats and good_col
        # known-false: one panning textured shot with slow brightness drift
        tex = _texture(rng, H, W * 3, (120, 110, 100))
        frames = []
        for k in range(6 * fps):
            f = tex[:, k * 4 % (2 * W): k * 4 % (2 * W) + W].astype(np.int16) + int(k * 0.5)
            frames.append(np.clip(f, 0, 255).astype(np.uint8))
        _encode(frames, fps, td / "false.mp4")
        r = measure(td / "false.mp4", a, "known-false")
        good = r["stats"]["n_shots"] == 1
        print(f"  {'ok  ' if good else 'FAIL'} known-false pan + drift: shots {r['stats']['n_shots']} (want 1)")
        ok &= good
        # documented limit: 1 s dissolve between two shots (reported, not asserted)
        A, B = _texture(rng, H, W, (200, 60, 50)), _texture(rng, H, W, (40, 90, 200))
        frames = [A] * (2 * fps) + [((1 - k / fps) * A + k / fps * B).astype(np.uint8) for k in range(fps)] + [B] * (2 * fps)
        _encode(frames, fps, td / "dissolve.mp4")
        r = measure(td / "dissolve.mp4", a, "dissolve")
        print(f"  info dissolve 1 s: shots {r['stats']['n_shots']} (a miss reads 1; documented limit)")
        # known-true dip: shot A fades out to white over 0.5 s, holds white 3 frames, shot B fades in over 0.5 s
        # (pale line-art style: low-contrast shots, no frame-to-frame jump big enough for the hard-cut test)
        A, B = _texture(rng, H, W, (225, 230, 240), 12), _texture(rng, H, W, (230, 225, 235), 12)
        white = np.full_like(A, 248)
        fade = 12
        frames = ([np.roll(A, k, 1) for k in range(2 * fps)]
                  + [((1 - k / fade) * A + k / fade * white).astype(np.uint8) for k in range(fade)]
                  + [white] * 3
                  + [((1 - k / fade) * white + k / fade * B).astype(np.uint8) for k in range(fade)]
                  + [np.roll(B, k, 1) for k in range(2 * fps)])
        centre = (2 * fps + fade + 1.5) / fps
        _encode(frames, fps, td / "dip.mp4")
        r = measure(td / "dip.mp4", a, "dip")
        b = [(s["t0"], s["starts_with"]) for s in r["shots"][1:]]
        good = len(b) == 1 and b[0][1] == "dip" and abs(b[0][0] - centre) <= 0.25
        print(f"  {'ok  ' if good else 'FAIL'} known-true fade through white: boundaries {b} want one dip near {centre:.2f}")
        ok &= good
        # same clip with dips off: the hard-cut test alone must not see it (shows the dip rule is what fires)
        r = measure(td / "dip.mp4", argparse.Namespace(**dict(vars(a), dip_std=0.0)), "dip-off")
        good = r["stats"]["n_shots"] == 1
        print(f"  {'ok  ' if good else 'FAIL'} same clip, dips off: shots {r['stats']['n_shots']} (want 1)")
        ok &= good
        # known-false dip: a pale, low-contrast but non-blank shot (luma std ~3) must give no boundary
        P = _texture(rng, H, W, (235, 235, 238), 6)
        _encode([np.roll(P, k, 1) for k in range(4 * fps)], fps, td / "pale.mp4")
        r = measure(td / "pale.mp4", a, "pale")
        good = r["stats"]["n_shots"] == 1
        print(f"  {'ok  ' if good else 'FAIL'} known-false pale non-blank shot: shots {r['stats']['n_shots']} (want 1)")
        ok &= good
    # stats on a given cut list
    st = stats(shots_from_cuts([1.0, 4.0, 4.5, 10.0], 12.0))
    good = (st["n_shots"] == 5 and abs(st["asl_s"] - 2.4) < 1e-9 and abs(st["msl_s"] - 2.0) < 1e-9
            and st["longest"] == {"shot": 4, "t0": 4.5, "dur_s": 5.5} and st["shortest"]["shot"] == 3)
    print(f"  {'ok  ' if good else 'FAIL'} stats on given cuts: ASL {st['asl_s']} (2.4) MSL {st['msl_s']} (2.0) "
          f"longest {st['longest']} shortest #{st['shortest']['shot']}")
    ok &= good
    print("selftest", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video", nargs="?")
    ap.add_argument("--out")
    ap.add_argument("--label")
    ap.add_argument("--cuts", help="comma-separated cut times in s")
    ap.add_argument("--cuts-json", help="list | segments.py json | mfp sheet json")
    ap.add_argument("--ratio", type=float, default=3.0)
    ap.add_argument("--window", type=int, default=2)
    ap.add_argument("--min-content", type=float, default=15.0)
    ap.add_argument("--min-shot", type=float, default=0.2)
    ap.add_argument("--weights", default=DEFAULT_WEIGHTS, help="h,s,v,edges weights of the content score")
    ap.add_argument("--dip-std", type=float, default=1.0,
                    help="luma std (0-255, at 128x72) below which a frame is near-blank; 0 turns dip boundaries off")
    ap.add_argument("--compare", nargs="+")
    ap.add_argument("--swatches", action="store_true",
                    help="also write swatches_pNN.png: each shot's middle frame with its colour, for checking")
    ap.add_argument("--swatches-from", help="write swatch sheets for an existing shotstats.json (or its dir)")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if a.compare:
        compare(a.compare, Path(a.out))
        return 0
    if a.swatches_from:
        p = Path(a.swatches_from)
        p = p / "shotstats.json" if p.is_dir() else p
        res = json.loads(p.read_text(encoding="utf-8"))
        for q in swatch_sheets(res, Path(a.out) if a.out else p.parent):
            print(q)
        return 0
    if not (a.video and a.out):
        ap.error("video and --out required")
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    res = measure(Path(a.video), a, a.label)
    (out / "shotstats.json").write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding="utf-8", newline="\n")
    barcode_png(res, out / "barcode.png")
    if a.swatches:
        swatch_sheets(res, out)
    st = res["stats"]
    print(f"{res['label']}: {st['n_shots']} shots in {res['duration_s']} s ({res['cut_source']}); ASL {st['asl_s']} s, "
          f"MSL {st['msl_s']} s; longest #{st['longest']['shot']} {st['longest']['dur_s']} s @ {tc(st['longest']['t0'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

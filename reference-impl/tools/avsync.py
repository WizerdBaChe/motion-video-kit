"""Audio-visual co-axis: put every narration line next to what the picture does while it is said.

Inputs: a video and a transcript .srt of the same video (post-brief / speech-subtitle output).

Frames are decoded at --fps (default 10), scaled to --width (default 320) and greyscaled. Bands
given with --exclude (height fractions, e.g. 0.80:1.0 for a burned subtitle strip, repeatable)
are ignored. For each consecutive frame pair:

    changed share = changed pixels (|grey diff| > --thr) / kept pixels
    active        = changed share > --move-min (0.002)

A VISUAL ONSET is the first active pair after at least --quiet s of inactive pairs: something
starts to change after a pause (a card fades in, a terminal line types, a page dissolves). Its
time is the midpoint of the pair; its region is the bounding box (fractions of the frame) of the
changed pixels over the first 0.3 s of the onset.

Reported:
- per line: start, end, text, the onsets inside [start - --pre, end), and lag = first onset -
  start (`avsync.md`, `avsync.json`);
- lock: onset times vs line starts, the same statistic and shifted control as narrlock.py
  (median |dt| to the nearest line start; p = share of +-3 s shifted onset sets at least as
  close), plus `lines_with_onset` = share of lines with an onset in [start - 0.3, start + 1.0]
  and its value under the same shifts (`cover_null_mean`, `cover_p`);
- line sheets (`--sheets`): one row per line = time, text, three colour thumbnails (start - 0.2 s,
  start + 0.6 s, end - 0.1 s) and a strip marking the onsets inside the line (black tick = line start). Read these, not only
  the numbers.

Calibration (selftest, synthetic 320x180 at 10 fps, lines every 2-4 s, a subtitle strip in the
bottom 20 % that changes at every line start):
- known-true: cards fade in at line starts + N(0.1, 0.15) s, pages clear every 5 lines; with the
  strip excluded must give p < 0.05, median |dt| < 0.35 s and >= 90 % of true entries found
  within 0.2 s;
- known-false: cards at uniform random times; with the strip excluded p > 0.1 in >= 4/5 seeds;
- confound control: the same known-false films WITHOUT --exclude must read locked (p < 0.05) in
  >= 4/5 seeds, i.e. a burned subtitle alone fakes narration lock, which is why --exclude exists;
- round trip: the known-true film encoded to H.264 and read back through ffmpeg must still lock.

What it cannot determine: what an onset IS (card, cursor blink, background loop) - read the
sheets; continuous motion (a camera drift, a looping ambience) has no pauses, so few onsets; a
fade slower than --thr grey levels per frame reads as still; a moving subtitle position or a
caption box outside the excluded band is counted as picture. Machine transcripts split lines
where the engine heard a pause, not where the script did; transcript timing error enters dt.
Text on the sheets is the transcript (machine), not the on-screen words.

Usage:
    python -X utf8 tools/avsync.py <video> --srt <file.srt> --out <dir> [--exclude 0.8:1.0] [--sheets]
           [--sheet-window T0:T1] [--fps 10 --width 320 --thr 20 --move-min 0.002 --quiet 0.3]
    python -X utf8 tools/avsync.py --selftest
"""
import argparse
import json
import re
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from avio import probe  # noqa: E402
from narrlock import lock  # noqa: E402

SRT = re.compile(r"(\d+):(\d\d):(\d\d)[,.](\d\d\d)\s*-->\s*(\d+):(\d\d):(\d\d)[,.](\d\d\d)[^\n]*\n(.*?)(?:\n\s*\n|\Z)",
                 re.S)
FONT = "C:/Windows/Fonts/msjh.ttc"


def parse_srt(text):
    out = []
    for m in SRT.finditer(text.replace("\r\n", "\n")):
        g = m.groups()
        a = int(g[0]) * 3600 + int(g[1]) * 60 + int(g[2]) + int(g[3]) / 1000
        b = int(g[4]) * 3600 + int(g[5]) * 60 + int(g[6]) + int(g[7]) / 1000
        out.append({"start": round(a, 3), "end": round(b, 3), "text": " ".join(g[8].split())})
    return sorted(out, key=lambda x: x["start"])


def keep_mask(h, w, excludes):
    keep = np.ones((h, w), bool)
    for y0, y1 in excludes:
        keep[int(round(y0 * h)):int(round(y1 * h)), :] = False
    return keep


TILE = 8
LOOP_JITTER = 2  # pairs (0.2 s at 10 fps): C45's progress bar repeats every 0.50 s exactly


def onsets_from_changes(changed_maps, fps, move_min, quiet, keep, loop_window=4.0, loop_bursts=4):
    """changed_maps: iterable of bool [H,W] maps for pairs (i-1, i), i = 1..N-1.

    Loop suppression: a TILE x TILE tile whose last loop_bursts STARTS (changed now, unchanged in
    the previous pair) fall inside the previous loop_window seconds at REGULAR intervals (spread of
    the intervals <= LOOP_JITTER pairs) is a looping element (a blinking progress bar, a pulsing
    dot) and is ignored for the current pair until it has been quiet for loop_window. Counting starts, not changed pairs, keeps a long
    one-off change (a 0.8 s page dissolve) from reading as a loop; requiring regular intervals keeps
    content that changes on every narration line (irregular 1.5-4 s gaps) from reading as a loop.
    loop_window 0 disables it."""
    n_keep = max(int(keep.sum()), 1)
    need_quiet = max(int(round(quiet * fps)), 1)
    span = max(int(round(0.3 * fps)), 1)
    W = int(round(loop_window * fps))
    starts, looping, prev_tiles = None, None, None
    shares, onsets, quiet_run, open_on = [], [], need_quiet, None
    for k, cm in enumerate(changed_maps):
        cm = cm & keep
        if W > 0:
            h, w = cm.shape
            th, tw = h // TILE, w // TILE
            tiles = cm[: th * TILE, : tw * TILE].reshape(th, TILE, tw, TILE).any(axis=(1, 3))
            if starts is None:
                starts = {}
                looping = np.zeros_like(tiles)
                prev_tiles = np.zeros_like(tiles)
            for key in [key for key, v in starts.items() if v[-1] < k - W]:
                del starts[key]
                looping[key] = False
            if looping.any():
                full = np.zeros_like(cm)
                full[: th * TILE, : tw * TILE] = np.repeat(np.repeat(looping, TILE, 0), TILE, 1)
                cm = cm & ~full
            for key in map(tuple, np.argwhere(tiles & ~prev_tiles)):
                v = starts.setdefault(key, [])
                v.append(k)
                v[:] = [x for x in v if x >= k - W][-loop_bursts:]
                if len(v) >= loop_bursts:
                    gaps = np.diff(v)
                    looping[key] |= bool(gaps.max() - gaps.min() <= LOOP_JITTER)  # sticky until W s quiet
            prev_tiles = tiles
        s = cm.sum() / n_keep
        shares.append(float(s))
        active = s > move_min
        if open_on is not None:
            open_on["acc"] |= cm
            open_on["left"] -= 1
            if open_on["left"] <= 0:
                onsets.append(close_onset(open_on))
                open_on = None
        if active and quiet_run >= need_quiet:
            open_on = {"t": (k + 0.5) / fps, "acc": cm.copy(), "left": span - 1}
            if open_on["left"] <= 0:
                onsets.append(close_onset(open_on))
                open_on = None
        quiet_run = 0 if active else quiet_run + 1
    if open_on is not None:
        onsets.append(close_onset(open_on))
    return onsets, shares


def close_onset(o):
    acc = o["acc"]
    h, w = acc.shape
    ys, xs = np.where(acc)
    box = [round(xs.min() / w, 3), round(ys.min() / h, 3), round((xs.max() + 1) / w, 3),
           round((ys.max() + 1) / h, 3)] if len(xs) else None
    return {"t": round(o["t"] + 1e-9, 3), "box": box, "area": round(float(acc.mean()), 4)}


def diff_maps(frames, thr):
    prev = None
    for f in frames:
        f16 = f.astype(np.int16)
        if prev is not None:
            yield np.abs(f16 - prev) > thr
        prev = f16


def stream_gray(video, fps, width):
    info = probe(video)
    h = int(round(info["height"] * width / info["width"] / 2)) * 2
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-i", str(video), "-vf", f"fps={fps},scale={width}:{h},format=gray",
                          "-f", "rawvideo", "-"], stdout=subprocess.PIPE)
    size = width * h
    try:
        while True:
            buf = p.stdout.read(size)
            if len(buf) < size:
                break
            yield np.frombuffer(buf, np.uint8).reshape(h, width)
    finally:
        p.stdout.close()
        p.wait()


def cover_stats(onsets, starts, shift=3.0, reps=2000, seed=0, pre=0.3, post=1.0):
    on = np.asarray(onsets, float)
    st = np.asarray(starts, float)

    def cover(o):
        if not o.size:
            return 0.0
        d = o[None, :] - st[:, None]
        return float(((d >= -pre) & (d <= post)).any(axis=1).mean())

    obs = cover(on)
    rng = np.random.default_rng(seed)
    null = np.array([cover(on + rng.uniform(-shift, shift, size=on.size)) for _ in range(reps)])
    return {"lines_with_onset": round(obs, 3), "cover_null_mean": round(float(null.mean()), 3),
            "cover_p": round(float((null >= obs).mean()), 4), "window_s": [-pre, post]}


def relate(lines, onsets, fps, pre, skip_before):
    ts = np.array([o["t"] for o in onsets]) if onsets else np.zeros(0)
    for ln in lines:
        inside = [o for o in onsets if ln["start"] - pre <= o["t"] < ln["end"]]
        ln["onsets"] = [o["t"] for o in inside]
        ln["lag_s"] = round(inside[0]["t"] - ln["start"], 3) if inside else None
    starts = [ln["start"] for ln in lines]
    ev = [t for t in ts.tolist() if t >= skip_before]
    res = {"n_lines": len(lines), "n_onsets": len(onsets), "n_onsets_used": len(ev)}
    if len(ev) >= 3 and len(starts) >= 3:
        lk = lock(ev, starts)
        s = np.asarray(starts)
        signed = [float(t - s[np.argmin(np.abs(s - t))]) for t in ev]
        lk["median_signed_dt_s"] = round(float(np.median(signed)), 3)
        res["lock"] = lk
        res["cover"] = cover_stats(ev, starts)
    else:
        res["lock"] = {"verdict": "undetermined: fewer than 3 onsets or lines"}
    lags = [ln["lag_s"] for ln in lines if ln["lag_s"] is not None]
    res["lag_s"] = {"n": len(lags), "median": round(float(np.median(lags)), 3) if lags else None,
                    "share_lines_without_onset": round(1 - len(lags) / max(len(lines), 1), 3)}
    return res


def analyse_frames(frames, fps, lines, excludes=(), thr=20, move_min=0.002, quiet=0.3, pre=0.3, skip_before=2.0,
                   loop_window=4.0, loop_bursts=4):
    frames = iter(frames)
    first = next(frames)
    keep = keep_mask(*first.shape, excludes)

    def chain():
        yield first
        yield from frames

    onsets, shares = onsets_from_changes(diff_maps(chain(), thr), fps, move_min, quiet, keep, loop_window, loop_bursts)
    res = relate(lines, onsets, fps, pre, skip_before)
    res["moving_share"] = round(float((np.asarray(shares) > move_min).mean()), 3) if shares else None
    return res, onsets


# ---------- line sheets ----------

def grab_colour(video, times, w=192, h=108):
    out = {}
    for t in times:
        r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{max(t, 0):.3f}", "-i", str(video), "-frames:v", "1",
                            "-vf", f"scale={w}:{h}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True)
        if len(r.stdout) >= w * h * 3:
            out[t] = np.frombuffer(r.stdout[: w * h * 3], np.uint8).reshape(h, w, 3)
    return out


def draw_sheets(video, lines, out_dir, window=None, per_page=10):
    from PIL import Image, ImageDraw, ImageFont
    font = ImageFont.truetype(FONT, 18)
    small = ImageFont.truetype(FONT, 14)
    sel = [ln for ln in lines if window is None or (window[0] <= ln["start"] < window[1])]
    tw, th, text_w, row_h = 256, 144, 460, 186
    width = 70 + text_w + 3 * (tw + 8) + 10
    paths = []
    for p0 in range(0, len(sel), per_page):
        page = sel[p0:p0 + per_page]
        times = []
        for ln in page:
            times += [ln["start"] - 0.2, ln["start"] + 0.6, max(ln["end"] - 0.1, ln["start"])]
        thumbs = grab_colour(video, times, tw, th)
        img = Image.new("RGB", (width, row_h * len(page) + 10), "white")
        d = ImageDraw.Draw(img)
        for i, ln in enumerate(page):
            y = 5 + i * row_h
            d.text((6, y + 4), f"{ln['start']:.1f}", fill=(40, 40, 40), font=small)
            d.text((6, y + 22), f"{ln['end']:.1f}", fill=(140, 140, 140), font=small)
            wrapped = textwrap.wrap(ln["text"], 22)[:4]
            for j, s in enumerate(wrapped):
                d.text((70, y + 4 + j * 24), s, fill=(20, 20, 20), font=font)
            lag = "no onset" if ln["lag_s"] is None else f"lag {ln['lag_s']:+.2f} s"
            d.text((70, y + th - 4), lag, fill=(180, 60, 40) if ln["lag_s"] is None else (30, 110, 60), font=small)
            x = 70 + text_w
            for k, t in enumerate([ln["start"] - 0.2, ln["start"] + 0.6, max(ln["end"] - 0.1, ln["start"])]):
                if t in thumbs:
                    img.paste(Image.fromarray(thumbs[t]), (x + k * (tw + 8), y))
                d.text((x + k * (tw + 8), y + th + 2), ["start-0.2", "start+0.6", "end-0.1"][k],
                       fill=(120, 120, 120), font=small)
            # onset strip across the three thumbnails: line window [start - 0.3, end]
            sx0, sx1, sy = x, x + 3 * (tw + 8) - 8, y + th + 30
            d.line([(sx0, sy), (sx1, sy)], fill=(200, 200, 200), width=2)
            span = max(ln["end"] - ln["start"] + 0.3, 0.1)
            for t in ln["onsets"]:
                px = sx0 + (t - (ln["start"] - 0.3)) / span * (sx1 - sx0)
                d.ellipse([px - 4, sy - 4, px + 4, sy + 4], fill=(30, 110, 200))
            sp = sx0 + 0.3 / span * (sx1 - sx0)
            d.line([(sp, sy - 7), (sp, sy + 7)], fill=(20, 20, 20), width=2)
            d.line([(0, y + row_h - 3), (width, y + row_h - 3)], fill=(225, 225, 225), width=1)
        p = Path(out_dir) / f"lines_{p0 // per_page:03d}.png"
        img.save(p)
        paths.append(str(p))
    return paths


def write_md(res, lines, path):
    L = ["# avsync: narration lines vs visual onsets", "",
         f"video: `{res['video']}`  srt: `{res['srt']}`  exclude: {res['exclude']}", ""]
    lk = res.get("lock", {})
    if "p" in lk:
        L += [f"- onsets used {lk['n_events']}, lines {lk['n_lines']}: median |dt| {lk['median_abs_dt_s']} s "
              f"(shifted null mean {lk['null_mean_s']} s), p {lk['p']}; median signed dt {lk['median_signed_dt_s']} s",
              f"- lines with an onset in [-0.3, +1.0] s of their start: {res['cover']['lines_with_onset']} "
              f"(shifted null {res['cover']['cover_null_mean']}, p {res['cover']['cover_p']})"]
    else:
        L.append(f"- lock: {lk.get('verdict')}")
    L += [f"- lines without any onset: {res['lag_s']['share_lines_without_onset']}; median first-onset lag "
          f"{res['lag_s']['median']} s", "", "| # | start | end | lag s | onsets | text |", "|---|---|---|---|---|---|"]
    for i, ln in enumerate(lines):
        L.append(f"| {i} | {ln['start']:.2f} | {ln['end']:.2f} | {'' if ln['lag_s'] is None else ln['lag_s']} | "
                 f"{', '.join(f'{t:.2f}' for t in ln['onsets'])} | {ln['text'].replace('|', '/')} |")
    Path(path).write_text("\n".join(L) + "\n", encoding="utf-8")


def parse_band(s):
    a, b = s.split(":")
    return float(a), float(b)


def analyse(video, srt, out, excludes=(), fps=10.0, width=320, thr=20, move_min=0.002, quiet=0.3,
            sheets=False, window=None, loop_window=4.0, loop_bursts=4):
    lines = parse_srt(Path(srt).read_text(encoding="utf-8"))
    res, onsets = analyse_frames(stream_gray(video, fps, width), fps, lines, excludes, thr, move_min, quiet,
                                 loop_window=loop_window, loop_bursts=loop_bursts)
    res.update({"video": str(video), "srt": str(srt), "exclude": [list(b) for b in excludes], "fps_sampled": fps,
                "width": width, "thr": thr, "move_min": move_min, "quiet_s": quiet,
                "loop_window_s": loop_window, "loop_bursts": loop_bursts})
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    if sheets:
        res["sheets"] = draw_sheets(video, lines, out, window)
    (out / "avsync.json").write_text(json.dumps({"summary": res, "lines": lines, "onsets": onsets},
                                                ensure_ascii=False, indent=1), encoding="utf-8")
    write_md(res, lines, out / "avsync.md")
    return res


# ---------- selftest ----------

def synth(seed, true_lock, dur=150.0, fps=10, w=320, h=180, blinker=False):
    rng = np.random.default_rng(seed)
    starts = np.cumsum(rng.uniform(2.0, 4.0, size=80))
    starts = starts[starts < dur - 3]
    lines = [{"start": float(s), "end": float(min(s + rng.uniform(1.5, 2.2), dur)), "text": f"line {i}"}
             for i, s in enumerate(starts)]
    n = int(dur * fps)
    if true_lock:
        entries = [s + rng.normal(0.1, 0.15) for s in starts if rng.random() < 0.8]
    else:
        entries = sorted(rng.uniform(3, dur - 2, size=int(0.8 * len(starts))).tolist())
    clears = [starts[i] for i in range(5, len(starts), 5)] if true_lock else \
        sorted(rng.uniform(3, dur - 2, size=len(starts) // 5).tolist())
    cards = []
    for t in entries:
        cw, ch = rng.integers(30, 70), rng.integers(18, 34)
        x, y = rng.integers(5, w - cw - 5), rng.integers(5, int(0.78 * h) - ch)
        cards.append((t, x, y, cw, ch))
    bg = 200
    sub_y0 = int(0.82 * h)
    frames = []
    for k in range(n):
        t = k / fps
        f = np.full((h, w), bg, np.uint8)
        last_clear = max([c for c in clears if c <= t], default=-1e9)
        for (t0, x, y, cw, ch) in cards:
            if t0 <= last_clear and t >= last_clear + CLEAR_S:
                continue
            a = np.clip((t - t0) / 0.3, 0, 1)
            if t0 <= last_clear:
                a *= np.clip(1 - (t - last_clear) / CLEAR_S, 0, 1)
            if a > 0:
                blk = f[y:y + ch, x:x + cw].astype(np.float32)
                blk[::3, :] = blk[::3, :] * (1 - a) + 40 * a
                blk[1::3, :] = blk[1::3, :] * (1 - a) + 255 * a
                f[y:y + ch, x:x + cw] = blk.astype(np.uint8)
        for i, ln in enumerate(lines):
            if ln["start"] <= t < ln["end"]:
                r = np.random.default_rng(1000 + i)
                f[sub_y0 + 6:sub_y0 + 22, 40:280] = np.where(r.random((16, 240)) < 0.5, 30, 230)
                break
        # a bar lit 0.1 s of every 0.5 s: >= 0.3 s quiet between flashes, so each flash is an onset, as measured
        # on C45's Claude Code panel (onsets every 0.50 s at 119.95-140.45 s)
        if blinker and k % 5 == 0:
            f[BLINK[1]:BLINK[3], BLINK[0]:BLINK[2]] = 60
        frames.append(f)
    return frames, lines, sorted(entries + list(clears))


CLEAR_S = 0.9  # page dissolve length; C45 station changes dissolve ~0.8 s
BLINK = (140, 100, 200, 104)  # x0, y0, x1, y1 at 320x180


def blink_share(onsets, w=320, h=180, after=6.0):
    """Share of onsets after `after` s whose box lies inside the blinker's row band."""
    late = [o for o in onsets if o["t"] > after and o["box"]]
    if not late:
        return 0.0
    y0, y1 = BLINK[1] / h, BLINK[3] / h
    inside = [o for o in late if o["box"][1] >= y0 - 0.02 and o["box"][3] <= y1 + 0.02]
    return len(inside) / len(late)


def selftest():
    ok = True
    ex = [(0.8, 1.0)]
    frames, lines, truth = synth(1, True)
    r, onsets = analyse_frames(frames, 10, [dict(x) for x in lines], ex)
    ts = np.array([o["t"] for o in onsets])
    found = np.mean([np.abs(ts - t).min() <= 0.2 for t in truth if t > 2]) if len(ts) else 0
    lk = r["lock"]
    good = lk.get("p", 1) < 0.05 and lk.get("median_abs_dt_s", 9) < 0.35 and found >= 0.9
    print(f"known-true (masked): p {lk.get('p')}, median |dt| {lk.get('median_abs_dt_s')} s, "
          f"true entries found {found:.2f} -> {'ok' if good else 'FAIL'}")
    ok &= good
    neg, conf = 0, 0
    for s in range(5):
        fr, ln, _ = synth(20 + s, False)
        r1, _ = analyse_frames(fr, 10, [dict(x) for x in ln], ex)
        r2, _ = analyse_frames(fr, 10, [dict(x) for x in ln], ())
        p1, p2 = r1["lock"].get("p", 0), r2["lock"].get("p", 1)
        neg += p1 > 0.1
        conf += p2 < 0.05
        print(f"  seed {s}: known-false masked p {p1}; same film unmasked p {p2}")
    good = neg >= 4
    print(f"known-false (masked): p > 0.1 in {neg}/5 (want >= 4) -> {'ok' if good else 'FAIL'}")
    ok &= good
    good = conf >= 4
    print(f"confound control (unmasked subtitle): p < 0.05 in {conf}/5 (want >= 4) -> {'ok' if good else 'FAIL'}")
    ok &= good
    with tempfile.TemporaryDirectory() as td:
        vid = Path(td) / "kt.mp4"
        h, w = frames[0].shape
        p = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "gray", "-s", f"{w}x{h}",
                              "-r", "10", "-i", "-", "-pix_fmt", "yuv420p", "-c:v", "libx264", "-crf", "20", str(vid)],
                             stdin=subprocess.PIPE)
        for f in frames:
            p.stdin.write(f.tobytes())
        p.stdin.close()
        p.wait()
        r3, _ = analyse_frames(stream_gray(vid, 10, 320), 10, [dict(x) for x in lines], ex)
        good = r3["lock"].get("p", 1) < 0.05
        print(f"round trip (H.264 + ffmpeg decode): p {r3['lock'].get('p')} -> {'ok' if good else 'FAIL'}")
        ok &= good
    # looping element: a bar blinking every 0.5 s on top of the known-true film
    fb, lb, tb = synth(1, True, blinker=True)
    r4, o4 = analyse_frames(fb, 10, [dict(x) for x in lb], ex)
    r5, o5 = analyse_frames(fb, 10, [dict(x) for x in lb], ex, loop_window=0)
    ts4 = np.array([o["t"] for o in o4])
    found4 = np.mean([np.abs(ts4 - t).min() <= 0.2 for t in tb if t > 6]) if len(ts4) else 0
    b4, b5 = blink_share(o4), blink_share(o5)
    good = b4 < 0.1 and found4 >= 0.9 and r4["lock"].get("p", 1) < 0.05
    print(f"loop suppression on: blinker onsets {b4:.2f} of late onsets (want < 0.1), true entries found "
          f"{found4:.2f}, p {r4['lock'].get('p')} -> {'ok' if good else 'FAIL'}")
    ok &= good
    good = b5 > 0.5
    print(f"loop control (suppression off): blinker onsets {b5:.2f} (want > 0.5, the blinker must fire) -> "
          f"{'ok' if good else 'FAIL'}")
    ok &= good
    print("SELFTEST", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("video", nargs="?")
    ap.add_argument("--srt")
    ap.add_argument("--out")
    ap.add_argument("--exclude", action="append", default=[], type=parse_band,
                    help="height-fraction band to ignore, e.g. 0.8:1.0 (repeatable)")
    ap.add_argument("--fps", type=float, default=10.0)
    ap.add_argument("--width", type=int, default=320)
    ap.add_argument("--thr", type=int, default=20)
    ap.add_argument("--move-min", type=float, default=0.002)
    ap.add_argument("--quiet", type=float, default=0.3)
    ap.add_argument("--loop-window", type=float, default=4.0, help="seconds of history for loop suppression; 0 = off")
    ap.add_argument("--loop-bursts", type=int, default=4, help="regular starts within --loop-window that mark a tile as looping")
    ap.add_argument("--sheets", action="store_true", help="write line sheets (lines_NNN.png)")
    ap.add_argument("--sheet-window", type=parse_band, help="only lines starting in T0:T1 seconds")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        sys.exit(selftest())
    if not (a.video and a.srt and a.out):
        ap.error("video, --srt and --out are required")
    res = analyse(a.video, a.srt, a.out, a.exclude, a.fps, a.width, a.thr, a.move_min, a.quiet,
                  a.sheets, a.sheet_window, a.loop_window, a.loop_bursts)
    print(json.dumps({k: v for k, v in res.items() if k != "sheets"}, ensure_ascii=False))


if __name__ == "__main__":
    main()

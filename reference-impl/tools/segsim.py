"""Section reuse: does a film contain a given source section, and how strongly compared with chance?

Question it serves (r13, user 2026-09-29): the user picked the best version of each section across several arms; a
model is asked to assemble them into one film. For each picked section (a clip [a, b] of a source video) this tool
finds the best-matching window in the assembled film and compares that score with the same search run on films that
were NOT built from the clip (other arms on the same site): the chance baseline.

Visual score: frames at --fps (default 4), shrunk to 32 px on the long side (colour), mean-centred; the score of a
window is the mean Pearson correlation of aligned frames; the film is searched at every offset (step 1/fps) and the
best window is kept (`best`, `at_s`). A section that was re-timed (stretched or cut) scores lower than one copied.
Text score (optional, needs fidelity.json with sample_text for both): Jaccard of the on-screen strings (NFKC, no
whitespace, >= 2 chars) inside the clip vs inside the best visual window.
Verdict per section, only against the baseline it was given: `reused` if the assembled score is above the highest
baseline score by at least --margin (0.1), `not separated` otherwise. With no baseline there is no verdict.

Calibration (--selftest, synthetic): a clip copied into a longer film at 7 s -> best ~1.0 at 7 s; the same clip
re-encoded through ffmpeg -> >= 0.9; a film of other content with a same-colour moving block -> < 0.5 (reads ~0.4:
shared shapes and colours lift the score, which is why the verdict needs a baseline) and `not separated`; a clip
slowed to 1.25x -> still found (>= 0.6) with its window starting inside the 5 s stretch. Real control (before trusting r13 numbers): every
picked clip against its OWN source video must score >= 0.95 at its own start.

What it cannot determine: whether the reuse looks good (INV-6); a section rebuilt in a new palette scores low even if
its structure is kept, so a low visual score with a high text score means "same content, new look".

Usage:
    python -X utf8 tools/segsim.py --clip SRC.mp4:A:B --film ASSEMBLED.mp4 [--baseline F1.mp4 F2.mp4 ...]
        [--clip-fid SRC_fidelity.json --film-fid FILM_fidelity.json] [--out f.json]
    python -X utf8 tools/segsim.py --selftest
"""
import argparse
import json
import re
import subprocess
import sys
import tempfile
import unicodedata
from pathlib import Path

import numpy as np

FPS = 4


def decode(video, fps=FPS, long_side=32, start=None, dur=None):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                          "-of", "csv=p=0", str(video)], capture_output=True, text=True, check=True).stdout
    w, h = (int(x) for x in out.strip().split(",")[:2])
    if w >= h:
        sw, sh = long_side, max(2, int(round(long_side * h / w)))
    else:
        sw, sh = max(2, int(round(long_side * w / h))), long_side
    cmd = ["ffmpeg", "-v", "error"]
    if start is not None:
        cmd += ["-ss", str(start)]
    cmd += ["-i", str(video)]
    if dur is not None:
        cmd += ["-t", str(dur)]
    cmd += ["-vf", f"fps={fps},scale={sw}:{sh}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(-1, sh, sw, 3).astype(np.float32)


def normalise(frames):
    f = frames.reshape(len(frames), -1)
    f = f - f.mean(axis=1, keepdims=True)
    n = np.linalg.norm(f, axis=1, keepdims=True)
    flat = n[:, 0] < 1e-6
    return f / np.where(n < 1e-6, 1, n), flat, frames.reshape(len(frames), -1).mean(axis=1)


def best_window(clip, film):
    """clip, film: frame arrays at the same size. Returns (best score, offset index)."""
    if len(film) < len(clip) or len(clip) == 0:
        return 0.0, None
    c, cflat, cmean = normalise(clip)
    f, fflat, fmean = normalise(film)
    sims = f @ c.T  # (film frames, clip frames)
    both_flat = fflat[:, None] & cflat[None, :]
    same_col = np.abs(fmean[:, None] - cmean[None, :]) < 8
    sims = np.where(both_flat, np.where(same_col, 1.0, 0.0), sims)
    n = len(clip)
    scores = [float(np.mean(sims[o + np.arange(n), np.arange(n)])) for o in range(len(film) - n + 1)]
    o = int(np.argmax(scores))
    return scores[o], o


def strings_in(fid_path, a, b):
    if not fid_path:
        return None
    d = json.loads(Path(fid_path).read_text(encoding="utf-8"))
    out = set()
    for t, s in d.get("sample_text", []):
        if a <= t <= b:
            for part in re.split(r"\s+", unicodedata.normalize("NFKC", s)):
                if len(part) >= 2:
                    out.add(part)
    return out


def jaccard(x, y):
    if x is None or y is None or not (x | y):
        return None
    return round(len(x & y) / len(x | y), 3)


def section(src, a, b, film, baseline=(), clip_fid=None, film_fid=None, margin=0.1, fps=FPS):
    clip = decode(src, fps, start=a, dur=b - a)
    fr = decode(film, fps)
    if fr.shape[1:] != clip.shape[1:]:
        fr = decode(film, fps, long_side=max(clip.shape[1:3]))
    score, off = best_window(clip, fr)
    res = {"clip": f"{src}:{a}:{b}", "film": str(film), "best": round(score, 3),
           "at_s": None if off is None else round(off / fps, 2)}
    if clip_fid and film_fid and off is not None:
        res["text_jaccard"] = jaccard(strings_in(clip_fid, a, b), strings_in(film_fid, off / fps, off / fps + (b - a)))
    base = []
    for bf in baseline:
        bfr = decode(bf, fps)
        base.append({"film": str(bf), "best": round(best_window(clip, bfr)[0], 3)})
    res["baseline"] = base
    if base:
        top = max(x["best"] for x in base)
        res["baseline_max"] = top
        res["verdict"] = "reused" if score >= top + margin else "not separated"
    return res


# ---------- selftest ----------
def _write(frames, path, fps=FPS):
    data = np.stack([np.repeat(np.repeat(f, 8, 0), 8, 1) for f in frames]).clip(0, 255).astype(np.uint8)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s",
                    f"{data.shape[2]}x{data.shape[1]}", "-r", str(fps), "-i", "-", "-pix_fmt", "yuv420p", str(path)],
                   input=data.tobytes(), check=True)


def _scene(n, seed, h=18, w=32):
    rng = np.random.default_rng(seed)
    base = rng.uniform(0, 255, (h, w, 3))
    frames = []
    for k in range(n):  # a block moving over a textured ground
        f = base.copy()
        x = (k * 2 + seed) % (w - 8)
        f[5:13, x:x + 8] = (255 * (seed % 2), 128, 255 * ((seed + 1) % 2))
        frames.append(f.astype(np.float32))
    return frames


def selftest():
    ok = True
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        clip_frames = _scene(16, 1)                                   # 4 s
        film = _scene(28, 5) + clip_frames + _scene(20, 7)             # clip at 7 s
        other = _scene(64, 9)
        slow = _scene(28, 5) + [clip_frames[int(i / 1.25)] for i in range(20)] + _scene(16, 7)
        _write(clip_frames, td / "src.mp4"); _write(film, td / "film.mp4")
        _write(other, td / "other.mp4"); _write(slow, td / "slow.mp4")
        r = section(td / "src.mp4", 0, 4, td / "film.mp4", [td / "other.mp4"])
        good = r["best"] >= 0.95 and r["at_s"] == 7.0 and r["verdict"] == "reused"
        ok &= good; print(f"  {'ok  ' if good else 'FAIL'} copy at 7 s: best {r['best']} at {r['at_s']} s, baseline {r['baseline_max']}, {r['verdict']}")
        r2 = section(td / "src.mp4", 0, 4, td / "other.mp4", [td / "film.mp4"])
        good = r2["best"] < 0.5 and r2["verdict"] == "not separated"  # same-colour moving block, other ground: ~0.4
        ok &= good; print(f"  {'ok  ' if good else 'FAIL'} unrelated film: best {r2['best']}, {r2['verdict']}")
        r3 = section(td / "src.mp4", 0, 4, td / "slow.mp4", [td / "other.mp4"])
        good = r3["best"] >= 0.6 and 6.75 <= (r3["at_s"] or 0) <= 8.0  # the 5 s stretch holds a 4 s window starting 7-8 s
        ok &= good; print(f"  {'ok  ' if good else 'FAIL'} clip slowed 1.25x: best {r3['best']} at {r3['at_s']} s")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(td / "film.mp4"), "-crf", "35", str(td / "film_re.mp4")], check=True)
        r4 = section(td / "src.mp4", 0, 4, td / "film_re.mp4")
        good = r4["best"] >= 0.9
        ok &= good; print(f"  {'ok  ' if good else 'FAIL'} re-encoded copy: best {r4['best']}")
    print("SELFTEST " + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--clip", help="SRC.mp4:A:B")
    ap.add_argument("--film")
    ap.add_argument("--baseline", nargs="*", default=[])
    ap.add_argument("--clip-fid")
    ap.add_argument("--film-fid")
    ap.add_argument("--margin", type=float, default=0.1)
    ap.add_argument("--out")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        sys.exit(selftest())
    src, s, e = a.clip.rsplit(":", 2)
    r = section(src, float(s), float(e), a.film, a.baseline, a.clip_fid, a.film_fid, a.margin)
    print(json.dumps(r, ensure_ascii=False))
    if a.out:
        Path(a.out).write_text(json.dumps(r, indent=1, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()

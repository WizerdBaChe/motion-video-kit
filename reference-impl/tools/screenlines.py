"""On-screen lyric (or subtitle) line starts: when does a NEW line of large text appear?

STATUS: PARTIAL (2026-10-04). Selftest PASS. Real positive control C31 (46 lyric line starts from its
source code; kinetic type that flies in word by word, often two lines stacked): recall 0.54 /
precision 0.41 within 0.5 s, 0.80 / 0.79 within 1.5 s, median onset 0.26 s LATE (73 % late) - the OCR
reads a word only once it has settled. It also cannot tell a lyric from manga balloons, titles or
interface text (C32-C36). Its starts are candidates for case notes, never a technique card; the
control for those films is a model frame read (measurements/C3x/text_events_modelread.json).
The first C31 run (whole frame as one string) missed every line that appears under a line still on
screen; that was reproduced as a synthetic case first, then fixed by tracking rows. Not tuned on
C31 after that.

Frames are sampled at --fps (default 5) at the video's own size and read by Windows.Media.Ocr
(tools/winocr.ps1, --lang en-US | ja | zh-Hans-CN | zh-Hant-TW). Per frame, only LARGE text counts:
OCR lines whose median word height is >= --min-h of the frame height (default 0.045; HUD and caption
decorations are smaller - C31: 8-20 px vs lyric words 46-97 px at 720 p). Text is lower-cased with
punctuation and spaces removed.

Rows: large boxes whose centres lie within half a word height form one row (the OCR splits a
visual row into several boxes), read left to right. Each row is matched to the lines already on
screen (tracks); a row matching none is a candidate new line. Per row R against a track L:

    same line   R shares >= 50 % of its character bigrams (of the shorter string) with L - a line that
                grows word by word or glyph by glyph, shrinks while fading, or is misread a little
    new line    R has >= 3 characters, is not the same line, and the next frame agrees (persists 2
                samples); also any text after >= 1.0 s without large text (a repeated line counts again;
                OCR dropouts run up to 0.4 s, so a held title must not restart on them)
    onset       back-dated through earlier samples that show a PART of R (skipping single empty samples),
                so a line revealed glyph by glyph starts at its first glyph, not when it is complete

Recognised text stays in memory: the output holds times, character counts and an 8-hex hash per line,
NEVER the text (lyrics are copyrighted).

Calibration (selftest, synthetic 1280x720 frames, en-US): a moving textured ground with small HUD text
that changes every frame (must be ignored) and five large lines - a pop-in, a word-by-word reveal
(0.3 s per word), a 0.4 s fade-in, the same line again after a 1.5 s gap, and a line replaced with no
gap, and a line that appears word by word under a line still on screen. Every true start must be found within 0.4 s and at most one extra start may appear; texture + HUD
alone must give 0 lines and one title held for 8 s exactly 1. (First run failed the word reveal, found
0.6 s late: the OCR drops whole frames now and then and garbles the HUD into tall boxes, so back-dating
through "any frame with text" stopped at a dropout or ran onto garbage. Back-dating now follows only
frames whose text is CONTAINED in the new line, skipping single empty frames.) A fade-in is read when
the text becomes legible, about 0.3 s into a 0.4 s fade - the onset is late by that much. Real positive
control: C31, whose lyric line starts are known from its source code (measurements/C31/code_boundaries.json).

What it cannot determine: text the OCR cannot read (heavy stylisation, vertical writing, strong
motion blur, text smaller than --min-h); a wrapped line whose second row is revealed later counts
twice; a very short new row (one or two words) can be absorbed by a long line still on screen; a big title or a sign in the picture counts as a line; where the singing starts (text may lead or lag
the voice). Windows only (WinRT OCR).

Usage:
    python -X utf8 tools/screenlines.py <video> --out <file.json> [--lang ja] [--fps 5] [--min-h 0.045]
        [--t0 S --t1 S]
    python -X utf8 tools/screenlines.py --selftest
"""
import argparse
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from avio import probe  # noqa: E402

PS = Path(__file__).resolve().parent / "winocr.ps1"
SAME = 0.5
MIN_CHARS = 3
GAP_S = 1.0   # OCR dropout runs reach 2 samples (0.4 s) on clean synthetic text


def ocr_frames(video, fps, t0=None, t1=None, lang="en-US"):
    info = probe(video)
    with tempfile.TemporaryDirectory() as td:
        cmd = ["ffmpeg", "-v", "error"]
        if t0 is not None:
            cmd += ["-ss", str(t0)]
        cmd += ["-i", str(video)]
        if t1 is not None:
            cmd += ["-t", str(t1 - (t0 or 0))]
        subprocess.run(cmd + ["-vf", f"fps={fps}", str(Path(td) / "f_%06d.png")], check=True)
        r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(PS),
                            "-Dir", td, "-Lang", lang], capture_output=True, check=True)
    out = []
    for line in r.stdout.decode("utf-8", errors="replace").splitlines():
        line = line.strip()
        if line.startswith("{"):
            d = json.loads(line)
            k = int(re.search(r"(\d+)", d["file"]).group(1)) - 1
            lines = d["lines"] if isinstance(d["lines"], list) else [d["lines"]]
            out.append(((t0 or 0) + k / fps, lines))
    out.sort(key=lambda x: x[0])
    return out, info["height"]


def norm(s):
    return re.sub(r"[\W_]+", "", s.lower())


def bigrams(s):
    return {s[i:i + 2] for i in range(len(s) - 1)} if len(s) > 1 else ({s} if s else set())


def same_line(a, b):
    A, B = bigrams(a), bigrams(b)
    if not A or not B:
        return False
    return len(A & B) / min(len(A), len(B)) >= SAME


def frame_rows(lines, height, min_h):
    """Large OCR lines grouped into rows (boxes whose centres lie within half a word height), each
    row read left to right and normalised. The OCR splits one visual row into several boxes."""
    big = sorted((l for l in lines if l.get("h", 0) >= min_h * height), key=lambda l: l["y"] + l["h"] / 2)
    rows = []
    for l in big:
        yc = l["y"] + l["h"] / 2
        if rows and abs(yc - rows[-1][0]) < 0.5 * max(l["h"], rows[-1][1]):
            rows[-1][2].append(l)
        else:
            rows.append([yc, l["h"], [l]])
    out = [norm("".join(x["text"] for x in sorted(r[2], key=lambda x: x["x"]))) for r in rows]
    return [r for r in out if r]


def contained(part, whole):
    """True when part reads as a piece of whole (a line caught mid-reveal or mid-fade)."""
    A, B = bigrams(part), bigrams(whole)
    return bool(A) and len(A & B) / len(A) >= SAME


def detect(series, fps):
    """series: [(t, [row strings])]. Returns line starts (t, n_chars, hash), one per sample time."""
    starts, tracks = [], []          # track: [text, last time seen]
    for k, (t, rows) in enumerate(series):
        tracks = [tr for tr in tracks if t - tr[1] < GAP_S]
        old = [tr[0] for tr in tracks]
        for r in rows:
            tr = next((tr for tr in tracks if same_line(r, tr[0])), None)
            if tr:
                tr[0] = r if len(r) >= len(tr[0]) else tr[0]
                tr[1] = t
                continue
            if len(r) < MIN_CHARS:
                continue
            nxt = []
            for kk in range(k + 1, min(k + 3, len(series))):   # the OCR drops a whole frame now and then
                if series[kk][1]:
                    nxt = series[kk][1]
                    break
            if not any(same_line(x, r) for x in nxt):
                continue
            # back-date through earlier frames that show a PART of this row (glyph / word reveal,
            # fade-in), skipping single empty frames; a frame with other text but no part stops it
            j, i = k, k - 1
            while i >= 0 and k - i <= 2 * fps:
                prev = series[i][1]
                if any(contained(x, r) and not any(same_line(x, o) for o in old) for x in prev):
                    j = i
                elif prev or (i - 1 >= 0 and not series[i - 1][1]):
                    break
                i -= 1
            tracks.append([r, t])
            if not starts or abs(starts[-1][0] - series[j][0]) > 1e-6:
                starts.append((series[j][0], len(r), hashlib.sha1(r.encode("utf-8")).hexdigest()[:8]))
    starts.sort()
    return starts


def analyse(video, lang="en-US", fps=5.0, min_h=0.045, t0=None, t1=None):
    frames, height = ocr_frames(video, fps, t0, t1, lang)
    series = [(t, frame_rows(lines, height, min_h)) for t, lines in frames]
    starts = detect(series, fps)
    return {"video": str(video), "lang": lang, "fps": fps, "min_h": min_h, "frames": len(series),
            "frames_with_text": sum(1 for _, s in series if s),
            "n_lines": len(starts), "line_starts_s": [round(t, 3) for t, _, _ in starts],
            "lines": [{"t": round(t, 3), "chars": n, "hash": h} for t, n, h in starts],
            "note": "times and hashes only; recognised text is never stored"}


# ---------------------------------------------------------------- selftest

LINES = [(1.0, 3.0, "LANTERN ROAD AT NIGHT", "pop"), (4.0, 6.5, "WE WALKED UNTIL MORNING", "words"),
         (7.5, 9.5, "NOBODY WAITS FOR TRAINS", "fade"), (11.0, 12.5, "NOBODY WAITS FOR TRAINS", "pop"),
         (12.5, 14.5, "HOLD THE EVENING RAIN", "pop"),
         (15.5, 18.5, "THE CITY SLEEPS BELOW", "pop", 300), (17.0, 19.5, "AND I KEEP WALKING HOME", "words", 460)]


def synth(path, lines=LINES, dur=20.0):
    import cv2
    W, H, FPS = 1280, 720, 30
    rng = np.random.default_rng(0)
    ground = cv2.GaussianBlur(rng.normal(0, 1, (H * 2, W * 2)).astype(np.float32), (0, 0), 3)
    ground = np.clip(60 + 25 * ground / ground.std(), 0, 255)
    n = int(dur * FPS)
    frames = []
    for i in range(n):
        t = i / FPS
        ox, oy = int(40 * np.sin(t)), int(30 * t) % H
        f = ground[oy:oy + H, W // 2 + ox:W // 2 + ox + W].copy()
        f = np.dstack([f, f * 0.9, f * 0.8]).astype(np.float32)
        hud = "".join(chr(65 + int(c)) for c in rng.integers(0, 26, 10))
        cv2.putText(f, f"{hud} {i:05d}", (30, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1, cv2.LINE_AA)
        for a, b, text, mode, *y in lines:
            if not (a <= t < b):
                continue
            show, alpha = text, 1.0
            if mode == "words":
                k = int((t - a) / 0.3) + 1
                show = " ".join(text.split()[:k])
            elif mode == "fade":
                alpha = min(1.0, (t - a) / 0.4)
            layer = f.copy()
            cv2.putText(layer, show, (120, y[0] if y else 400), cv2.FONT_HERSHEY_DUPLEX, 2.2, (255, 245, 230), 4, cv2.LINE_AA)
            f = (1 - alpha) * f + alpha * layer
        frames.append(np.clip(f, 0, 255).astype(np.uint8))
    with tempfile.TemporaryDirectory() as td:
        raw = Path(td) / "v.raw"
        raw.write_bytes(np.stack(frames).tobytes())
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}",
                        "-r", str(FPS), "-i", str(raw), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18",
                        str(path)], check=True)
    return [l[0] for l in lines]


def selftest():
    ok = True
    with tempfile.TemporaryDirectory() as td:
        v = Path(td) / "lyrics.mp4"
        truth = synth(v)
        res = analyse(v)
        got = res["line_starts_s"]
        hits = [min((abs(g - t) for g in got), default=9) for t in truth]
        recall = np.mean([h <= 0.4 for h in hits])
        extra = sum(1 for g in got if min(abs(g - t) for t in truth) > 0.4)
        good = recall == 1.0 and extra <= 1
        print(f"truth {truth}\nfound {got}\nerrors {[round(h, 2) for h in hits]} -> recall {recall:.2f} "
              f"(want 1.0 within 0.4 s), extra {extra} (want <= 1, HUD text changes every frame) "
              f"{'ok' if good else 'FAIL'}")
        ok &= bool(good)
        for name, lines, want in (("known-false texture + changing HUD only", [], 0),
                                  ("known-false one title held 8 s", [(0.5, 8.5, "LANTERN ROAD", "pop")], 1)):
            v = Path(td) / "neg.mp4"
            synth(v, lines, 9.0)
            n = analyse(v)["n_lines"]
            good = n == want
            print(f"{name}: {n} lines (want {want}) {'ok' if good else 'FAIL'}")
            ok &= good
    print("SELFTEST", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video", nargs="?")
    ap.add_argument("--out")
    ap.add_argument("--lang", default="en-US")
    ap.add_argument("--fps", type=float, default=5.0)
    ap.add_argument("--min-h", type=float, default=0.045)
    ap.add_argument("--t0", type=float)
    ap.add_argument("--t1", type=float)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        sys.exit(selftest())
    res = analyse(a.video, a.lang, a.fps, a.min_h, a.t0, a.t1)
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding="utf-8", newline="\n")
        Path(a.out).with_name(Path(a.out).stem + "_starts.json").write_text(
            json.dumps(res["line_starts_s"]), encoding="utf-8", newline="\n")
    print(f"{res['n_lines']} lines; {res['frames_with_text']}/{res['frames']} sampled frames had large text")


if __name__ == "__main__":
    main()

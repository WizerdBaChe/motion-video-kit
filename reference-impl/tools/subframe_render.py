"""Render a time-driven page (window.__setTime) with N sub-frames per frame averaged: motion blur (W09).

    python -X utf8 tools/subframe_render.py <index.html> -o <out.mp4> --duration S --size WxH [--fps 30]
        [--subframes 4] [--shutter 0.5] [--audio F] [--hide SELECTOR]
    python -X utf8 tools/subframe_render.py --selftest

Both arms of a W09 pair come from THIS tool (--subframes 1 is the control), so the only difference between the two
films is the sub-frame average; filmkit is not used for either side. Sub-frame k of frame i is sampled at
t = i/fps + ((k + 0.5)/N - 0.5) * shutter/fps, i.e. a shutter of `shutter` x frame interval centred on the frame time
(0.5 = the film-camera 180-degree shutter). N = 1 samples t = i/fps exactly. The average is taken in linear 8-bit
sRGB values (no gamma decode), which is what a plain frame accumulation does.
Writes <out.mp4> (H.264 yuv420p, AAC when --audio) and <out>.subframe.json (parameters, timings).
Limits: a page that is not a pure function of t (timers, random without seed) blurs its noise too; canvas/WebGL is
captured as rendered; text gets blurred like everything else that moves.
"""
import argparse
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np


def sample_times(i, fps, n, shutter):
    t0 = i / fps
    if n == 1:
        return [t0]
    return [max(0.0, t0 + ((k + 0.5) / n - 0.5) * shutter / fps) for k in range(n)]


def render(page, out, duration, size, fps=30, n=4, shutter=0.5, audio=None, quiet=False, hide=None):
    import cv2
    from playwright.sync_api import sync_playwright
    w, h = (int(v) for v in size.lower().split("x"))
    frames = int(round(duration * fps))
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{w}x{h}", "-r", str(fps),
           "-i", "-"]
    if audio:
        cmd += ["-i", str(audio), "-c:a", "aac", "-b:a", "192k", "-ac", "2", "-shortest"]
    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "16", "-preset", "medium", "-movflags", "+faststart",
            str(out)]
    t_start = time.time()
    enc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    with sync_playwright() as pw:
        br = pw.chromium.launch()
        pg = br.new_page(viewport={"width": w, "height": h})
        pg.goto(Path(page).resolve().as_uri())
        pg.wait_for_function("typeof window.__setTime === 'function'", timeout=30000)
        try:
            pg.wait_for_function("window.__ready === undefined || window.__ready === true", timeout=30000)
        except Exception:
            pass
        if hide:   # r31: hide elements (e.g. lyric text) for a pictures-only read; visibility keeps the layout
            pg.add_style_tag(content=f"{hide} {{ visibility: hidden !important; }}")
        for i in range(frames):
            acc = np.zeros((h, w, 3), np.float64)
            ts = sample_times(i, fps, n, shutter)
            for t in ts:
                pg.evaluate("t => { const r = window.__setTime(t); return r && r.then ? r.then(() => 1) : 1; }", t)
                png = pg.screenshot(type="png")
                acc += cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR)[:h, :w]
            enc.stdin.write(np.clip(np.rint(acc / len(ts)), 0, 255).astype(np.uint8).tobytes())
            if not quiet and i % (fps * 4) == 0:
                print(f"  frame {i}/{frames}", flush=True)
        br.close()
    enc.stdin.close()
    if enc.wait() != 0:
        raise SystemExit("ffmpeg failed")
    meta = {"page": str(page), "out": str(out), "duration_s": duration, "size": size, "fps": fps, "subframes": n,
            "shutter": shutter, "audio": str(audio) if audio else None, "frames": frames,
            "hide": hide, "wall_s": round(time.time() - t_start, 1), "tool": "tools/subframe_render.py"}
    Path(str(out) + ".subframe.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    return meta


PAGE = """<!doctype html><html><body style="margin:0;background:#fff">
<div id="b" style="position:absolute;top:40px;left:0;width:20px;height:40px;background:#000"></div>
<script>window.__setTime = t => { document.getElementById('b').style.left = (%s) + 'px'; };</script></body></html>"""


def _edge_width(frame_row):
    """Pixels on the row that are neither white nor black (the blurred edge zone)."""
    v = frame_row.mean(axis=1)
    return int(((v > 20) & (v < 235)).sum())


def selftest():
    import cv2
    ok = True
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        td = Path(td)
        for name, expr, want_blur in (("moving", "t * 600", True), ("static", "100", False)):
            p = td / f"{name}.html"
            p.write_text(PAGE % expr, encoding="utf-8")
            widths = {}
            for n in (1, 4):
                out = td / f"{name}_{n}.mp4"
                render(p, out, 0.5, "320x120", fps=30, n=n, quiet=True)
                cap = cv2.VideoCapture(str(out))
                cap.set(cv2.CAP_PROP_POS_FRAMES, 8)
                _, fr = cap.read()
                cap.release()
                widths[n] = _edge_width(fr[60])
            # 600 px/s at 30 fps, shutter 0.5 -> 10 px smear on each edge with N=4; N=1 has a sharp edge (codec ~2 px)
            blurred = widths[4] >= widths[1] + 6
            good = blurred if want_blur else (abs(widths[4] - widths[1]) <= 1)
            ok &= good
            kind = "pos" if want_blur else "neg"
            print(f"{kind} {name}: edge-zone px N=1 {widths[1]}, N=4 {widths[4]} -> {'ok' if good else 'FAIL'}")
        # --hide control: a black block marked data-role=lyric disappears (pos), an unmarked one stays (neg)
        p = td / "hide.html"
        p.write_text('<!doctype html><html><body style="margin:0;background:#fff">'
                     '<div data-role="lyric" style="position:absolute;left:20px;top:20px;width:60px;height:60px;background:#000"></div>'
                     '<div style="position:absolute;left:200px;top:20px;width:60px;height:60px;background:#000"></div>'
                     '<script>window.__setTime = t => {};</script></body></html>', encoding="utf-8")
        out = td / "hide.mp4"
        render(p, out, 0.2, "320x120", fps=30, n=1, quiet=True, hide="[data-role=lyric]")
        cap = cv2.VideoCapture(str(out))
        _, fr = cap.read()
        cap.release()
        hidden, kept = fr[50, 50].mean() > 200, fr[50, 230].mean() < 50
        ok &= hidden and kept
        print(f"pos hide: marked block hidden {hidden}; neg: unmarked block kept {kept} -> {'ok' if hidden and kept else 'FAIL'}")
    print("SELFTEST PASS" if ok else "SELFTEST FAIL")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("page", nargs="?")
    ap.add_argument("-o", dest="out")
    ap.add_argument("--duration", type=float)
    ap.add_argument("--size")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--subframes", type=int, default=4)
    ap.add_argument("--shutter", type=float, default=0.5)
    ap.add_argument("--audio")
    ap.add_argument("--hide", help="CSS selector hidden (visibility) before capture, e.g. '[data-role=lyric]'")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        sys.exit(selftest())
    if not (a.page and a.out and a.duration and a.size):
        ap.error("page, -o, --duration and --size are required")
    print(json.dumps(render(a.page, a.out, a.duration, a.size, a.fps, a.subframes, a.shutter, a.audio, hide=a.hide), indent=1))


if __name__ == "__main__":
    main()

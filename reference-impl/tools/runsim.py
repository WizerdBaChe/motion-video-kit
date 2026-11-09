"""Run-to-run similarity: how alike are the videos one condition produces when it is run several times?

Question it serves (r11, C21's author): "a detailed storyboard makes the result follow your intent; one line lets
the model decide". If that holds, repeated runs of the storyboard condition resemble EACH OTHER more than repeated
runs of the one-line condition. This tool measures that resemblance; it does not judge which is better.

Two measures per pair of videos:
  visual  : frames sampled at --fps, shrunk to 32 px on the long side (colour), Pearson correlation of the
            mean-centred pixels at the same time t, averaged over t. `visual_shift` allows a +-1 s timing slip
            (per t, the best match within the window). Flat frames: 1.0 if both flat with the same mean colour
            (within 8/255), else 0.
  text    : Jaccard overlap of the steady on-screen strings (fidelity.py's `strings`, NFKC, whitespace removed,
            >= 2 characters), when a fidelity.json is given for both.
Group summary: mean/min/max over all pairs inside a group; `--cross` also reports pairs across two groups.

Limits: the visual measure is layout-and-colour similarity at matching times; two videos with the same plan in
different palettes score low, the same palette with different content can score medium. Text overlap needs DOM text.

Usage:
    python -X utf8 tools/runsim.py --group S=dirA,dirB,dirC --group O=dirD,dirE,dirF --out sim.json [--cross S O]
        (each dir holds final.mp4 and optionally fidelity/fidelity.json)
    python -X utf8 tools/runsim.py --selftest
"""
import argparse
import itertools
import json
import statistics as st
import subprocess
import sys
import tempfile
import unicodedata
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from avio import probe  # noqa: E402


def frames(video, fps=2.0, long_side=32):
    info = probe(video)
    w, h = info["width"], info["height"]
    sw, sh = (long_side, max(2, round(long_side * h / w))) if w >= h else (max(2, round(long_side * w / h)), long_side)
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-vf", f"fps={fps},scale={sw}:{sh}:flags=area",
                        "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True, check=True)
    a = np.frombuffer(r.stdout, dtype=np.uint8).astype(np.float32)
    return a.reshape(-1, sh * sw * 3), (sw, sh)


def frame_sim(a, b):
    sa, sb = a.std(), b.std()
    if sa < 1e-3 or sb < 1e-3:
        return 1.0 if (sa < 1e-3 and sb < 1e-3 and abs(a.mean() - b.mean()) <= 8) else 0.0
    return float(np.corrcoef(a, b)[0, 1])


def visual(fa, fb, fps=2.0):
    n = min(len(fa), len(fb))
    if n == 0:
        return None, None
    aligned = [frame_sim(fa[i], fb[i]) for i in range(n)]
    k = int(round(fps))
    shifted = [max(frame_sim(fa[i], fb[j]) for j in range(max(0, i - k), min(n, i + k + 1))) for i in range(n)]
    return round(float(np.mean(aligned)), 3), round(float(np.mean(shifted)), 3)


def text_set(fid_path):
    if not fid_path or not Path(fid_path).exists():
        return None
    fid = json.loads(Path(fid_path).read_text(encoding="utf-8"))
    out = set()
    for s in fid.get("strings", []):
        t = "".join(unicodedata.normalize("NFKC", s["text"]).split())
        if len(t) >= 2:
            out.add(t)
    return out


def jaccard(a, b):
    if a is None or b is None or not (a | b):
        return None
    return round(len(a & b) / len(a | b), 3)


def pair(da, db, cache, fps):
    for d in (da, db):
        if d not in cache:
            cache[d] = (frames(Path(d) / "final.mp4", fps)[0], text_set(Path(d) / "fidelity" / "fidelity.json"))
    (fa, ta), (fb, tb) = cache[da], cache[db]
    v, vs = visual(fa, fb, fps)
    return {"a": da, "b": db, "visual": v, "visual_shift": vs, "text": jaccard(ta, tb)}


def summary(rows, key):
    vals = [r[key] for r in rows if r[key] is not None]
    return {"mean": round(st.mean(vals), 3), "min": min(vals), "max": max(vals), "n_pairs": len(vals)} if vals else None


def run(groups, cross, fps=2.0):
    cache, res = {}, {"fps": fps, "groups": {}, "cross": {}}
    for name, dirs in groups.items():
        rows = [pair(a, b, cache, fps) for a, b in itertools.combinations(dirs, 2)]
        res["groups"][name] = {"pairs": rows, **{k: summary(rows, k) for k in ("visual", "visual_shift", "text")}}
    if cross:
        g1, g2 = cross
        rows = [pair(a, b, cache, fps) for a in groups[g1] for b in groups[g2]]
        res["cross"][f"{g1}x{g2}"] = {"pairs": rows, **{k: summary(rows, k) for k in ("visual", "visual_shift", "text")}}
    return res


def write_video(path, frames_rgb, fps=10):
    h, w, _ = frames_rgb[0].shape
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}",
                          "-r", str(fps), "-i", "-", "-pix_fmt", "yuv420p", "-c:v", "libx264", "-crf", "18", str(path)],
                         stdin=subprocess.PIPE)
    for f in frames_rgb:
        p.stdin.write(f.astype(np.uint8).tobytes())
    p.stdin.close()
    p.wait()


def synth(kind, n=40, w=320, h=180, seed=0):
    rng = np.random.default_rng(seed)
    out = []
    for i in range(n):
        f = np.full((h, w, 3), 245, np.float32)
        if kind in ("A", "A_noise"):
            x = int(20 + i * 6)
            f[40:120, x:x + 60] = (200, 40, 40)
            f[130:160, 20:300] = (30, 30, 30) if i < 20 else (40, 90, 200)
        elif kind == "B":
            y = int(10 + i * 3)
            f[y:y + 50, 200:300] = (40, 160, 60)
            f[20:60, 20:120] = (240, 200, 30) if i % 10 < 5 else (20, 20, 20)
        if kind == "A_noise":
            f = np.clip(f + rng.normal(0, 12, f.shape), 0, 255)
        out.append(f)
    return out


def selftest():
    ok = True

    def check(name, cond):
        nonlocal ok
        ok &= bool(cond)
        print(("  ok  " if cond else "  FAIL") + " " + name)

    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        dirs = {}
        for k in ("A", "A_noise", "B"):
            d = td / k
            (d / "fidelity").mkdir(parents=True)
            write_video(d / "final.mp4", synth(k))
            dirs[k] = str(d)
        texts = {"A": ["找書店", "22 縣市", "讀書會"], "A_noise": ["找書店", "22 縣市", "每週選書"], "B": ["加 LINE", "0 元"]}
        for k, ts in texts.items():
            (Path(dirs[k]) / "fidelity" / "fidelity.json").write_text(
                json.dumps({"strings": [{"text": t} for t in ts]}, ensure_ascii=False), encoding="utf-8")
        cache = {}
        same = pair(dirs["A"], dirs["A"], cache, 2.0)
        near = pair(dirs["A"], dirs["A_noise"], cache, 2.0)
        far = pair(dirs["A"], dirs["B"], cache, 2.0)
        check(f"identical video: visual 1.0 ({same['visual']}), text 1.0 ({same['text']})",
              same["visual"] >= 0.999 and same["text"] == 1.0)
        check(f"same content + noise: visual > 0.9 ({near['visual']})", near["visual"] > 0.9)
        check(f"different content: visual < 0.5 ({far['visual']})", far["visual"] < 0.5)
        check(f"text overlap 2 of 4 = 0.5 ({near['text']}), disjoint = 0.0 ({far['text']})",
              near["text"] == 0.5 and far["text"] == 0.0)
        check("ordering: identical >= noisy copy > different (the 32-px area shrink averages pixel noise away)", same["visual"] >= near["visual"] > far["visual"])
        res = run({"G": [dirs["A"], dirs["A_noise"], dirs["B"]]}, None)
        g = res["groups"]["G"]["visual"]
        check(f"group summary over 3 pairs (n_pairs {g['n_pairs']}, min {g['min']} <= mean {g['mean']} <= max {g['max']})",
              g["n_pairs"] == 3 and g["min"] <= g["mean"] <= g["max"])
    flat = np.full(10, 100.0)
    check("flat frames: same colour 1.0, different colour 0.0",
          frame_sim(flat, flat + 3) == 1.0 and frame_sim(flat, flat + 50) == 0.0)
    print("SELFTEST " + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--group", action="append", default=[], help="NAME=dir,dir,...")
    ap.add_argument("--cross", nargs=2)
    ap.add_argument("--fps", type=float, default=2.0)
    ap.add_argument("--out")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        sys.exit(selftest())
    groups = {g.split("=", 1)[0]: g.split("=", 1)[1].split(",") for g in a.group}
    res = run(groups, a.cross, a.fps)
    Path(a.out).write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding="utf-8")
    brief = {n: {k: v[k] for k in ("visual", "visual_shift", "text")} for n, v in {**res["groups"], **res["cross"]}.items()}
    print(json.dumps(brief, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()

"""Regenerate the README showcase clips (docs/assets/showcase-*.gif) from the film MP4s.

Usage:
  python -X utf8 docs/assets/build_showcase.py --src <folder holding the showcase MP4s> [--out docs/assets]
  python -X utf8 docs/assets/build_showcase.py --render-explainer <folder>   # re-render the narrated-explainer
                                                                              # MP4 from the shipped example page

The five full films are release assets of the GitHub release (names in CLIPS below); the explainer is
ALSO re-renderable from the shipped example page with the shipped filmkit (--render-explainer), which is the
reproducible part. Each GIF is cut from a window of its film (seconds, from-to), scaled to the width given,
palette-optimised, and must stay under MAX_BYTES. ffmpeg is required (and Python 3.9+ for the render step).
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

MAX_BYTES = 5 * 1024 * 1024
HERE = Path(__file__).resolve().parent
KIT = HERE.parents[1] / "reference-impl"

# name, release asset, windows [(from, to)], width, fps, group (zh caption lives in README)
CLIPS = [
    ("hype-ad", "showcase-hype-ad.mp4", [(15.0, 29.0)], 560, 10),
    ("product-intro", "showcase-product-intro.mp4", [(5.0, 15.0)], 560, 10),
    ("narrated-explainer", "showcase-narrated-explainer.mp4", [(0.0, 4.4), (11.0, 16.0)], 400, 10),
    ("webgl-scene", "showcase-webgl-scene.mp4", [(0.0, 7.0)], 560, 10),
    ("text-motion", "showcase-text-motion.mp4", [(0.0, 9.0)], 560, 10),
]


def run(cmd: list[str]) -> None:
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if p.returncode != 0:
        sys.exit(f"STOP: {' '.join(cmd[:3])} failed: {p.stderr[-400:]}")


def make_gif(src: Path, dst: Path, windows: list[tuple[float, float]], width: int, fps: int) -> None:
    parts, labels = [], []
    for i, (a, b) in enumerate(windows):
        parts.append(f"[0:v]trim=start={a}:end={b},setpts=PTS-STARTPTS,fps={fps},scale={width}:-2:flags=lanczos[v{i}]")
        labels.append(f"[v{i}]")
    chain = ";".join(parts)
    chain += f";{''.join(labels)}concat=n={len(windows)}:v=1:a=0[c];[c]split[a][b];[a]palettegen=max_colors=96:stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=4"
    run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-filter_complex", chain, "-loop", "0", str(dst)])


def render_explainer(out_dir: Path) -> Path:
    """Render the shipped example page to an MP4 with the shipped filmkit (59.5 s, 1080x1350, 30 fps)."""
    import shutil
    page = KIT / "films" / "fanout-pool-explainer" / "page"
    work = out_dir / "_render_page"
    if work.exists():
        shutil.rmtree(work)
    shutil.copytree(page, work)  # filmkit writes next to the page: render a copy, never the shipped folder
    mp4 = work / "fanout-pool-explainer.mp4"
    run([sys.executable, "-X", "utf8", str(KIT / "tools" / "filmkit" / "render.py"), str(work / "index.html"),
         "-o", str(mp4), "--duration", "59.5", "--size", "1080x1350", "--fps", "30", "--profile", "lab-round"])
    final = out_dir / "showcase-narrated-explainer.mp4"
    shutil.copy2(mp4, final)
    return final


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", type=Path)
    ap.add_argument("--out", type=Path, default=HERE)
    ap.add_argument("--render-explainer", type=Path, metavar="FOLDER")
    a = ap.parse_args()
    if a.render_explainer:
        a.render_explainer.mkdir(parents=True, exist_ok=True)
        print("rendered", render_explainer(a.render_explainer))
        return 0
    if not a.src or not a.src.is_dir():
        ap.error("--src <folder with the showcase MP4s> is required")
    bad = 0
    for name, asset, windows, width, fps in CLIPS:
        src = a.src / asset
        if not src.is_file():
            print(f"MISSING {asset}")
            bad += 1
            continue
        dst = a.out / f"showcase-{name}.gif"
        make_gif(src, dst, windows, width, fps)
        size = dst.stat().st_size
        print(f"{dst.name}: {size / 1e6:.2f} MB, windows {windows}")
        if size > MAX_BYTES:
            print(f"  TOO BIG (> {MAX_BYTES / 1e6:.0f} MB): shorten the window or lower width/fps")
            bad += 1
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

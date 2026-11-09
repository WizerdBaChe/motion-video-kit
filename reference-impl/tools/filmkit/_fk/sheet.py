"""Contact sheet: one thumbnail per second, evenly sampled beyond max_frames (PSM 6.6, P-25b)."""
from __future__ import annotations

import math
import subprocess
import time
from pathlib import Path

from .common import one_line, write_bytes_atomic
from .types import SheetResult


def make_sheet(file: Path, out_png: Path, profile: dict, deadline: float, duration_s: float | None = None,
               retry: dict | None = None) -> SheetResult:
    cfg = profile.get("sheet", {})
    cols, tw, maxf = int(cfg.get("columns", 10)), int(cfg.get("thumb_width", 192)), int(cfg.get("max_frames", 300))
    if not duration_s or duration_s <= 0:
        return SheetResult(False, None, "film duration unknown")
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        return SheetResult(False, None, "check timed out")
    n = max(1, math.ceil(duration_s))
    rate, note = "1", None
    if n > maxf:
        rate = f"{maxf}/{duration_s:.6f}"
        n = maxf
        note = f"{maxf} thumbnails sampled evenly, one every {duration_s / maxf:.2f} s"
    rows = math.ceil(n / cols)
    vf = f"fps={rate},scale={tw}:-2,tile={cols}x{rows}"
    argv = ["ffmpeg", "-hide_banner", "-nostats", "-loglevel", "error", "-i", str(file), "-vf", vf, "-frames:v", "1",
            "-f", "image2pipe", "-c:v", "png", "-"]
    try:
        r = subprocess.run(argv, capture_output=True, timeout=remaining)
    except FileNotFoundError:
        return SheetResult(False, None, "ffmpeg not found on PATH")
    except subprocess.TimeoutExpired:
        return SheetResult(False, None, "check timed out")
    if r.returncode != 0 or not r.stdout:
        lines = r.stderr.decode("utf-8", "replace").strip().splitlines()
        return SheetResult(False, None, one_line(lines[-1] if lines else "ffmpeg produced no image", 200))
    try:
        write_bytes_atomic(Path(out_png), r.stdout, retry, make_fk_dir=False)
    except Exception as e:
        return SheetResult(False, None, one_line(e, 200))
    return SheetResult(True, Path(out_png).as_posix(), None, note)

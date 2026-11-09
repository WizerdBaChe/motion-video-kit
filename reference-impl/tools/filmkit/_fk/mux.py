"""Video partial + author audio -> publish partial; container encoding only (PSM 6.4, Y-18).

Never -af, -filter:a, -ac, -ar, -shortest, -t: the author's audio is not changed (design 1.4).
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from .common import EncodeError, EnvError, Timeout, one_line
from .types import ProfileArgs

BANNED = ("-af", "-filter:a", "-ac", "-ar", "-shortest", "-t")


def mux_argv(video_partial: Path, audio: Path, args: ProfileArgs, publish_partial: Path) -> list[str]:
    return ["ffmpeg", "-hide_banner", "-nostats", "-loglevel", "error", "-y",
            "-i", str(video_partial), "-i", str(audio), "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
            *args.audio_args, *args.container_args, "-f", "mp4", str(publish_partial)]


def mux(video_partial: Path, audio: Path, args: ProfileArgs, publish_partial: Path, timeout_s: float) -> None:
    argv = mux_argv(video_partial, audio, args, publish_partial)
    try:
        r = subprocess.run(argv, capture_output=True, timeout=max(0.1, timeout_s))
    except FileNotFoundError:
        raise EnvError("ffmpeg not found on PATH")
    except subprocess.TimeoutExpired:
        raise Timeout(f"ffmpeg did not finish muxing within {timeout_s:.0f} s")
    if r.returncode != 0:
        tail = one_line(" | ".join(r.stderr.decode("utf-8", "replace").strip().splitlines()[-4:]) or "no stderr", 400)
        raise EncodeError(f"ffmpeg mux exited {r.returncode}: {tail}")

"""Frame pipe -> video partial (PSM 6.4; argv only from resolve_profile(), FK-INV-4)."""
from __future__ import annotations

import collections
import subprocess
import threading
from pathlib import Path

from .common import EncodeError, EnvError, Timeout, one_line
from .types import ProfileArgs


def encoder_argv(args: ProfileArgs, width: int, height: int, fps: int, video_partial: Path) -> list[str]:
    return ["ffmpeg", "-hide_banner", "-nostats", "-loglevel", "error", "-y",
            "-f", "image2pipe", "-c:v", "png", "-framerate", str(fps), "-i", "-",
            *args.video_args, *args.container_args, "-f", "mp4", str(video_partial)]


class Encoder:
    def __init__(self, argv: list[str]):
        self.argv = argv
        self.stderr = collections.deque(maxlen=20)
        try:
            self.proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        except FileNotFoundError:
            raise EnvError("ffmpeg not found on PATH")
        self._t = threading.Thread(target=self._drain, daemon=True)
        self._t.start()

    @property
    def pid(self) -> int:
        return self.proc.pid

    def _drain(self):
        for line in iter(self.proc.stderr.readline, b""):
            self.stderr.append(line.decode("utf-8", "replace").rstrip())

    def _tail(self) -> str:
        self._t.join(timeout=1.0)
        return one_line(" | ".join(self.stderr), 400) or "no stderr"

    def write(self, png: bytes) -> None:
        try:
            self.proc.stdin.write(png)
        except (BrokenPipeError, OSError, ValueError):
            self.proc.wait(timeout=5)
            raise EncodeError(f"ffmpeg stopped while receiving frames (exit {self.proc.returncode}): {self._tail()}")

    def close_stdin(self) -> None:
        try:
            self.proc.stdin.close()
        except OSError:
            pass

    def wait(self, timeout_s: float) -> None:
        try:
            rc = self.proc.wait(timeout=max(0.1, timeout_s))
        except subprocess.TimeoutExpired:
            self.kill()
            raise Timeout(f"ffmpeg did not finish encoding within {timeout_s:.0f} s")
        if rc != 0:
            raise EncodeError(f"ffmpeg exited {rc}: {self._tail()}")

    def kill(self) -> None:
        try:
            self.proc.kill()
            self.proc.wait(timeout=5)
        except Exception:
            pass


def open_encoder(args: ProfileArgs, width: int, height: int, fps: int, video_partial: Path) -> Encoder:
    return Encoder(encoder_argv(args, width, height, fps, video_partial))

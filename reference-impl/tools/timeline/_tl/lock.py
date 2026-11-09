"""FilmLock: OS byte lock on <folder>/.tl.lock (PSM 3.1, 5.5; TG-18).

Duplicates filmkit's OutputLock mechanism instead of importing it: the timeline library must stay mountable
without filmkit's private _fk package. The lseek-before-locking detail is taken from tools/filmkit/_fk/guard.py
(msvcrt.locking locks from the current file position, so the position is reset to byte 0 before lock and unlock).
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from .common import LOCK_NAME, Busy, posix

IS_WINDOWS = sys.platform == "win32"
if IS_WINDOWS:
    import msvcrt
else:  # unprobed off Windows; selftest reports the lock controls skipped
    import fcntl


class FilmLock:
    """Byte 0 of <folder>/.tl.lock; released by the OS when the holder ends. Retry 2.0 s every 0.05 s."""

    def __init__(self, folder: Path, retry_s: float = 2.0, step_s: float = 0.05):
        self.folder = Path(folder)
        self.path = self.folder / LOCK_NAME
        self.retry_s = retry_s
        self.step_s = step_s
        self.fd: int | None = None

    def _try(self, fd: int) -> bool:
        try:
            if IS_WINDOWS:
                os.lseek(fd, 0, 0)
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            else:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError:
            return False

    def __enter__(self) -> "FilmLock":
        self.folder.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.path, os.O_RDWR | os.O_CREAT)
        t0 = time.monotonic()
        while not self._try(fd):
            if time.monotonic() - t0 >= self.retry_s:
                os.close(fd)
                raise Busy(f"another tl command holds {posix(self.path)}",
                           hint="another tl command runs on this film; wait for it to end")
            time.sleep(self.step_s)
        self.fd = fd
        return self

    def __exit__(self, *exc) -> None:
        if self.fd is None:
            return
        try:
            if IS_WINDOWS:
                os.lseek(self.fd, 0, 0)
                msvcrt.locking(self.fd, msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(self.fd, fcntl.LOCK_UN)
        except OSError:
            pass
        os.close(self.fd)
        self.fd = None

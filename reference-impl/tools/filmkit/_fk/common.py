"""Exit codes, the FilmkitError hierarchy, atomic writes with retry, hashing helpers (PSM 6.0)."""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

EXIT_OK = 0
EXIT_NO_OUTPUT = 1
EXIT_BLOCKING = 2
EXIT_INCOMPLETE = 3

FK_DIR = ".filmkit"
DEFAULT_RETRY = {"attempts": 10, "step_s": 0.05}


class FilmkitError(Exception):
    kind = "internal"

    def __init__(self, message: str, hint: str | None = None, **fields):
        super().__init__(message)
        self.message = message
        self.hint = hint
        self.fields = fields


class Busy(FilmkitError):
    kind = "busy"


class SpecInvalid(FilmkitError):
    kind = "spec_invalid"


class OutputForeign(FilmkitError):
    kind = "output_foreign"


class EnvError(FilmkitError):
    kind = "env"


class PageContract(FilmkitError):
    kind = "page_contract"


class AssetLoad(FilmkitError):
    kind = "asset_load"


class NotReady(FilmkitError):
    kind = "not_ready"


class PageRuntime(FilmkitError):
    kind = "page_runtime"


class EncodeError(FilmkitError):
    kind = "encode"


class VerifyError(FilmkitError):
    kind = "verify"


class PublishError(FilmkitError):
    kind = "publish"


class Timeout(FilmkitError):
    kind = "timeout"


class Interrupted(FilmkitError):
    kind = "interrupted"


class Internal(FilmkitError):
    kind = "internal"


class RecordWriteError(Internal):
    kind = "internal"


ERROR_CLASSES = [Busy, SpecInvalid, OutputForeign, EnvError, PageContract, AssetLoad, NotReady, PageRuntime,
                 EncodeError, VerifyError, PublishError, Timeout, Interrupted, Internal, RecordWriteError]


class FkArgParser:
    """argparse.ArgumentParser whose error() raises SpecInvalid (exit 1 with five lines, not argparse's 2)."""

    def __new__(cls, *a, **kw):
        import argparse

        class _P(argparse.ArgumentParser):
            def error(self, message):
                raise SpecInvalid(f"invalid arguments: {message}", hint=f"see: python -X utf8 {self.prog} --help")
        return _P(*a, **kw)


# ---------------------------------------------------------------- selftest fault points
def fault_point(name: str, **ctx) -> None:
    """Selftest hook. FILMKIT_SELFTEST_FAULT="name=action[,name=action]".

    Actions: raise | interrupt | exit | sleep:<seconds>:<marker file>. A marker file receives ctx as JSON
    before the sleep, so a test process can act at that exact point. Unset in normal use.
    """
    spec = os.environ.get("FILMKIT_SELFTEST_FAULT")
    if not spec:
        return
    for item in spec.split(","):
        if "=" not in item:
            continue
        key, action = item.split("=", 1)
        if key != name:
            continue
        if action == "raise":
            raise RuntimeError(f"injected fault at {name}")
        if action == "interrupt":
            raise KeyboardInterrupt()
        if action == "exit":
            os._exit(137)
        if action.startswith("sleep:"):
            parts = action.split(":", 2)
            secs = float(parts[1])
            if len(parts) > 2 and parts[2]:
                Path(parts[2]).write_text(json.dumps({"point": name, "pid": os.getpid(), **ctx}), encoding="utf-8")
            time.sleep(secs)


# ---------------------------------------------------------------- hashing
def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def posix_abs(path: Path | str) -> str:
    return Path(path).resolve().as_posix()


def one_line(text: str, limit: int = 300) -> str:
    s = " ".join(str(text).split())
    return s if len(s) <= limit else s[: limit - 3] + "..."


def last_line(exc: BaseException) -> str:
    s = str(exc).strip().splitlines()
    return f"{type(exc).__name__}: {s[-1] if s else ''}".strip()


# ---------------------------------------------------------------- atomic writes
def replace_with_retry(src: Path, dst: Path, retry: dict | None = None) -> None:
    """os.replace with retry on PermissionError (a reader briefly blocks the replace on NTFS, SG-7)."""
    retry = retry or DEFAULT_RETRY
    attempts = int(retry.get("attempts", 10))
    step = float(retry.get("step_s", 0.05))
    for i in range(attempts):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if i == attempts - 1:
                raise
            time.sleep(step)


def unlink_with_retry(path: Path, retry: dict | None = None) -> bool:
    retry = retry or DEFAULT_RETRY
    for i in range(int(retry.get("attempts", 10))):
        try:
            path.unlink()
            return True
        except FileNotFoundError:
            return True
        except PermissionError:
            time.sleep(float(retry.get("step_s", 0.05)))
    return False


def _tmp_path(target: Path, make_fk_dir: bool) -> tuple[Path, bool]:
    fk = target.parent if target.parent.name == FK_DIR else target.parent / FK_DIR
    if fk.is_dir() or make_fk_dir:
        fk.mkdir(exist_ok=True)
        return fk / f"{target.name}.{os.getpid()}.tmp", False
    return target.with_name(target.name + ".filmkit-tmp"), True


def write_bytes_atomic(path: Path, data: bytes, retry: dict | None = None, make_fk_dir: bool = True) -> None:
    """Write tmp, fsync, os.replace (retry). Raises RecordWriteError when the replace keeps failing."""
    path = Path(path)
    tmp, beside = _tmp_path(path, make_fk_dir)
    try:
        with open(tmp, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        fault_point("atomic_write_before_replace", target=str(path))
        fault_point(f"atomic_write_before_replace:{path.name}", target=str(path))
        replace_with_retry(tmp, path, retry)
    except OSError as e:
        if beside or tmp.exists():
            unlink_with_retry(tmp, retry)
        raise RecordWriteError(f"cannot write {path.name}: {last_line(e)}",
                               hint=f"close the program locking {path.parent.as_posix()} (antivirus, sync software) and rerun")


def write_json_atomic(path: Path, obj: dict, retry: dict | None = None, make_fk_dir: bool = True) -> None:
    data = (json.dumps(obj, ensure_ascii=False, indent=1) + "\n").encode("utf-8")
    write_bytes_atomic(path, data, retry, make_fk_dir)


def read_json(path: Path) -> tuple[dict | None, str | None]:
    try:
        obj = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, "missing"
    except (OSError, ValueError) as e:
        return None, last_line(e)
    if not isinstance(obj, dict):
        return None, "not a JSON object"
    return obj, None

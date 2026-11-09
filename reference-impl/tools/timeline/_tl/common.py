"""Exit codes, TlError hierarchy, atomic writes with retry, rows, the five stdout lines (PSM 5.2, 5.3)."""
from __future__ import annotations

import json
import os
import shutil
import stat
import sys
import time
from pathlib import Path

EXIT_OK = 0
EXIT_REFUSED = 1
EXIT_BLOCKING = 2
EXIT_INCOMPLETE = 3

RETRY = {"attempts": 10, "step_s": 0.05}
TL_DIR = ".tl"
LOCK_NAME = ".tl.lock"

NOT_JUDGED_EN = "format and timing checked; pictures not judged"
NOT_JUDGED_ZH = "格式與時機已檢查，畫面未判斷"

# TL-INV-8: words no tool output may carry ("Done:" is the command status word and is allowed)
JUDGEMENT_WORDS_ZH = ("好看", "漂亮", "完美", "很棒", "完成", "成功了")
JUDGEMENT_WORDS_EN = ("looks good", "beautiful", "perfect", "great job", "polished", "finished film")


class TlError(Exception):
    kind = "internal"

    def __init__(self, message: str, hint: str | None = None, **fields):
        super().__init__(message)
        self.message = message
        self.hint = hint
        self.fields = fields


class SpecInvalid(TlError):
    kind = "spec_invalid"


class NotCurrent(TlError):
    kind = "not_current"


class NotApproved(TlError):
    kind = "not_approved"


class MissingRequired(TlError):
    kind = "missing_required"


class FingerprintMismatch(TlError):
    kind = "fingerprint_mismatch"


class EditedOutput(TlError):
    kind = "edited_output"


class VoiceMismatch(TlError):
    kind = "voice_mismatch"


class EnvError(TlError):
    kind = "env"


class Busy(TlError):
    kind = "busy"


class IllegalTransition(TlError):
    kind = "illegal_transition"


class InstrumentUnavailable(TlError):
    kind = "instrument_unavailable"


class Internal(TlError):
    kind = "internal"


ERROR_CLASSES = [SpecInvalid, NotCurrent, NotApproved, MissingRequired, FingerprintMismatch, EditedOutput,
                 VoiceMismatch, EnvError, Busy, IllegalTransition, InstrumentUnavailable, Internal]


class TlArgParser:
    """argparse.ArgumentParser whose error() raises SpecInvalid (exit 1 with five lines, not argparse's 2)."""

    def __new__(cls, *a, **kw):
        import argparse

        class _P(argparse.ArgumentParser):
            def error(self, message):
                raise SpecInvalid(f"invalid arguments: {message}", hint=f"see: python -X utf8 {self.prog} --help")
        return _P(*a, **kw)


# ---------------------------------------------------------------- selftest fault points (TG-16)
def fault_point(name: str) -> None:
    """Selftest hook. TL_SELFTEST_FAULT="name=exit|raise[,..]". Unset in normal use."""
    spec = os.environ.get("TL_SELFTEST_FAULT")
    if not spec:
        return
    for item in spec.split(","):
        key, _, action = item.partition("=")
        if key != name:
            continue
        if action == "exit":
            os._exit(137)
        if action == "raise":
            raise RuntimeError(f"injected fault at {name}")


# ---------------------------------------------------------------- text helpers
def one_line(text, limit: int = 300) -> str:
    s = " ".join(str(text).split())
    return s if len(s) <= limit else s[: limit - 3] + "..."


def last_line(exc: BaseException) -> str:
    s = str(exc).strip().splitlines()
    return f"{type(exc).__name__}: {s[-1] if s else ''}".strip()


def posix(path) -> str:
    return Path(path).as_posix()


def r6(x: float) -> float:
    """Values that are never frame-snapped are written rounded to 6 decimals (PSM 4 preamble)."""
    v = round(float(x), 6)
    return 0.0 if v == 0 else v


def dumps(obj) -> str:
    """One fixed way of writing tool JSON (BR-16): key order as built, shortest float repr, LF, final newline."""
    return json.dumps(obj, ensure_ascii=False, indent=2) + "\n"


def read_json(path: Path):
    try:
        raw = Path(path).read_bytes()
    except FileNotFoundError:
        raise SpecInvalid(f"missing file: {posix(path)}", hint=f"create {posix(path)}")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise SpecInvalid(f"not UTF-8 text: {posix(path)}", hint="save the file as UTF-8")
    if text.startswith("﻿"):
        text = text[1:]
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise SpecInvalid(f"not valid JSON: {posix(path)} line {e.lineno} col {e.colno}: {e.msg}",
                          hint=f"fix the JSON in {posix(path)}")


# ---------------------------------------------------------------- atomic writes (PSM 3.3)
def replace_with_retry(src: Path, dst: Path) -> None:
    for i in range(RETRY["attempts"]):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if i == RETRY["attempts"] - 1:
                raise
            time.sleep(RETRY["step_s"])


def tmp_dir_for(film: Path, target: Path) -> Path:
    """build/.tl/ for files under build/, <film>/.tl/ otherwise (never build/'s top level)."""
    film = Path(film)
    try:
        rel = Path(target).resolve().relative_to(film.resolve())
        if rel.parts and rel.parts[0] == "build":
            return film / "build" / TL_DIR
    except ValueError:
        pass
    return film / TL_DIR


def write_bytes_atomic(target: Path, data: bytes, tmp_dir: Path) -> None:
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp = tmp_dir / f"{target.name}.{os.getpid()}.tmp"
    with open(tmp, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    replace_with_retry(tmp, target)


def write_text_atomic(target: Path, text: str, tmp_dir: Path) -> None:
    write_bytes_atomic(target, text.encode("utf-8"), tmp_dir)


def film_write(film: Path, target: Path, text: str) -> None:
    write_text_atomic(target, text, tmp_dir_for(film, target))


def clean_tmp(film: Path) -> list[str]:
    """Partial .tmp files from an interrupted run are cleaned on the next start (PSM 11)."""
    notes = []
    for d in (Path(film) / TL_DIR, Path(film) / "build" / TL_DIR):
        if d.is_dir():
            for p in d.glob("*.tmp"):
                try:
                    p.unlink()
                    notes.append(f"removed partial file {p.name}")
                except OSError:
                    pass
    return notes


def _on_rm_error(func, path, exc_info):
    os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
    func(path)


def rmtree_force(path: Path) -> None:
    """rmtree that clears the read-only attribute first (versions/<n>/ files are read-only, TL-INV-6)."""
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=lambda f, p, e: _on_rm_error(f, p, None))
    else:  # pragma: no cover
        shutil.rmtree(path, onerror=_on_rm_error)


# ---------------------------------------------------------------- rows (PSM 4.6)
def row(check: str, where: str, bucket: str, *, stage: str, measured=None, expected=None, basis: str | None = None,
        provisional: bool = False, reason: str | None = None, message_key: str = "", message: str = "",
        rid: str | None = None) -> dict:
    return {"id": rid or f"{check}#{where}", "check": check, "stage": stage, "bucket": bucket, "where": where,
            "measured": measured, "expected": expected, "basis": basis, "provisional": provisional,
            "reason": reason, "message_key": message_key, "message": message}


def summarize(rows: list[dict]) -> dict:
    s = {"blocking": 0, "look": 0, "info": 0, "undetermined": 0}
    for r in rows:
        s[r["bucket"]] = s.get(r["bucket"], 0) + 1
    return s


# ---------------------------------------------------------------- five lines (PSM 5.2)
class Outcome:
    """What a command reports: five lines, exit code, --json document."""

    def __init__(self, command: str, film: str = ""):
        self.command = command
        self.film = film
        self.status = "done"
        self.kind = None
        self.message = ""
        self.hint = None
        self.result_line = ""
        self.steps: list[tuple[str, bool]] = []
        self.check_line = "Check: not run"
        self.look_line = "Look: not needed"
        self.notes: list[str] = []
        self.exit_code = EXIT_OK
        self.outputs: dict = {}
        self.summary: dict = {}
        self.result = None
        self.nothing_written = False

    def fail(self, err: TlError, nothing_written: bool = True) -> "Outcome":
        self.status = "failed"
        self.kind = err.kind
        self.message = err.message
        self.hint = err.hint
        self.exit_code = EXIT_REFUSED
        self.nothing_written = nothing_written
        return self

    def lines(self) -> list[str]:
        steps = " -> ".join(n if ok else f"{n} (failed)" for n, ok in self.steps) or "none"
        notes = list(self.notes)
        if NOT_JUDGED_EN not in notes:
            notes.append(NOT_JUDGED_EN)
        if self.status == "failed":
            if self.nothing_written:
                steps += "; nothing written"
            if self.hint:
                notes.insert(0, f"hint: {self.hint}")
            head = f"Failed: {self.kind} — {self.message}"
            chk, look = "Check: not run", "Look: not needed"
        else:
            head = f"Done: {self.command} {self.film} — {self.result_line}".rstrip(" —")
            chk, look = self.check_line, self.look_line
        note_text = one_line("; ".join(one_line(n, 600) for n in notes if n), 3000) if notes else "none"
        return [one_line(head, 1200), f"Steps: {steps}", chk, look, f"Notes: {note_text}"]

    def json_doc(self) -> dict:
        return {"command": self.command, "status": self.status, "kind": self.kind,
                "message": self.message if self.status == "failed" else self.result_line, "hint": self.hint,
                "exit_code": self.exit_code, "outputs": self.outputs, "summary": self.summary,
                "lines": self.lines(), "result": self.result}

"""Re-render command for format FAIL rows (D11, D28; PSM 4.3 rules 1-7).

Rebuilt from last_success's structured fields, never parsed from a cli (R-1). Paths absolute with "/" (R-2),
quoted by subprocess.list2cmdline.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from .common import sha256_file
from .types import ExpectedSpec

NEW_OUT = "<new-out>"


def _num(x: float) -> str:
    s = f"{float(x):.6f}".rstrip("0").rstrip(".")
    return s or "0"


def _abs(base: Path, p: str | None) -> str | None:
    if not p:
        return None
    q = Path(p)
    return (q if q.is_absolute() else (base / q)).resolve().as_posix()


def describes(record: dict | None, file: Path) -> bool:
    ls = (record or {}).get("last_success") or {}
    sha = (ls.get("output") or {}).get("sha256")
    return bool(sha) and Path(file).is_file() and sha256_file(Path(file)) == sha


def build(record: dict | None, file: Path, args, kit_dir: Path, *, spec: ExpectedSpec | None = None,
          include_audio: bool = False, record_dir: Path | None = None) -> str:
    """record: reconciled render.json; args: CheckArgs; spec: the check's ExpectedSpec (the authority)."""
    file = Path(file).resolve()
    rdir = Path(record_dir).resolve() if record_dir else file.parent
    exe = (Path(kit_dir).resolve() / "render.py").as_posix()
    if describes(record, file):
        ls = record["last_success"]
        exp = ls.get("expected") or {}
        page = _abs(rdir, ls.get("page"))
        out = (rdir / ls["output"]["name"]).resolve().as_posix()
        dur = exp.get("duration_s")
        size = f"{exp['width']}x{exp['height']}" if exp.get("width") else None
        fps = exp.get("fps")
        audio = _abs(rdir, ls.get("audio"))
        plan = _abs(rdir, ls.get("plan"))
        rules = ls.get("rules")
        film_type = ls.get("film_type")
        prof = ls.get("profile")
    else:
        page, out, dur, size, fps, audio, plan, rules, film_type = "<page>", NEW_OUT, None, None, None, None, None, None, None
        prof = getattr(args, "profile", None)
    if spec is not None:            # expected values override the base (rule 3)
        if spec.duration_s is not None and spec.duration_unusable is None:
            dur = spec.duration_s
        if spec.width is not None:
            size = f"{spec.width}x{spec.height}"
        if spec.fps is not None and spec.source.get("fps") in ("flag", "plan"):
            fps = spec.fps
        elif fps is None:
            fps = spec.fps
    argv = ["python", "-X", "utf8", exe, page, "-o", out,
            "--duration", _num(dur) if dur is not None else "<S>",
            "--size", size or "<WxH>"]
    if fps is not None:
        argv += ["--fps", str(int(fps))]
    if include_audio or audio:
        argv += ["--audio", audio or "<audio>"]
    if plan:
        argv += ["--plan", plan]
    if prof:
        argv += ["--profile", str(prof)]
    if rules:
        argv += ["--rules", Path(rules).as_posix()]
    if film_type:
        argv += ["--film-type", film_type]
    return subprocess.list2cmdline(argv)

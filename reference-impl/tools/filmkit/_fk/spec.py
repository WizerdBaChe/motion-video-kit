"""ExpectedSpec, frame count N, film_plan validation; shared by every entry (PSM 4.1, 5.2)."""
from __future__ import annotations

import json
import re
from pathlib import Path

from .common import SpecInvalid
from .types import ExpectedSpec

SIZE_RE = re.compile(r"^([0-9]+)x([0-9]+)$")
FILM_TYPE_RE = re.compile(r"^[a-z0-9-]{1,40}$")
PLAN_KEYS = {"schema_version", "expected", "film_type", "sections", "holds", "blacks", "silences", "narration_lines",
             "mount_design_axes", "mount_design_axes_why", "cuts", "pulses"}
EXPECTED_KEYS = {"duration_s", "size", "fps", "audio_expected"}


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def size_problem(text: str) -> str | None:
    m = SIZE_RE.match(text or "")
    if not m:
        return f"size {text!r} is not WxH"
    w, h = int(m.group(1)), int(m.group(2))
    if w % 2 or h % 2:
        return f"size {w}x{h} has an odd dimension (H.264 yuv420p needs even width and height)"
    if w < 16 or h < 16:
        return f"size {w}x{h} is below 16 px"
    return None


def parse_size(text: str) -> tuple[int, int]:
    p = size_problem(text)
    if p:
        raise SpecInvalid(p, hint="give --size as WxH with both numbers even and >= 16, e.g. 1280x720")
    w, h = SIZE_RE.match(text).groups()
    return int(w), int(h)


def frame_count(duration_s: float, fps: int) -> int:
    n = round(duration_s * fps)
    if abs(duration_s * fps - n) > 1e-6 or n < 1:
        near = max(n, 1) / fps
        raise SpecInvalid(f"duration {duration_s} s is not a whole number of frames at {fps} fps",
                          hint=f"duration must be a whole number of frames at {fps} fps (e.g. {near:g} s)")
    return n


def validate_plan(obj, default_fps: int = 30) -> list[str]:
    """Strict validation; empty list = valid. Unknown keys and zero-length intervals are errors."""
    errs: list[str] = []
    if not isinstance(obj, dict):
        return ["plan is not a JSON object"]
    for k in obj:
        if k not in PLAN_KEYS:
            errs.append(f"unknown key: {k}")
    if obj.get("schema_version") != 1 or isinstance(obj.get("schema_version"), bool):
        errs.append("schema_version must be 1")
    exp = obj.get("expected")
    if exp is not None:
        if not isinstance(exp, dict):
            errs.append("expected must be an object")
        else:
            for k in exp:
                if k not in EXPECTED_KEYS:
                    errs.append(f"unknown key: expected.{k}")
            fps = exp.get("fps", default_fps)
            if "fps" in exp and (not isinstance(fps, int) or isinstance(fps, bool) or not 1 <= fps <= 120):
                errs.append("expected.fps must be an integer 1-120")
                fps = None
            if "duration_s" in exp:
                d = exp["duration_s"]
                if not _num(d) or d <= 0:
                    errs.append("expected.duration_s must be a number > 0")
                elif isinstance(fps, int):
                    try:
                        frame_count(float(d), fps)
                    except SpecInvalid as e:
                        errs.append(f"expected.duration_s: {e.message}")
            if "size" in exp:
                s = exp["size"]
                p = size_problem(s) if isinstance(s, str) else "size must be a string WxH"
                if p:
                    errs.append(f"expected.size: {p}")
            if "audio_expected" in exp and not isinstance(exp["audio_expected"], bool):
                errs.append("expected.audio_expected must be true or false")
    if "film_type" in obj and (not isinstance(obj["film_type"], str) or not FILM_TYPE_RE.match(obj["film_type"])):
        errs.append("film_type must match ^[a-z0-9-]{1,40}$")
    if "mount_design_axes" in obj and not isinstance(obj["mount_design_axes"], bool):
        errs.append("mount_design_axes must be true or false")
    if "mount_design_axes_why" in obj and (not isinstance(obj["mount_design_axes_why"], str)
                                           or not obj["mount_design_axes_why"].strip()):
        errs.append("mount_design_axes_why must be a non-empty string")
    for key, need_why in (("sections", False), ("narration_lines", False), ("holds", True), ("blacks", True),
                          ("silences", True), ("cuts", True), ("pulses", True)):
        if key not in obj:
            continue
        arr = obj[key]
        if not isinstance(arr, list):
            errs.append(f"{key} must be a list")
            continue
        allowed = {"t0", "t1", "why"} if need_why else {"id", "t0", "t1"}
        for i, it in enumerate(arr):
            where = f"{key}[{i}]"
            if not isinstance(it, dict):
                errs.append(f"{where} must be an object")
                continue
            for k in it:
                if k not in allowed:
                    errs.append(f"unknown key: {where}.{k}")
            if not need_why and not isinstance(it.get("id"), str):
                errs.append(f"{where}.id must be a string")
            t0, t1 = it.get("t0"), it.get("t1")
            if not _num(t0) or not _num(t1) or t0 < 0 or t1 < 0:
                errs.append(f"{where}: t0 and t1 must be numbers >= 0")
            elif not t0 < t1:
                errs.append(f"{where}: t0 must be < t1")
            if need_why and (not isinstance(it.get("why"), str) or not it["why"].strip()):
                errs.append(f"{where}.why must be a non-empty string")
    return errs


def load_plan(path: Path, default_fps: int = 30) -> tuple[dict | None, str | None]:
    try:
        obj = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, f"plan file not found: {Path(path).as_posix()}"
    except (OSError, ValueError) as e:
        return None, f"plan file is not valid JSON: {e}"
    errs = validate_plan(obj, default_fps)
    if errs:
        return None, "; ".join(errs[:5])
    return obj, None


def build_expected_spec(flags, plan: dict | None, plan_mode: str, profile: dict) -> ExpectedSpec:
    """Per field: flag > plan (only plan_mode == "full") > profile default (fps only) > absent."""
    src: dict[str, str] = {}
    pexp = (plan or {}).get("expected", {}) if plan_mode == "full" else {}

    def pick(name, flag_val, plan_key):
        if flag_val is not None:
            src[name] = "flag"
            return flag_val
        if plan_key in pexp:
            src[name] = "plan"
            return pexp[plan_key]
        return None

    duration = pick("duration_s", getattr(flags, "duration_s", None), "duration_s")
    size = pick("size", getattr(flags, "size", None), "size")
    if isinstance(size, str):
        size = tuple(int(x) for x in size.split("x"))
    fps = pick("fps", getattr(flags, "fps", None), "fps")
    if fps is None:
        fps = int(profile.get("fps_default", 30))
        src["fps"] = "profile"
    audio = pick("audio_expected", getattr(flags, "audio_expected", None), "audio_expected")
    film_type = getattr(flags, "film_type", None)
    if film_type is not None:
        src["film_type"] = "flag"
    elif plan_mode == "full" and plan and plan.get("film_type"):
        film_type = plan["film_type"]
        src["film_type"] = "plan"
    n = None
    unusable = None
    if duration is not None:
        try:
            n = frame_count(float(duration), int(fps))
        except SpecInvalid as e:
            unusable = f"{e.message}; {e.hint}"
    return ExpectedSpec(duration_s=float(duration) if duration is not None else None, n_frames=n,
                        width=size[0] if size else None, height=size[1] if size else None, fps=int(fps),
                        audio_expected=audio, film_type=film_type, source=src, duration_unusable=unusable)

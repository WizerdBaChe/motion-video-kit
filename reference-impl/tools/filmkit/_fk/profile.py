"""Profile loading and resolve_profile(), the only encoder argv source (PSM 4.4, 6.4; FK-INV-4)."""
from __future__ import annotations

import json
from pathlib import Path

from .common import SpecInvalid
from .manifest import KIT_DIR
from .types import ProfileArgs


def load_profiles(kit_dir: Path = KIT_DIR) -> dict:
    return json.loads((kit_dir / "profiles.json").read_text(encoding="utf-8"))


def get_profile(name: str, kit_dir: Path = KIT_DIR) -> dict:
    profiles = load_profiles(kit_dir)["profiles"]
    if name not in profiles:
        raise SpecInvalid(f"unknown profile: {name}", hint=f"use one of: {', '.join(sorted(profiles))}")
    return profiles[name]


def resolve_profile(profile: dict, fps: int, has_audio: bool, name: str = "") -> ProfileArgs:
    v = profile["video"]
    video = ["-c:v", v["codec"], "-crf", str(v["crf"]), "-preset", v["preset"], "-pix_fmt", v["pix_fmt"]]
    audio: list[str] = []
    if has_audio:
        a = profile["audio"]
        audio = ["-c:a", a["codec"], "-b:a", a["bitrate"]]
    container = ["-movflags", "+faststart"] if v.get("faststart") else []
    return ProfileArgs(name=name or profile.get("name", ""), video_args=tuple(video), audio_args=tuple(audio),
                       container_args=tuple(container))


CODEC_NAMES = {"libx264": "h264", "aac": "aac"}


def probe_codec_name(encoder: str) -> str:
    return CODEC_NAMES.get(encoder, encoder)

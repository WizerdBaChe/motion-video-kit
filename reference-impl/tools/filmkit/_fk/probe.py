"""ProbeFacts via ffprobe (PSM 6.5)."""
from __future__ import annotations

import json
import struct
import subprocess
import time
from fractions import Fraction
from pathlib import Path

from .common import EnvError, one_line
from .types import ProbeFacts

TIMED_OUT = "check timed out"


def top_atoms(path: Path) -> list[str]:
    """Top-level MP4 atom types in file order (32-bit size, size 1 -> 64-bit largesize, size 0 -> to EOF)."""
    out = []
    size_total = Path(path).stat().st_size
    with open(path, "rb") as f:
        pos = 0
        while pos + 8 <= size_total:
            f.seek(pos)
            hdr = f.read(16)
            if len(hdr) < 8:
                break
            sz, typ = struct.unpack(">I4s", hdr[:8])
            if sz == 1:
                if len(hdr) < 16:
                    break
                sz = struct.unpack(">Q", hdr[8:16])[0]
            elif sz == 0:
                sz = size_total - pos
            if sz < 8:
                break
            out.append(typ.decode("latin1"))
            pos += sz
    return out


def is_faststart(path: Path) -> bool:
    atoms = top_atoms(path)
    if "moov" not in atoms or "mdat" not in atoms:
        return False
    return atoms.index("moov") < atoms.index("mdat")


def _frac(s) -> float | None:
    try:
        v = Fraction(s)
        return float(v) if v else None
    except (ValueError, ZeroDivisionError, TypeError):
        return None


def probe(file: Path, deadline: float) -> ProbeFacts:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        return ProbeFacts(readable=None, error=TIMED_OUT)
    argv = ["ffprobe", "-v", "error", "-count_packets", "-show_entries",
            "stream=index,codec_type,codec_name,pix_fmt,width,height,r_frame_rate,avg_frame_rate,nb_read_packets,"
            "duration,channels,sample_rate:format=duration", "-of", "json", str(file)]
    try:
        r = subprocess.run(argv, capture_output=True, timeout=remaining)
    except FileNotFoundError:
        raise EnvError("ffprobe not found on PATH")
    except subprocess.TimeoutExpired:
        return ProbeFacts(readable=None, error=TIMED_OUT)
    err = r.stderr.decode("utf-8", "replace").strip()
    try:
        j = json.loads(r.stdout.decode("utf-8", "replace") or "{}")
    except ValueError:
        j = {}
    streams = j.get("streams") or []
    v = next((s for s in streams if s.get("codec_type") == "video"), None)
    a = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if r.returncode != 0 or v is None:
        return ProbeFacts(readable=False, error=one_line(err.splitlines()[-1] if err else "no video stream", 300))
    fps_avg, fps_r = _frac(v.get("avg_frame_rate")), _frac(v.get("r_frame_rate"))
    n = int(v["nb_read_packets"]) if str(v.get("nb_read_packets", "")).isdigit() else None
    vdur = float(v["duration"]) if v.get("duration") not in (None, "N/A") else (n / fps_avg if n and fps_avg else None)
    adur = float(a["duration"]) if a and a.get("duration") not in (None, "N/A") else None
    audio = None
    if a:
        audio = {"codec": a.get("codec_name"), "channels": a.get("channels"),
                 "sample_rate": int(a["sample_rate"]) if str(a.get("sample_rate", "")).isdigit() else None}
    try:
        fs = is_faststart(Path(file))
    except OSError:
        fs = None
    return ProbeFacts(readable=True, n_frames=n, video_duration_s=vdur, audio_duration_s=adur,
                      width=v.get("width"), height=v.get("height"), fps_avg=fps_avg, fps_r=fps_r,
                      fps_constant=(fps_avg is not None and fps_r is not None and abs(fps_avg - fps_r) < 1e-9),
                      video_codec=v.get("codec_name"), pix_fmt=v.get("pix_fmt"), faststart=fs, audio=audio,
                      error=None)

"""One decode pass: black / frozen / silent / astats / ebur128, plus the first-frame probe (PSM 6.5, design SG-15).

`scan()` runs one ffmpeg pass over the file and parses its stderr into intervals; then closes the intervals that
are still open when the file ends (SG-15): a film that ends still and silent is measured as a whole interval, not
dropped. It states what ffmpeg reported and how the open ends were closed; it judges nothing (judge.py does).

M3: the audio chain ends with `ebur128=peak=true:framelog=quiet`; only its closing summary is parsed (Q-19:
without `framelog=quiet` stderr carries one line per 100 ms). Narration lines named by the plan get one more
short pass each (peak level inside the line's interval, FK-R-9 line branch).
"""
from __future__ import annotations

import math
import re
import statistics
import struct
import subprocess
import time
from pathlib import Path

from .common import fault_point, last_line, one_line
from .types import Interval, ProbeFacts, ScanEvents

NOT_BUILT = "content scan not built in this kit version"      # kept for callers that import the old name
TIMED_OUT = "check timed out"
FIRST_FRAME_SIZE = (64, 36)
# W32: per frame pair the largest tile (1/16 of the width) of the absolute luma difference, on a 320x180 grey picture
# cut into 16x9 tiles; tblend yields one value fewer than there are frames (checked by the W32-fail control)
LOCAL_MOTION_VF = "scale=320:180,format=gray,format=gray16le,tblend=all_mode=difference,scale=16:9:flags=area"
LOCAL_MOTION_TILES = 16 * 9
FILM_START_EPS_S = 0.1  # a still that starts within this many seconds of frame 0 touches the film start (W32: never excluded)

BLACK_RE = re.compile(r"black_start:\s*(-?[\d.]+)\s+black_end:\s*(-?[\d.]+)")
FREEZE_START_RE = re.compile(r"freeze_start:\s*(-?[\d.]+)")
FREEZE_END_RE = re.compile(r"freeze_end:\s*(-?[\d.]+)")
SILENCE_START_RE = re.compile(r"silence_start:\s*(-?[\d.]+)")
SILENCE_END_RE = re.compile(r"silence_end:\s*(-?[\d.]+)")
PEAK_RE = re.compile(r"Peak level dB:\s*(-?inf|-?[\d.]+)", re.I)
# ebur128 closing summary (framelog=quiet leaves only this block in stderr, Q-19); stderr may carry CRLF
LOUD_RE = re.compile(r"Integrated loudness:\s+I:\s*(-?inf|-?[\d.]+)\s*LUFS\s+Threshold:\s*(-?inf|-?[\d.]+)\s*LUFS\s+"
                     r"Loudness range:\s+LRA:\s*([\d.]+)\s*LU.*?True peak:\s+Peak:\s*(-?inf|-?[\d.]+)\s*dBFS", re.S | re.I)
EBUR128_AF = "ebur128=peak=true:framelog=quiet"


def video_end_of(facts: ProbeFacts) -> float | None:
    """n_frames / fps (PSM 6.5); the stream duration when either is missing."""
    if facts.n_frames and facts.fps_avg:
        return facts.n_frames / facts.fps_avg
    return facts.video_duration_s


def film_end_of(facts: ProbeFacts) -> float | None:
    """max(video_end, audio_duration_s) (design SG-15 v4.4): the end every closed interval is clamped to."""
    ve = video_end_of(facts)
    ends = [x for x in (ve, facts.audio_duration_s) if x is not None]
    return max(ends) if ends else None


def parse_stderr(text: str) -> dict:
    """The raw detector lines of one ffmpeg run -> lists of (start, end|None). No closure here."""
    black, freeze_starts, freeze_ends, sil_starts, sil_ends, peaks = [], [], [], [], [], []
    for line in text.splitlines():
        if "blackdetect" in line:
            m = BLACK_RE.search(line)
            if m:
                black.append((float(m.group(1)), float(m.group(2))))
        elif "freezedetect" in line:
            m = FREEZE_START_RE.search(line)
            if m:
                freeze_starts.append(float(m.group(1)))
            m = FREEZE_END_RE.search(line)
            if m:
                freeze_ends.append(float(m.group(1)))
        elif "silencedetect" in line:
            m = SILENCE_START_RE.search(line)
            if m:
                sil_starts.append(float(m.group(1)))
            m = SILENCE_END_RE.search(line)
            if m:
                sil_ends.append(float(m.group(1)))
        elif "astats" in line:
            m = PEAK_RE.search(line)
            if m:
                peaks.append(float(m.group(1)))
    return {"black": black, "freeze_starts": freeze_starts, "freeze_ends": freeze_ends,
            "silence_starts": sil_starts, "silence_ends": sil_ends, "peaks": peaks}


def parse_loudness(text: str) -> dict | None:
    """The ebur128 summary of one ffmpeg run -> {integrated_lufs, threshold_lufs, lra_lu, true_peak_db}, or None when
    the run printed none (no audio, or the filter did not close). Values are floats; -inf is kept."""
    m = LOUD_RE.search(text)
    if not m:
        return None
    return {"integrated_lufs": float(m.group(1)), "threshold_lufs": float(m.group(2)), "lra_lu": float(m.group(3)),
            "true_peak_db": float(m.group(4))}


def line_peaks(file: Path, lines: list[dict], deadline: float) -> list[dict]:
    """Peak level (astats, dB) inside each narration line's interval: one short pass per line, the interval cut with
    atrim after decoding so the edges are exact. peak_db is None when the interval holds no samples. Raises
    TimeoutError at the deadline."""
    out = []
    for ln in lines:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError(TIMED_OUT)
        t0, t1 = float(ln["t0"]), float(ln["t1"])
        af = f"atrim=start={t0:.6f}:end={t1:.6f},astats=metadata=1:reset=0"
        argv = ["ffmpeg", "-hide_banner", "-nostats", "-i", str(file), "-map", "0:a:0", "-af", af, "-f", "null", "-"]
        try:
            r = subprocess.run(argv, capture_output=True, timeout=remaining)
        except subprocess.TimeoutExpired:
            raise TimeoutError(TIMED_OUT)
        if r.returncode != 0:
            tail = [x for x in r.stderr.decode("utf-8", "replace").strip().splitlines() if x.strip()]
            raise RuntimeError("line scan failed: " + one_line(tail[-1] if tail else f"ffmpeg exit {r.returncode}", 300))
        peaks = parse_stderr(r.stderr.decode("utf-8", "replace"))["peaks"]
        out.append({"id": ln["id"], "t0": t0, "t1": t1, "peak_db": peaks[-1] if peaks else None})
    return out


def pair(starts: list[float], ends: list[float]) -> list[tuple[float, float | None]]:
    """Starts and ends come in order and alternate; a start without an end is open (None)."""
    out = []
    for i, s in enumerate(starts):
        out.append((s, ends[i] if i < len(ends) else None))
    return out


def close_intervals(raw: dict, facts: ProbeFacts, thresholds: dict) -> dict:
    """SG-15 closure (PSM 6.5). Returns {"black": [...], "frozen": [...], "silent": [...]} of Interval."""
    fps = facts.fps_avg or 30.0
    video_end = video_end_of(facts) or 0.0
    film_end = film_end_of(facts) or video_end
    last_pts = video_end - 1.0 / fps
    audio_end = facts.audio_duration_s if facts.audio_duration_s is not None else video_end
    sr = (facts.audio or {}).get("sample_rate") or 48000
    one_audio_frame = 1024.0 / sr
    tol = 1e-3

    win = start_window(thresholds)

    def keep(iv: Interval, key: str) -> bool:
        floor = float(thresholds.get(key, {}).get("min_duration_s", 0))
        if key == "freeze":     # D18: a still that runs to the end is kept down to its own floor; W33: so is one that
            # starts inside the start window (profile freeze.start_window_s)
            floor = freeze_floor(thresholds, at_end=iv.open_at_end, at_start=win is not None and iv.t0 <= win + 1e-9)
        return (iv.t1 - iv.t0) >= floor - tol

    black = []
    for s, e in raw["black"]:
        t0, t1, open_end = max(0.0, s), e, False
        if t1 >= last_pts - 0.5 / fps:           # black_end at the last frame's pts (Q-14: one-frame error accepted)
            t1, open_end = video_end, True
        black.append(Interval(round(t0, 6), round(min(t1, film_end), 6), open_end))
    frozen = []
    for s, e in pair(raw["freeze_starts"], raw["freeze_ends"]):
        if e is None:
            frozen.append(Interval(round(max(0.0, s), 6), round(video_end, 6), True))
        else:
            frozen.append(Interval(round(max(0.0, s), 6), round(min(e, film_end), 6), False))
    silent = []
    for s, e in pair(raw["silence_starts"], raw["silence_ends"]):
        t0 = max(0.0, s)
        t1 = audio_end if e is None else e
        near_end = e is None or t1 >= film_end - one_audio_frame
        if near_end:
            t1 = min(t1, film_end)               # clamp only at or past film_end - one audio frame (R-7c)
        flag = near_end and (film_end - t1) <= one_audio_frame + 1e-6
        silent.append(Interval(round(t0, 6), round(t1, 6), flag))
    return {"black": [i for i in black if keep(i, "black")],
            "frozen": [i for i in frozen if keep(i, "freeze")],
            "silent": [i for i in silent if keep(i, "silence")]}


def start_window(thresholds: dict) -> float | None:
    """The profile's `freeze.start_window_s` (W33, user ruling 2026-10-10): a still that starts within this many seconds
    of frame 0 is held to `start_min_duration_s`. None when the profile has no window, so no still counts as a head one."""
    w = (thresholds.get("freeze") or {}).get("start_window_s")
    return float(w) if w is not None else None


def freeze_floor(thresholds: dict, at_end: bool = False, at_start: bool = False) -> float:
    """Shortest still that is kept: `min_duration_s` anywhere; `end_min_duration_s` (when set) for a still that runs to
    the end of the film (D18, 2026-10-10: the end-hold range starts at 1.5 s, under the general 2.0 s floor);
    `start_min_duration_s` (when set) for one that starts inside the start window (W33, 2026-10-10). Both flags: the
    smallest."""
    f = thresholds.get("freeze", {})
    floors = [float(f.get("min_duration_s", 2.0))]
    if at_end and f.get("end_min_duration_s") is not None:
        floors.append(float(f["end_min_duration_s"]))
    if at_start and f.get("start_min_duration_s") is not None:
        floors.append(float(f["start_min_duration_s"]))
    return min(floors)


def local_motion_levels(file: Path, t0: float, t1: float, deadline: float) -> list[float]:
    """W32: for each frame pair inside [t0, t1], the largest tile's mean absolute luma difference (0..1). One ffmpeg
    pass, stdlib only. Raises TimeoutError at the deadline and RuntimeError when ffmpeg fails or returns no frame."""
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError(TIMED_OUT)
    argv = ["ffmpeg", "-hide_banner", "-nostats", "-loglevel", "error", "-ss", f"{t0:.6f}", "-t", f"{t1 - t0:.6f}",
            "-i", str(file), "-an", "-vf", LOCAL_MOTION_VF, "-f", "rawvideo", "-pix_fmt", "gray16le", "-"]
    try:
        r = subprocess.run(argv, capture_output=True, timeout=remaining)
    except subprocess.TimeoutExpired:
        raise TimeoutError(TIMED_OUT)
    if r.returncode != 0:
        tail = [x for x in r.stderr.decode("utf-8", "replace").strip().splitlines() if x.strip()]
        raise RuntimeError(one_line(tail[-1] if tail else f"ffmpeg exit {r.returncode}", 300))
    size = LOCAL_MOTION_TILES * 2
    n = len(r.stdout) // size
    if n == 0:
        raise RuntimeError("ffmpeg returned no frame difference")
    return [max(struct.unpack_from(f"<{LOCAL_MOTION_TILES}H", r.stdout, i * size)) / 65535.0 for i in range(n)]


def split_local_motion(file: Path, frozen: list, thresholds: dict, deadline: float) -> tuple[list, list, list]:
    """W32: take the stills whose largest tile moves out of `frozen`. Returns (kept, moved, notes); `moved` holds
    (t0, t1, median over frames). The median, not the maximum: a true still reaches 0.027 in a single frame at its
    edges. A pass that fails or runs out of time keeps its interval and adds a note; this never raises. Without
    `freeze.local_tile_median_max` in the profile no pass runs. Mid-film stills only (user ruling 2026-10-10): one
    that touches the film start (t0 <= FILM_START_EPS_S) or runs to the end (open_at_end) is kept without a pass,
    because a head or end hold is a hold whatever moves in a corner of it."""
    limit = (thresholds.get("freeze") or {}).get("local_tile_median_max")
    if limit is None or not frozen:
        return list(frozen), [], []
    kept, moved, notes = [], [], []
    for iv in frozen:
        if iv.open_at_end or iv.t0 <= FILM_START_EPS_S + 1e-9:
            kept.append(iv)
            continue
        try:
            fault_point("local_motion")
            med = statistics.median(local_motion_levels(file, iv.t0, iv.t1, deadline))
        except TimeoutError:
            kept.append(iv)
            notes.append(f"local motion pass timed out for {iv.t0:.2f}-{iv.t1:.2f} s; the interval is kept as a still")
            continue
        except Exception as e:
            kept.append(iv)
            notes.append(f"local motion pass failed for {iv.t0:.2f}-{iv.t1:.2f} s ({last_line(e)}); the interval is kept as a still")
            continue
        if med > float(limit):
            moved.append((iv.t0, iv.t1, round(med, 6)))
        else:
            kept.append(iv)
    return kept, moved, notes


def first_frame_stats(file: Path, fps: float, n_frames: int | None, deadline: float,
                      flat_std: float | None = None) -> dict | None:
    """Luma of frame 0 and of the frame at index `fps` (one second in), at 64x36 (Reading 5 of the M2 card).
    {"std": luma stddev of frame 0, "mean": its mean, "diff": mean absolute luma difference between the two,
    "flat_frames": how many leading frames (0..index) have std <= `flat_std` (D18: a one- or two-frame flat start is not
    visible), absent when `flat_std` is None}. None when the film has no frame at 1 s (UNDET upstream)."""
    idx = int(round(fps))
    if n_frames is not None and n_frames <= idx:
        return None
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError(TIMED_OUT)
    w, h = FIRST_FRAME_SIZE
    argv = ["ffmpeg", "-hide_banner", "-nostats", "-loglevel", "error", "-i", str(file), "-an", "-frames:v", str(idx + 1),
            "-vf", f"scale={w}:{h}:flags=area,format=gray", "-f", "rawvideo", "-"]
    try:
        r = subprocess.run(argv, capture_output=True, timeout=remaining)
    except subprocess.TimeoutExpired:
        raise TimeoutError(TIMED_OUT)
    size = w * h
    if r.returncode != 0 or len(r.stdout) < size * (idx + 1):
        return None
    a, b = r.stdout[:size], r.stdout[size * idx: size * (idx + 1)]
    mean = sum(a) / size
    std = math.sqrt(sum((x - mean) ** 2 for x in a) / size)
    diff = sum(abs(x - y) for x, y in zip(a, b)) / size
    out = {"std": round(std, 3), "mean": round(mean, 3), "diff": round(diff, 3), "index": idx}
    if flat_std is not None:
        n = 0
        while n <= idx:
            fr = r.stdout[size * n: size * (n + 1)]
            m = sum(fr) / size
            if math.sqrt(sum((x - m) ** 2 for x in fr) / size) > flat_std:
                break
            n += 1
        out["flat_frames"] = n
    return out


def scan(file: Path, facts: ProbeFacts, profile: dict, want: set[str], deadline: float,
         lines: list[dict] | None = None) -> ScanEvents:
    """One ffmpeg pass (black, freeze, silence, astats, ebur128), the first-frame probe and, when `lines` (the plan's
    narration lines) are given, one short pass per line. Never raises: a failure or a deadline comes back as
    ScanEvents(error=..., finished=False) and the rows become UNDET with unfinished true."""
    th = profile.get("thresholds", {})
    try:
        fault_point("scan")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return ScanEvents(error=TIMED_OUT, finished=False)
        b, f, s = th.get("black", {}), th.get("freeze", {}), th.get("silence", {})
        vf = (f"blackdetect=d={b.get('min_duration_s', 2.0)}:pic_th={b.get('picture_ratio', 0.98)}:"
              f"pix_th={b.get('pixel_threshold', 0.10)},freezedetect=n={f.get('noise', 0.001)}:"
              f"d={freeze_floor(th, at_end=True, at_start=True):g}")
        argv = ["ffmpeg", "-hide_banner", "-nostats", "-i", str(file), "-map", "0:v:0", "-vf", vf]
        if facts.audio:
            af = (f"silencedetect=n={s.get('noise_db', -50)}dB:d={s.get('min_duration_s', 2.0)},"
                  f"astats=metadata=1:reset=0,{EBUR128_AF}")
            argv += ["-map", "0:a:0", "-af", af]
        argv += ["-f", "null", "-"]
        try:
            r = subprocess.run(argv, capture_output=True, timeout=remaining)
        except FileNotFoundError:
            return ScanEvents(error="scan failed: ffmpeg not found on PATH", finished=False)
        except subprocess.TimeoutExpired:
            return ScanEvents(error=TIMED_OUT, finished=False)
        text = r.stderr.decode("utf-8", "replace")
        if r.returncode != 0:
            lines = [ln for ln in text.strip().splitlines() if ln.strip()]
            return ScanEvents(error="scan failed: " + one_line(lines[-1] if lines else f"ffmpeg exit {r.returncode}", 300),
                              finished=False)
        raw = parse_stderr(text)
        closed = close_intervals(raw, facts, th)
        frozen, moved, lm_notes = split_local_motion(file, closed["frozen"], th, deadline)
        peak = raw["peaks"][-1] if (facts.audio and raw["peaks"]) else None   # the last one is Overall
        first = None
        if "first_frame" in want and facts.fps_avg:
            try:
                first = first_frame_stats(file, facts.fps_avg, facts.n_frames, deadline,
                                          th.get("first_frame", {}).get("max_luma_stddev"))
            except TimeoutError:
                return ScanEvents(error=TIMED_OUT, finished=False)
        loud = parse_loudness(text) if facts.audio else None
        line_res = ()
        if lines and facts.audio:
            try:
                line_res = tuple(line_peaks(file, lines, deadline))
            except TimeoutError:
                return ScanEvents(error=TIMED_OUT, finished=False)
        return ScanEvents(black=tuple(closed["black"]), frozen=tuple(frozen), silent=tuple(closed["silent"]),
                          audio_peak_db=peak, loudness=loud, error=None, finished=True, first_frame=first, lines=line_res,
                          frozen_local_motion=tuple(moved), notes=tuple(lm_notes))
    except Exception as e:      # a scan failure is a row-level UNDET, never a crash of the check
        return ScanEvents(error="scan failed: " + last_line(e), finished=False)

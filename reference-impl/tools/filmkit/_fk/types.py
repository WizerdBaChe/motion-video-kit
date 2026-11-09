"""In-memory types (PSM 4.10). Frozen dataclasses unless noted."""
from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path


@dataclass(frozen=True)
class ExpectedSpec:
    duration_s: float | None
    n_frames: int | None
    width: int | None
    height: int | None
    fps: int | None
    audio_expected: bool | None
    film_type: str | None
    source: dict = field(default_factory=dict)
    duration_unusable: str | None = None   # reason when a duration was given but is not a whole number of frames

    def to_json(self) -> dict:
        return {"duration_s": self.duration_s, "n_frames": self.n_frames, "width": self.width, "height": self.height,
                "fps": self.fps, "audio_expected": self.audio_expected, "source": dict(self.source)}


@dataclass(frozen=True)
class Decision:
    result: str                      # "REJECTED" | "CREATED"
    kind: str | None = None
    message: str | None = None
    hint: str | None = None
    notes: tuple = ()
    previous: dict | None = None     # reconciled record
    lock: object | None = None       # the held OutputLock when CREATED (ledger: carries the lock out of start_decision)


@dataclass(frozen=True)
class FontLoad:
    family: str
    src: str
    status: str                      # "loaded" | "error"


@dataclass(frozen=True)
class FamilyCheck:
    family: str
    result: str                      # "present" | "substituted" | "undetermined"
    decided_by: str | None
    per_script: dict
    lists: dict
    baselines: dict
    sampled_at: tuple

    def to_json(self) -> dict:
        return {"family": self.family, "result": self.result, "decided_by": self.decided_by,
                "per_script": dict(self.per_script), "lists": self.lists, "baselines": self.baselines,
                "sampled_at": list(self.sampled_at)}


@dataclass
class LoadReport:                     # mutable during capture
    ready_shape: str = "absent"
    fonts: list = field(default_factory=list)
    font_families: list = field(default_factory=list)
    local_files: list = field(default_factory=list)
    blocked_requests: list = field(default_factory=list)
    console: list = field(default_factory=list)
    console_truncated: bool = False

    def to_json(self) -> dict:
        return {"ready_shape": self.ready_shape,
                "fonts": [{"family": f.family, "src": f.src, "status": f.status} for f in self.fonts],
                "font_families": [f.to_json() for f in self.font_families],
                "local_files": list(self.local_files), "blocked_requests": list(self.blocked_requests),
                "console": list(self.console), "console_truncated": self.console_truncated}


@dataclass(frozen=True)
class RenderArgs:
    page: Path
    out: Path
    duration_s: float | None
    size: tuple | None
    fps: int | None
    audio: Path | None
    audio_expected: bool | None
    plan: Path | None
    profile: str
    rules: Path | None
    film_type: str | None
    timeout_s: float | None
    ready_timeout_s: float | None
    check_timeout_s: float | None
    keep_frames: bool
    json_out: bool
    argv: tuple = ()
    target: str | None = None      # M3: name of a rules-file loudness target the check compares against (FK-R-17)
    start_s: Fraction = Fraction(0)  # window render: frame i shows page time start + i/fps (agent-review design M2)
    gpu: bool = False                # capture on the hardware GPU (opt-in; default stays software rendering)


@dataclass(frozen=True)
class ReportMeta:
    file: dict
    render_record: dict | None
    plan: dict
    expected: dict
    profile: str
    kit_hash: str
    rules: dict | None
    probe: dict
    events: list
    exemptions: list
    internal_error: str | None
    look_without_exemptions: int | None = None     # BR-6's second count (PSM 7.3); None -> equals look
    exemption_totals: dict | None = None           # {"declarations", "seconds", "share_of_film"} or None (no declarations)


@dataclass(frozen=True)
class CheckSummary:
    blocking: int
    look: int
    undetermined: int
    confirmed: int
    look_without_exemptions: int
    incomplete: bool
    internal_error: str | None

    def to_json(self) -> dict:
        return {"blocking": self.blocking, "look": self.look, "undetermined": self.undetermined,
                "confirmed": self.confirmed, "look_without_exemptions": self.look_without_exemptions,
                "incomplete": self.incomplete, "internal_error": self.internal_error}


@dataclass(frozen=True)
class RunEvent:
    state: str
    at: str
    kind: str | None = None
    message: str | None = None
    hint: str | None = None
    progress: dict | None = None


@dataclass(frozen=True)
class RunSummary:
    final_state: str
    kind: str | None
    hint: str | None
    n_frames: int | None
    duration_s: float | None
    width: int | None
    height: int | None
    video_codec: str | None
    pix_fmt: str | None
    audio_desc: str | None
    steps: tuple
    out_path: str
    published: bool
    message: str | None = None
    notes: tuple = ()
    fps: float | None = None
    previous_kept: bool = False
    display_dir: str = ""            # the output folder as the caller wrote it, with a trailing "/" (or "")


@dataclass(frozen=True)
class ProfileArgs:
    name: str
    video_args: tuple
    audio_args: tuple
    container_args: tuple

    def to_json(self) -> dict:
        return {"name": self.name, "video_args": list(self.video_args), "audio_args": list(self.audio_args),
                "container_args": list(self.container_args)}


@dataclass(frozen=True)
class ProbeFacts:
    readable: bool | None             # None: the probe did not finish (deadline)
    n_frames: int | None = None
    video_duration_s: float | None = None
    audio_duration_s: float | None = None
    width: int | None = None
    height: int | None = None
    fps_avg: float | None = None
    fps_r: float | None = None
    fps_constant: bool | None = None
    video_codec: str | None = None
    pix_fmt: str | None = None
    faststart: bool | None = None
    audio: dict | None = None
    error: str | None = None

    def to_json(self) -> dict:
        return {k: getattr(self, k) for k in ("readable", "n_frames", "video_duration_s", "audio_duration_s", "width",
                                              "height", "fps_avg", "fps_r", "fps_constant", "video_codec", "pix_fmt",
                                              "faststart", "audio", "error")}


@dataclass(frozen=True)
class Interval:
    t0: float
    t1: float
    open_at_end: bool = False


@dataclass(frozen=True)
class ScanEvents:
    black: tuple = ()
    frozen: tuple = ()
    silent: tuple = ()
    audio_peak_db: float | None = None
    loudness: dict | None = None
    error: str | None = None
    finished: bool = False
    first_frame: dict | None = None     # {"std", "mean", "diff", "index"}: frame 0 vs the frame at 1 s (FK-R-10)
    lines: tuple = ()                   # M3: [{"id", "t0", "t1", "peak_db"}] per narration line (FK-R-9 line branch)
    frozen_local_motion: tuple = ()     # W32: (t0, t1, median) of still-looking spans left out because one tile moves
    notes: tuple = ()                   # W32: why a pass was skipped (its interval is kept); reaches the check notes


@dataclass(frozen=True)
class OutputNames:
    json: str
    md: str
    sheet: str


@dataclass(frozen=True)
class SheetResult:
    ok: bool
    path: str | None
    error: str | None
    note: str | None = None


@dataclass(frozen=True)
class CheckResult:
    rows: list
    summary: CheckSummary
    exit_code: int
    outputs: OutputNames
    sheet: SheetResult
    check_json: dict | None = None
    notes: tuple = ()

"""ffprobe check of a partial and the publish sequence (PSM 6.4; FK-INV-1, D23, Q-13)."""
from __future__ import annotations

import time
from pathlib import Path
from typing import Protocol

from .common import PublishError, VerifyError, fault_point, last_line, replace_with_retry, sha256_file
from .probe import probe
from .profile import probe_codec_name
from .types import ExpectedSpec, ProbeFacts


class Publishable(Protocol):
    def set_pending(self, sha256: str, nbytes: int) -> None: ...
    def promote(self, out_meta: dict) -> None: ...


class PostPublishError(Exception):
    """promote() failed after the rename: the file is published and owned through pending_publish."""

    def __init__(self, cause: BaseException, sha256: str):
        super().__init__(last_line(cause))
        self.cause = cause
        self.sha256 = sha256


def verify_partial(partial: Path, expected: ExpectedSpec, profile: dict) -> ProbeFacts:
    facts = probe(partial, time.monotonic() + 120)
    if not facts.readable:
        raise VerifyError(f"encoded file is not readable: {facts.error}")
    want_codec = probe_codec_name(profile["video"]["codec"])
    got = f"{facts.n_frames} frames {facts.width}x{facts.height} {facts.video_codec}/{facts.pix_fmt} faststart={facts.faststart}"
    want = (f"{expected.n_frames} frames {expected.width}x{expected.height} {want_codec}/{profile['video']['pix_fmt']} "
            f"faststart={bool(profile['video'].get('faststart'))}")
    if (facts.n_frames != expected.n_frames or facts.width != expected.width or facts.height != expected.height
            or facts.video_codec != want_codec or facts.pix_fmt != profile["video"]["pix_fmt"]
            or facts.faststart != bool(profile["video"].get("faststart"))):
        raise VerifyError(f"encoded file does not match: expected {want}, got {got}")
    return facts


def publish(partial: Path, out_path: Path, record: Publishable, retry: dict | None = None) -> str:
    """set_pending -> os.replace (retry) -> promote. Before the rename nothing is published; a failure of
    set_pending propagates and the rename is never attempted."""
    sha = sha256_file(partial)
    nbytes = Path(partial).stat().st_size
    record.set_pending(sha, nbytes)
    fault_point("after_set_pending")
    try:
        replace_with_retry(Path(partial), Path(out_path), retry)
    except OSError as e:
        try:
            _clear_pending(record)
        except Exception:
            pass
        raise PublishError(f"cannot rename the verified file to {Path(out_path).name}: {last_line(e)}")
    fault_point("after_rename")
    try:
        record.promote({"name": Path(out_path).name, "sha256": sha, "bytes": nbytes})
    except BaseException as e:
        raise PostPublishError(e, sha)
    return sha


def _clear_pending(record) -> None:
    rec = getattr(record, "rec", None)
    if isinstance(rec, dict):
        rec["pending_publish"] = None
        record._write()

"""Edit decision list on OpenTimelineIO 0.18.1 (docs/edit-route-design.md §2.2).

v1 shape: one video track `V1` (clips and gaps) + one optional audio track `A1` (one music clip). All times are integer
frames at the timeline rate, so cuts sit on the frame grid. Each clip names its asset in metadata["mvl"]["asset"] and
points at `assets/<file>` relative to the film folder.
"""
from pathlib import Path

import opentimelineio as otio

from assets import load, verify, media_kind


def new(name: str, fps: int) -> otio.schema.Timeline:
    tl = otio.schema.Timeline(name=name)
    tl.global_start_time = otio.opentime.RationalTime(0, fps)
    tl.metadata["mvl"] = {"fps": fps, "edl_version": 1}
    tl.tracks.append(otio.schema.Track(name="V1", kind=otio.schema.TrackKind.Video))
    tl.tracks.append(otio.schema.Track(name="A1", kind=otio.schema.TrackKind.Audio))
    return tl


def _rng(start, dur, fps):
    return otio.opentime.TimeRange(otio.opentime.RationalTime(start, fps), otio.opentime.RationalTime(dur, fps))


def _clip(film, asset_id, start, dur, fps, name=None):
    rec = load(film, asset_id)
    c = otio.schema.Clip(name=name or asset_id, source_range=_rng(start, dur, fps),
                         media_reference=otio.schema.ExternalReference(target_url=f"assets/{rec['file']}"))
    c.metadata["mvl"] = {"asset": asset_id}
    return c


def add_clip(tl, film, asset_id, start_frame, dur_frames, name=None):
    fps = tl.metadata["mvl"]["fps"]
    tl.tracks[0].append(_clip(film, asset_id, start_frame, dur_frames, fps, name))


def add_gap(tl, dur_frames):
    fps = tl.metadata["mvl"]["fps"]
    tl.tracks[0].append(otio.schema.Gap(source_range=_rng(0, dur_frames, fps)))


def set_music(tl, film, asset_id, start_frame, dur_frames):
    fps = tl.metadata["mvl"]["fps"]
    a = tl.tracks[1]
    while len(a):
        a.pop()
    a.append(_clip(film, asset_id, start_frame, dur_frames, fps))


def save(tl, path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    otio.adapters.write_to_file(tl, str(path))


def read(path):
    return otio.adapters.read_from_file(str(path))


def plan(tl, film) -> tuple[dict, list[str]]:
    """Flatten the EDL into render steps; problems (asset gate, rate, shape) are returned, never raised."""
    problems = []
    fps = (tl.metadata.get("mvl") or {}).get("fps")
    if not fps:
        return {}, ["timeline metadata mvl.fps missing"]
    vids = [t for t in tl.tracks if t.kind == otio.schema.TrackKind.Video]
    auds = [t for t in tl.tracks if t.kind == otio.schema.TrackKind.Audio]
    if len(vids) != 1 or len(auds) > 1:
        problems.append(f"v1 EDL takes 1 video and <= 1 audio track, got {len(vids)} and {len(auds)}")
    steps, seen = [], set()

    def frames(item, what):
        r = item.source_range
        if r is None:
            problems.append(f"{what}: no source_range")
            return 0, 0
        for x in (r.start_time, r.duration):
            if x.rate != fps or x.value != int(x.value):
                problems.append(f"{what}: time {x} not whole frames at {fps} fps")
        return int(r.start_time.value), int(r.duration.value)

    for i, item in enumerate(vids[0] if vids else []):
        if isinstance(item, otio.schema.Transition):
            problems.append(f"V1[{i}]: transitions are not in v1 (hard cuts only)")
            continue
        s, d = frames(item, f"V1[{i}]")
        if isinstance(item, otio.schema.Gap):
            steps.append({"kind": "gap", "dur_frames": d})
            continue
        aid = (item.metadata.get("mvl") or {}).get("asset")
        if not aid:
            problems.append(f"V1[{i}] {item.name}: no mvl.asset")
            continue
        seen.add(aid)
        steps.append({"kind": media_kind(load(film, aid)["file"]) if not verify(film, aid) else "?",
                      "asset": aid, "start_frame": s, "dur_frames": d})
    music = None
    if auds and len(auds[0]):
        if len(auds[0]) > 1:
            problems.append("A1: v1 takes one music clip")
        item = auds[0][0]
        aid = (item.metadata.get("mvl") or {}).get("asset")
        s, d = frames(item, "A1[0]")
        if aid:
            seen.add(aid)
            music = {"asset": aid, "start_frame": s, "dur_frames": d}
    for aid in sorted(seen):
        problems += verify(film, aid)
    total = sum(st["dur_frames"] for st in steps)
    if total <= 0:
        problems.append("V1 is empty")
    return {"fps": fps, "steps": steps, "music": music, "total_frames": total, "assets": sorted(seen)}, problems

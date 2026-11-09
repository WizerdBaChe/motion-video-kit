"""Render an EDL to MP4 with ffmpeg, then state facts with filmkit check (docs/edit-route-design.md §1).

The asset gate (edl.plan -> assets.verify) runs first; any problem refuses the render before ffmpeg starts. Output:
<out>.mp4, <out>.edit.json (EDL sha, asset hashes, ffmpeg command, check summary), filmkit's check.* beside it.
"""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import edl as E
from assets import asset_file, load

REPO = Path(__file__).resolve().parents[2]


class Refused(Exception):
    pass


def _probe_dur(p: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)],
                       capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def build_cmd(film, pl, out, size):
    film = Path(film)
    fps, W, H = pl["fps"], *size.split("x")
    args, fil, labels = [], [], []
    norm = (f"fps={fps},scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=black,"
            f"setsar=1,format=yuv420p")
    for i, st in enumerate(pl["steps"]):
        d = st["dur_frames"]
        if st["kind"] == "gap":
            args += ["-f", "lavfi", "-i", f"color=c=black:s={size}:r={fps}:d={d / fps + 1}"]
            fil.append(f"[{i}:v]{norm},trim=end_frame={d},setpts=PTS-STARTPTS[v{i}]")
        elif st["kind"] == "image":
            args += ["-loop", "1", "-framerate", str(fps), "-t", f"{d / fps + 1}", "-i", str(asset_file(film, st["asset"]))]
            fil.append(f"[{i}:v]{norm},trim=end_frame={d},setpts=PTS-STARTPTS[v{i}]")
        elif st["kind"] == "video":
            src = asset_file(film, st["asset"])
            s = st["start_frame"] / fps
            if _probe_dur(src) + 1e-3 < s + d / fps:
                raise Refused(f"{st['asset']}: source is {_probe_dur(src):.3f} s, EDL needs {s + d / fps:.3f} s")
            args += ["-i", str(src)]
            fil.append(f"[{i}:v]trim=start={s:.6f},setpts=PTS-STARTPTS,{norm},trim=end_frame={d},setpts=PTS-STARTPTS[v{i}]")
        else:
            raise Refused(f"step {i}: kind {st['kind']} cannot be a picture")
        labels.append(f"[v{i}]")
    fil.append("".join(labels) + f"concat=n={len(labels)}:v=1:a=0[v]")
    total_s = pl["total_frames"] / fps
    maps = ["-map", "[v]"]
    if pl["music"]:
        m = pl["music"]
        k = len(pl["steps"])
        args += ["-i", str(asset_file(film, m["asset"]))]
        fil.append(f"[{k}:a]atrim=start={m['start_frame'] / fps:.6f}:duration={m['dur_frames'] / fps:.6f},"
                   f"asetpts=PTS-STARTPTS,aformat=sample_rates=48000:channel_layouts=stereo,apad=whole_dur={total_s:.6f}[a]")
        maps += ["-map", "[a]", "-c:a", "aac", "-b:a", "192k"]
    return (["ffmpeg", "-v", "error", "-y"] + args + ["-filter_complex", ";".join(fil)] + maps +
            ["-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", "-r", str(fps), "-t", f"{total_s:.6f}",
             "-movflags", "+faststart", str(out)])


def render(film, edl_path, out, size="1280x720", profile="lab-round", check=True):
    film, out = Path(film), Path(out)
    tl = E.read(edl_path)
    pl, problems = E.plan(tl, film)
    if problems:
        raise Refused("; ".join(problems))
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = build_cmd(film, pl, out, size)
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(f"ffmpeg failed: {r.stderr[-800:]}")
    rec = {"edl": str(edl_path), "edl_sha256": hashlib.sha256(Path(edl_path).read_bytes()).hexdigest(),
           "film": str(film), "fps": pl["fps"], "size": size, "total_frames": pl["total_frames"],
           "duration_s": pl["total_frames"] / pl["fps"],
           "assets": [{"id": a, "sha256": load(film, a)["sha256"], "source": load(film, a)["source"]} for a in pl["assets"]],
           "ffmpeg": cmd, "check": None}
    if check:
        c = subprocess.run([sys.executable, "-X", "utf8", str(REPO / "tools/filmkit/check.py"), str(out),
                            "--duration", f"{rec['duration_s']:.6f}", "--size", size, "--fps", str(pl["fps"]),
                            "--audio-expected", "yes" if pl["music"] else "no", "--profile", profile, "--json"],
                           capture_output=True, text=True, encoding="utf-8")
        try:
            doc = json.loads(c.stdout)
            rows = doc.get("rows", [])
            rec["check"] = {"exit": c.returncode,
                            "blocking": [x.get("id") for x in rows if x.get("verdict") == "blocking" or x.get("bucket") == "blocking"],
                            "summary": doc.get("summary")}
        except ValueError:
            rec["check"] = {"exit": c.returncode, "error": (c.stderr or c.stdout)[-500:]}
    Path(str(out) + ".edit.json").write_text(json.dumps(rec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return rec

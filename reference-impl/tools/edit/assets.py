"""Asset register + provenance for the edit route (docs/edit-route-design.md §2.1).

Every asset is `<film>/assets/<id>.<ext>` with `<film>/assets/<id>.provenance.json` beside it. verify() is the gate
the renderer runs before any ffmpeg call: the file exists, its sha256 matches, and the source-specific keys are present.
"""
import datetime as dt
import hashlib
import json
import re
import shutil
from pathlib import Path

SCHEMA = 1
ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,39}$")
COMMON = ("schema", "id", "file", "sha256", "source", "created_at", "made_by")
# Keys that must be present per source; a value may be null where a provider does not expose it (seed, cost),
# except the ones in NONEMPTY.
BY_SOURCE = {
    "footage": ("origin", "license"),
    "generated": ("provider", "model", "prompt", "seed", "params", "cost", "job_id", "adapter", "adapter_version",
                  "inputs"),
    "motion": ("page", "render_record_sha256"),
}
NONEMPTY = {"generated": ("provider", "model", "prompt", "adapter"), "footage": ("origin",), "motion": ("page",)}
MEDIA = {".mp4": "video", ".mov": "video", ".webm": "video", ".mkv": "video", ".png": "image", ".jpg": "image",
         ".jpeg": "image", ".webp": "image", ".wav": "audio", ".mp3": "audio", ".m4a": "audio", ".flac": "audio"}


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def prov_path(film: Path, asset_id: str) -> Path:
    return Path(film) / "assets" / f"{asset_id}.provenance.json"


def media_kind(path) -> str | None:
    return MEDIA.get(Path(path).suffix.lower())


def register(film, src, asset_id, source, fields, made_by="tools/edit", move=False):
    """Copy (or move) `src` into the film's assets/ and write its provenance. Never overwrites an existing id."""
    film, src = Path(film), Path(src)
    if not ID_RE.match(asset_id):
        raise ValueError(f"bad asset id {asset_id!r}")
    if source not in BY_SOURCE:
        raise ValueError(f"source must be one of {sorted(BY_SOURCE)}")
    if media_kind(src) is None:
        raise ValueError(f"unsupported media type {src.suffix}")
    dst = film / "assets" / f"{asset_id}{src.suffix.lower()}"
    pp = prov_path(film, asset_id)
    if dst.exists() or pp.exists():
        raise FileExistsError(f"asset {asset_id} already registered")
    dst.parent.mkdir(parents=True, exist_ok=True)
    (shutil.move if move else shutil.copyfile)(str(src), str(dst))
    rec = {"schema": SCHEMA, "id": asset_id, "file": dst.name, "sha256": sha256(dst), "source": source,
           "created_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"), "made_by": made_by}
    rec.update(fields)
    problems = check_record(rec)
    if problems:
        dst.unlink()
        raise ValueError(f"provenance for {asset_id} incomplete: {problems}")
    pp.write_text(json.dumps(rec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return rec


def check_record(rec: dict) -> list[str]:
    out = [f"missing {k}" for k in COMMON if k not in rec]
    src = rec.get("source")
    if src not in BY_SOURCE:
        return out + [f"source {src!r} unknown"]
    out += [f"missing {k}" for k in BY_SOURCE[src] if k not in rec]
    out += [f"empty {k}" for k in NONEMPTY.get(src, ()) if k in rec and not rec[k]]
    if src == "generated" and not isinstance(rec.get("inputs", []), list):
        out.append("inputs must be a list")
    return out


def verify(film, asset_id) -> list[str]:
    """Problems with one asset; [] means usable."""
    film = Path(film)
    pp = prov_path(film, asset_id)
    if not pp.exists():
        return [f"{asset_id}: no provenance file {pp.name}"]
    try:
        rec = json.loads(pp.read_text(encoding="utf-8"))
    except ValueError as e:
        return [f"{asset_id}: provenance unreadable ({e})"]
    out = [f"{asset_id}: {p}" for p in check_record(rec)]
    f = film / "assets" / str(rec.get("file", ""))
    if not f.is_file():
        out.append(f"{asset_id}: file {rec.get('file')} missing")
    elif sha256(f) != rec.get("sha256"):
        out.append(f"{asset_id}: sha256 differs from provenance (file changed after registration)")
    for inp in rec.get("inputs") or []:
        ip = film / "assets" / str(inp.get("file", ""))
        if ip.is_file() and inp.get("sha256") and sha256(ip) != inp["sha256"]:
            out.append(f"{asset_id}: input {inp.get('id')} changed since generation")
    return out


def load(film, asset_id) -> dict:
    return json.loads(prov_path(film, asset_id).read_text(encoding="utf-8"))


def asset_file(film, asset_id) -> Path:
    return Path(film) / "assets" / load(film, asset_id)["file"]

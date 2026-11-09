"""Normalized hashing, folder hash, library and runtime hash (PSM 4.12, TL-INV-1, TG-8)."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .common import SpecInvalid, posix

TEXT_EXT = {".json", ".js", ".html", ".css", ".svg", ".md", ".txt", ".srt", ".csv", ".tmpl"}
SKIP_DIRS = {"__pycache__"}
SKIP_SUFFIXES = {".pyc"}
LIB_DIR = Path(__file__).resolve().parent.parent

# Runtime hash subset (TL-INV-12): everything that changes what compile would produce.
RUNTIME_PREFIXES = ("_tl/", "runtime/")
RUNTIME_FILES = ("tl.py", "film.timeline.schema.json")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_json(obj) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def json_nsha(obj) -> str:
    return _sha(canonical_json(obj).encode("utf-8"))


def normalize_text(raw: bytes, path: Path) -> str:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise SpecInvalid(f"not UTF-8 text: {posix(path)}", hint="save the file as UTF-8 (TG-8)")
    if text.startswith("﻿"):
        text = text[1:]
    return text.replace("\r\n", "\n").replace("\r", "\n")


def bytes_nsha(raw: bytes, path: Path) -> str:
    path = Path(path)
    ext = path.suffix.lower()
    if ext not in TEXT_EXT:
        return _sha(raw)
    text = normalize_text(raw, path)
    if ext == ".json":
        try:
            obj = json.loads(text)
        except json.JSONDecodeError as e:
            raise SpecInvalid(f"not valid JSON: {posix(path)} line {e.lineno}: {e.msg}", hint=f"fix {posix(path)}")
        text = canonical_json(obj)
    return _sha(text.encode("utf-8"))


def file_nsha(path: Path) -> str:
    path = Path(path)
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        raise SpecInvalid(f"missing file: {posix(path)}", hint=f"restore {posix(path)}")
    return bytes_nsha(raw, path)


def case_collisions(rels) -> list[tuple[str, str]]:
    seen: dict[str, str] = {}
    out = []
    for r in rels:
        k = r.casefold()
        if k in seen and seen[k] != r:
            out.append((seen[k], r))
        else:
            seen[k] = r
    return out


def check_case(rels, where: str) -> None:
    """Two paths in one hashed set equal case-insensitively -> spec_invalid (TG-8 path case)."""
    hits = case_collisions(rels)
    if hits:
        a, b = hits[0]
        raise SpecInvalid(f"paths differ only by case in {where}: {a} / {b}",
                          hint="rename one of them; NTFS treats them as the same file (TG-8)")


def lines_nsha(entries: list[tuple[str, str]], where: str = "set") -> str:
    """sha256 over 'relpath\\0nsha\\n' lines sorted by UTF-8 bytes (filmkit inputs_sha256 line format)."""
    check_case([r for r, _ in entries], where)
    lines = sorted(f"{r}\0{h}\n".encode("utf-8") for r, h in entries)
    return _sha(b"".join(lines))


def folder_files(folder: Path, pattern: str = "**/*") -> list[Path]:
    folder = Path(folder)
    out = []
    for p in sorted(folder.glob(pattern)):
        if not p.is_file():
            continue
        rel = p.relative_to(folder)
        if any(part in SKIP_DIRS for part in rel.parts) or p.suffix in SKIP_SUFFIXES:
            continue
        out.append(p)
    return out


def folder_nsha(folder: Path, pattern: str = "**/*") -> str:
    folder = Path(folder)
    entries = [(p.relative_to(folder).as_posix(), file_nsha(p)) for p in folder_files(folder, pattern)]
    return lines_nsha(entries, posix(folder))


# ---------------------------------------------------------------- MANIFEST.txt, library and runtime hash
def read_manifest(lib_dir: Path = LIB_DIR) -> list[str]:
    text = (Path(lib_dir) / "MANIFEST.txt").read_bytes().decode("utf-8")
    return [line for line in text.split("\n") if line]


def _kit_hash(lib_dir: Path, rels: list[str]) -> str:
    """filmkit's kit-hash algorithm (tools/filmkit/_fk/manifest.py kit_hash) over the given listed files."""
    h = hashlib.sha256()
    for rel in rels:
        h.update(rel.encode("utf-8") + b"\0" + (Path(lib_dir) / rel).read_bytes() + b"\n")
    return h.hexdigest()


def is_runtime(rel: str) -> bool:
    return rel in RUNTIME_FILES or rel.startswith(RUNTIME_PREFIXES)


def library_hash(lib_dir: Path = LIB_DIR) -> str:
    return _kit_hash(lib_dir, read_manifest(lib_dir))


def runtime_hash(lib_dir: Path = LIB_DIR) -> str:
    return _kit_hash(lib_dir, [r for r in read_manifest(lib_dir) if is_runtime(r)])


def manifest_problems(lib_dir: Path = LIB_DIR) -> list[str]:
    """Unlisted files, missing files, unsorted or malformed lines. Empty list = complete (PSM 3.1)."""
    lib_dir = Path(lib_dir)
    problems = []
    raw = (lib_dir / "MANIFEST.txt").read_bytes()
    if b"\r" in raw:
        problems.append("MANIFEST.txt has CR characters")
    lines = raw.decode("utf-8").split("\n")
    if lines and lines[-1] == "":
        lines = lines[:-1]
    if any(not ln for ln in lines):
        problems.append("MANIFEST.txt has blank lines")
    listed = [ln for ln in lines if ln]
    if listed != sorted(listed):
        problems.append("MANIFEST.txt is not sorted")
    if "MANIFEST.txt" not in listed:
        problems.append("MANIFEST.txt does not list itself")
    for rel in listed:
        if not (lib_dir / rel).is_file():
            problems.append(f"listed but missing: {rel}")
    for p in sorted(lib_dir.rglob("*")):
        if not p.is_file():
            continue
        relp = p.relative_to(lib_dir)
        if any(part in SKIP_DIRS for part in relp.parts) or p.suffix in SKIP_SUFFIXES:
            continue
        if p.name == ".tl.lock":  # the index lock (PSM 5.5) is a lock artefact, like __pycache__
            continue
        if relp.as_posix() not in listed:
            problems.append(f"unlisted file: {relp.as_posix()}")
    return problems

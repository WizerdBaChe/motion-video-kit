"""Kit hash over MANIFEST.txt (PSM 4.7, FK-INV-15)."""
from __future__ import annotations

import hashlib
from pathlib import Path

KIT_DIR = Path(__file__).resolve().parent.parent
IGNORED_DIRS = {"__pycache__"}
IGNORED_SUFFIXES = {".pyc"}


def read_manifest(kit_dir: Path = KIT_DIR) -> list[str]:
    text = (kit_dir / "MANIFEST.txt").read_bytes().decode("utf-8")
    return [line for line in text.split("\n") if line]


def kit_hash(kit_dir: Path = KIT_DIR) -> str:
    h = hashlib.sha256()
    for rel in read_manifest(kit_dir):
        h.update(rel.encode("utf-8") + b"\0" + (kit_dir / rel).read_bytes() + b"\n")
    return h.hexdigest()


def manifest_problems(kit_dir: Path = KIT_DIR) -> list[str]:
    """Unlisted files, missing files, unsorted or malformed lines. Empty list = complete."""
    problems = []
    raw = (kit_dir / "MANIFEST.txt").read_bytes()
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
        if not (kit_dir / rel).is_file():
            problems.append(f"listed but missing: {rel}")
    for p in sorted(kit_dir.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(kit_dir).as_posix()
        if any(part in IGNORED_DIRS for part in p.relative_to(kit_dir).parts) or p.suffix in IGNORED_SUFFIXES:
            continue
        if rel not in listed:
            problems.append(f"unlisted file: {rel}")
    return problems

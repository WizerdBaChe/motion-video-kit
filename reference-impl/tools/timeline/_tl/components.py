"""component.json validation, library index build/load, evidence.json merge (PSM 4.9; design 6.5)."""
from __future__ import annotations

import re
from pathlib import Path

from .common import SpecInvalid, dumps, posix, read_json, write_text_atomic
from .model import ENERGY, FAMILIES, ROLES, RHYTHM, is_int, is_num, nonempty_str
from .nhash import check_case, file_nsha, folder_nsha

COMP_ID_RE = re.compile(r"^([a-z0-9-]+)\.([a-z0-9-]+)$")
REF_RE = re.compile(r"^([a-z0-9-]+)\.([a-z0-9-]+)@([0-9]+)$")
CARD_RE = re.compile(r"^T[0-9]{2}$")
TIERS = ("unverified", "user-viewed", "measured", "verified")
TIER_RANK = {"unverified": 0, "user-viewed": 1, "measured": 1, "verified": 2}
STATES = ("draft", "candidate", "in-use", "verified")
SELECTABLE = ("candidate", "in-use", "verified")
PARAM_TYPES = ("number", "integer", "string", "boolean", "asset", "line", "color")
COMP_KEYS = {"schema_version", "id", "version", "family", "card", "card_tier", "tone", "when", "conflicts", "params",
             "emits", "intents", "label_type", "hold_range", "stock", "requires", "license", "provenance", "impl"}
PARAM_KEYS = {"type", "default", "min", "max", "enum", "evidence", "source"}
WHEN_ROLES = ROLES + ("overlay", "transition")
LIB_COMPONENTS = Path(__file__).resolve().parent.parent / "components"


def ref_of(cid: str, version: int) -> str:
    return f"{cid}@{version}"


def split_ref(ref: str):
    m = REF_RE.match(ref or "")
    if not m:
        return None
    return m.group(1), m.group(2), int(m.group(3))


def _any_or_list(v, allowed) -> bool:
    return v == "any" or (isinstance(v, list) and all(x in allowed for x in v))


def validate_component(obj, rel_folder: str) -> list[str]:
    """Problems with one component.json; empty list = valid. `rel_folder` = '<family>/<name>.v<version>'."""
    p: list[str] = []
    if not isinstance(obj, dict):
        return [f"{rel_folder}: component.json is not an object"]
    extra = sorted(set(obj) - COMP_KEYS)
    if extra:
        p.append(f"unknown key(s) {extra}")
    for k in ("schema_version", "id", "version", "family", "card", "card_tier", "tone", "when", "params",
              "label_type", "stock", "requires", "license", "provenance", "impl"):
        if k not in obj:
            p.append(f"missing {k}")
    if obj.get("schema_version") != 1:
        p.append("schema_version must be 1")
    m = COMP_ID_RE.match(obj.get("id") or "") if isinstance(obj.get("id"), str) else None
    if not m:
        p.append(f"id {obj.get('id')!r} is not <family>.<name>")
    if not (is_int(obj.get("version")) and obj["version"] >= 1):
        p.append("version must be an integer >= 1")
    fam = obj.get("family")
    if fam not in FAMILIES:
        p.append(f"family {fam!r} not in design 7.4")
    if m and m.group(1) != fam:
        p.append("id prefix differs from family")
    if m and is_int(obj.get("version")) and rel_folder != f"{fam}/{m.group(2)}.v{obj['version']}":
        p.append(f"folder {rel_folder} should be {fam}/{m.group(2)}.v{obj['version']}")
    card = obj.get("card")
    if card is not None and not (isinstance(card, str) and CARD_RE.match(card)):
        p.append("card must be Tnn or null")
    if obj.get("card_tier") not in TIERS:
        p.append(f"card_tier must be one of {TIERS}")
    tone = obj.get("tone")
    if not (isinstance(tone, dict) and set(tone) == {"energy", "film_types"} and _any_or_list(tone.get("energy"), ENERGY)
            and (tone.get("film_types") == "any" or isinstance(tone.get("film_types"), list))):
        p.append("tone must be {energy: [..]|any, film_types: [..]|any}")
    when = obj.get("when")
    if not (isinstance(when, dict) and set(when) == {"roles", "rhythm_sources"}
            and _any_or_list(when.get("roles"), WHEN_ROLES)
            and _any_or_list(when.get("rhythm_sources"), RHYTHM + ("music-bar",))):
        p.append("when must be {roles: [..]|any, rhythm_sources: [..]|any}")
    if not (isinstance(obj.get("conflicts", []), list) and all(isinstance(x, str) and COMP_ID_RE.match(x)
                                                               for x in obj.get("conflicts", []))):
        p.append("conflicts must list component ids")
    params = obj.get("params")
    if not isinstance(params, dict):
        p.append("params must be an object")
    else:
        for name, spec in params.items():
            if not isinstance(spec, dict):
                p.append(f"param {name} not an object")
                continue
            extra = sorted(set(spec) - PARAM_KEYS)
            if extra:
                p.append(f"param {name}: unknown key(s) {extra}")
            if spec.get("type") not in PARAM_TYPES:
                p.append(f"param {name}: type must be one of {PARAM_TYPES}")
            if spec.get("evidence") not in TIERS:
                p.append(f"param {name}: evidence tier required (BR-7)")
            if "source" in spec and not (spec["source"] == "clip_dur" and spec.get("type") == "number"):
                p.append(f"param {name}: source must be clip_dur on a number param")
            for b in ("min", "max"):
                if b in spec and not is_num(spec[b]):
                    p.append(f"param {name}: {b} must be a number")
            if "enum" in spec and not isinstance(spec["enum"], list):
                p.append(f"param {name}: enum must be a list")
    for k in ("emits", "intents"):
        if k in obj and not isinstance(obj[k], list):
            p.append(f"{k} must be a list")
    if not isinstance(obj.get("label_type"), bool):
        p.append("label_type must be a boolean")
    elif obj["label_type"]:
        hr = obj.get("hold_range")
        if not (isinstance(hr, list) and len(hr) == 2 and all(is_num(x) for x in hr) and 0 < hr[0] <= hr[1]):
            p.append("label_type true requires hold_range [a, b] with 0 < a <= b (D-T15)")
    if not isinstance(obj.get("stock"), bool):
        p.append("stock must be a boolean")
    if not (isinstance(obj.get("requires"), list) and all(isinstance(x, str) and REF_RE.match(x) for x in obj["requires"])):
        p.append("requires must list refs <id>@<version>")
    for k in ("license", "provenance", "impl"):
        if k in obj and not nonempty_str(obj[k]):
            p.append(f"{k} must be a non-empty string")
    return [f"{rel_folder}: {x}" for x in p]


def component_tier(ev: dict) -> str:
    if ev.get("state") == "verified":
        return "verified"
    w, m = bool(ev.get("watched")), bool(ev.get("measured"))
    if w and m:
        return "user-viewed+measured"
    if w:
        return "user-viewed"
    if m:
        return "measured"
    return "unverified"


def _rank(tier: str) -> int:
    return max(TIER_RANK.get(t, 0) for t in tier.split("+"))


def claim_tier(comp_tier: str, card: str | None, card_tier: str) -> str:
    """min(component tier, card_tier); card null -> the component's own tier (TL-INV-7, design 6.5)."""
    if card is None:
        return comp_tier
    return card_tier if TIER_RANK.get(card_tier, 0) < _rank(comp_tier) else comp_tier


class Index:
    def __init__(self, obj: dict, folder: Path, nsha: str | None):
        self.obj = obj
        self.folder = Path(folder)
        self.nsha = nsha
        self.entries = list(obj.get("components") or [])
        self.by_ref = {e["ref"]: e for e in self.entries}

    def same_family(self, family: str) -> list[str]:
        return sorted(e["ref"] for e in self.entries if e.get("family") == family)

    def get(self, ref: str):
        return self.by_ref.get(ref)

    def selectable(self, ref: str) -> bool:
        e = self.by_ref.get(ref)
        return bool(e) and e.get("state") in SELECTABLE

    def requires_closure(self, ref: str) -> tuple[list[str], list[str]]:
        """(closure refs in discovery order excluding ref itself, missing refs)."""
        seen, missing, order = {ref}, [], []
        stack = [ref]
        while stack:
            r = stack.pop(0)
            e = self.by_ref.get(r)
            if not e:
                continue
            for q in e.get("requires") or []:
                if q in seen:
                    continue
                seen.add(q)
                if q in self.by_ref:
                    order.append(q)
                    stack.append(q)
                else:
                    missing.append(q)
        return order, missing

    def path_of(self, ref: str) -> Path:
        return self.folder / self.by_ref[ref]["path"]


def _scan(components_dir: Path) -> list[tuple[str, Path]]:
    out = []
    for cj in sorted(Path(components_dir).glob("*/*/component.json")):
        out.append((cj.parent.relative_to(components_dir).as_posix(), cj))
    return out


def build_index(components_dir: Path) -> tuple[dict, str]:
    """Validate every component.json; return (index object, INDEX.md text). Raises SpecInvalid with all problems."""
    components_dir = Path(components_dir)
    problems: list[str] = []
    ev_path = components_dir / "evidence.json"
    evidence = read_json(ev_path) if ev_path.is_file() else {"schema_version": 1, "entries": {}}
    ev_entries = evidence.get("entries") if isinstance(evidence, dict) else None
    if not isinstance(ev_entries, dict):
        raise SpecInvalid(f"evidence.json malformed: {posix(ev_path)}", hint="entries must be an object keyed id@version")
    found = _scan(components_dir)
    check_case([rel for rel, _ in found], posix(components_dir))
    comps = []
    for rel, cj in found:
        obj = read_json(cj)
        pr = validate_component(obj, rel)
        if not pr and not (cj.parent / obj["impl"]).is_file():
            pr.append(f"{rel}: impl file {obj['impl']} missing")
        if pr:
            problems.extend(pr)
            continue
        ref = ref_of(obj["id"], obj["version"])
        ev = ev_entries.get(ref) or {}
        state = ev.get("state", "draft")
        if state not in STATES:
            problems.append(f"evidence.json {ref}: state {state!r}")
            continue
        ct = component_tier(ev)
        entry = dict(obj)
        entry.update({"ref": ref, "path": rel, "dir_nsha": folder_nsha(cj.parent), "state": state,
                      "watched": bool(ev.get("watched")), "measured": bool(ev.get("measured")),
                      "claim_tier": claim_tier(ct, obj.get("card"), obj.get("card_tier"))})
        comps.append(entry)
    refs = [c["ref"] for c in comps]
    for r in sorted(set(x for x in refs if refs.count(x) > 1)):
        problems.append(f"duplicate component {r}")
    if problems:
        raise SpecInvalid(f"{len(problems)} component problem(s): " + "; ".join(problems[:5]),
                          hint="fix component.json files, then run tl.py index", problems=problems)
    comps.sort(key=lambda c: c["ref"])
    index = {"schema_version": 1, "generator": "tl", "components": comps}
    return index, index_md(index)


def index_md(index: dict) -> str:
    lines = ["# 元件索引（GENERATED by `tl.py index`; never hand-edit）", "",
             "對外宣稱的等級＝min(元件等級, 技巧卡等級)（TL-INV-7）。狀態 draft 的元件不能被選用。", ""]
    comps = index.get("components") or []
    if not comps:
        lines.append("目前元件庫是空的（TL-1 起加入元件）。")
        return "\n".join(lines) + "\n"
    lines += ["| 元件 | 族 | 狀態 | 對外等級 | 技巧卡 | 基調 energy | 片型 | 時機 roles | 相依 | 出處 |",
              "|---|---|---|---|---|---|---|---|---|---|"]
    for c in comps:
        tone, when = c.get("tone") or {}, c.get("when") or {}
        fmt = lambda v: "any" if v == "any" else "、".join(v or [])
        lines.append(f"| `{c['ref']}` | {c['family']} | {c['state']} | {c['claim_tier']} | {c.get('card') or '—'} "
                     f"({c.get('card_tier')}) | {fmt(tone.get('energy'))} | {fmt(tone.get('film_types'))} | "
                     f"{fmt(when.get('roles'))} | {'、'.join(c.get('requires') or []) or '—'} | {c.get('provenance')} |")
    return "\n".join(lines) + "\n"


def write_index(components_dir: Path, index: dict, md: str) -> None:
    tmp = Path(components_dir) / ".tl"
    write_text_atomic(Path(components_dir) / "index.json", dumps(index), tmp)
    write_text_atomic(Path(components_dir) / "INDEX.md", md, tmp)
    try:
        tmp.rmdir()
    except OSError:
        pass


def index_is_current(components_dir: Path, index: dict, md: str) -> bool:
    d = Path(components_dir)
    try:
        return (d / "index.json").read_bytes().decode("utf-8").replace("\r\n", "\n") == dumps(index) \
            and (d / "INDEX.md").read_bytes().decode("utf-8").replace("\r\n", "\n") == md
    except FileNotFoundError:
        return False


def load_index(components_dir: Path) -> Index:
    d = Path(components_dir)
    p = d / "index.json"
    if not p.is_file():
        raise SpecInvalid(f"component index missing: {posix(p)}", hint=f"run tl.py index --components {posix(d)}")
    obj = read_json(p)
    if not isinstance(obj, dict) or not isinstance(obj.get("components"), list):
        raise SpecInvalid(f"component index malformed: {posix(p)}", hint="run tl.py index")
    return Index(obj, d, file_nsha(p))

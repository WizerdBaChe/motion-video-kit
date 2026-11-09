"""Read the shared rules file: film_types, end_hold range, params.timeline (PSM 4.10, 6.3; TL-INV-10)."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .common import SpecInvalid, posix, read_json
from .nhash import file_nsha

LIB_DIR = Path(__file__).resolve().parent.parent
DEFAULT_RULES = LIB_DIR.parent / "filmkit_rules.json"


@dataclass(frozen=True)
class Rules:
    path: Path | None
    sha: str | None
    film_types: list | None
    end_hold_range: tuple | None
    timeline: dict = field(default_factory=dict)

    @property
    def present(self) -> bool:
        return self.path is not None

    def absent_reason(self, key: str) -> str:
        return "rules file not present" if not self.present else f"rules key {key} absent"


def load_rules(path: Path | None) -> Rules:
    """Absent file -> Rules(None, None, None, None, {}). Present but unparsable -> spec_invalid."""
    p = Path(path) if path else DEFAULT_RULES
    if not p.is_file():
        return Rules(None, None, None, None, {})
    obj = read_json(p)
    if not isinstance(obj, dict):
        raise SpecInvalid(f"rules file is not a JSON object: {posix(p)}", hint="fix the rules file (INV-7)")
    ft = obj.get("film_types")
    film_types = list(ft) if isinstance(ft, list) else None
    end_hold = None
    for r in obj.get("rules") or []:
        if isinstance(r, dict) and r.get("id") == "end_hold":
            rs = r.get("range_s")
            if isinstance(rs, list) and len(rs) == 2 and all(isinstance(x, (int, float)) for x in rs):
                end_hold = (float(rs[0]), float(rs[1]))
    params = obj.get("params") if isinstance(obj.get("params"), dict) else {}
    tl = params.get("timeline") if isinstance(params.get("timeline"), dict) else {}
    return Rules(p, file_nsha(p), film_types, end_hold, dict(tl))

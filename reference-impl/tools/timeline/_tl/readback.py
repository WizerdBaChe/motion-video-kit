"""readback: what changed between two approved versions of a film, per clip and line (works contract W-5).

Diffs versions/<n>/timeline.json against versions/<m>/timeline.json track by track, matching entries by id; the
result is appended to <film>/作者修改紀錄.md as evidence for the main loop. It never becomes a rule by itself.
Minimal by design (shared-design-layer-design.md WC-2 step 4); TL-1 may extend it.
"""
from __future__ import annotations

import json
from pathlib import Path

from .common import NotCurrent, posix, read_json
from .state import now


def _short(v) -> str:
    s = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False, sort_keys=True)
    return s if len(s) <= 80 else s[:77] + "..."


def version_timeline(film: Path, n: int) -> dict:
    p = Path(film) / "versions" / str(n) / "timeline.json"
    if not p.is_file():
        raise NotCurrent(f"versions/{n}/timeline.json is missing", hint="see state.json versions; approve makes them")
    return read_json(p)


def diff(a: dict, b: dict) -> list[str]:
    out = []
    ta, tb = a.get("tracks") or {}, b.get("tracks") or {}
    for track in sorted(set(ta) | set(tb)):
        xa = {e.get("id"): e for e in ta.get(track) or [] if isinstance(e, dict)}
        xb = {e.get("id"): e for e in tb.get(track) or [] if isinstance(e, dict)}
        order_a = [i for i in xa if i in xb]
        order_b = [i for i in xb if i in xa]
        if order_a != order_b:
            out.append(f"- {track}：順序 {' '.join(map(str, order_a))} → {' '.join(map(str, order_b))}")
        for i in [i for i in xa if i not in xb]:
            out.append(f"- {track} {i}：刪除（{_short(xa[i].get('what') or xa[i].get('text') or '')}）")
        for i in [i for i in xb if i not in xa]:
            out.append(f"- {track} {i}：新增（{_short(xb[i].get('what') or xb[i].get('text') or '')}）")
        for i in order_b:
            ea, eb = xa[i], xb[i]
            for k in sorted(set(ea) | set(eb)):
                if ea.get(k) != eb.get(k):
                    out.append(f"- {track} {i}.{k}：{_short(ea.get(k))} → {_short(eb.get(k))}")
    for k in sorted((set(a) | set(b)) - {"tracks"}):
        if a.get(k) != b.get(k):
            out.append(f"- {k}：{_short(a.get(k))} → {_short(b.get(k))}")
    return out


def record(film: Path, n: int, m: int) -> tuple[str, int]:
    rows = diff(version_timeline(film, n), version_timeline(film, m))
    text = (f"## 第 {n} 版 → 第 {m} 版（{now()[:10]}，tl.py readback 草稿）\n\n"
            f"- 比對：`versions/{n}/timeline.json` 與 `versions/{m}/timeline.json`（{posix(film)}）\n\n"
            "### 逐段差異\n\n" + ("\n".join(rows) if rows else "- 時間軸沒有差異") + "\n\n"
            "### 整理出的規則（主迴圈手寫；只是紀錄，不自動變規則）\n\n- TODO\n")
    return text, len(rows)

"""pagescan: per-frame page scan for build errors (convergence design §2; rows QF-1..QF-8).

usage: python -X utf8 pagescan.py <page.html> --duration S --size WxH [--fps N] [--plan film_plan.json]
                                  [--t0 S] [--t1 S] [--stride K] [--font-stride K] [--out-prefix P] [--json]
                                  [--timeline FILM_DIR]

Reads the page (never the MP4). Every row is a look or an information row: it reports what it read,
never whether the picture is good (INV-6). Exit 0 read, 3 a row is undetermined, 1 nothing read.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _fk import pagescan as ps  # noqa: E402
from _fk.spec import load_plan  # noqa: E402

LIMITS = [
    "畫面好壞未判斷：每一列只說量到什麼。",
    "畫在 canvas／WebGL 裡的字沒有頁面節點，量不到；canvas 佔畫面一半以上時，文字相關各列回「無法判定」。",
    "QF-1c 只看頁面數字（縮放速率每秒 0.2%–15% 持續至少 1 秒）；QF-1 只在這些段落裡量像素，門檻 0.25 px 由一個頁面（r33 B2 慢推對關掉慢推）定出，屬暫定。",
    "QF-2 需要逐格讀（stride 1）；宣告在 film_plan.json `cuts` 的硬切不列。",
    "QF-3 每隔 font-stride 格讀一次；只看渲染最多字的那個字型。",
    "QF-6 量元素的縮放與透明度來回；宣告在 `pulses` 的內容型脈動（T12）不列。整頁濾鏡或 canvas 畫出的脈動量不到。",
    "QF-7／QF-8 只在給了 --timeline 導演表資料夾時出現。QF-7 比對狀態表裡字串與數字的事實是否出現在該鏡頭時段的頁面文字（不分大小寫與空白，子字串比對：事實 5 也會在「15」裡找到），不看是非值，也不看圖片裡的字。",
    "QF-8 只認帶 data-asset 的元素；可見＝透明度 0.5 以上且有一部分在畫面內；秒數以讀到的格數乘 stride 計。",
]


def md_report(page: Path, res: dict) -> str:
    rows = res["rows"]
    out = [f"# pagescan：{page.name}", "", f"- 讀了 {res['frames_read']} 格；canvas 佔畫面中位數 {res['canvas_share_median']:.0%}", ""]
    names = {"QF-1": "文字逐格抖動", "QF-1c": "文字上的慢速縮放（成因）", "QF-2": "文字一格內出現",
             "QF-3": "字型被替換", "QF-6": "反覆脈動", "QF-7": "狀態表文字", "QF-8": "指定素材"}
    for key, row in rows.items():
        head = f"## {key} {names.get(key, row['name'])}"
        if "undetermined" in row:
            out += [head, "", f"- 無法判定：{row['undetermined']}", ""]
            continue
        listed = row.get("listed", [])
        out += [head, "", f"- 需要看：{len(listed)} 筆" + (f"；宣告過的 {len(row['declared'])} 筆" if row.get("declared") else "")]
        for it in listed[:12]:
            out.append("  - " + json.dumps(it, ensure_ascii=False))
        out.append("")
    out += ["## 限制", ""] + [f"- {x}" for x in LIMITS]
    return "\n".join(out) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("page")
    ap.add_argument("--duration", type=float, required=True)
    ap.add_argument("--size", required=True)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--plan")
    ap.add_argument("--t0", type=float, default=0.0)
    ap.add_argument("--t1", type=float)
    ap.add_argument("--stride", type=int, default=1)
    ap.add_argument("--font-stride", type=int, default=15)
    ap.add_argument("--out-prefix")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--from-raw", help="re-analyse a <prefix>.pagescan.raw.json instead of reading the page")
    ap.add_argument("--timeline", help="film folder: film.timeline.json (+ build/timeline.resolved.json) for QF-7/QF-8")
    a = ap.parse_args(argv)
    tl = None
    if a.timeline:
        fd = Path(a.timeline)
        try:
            tobj = json.loads((fd / "film.timeline.json").read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            print(f"pagescan: timeline not read: {e}", file=sys.stderr)
            return 1
        rp = fd / "build" / "timeline.resolved.json"
        resolved = json.loads(rp.read_text(encoding="utf-8")) if rp.is_file() else None
        tl = ps.timeline_inputs(tobj, resolved)
    page = Path(a.page).resolve()
    w, h = (int(v) for v in a.size.lower().split("x"))
    plan = None
    if a.plan:
        plan, err = load_plan(Path(a.plan), a.fps)
        if err:
            print(f"pagescan: plan refused: {err}", file=sys.stderr)
            return 1
    prefix = Path(a.out_prefix) if a.out_prefix else page.with_name(page.stem)
    if a.from_raw:
        raw = json.loads(Path(a.from_raw).read_text(encoding="utf-8"))
        frames, fonts = raw["frames"], raw["fonts"]
    else:
        try:
            frames, fonts = ps.read_page(page, a.duration, (w, h), a.fps, a.stride, a.font_stride, a.t0, a.t1)
        except Exception as e:  # the kit's typed errors carry a readable message
            print(f"pagescan: page not read: {type(e).__name__}: {e}", file=sys.stderr)
            return 1
        Path(f"{prefix}.pagescan.raw.json").write_text(json.dumps({"frames": frames, "fonts": fonts}), encoding="utf-8")
    res = ps.analyse(frames, fonts, a.fps, plan, tl)
    res.update({"page": page.as_posix(), "size": f"{w}x{h}", "fps": a.fps, "stride": a.stride,
                "window": [a.t0, a.t1 if a.t1 is not None else a.duration],
                "plan": None if not a.plan else Path(a.plan).resolve().as_posix(),
                "timeline": None if not a.timeline else Path(a.timeline).resolve().as_posix(), "limits": LIMITS})
    Path(f"{prefix}.pagescan.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    Path(f"{prefix}.pagescan.md").write_text(md_report(page, res), encoding="utf-8")
    undetermined = any("undetermined" in r for r in res["rows"].values())
    if a.json:
        print(json.dumps(res, ensure_ascii=False))
    else:
        counts = {k: (len(r["listed"]) if "listed" in r else "undetermined") for k, r in res["rows"].items()}
        print(f"pagescan {page.name}: frames={res['frames_read']} " + " ".join(f"{k}={v}" for k, v in counts.items()))
        print(f"written: {prefix}.pagescan.json, {prefix}.pagescan.md")
    return 3 if undetermined else 0


if __name__ == "__main__":
    sys.exit(main())

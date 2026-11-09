"""Regenerate the two README images of the core (the director sheet and the storyboard) from the SHIPPED example.

Usage:  python -X utf8 docs/assets/build_core.py [--out docs/assets]
Needs:  Python 3.12, `pip install playwright pillow` and `playwright install chromium`.

  core-director-sheet.png  the read-only timeline page that the shipped `tools/timeline/tl.py view` writes for the
                           example film (`reference-impl/films/fanout-pool-explainer/film.timeline.json`): the
                           film-wide decisions with who ruled each (you / model) and the per-clip time bands.
                           The page is the tool's own output, cropped, not redrawn.
  core-storyboard.png      one card per clip, built from the same JSON: role, seconds, headline, what the clip
                           shows, the motion-intent lines and the key frames (timeline `keys[]`), each key frame a
                           still rendered from the shipped example page with `window.__setTime(t)`.

The example is copied to a scratch folder first: tl.py writes build/ next to the film and the page is rendered
from a copy, so the shipped folders stay byte-identical to the origin.
"""
from __future__ import annotations

import argparse
import html
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
KIT = HERE.parents[1] / "reference-impl"
EX = KIT / "films" / "fanout-pool-explainer"
TL = KIT / "tools" / "timeline" / "tl.py"
W, H = 1080, 1350  # the film's own size (4:5)
# The README image names no third-party product: clip S1's source stamp (it names a vendor's tool) is on screen
# from 1.5 s after its start, so S1 shows its breakdown key at 1.0 s (before the stamp) and drops its second key.
SKIP_KEYS = {"KS1-zero"}
REL_TIME = {"KS1-burst": 1.0}

CSS = """
:root{--bg:#f6f3ec;--card:#fffdf8;--ink:#1d1b17;--mute:#6f685c;--line:#d9d2c3;--acc:#0f7a5c;--hot:#c4421a}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 "Noto Sans TC","Microsoft JhengHei",sans-serif}
.wrap{width:1560px;padding:28px 32px 32px}
h1{font-size:26px;margin:0 0 4px}.sub{color:var(--mute);margin:0 0 20px}
.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:18px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px}
.hd{display:flex;justify-content:space-between;align-items:baseline;border-bottom:1px solid var(--line);padding-bottom:6px;margin-bottom:10px}
.id{font-weight:700;font-size:20px}.role{color:var(--acc);font-weight:600}.sec{color:var(--mute);font-variant-numeric:tabular-nums}
.stills{display:flex;gap:10px;margin-bottom:10px}.still{flex:1;min-width:0}
.still img{width:100%;display:block;border:1px solid var(--line);border-radius:4px}
.cap{font-size:12px;color:var(--mute);margin-top:2px}.cap b{color:var(--ink)}
.head{font-weight:700;font-size:17px;margin:2px 0 6px}
.what{font-size:13px;color:var(--mute);margin:0 0 8px;display:-webkit-box;-webkit-line-clamp:4;-webkit-box-orient:vertical;overflow:hidden}
ul{margin:0;padding-left:18px;font-size:13px}li{margin:2px 0}
.tag{display:inline-block;font-size:11px;border:1px solid var(--line);border-radius:10px;padding:0 7px;margin-right:4px;color:var(--mute)}
"""


def run(cmd: list[str]) -> str:
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if p.returncode != 0:
        sys.exit(f"STOP: {' '.join(cmd[:4])} -> exit {p.returncode}: {(p.stdout + p.stderr)[-500:]}")
    return p.stdout


def director_sheet(work: Path, out: Path, pw) -> None:
    film = work / "fanout-pool-explainer"  # tl.py requires the folder name to equal meta.film_id (TV-1)
    shutil.copytree(EX, film, ignore=shutil.ignore_patterns("page"))
    for args in (["validate", "--static"], ["resolve"], ["validate", "--timed"], ["view"]):
        run([sys.executable, "-X", "utf8", str(TL), *args, str(film)])
    b = pw.chromium.launch()
    pg = b.new_page(viewport={"width": 1400, "height": 900}, device_scale_factor=1)
    pg.goto((film / "build" / "timeline.html").as_uri())
    pg.wait_for_timeout(400)
    a = work / "_a.png"
    c = work / "_c.png"
    pg.locator(".lanes").first.screenshot(path=str(a))
    pg.locator(".cards").first.screenshot(path=str(c))
    # the cards grid: keep the first row only (the film-wide decisions), cut where the second row starts
    cut = pg.evaluate("""() => {const cs=[...document.querySelectorAll('.cards .card')];
        const top0=cs[0].getBoundingClientRect().top; const r2=cs.find(x=>x.getBoundingClientRect().top>top0+5);
        return r2 ? r2.getBoundingClientRect().top - document.querySelector('.cards').getBoundingClientRect().top - 6 : 0}""")
    b.close()
    from PIL import Image
    ia, ic = Image.open(a).convert("RGB"), Image.open(c).convert("RGB")
    ic = ic.crop((0, 0, ic.width, int(cut) or ic.height))
    pad = 24
    canvas = Image.new("RGB", (max(ia.width, ic.width) + 2 * pad, ia.height + ic.height + 3 * pad), (246, 243, 236))
    canvas.paste(ia, (pad, pad))
    canvas.paste(ic, (pad, ia.height + 2 * pad))
    canvas.save(out / "core-director-sheet.png", optimize=True)


def storyboard(work: Path, out: Path, pw) -> None:
    d = json.loads((EX / "film.timeline.json").read_text(encoding="utf-8"))
    clips = d["tracks"]["picture"]
    page = work / "page"
    shutil.copytree(EX / "page", page)
    b = pw.chromium.launch()
    pg = b.new_page(viewport={"width": W, "height": H})
    pg.goto((page / "index.html").as_uri())
    pg.wait_for_timeout(600)
    start, rows, still_dir = 0.0, [], work / "stills"
    still_dir.mkdir()
    for c in clips:
        keys = [k for k in c.get("keys", []) if k["id"] not in SKIP_KEYS]  # SKIP_KEYS: a frame with a third-party product name
        pick = keys if len(keys) <= 2 else [keys[0], keys[-1]]
        imgs = []
        for k in pick:
            t = round(start + REL_TIME.get(k["id"], k["at"]), 2)
            pg.evaluate("t => window.__setTime(t)", t)
            pg.wait_for_timeout(120)
            p = still_dir / f"{k['id']}.jpg"
            pg.screenshot(path=str(p), type="jpeg", quality=82)
            imgs.append((k, t, p))
        rows.append((c, start, imgs))
        start += c["dur"]
    b.close()
    cards = []
    for c, s, imgs in rows:
        st = "".join(
            f'<div class="still"><img src="{p.as_uri()}"><div class="cap"><b>{html.escape(k["id"])}</b> {t:.1f} s '
            f'· {html.escape(k["role"])}{" · hold " + str(k["hold"]) + " s" if k.get("hold") else ""}</div></div>'
            for k, t, p in imgs)
        mi = "".join(f"<li>{html.escape(x)}</li>" for x in c["motion_intent"][:3])
        cards.append(
            f'<div class="card"><div class="hd"><span><span class="id">{html.escape(c["id"])}</span> '
            f'<span class="role">{html.escape(c["role"])}</span></span><span class="sec">{s:.1f}–{s + c["dur"]:.1f} s</span></div>'
            f'<div class="stills">{st}</div><div class="head">{html.escape(c["headline"])}</div>'
            f'<p class="what">{html.escape(c["what"])}</p>'
            f'<div><span class="tag">freedom: {html.escape(c["freedom"])}</span>'
            f'<span class="tag">camera goal: {html.escape(c["camera"]["goal"])}</span></div>'
            f'<ul>{mi}</ul></div>')
    dec = d["decisions"]
    sub = (f'film_type {dec["film_type"]["value"]} · energy {dec["energy"]["value"]} · rhythm_source '
           f'{dec["rhythm_source"]["value"]} · {d["meta"]["format"]["size"]} @ {d["meta"]["format"]["fps"]} fps · '
           f'{start:.1f} s · {len(clips)} clips')
    doc = (f'<!doctype html><meta charset="utf-8"><style>{CSS}</style><div class="wrap"><h1>分鏡 storyboard · '
           f'{html.escape(d["meta"]["film_id"])}</h1><p class="sub">{html.escape(sub)}</p><div class="grid">'
           + "".join(cards) + "</div></div>")
    f = work / "storyboard.html"
    f.write_text(doc, encoding="utf-8")
    b = pw.chromium.launch()
    pg = b.new_page(viewport={"width": 1560, "height": 900})
    pg.goto(f.as_uri())
    pg.wait_for_timeout(500)
    pg.screenshot(path=str(out / "core-storyboard.png"), full_page=True)
    b.close()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=HERE)
    a = ap.parse_args()
    from playwright.sync_api import sync_playwright
    with tempfile.TemporaryDirectory() as td, sync_playwright() as pw:
        work = Path(td)
        (work / "d").mkdir()
        (work / "s").mkdir()
        director_sheet(work / "d", a.out, pw)
        storyboard(work / "s", a.out, pw)
    for n in ("core-director-sheet.png", "core-storyboard.png"):
        print(n, (a.out / n).stat().st_size, "bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())

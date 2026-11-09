"""DOM reads of a time-driven page (window.__setTime): staggered entrances per section (T14) and where
each lyric line sits (T16). Reads the arm's page, not the video, so it only sees what the DOM holds:
anything painted inside a <canvas> is one element to it.

    python -X utf8 tools/domlayers.py <index.html> --out f.json --duration S [--size 1280x720]
        [--sections 0,4,8,...] [--pre 0.5] [--win 2.4] [--lyrics lyrics.json] [--fps 15]
    python -X utf8 tools/domlayers.py --selftest

Stagger (T14). Every DOM element that paints something (img, svg root, canvas, video, an element with its own
text, or a box with a background of >= 100 px2) is sampled at --fps; it is visible when its effective opacity
(product over ancestors; display none / visibility hidden = 0) is >= 0.5 and >= 16 px2 of it is inside the
viewport. An ENTRANCE is invisible -> visible inside [start - pre, start + win). Entrance times closer than
0.15 s merge into one LAYER (a letter-by-letter reveal is one layer). Per section: entrances, layers, onsets.
`canvas_share` = largest visible canvas / frame; a section with canvas_share >= 0.5 is `undetermined`.

Lyrics (T16). At each line's mid time, the element that holds the line's text (whitespace and punctuation
ignored; the deepest holder with the largest visible glyph area) gives a glyph bounding box from its text
nodes' client rects (glyphs whose effective opacity >= 0.3). Class `subtitle` = horizontal, centred (centre x
within 0.5 +- 0.08 W), centre y >= 0.7 H, height <= 0.15 H; `other` = visible elsewhere, left/right aligned,
large or vertical; `not-found`. Calibration history: the first rule (centre x 0.3-0.7) read r21 A1r's
left-aligned bottom log lines as subtitles; tightened to 'centred' after reading that page (2026-10-11), so r21
A1r is not an independent check of the rule.

Limits: clip-path / overflow masks are not modelled (a masked-out element still reads visible); an element
re-created with a different tag path reads as a new entrance; canvas content is invisible; letter spans
re-created per frame read as the same key only if their path and text are stable.
"""
import argparse
import json
import re
import sys
import tempfile
from pathlib import Path

COLLECT = r"""() => {
  const W = innerWidth, H = innerHeight, out = [];
  function op(el) { let o = 1; for (let e = el; e && e.nodeType === 1; e = e.parentElement) {
      const cs = getComputedStyle(e); if (cs.display === 'none' || cs.visibility === 'hidden') return 0;
      o *= parseFloat(cs.opacity); if (o < 0.01) return 0; } return o; }
  function path(el) { const p = []; for (let e = el; e && e !== document.body; e = e.parentElement) {
      let i = 0; for (let s = e; (s = s.previousElementSibling);) i++; p.push(e.tagName + i); } return p.reverse().join('/'); }
  for (const el of document.body.querySelectorAll('*')) {
    const tag = el.tagName.toLowerCase();
    if (tag === 'script' || tag === 'style' || tag === 'template') continue;
    let kind = null, txt = '';
    if (['img', 'canvas', 'video'].includes(tag)) kind = tag;
    else if (tag === 'svg') { if (el.parentElement && el.parentElement.closest('svg')) continue; kind = 'svg'; }
    else if (el.closest('svg')) continue;
    else {
      for (const n of el.childNodes) if (n.nodeType === 3) txt += n.textContent;
      txt = txt.trim();
      if (txt) kind = 'text';
      else { const cs = getComputedStyle(el);
        const bgc = cs.backgroundColor, clear = bgc === 'transparent' || /rgba\([^)]*,\s*0\)$/.test(bgc);
        if (cs.backgroundImage !== 'none' || !clear) kind = 'box'; }
    }
    if (!kind) continue;
    const r = el.getBoundingClientRect();
    const ix = Math.max(0, Math.min(r.right, W) - Math.max(r.left, 0));
    const iy = Math.max(0, Math.min(r.bottom, H) - Math.max(r.top, 0));
    const area = ix * iy;
    if (kind === 'box' && r.width * r.height < 100) continue;
    const o = area >= 16 ? op(el) : 0;
    out.push([path(el) + (txt ? '|' + txt.slice(0, 24) : ''), kind, o >= 0.5 && area >= 16, area / (W * H)]);
  }
  return out;
}"""

LYRIC = r"""(lines) => {
  const W = innerWidth, H = innerHeight;
  const norm = s => s.replace(/[\s　，。、！？,.!?「」『』…—\-]/g, '');
  function op(el) { let o = 1; for (let e = el; e && e.nodeType === 1; e = e.parentElement) {
      const cs = getComputedStyle(e); if (cs.display === 'none' || cs.visibility === 'hidden') return 0;
      o *= parseFloat(cs.opacity); if (o < 0.01) return 0; } return o; }
  const res = [];
  for (const line of lines) {
    const key = norm(line);
    const holders = [...document.body.querySelectorAll('*')].filter(e =>
      !['SCRIPT', 'STYLE', 'TEMPLATE'].includes(e.tagName) && norm(e.textContent).includes(key));
    const deepest = holders.filter(e => ![...e.children].some(c => norm(c.textContent).includes(key)));
    let best = null;
    for (const h of deepest) {
      let x0 = 1e9, y0 = 1e9, x1 = -1e9, y1 = -1e9, area = 0;
      const walker = document.createTreeWalker(h, NodeFilter.SHOW_TEXT);
      for (let n; (n = walker.nextNode());) {
        if (!n.textContent.trim() || op(n.parentElement) < 0.3) continue;
        const rg = document.createRange(); rg.selectNodeContents(n);
        for (const r of rg.getClientRects()) {
          const ax0 = Math.max(r.left, 0), ay0 = Math.max(r.top, 0), ax1 = Math.min(r.right, W), ay1 = Math.min(r.bottom, H);
          if (ax1 - ax0 < 1 || ay1 - ay0 < 1) continue;
          area += (ax1 - ax0) * (ay1 - ay0);
          x0 = Math.min(x0, ax0); y0 = Math.min(y0, ay0); x1 = Math.max(x1, ax1); y1 = Math.max(y1, ay1);
        }
      }
      if (area > 0 && (!best || area > best.area)) best = {area, box: [x0, y0, x1, y1]};
    }
    res.push(best);
  }
  return res;
}"""


def classify(box, w, h):
    if box is None:
        return "not-found"
    x0, y0, x1, y1 = box
    bw, bh = x1 - x0, y1 - y0
    cx, cy = (x0 + x1) / 2 / w, (y0 + y1) / 2 / h
    if bh > bw:
        return "other"
    return "subtitle" if abs(cx - 0.5) <= 0.08 and cy >= 0.7 and bh <= 0.15 * h else "other"


def _norm(s):
    return re.sub(r"[\s　，。、！？,.!?「」『』…—\-]", "", s)


def _median(xs):
    xs = sorted(xs)
    if not xs:
        return None
    return xs[len(xs) // 2] if len(xs) % 2 else (xs[len(xs) // 2 - 1] + xs[len(xs) // 2]) / 2


def cluster(times, gap=0.15):
    out = []
    for t in sorted(times):
        if out and t - out[-1][-1] <= gap:
            out[-1].append(t)
        else:
            out.append([t])
    return out


def read(page_path, duration, size, sections, pre, win, lyrics, fps, fn="__setTime"):
    from playwright.sync_api import sync_playwright
    w, h = map(int, size.lower().split("x"))
    n = int(round(duration * fps))
    times = [round(i / fps, 4) for i in range(n)]
    series, kinds, canvas = {}, {}, {}
    lyric_rows = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": w, "height": h})
        pg.goto(Path(page_path).resolve().as_uri())
        pg.wait_for_function(f"typeof window.{fn} === 'function'", timeout=20000)
        for i, t in enumerate(times):
            pg.evaluate(f"t => window.{fn}(t)", t)
            cmax = 0.0
            for key, kind, vis, share in pg.evaluate(COLLECT):
                s = series.setdefault(key, [False] * n)
                s[i] = s[i] or vis
                kinds[key] = kind
                if kind == "canvas" and vis:
                    cmax = max(cmax, share)
            canvas[i] = cmax
        if lyrics:
            for ln in lyrics:
                t = round((ln["start_s"] + ln["end_s"]) / 2, 3)
                pg.evaluate(f"t => window.{fn}(t)", t)
                got = pg.evaluate(LYRIC, [ln["text"]])[0]
                box = got["box"] if got else None
                lyric_rows.append({"n": ln.get("n"), "t": t, "text_chars": len(ln["text"]),
                                   "box": [round(v) for v in box] if box else None, "class": classify(box, w, h)})
        b.close()
    lyric_text = "".join(_norm(ln["text"]) for ln in lyrics) if lyrics else ""
    rows = []
    for s0 in sections:
        lo, hi = s0 - pre, s0 + win
        onsets = []
        for key, s in series.items():
            for i in range(n):   # before t = 0 everything counts as invisible: the first frame is an entrance
                if lo <= times[i] < hi and s[i] and (i == 0 or not s[i - 1]):
                    onsets.append((times[i], key))
        cs = max([canvas[i] for i in range(n) if lo <= times[i] < hi] or [0.0])
        layers = cluster([t for t, _ in onsets])
        # descriptive (added 2026-10-12 after r27 MA2): the same count without text elements whose text is part of a
        # lyric line, so a karaoke-style per-character fill does not read as one layer per character
        rest = [t for t, k in onsets if not ("|" in k and lyric_text and _norm(k.split("|", 1)[1]) in lyric_text)]
        rows.append({"start": s0, "entrances": len(onsets), "layers": len(layers),
                     "layers_excl_lyric": len(cluster(rest)) if lyric_text else None,
                     "layer_onsets": [round(c[0], 3) for c in layers], "canvas_share": round(cs, 3),
                     "status": "undetermined" if cs >= 0.5 else "ok"})
    ok = [r["layers"] for r in rows if r["status"] == "ok"]
    ok_x = [r["layers_excl_lyric"] for r in rows if r["status"] == "ok" and r["layers_excl_lyric"] is not None]
    found = [r for r in lyric_rows if r["class"] != "not-found"]
    summary = {"sections_ok": len(ok),
               "median_layers": _median(ok),
               "median_layers_excl_lyric": _median(ok_x),
               "lyrics_found": len(found), "lyrics_total": len(lyric_rows),
               "subtitle_share": round(sum(r["class"] == "subtitle" for r in found) / len(found), 3) if found else None}
    return {"page": str(page_path), "fps": fps, "pre": pre, "win": win, "summary": summary,
            "sections": rows, "lyrics": lyric_rows, "elements": len(series)}


# ---------------------------------------------------------------- selftest
PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>
html,body{{margin:0;width:1280px;height:720px;overflow:hidden;background:#222}}
.e{{position:absolute;opacity:0;color:#fff;font:40px sans-serif}}
.b{{background:#c33;width:200px;height:120px}}
</style></head><body>{body}<script>
const items = {items};
window.__setTime = function (t) {{
  for (const [id, a, b] of items) {{ const el = document.getElementById(id);
    el.style.opacity = (t >= a && t < b) ? 1 : 0; }}
  {extra}
}};
window.__setTime(0);
</script></body></html>"""


def page(body, items, extra=""):
    return PAGE.format(body=body, items=json.dumps(items), extra=extra)


def selftest():
    td = Path(tempfile.mkdtemp(prefix="domlayers_"))
    fails = []

    def check(name, cond, got):
        print(f"  {'PASS' if cond else 'FAIL'} {name}: {got}")
        if not cond:
            fails.append(name)

    # 1 stagger: section 0 everything at once (known-false), section 4 four layers 0.4 s apart (known-true),
    #   section 8 a group wrapper fading in with 5 children (one layer: ancestor opacity), section 12 letters 0.1 s apart
    body = ('<div id="a1" class="e b" style="left:10px;top:10px"></div><div id="a2" class="e" style="left:300px;top:10px">ALL</div>'
            '<div id="a3" class="e b" style="left:600px;top:10px"></div>'
            + "".join(f'<div id="s{i}" class="e b" style="left:{40 + i * 260}px;top:300px"></div>' for i in range(4))
            + '<div id="g" class="e" style="left:0;top:0">' + "".join(
                f'<div class="b" style="position:absolute;left:{i * 210}px;top:500px"></div>' for i in range(5)) + '</div>'
            + "".join(f'<span id="L{i}" class="e" style="left:{100 + i * 50}px;top:620px">字</span>' for i in range(6)))
    items = ([["a1", 0, 3.5], ["a2", 0, 3.5], ["a3", 0, 3.5]]
             + [[f"s{i}", 4 + i * 0.4, 7.5] for i in range(4)] + [["g", 8, 11.5]]
             + [[f"L{i}", 12 + i * 0.1, 15.5] for i in range(6)])
    (td / "stagger.html").write_text(page(body, items), encoding="utf-8")
    r = read(td / "stagger.html", 16, "1280x720", [0, 4, 8, 12], 0.5, 2.4, None, 15)
    lay = [s["layers"] for s in r["sections"]]
    check("all-at-once reads 1 layer (known-false)", lay[0] == 1, lay[0])
    check("four 0.4 s steps read 4 layers (known-true)", lay[1] == 4, lay[1])
    check("group fading as one reads 1 layer", lay[2] == 1, lay[2])
    check("letters 0.1 s apart read 1 layer", lay[3] == 1, lay[3])
    check("positive control fires above negative", lay[1] > lay[0], lay)

    # 1b karaoke-style fill: one picture at 0, then six lyric characters lighting 0.25 s apart (r27 MA2's shape);
    #    all layers read 7, the descriptive count without lyric text reads 1
    kb = ('<div id="pic" class="e b" style="left:10px;top:10px"></div>'
          + "".join(f'<span id="K{i}" class="e" style="left:{300 + i * 50}px;top:600px">{c}</span>'
                    for i, c in enumerate("雪停在門口了")))
    kitems = [["pic", 0, 3.5]] + [[f"K{i}", 0.5 + i * 0.25, 3.5] for i in range(6)]
    (td / "karaoke.html").write_text(page(kb, kitems), encoding="utf-8")
    r = read(td / "karaoke.html", 4, "1280x720", [0], 0.5, 2.4,
             [{"n": 1, "start_s": 0.5, "end_s": 2.0, "text": "雪停在門口了"}], 15)
    s0 = r["sections"][0]
    check("karaoke fill: every character reads a layer", s0["layers"] == 7, s0["layers"])
    check("karaoke fill: without lyric text reads 1 layer", s0["layers_excl_lyric"] == 1, s0["layers_excl_lyric"])

    # 2 canvas page -> undetermined
    cbody = '<canvas id="c" class="e" width="1280" height="720" style="left:0;top:0"></canvas>'
    (td / "canvas.html").write_text(page(cbody, [["c", 0, 9]]), encoding="utf-8")
    r = read(td / "canvas.html", 4, "1280x720", [0], 0.5, 2.4, None, 15)
    check("full-frame canvas reads undetermined", r["sections"][0]["status"] == "undetermined", r["sections"][0])

    # 3 lyrics: bottom-centre subtitle (known-true), big top-left, vertical, per-letter spans, hidden copy, absent
    lb = ('<div id="sub" class="e" style="left:0;width:1280px;text-align:center;top:640px;font-size:32px">我數著經過的窗</div>'
          '<div id="big" class="e" style="left:40px;top:40px;font-size:120px">花開滿昨天的路</div>'
          '<div id="ver" class="e" style="left:1100px;top:60px;font-size:48px;writing-mode:vertical-rl">風替我記住步子</div>'
          '<div id="spn" class="e" style="left:400px;top:300px;font-size:60px">' + "".join(
              f"<span>{c}</span>" for c in "海慢慢收起太陽") + '</div>'
          '<div style="display:none">浪記得你的名字</div><div id="vis" class="e" style="left:500px;top:100px">浪記得你的名字</div>'
          '<div id="lft" class="e" style="left:72px;top:600px;font-size:32px">I log the doors, I log the halls, every one</div>')
        # the lyric lines are each visible in their own second
    litems = [["sub", 0, 1], ["big", 1, 2], ["ver", 2, 3], ["spn", 3, 4], ["vis", 4, 5], ["lft", 4, 5]]
    (td / "lyrics.html").write_text(page(lb, litems), encoding="utf-8")
    lyr = [{"n": 1, "start_s": 0.2, "end_s": 0.8, "text": "我數著經過的窗"},
           {"n": 2, "start_s": 1.2, "end_s": 1.8, "text": "花開滿昨天的路"},
           {"n": 3, "start_s": 2.2, "end_s": 2.8, "text": "風替我記住步子"},
           {"n": 4, "start_s": 3.2, "end_s": 3.8, "text": "海慢慢收起太陽"},
           {"n": 5, "start_s": 4.2, "end_s": 4.8, "text": "浪記得你的名字"},
           {"n": 6, "start_s": 0.2, "end_s": 0.8, "text": "林子很深很安靜"},
           {"n": 7, "start_s": 4.2, "end_s": 4.8, "text": "I log the doors, I log the halls, every one"}]
    r = read(td / "lyrics.html", 5, "1280x720", [], 0.5, 2.4, lyr, 5)
    cls = [x["class"] for x in r["lyrics"]]
    check("bottom-centre line reads subtitle (known-true)", cls[0] == "subtitle", cls[0])
    check("big top-left line reads other (known-false)", cls[1] == "other", cls[1])
    check("vertical line reads other", cls[2] == "other", cls[2])
    check("per-letter spans are found", cls[3] == "other", cls[3])
    check("hidden copy ignored, visible copy found", cls[4] == "other" and r["lyrics"][4]["box"][1] < 300, r["lyrics"][4])
    check("absent line reads not-found", cls[5] == "not-found", cls[5])
    check("left-aligned long bottom line reads other (known-false)", cls[6] == "other", r["lyrics"][6])
    check("line hidden at its time reads not-found",
          read(td / "lyrics.html", 5, "1280x720", [], 0.5, 2.4,
               [{"n": 1, "start_s": 1.2, "end_s": 1.8, "text": "我數著經過的窗"}], 5)["lyrics"][0]["class"] == "not-found", "")
    print("SELFTEST", "PASS" if not fails else f"FAIL ({', '.join(fails)})")
    return 0 if not fails else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("page", nargs="?")
    ap.add_argument("--out")
    ap.add_argument("--duration", type=float)
    ap.add_argument("--size", default="1280x720")
    ap.add_argument("--sections", default="")
    ap.add_argument("--pre", type=float, default=0.5)
    ap.add_argument("--win", type=float, default=2.4)
    ap.add_argument("--lyrics")
    ap.add_argument("--fps", type=float, default=15)
    ap.add_argument("--fn", default="__setTime", help="the page's time function on window (r3 pages: render)")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        sys.exit(selftest())
    if not (a.page and a.out and a.duration):
        ap.error("page, --out and --duration are required")
    secs = [float(x) for x in a.sections.split(",") if x.strip()]
    lyr = json.loads(Path(a.lyrics).read_text(encoding="utf-8"))["lines"] if a.lyrics else None
    r = read(a.page, a.duration, a.size, secs, a.pre, a.win, lyr, a.fps, a.fn)
    Path(a.out).write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(r["summary"], ensure_ascii=False))


if __name__ == "__main__":
    main()

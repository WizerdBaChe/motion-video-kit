"""Page scan: per-frame DOM + pixel reads of a time-driven page for build errors (convergence design §2).

Rows (all look/info; nothing blocks, INV-6):
  QF-1c slow_scale_on_text  a text element's effective scale drifts slowly (the T09 "breathing" push); DOM only
  QF-1  text_shimmer        inside a QF-1c segment, the glyphs' ink centroid departs from a smooth trend
  QF-2  one_frame_pop       a text element goes from absent/transparent to opaque between two frames
  QF-3  font_node           the platform font rendering most glyphs is not the element's first family
  QF-6  pulse               an element's scale or opacity alternates >= 3 cycles within 4 s
  QF-7  state_text          declared state facts missing from the DOM text of their clip window (M2)
  QF-8  required_asset      a required asset shown too briefly, cropped, or stretched (M2)

Analysis functions are pure (lists of numbers in, findings out) so the selftest can drive them with
synthetic series; `read_page` is the only part that needs a browser.
"""
from __future__ import annotations

import math
from fractions import Fraction
from pathlib import Path

# ------------------------------------------------------------------ provisional thresholds (design §2)
SHIMMER_MIN_FRAMES = 12
SHIMMER_PX = 0.25            # median centroid residual (px) that lists a run
SLOW_SCALE_MAX = 0.15        # /s: below this an ongoing scale change is a drift, not a move
SLOW_SCALE_MIN = 0.002       # /s: below this it is numerical noise
SLOW_SCALE_MIN_S = 1.0
POP_LOW, POP_HIGH = 0.1, 0.9
PULSE_SCALE_AMP = 0.01
PULSE_OPACITY_AMP = 0.1
PULSE_CYCLES, PULSE_WINDOW_S = 3, 4.0
OPAQUE = 0.95

READ_JS = r"""() => {
  window.__qfn = window.__qfn || 0;
  const vw = innerWidth, vh = innerHeight, out = {text: [], xf: [], asset: [], canvas: 0};
  const skip = new Set(['SCRIPT','STYLE','NOSCRIPT','TEMPLATE','TITLE','HEAD']);
  function eff(el) { let o = 1; for (let a = el; a && a.nodeType === 1; a = a.parentElement) {
      const cs = getComputedStyle(a); if (cs.display === 'none' || cs.visibility === 'hidden') return 0;
      o *= parseFloat(cs.opacity); if (o < 0.005) return 0; } return o; }
  function clipFrac(el, r) { let x0 = Math.max(0, r.left), y0 = Math.max(0, r.top),
      x1 = Math.min(vw, r.right), y1 = Math.min(vh, r.bottom);
    for (let a = el.parentElement; a && a.nodeType === 1; a = a.parentElement) {
      const cs = getComputedStyle(a); if (cs.overflow === 'visible' && cs.clipPath === 'none') continue;
      const q = a.getBoundingClientRect(); x0 = Math.max(x0, q.left); y0 = Math.max(y0, q.top);
      x1 = Math.min(x1, q.right); y1 = Math.min(y1, q.bottom); }
    const a = Math.max(0, x1 - x0) * Math.max(0, y1 - y0), full = r.width * r.height;
    return full > 0 ? a / full : 0; }
  function stamp(el) { if (!el.dataset.qf) el.dataset.qf = 'q' + (window.__qfn++); return el.dataset.qf; }
  const all = document.body ? document.body.querySelectorAll('*') : [];
  for (const el of all) {
    if (skip.has(el.tagName)) continue;
    const isHtml = el instanceof HTMLElement;
    let own = '';
    for (const c of el.childNodes) if (c.nodeType === 3) own += c.nodeValue;
    own = own.replace(/\s+/g, ' ').trim();
    const cs = getComputedStyle(el);
    const hasXf = cs.transform !== 'none';
    const asset = el.dataset ? el.dataset.asset : undefined;
    if (el.tagName === 'CANVAS') { const r = el.getBoundingClientRect(); if (eff(el) > 0)
      out.canvas += Math.max(0, Math.min(vw, r.right) - Math.max(0, r.left)) * Math.max(0, Math.min(vh, r.bottom) - Math.max(0, r.top)); }
    if (!own && !hasXf && !asset) continue;
    const r = el.getBoundingClientRect();
    if (r.width < 1 || r.height < 1) continue;
    const o = eff(el); if (o <= 0) continue;
    const ow = isHtml ? el.offsetWidth : 0;
    const sc = ow > 0 ? r.width / ow : null;
    const id = stamp(el);
    if (own) out.text.push([id, own.slice(0, 60), r.left, r.top, r.width, r.height, o, sc, cs.fontFamily]);
    if (hasXf && !own) out.xf.push([id, r.left, r.top, r.width, r.height, o, sc]);
    if (asset) { const nw = el.naturalWidth || el.videoWidth || 0, nh = el.naturalHeight || el.videoHeight || 0;
      out.asset.push([id, asset, r.width, r.height, o, clipFrac(el, r), nw, nh]); }
  }
  out.canvas = out.canvas / (vw * vh);
  return out;
}"""


# ------------------------------------------------------------------ pure analysis
def quad_resid(ys: list[float]) -> list[float]:
    """Absolute residuals of ys against its least-squares quadratic in the index (n >= 3)."""
    n = len(ys)
    xs = list(range(n))
    # normal equations for a + b x + c x^2
    s = [sum(x ** k for x in xs) for k in range(5)]
    t = [sum((x ** k) * y for x, y in zip(xs, ys)) for k in range(3)]
    m = [[s[0], s[1], s[2]], [s[1], s[2], s[3]], [s[2], s[3], s[4]]]
    coef = _solve3(m, t)
    if coef is None:
        mu = sum(ys) / n
        return [abs(y - mu) for y in ys]
    a, b, c = coef
    return [abs(y - (a + b * x + c * x * x)) for x, y in zip(xs, ys)]


def _solve3(m, v):
    m = [row[:] + [v[i]] for i, row in enumerate(m)]
    for col in range(3):
        piv = max(range(col, 3), key=lambda r: abs(m[r][col]))
        if abs(m[piv][col]) < 1e-12:
            return None
        m[col], m[piv] = m[piv], m[col]
        for r in range(3):
            if r != col:
                f = m[r][col] / m[col][col]
                m[r] = [a - f * b for a, b in zip(m[r], m[col])]
    return [m[i][3] / m[i][i] for i in range(3)]


def median(xs):
    s = sorted(xs)
    n = len(s)
    return (s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2) if n else float("nan")


def p90(xs):
    s = sorted(xs)
    return s[min(len(s) - 1, int(math.ceil(0.9 * len(s))) - 1)] if s else float("nan")


def runs_of(samples: list[tuple], ok) -> list[list[tuple]]:
    """Split a per-frame sample list [(k, ...), ...] into runs of consecutive k where ok(sample) holds."""
    out, cur = [], []
    for s in samples:
        if ok(s) and cur and s[0] == cur[-1][0] + 1:
            cur.append(s)
        else:
            if len(cur) >= 2:
                out.append(cur)
            cur = [s] if ok(s) else []
    if len(cur) >= 2:
        out.append(cur)
    return out


def drift_segments(samples: list[tuple], fps: int) -> list[list[tuple]]:
    """Segments of ONE text element in which its effective scale changes at a slow, sustained rate:
    the 5-frame mean of the per-frame relative rate stays in [SLOW_SCALE_MIN, SLOW_SCALE_MAX) /s for at
    least SLOW_SCALE_MIN_S, with unchanged text and opacity >= OPAQUE. Pure DOM facts."""
    def ok(s):
        return s[6] >= OPAQUE and s[7] is not None and s[4] >= 6 and s[5] >= 6

    out = []
    for run in runs_of(samples, ok):
        rates = [None] + [(b[7] - a[7]) / a[7] * fps if a[7] else None for a, b in zip(run, run[1:])]
        sm = []
        for i in range(len(run)):
            win = [r for r in rates[max(1, i - 2):i + 3] if r is not None]
            sm.append(sum(win) / len(win) if win else None)
        cur = []
        for s, r, prev in zip(run, sm, [None] + run[:-1]):
            good = r is not None and SLOW_SCALE_MIN <= abs(r) < SLOW_SCALE_MAX
            same = prev is None or not cur or s[1] == cur[-1][1]
            if good and same:
                cur.append(s)
            else:
                if len(cur) / fps >= SLOW_SCALE_MIN_S:
                    out.append(cur)
                cur = [s] if good else []
        if len(cur) / fps >= SLOW_SCALE_MIN_S:
            out.append(cur)
    return out


def drift_findings(samples: list[tuple], fps: int) -> list[dict]:
    """QF-1c per drift segment, with the QF-1 pixel residual measured inside it."""
    found = []
    for seg in drift_segments(samples, fps):
        rate = (seg[-1][7] - seg[0][7]) / seg[0][7] / ((len(seg) - 1) / fps)
        px = [s for s in seg if s[8] is not None]
        c_med = d_med = None
        if len(px) >= SHIMMER_MIN_FRAMES:
            rx = quad_resid([s[8] / s[4] for s in px])
            ry = quad_resid([s[9] / s[5] for s in px])
            c_med = round(median([math.hypot(a * s[4], b * s[5]) for a, b, s in zip(rx, ry, px)]), 4)
            dens = [s[10] / (s[4] * s[5]) for s in px]
            mu = sum(dens) / len(dens)
            d_med = round(median([v / mu for v in quad_resid(dens)]), 5) if mu > 0 else None
        found.append({"t0": round(seg[0][0] / fps, 3), "t1": round(seg[-1][0] / fps, 3), "frames": len(seg),
                      "text": seg[0][1], "scale_rate_per_s": round(rate, 5),
                      "centroid_resid_px_median": c_med, "density_resid_rel_median": d_med,
                      "shimmer_listed": c_med is not None and c_med >= SHIMMER_PX})
    return found


def in_windows(t: float, wins: list[dict], pad: float = 0.0) -> dict | None:
    for w in wins:
        if w["t0"] - pad <= t <= w["t1"] + pad:
            return w
    return None


def pops(series: dict[str, dict[int, tuple]], frames: list[int], fps: int, cuts: list[dict]) -> list[dict]:
    """series: id -> {k: (text, opacity)}; frames: sampled frame numbers in order (stride 1 needed).
    One finding per frame at which >= 1 text element jumps from < POP_LOW to >= POP_HIGH."""
    by_k: dict[int, list[str]] = {}
    for el, pts in series.items():
        for a, b in zip(frames, frames[1:]):
            if b != a + 1 or b not in pts:
                continue
            prev = pts.get(a, (None, 0.0))[1]
            if prev < POP_LOW and pts[b][1] >= POP_HIGH:
                by_k.setdefault(b, []).append(pts[b][0])
    out = []
    for k in sorted(by_k):
        t = k / fps
        w = in_windows(t, cuts, pad=1.0 / fps)
        out.append({"t": round(t, 4), "frame": k, "elements": len(by_k[k]), "texts": by_k[k][:6],
                    "declared": None if w is None else w.get("why"), "listed": w is None})
    return out


def extrema_cycles(vals: list[float], amp: float, rel: bool) -> list[int]:
    """Indices of alternating extrema whose swing from the previous extremum is at least amp
    (relative to the value when rel). A pulse of one cycle has two such swings."""
    def swing(a, b):
        return (b - a) / abs(a) if rel and a else b - a

    idx: list[int] = []
    if not vals:
        return idx
    direction = 1                          # tracking a maximum first; a fall from the start marks index 0
    ci, cv = 0, vals[0]
    for i, v in enumerate(vals[1:], 1):
        if direction > 0:
            if v >= cv:
                ci, cv = i, v
            elif -swing(cv, v) >= amp:
                idx.append(ci)
                direction, ci, cv = -1, i, v
        else:
            if v <= cv:
                ci, cv = i, v
            elif swing(cv, v) >= amp:
                idx.append(ci)
                direction, ci, cv = 1, i, v
    return idx


def pulses(series: dict[str, dict[int, tuple]], fps: int, declared: list[dict]) -> list[dict]:
    """series: id -> {k: (label, scale or None, opacity)}. One finding per element whose scale or
    opacity alternates >= PULSE_CYCLES cycles inside any PULSE_WINDOW_S window."""
    out = []
    for el, pts in series.items():
        ks = sorted(pts)
        if len(ks) < 6:
            continue
        for what, pos, amp, rel in (("scale", 1, PULSE_SCALE_AMP, True), ("opacity", 2, PULSE_OPACITY_AMP, False)):
            vals = [pts[k][pos] for k in ks]
            if any(v is None for v in vals):
                continue
            ex = [ks[i] for i in extrema_cycles(vals, amp, rel)]
            need = 2 * PULSE_CYCLES
            best = None
            for i in range(len(ex) - need + 1):
                if (ex[i + need - 1] - ex[i]) / fps <= PULSE_WINDOW_S:
                    best = (ex[i], ex[i + need - 1])
                    break
            if best:
                t0, t1 = best[0] / fps, best[1] / fps
                w = in_windows((t0 + t1) / 2, declared)
                period = (best[1] - best[0]) / fps / PULSE_CYCLES
                out.append({"element": pts[ks[0]][0], "what": what, "t0": round(t0, 3), "t1": round(t1, 3),
                            "period_s": round(period, 3), "declared": None if w is None else w.get("why"),
                            "listed": w is None})
    return out


def font_majority(fonts: list[dict]) -> dict | None:
    """CDP getPlatformFontsForNode list -> the entry rendering most glyphs."""
    return max(fonts, key=lambda f: f.get("glyphCount", 0)) if fonts else None


GENERIC = {"serif", "sans-serif", "monospace", "cursive", "fantasy", "system-ui", "ui-sans-serif", "ui-serif",
           "ui-monospace", "math", "emoji", "fangsong"}


def font_verdict(first: str | None, face_families: set[str], major: dict | None) -> str:
    """present / substituted / undetermined for one node."""
    if not first or major is None or first.lower() in GENERIC:
        return "undetermined"
    if first in face_families:
        return "present" if major.get("isCustomFont") else "substituted"
    return "present" if major.get("familyName", "").lower() == first.lower() else "substituted"


# ------------------------------------------------------------------ browser part
def png_gray(data: bytes) -> list[list[float]]:
    """Decode an 8-bit, non-interlaced PNG (grey, grey+alpha, RGB, RGBA) to rows of luma (BT.601).
    Standard library only: the kit imports nothing but the standard library and Playwright (FK-INV-7)."""
    import struct
    import zlib
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG")
    pos, idat, w = 8, [], None
    while pos < len(data):
        n, t = struct.unpack(">I4s", data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + n]
        if t == b"IHDR":
            w, h, depth, ctype, _c, _f, inter = struct.unpack(">IIBBBBB", body)
            if depth != 8 or inter != 0 or ctype not in (0, 2, 4, 6):
                raise ValueError(f"unsupported PNG depth {depth} type {ctype} interlace {inter}")
            bpp = {0: 1, 2: 3, 4: 2, 6: 4}[ctype]
        elif t == b"IDAT":
            idat.append(body)
        elif t == b"IEND":
            break
        pos += 12 + n
    if w is None:
        raise ValueError("PNG without IHDR")
    raw = zlib.decompress(b"".join(idat))
    stride = w * bpp
    prev = bytearray(stride)
    rows = []
    for r in range(h):
        f = raw[r * (stride + 1)]
        cur = bytearray(raw[r * (stride + 1) + 1:(r + 1) * (stride + 1)])
        if f == 1:
            for i in range(bpp, stride):
                cur[i] = (cur[i] + cur[i - bpp]) & 255
        elif f == 2:
            for i in range(stride):
                cur[i] = (cur[i] + prev[i]) & 255
        elif f == 3:
            for i in range(stride):
                cur[i] = (cur[i] + ((cur[i - bpp] if i >= bpp else 0) + prev[i]) // 2) & 255
        elif f == 4:
            for i in range(stride):
                a = cur[i - bpp] if i >= bpp else 0
                b, c = prev[i], (prev[i - bpp] if i >= bpp else 0)
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                cur[i] = (cur[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        if bpp >= 3:
            rows.append([0.299 * cur[i] + 0.587 * cur[i + 1] + 0.114 * cur[i + 2] for i in range(0, stride, bpp)])
        else:
            rows.append([float(cur[i]) for i in range(0, stride, bpp)])
        prev = cur
    return rows


def clip_box(x, y, w, h, vw: int, vh: int):
    """The integer box read around a text rect (1 px margin), or None when it leaves the viewport."""
    x0, y0 = int(math.floor(x)) - 1, int(math.floor(y)) - 1
    x1, y1 = int(math.ceil(x + w)) + 1, int(math.ceil(y + h)) + 1
    if x0 < 0 or y0 < 0 or x1 > vw or y1 > vh or x1 - x0 < 4 or y1 - y0 < 4:
        return None
    return x0, y0, x1, y1


def ink_centroid(rows: list[list[float]], x0: int, y0: int, x, y):
    """rows: luma of the box whose top-left is (x0, y0). Ink = |pixel - border median| of at least 24 levels.
    Returns (cx, cy, mass) relative to the rect origin (x, y), or (None, None, 0)."""
    border = rows[0] + rows[-1] + [r[0] for r in rows] + [r[-1] for r in rows]
    bg = median(border)
    m = sx = sy = 0.0
    for j, r in enumerate(rows):
        for i, v in enumerate(r):
            d = abs(v - bg)
            if d >= 24:
                m += d
                sx += d * i
                sy += d * j
    if m <= 0:
        return None, None, 0.0
    return sx / m + x0 - x, sy / m + y0 - y, m


def read_page(page: Path, duration: float, size: tuple[int, int], fps: int, stride: int, font_stride: int,
              t0: float = 0.0, t1: float | None = None, timeout_s: float = 30.0):
    """Pass 1 seeks every stride-th frame in [t0, t1] and reads the DOM and, every font_stride frames, the
    per-node fonts. Pass 2 re-seeks only the frames inside a QF-1c drift segment and reads the ink centroid
    of those text rects from a clipped screenshot (a page is a pure function of time, so the rect read in
    pass 1 is the rect painted in pass 2). Raises the kit's typed errors on load failure."""
    import copy
    from .capture import PlaywrightBackend, first_family
    w, h = size
    b = PlaywrightBackend("pagescan")
    frames, fonts = [], []
    b.open(page, w, h)
    try:
        b.load(timeout_s)
        face_families = set(b.page.evaluate(
            "() => [...document.fonts].map(f => f.family.replace(/^[\"']|[\"']$/g, ''))"))
        k0 = round(t0 * fps)
        k1 = round((duration if t1 is None else t1) * fps) - (1 if t1 is None else 0)
        cdp = b.page.context.new_cdp_session(b.page)
        cdp.send("DOM.enable")
        cdp.send("CSS.enable")
        for k in range(k0, k1 + 1, stride):
            b.seek(Fraction(k, fps))
            dom = b.page.evaluate(READ_JS)
            texts = [el + [None, None, 0.0] for el in dom["text"]]
            frames.append({"k": k, "text": texts, "xf": dom["xf"], "asset": dom["asset"], "canvas": dom["canvas"]})
            if (k - k0) % font_stride == 0:
                root = cdp.send("DOM.getDocument", {"depth": 0})["root"]["nodeId"]
                for el in dom["text"][:300]:
                    q = cdp.send("DOM.querySelector", {"nodeId": root, "selector": f'[data-qf="{el[0]}"]'})
                    nid = q.get("nodeId")
                    if not nid:
                        continue
                    fl = cdp.send("CSS.getPlatformFontsForNode", {"nodeId": nid}).get("fonts", [])
                    first = first_family(el[8])
                    fonts.append({"k": k, "id": el[0], "text": el[1], "first": first,
                                  "major": font_majority(fl), "verdict": font_verdict(first, face_families, font_majority(fl))})
        cdp.detach()
        # pass 2: pixels only where the DOM shows a drift (design §2 correction)
        tracked = copy.deepcopy(frames)
        track_ids(tracked)
        series: dict[str, list[tuple]] = {}
        for fi, f in enumerate(tracked):
            for ei, el in enumerate(f["text"]):
                series.setdefault(el[0], []).append((f["k"], el[1], el[2], el[3], el[4], el[5], el[6], el[7], fi, ei))
        need: dict[int, list[int]] = {}
        for s in series.values():
            for seg in drift_segments(s, fps):
                for smp in seg:
                    need.setdefault(smp[8], []).append(smp[9])
        for fi in sorted(need):
            f = frames[fi]
            b.seek(Fraction(f["k"], fps))
            for ei in need[fi]:
                el = f["text"][ei]
                box = clip_box(el[2], el[3], el[4], el[5], w, h)
                if box is None:
                    continue
                x0, y0, x1, y1 = box
                png = b.page.screenshot(type="png", clip={"x": x0, "y": y0, "width": x1 - x0, "height": y1 - y0})
                el[9], el[10], el[11] = ink_centroid(png_gray(png), x0, y0, el[2], el[3])
    finally:
        b.close()
    return frames, fonts


def track_ids(frames: list[dict]) -> None:
    """Give each text element a track id that survives a page rebuilding its DOM every frame (innerHTML):
    an element whose stamped id is new inherits the track of an unmatched element of the previous frame
    with the same text whose centre lies within max(24 px, its height). Rewrites el[0] in place."""
    prev: dict[str, tuple] = {}            # stamped id -> (track, text, cx, cy, h)
    for f in frames:
        cur: dict[str, tuple] = {}
        used = set()
        for el in f["text"]:
            if el[0] in prev:
                used.add(el[0])
        for el in f["text"]:
            sid, txt, x, y, w, h = el[0], el[1], el[2], el[3], el[4], el[5]
            cx, cy = x + w / 2, y + h / 2
            if sid in prev:
                track = prev[sid][0]
            else:
                track, best = sid, None
                for psid, (ptrack, ptxt, pcx, pcy, ph) in prev.items():
                    if psid in used or ptxt != txt:
                        continue
                    dd = math.hypot(cx - pcx, cy - pcy)
                    if dd <= max(24.0, ph) and (best is None or dd < best[0]):
                        best = (dd, psid, ptrack)
                if best:
                    used.add(best[1])
                    track = best[2]
            cur[sid] = (track, txt, cx, cy, h)
            el[0] = track
        prev = cur


def analyse(frames: list[dict], fonts: list[dict], fps: int, plan: dict | None, tl: dict | None = None) -> dict:
    """`tl` = timeline_inputs(...) or None (QF-7/QF-8 then absent: no director table given)."""
    plan = plan or {}
    track_ids(frames)
    cuts, declared_pulses = plan.get("cuts", []), plan.get("pulses", [])
    text_series: dict[str, list[tuple]] = {}
    pop_series: dict[str, dict[int, tuple]] = {}
    pulse_series: dict[str, dict[int, tuple]] = {}
    canvas = []
    for f in frames:
        k = f["k"]
        canvas.append(f["canvas"])
        for el in f["text"]:
            eid, txt, x, y, w, h, o, sc, _fam, cx, cy, m = el
            text_series.setdefault(eid, []).append((k, txt, x, y, w, h, o, sc, cx, cy, m))
            pop_series.setdefault(eid, {})[k] = (txt, o)
            pulse_series.setdefault(eid, {})[k] = (txt, sc, o)
        for eid, x, y, w, h, o, sc in f["xf"]:
            pulse_series.setdefault(eid, {})[k] = (f"<{eid}>", sc, o)
    drift = []
    for eid, s in text_series.items():
        for r in drift_findings(s, fps):
            r["element"] = eid
            drift.append(r)
    ks = [f["k"] for f in frames]
    stride1 = all(b - a == 1 for a, b in zip(ks, ks[1:]))
    canvas_share = median(canvas) if canvas else 0.0
    subst = [x for x in fonts if x["verdict"] == "substituted"]
    rows = {
        "QF-1c": {"name": "slow_scale_on_text", "listed": drift},
        "QF-1": {"name": "text_shimmer", "listed": [r for r in drift if r["shimmer_listed"]],
                 "measured_in": "QF-1c segments only (pixels are read where the DOM shows a drift)"},
        "QF-2": ({"name": "one_frame_pop", "listed": [p for p in pops(pop_series, ks, fps, cuts) if p["listed"]],
                  "declared": [p for p in pops(pop_series, ks, fps, cuts) if not p["listed"]]}
                 if stride1 else {"name": "one_frame_pop", "undetermined": "stride > 1: consecutive frames not read"}),
        "QF-3": {"name": "font_node", "listed": _dedupe_fonts(subst), "nodes_read": len(fonts),
                 "undetermined_nodes": sum(1 for x in fonts if x["verdict"] == "undetermined")},
        "QF-6": {"name": "pulse", "listed": [p for p in pulses(pulse_series, fps, declared_pulses) if p["listed"]],
                 "declared": [p for p in pulses(pulse_series, fps, declared_pulses) if not p["listed"]]},
    }
    if tl is not None:
        if tl["windows"] is None:
            rows["QF-7"] = {"name": "state_text", "undetermined": "no resolved times (run tl.py resolve on the film)"}
        else:
            st = state_text(tl["windows"], frames, fps)
            rows["QF-7"] = {"name": "state_text", "listed": [x for x in st if x.get("listed")],
                            "read": [x for x in st if not x.get("listed")]}
        ra = required_assets(tl["required"], frames, fps)
        rows["QF-8"] = {"name": "required_asset", "listed": [x for x in ra if x["listed"]],
                        "read": [x for x in ra if not x["listed"]]}
    if canvas_share >= 0.5:
        for key in ("QF-1", "QF-1c", "QF-2", "QF-3") + (("QF-7",) if "QF-7" in rows else ()):
            rows[key]["undetermined"] = f"canvas covers {canvas_share:.0%} of the frame (median): its text has no DOM node"
    return {"rows": rows, "frames_read": len(frames), "canvas_share_median": round(canvas_share, 3)}


ASPECT_DRIFT = 0.01
VISIBLE_O = 0.5


def timeline_inputs(timeline: dict, resolved: dict | None) -> dict:
    """From a director table and its resolved times: state windows for QF-7, required assets for QF-8.
    Without resolved times the windows are unknown (QF-7 undetermined); required assets need no times."""
    states = {s.get("id"): s for s in timeline.get("product_state") or [] if isinstance(s, dict)}
    tr = timeline.get("tracks") or {}
    shows = {c.get("id"): c.get("shows_state") for c in (tr.get("picture") or []) + (tr.get("overlay") or [])
             if isinstance(c, dict) and c.get("shows_state")}
    out = {"windows": None, "required": {a["id"]: a["required"] for a in timeline.get("assets") or []
                                        if isinstance(a, dict) and isinstance(a.get("required"), dict)}}
    if resolved is not None:
        wins = []
        for c in (resolved.get("picture") or []) + (resolved.get("overlay") or []):
            sids = shows.get(c.get("id"))
            if not sids:
                continue
            facts = {}
            for sid in sids:
                for k, v in ((states.get(sid) or {}).get("facts") or {}).items():
                    if isinstance(v, str) or (isinstance(v, (int, float)) and not isinstance(v, bool)):
                        facts[f"{sid}.{k}"] = v
            wins.append({"clip": c["id"], "t0": c["t0"], "t1": c["e"], "facts": facts})
        out["windows"] = wins
    return out


def _norm(s: str) -> str:
    return "".join(s.split()).casefold()


def _fact_text(v) -> str:
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return _norm(str(v))


def state_text(windows: list[dict], frames: list[dict], fps: int) -> list[dict]:
    """QF-7: per clip window, each declared string/number fact must appear in the DOM text read inside it
    (whitespace and case ignored). A window no frame fell into is reported as unread, not as missing."""
    out = []
    for w in windows:
        texts = [el[1] for f in frames if w["t0"] <= f["k"] / fps < w["t1"] for el in f["text"]]
        if not texts:
            out.append({"clip": w["clip"], "t0": round(w["t0"], 3), "t1": round(w["t1"], 3), "unread": True})
            continue
        joined = _norm(" ".join(texts))
        missing = [k for k, v in w["facts"].items() if _fact_text(v) not in joined]
        out.append({"clip": w["clip"], "t0": round(w["t0"], 3), "t1": round(w["t1"], 3),
                    "checked": len(w["facts"]), "missing": missing, "listed": bool(missing)})
    return out


def required_assets(required: dict, frames: list[dict], fps: int) -> list[dict]:
    """QF-8: per required asset id (elements carrying data-asset): visible seconds (opacity >= 0.5 and some
    box inside the viewport), the smallest visible fraction of its own box, the largest aspect drift against
    its natural size. Listed when below min_visible_s, cropped under no_crop, or drift > 1 %."""
    ks = [f["k"] for f in frames]
    step = min((b - a for a, b in zip(ks, ks[1:])), default=1) or 1
    out = []
    for aid, req in required.items():
        vis, min_frac, drift = 0, None, 0.0
        for f in frames:
            els = [e for e in f.get("asset", []) if e[1] == aid and e[4] >= VISIBLE_O and e[5] > 0]
            if not els:
                continue
            vis += 1
            e = max(els, key=lambda x: x[5] * x[2] * x[3])
            min_frac = e[5] if min_frac is None else min(min_frac, e[5])
            if e[6] > 0 and e[7] > 0 and e[3] > 0:
                drift = max(drift, abs((e[2] / e[3]) / (e[6] / e[7]) - 1))
        secs = vis * step / fps
        why = []
        if vis == 0:
            why.append("never on screen (no visible element with data-asset)")
        elif "min_visible_s" in req and secs + 1e-9 < req["min_visible_s"]:
            why.append(f"visible {secs:.2f} s < {req['min_visible_s']} s")
        if req.get("no_crop") and min_frac is not None and min_frac < 0.999:
            why.append(f"cropped: smallest visible share {min_frac:.3f}")
        if drift > ASPECT_DRIFT:
            why.append(f"aspect drift {drift:.1%}")
        out.append({"asset": aid, "visible_s": round(secs, 3), "min_visible_share": None if min_frac is None
                    else round(min_frac, 4), "aspect_drift": round(drift, 4), "why": why, "listed": bool(why)})
    return out


def _dedupe_fonts(subst: list[dict]) -> list[dict]:
    seen, out = set(), []
    for x in subst:
        key = (x["first"], (x["major"] or {}).get("familyName"), x["text"][:20])
        if key in seen:
            continue
        seen.add(key)
        out.append({"t": None, "frame": x["k"], "text": x["text"], "first_family": x["first"],
                    "rendered_by": (x["major"] or {}).get("familyName")})
    return out

"""Write preview.html next to an arm's index.html: the same page plus a small player
(play/pause, scrubber, time readout, arrow keys) that drives window.__setTime(t).

Why: arm pages are pure functions of time (frame rule: no timers), so opening index.html
by hand shows one still frame at t=0. preview.html leaves index.html untouched and adds
the clock only for a human viewer. Works from file:// (no server, no iframe).

usage: python -X utf8 tools/preview.py <index.html> [--duration S]   (or --selftest)
"""
import argparse
import re
import sys
import tempfile
from pathlib import Path

PLAYER = r"""
<!-- preview player added by motion-video-lab tools/preview.py; not part of the arm's page -->
<div id="__pv" style="position:fixed;left:0;right:0;bottom:0;z-index:2147483647;display:flex;gap:8px;align-items:center;
 padding:6px 10px;background:rgba(0,0,0,.78);color:#fff;font:13px Consolas,monospace">
 <button id="__pvb" style="font:inherit;min-width:64px">play</button>
 <input id="__pvs" type="range" min="0" step="0.001" value="0" style="flex:1">
 <span id="__pvt">0.00 s</span>
</div>
<script>
(function () {
  var D = __DURATION__, t = 0, playing = false, last = 0;
  var b = document.getElementById('__pvb'), s = document.getElementById('__pvs'), o = document.getElementById('__pvt');
  function fail(msg) { o.textContent = msg; o.style.color = '#f87171'; console.error('[preview] ' + msg); }
  function dur() { var m = window.__meta || {}; return D || m.duration || m.total || 0; }
  function show(x) {
    t = Math.max(0, Math.min(dur(), x));
    try { window.__setTime(t); } catch (e) { fail('__setTime threw: ' + e.message); playing = false; return; }
    s.value = t; o.textContent = t.toFixed(2) + ' / ' + dur().toFixed(2) + ' s';
  }
  function tick(now) {
    if (!playing) return;
    show(t + (now - last) / 1000); last = now;
    if (t >= dur()) { playing = false; b.textContent = 'play'; return; }
    requestAnimationFrame(tick);
  }
  function toggle() {
    if (t >= dur()) t = 0;
    playing = !playing; b.textContent = playing ? 'pause' : 'play';
    if (playing) { last = performance.now(); requestAnimationFrame(tick); }
  }
  function start() {
    if (typeof window.__setTime !== 'function') return fail('page has no window.__setTime');
    if (!dur()) return fail('duration unknown: rerun preview.py with --duration');
    s.max = dur(); show(0);
  }
  b.onclick = toggle;
  s.oninput = function () { playing = false; b.textContent = 'play'; show(+s.value); };
  addEventListener('keydown', function (e) {
    if (e.key === ' ') { e.preventDefault(); toggle(); }
    else if (e.key === 'ArrowRight') show(t + 1 / 30);
    else if (e.key === 'ArrowLeft') show(t - 1 / 30);
  });
  if (document.readyState === 'complete') start(); else addEventListener('load', start);
})();
</script>
"""


def guess_duration(page_dir: Path):
    plan = page_dir / "plan.md"
    if plan.exists():
        m = re.search(r"duration[^0-9]{0,40}([0-9]+(?:\.[0-9]+)?)\s*s", plan.read_text(encoding="utf-8", errors="replace"), re.I)
        if m:
            return float(m.group(1))
    return 0.0


def make(index: Path, duration: float = 0.0) -> Path:
    html = index.read_text(encoding="utf-8", errors="replace")
    d = duration or guess_duration(index.parent)
    block = PLAYER.replace("__DURATION__", repr(float(d)))
    if "</body>" in html.lower():
        i = html.lower().rfind("</body>")
        out_html = html[:i] + block + html[i:]
    else:
        out_html = html + block
    out = index.with_name("preview.html")
    out.write_text(out_html, encoding="utf-8")
    return out


def selftest():
    ok = True
    with tempfile.TemporaryDirectory() as td:
        p = Path(td)
        (p / "plan.md").write_text("**Exact duration: 45.000 s (1350 frames)**", encoding="utf-8")
        (p / "index.html").write_text("<html><body><p>x</p></body></html>", encoding="utf-8")
        out = make(p / "index.html")
        h = out.read_text(encoding="utf-8")
        checks = [("duration read from plan.md", "var D = 45.0," in h),
                  ("player inserted before </body>", h.index("__pv") < h.lower().rindex("</body>")),
                  ("index.html untouched", "__pv" not in (p / "index.html").read_text(encoding="utf-8"))]
        (p / "plan.md").unlink()
        h2 = make(p / "index.html").read_text(encoding="utf-8")
        checks.append(("no plan -> duration 0 (page meta or on-screen error)", "var D = 0.0," in h2))
    for name, good in checks:
        print(f"  {'ok ' if good else 'BAD'} {name}")
        ok = ok and good
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("index", nargs="?")
    ap.add_argument("--duration", type=float, default=0.0)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        sys.exit(0 if selftest() else 1)
    if not a.index:
        ap.error("index.html path required")
    print(make(Path(a.index), a.duration))


if __name__ == "__main__":
    main()

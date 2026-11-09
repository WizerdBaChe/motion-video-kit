"""CaptureBackend protocol, PlaywrightBackend, font fingerprint probe (PSM 6.3; SG-1/2/6/10/12; FK-INV-3, FK-INV-9)."""
from __future__ import annotations

import json
import re
from fractions import Fraction
from pathlib import Path
from typing import Protocol
from urllib.parse import urlparse
from urllib.request import url2pathname

from .common import AssetLoad, EnvError, Internal, NotReady, PageContract, PageRuntime, one_line, sha256_file
from .types import FamilyCheck, FontLoad, LoadReport

GENERIC_FAMILIES = {"serif", "sans-serif", "monospace", "cursive", "fantasy", "system-ui", "ui-serif", "ui-sans-serif",
                    "ui-monospace", "ui-rounded", "emoji", "math", "fangsong"}
PLATFORM_ALIASES = {"-apple-system", "blinkmacsystemfont"}
PROBE_TEXT = {"latin": "Hamburgefonstiv 0123", "cjk": "永和九年歲在癸丑"}
FALLBACKS = ("serif", "sans-serif", "monospace")
CONSOLE_CAP = 200
CONSOLE_CHARS = 500


class CaptureBackend(Protocol):
    def open(self, page_path: Path, width: int, height: int) -> None: ...
    def load(self, ready_timeout_s: float) -> LoadReport: ...
    def seek(self, t: Fraction) -> None: ...
    def snapshot(self) -> bytes: ...
    def live_animations(self) -> int: ...
    def sample_font_families(self, moment: str) -> list[FamilyCheck]: ...
    def close(self) -> None: ...


# ------------------------------------------------------------------ font fingerprint (pure part)
def first_family(css_value: str) -> str | None:
    """The family a computed font-family value asks for first. Platform aliases (-apple-system,
    BlinkMacSystemFont) are skipped, as Chromium skips them on Windows (Q-7d); a generic family ends the
    search with None (it always resolves, so later names are never used)."""
    for m in re.finditer(r'''\s*(?:"([^"]*)"|'([^']*)'|([^,]*))\s*(?:,|$)''', css_value or ""):
        name = (m.group(1) or m.group(2) or m.group(3) or "").strip()
        if not name:
            continue
        if name.lower() in PLATFORM_ALIASES:
            continue
        if name.lower() in GENERIC_FAMILIES:
            return None
        return name
    return None


def decide_script(lists: dict[str, list[str]], baselines: dict[str, list[str]]) -> str:
    for fb in FALLBACKS:
        if not baselines.get(fb) or not lists.get(fb):
            raise ValueError("font probe returned an empty font list (probe element not laid out)")
    if len({json.dumps(baselines[fb]) for fb in FALLBACKS}) == 1:
        return "undetermined"
    if all(lists[fb] == baselines[fb] for fb in FALLBACKS):
        return "substituted"
    return "present"


def decide_family(family: str, lists: dict, baselines: dict, sampled_at: tuple) -> FamilyCheck:
    per = {s: decide_script(lists[s], baselines[s]) for s in PROBE_TEXT}
    decided_by = next((s for s in PROBE_TEXT if per[s] == "present"), None)
    decidable = [v for v in per.values() if v != "undetermined"]
    if decided_by:
        result = "present"
    elif decidable and all(v == "substituted" for v in decidable):
        result = "substituted"       # includes R-9: an undetermined script does not block a decision
    else:
        result = "undetermined"
    return FamilyCheck(family=family, result=result, decided_by=decided_by, per_script=per, lists=lists,
                       baselines=baselines, sampled_at=tuple(sampled_at))


# ------------------------------------------------------------------ Playwright backend
_SEEK_JS = """async (t) => {
  try { window.__setTime(t); } catch (e) { return {error: String(e && e.stack || e)}; }
  await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
  let live = 0;
  try { live = document.getAnimations().filter(a => a.playState === 'running').length; } catch (e) {}
  return {live};
}"""

_FONTS_JS = """async () => {
  const srcs = {};
  for (const sh of document.styleSheets) {
    let rules; try { rules = sh.cssRules; } catch (e) { continue; }
    for (const r of rules) if (r.type === 5) {
      const fam = r.style.getPropertyValue('font-family').replace(/^["']|["']$/g, '').trim();
      srcs[fam] = (srcs[fam] ? srcs[fam] + ' | ' : '') + r.style.getPropertyValue('src');
    }
  }
  const out = [];
  for (const f of document.fonts) {
    try { await f.load(); } catch (e) {}
    const fam = f.family.replace(/^["']|["']$/g, '');
    out.push([fam, f.status, srcs[fam] || '']);
  }
  return out;
}"""

_READY_SHAPE_JS = """() => { const r = window.__ready;
  if (r === undefined) return 'absent';
  if (r && typeof r.then === 'function') return 'promise';
  return r ? 'true' : 'flag'; }"""

_FAMILIES_JS = """() => { const fams = new Set(); const root = document.body || document.documentElement;
  const w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT); let n;
  while ((n = w.nextNode())) { if (!n.nodeValue.trim()) continue; const el = n.parentElement; if (!el) continue;
    if (['SCRIPT','STYLE','NOSCRIPT','TEMPLATE','TITLE'].includes(el.tagName)) continue;
    fams.add(getComputedStyle(el).fontFamily); }
  return [...fams]; }"""

_PROBE_INSERT_JS = """([probes, placement]) => {
  const host = document.createElement('fk-probe-host');
  host.id = 'fk-probe-host';
  let root;
  if (placement === 'body-unsafe') { (document.body || document.documentElement).appendChild(host); root = host; }
  else { document.documentElement.appendChild(host); host.style.setProperty('all', 'initial', 'important');
         root = host.attachShadow({mode: 'open'}); }
  for (const [id, family, text] of probes) {
    const s = document.createElement('span'); s.id = id; s.textContent = text;
    for (const [k, v] of [['font-family', family], ['font-size', '16px'], ['visibility', 'hidden'],
                          ['position', 'absolute'], ['left', '-10000px']]) s.style.setProperty(k, v, 'important');
    root.appendChild(s);
  }
  for (const s of root.querySelectorAll('span')) s.getBoundingClientRect();
  return new Promise(r => requestAnimationFrame(() => requestAnimationFrame(() => r(true))));
}"""

_PROBE_REMOVE_JS = "() => { const h = document.getElementById('fk-probe-host'); if (h) h.remove(); }"
_PROBE_DISPLAY_NONE_JS = "() => { const h = document.getElementById('fk-probe-host'); const r = h.shadowRoot || h; for (const s of r.querySelectorAll('span')) s.style.setProperty('display','none','important'); void document.documentElement.offsetHeight; return new Promise(res => requestAnimationFrame(() => requestAnimationFrame(res))); }"


def _family_css(name: str) -> str:
    return '"' + name.replace('"', '\\"') + '"'


class PlaywrightBackend:
    """Chromium via Playwright screenshots (D6). probe_placement: shadow (real) | body-unsafe | off |
    display-none (the last three are selftest fixtures)."""

    def __init__(self, run_id: str, probe_placement: str = "shadow"):
        self.run_id = run_id
        self.placement = probe_placement
        self.report = LoadReport()
        self.page_dir: Path | None = None
        self.page_path: Path | None = None
        self.first_hashes: dict[str, str] = {}
        self.errors: list[str] = []
        self.new_blocked: list[str] = []
        self.failed_requests: list[str] = []
        self._live = 0
        self._pw = None
        self.browser = None
        self.page = None
        self._fams: dict[str, dict] = {}       # family -> {"lists":..., "moments": [...]}
        self._baselines: dict | None = None
        self._deferred_remove = 0
        self.chromium_version = None
        self.gpu = False                 # set by the caller before open(); True = hardware GPU flags
        self.webgl_renderer = None       # UNMASKED_RENDERER_WEBGL seen by a blank page, or None

    # -- request policy (FK-INV-9)
    def _route(self, route):
        url = route.request.url
        if url.startswith("file:"):
            try:
                p = Path(url2pathname(urlparse(url).path)).resolve()
                rel = p.relative_to(self.page_dir)
            except (ValueError, OSError):
                rel = None
            if rel is not None:
                rp = rel.as_posix()
                if rp not in self.report.local_files:
                    self.report.local_files.append(rp)
                    if p.is_file():
                        self.first_hashes[rp] = sha256_file(p)
                route.continue_()
                return
        self.report.blocked_requests.append(one_line(url, 300))
        self.new_blocked.append(url)
        route.abort()

    def _on_console(self, msg):
        if len(self.report.console) < CONSOLE_CAP:
            self.report.console.append(f"{msg.type}: {msg.text}"[:CONSOLE_CHARS])
        else:
            self.report.console_truncated = True

    def _on_failed(self, req):
        # The DevTools CSS agent used by the font probe re-fetches the page document (type "other"); that
        # internal fetch fails with "origin" and is not a page request.
        if req.resource_type == "other" and self.page_path is not None and req.url == self.page_path.as_uri():
            return
        if req.url.startswith("file:") and req.url not in self.new_blocked:
            self.failed_requests.append(f"{req.url} ({req.failure})")

    def open(self, page_path: Path, width: int, height: int) -> None:
        from playwright.sync_api import sync_playwright
        self.page_path = Path(page_path).resolve()
        self.page_dir = self.page_path.parent
        try:
            self._pw = sync_playwright().start()
            # Python owns the browser's lifetime: the driver must not close Chromium on the console's Ctrl-C
            gpu_args = (["--use-angle=d3d11", "--enable-gpu", "--ignore-gpu-blocklist", "--force_high_performance_gpu"]
                        if self.gpu else [])
            self.browser = self._pw.chromium.launch(handle_sigint=False, handle_sigterm=False, handle_sighup=False,
                                                    args=gpu_args)
        except Exception as e:
            raise EnvError(f"Chromium did not start: {one_line(e, 200)}")
        self.chromium_version = self.browser.version
        self.webgl_renderer = self._probe_webgl_renderer()
        ctx = self.browser.new_context(viewport={"width": width, "height": height}, device_scale_factor=1)
        ctx.route("**/*", self._route)
        self.page = ctx.new_page()
        self.page.on("pageerror", lambda e: self.errors.append(one_line(f"{e}", 400)))
        self.page.on("crash", lambda *_: self.errors.append("page crashed"))
        self.page.on("console", self._on_console)
        self.page.on("requestfailed", self._on_failed)

    def _probe_webgl_renderer(self):
        """Which adapter WebGL lands on, read from a throwaway blank page (never the film page)."""
        try:
            pg = self.browser.new_page()
            try:
                return pg.evaluate("""() => { const c = document.createElement('canvas');
                    const g = c.getContext('webgl2') || c.getContext('webgl');
                    if (!g) return 'no-webgl';
                    const d = g.getExtension('WEBGL_debug_renderer_info');
                    return d ? g.getParameter(d.UNMASKED_RENDERER_WEBGL) : g.getParameter(g.RENDERER); }""")
            finally:
                pg.close()
        except Exception:
            return None

    def check_requests(self, where: str) -> None:
        if self.new_blocked:
            url = self.new_blocked[0]
            raise AssetLoad(f"request blocked ({where}): {one_line(url, 200)} (outside the page folder)")
        if self.failed_requests:
            raise AssetLoad(f"request failed ({where}): {one_line(self.failed_requests[0], 200)}")

    def check_errors(self, where: str) -> None:
        if self.errors:
            raise PageRuntime(f"page error ({where}): {self.errors[0]}")

    def load(self, ready_timeout_s: float) -> LoadReport:
        from playwright.sync_api import Error as PwError
        try:
            self.page.goto(self.page_path.as_uri(), wait_until="load", timeout=max(1.0, ready_timeout_s) * 1000)
        except PwError as e:
            self.check_errors("frame: loading")
            self.check_requests("frame: loading")
            if "Timeout" in str(e):
                raise NotReady(f"page did not reach 'load' within {ready_timeout_s:g} s", ready_timeout_s=ready_timeout_s)
            raise PageRuntime(f"page load failed (frame: loading): {one_line(e, 200)}")
        fonts = self.page.evaluate(_FONTS_JS)
        self.report.fonts = [FontLoad(f, src, "loaded" if st == "loaded" else "error") for f, st, src in fonts]
        # page errors are read after the __ready step: a rejected __ready also raises an unhandled-rejection
        # pageerror, and the ready outcome is the more specific kind (not_ready)
        bad = [f for f in self.report.fonts if f.status != "loaded"]
        if bad:
            raise AssetLoad(f"font failed: {bad[0].family} ({one_line(bad[0].src, 150) or 'no src'}) (status error)")
        self.check_requests("frame: loading")
        shape = self.page.evaluate(_READY_SHAPE_JS)
        self.report.ready_shape = shape
        ms = int(ready_timeout_s * 1000)
        if shape == "promise":
            r = self.page.evaluate(
                "(ms) => Promise.race([window.__ready.then(() => 'ok', e => 'rejected:' + (e && e.message || String(e))),"
                " new Promise(r => setTimeout(() => r('timeout'), ms))])", ms)
            if r == "timeout":
                raise NotReady(f"window.__ready did not settle within {ready_timeout_s:g} s", ready_timeout_s=ready_timeout_s)
            if r.startswith("rejected:"):
                raise NotReady(f"window.__ready rejected: {one_line(r[9:], 200)}", ready_timeout_s=ready_timeout_s)
        elif shape == "flag":
            ok = self.page.evaluate(
                "(ms) => new Promise(r => { const t0 = performance.now(); (function poll() {"
                " if (window.__ready === true) return r(true); if (performance.now() - t0 > ms) return r(false);"
                " setTimeout(poll, 50); })(); })", ms)
            if not ok:
                raise NotReady(f"window.__ready stayed false for {ready_timeout_s:g} s", ready_timeout_s=ready_timeout_s)
        else:
            self.page.evaluate("() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))")
        self.check_errors("frame: loading")
        self.check_requests("frame: loading")
        if not self.page.evaluate("() => typeof window.__setTime === 'function'"):
            raise PageContract("page has no window.__setTime")
        return self.report

    def seek(self, t: Fraction) -> None:
        from playwright.sync_api import Error as PwError
        try:
            r = self.page.evaluate(_SEEK_JS, float(t))
        except PwError as e:
            raise PageRuntime(f"page failed at t={float(t):.6g} s: {one_line(e, 200)}")
        if r.get("error"):
            raise PageRuntime(f"__setTime threw at t={float(t):.6g} s: {one_line(r['error'], 300)}")
        self._live = int(r.get("live") or 0)

    def snapshot(self) -> bytes:
        from playwright.sync_api import Error as PwError
        try:
            png = self.page.screenshot(type="png", timeout=30000)
        except PwError as e:
            raise PageRuntime(f"screenshot failed: {one_line(e, 200)}")
        if self._deferred_remove:
            self._deferred_remove -= 1
            if not self._deferred_remove:
                self.page.evaluate(_PROBE_REMOVE_JS)
        return png

    def live_animations(self) -> int:
        return self._live

    # -- font fingerprint (SG-12 v4.2, Q-1, Q-7, R-5)
    def _probe_lists(self, families: list[str], need_baseline: bool) -> tuple[dict, dict | None]:
        sentinel = f"fk-missing-{self.run_id}"
        probes, keys = [], []
        targets = ([sentinel] if need_baseline else []) + families
        for fi, fam in enumerate(targets):
            for script, text in PROBE_TEXT.items():
                for fb in FALLBACKS:
                    pid = f"fkp-{fi}-{script}-{fb}"
                    probes.append([pid, f"{_family_css(fam)}, {fb}", text])
                    keys.append((fam, script, fb, pid))
        self.page.evaluate(_PROBE_INSERT_JS, [probes, "body-unsafe" if self.placement == "body-unsafe" else "shadow"])
        if self.placement == "display-none":
            self.page.evaluate(_PROBE_DISPLAY_NONE_JS)
        cdp = self.page.context.new_cdp_session(self.page)
        try:
            cdp.send("DOM.enable")
            cdp.send("CSS.enable")
            doc = cdp.send("DOM.getDocument", {"depth": -1, "pierce": True})
            ids = {}

            def walk(node):
                a = node.get("attributes") or []
                for i in range(0, len(a), 2):
                    if a[i] == "id" and a[i + 1].startswith("fkp-"):
                        ids[a[i + 1]] = node["nodeId"]
                for k in ("children", "shadowRoots"):
                    for c in node.get(k) or []:
                        walk(c)
                if node.get("contentDocument"):
                    walk(node["contentDocument"])
            walk(doc["root"])
            raw: dict = {}
            for fam, script, fb, pid in keys:
                fonts = []
                if pid in ids:
                    fonts = cdp.send("CSS.getPlatformFontsForNode", {"nodeId": ids[pid]}).get("fonts", [])
                raw.setdefault(fam, {}).setdefault(script, {})[fb] = sorted({f["familyName"] for f in fonts})
        finally:
            try:
                cdp.detach()
            except Exception:
                pass
            if self.placement == "body-unsafe":
                self._deferred_remove = 2        # fixture: host stays through the next frame's __setTime
            else:
                self.page.evaluate(_PROBE_REMOVE_JS)
        base = raw.pop(sentinel) if need_baseline else None
        return raw, base

    def sample_font_families(self, moment: str) -> list[FamilyCheck]:
        if self.placement == "off":
            return []
        values = self.page.evaluate(_FAMILIES_JS)
        seen = []
        for v in values:
            f = first_family(v)
            if f and f not in seen:
                seen.append(f)
        new = [f for f in seen if f not in self._fams]
        if new or (seen and self._baselines is None):
            raw, base = self._probe_lists(new, self._baselines is None)
            if base is not None:
                self._baselines = base
            for f in new:
                self._fams[f] = {"lists": raw[f], "moments": []}
        out = []
        for f in seen:
            self._fams[f]["moments"].append(moment)
            try:
                out.append(decide_family(f, self._fams[f]["lists"], self._baselines, tuple(self._fams[f]["moments"])))
            except ValueError as e:
                raise Internal(f"font probe for {f}: {e}")
        return out

    def close(self) -> None:
        try:
            if self.browser:
                self.browser.close()
        except BaseException:
            pass
        try:
            if self._pw:
                self._pw.stop()
        except BaseException:
            pass

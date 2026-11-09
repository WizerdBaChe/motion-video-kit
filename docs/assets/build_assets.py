"""Regenerate every README image of motion-video-kit.

Usage (repo root):
  python -X utf8 docs/assets/build_assets.py --only flow               flow.build.mjs selftest + build for both languages,
                                                                         browser text-fit check, flow.<lang>.png (@2x)
  python -X utf8 docs/assets/build_assets.py --only core               core-director-sheet.png, core-storyboard.png
                                                                         (runs the SHIPPED tools/timeline/tl.py and the
                                                                         shipped example page; see build_core.py)
  python -X utf8 docs/assets/build_assets.py --only showcase --src DIR the five showcase GIFs from the release MP4s in DIR
                                                                         (see build_showcase.py)
  python -X utf8 docs/assets/build_assets.py --src DIR                 all of the above

Needs: Python 3.12, `pip install playwright pillow`, `playwright install chromium`, Node.js (standard library only),
ffmpeg on PATH (showcase). Offline: nothing touches the network. Fonts: the pages use locally installed CJK fonts
(Noto Sans TC or Microsoft JhengHei); without one the type differs, the content does not.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
LANGS = ("zh-TW", "en")

# text sits inside its node: the browser's own box of every <text> against the rect of its group
FIT_JS = """() => {
  const bad = [];
  for (const g of document.querySelectorAll('[data-node]')) {
    const r = g.querySelector('rect').getBoundingClientRect();
    for (const t of g.querySelectorAll('text')) {
      const a = t.getBoundingClientRect();
      if (a.left < r.left + 4 || a.right > r.right - 4 || a.top < r.top || a.bottom > r.bottom) bad.push(g.dataset.node);
    }
  }
  return bad;
}"""


def sh(cmd: list[str]) -> str:
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if p.returncode != 0:
        sys.exit(f"STOP: {' '.join(cmd[:3])} -> exit {p.returncode}\n{p.stdout}{p.stderr}")
    return p.stdout


def flow() -> None:
    from playwright.sync_api import sync_playwright
    print(sh(["node", str(HERE / "flow.build.mjs"), "--selftest"]).strip())
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        for lang in LANGS:
            print(sh(["node", str(HERE / "flow.build.mjs"), "--lang", lang]).strip())
            svg = HERE / f"flow.{lang}.svg"
            pg = b.new_page(viewport={"width": 1500, "height": 700}, device_scale_factor=2)
            pg.set_content(f'<body style="margin:0">{svg.read_text(encoding="utf-8")}</body>')
            pg.wait_for_timeout(300)
            bad = pg.evaluate(FIT_JS)
            if bad:
                sys.exit(f"STOP: browser text-fit check failed for {lang}: {bad}")
            # a known-bad copy must fail the same check (positive control of the check itself)
            pg.evaluate("document.querySelector('[data-node=n1] text').setAttribute('font-size','60')")
            if not pg.evaluate(FIT_JS):
                sys.exit("STOP: the text-fit check did not fire on a deliberately oversized label")
            pg.set_content(f'<body style="margin:0">{svg.read_text(encoding="utf-8")}</body>')
            pg.wait_for_timeout(200)
            pg.locator("svg").screenshot(path=str(HERE / f"flow.{lang}.png"))
            print(f"flow.{lang}.png written; text-fit: 0 overflow, positive control fired")
            pg.close()
        b.close()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", choices=["flow", "core", "showcase"])
    ap.add_argument("--src", type=Path, help="folder with the showcase MP4s (release assets)")
    a = ap.parse_args()
    todo = [a.only] if a.only else ["flow", "core"] + (["showcase"] if a.src else [])
    if "flow" in todo:
        flow()
    if "core" in todo:
        print(sh([sys.executable, "-X", "utf8", str(HERE / "build_core.py")]).strip())
    if "showcase" in todo:
        if not a.src:
            ap.error("--only showcase needs --src")
        print(sh([sys.executable, "-X", "utf8", str(HERE / "build_showcase.py"), "--src", str(a.src)]).strip())
    return 0


if __name__ == "__main__":
    sys.exit(main())

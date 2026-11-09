"""Edit route CLI (docs/edit-route-design.md). A film folder holds assets/, edit/*.otio and build/.

    python -X utf8 tools/edit/edit.py register <film> <file> --id ID --source footage|motion --field k=v ...
    python -X utf8 tools/edit/edit.py gen <film> --adapter mock --id ID --prompt "..." [--seed N --seconds S --kind video|image --size WxH]
    python -X utf8 tools/edit/edit.py verify <film> [ID ...]
    python -X utf8 tools/edit/edit.py beatcut <film> --music ID --clips ID,ID,.. --out edit/x.otio [--beats-per-cut 2 --duration S --fps 30]
    python -X utf8 tools/edit/edit.py render <film> <edl.otio> -o build/x.mp4 [--size 1280x720 --profile lab-round]
    python -X utf8 tools/edit/edit.py verify-beat <video> [--edl <film>/edit/x.otio]   # --edl adds recall against the declared cuts
    python -X utf8 tools/edit/edit.py --selftest
Exit: 0 ok; 1 refused / problems found; 2 usage.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import assets as A  # noqa: E402


def main():
    if "--selftest" in sys.argv:
        import selftest
        return selftest.main()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("register"); p.add_argument("film"); p.add_argument("file"); p.add_argument("--id", required=True)
    p.add_argument("--source", required=True, choices=["footage", "motion"]); p.add_argument("--field", action="append", default=[])
    p = sub.add_parser("gen"); p.add_argument("film"); p.add_argument("--adapter", default="mock"); p.add_argument("--id", required=True)
    p.add_argument("--prompt", required=True); p.add_argument("--seed", type=int); p.add_argument("--seconds", type=float, default=2.0)
    p.add_argument("--kind", default="video", choices=["video", "image"]); p.add_argument("--size", default="1280x720")
    p.add_argument("--fps", type=int, default=30); p.add_argument("--input", action="append", default=[])
    p = sub.add_parser("verify"); p.add_argument("film"); p.add_argument("ids", nargs="*")
    p = sub.add_parser("beatcut"); p.add_argument("film"); p.add_argument("--music", required=True)
    p.add_argument("--clips", required=True); p.add_argument("--out", required=True)
    p.add_argument("--beats-per-cut", type=int, default=2); p.add_argument("--duration", type=float)
    p.add_argument("--fps", type=int, default=30); p.add_argument("--shift", type=float, default=0.0)
    p = sub.add_parser("render"); p.add_argument("film"); p.add_argument("edl"); p.add_argument("-o", "--out", required=True)
    p.add_argument("--size", default="1280x720"); p.add_argument("--profile", default="lab-round")
    p = sub.add_parser("verify-beat"); p.add_argument("video"); p.add_argument("--fps", type=int, default=30)
    p.add_argument("--edl")
    a = ap.parse_args()

    if a.cmd == "register":
        fields = dict(f.split("=", 1) for f in a.field)
        print(json.dumps(A.register(a.film, a.file, a.id, a.source, fields), ensure_ascii=False, indent=1))
    elif a.cmd == "gen":
        from adapters import ADAPTERS, Request
        rec = ADAPTERS[a.adapter]().generate(a.film, Request(asset_id=a.id, prompt=a.prompt, kind=a.kind, seconds=a.seconds,
                                                             size=a.size, fps=a.fps, seed=a.seed, inputs=a.input))
        print(json.dumps(rec, ensure_ascii=False, indent=1))
    elif a.cmd == "verify":
        ids = a.ids or sorted(p.name[:-len(".provenance.json")] for p in (Path(a.film) / "assets").glob("*.provenance.json"))
        probs = [x for i in ids for x in A.verify(a.film, i)]
        print("\n".join(probs) or f"{len(ids)} assets ok")
        return 1 if probs else 0
    elif a.cmd == "beatcut":
        import beatcut
        out = Path(a.film) / a.out if not Path(a.out).is_absolute() else Path(a.out)
        info = beatcut.beatcut(a.film, a.music, a.clips.split(","), out, fps=a.fps, beats_per_cut=a.beats_per_cut,
                               duration_s=a.duration, shift_s=a.shift)
        print(f"{out}: {len(info['declared_cuts_s'])} cuts, {info['grid']['bpm']:.2f} BPM")
    elif a.cmd == "render":
        import render
        film = Path(a.film)
        edl = Path(a.edl) if Path(a.edl).is_absolute() else film / a.edl
        out = Path(a.out) if Path(a.out).is_absolute() else film / a.out
        try:
            rec = render.render(film, edl, out, size=a.size, profile=a.profile)
        except render.Refused as e:
            print(f"refused: {e}")
            return 1
        print(f"{out}: {rec['total_frames']} frames, check {json.dumps(rec['check'])[:200]}")
        return 0 if (rec["check"] or {}).get("exit") == 0 else 1
    elif a.cmd == "verify-beat":
        import beatcut
        declared = None
        if a.edl:
            declared = json.loads(Path(a.edl).read_text(encoding="utf-8"))["metadata"]["mvl"]["beatcut"]["declared_cuts_s"]
        print(json.dumps(beatcut.verify(a.video, a.fps, declared), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())

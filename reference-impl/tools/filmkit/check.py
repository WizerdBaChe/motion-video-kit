"""filmkit check.py: state facts about one MP4 (CheckRun). Writes check.json, check.md, sheet_1fps.png beside it."""
from __future__ import annotations

import sys
from pathlib import Path

KIT = Path(__file__).resolve().parent
if str(KIT) not in sys.path:
    sys.path.insert(0, str(KIT))

import argparse
import json
import re
import time

from _fk import kinds
from _fk.checkrun import CheckArgs, check_run
from _fk.common import FilmkitError, FkArgParser, SpecInvalid, last_line, one_line
from _fk.profile import get_profile
from _fk.spec import SIZE_RE
from _fk.summary import audio_desc, exit_code, five_lines
from _fk.types import RunSummary

EPILOG = """example:
  python -X utf8 kit/filmkit/check.py build/final.mp4 --duration 30 --size 1280x720 --audio-expected yes

Exit codes: 0 no blocking row; 2 a blocking row; 3 some rows could not finish; 1 the check could not run.
Expected values not given make the matching rows "undetermined". Pixels and quality are not judged."""


def build_parser():
    p = FkArgParser(prog="check.py", formatter_class=argparse.RawDescriptionHelpFormatter, epilog=EPILOG,
                    description="State facts about one MP4 against expected values; write check.json, check.md and "
                                "sheet_1fps.png next to it. Never changes the file.")
    p.add_argument("file", help="the video file to check")
    p.add_argument("--duration", type=float, metavar="S", help="expected duration in seconds")
    p.add_argument("--size", metavar="WxH", help="expected frame size, e.g. 1280x720")
    p.add_argument("--fps", type=int, metavar="N", help="expected frame rate (default: the profile's, 30)")
    p.add_argument("--profile", default="lab-round", metavar="NAME", help="format profile (default lab-round)")
    p.add_argument("--audio-expected", choices=["yes", "no"], help="whether an audio stream is expected")
    p.add_argument("--plan", metavar="F", help="film_plan.json: expected values and declared exemptions")
    p.add_argument("--plan-exemptions-only", action="store_true",
                   help="read only the declaration fields of --plan, never its expected values")
    p.add_argument("--render-record", metavar="F", help="render.json to read (default: render.json beside the file)")
    p.add_argument("--mounted-kit-hash", metavar="H|none", help="kit hash the round mounted, or none")
    p.add_argument("--out-prefix", default="", metavar="P", help="prefix for the three output names, e.g. lab.")
    p.add_argument("--rules", metavar="F", help="rules file (lab side); evaluated and hashed")
    p.add_argument("--film-type", metavar="T", help="film type slug; picks the rules that apply")
    p.add_argument("--target", metavar="NAME", help="loudness target in the --rules file to compare with (needs --rules)")
    p.add_argument("--check-timeout", type=float, metavar="S", help="seconds for the whole check (default: profile)")
    p.add_argument("--json", action="store_true", help="print the check.json document instead of five lines")
    return p


def _emit(lines, as_json, doc):
    if as_json:
        print(json.dumps(doc, ensure_ascii=False))
    else:
        for ln in lines:
            print(ln)
    sys.stdout.flush()


def _fail(kind, message, hint, as_json, file="", notes=()):
    msg, h = kinds.render(kind, message, hint)
    st = RunSummary("FAILED", kind, h, None, None, None, None, None, None, None, (("probe", False),), file, False,
                    message=msg, notes=tuple(notes))
    _emit(five_lines(st, None), as_json, {"status": "rejected", "kind": kind, "message": msg, "hint": h, "exit_code": 1})
    return 1


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    as_json = "--json" in argv
    try:
        ns = build_parser().parse_args(argv)
        size = None
        if ns.size is not None:
            m = SIZE_RE.match(ns.size)
            if not m:
                raise SpecInvalid(f"size {ns.size!r} is not WxH", hint="give --size as WxH, e.g. 1280x720")
            size = (int(m.group(1)), int(m.group(2)))
        prof = get_profile(ns.profile)
        if ns.target is not None and not ns.rules:
            raise SpecInvalid("--target given without --rules", hint="give --rules <rules file> too, or drop --target")
    except FilmkitError as e:
        return _fail(e.kind, e.message, e.hint, as_json)
    mk = ns.mounted_kit_hash
    if mk is not None and mk != "none" and not re.fullmatch(r"[0-9a-f]{64}", mk):
        return _fail("spec_invalid", f"--mounted-kit-hash {mk!r} is neither none nor a 64-digit hex hash",
                     "give the kit hash the round mounted, or none", as_json)
    args = CheckArgs(file=Path(ns.file), duration_s=ns.duration, size=size, fps=ns.fps, profile=ns.profile,
                     audio_expected=None if ns.audio_expected is None else ns.audio_expected == "yes",
                     plan=Path(ns.plan) if ns.plan else None, plan_exemptions_only=ns.plan_exemptions_only,
                     render_record=Path(ns.render_record) if ns.render_record else None,
                     mounted_kit_hash=mk, out_prefix=ns.out_prefix, rules=Path(ns.rules) if ns.rules else None,
                     film_type=ns.film_type,
                     check_timeout_s=ns.check_timeout if ns.check_timeout is not None else float(prof["timeouts_s"]["check"]),
                     json_out=ns.json, target=ns.target)
    try:
        res = check_run(args, time.monotonic() + args.check_timeout_s)
    except FilmkitError as e:
        return _fail(e.kind, e.message, e.hint, as_json, ns.file)
    except KeyboardInterrupt:
        return _fail("interrupted", "check interrupted", None, as_json, ns.file)
    except Exception as e:
        return _fail("internal", last_line(e), None, as_json, ns.file)
    pr = (res.check_json or {}).get("probe") or {}
    disp = Path(ns.file).parent.as_posix()
    st = RunSummary("CHECKED", None, None, pr.get("n_frames"), pr.get("video_duration_s"), pr.get("width"),
                    pr.get("height"), pr.get("video_codec"), pr.get("pix_fmt"), audio_desc(pr.get("audio")),
                    (("probe", True), ("judge", True), ("report", res.check_json is not None), ("sheet", res.sheet.ok)),
                    ns.file, True, fps=pr.get("fps_avg"), display_dir="" if disp in ("", ".") else disp + "/")
    code = exit_code(st, res)
    _emit(five_lines(st, res), as_json, res.check_json if res.check_json is not None else
          {"status": "checked", "summary": res.summary.to_json(), "exit_code": code})
    return code


if __name__ == "__main__":
    sys.exit(main())

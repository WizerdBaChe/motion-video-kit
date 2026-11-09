"""Timeline layer CLI (PSM 5.1). Format and timing checked; pictures not judged.

python -X utf8 tools/timeline/tl.py <validate --static|validate --timed|resolve|view|approve|at|mark|index> ...
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # works under python -I (PSM 3.1, P-7)

import contextlib  # noqa: E402
import io  # noqa: E402
import json  # noqa: E402

from _tl import approve as AP  # noqa: E402
from _tl import at as AT  # noqa: E402
from _tl import components as C  # noqa: E402
from _tl import currency as CU  # noqa: E402
from _tl import model as M  # noqa: E402
from _tl import readback as RB  # noqa: E402
from _tl import resolve as R  # noqa: E402
from _tl import state as S  # noqa: E402
from _tl import validate_static as VS  # noqa: E402
from _tl import validate_timed as VT  # noqa: E402
from _tl.common import (EXIT_BLOCKING, EXIT_INCOMPLETE, EXIT_OK, EXIT_REFUSED, Internal, NotCurrent, Outcome,  # noqa: E402
                        SpecInvalid, TlArgParser, TlError, clean_tmp, dumps, film_write, last_line, posix, read_json)
from _tl.lock import FilmLock  # noqa: E402
from _tl.nhash import file_nsha  # noqa: E402
from _tl.rules import DEFAULT_RULES, load_rules  # noqa: E402
from _tl.view import render_view  # noqa: E402

LIB = Path(__file__).resolve().parent
TL0_COMMANDS = ["validate", "resolve", "view", "approve", "at", "mark", "readback", "index"]  # readback: works W-5


def build_parser():
    p = TlArgParser(prog="tl.py", description="Timeline layer: one file holds the film's decisions and timing; "
                    "checked and resolved by a program; shown as a page. Format and timing checked; pictures not judged.")
    sub = p.add_subparsers(dest="cmd", metavar="{" + ",".join(TL0_COMMANDS) + "}")

    def common(sp):
        sp.add_argument("--rules", default=None, help=f"shared rules file (default {posix(DEFAULT_RULES)}; missing is not an error)")
        sp.add_argument("--components", default=None, help="component library folder (default tools/timeline/components)")
        sp.add_argument("--json", action="store_true", help="print one JSON document instead of five lines")

    sp = sub.add_parser("validate", help="static or timed rows; writes build/validate.json")
    sp.add_argument("film")
    g = sp.add_mutually_exclusive_group(required=True)
    g.add_argument("--static", action="store_true")
    g.add_argument("--timed", action="store_true")
    common(sp)
    sp = sub.add_parser("resolve", help="writes build/timeline.resolved.json")
    sp.add_argument("film")
    common(sp)
    sp = sub.add_parser("view", help="writes build/timeline.html")
    sp.add_argument("film")
    common(sp)
    sp = sub.add_parser("approve", help="writes versions/<n>/ and state.json")
    sp.add_argument("film")
    sp.add_argument("--by", choices=["user", "model"], required=True)
    sp.add_argument("--note", default=None, help="the user's words (required with --by user)")
    sp.add_argument("--questions", default=None, help="build/questions.md (required with --by model)")
    common(sp)
    sp = sub.add_parser("at", help="read-only: which clip and line at <seconds>")
    sp.add_argument("film")
    sp.add_argument("seconds", type=float)
    sp.add_argument("--version", type=int, default=None)
    common(sp)
    sp = sub.add_parser("mark", help="state event: --abandoned")
    sp.add_argument("film")
    sp.add_argument("--abandoned", action="store_true", required=True)
    sp.add_argument("--version", type=int, default=None)
    sp.add_argument("--note", required=True)
    common(sp)
    sp = sub.add_parser("readback", help="diff versions <n> and <m>; appends 作者修改紀錄.md")
    sp.add_argument("film")
    sp.add_argument("n", type=int)
    sp.add_argument("m", type=int)
    common(sp)
    sp = sub.add_parser("index", help="rebuild components/INDEX.md and index.json; --check exits 1 when stale")
    sp.add_argument("--check", action="store_true")
    common(sp)
    return p


def subcommands(parser) -> list[str]:
    for a in parser._actions:  # argparse keeps sub-parsers in a _SubParsersAction
        if a.__class__.__name__ == "_SubParsersAction":
            return list(a.choices)
    return []


# ---------------------------------------------------------------- shared preamble
class Ctx:
    def __init__(self, ns, out: Outcome):
        self.ns = ns
        self.out = out
        self.film = Path(ns.film)
        self.rules = load_rules(Path(ns.rules) if ns.rules else None)
        self.comp_dir = Path(ns.components) if ns.components else C.LIB_COMPONENTS
        self.index = C.load_index(self.comp_dir)
        self.state = None
        self.cur = None

    def open(self):
        if not (self.film / "film.timeline.json").is_file():
            raise SpecInvalid(f"no film.timeline.json in {posix(self.film)}", hint="check the film folder path")
        self.out.notes += clean_tmp(self.film)
        self.state = S.load_state(self.film)
        before = json.dumps(self.state, sort_keys=True)
        self.out.notes += S.recover(self.film, self.state)
        if json.dumps(self.state, sort_keys=True) != before:
            S.save_state(self.film, self.state)
        S.verify_versions(self.film, self.state)
        self.cur = VS.current_inputs(self.film, self.rules, self.index)
        self.out.notes += S.sync_draft(self.state, self.cur)

    def close_state(self):
        S.refresh(self.state, CU.is_valid(self.film, self.cur))
        S.save_state(self.film, self.state)
        d = self.state.get("draft")
        if d:
            self.out.notes.append(f"draft {d['n']}: {d['state']}")

    def timeline(self) -> dict:
        return M.require_obj(read_json(self.film / "film.timeline.json"))


def _check_line(summary: dict, path: str) -> str:
    return (f"Check: {summary.get('blocking', 0)} blocking, {summary.get('look', 0)} need a look, "
            f"{summary.get('undetermined', 0)} undetermined — {path}")


def _exit_for(summary: dict, rows: list) -> int:
    if summary.get("blocking"):
        return EXIT_BLOCKING
    if any(r["bucket"] == "undetermined" and (r.get("reason") or "").startswith("evaluator error") for r in rows):
        return EXIT_INCOMPLETE
    return EXIT_OK


# ---------------------------------------------------------------- commands
def cmd_validate_static(ctx: Ctx, out: Outcome):
    out.command = "validate --static"
    res = VS.run_static(ctx.film, ctx.rules, ctx.index)
    written = VS.write_outputs(ctx.film, res)
    r = res["result"]
    s = r["static"]["summary"]
    out.steps = [("schema", True), ("assets", True), ("uses", True), ("components", True), ("rows", True),
                 ("candidates", True)]
    if any("later checks not run" in n for n in r["notes"]):
        out.steps = [("schema" if "schema" in " ".join(r["notes"]) else "assets", False)]
    out.result_line = f"{s['blocking']} blocking, {s['look']} need a look, {s['info']} info, {s['undetermined']} undetermined"
    out.check_line = _check_line(s, posix(ctx.film / "build" / "validate.json"))
    out.notes += r["notes"]
    if r["defaults_applied"]:
        out.notes.append("defaults applied: " + ", ".join(r["defaults_applied"]))
    if r["decisions_unset"]:
        out.notes.append("decisions unset: " + ", ".join(r["decisions_unset"]))
    if s["blocking"] == 0:
        out.notes.append(f"next: tl.py resolve {posix(ctx.film)}")
    out.outputs = {"validate": posix(ctx.film / "build" / "validate.json"), "written": written}
    out.summary = s
    out.result = r
    out.exit_code = _exit_for(s, r["static"]["rows"])


def cmd_resolve(ctx: Ctx, out: Outcome):
    CU.static_ok(ctx.film, ctx.cur)
    obj = ctx.timeline()
    t = M.tracks(obj)
    lj = M.lines_json_obj(ctx.film)
    if lj is not None:
        bad = M.validate_lines_json(lj, [ln["id"] for ln in t["narration"]])
        if bad:
            raise SpecInvalid(f"voice/lines.json: {bad[0]['measured']}", hint="fix voice/lines.json (PSM 4.4)")
    src = R.line_durations(t["narration"], lj)
    inputs = {k: ctx.cur[k] for k in CU.RESOLVED_FIELDS}
    res = R.resolve(ctx.film, obj, src, inputs=inputs)
    p = ctx.film / "build" / "timeline.resolved.json"
    film_write(ctx.film, p, dumps(res))
    est = sum(1 for ln in res["lines"] if ln["estimated"])
    out.steps = [("narration", True), ("anchors", True), ("snap", True), ("film length", True), ("gap fill", True)]
    out.result_line = (f"film end {res['film_end_s']:.6g} s, {res['n_frames']} frames, {len(res['picture'])} picture clips, "
                       f"{len(res['lines'])} lines ({est} estimated), {len(res['extensions'])} extension(s)")
    out.check_line = "Check: not run (resolve writes times; run validate --timed)"
    out.notes += res["notes"]
    out.notes.append(f"next: tl.py validate --timed {posix(ctx.film)}")
    out.outputs = {"resolved": posix(p)}
    out.result = res
    S.stamp(ctx.state, "resolve", inputs)


def cmd_validate_timed(ctx: Ctx, out: Outcome):
    out.command = "validate --timed"
    v = CU.static_ok(ctx.film, ctx.cur)
    res = CU.resolved_ok(ctx.film, ctx.cur)
    obj = ctx.timeline()
    tm = VT.run_timed(ctx.film, res, obj, ctx.rules, ctx.index, execute_clips=False)
    v["stage"] = "timed"
    v["inputs"] = dict(v["inputs"], lines_nsha=ctx.cur["lines_nsha"],
                       resolved_nsha=file_nsha(ctx.film / "build" / "timeline.resolved.json"))
    v["timed"] = {"rows": tm["rows"], "summary": tm["summary"]}
    v["freedom_share"] = tm["freedom_share"]
    p = ctx.film / "build" / "validate.json"
    film_write(ctx.film, p, dumps(v))
    s = tm["summary"]
    out.steps = [("TV-2", True), ("TV-4b", True), ("TV-7", True), ("TV-10", True), ("TV-14", True), ("TV-19", True)]
    out.result_line = f"{s['blocking']} blocking, {s['look']} need a look, {s['info']} info, {s['undetermined']} undetermined"
    out.check_line = _check_line(s, posix(p))
    if s["blocking"] == 0:
        out.notes.append(f"next: tl.py view {posix(ctx.film)}")
    out.outputs = {"validate": posix(p)}
    out.summary = s
    out.result = v
    out.exit_code = _exit_for(s, tm["rows"])


def cmd_view(ctx: Ctx, out: Outcome):
    v, res = CU.timed_ok(ctx.film, ctx.cur)
    obj = ctx.timeline()
    S.refresh(ctx.state, CU.is_valid(ctx.film, ctx.cur))
    html = render_view(ctx.film, res, v, ctx.state, obj)
    p = ctx.film / "build" / "timeline.html"
    film_write(ctx.film, p, html)
    rows = (v.get("static") or {}).get("rows", []) + (v.get("timed") or {}).get("rows", [])
    s = {"blocking": sum(r["bucket"] == "blocking" for r in rows), "look": sum(r["bucket"] == "look" for r in rows),
         "undetermined": sum(r["bucket"] == "undetermined" for r in rows)}
    out.steps = [("read resolved", True), ("read validate", True), ("page", True)]
    out.result_line = f"page written ({len(res['picture'])} clips, {len(res['lines'])} lines)"
    out.check_line = _check_line(s, posix(ctx.film / "build" / "validate.json"))
    out.look_line = f"Look: {posix(p)} (pictures not judged by this tool)"
    out.outputs = {"page": posix(p)}
    out.summary = s


def cmd_approve(ctx: Ctx, out: Outcome):
    d = ctx.state.get("draft")
    S.refresh(ctx.state, CU.is_valid(ctx.film, ctx.cur))
    if not d or d["state"] != "VALID":
        try:
            CU.timed_ok(ctx.film, ctx.cur)
        except NotCurrent as e:
            raise NotCurrent(f"approve needs a VALID draft: {e.message}", hint=e.hint)
    v, res = CU.timed_ok(ctx.film, ctx.cur)
    obj = ctx.timeline()
    appr = AP.approve(ctx.film, by=ctx.ns.by, note=ctx.ns.note, questions=ctx.ns.questions, state=ctx.state, obj=obj,
                      resolved=res, validate=v, index=ctx.index, cur=ctx.cur)
    p = ctx.film / "versions" / str(appr["n"]) / "approval.json"
    rows = (v.get("static") or {}).get("rows", []) + (v.get("timed") or {}).get("rows", [])
    out.steps = [("currency", True), ("TV-18", True), ("copies", True), ("approval", True), ("state", True)]
    out.result_line = AP.line1(posix(ctx.film), appr)
    out.check_line = (f"Check: 0 blocking, {sum(r['bucket'] == 'look' for r in rows)} need a look, "
                      f"{len(appr['undetermined'])} undetermined — {posix(p)}")
    out.outputs = {"approval": posix(p)}
    out.result = appr
    S.stamp(ctx.state, "approve", dict(S.draft_inputs(ctx.cur), version=appr["n"], by=ctx.ns.by))


def cmd_mark(ctx: Ctx, out: Outcome):
    S.transition(ctx.state, "abandon", version=ctx.ns.version, note=ctx.ns.note)
    S.save_state(ctx.film, ctx.state)
    out.steps = [("state", True)]
    out.result_line = f"{'version ' + str(ctx.ns.version) if ctx.ns.version is not None else 'draft'} marked ABANDONED"
    out.outputs = {"state": posix(S.state_path(ctx.film))}


def cmd_readback(ns, out: Outcome):
    film = Path(ns.film)
    text, n_rows = RB.record(film, ns.n, ns.m)
    p = film / "作者修改紀錄.md"
    old = p.read_text(encoding="utf-8").rstrip() + "\n\n" if p.is_file() else f"# {film.name} 作者修改紀錄\n\n"
    with FilmLock(film):
        film_write(film, p, old + text)
    out.steps = [("versions", True), ("diff", True), ("record", True)]
    out.result_line = f"{n_rows} difference(s) between versions {ns.n} and {ns.m} appended"
    out.check_line = "Check: not a check (evidence for the main loop; fill 「整理出的規則」 by hand)"
    out.outputs = {"record": posix(p)}


def cmd_at(ns, out: Outcome):
    film = Path(ns.film)
    if ns.version is not None:
        p = film / "versions" / str(ns.version) / "timeline.resolved.json"
    else:
        p = film / "build" / "timeline.resolved.json"
    if not p.is_file():
        raise NotCurrent(f"{posix(p)} is missing", hint=f"run tl.py resolve {posix(film)}")
    res = read_json(p)
    ans = AT.at(res, ns.seconds)
    out.steps = [("read resolved", True), ("query", True)]
    out.result_line = AT.describe(ans)
    out.check_line = "Check: not run (read-only query)"
    if ns.version is None:
        try:
            rules = load_rules(Path(ns.rules) if ns.rules else None)
            index = C.load_index(Path(ns.components) if ns.components else C.LIB_COMPONENTS)
            cur = VS.current_inputs(film, rules, index)
            stale = [k for k in CU.RESOLVED_FIELDS if (res.get("inputs") or {}).get(k) != cur.get(k)]
            out.notes.append("resolved file is current" if not stale else f"resolved file is NOT current ({', '.join(stale)} changed)")
        except TlError as e:
            out.notes.append(f"currency unknown: {e.message}")
    else:
        out.notes.append(f"answered from versions/{ns.version}/")
    out.outputs = {"resolved": posix(p)}
    out.result = ans


def cmd_index(ns, out: Outcome):
    d = Path(ns.components) if ns.components else C.LIB_COMPONENTS
    with FilmLock(d):
        index, md = C.build_index(d)
        if ns.check:
            if not C.index_is_current(d, index, md):
                raise NotCurrent(f"component index is stale: {posix(d)}",
                                 hint=f"run tl.py index{'' if not ns.components else ' --components ' + posix(d)}")
            out.result_line = "index is current"
            out.check_line = "Check: index files compared"
        else:
            C.write_index(d, index, md)
            out.result_line = f"{len(index['components'])} component(s) indexed"
        out.steps = [("scan", True), ("validate", True), ("compare" if ns.check else "index", True)]
        out.outputs = {"index": posix(d / "index.json"), "md": posix(d / "INDEX.md")}
        out.result = index


def run(argv: list[str]) -> tuple[int, Outcome]:
    out = Outcome("tl")
    as_json = "--json" in argv
    try:
        ns = build_parser().parse_args(argv)
        if not ns.cmd:
            raise SpecInvalid("no sub-command given", hint="see: python -X utf8 tl.py --help")
        out.command = ns.cmd
        out.film = posix(ns.film) if hasattr(ns, "film") else ""
        if ns.cmd == "at":
            cmd_at(ns, out)
        elif ns.cmd == "readback":
            cmd_readback(ns, out)
        elif ns.cmd == "index":
            out.film = posix(ns.components) if ns.components else "components"
            cmd_index(ns, out)
        else:
            with FilmLock(Path(ns.film)):
                ctx = Ctx(ns, out)
                ctx.open()
                try:
                    if ns.cmd == "validate":
                        (cmd_validate_static if ns.static else cmd_validate_timed)(ctx, out)
                    elif ns.cmd == "resolve":
                        cmd_resolve(ctx, out)
                    elif ns.cmd == "view":
                        cmd_view(ctx, out)
                    elif ns.cmd == "approve":
                        cmd_approve(ctx, out)
                    elif ns.cmd == "mark":
                        cmd_mark(ctx, out)
                except NotCurrent:
                    # a refusal may still carry the state change it defines (VALID -> DRAFT on stale inputs)
                    ctx.close_state()
                    raise
                if ns.cmd != "mark":
                    ctx.close_state()
    except TlError as e:
        out.fail(e)
    except SystemExit as e:  # argparse --help
        raise e
    except Exception as e:  # noqa: BLE001
        out.fail(Internal(last_line(e)))
    return out.exit_code, out


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    code, out = run(argv)
    if "--json" in argv:
        print(json.dumps(out.json_doc(), ensure_ascii=False, indent=2))
    else:
        print("\n".join(out.lines()))
    return code


def run_captured(argv: list[str]) -> tuple[int, str, Outcome]:
    """Selftest helper: run in-process, capture stdout."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = main(argv)
    return code, buf.getvalue(), None


if __name__ == "__main__":
    sys.exit(main())

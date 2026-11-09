"""CheckRun orchestration: check.py, and in-process from render (PSM 5.3, 5.6).

Imports nothing from encode, mux, capture, record or transform_core (PSM 5.4).
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, replace
from pathlib import Path

from . import formal as fkformal, guard, judge as fkjudge, messages_zh, report, rerun as fkrerun, scan as fkscan
from . import sheet as fksheet
from .common import (FK_DIR, OutputForeign, SpecInvalid, fault_point, last_line, read_json, sha256_bytes,
                     sha256_file)
from .manifest import KIT_DIR, kit_hash
from .probe import probe
from .profile import get_profile
from .spec import build_expected_spec, load_plan
from .types import CheckResult, ExpectedSpec, OutputNames, ProbeFacts, ReportMeta, SheetResult


@dataclass(frozen=True)
class CheckArgs:                    # exactly the check.py flag set
    file: Path
    duration_s: float | None
    size: tuple | None
    fps: int | None
    profile: str
    audio_expected: bool | None
    plan: Path | None
    plan_exemptions_only: bool
    render_record: Path | None
    mounted_kit_hash: str | None
    out_prefix: str
    rules: Path | None
    film_type: str | None
    check_timeout_s: float
    json_out: bool
    rows_subset: frozenset | None = None   # Transform: format rows only
    target: str | None = None              # M3: name of a rules-file loudness target to compare with (FK-R-17)


def output_names(file: Path, prefix: str) -> OutputNames:
    """PSM 5.6: render output named by a same-folder render.json -> check.*; anything else -> <name>.check.*"""
    file = Path(file)
    rec, _ = guard.read_record(file.parent / "render.json")
    owned_name = None
    if rec is not None:
        owned_name = ((rec.get("last_success") or {}).get("output") or {}).get("name")
        if rec.get("pending_publish") and rec.get("output") == file.name:
            owned_name = file.name
    if owned_name == file.name:
        return OutputNames(f"{prefix}check.json", f"{prefix}check.md", f"{prefix}sheet_1fps.png")
    return OutputNames(f"{prefix}{file.name}.check.json", f"{prefix}{file.name}.check.md",
                       f"{prefix}{file.name}.sheet_1fps.png")


def check_ownership(folder: Path, names: OutputNames) -> None:
    """All three must be filmkit's (or absent) before anything is written; else output_foreign."""
    folder = Path(folder)
    j, m, s = folder / names.json, folder / names.md, folder / names.sheet
    owned_json = None
    if j.exists():
        obj, _ = read_json(j)
        if not obj or obj.get("generator") != "filmkit":
            raise OutputForeign(f"{names.json} exists and was not written by filmkit")
        owned_json = obj
    if m.exists():
        try:
            first = m.read_text(encoding="utf-8").split("\n", 1)[0]
        except (OSError, UnicodeDecodeError):
            first = ""
        if first != messages_zh.FIRST_LINE:
            raise OutputForeign(f"{names.md} exists and was not written by filmkit")
    if s.exists():
        if not owned_json or (owned_json.get("outputs") or {}).get("sheet") != names.sheet:
            raise OutputForeign(f"{names.sheet} exists and is not listed by a filmkit {names.json}")


def fallback_rows(reason: str, unfinished: bool = True) -> list[dict]:
    return [fkjudge.undet(rid, name, cat, reason, unfinished=unfinished) for rid, name, cat in fkjudge.ALL_ROW_IDS]

SCAN_WANT = {"black", "frozen", "silent", "astats", "first_frame"}


def _profile(name: str) -> dict:
    p = dict(get_profile(name))
    p["name"] = name
    return p


def format_rows(file: Path, spec: ExpectedSpec, profile_name: str, deadline: float) -> tuple[ProbeFacts, list[dict]]:
    """The format rows (FK-R-1..5) of one file against an expected spec: probe, judge, nothing written. Transform's
    VERIFYING uses it on the partial before publishing (PSM 6.8); no scan, no report, no sheet."""
    prof = _profile(profile_name)
    facts = probe(Path(file), deadline)
    judged = fkjudge.judge_full(facts, None, spec, None, "absent", None, None, None, prof, None, kit_hash(KIT_DIR), False)
    return facts, [r for r in judged["rows"] if r["category"] == "format"]


def check_run(args: CheckArgs, deadline: float, *, internal_error: str | None = None,
              kit_dir: Path = KIT_DIR, lock_held_by_other: bool | None = None) -> CheckResult:
    """lock_held_by_other: render passes False (the lock is its own); None = probe the folder lock, but only when a
    record says `running` (owner_state row 6)."""
    file = Path(args.file).resolve()
    if not file.is_file():
        raise SpecInvalid(f"file not found: {file.as_posix()}", hint="give the path of an existing video file")
    prof = _profile(args.profile)
    retry = prof.get("write_retry")
    names = output_names(file, args.out_prefix)
    check_ownership(file.parent, names)
    notes: list[str] = []

    # plan
    plan, plan_mode, plan_meta = None, "absent", {"name": None, "mode": "absent", "sha256": None}
    if args.plan is not None:
        pobj, perr = load_plan(Path(args.plan), int(prof.get("fps_default", 30)))
        psha = sha256_file(Path(args.plan)) if Path(args.plan).is_file() else None
        if perr:
            plan_mode = "unusable"
            notes.append(f"plan unusable, ignored: {perr}")
        else:
            plan, plan_mode = pobj, ("exemptions_only" if args.plan_exemptions_only else "full")
        plan_meta = {"name": Path(args.plan).name, "mode": plan_mode, "sha256": psha}
    spec = build_expected_spec(args, plan, plan_mode, prof)

    # record (in memory only; check never writes render.json)
    rec_path = Path(args.render_record) if args.render_record else file.parent / "render.json"
    record = None
    rec_meta = None
    if rec_path.is_file():
        raw, err = guard.read_record(rec_path)
        rec_meta = {"name": rec_path.name, "sha256": sha256_file(rec_path)}
        if raw is not None:
            record = guard.reconcile(raw, file)
        else:
            notes.append(f"render record unreadable: {err}")
    describing = record if fkrerun.describes(record, file) else None
    lock_other = lock_held_by_other
    if lock_other is None:
        lock_other = bool(record and record.get("status") == "running") and not guard.try_lock_free(rec_path.parent)
    prov = guard.provenance(record, file, rec_path.parent, lock_other)

    # a file written by transform.py (M3): its own record sits beside it; used only when no render record describes it
    derived = None
    if describing is None and args.render_record is None:
        tpath = guard.transform_record_path(file)
        if tpath.is_file():
            traw, terr = guard.read_record(tpath)
            if traw is not None and traw.get("op"):
                derived = guard.reconcile(traw, file)
            else:
                notes.append(f"transform record unreadable: {terr or 'not a transform record'}")
    if derived is not None:
        t_lock_other = bool(derived.get("status") == "running") and not guard.try_lock_free(file.parent)
        prov = guard.provenance_derived(derived, file, t_lock_other)

    # rules
    rules, rules_meta, rules_error = None, None, None
    if args.rules is not None:
        rp = Path(args.rules)
        try:
            data = rp.read_bytes()
            rules_meta = {"name": rp.name, "sha256": sha256_bytes(data)}
            rules = json.loads(data.decode("utf-8"))
            if not isinstance(rules, dict):
                raise ValueError("the rules file is not a JSON object")
        except (OSError, ValueError) as e:
            rules_meta = rules_meta or {"name": rp.name, "sha256": None}
            rules, rules_error = None, last_line(e)
            notes.append(f"rules file unreadable: {rules_error}")

    # formal path (FK-R-18 / FK-R-19): the page folder is the render record's folder, else the file's
    formal = None
    if args.rows_subset is None:
        try:
            formal = fkformal.facts(rec_path.parent if rec_meta else file.parent,
                                    plan if plan_mode in ("full", "exemptions_only") else None)
            if formal["item"] or formal["axes"]:    # only when the formal path is in play; lab pages stay quiet
                st = formal["stamp"] or {}
                notes.append("formal path: item {item}, design-axes {sha}, current mount {cur}, actor {actor}, toolbox "
                             "{tb}".format(item=formal["item"] or "none", sha=(formal["axes_sha"] or "none")[:12],
                                           cur=(formal["current_mount_sha"] or "unknown")[:12],
                                           actor=st.get("actor") or "none", tb=len(st.get("toolbox") or [])))
        except Exception as e:  # the formal facts never stop a check; the rows become absent and a note says why
            notes.append(f"formal path facts unavailable: {last_line(e)}")

    facts = ProbeFacts(readable=None, error="check timed out")
    file_sha = sha256_file(file)
    judged: dict = {}
    try:
        facts = probe(file, deadline)
        scan_events = None
        if facts.readable and args.rows_subset is None:
            nl = (plan or {}).get("narration_lines") if plan_mode in ("full", "exemptions_only") else None
            scan_events = fkscan.scan(file, facts, prof, SCAN_WANT, deadline, lines=nl or None)
            notes.extend(scan_events.notes)
        fault_point("judge")
        judged = fkjudge.judge_full(facts, scan_events, spec, plan, plan_mode, describing, derived, rules, prof,
                                    args.mounted_kit_hash, kit_hash(kit_dir), lock_other, prov, rules_error,
                                    args.target, formal)
        rows = judged["rows"]
        if args.rows_subset is not None:
            rows = [r for r in rows if r["id"].split("#")[0] in args.rows_subset]
        for r in rows:
            if r["category"] == "format" and r["verdict"] == "FAIL":
                if derived is not None:        # no re-render command for a derived file; name its record (PSM 4.3 rule 7)
                    r["rerun"] = None
                    r["rerun_note"] = (f"made by transform.py {derived.get('op')}; "
                                       f"the record is {guard.transform_record_path(file).name}")
                    continue
                r["rerun"] = fkrerun.build(record, file, args, kit_dir, spec=spec,
                                           include_audio=r["id"] == "FK-R-5", record_dir=rec_path.parent)
    except KeyboardInterrupt:
        rows = fallback_rows("interrupted")
    except Exception as e:  # post-publish exceptions never fail the run (PSM 6.2)
        internal_error = internal_error or last_line(e)
        rows = fallback_rows(f"check stopped: {last_line(e)}")
    if args.rows_subset is not None:
        rows = [r for r in rows if r["id"].split("#")[0] in args.rows_subset]

    font_moments = None
    if describing:
        fams = ((describing.get("last_success") or {}).get("load_report") or {}).get("font_families") or []
        ms = []
        for f in fams:
            for m in f.get("sampled_at") or []:
                if m not in ms:
                    ms.append(m)
        font_moments = sorted(ms, key=float) if ms else None
        subst = [f["family"] for f in fams if f.get("result") == "substituted"]
        if subst:
            notes.append("font families substituted: " + ", ".join(subst))
    meta = ReportMeta(file={"name": file.name, "sha256": file_sha, "bytes": file.stat().st_size},
                      render_record=rec_meta, plan=plan_meta,
                      expected={**spec.to_json(), "audio_expected": spec.audio_expected, "film_type": spec.film_type},
                      profile=args.profile, kit_hash=kit_hash(kit_dir), rules=rules_meta, probe=facts.to_json(),
                      events=[], exemptions=judged.get("exemptions", []), internal_error=internal_error,
                      look_without_exemptions=judged.get("look_without_exemptions"),
                      exemption_totals=judged.get("exemption_totals"))
    try:
        res = report.write_report(rows, meta, file.parent, names, retry, font_moments)
    except Exception as e:  # check.json could not be written: exit code from the in-memory summary
        meta = replace(meta, internal_error=meta.internal_error or last_line(e))
        summ = report.summarize(rows, meta.internal_error, meta.look_without_exemptions)
        return CheckResult(rows=rows, summary=summ, exit_code=report.code_for(summ), outputs=names,
                           sheet=SheetResult(False, None, "check.json not written"), check_json=None,
                           notes=tuple(notes))
    sh = fksheet.make_sheet(file, file.parent / names.sheet, prof, deadline, facts.video_duration_s, retry)
    return replace(res, sheet=replace(sh, path=(file.parent / names.sheet).as_posix()) if sh.ok else sh,
                   notes=tuple(notes), check_json=res.check_json)


def facts_for_summary(res: CheckResult) -> dict:
    return (res.check_json or {}).get("probe") or {}

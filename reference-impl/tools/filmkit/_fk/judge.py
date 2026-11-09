"""Row table (design 7.5, PSM 7) and the generic range comparator.

Rows: FK-R-1..6 (+ FK-R-3#size, FK-R-5#length, FK-R-6#font), FK-R-7..12 content rows (M2), FK-R-13 (M1; M3 adds
the derived-file branch), FK-R-14 declared exemptions and FK-R-15 conflicts (M2), FK-R-16 rule rows from the rules
file (M2), FK-R-17 loudness (M3), FK-R-9's narration-line branch (M3).

Content rows are evaluated twice (PSM 7.3): once with the author's declarations and once without; only the first
run's rows are written, the second run supplies `look_without_exemptions` (BR-6).
"""
from __future__ import annotations

from .profile import probe_codec_name
from .scan import film_end_of, freeze_floor, start_window, video_end_of
from .types import ExpectedSpec, Interval, ProbeFacts, ScanEvents

FLAG_OF = {"duration_s": "--duration", "size": "--size", "fps": "--fps", "audio_expected": "--audio-expected"}
UNDET_DECODE = "container not readable"
EPS = 1e-6
TOL = 1e-3
PARTIAL_WORD = "（暫定）"       # appended to a provisional rule's sentence (PSM 4.5, P-19c)


def bucket(verdict: str, severity: str | None) -> str:
    if verdict == "UNDET":
        return "undetermined"
    if verdict == "FAIL" and severity == "blocking":
        return "blocking"
    if verdict == "WARN" and severity == "look":
        return "look"
    return "confirmed"


def row(rid, name, category, verdict, severity, *, measured=None, expected=None, basis=None, reason=None,
        unfinished=False, message_key=None, milestone="M0", duration=None, where="file") -> dict:
    b = bucket(verdict, severity)
    t0 = t1 = None
    if where == "file" and b == "look":
        t0, t1 = 0.0, (round(duration, 6) if duration is not None else None)
    return {"id": rid, "name": name, "category": category, "verdict": verdict, "severity": severity, "bucket": b,
            "t0": t0, "t1": t1, "t": None, "where": where, "measured": measured, "expected": expected, "basis": basis,
            "provisional": False, "reason": reason, "unfinished": unfinished, "rerun": None,
            "message_key": message_key or f"{name}.{'ok' if verdict == 'PASS' else verdict.lower()}",
            "milestone": milestone}


def undet(rid, name, category, reason, unfinished=False) -> dict:
    return row(rid, name, category, "UNDET", None, reason=reason, unfinished=unfinished, message_key="undetermined")


def _basis(spec: ExpectedSpec, field: str, profile_name: str) -> str:
    src = spec.source.get(field)
    if src == "flag":
        return f"expected value from flag {FLAG_OF.get(field, field)}"
    if src == "plan":
        return "expected value from film_plan.json"
    if src == "probe":
        return "expected value from the input file"
    if src == "profile":
        return f"profile default fps of {profile_name}"
    return "no expected value"


def judge(facts: ProbeFacts, scan: ScanEvents | None, spec: ExpectedSpec, plan: dict | None, plan_mode: str,
          record: dict | None, transform_rec: dict | None, rules: dict | None, profile: dict,
          mounted_kit_hash: str | None, kit_hash: str, lock_held_by_other: bool,
          provenance: dict | None = None, rules_error: str | None = None, target: str | None = None,
          formal: dict | None = None) -> list[dict]:
    """The rows of one check (the first run of PSM 7.3). See judge_full for the second count and the exemption log."""
    return judge_full(facts, scan, spec, plan, plan_mode, record, transform_rec, rules, profile, mounted_kit_hash,
                      kit_hash, lock_held_by_other, provenance, rules_error, target, formal)["rows"]


def judge_full(facts: ProbeFacts, scan: ScanEvents | None, spec: ExpectedSpec, plan: dict | None, plan_mode: str,
               record: dict | None, transform_rec: dict | None, rules: dict | None, profile: dict,
               mounted_kit_hash: str | None, kit_hash: str, lock_held_by_other: bool,
               provenance: dict | None = None, rules_error: str | None = None, target: str | None = None,
               formal: dict | None = None) -> dict:
    """record: the reconciled render.json when it describes the checked file, else None. provenance: guard.provenance()
    facts for FK-R-13 (the judge reads no files); None -> no FK-R-13 row. rules: the parsed rules file (None = no
    --rules); rules_error: why a given rules file could not be read. target: the name of a rules-file loudness target
    to compare with (FK-R-17); None -> the loudness is reported, never compared. formal: formal.facts() for FK-R-18 /
    FK-R-19 (formal-path design §4.4); None -> no FK-R-18 / FK-R-19 rows.

    Returns {"rows", "look_without_exemptions", "exemptions", "exemption_totals"}: the content rows are evaluated
    twice, with and without the author's declarations (PSM 7.3, BR-6); only the first run's rows are written."""
    pname = profile.get("name", "lab-round")
    th = profile.get("thresholds", {})
    fmt: list[dict] = []
    dur = facts.video_duration_s

    # FK-R-1 .. FK-R-5 need the container
    if facts.readable is None:
        reason = facts.error or "check timed out"
        for rid, name in (("FK-R-1", "container_readable"), ("FK-R-2", "duration"), ("FK-R-3", "frame_geometry"),
                          ("FK-R-4", "pixel_format_codec"), ("FK-R-5", "audio_presence")):
            fmt.append(undet(rid, name, "format", reason, unfinished=True))
    elif not facts.readable:
        fmt.append(row("FK-R-1", "container_readable", "format", "FAIL", "blocking",
                       measured=f"not readable ({facts.error})", expected="a readable MP4",
                       basis="ffprobe stream facts", message_key="container_readable.unreadable"))
        for rid, name in (("FK-R-2", "duration"), ("FK-R-3", "frame_geometry"), ("FK-R-4", "pixel_format_codec"),
                          ("FK-R-5", "audio_presence")):
            fmt.append(undet(rid, name, "format", UNDET_DECODE))
    else:
        fmt.append(row("FK-R-1", "container_readable", "format", "PASS", None,
                       measured=f"video stream {facts.video_codec}, {facts.n_frames} frames", basis="ffprobe stream facts"))
        fmt += _duration(facts, spec, th, pname, dur)
        fmt += _geometry(facts, spec, pname, dur)
        fmt += _codec(facts, profile, pname, dur)
        fmt += _audio(facts, spec, profile, th, pname, dur)

    page = _page_load(record, dur)
    prov = _provenance(provenance, mounted_kit_hash, dur) + _formal_rows(formal, pname, dur)
    plan_usable = plan if plan_mode in ("full", "exemptions_only") else None
    decls = declarations(plan_usable)
    ctx = dict(facts=facts, scan=scan, spec=spec, plan=plan_usable, plan_decls=decls, record=record, rules=rules,
               rules_error=rules_error, profile=profile, dur=dur, target=target)
    c712, c15, c16, log = _content_rows(decls=decls, **ctx)
    n712, n15, n16, _ = _content_rows(decls=[], **ctx)
    rows = fmt + page + c712 + prov + _declared_rows(decls, log, facts, dur) + c15 + c16
    rows_without = fmt + page + n712 + prov + n15 + n16
    look_without = sum(1 for r in rows_without if r["bucket"] == "look")
    exemptions = [{"type": d["type"], "source": d["source"], "t0": d["t0"], "t1": d["t1"], "why": d["why"],
                   "exempted_rows": list(log.get(i, {}).get("rows", [])),
                   "exempted_s": round(log.get(i, {}).get("seconds", 0.0), 6)} for i, d in enumerate(decls)]
    return {"rows": rows, "look_without_exemptions": look_without, "exemptions": exemptions,
            "exemption_totals": _exemption_totals(decls, facts, dur)}


def _duration(facts, spec, th, pname, dur):
    if spec.duration_unusable:
        return [undet("FK-R-2", "duration", "format", spec.duration_unusable)]
    if spec.n_frames is None:
        return [undet("FK-R-2", "duration", "format", "no expected duration given")]
    tol = int(th.get("duration_tolerance_frames", 1))
    measured = f"{facts.n_frames} frames ({facts.video_duration_s:.3f} s)" if facts.video_duration_s is not None else f"{facts.n_frames} frames"
    expected = f"{spec.n_frames} frames ({spec.duration_s:g} s at {spec.fps} fps), tolerance {tol} frame"
    ok = facts.n_frames is not None and abs(facts.n_frames - spec.n_frames) <= tol
    return [row("FK-R-2", "duration", "format", "PASS" if ok else "FAIL", None if ok else "blocking",
                measured=measured, expected=expected, basis=_basis(spec, "duration_s", pname), duration=dur,
                message_key="duration.ok" if ok else "duration.mismatch")]


def _geometry(facts, spec, pname, dur):
    out = []
    even = (facts.width or 1) % 2 == 0 and (facts.height or 1) % 2 == 0
    const = bool(facts.fps_constant)
    size_known = spec.width is not None
    size_ok = (not size_known) or (facts.width == spec.width and facts.height == spec.height)
    ok = even and const and size_ok
    fps_txt = f"{facts.fps_avg:g} fps" if facts.fps_avg else "fps unknown"
    measured = f"{facts.width}x{facts.height}, {fps_txt}, {'constant' if const else f'variable (r_frame_rate {facts.fps_r} vs avg {facts.fps_avg})'}"
    exp_size = f"{spec.width}x{spec.height}, " if size_known else ""
    expected = f"{exp_size}even width and height, constant fps"
    basis = (_basis(spec, "size", pname) + "; " if size_known else "") + "ffprobe stream facts"
    out.append(row("FK-R-3", "frame_geometry", "format", "PASS" if ok else "FAIL", None if ok else "blocking",
                   measured=measured, expected=expected, basis=basis, duration=dur,
                   message_key="frame_geometry.ok" if ok else "frame_geometry.mismatch"))
    if not size_known:
        out.append(undet("FK-R-3#size", "frame_geometry", "format", "no expected size given"))
    return out


def _codec(facts, profile, pname, dur):
    v = profile["video"]
    want_codec = probe_codec_name(v["codec"])
    want_fs = bool(v.get("faststart"))
    bad = []
    if facts.video_codec != want_codec:
        bad.append("codec")
    if facts.pix_fmt != "yuv420p":
        bad.append("pix_fmt")
    if bool(facts.faststart) != want_fs:
        bad.append("faststart")
    measured = f"codec {facts.video_codec}, pix_fmt {facts.pix_fmt}, faststart {'yes' if facts.faststart else 'no'}"
    expected = f"codec {want_codec}, pix_fmt yuv420p, faststart {'yes' if want_fs else 'no'}"
    ok = not bad
    return [row("FK-R-4", "pixel_format_codec", "format", "PASS" if ok else "FAIL", None if ok else "blocking",
                measured=measured, expected=expected, basis=f"profile {pname}; top-level MP4 atoms (moov before mdat)",
                duration=dur, message_key="pixel_format_codec.ok" if ok else "pixel_format_codec.mismatch:" + "+".join(bad))]


def _audio(facts, spec, profile, th, pname, dur):
    a = facts.audio
    want_codec = probe_codec_name(profile["audio"]["codec"])
    want_ch = int(profile["audio"].get("channels", 2))
    desc = (f"{a.get('codec')} {a.get('channels')} ch {a.get('sample_rate')} Hz" if a else "no audio stream")
    basis = _basis(spec, "audio_expected", pname)
    out = []
    exp = spec.audio_expected
    if exp is None:
        out.append(row("FK-R-5", "audio_presence", "format", "PASS", "info", measured=desc, basis="ffprobe stream facts",
                       duration=dur, message_key="audio_presence.info"))
    elif exp and not a:
        out.append(row("FK-R-5", "audio_presence", "format", "FAIL", "blocking", measured=desc,
                       expected="an audio stream", basis=basis, duration=dur, message_key="audio_presence.missing"))
    elif not exp and a:
        out.append(row("FK-R-5", "audio_presence", "format", "WARN", "look", measured=desc, expected="no audio stream",
                       basis=basis, duration=dur, message_key="audio_presence.unexpected"))
    elif exp and a and (a.get("codec") != want_codec or a.get("channels") != want_ch):
        out.append(row("FK-R-5", "audio_presence", "format", "FAIL", "blocking", measured=desc,
                       expected=f"{want_codec} {want_ch} ch", basis=f"{basis}; profile {pname}", duration=dur,
                       message_key="audio_presence.format"))
    else:
        out.append(row("FK-R-5", "audio_presence", "format", "PASS", None, measured=desc,
                       expected=("an audio stream" if exp else "no audio stream"), basis=basis, duration=dur,
                       message_key="audio_presence.ok"))
    if a:
        tol = float(th.get("av_length_tolerance_s", 0.1))
        if facts.audio_duration_s is not None and facts.video_duration_s is not None:
            diff = abs(facts.audio_duration_s - facts.video_duration_s)
            ok = diff <= tol
            out.append(row("FK-R-5#length", "audio_length", "format", "PASS" if ok else "WARN", None if ok else "look",
                           measured=f"{diff:.3f} s (audio {facts.audio_duration_s:.3f} s, video {facts.video_duration_s:.3f} s)",
                           expected=f"tolerance {tol:g} s", basis=f"profile {pname}; ffprobe stream facts", duration=dur,
                           message_key="audio_length.ok" if ok else "audio_length.mismatch"))
        else:
            out.append(undet("FK-R-5#length", "audio_length", "format", "stream duration not reported"))
    return out


def _page_load(record, dur):
    if record is None or not (record.get("last_success") or {}).get("load_report"):
        return [undet("FK-R-6", "page_load_errors", "content", "no render record describes this file")]
    lr = record["last_success"]["load_report"]
    basis = "render.json last_success.load_report"
    failed_fonts = [f"{f.get('family')} ({f.get('src')})" for f in lr.get("fonts", []) if f.get("status") != "loaded"]
    blocked = list(lr.get("blocked_requests") or [])
    out = []
    fams = lr.get("font_families") or []
    if failed_fonts or blocked:
        out.append(row("FK-R-6", "page_load_errors", "content", "FAIL", "blocking",
                       measured="; ".join([f"font failed: {x}" for x in failed_fonts] + [f"blocked: {x}" for x in blocked]),
                       expected="no failed or blocked resource", basis=basis, duration=dur,
                       message_key="page_load_errors.failed"))
    else:
        subst = [f["family"] for f in fams if f.get("result") == "substituted"]
        if subst:
            out.append(row("FK-R-6", "page_load_errors", "content", "WARN", "look",
                           measured="substituted: " + ", ".join(subst), expected="every named font family present",
                           basis=basis, duration=dur, message_key="page_load_errors.substituted"))
        else:
            fonts = lr.get("fonts") or []
            out.append(row("FK-R-6", "page_load_errors", "content", "PASS", None,
                           measured=(f"{len(fonts)}/{len(fonts)} @font-face loaded, {len(lr.get('local_files') or [])} local files, "
                                     f"0 blocked, font families present: {', '.join(f['family'] for f in fams) or 'none probed'}"),
                           basis=basis, duration=dur))
    und = [f["family"] for f in fams if f.get("result") == "undetermined"]
    if und:
        out.append(undet("FK-R-6#font", "page_load_errors", "content",
                         f"font family could not be told apart from the default font on this machine: {', '.join(und)}"))
    return out


def _provenance(prov, mounted, dur):
    """FK-R-13, in the order of PSM 7.2: `--mounted-kit-hash none` and no record -> info and stop; else the owner_state
    table (design 7.4b) on the reconciled record; the kit-hash comparison only for CURRENT and only with a hash."""
    if prov is None:
        return []
    key = lambda k: f"render_provenance.{k}"
    state = prov["state"]
    derived = prov.get("derived")           # M3: a file written by transform.py; its record is <file>.transform.json
    rec_name = "transform record" if derived else "render.json"
    if mounted == "none" and not prov["has_record"]:
        return [row("FK-R-13", "render_provenance", "content", "PASS", "info",
                    measured="no render.json beside the file; this round mounted no kit",
                    basis="flag --mounted-kit-hash none", duration=dur, message_key=key("no_kit"), milestone="M1")]
    if state == "UNDET_INPUTS":
        return [undet("FK-R-13", "render_provenance", "content", prov["why"])]
    if state in ("FOREIGN", "STALE"):
        foreign = state == "FOREIGN"
        if derived:
            expected = ("a file written by filmkit's transform.py with its transform record beside it" if foreign
                        else "the source file and last run as recorded in the transform record")
            basis = "transform record last_success.output.sha256, pending_publish, inputs_sha256 and status"
        else:
            expected = ("a file written by filmkit with its render.json beside it" if foreign
                        else "inputs and last run as recorded in render.json")
            basis = "render.json last_success.output.sha256, pending_publish, inputs_sha256 and status"
        return [row("FK-R-13", "render_provenance", "content", "WARN", "look", measured=prov["why"], expected=expected,
                    basis=basis, duration=dur, message_key=key("foreign" if foreign else "stale"), milestone="M1")]
    if derived and prov.get("chain_problem"):
        return [row("FK-R-13", "render_provenance", "content", "WARN", "look", measured=prov["chain_problem"],
                    expected="the source file still owned by its own render.json, as when this file was made",
                    basis="transform record input_render_record_sha256 and the source's render.json",
                    duration=dur, message_key=key("chain"), milestone="M3")]
    ident = f"run {prov.get('run_id')}"
    if mounted not in (None, "none") and prov.get("kit_hash") != mounted:
        return [row("FK-R-13", "render_provenance", "content", "WARN", "look",
                    measured=f"the render used kit {str(prov.get('kit_hash'))[:12]}", expected=f"mounted kit {str(mounted)[:12]}",
                    basis=f"{rec_name} last_success.kit_hash and flag --mounted-kit-hash" if derived
                    else "render.json last_success.kit_hash and flag --mounted-kit-hash", duration=dur,
                    message_key=key("kit_mismatch"), milestone="M1")]
    kit = f"; kit {str(prov.get('kit_hash'))[:12]} equals the mounted kit" if mounted not in (None, "none") else ""
    if derived:
        return [row("FK-R-13", "render_provenance", "content", "PASS", None,
                    measured=f"written by filmkit transform.py ({derived.get('op')}, {ident}); source unchanged{kit}",
                    basis="transform record last_success and pending_publish", duration=dur, message_key=key("ok"),
                    milestone="M3")]
    return [row("FK-R-13", "render_provenance", "content", "PASS", None,
                measured=f"written by filmkit ({ident}); inputs unchanged{kit}",
                basis="render.json last_success and pending_publish", duration=dur, message_key=key("ok"), milestone="M1")]


# ====================================================================================================
# Formal-path rows (~/.claude/references/formal-path-governance-design.md §4.4): was the shared design layer mounted
# and is the generation act stamped? Blocking only where a film leaves the lab; a lab round reports them as info.
FORMAL_BLOCKING_PROFILES = ("delivery-web",)
B18 = "design-axes.md sha vs the shared layer's digest.py check --medium video"
B19 = "the works item's state.json made_by (W-2 keys + actor + toolbox)"


def _formal_rows(formal: dict | None, pname: str, dur) -> list[dict]:
    if formal is None:
        return []
    strict = pname in FORMAL_BLOCKING_PROFILES

    def bad(rid, name, key, measured, expected, basis):
        return row(rid, name, "content", "FAIL" if strict else "WARN", "blocking" if strict else "info",
                   measured=measured if strict else f"{measured} (profile {pname}: info only)", expected=expected,
                   basis=basis, message_key=key, milestone="F1", duration=dur)

    out = []
    opt = formal.get("optout")
    cur = formal.get("current_mount_sha")
    if opt and opt.get("why"):
        out.append(row("FK-R-18", "provenance_mount", "content", "PASS", "info",
                       measured=f"declared not mounted in {opt['source']}: {opt['why']}", basis=B18,
                       message_key="provenance_mount.declared", milestone="F1", duration=dur))
    elif not formal.get("axes"):
        why = f"; {opt['source']} says mount_design_axes false without a why" if opt else ""
        out.append(bad("FK-R-18", "provenance_mount", "provenance_mount.missing",
                       f"no design-axes.md in the works item or beside the page{why}",
                       "<item>/inputs/design-axes.md copied by works_contract.py open", B18))
    elif not cur:
        out.append(undet("FK-R-18", "provenance_mount", "content",
                         f"the current mount is unknown: {formal.get('current_error')}"))
    elif formal.get("axes_sha") != cur:
        out.append(bad("FK-R-18", "provenance_mount", "provenance_mount.stale",
                       f"{formal['axes']} sha {str(formal.get('axes_sha'))[:12]}",
                       f"the current mount/video.md sha {cur[:12]}", B18))
    else:
        out.append(row("FK-R-18", "provenance_mount", "content", "PASS", None,
                       measured=f"{formal['axes']} = the current mount ({cur[:12]})", basis=B18, milestone="F1"))
    stamp = formal.get("stamp")
    if not formal.get("item"):
        out.append(bad("FK-R-19", "provenance_stamp", "provenance_stamp.not_item",
                       "not a works item: no state.json in the page folder or above it",
                       "a works item made by works_contract.py open (or adopt)", B19))
    elif formal.get("state_error"):
        out.append(bad("FK-R-19", "provenance_stamp", "provenance_stamp.missing",
                       f"state.json unreadable: {formal['state_error']}", "a readable state.json", B19))
    elif stamp is None or formal.get("stamp_missing"):
        got = (f"made_by[{stamp.get('stage')}] lacks {', '.join(formal['stamp_missing'])}" if stamp
               else "state.json has no made_by row of stage open / generate / build / adopt")
        out.append(bad("FK-R-19", "provenance_stamp", "provenance_stamp.missing", got,
                       "the last generating row carries every W-2 key, actor and toolbox", B19))
    else:
        tb = stamp.get("toolbox") or []
        out.append(row("FK-R-19", "provenance_stamp", "content", "PASS", None,
                       measured=f"made_by[{stamp.get('stage')}] by {stamp.get('actor')}, toolbox "
                                f"{', '.join(t.get('path', '?') for t in tb if isinstance(t, dict)) or 'none'}",
                       basis=B19, milestone="F1"))
    return out


# M2 content rows (design 7.5: FK-R-7..12, 14, 15, 16)
# ====================================================================================================
IV_KINDS = {
    "black": {"rid": "FK-R-7", "name": "black_interval", "where": "picture", "decl": "black", "th": "black",
              "none": "no undeclared black picture"},
    "frozen": {"rid": "FK-R-8", "name": "frozen_interval", "where": "picture", "decl": "hold", "th": "freeze",
               "none": "no undeclared still picture"},
    "silent": {"rid": "FK-R-9", "name": "silent_interval", "where": "audio", "decl": "silence", "th": "silence",
               "none": "no undeclared silence"},
}
DECL_KEYS = (("hold", "holds"), ("black", "blacks"), ("silence", "silences"))
SOURCE_OF = {"black": "black", "frozen": "frozen", "silent": "silent"}
CONTENT_ROW_IDS = [("FK-R-7", "black_interval", "content"), ("FK-R-8", "frozen_interval", "content"),
                   ("FK-R-9", "silent_interval", "content"), ("FK-R-10", "first_frame_blank", "content"),
                   ("FK-R-11", "live_animations", "content"), ("FK-R-12", "seek_determinism", "content")]


def trow(rid, name, category, verdict, severity, where, t0, t1, *, t=None, **kw) -> dict:
    """A row that carries a place in time (t0/t1 for a span, t for a point); otherwise like row()."""
    r = row(rid, name, category, verdict, severity, where=where, milestone="M2", **kw)
    r["t0"], r["t1"] = t0, t1
    r["t"] = t if t is not None else (round((t0 + t1) / 2, 6) if t0 is not None and t1 is not None else None)
    return r


def declarations(plan: dict | None) -> list[dict]:
    """The author's holds / blacks / silences, in file order per type (FK-INV-8: each has a non-empty why)."""
    out = []
    for typ, key in DECL_KEYS:
        for d in (plan or {}).get(key) or []:
            out.append({"type": typ, "source": key, "t0": float(d["t0"]), "t1": float(d["t1"]), "why": d["why"]})
    return out


def _subtract(t0: float, t1: float, cuts: list[tuple[float, float]]) -> list[tuple[float, float]]:
    pieces = [(t0, t1)]
    for c0, c1 in cuts:
        nxt = []
        for a, b in pieces:
            if c1 <= a + EPS or c0 >= b - EPS:
                nxt.append((a, b))
                continue
            if a < c0 - EPS:
                nxt.append((a, c0))
            if c1 < b - EPS:
                nxt.append((c1, b))
        pieces = nxt
    return [(a, b) for a, b in pieces if b - a > EPS]


def _union_length(spans: list[tuple[float, float]]) -> float:
    total, end = 0.0, None
    for a, b in sorted(spans):
        if end is None or a > end:
            total += b - a
            end = b
        elif b > end:
            total += b - end
            end = b
    return total


def _exemption_totals(decls: list[dict], facts: ProbeFacts, dur: float | None) -> dict | None:
    if not decls:
        return None
    film = video_end_of(facts) or dur or 0.0
    spans = [(max(0.0, d["t0"]), min(d["t1"], film)) for d in decls if min(d["t1"], film) > max(0.0, d["t0"])]
    secs = _union_length(spans)
    return {"declarations": len(decls), "seconds": round(secs, 6),
            "share_of_film": round(secs / film, 6) if film else None}


def _tspan(a: float, b: float) -> str:
    return f"{b - a:.2f} s ({a:.2f}–{b:.2f} s)"


def _basis_of(kind: str, th: dict) -> str:
    t = th.get(IV_KINDS[kind]["th"], {})
    floor = float(t.get("min_duration_s", 0))
    if kind == "black":
        return (f"ffmpeg blackdetect: picture ratio {t.get('picture_ratio')}, pixel threshold {t.get('pixel_threshold')}, "
                f"at least {floor:g} s")
    if kind == "frozen":
        return f"ffmpeg freezedetect: noise {t.get('noise')}, at least {floor:g} s"
    return f"ffmpeg silencedetect: noise {t.get('noise_db')} dB, at least {floor:g} s"


def _scan_state(facts: ProbeFacts, scan: ScanEvents | None) -> tuple[str, str, bool]:
    """(state, reason, unfinished). Unfinished means the check did not finish (timeout, scan failure); a file that
    cannot be read is a conclusion about the file (design 7.4), not an unfinished check."""
    if facts.readable is None:
        return "timeout", facts.error or "check timed out", True
    if not facts.readable:
        return "unreadable", UNDET_DECODE, False
    if scan is None:
        return "not_run", "content scan not run", False
    if not scan.finished:
        return "failed", scan.error or "scan failed", True
    return "ok", "", False


def _undet_content(facts, reason, unfinished, has_audio, state) -> list[dict]:
    rows = [undet(rid, name, cat, reason, unfinished) for rid, name, cat in CONTENT_ROW_IDS[:2]]
    if has_audio or state in ("timeout", "unreadable"):
        rows.append(undet("FK-R-9", "silent_interval", "content", reason, unfinished))
    rows.append(undet("FK-R-10", "first_frame_blank", "content", reason, unfinished))
    return rows


def _interval_rows(kind: str, ivs, decls: list[dict], th: dict, dur, log: dict, skip=None, note: str = "") -> list[dict]:
    meta = IV_KINDS[kind]
    floor = float(th.get(meta["th"], {}).get("min_duration_s", 0))
    basis = _basis_of(kind, th)
    mine = [(i, d) for i, d in enumerate(decls) if d["type"] == meta["decl"]]
    rows, k, skipped, kept = [], 0, 0, []
    for iv in ivs:
        if skip and skip(iv):
            skipped += 1
            continue
        kept.append(iv)
        k += 1
        rid = f"{meta['rid']}#{k}"
        text = _tspan(iv.t0, iv.t1) + (", runs to the end of the film" if iv.open_at_end else "")
        expected = f"{meta['none']} of at least {floor:g} s"
        over = [(i, d) for i, d in mine if min(iv.t1, d["t1"]) - max(iv.t0, d["t0"]) > EPS]
        if not over:
            rows.append(trow(rid, meta["name"], "content", "WARN", "look", meta["where"], iv.t0, iv.t1, measured=text,
                             expected=expected, basis=basis, message_key=f"{meta['name']}.look"))
            continue
        cuts = [(d["t0"], d["t1"]) for _, d in over]
        pieces = _subtract(iv.t0, iv.t1, cuts)
        big = max(pieces, key=lambda p: p[1] - p[0]) if pieces else None
        decl_txt = "; ".join(f"declared in {d['source']}: \"{d['why']}\" ({d['t0']:.2f}–{d['t1']:.2f} s)" for _, d in over)
        for i, d in over:
            e = log.setdefault(i, {"rows": [], "seconds": 0.0})
            e["rows"].append(rid)
            e["seconds"] += min(iv.t1, d["t1"]) - max(iv.t0, d["t0"])
        if big and (big[1] - big[0]) >= floor - TOL:
            rows.append(trow(rid, meta["name"], "content", "WARN", "look", meta["where"], big[0], big[1],
                             measured=f"{text}; the declaration leaves {_tspan(*big)} uncovered", expected=expected,
                             basis=f"{basis}; {decl_txt}", message_key=f"{meta['name']}.look"))
        else:
            rows.append(trow(rid, meta["name"], "content", "PASS", "info", meta["where"], iv.t0, iv.t1, measured=text,
                             expected=expected, basis=f"{basis}; {decl_txt}", message_key=f"{meta['name']}.declared"))
    for r, iv in zip(rows, kept):
        r["open_at_end"] = bool(iv.open_at_end)       # one row per kept interval, in order (calibration reads it)
    if not rows and skipped:
        return []              # every interval is listed by another row (FK-R-7 or a rule row): not repeated here
    if not rows:
        rows.append(row(meta["rid"], meta["name"], "content", "PASS", None,
                        measured=f"none found (detection floor {floor:g} s){note}", basis=basis, duration=dur,
                        milestone="M2", message_key=f"{meta['name']}.ok"))
    return rows


def _local_motion_rows(scan, th) -> list[dict]:
    """W32: one info row per still-looking span left out of `frozen` because one tile of the picture moves. Its own id
    family (FK-R-8L), so a reader of the FK-R-8 rows never takes it for a still."""
    limit = (th.get("freeze") or {}).get("local_tile_median_max")
    rows = []
    for k, (t0, t1, med) in enumerate(scan.frozen_local_motion, 1):
        rows.append(trow(f"FK-R-8L#{k}", "frozen_interval", "content", "PASS", "info", "picture", t0, t1,
                         measured=f"{_tspan(t0, t1)}; the largest tile changes by a median of {med:.5f} per frame",
                         expected=f"a median of at most {limit:g}" if limit is not None else None,
                         basis="ffmpeg tblend frame difference at 320x180, largest tile of a 16x9 grid, median over the frames of the span",
                         message_key="frozen_interval.local_motion"))
    return rows


def _silent_rows(facts, scan, spec, decls, th, dur, log) -> list[dict]:
    """FK-R-9. All samples zero is a determinate fact (SG-14), not a threshold: blocking when sound was expected."""
    if not facts.audio:
        return []
    exp = spec.audio_expected
    if exp is False:
        return []          # no sound expected: the stream itself is FK-R-5's row
    peak = scan.audio_peak_db
    if peak is not None and peak == float("-inf"):
        basis = f"ffmpeg astats overall peak level; {_exp_src(spec)}"
        meas = "every audio sample is 0 (peak level -inf dB)"
        if exp:
            return [row("FK-R-9", "silent_interval", "content", "FAIL", "blocking", measured=meas,
                        expected="an audio track with sound in it", basis=basis, duration=dur, milestone="M2",
                        message_key="silent_interval.allzero")]
        return [row("FK-R-9", "silent_interval", "content", "WARN", "look", measured=meas,
                    expected="an audio track with sound in it", basis=basis, duration=dur, milestone="M2",
                    message_key="silent_interval.allzero_look")]
    note = f"; peak level {peak:.1f} dB" if peak is not None else ""
    return _interval_rows("silent", scan.silent, decls, th, dur, log, note=note) + _line_rows(facts, scan, th)


def _db(x) -> str:
    return "-inf" if x == float("-inf") else f"{x:.1f}"


def _line_rows(facts, scan, th) -> list[dict]:
    """FK-R-9's narration-line branch (M3, D27): a narration line whose own span is near digital silence. A silences
    declaration over a line never exempts it (FK-R-15 reports the conflict); the level is the profile's silence level."""
    lines = scan.lines
    if not lines:
        return []
    floor = th.get("silence", {}).get("noise_db")
    if floor is None:
        return [undet("FK-R-9#lines", "silent_interval", "content", "the silence level is not set in the profile")]
    film_end = film_end_of(facts)
    basis = (f"ffmpeg astats peak level inside the line (atrim at the line's times); near-silent means peak <= "
             f"{floor:g} dB, the profile's silence level; not calibrated")
    rows, peaks = [], []
    for ln in lines:
        rid = f"FK-R-9#line-{ln['id']}"
        p = ln.get("peak_db")
        if p is None or (film_end is not None and ln["t0"] >= film_end - EPS):
            rows.append(undet(rid, "silent_interval", "content", "narration line not inside the audio track"))
            continue
        peaks.append(p)
        if p <= floor:
            r = trow(rid, "silent_interval", "content", "WARN", "look", "audio", ln["t0"], ln["t1"],
                     measured=f"narration line {ln['id']}: peak level {_db(p)} dB over {_tspan(ln['t0'], ln['t1'])}",
                     expected=f"sound above {floor:g} dB inside a narration line", basis=basis,
                     message_key="silent_interval.line")
            r["milestone"] = "M3"
            r["values"] = {"line": ln["id"], "peak_db": None if p == float("-inf") else p}
            rows.append(r)
    if peaks and not any(r["verdict"] != "PASS" for r in rows):
        rows.append(row("FK-R-9#lines", "silent_interval", "content", "PASS", None,
                        measured=f"{len(peaks)} narration lines, quietest peak {_db(min(peaks))} dB", basis=basis,
                        milestone="M3", message_key="silent_interval.line_ok"))
    return rows


def _loudness_rows(facts, scan, rules, rules_error, target, dur) -> list[dict]:
    """FK-R-17 (M3). The measured loudness is always reported as info. A named rules-file target adds one comparison
    row: true peak above the target's ceiling, or integrated loudness farther from the target than its
    `tolerance_lu`, is WARN / look. The tolerance lives in the rules file; a target without one is compared on the
    true peak only and the loudness part is UNDET (FK-INV-12: the kit holds no number of its own)."""
    if not facts.audio:
        return [undet(f"FK-R-17#{target}", "loudness", "rule", "the file has no audio track to measure")] if target else []
    loud = scan.loudness
    if not loud:
        return [undet("FK-R-17", "loudness", "rule", "the ebur128 summary was not found in the scan output")]
    i, tp = loud["integrated_lufs"], loud["true_peak_db"]
    measured = f"integrated {_db(i)} LUFS, true peak {_db(tp)} dBTP"
    basis = "ffmpeg ebur128 summary (integrated loudness, gated; true peak, oversampled)"
    info = row("FK-R-17", "loudness", "rule", "PASS", "info", measured=measured, basis=basis, duration=dur,
               milestone="M3", message_key="loudness.info")
    info["values"] = {"integrated_lufs": None if i == float("-inf") else i,
                      "true_peak_db": None if tp == float("-inf") else tp, "lra_lu": loud.get("lra_lu")}
    out = [info]
    if target is None:
        return out
    rid = f"FK-R-17#{target}"
    if rules_error:
        return out + [undet(rid, "loudness", "rule", f"rules file unreadable: {rules_error}")]
    if rules is None:
        return out + [undet(rid, "loudness", "rule", "no rules file given for the loudness target")]
    entry = (rules.get("targets") or {}).get(target) if isinstance(rules.get("targets"), dict) else None
    if entry is None:
        return out + [undet(rid, "loudness", "rule", f"loudness target not in the rules file: {target}")]
    ent = entry if isinstance(entry, dict) else {}
    lufs, ceil, tol = ent.get("lufs"), ent.get("true_peak"), ent.get("tolerance_lu")
    num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)
    if not (num(lufs) and num(ceil)) or (tol is not None and not num(tol)):
        return out + [undet(rid, "loudness", "rule", f"loudness target is malformed in the rules file: {target}")]
    src = f"rules file target {target}"
    tb = f"ffmpeg ebur128 summary compared with {src} ({ent.get('source', 'no source recorded')})"
    over_tp = tp > ceil + EPS
    exp = (f"integrated {lufs:g} LUFS within ±{tol:g} LU, true peak at most {ceil:g} dBTP" if tol is not None
           else f"true peak at most {ceil:g} dBTP")
    if i == float("-inf"):
        dev, over_i = None, True
    else:
        dev = i - lufs
        over_i = tol is not None and abs(dev) > tol + EPS
    vals = {"target": target, "target_lufs": lufs, "target_true_peak": ceil, "tolerance_lu": tol,
            "deviation_lu": None if dev is None else round(dev, 3)}
    if over_tp or over_i:
        meas = (f"integrated {_db(i)} LUFS ({'silent' if dev is None else f'{dev:+.1f} LU from the target'}), "
                f"true peak {_db(tp)} dBTP")
        r = row(rid, "loudness", "rule", "WARN", "look", measured=meas, expected=exp, basis=tb, duration=dur,
                milestone="M3", message_key="loudness.out")
    elif tol is None:
        return out + [undet(rid, "loudness", "rule", f"the rules file target {target} gives no loudness tolerance")]
    else:
        r = row(rid, "loudness", "rule", "PASS", None, measured=measured, expected=exp, basis=tb, duration=dur,
                milestone="M3", message_key="loudness.ok")
    r["values"] = vals
    return out + [r]


def _exp_src(spec) -> str:
    src = spec.source.get("audio_expected")
    return {"flag": "sound expected by flag --audio-expected", "plan": "sound expected by film_plan.json"}.get(src, "no sound expectation given")


def _first_frame_rows(facts, scan, th, covered: bool) -> list[dict]:
    ff = th.get("first_frame", {})
    mx, mn = ff.get("max_luma_stddev"), ff.get("min_diff_to_1s")
    if mx is None or mn is None:
        return [undet("FK-R-10", "first_frame_blank", "content", "first-frame thresholds are not set in the profile")]
    stats = scan.first_frame
    if stats is None:
        idx = int(round(facts.fps_avg or 0))
        if facts.n_frames is not None and idx and facts.n_frames <= idx:
            return [undet("FK-R-10", "first_frame_blank", "content", "the film has no frame at 1 s")]
        return [undet("FK-R-10", "first_frame_blank", "content", "frame 0 and the frame at 1 s could not be read")]
    if covered:
        return []          # the black or still interval that starts at frame 0 is already listed (design 7.5)
    min_flat = float(ff.get("min_flat_s", 0) or 0)
    flat_n = stats.get("flat_frames")
    flat_s = flat_n / facts.fps_avg if (flat_n is not None and facts.fps_avg) else None
    meas = (f"frame 0 luma std {stats['std']:.1f} (mean {stats['mean']:.0f}); mean difference to the frame at "
            f"{stats['index']} frames {stats['diff']:.1f}")
    if flat_s is not None:
        meas += f"; flat for {flat_n} frames ({flat_s:.2f} s)"
    basis = (f"frame 0 and frame {stats['index']} at 64x36 luma; flat means std <= {mx:g}, different means "
             f"difference >= {mn:g}; thresholds not calibrated")
    if min_flat:
        basis += f"; a flat start shorter than {min_flat:g} s is info only (D18)"
    values = {"std": stats["std"], "mean": stats["mean"], "diff": stats["diff"], "index": stats["index"]}
    if flat_n is not None:
        values["flat_frames"] = flat_n
    blank = stats["std"] <= mx and stats["diff"] >= mn
    brief = blank and min_flat and flat_s is not None and flat_s < min_flat - 1e-9
    if brief:              # D18 (W30): one or two flat frames are not visible; recorded, never asked about
        r = trow("FK-R-10", "first_frame_blank", "content", "PASS", "info", "picture", None, None, t=0.0, measured=meas,
                 expected=f"a flat start of at least {min_flat:g} s", basis=basis, message_key="first_frame_blank.brief")
    elif blank:
        r = trow("FK-R-10", "first_frame_blank", "content", "WARN", "look", "picture", None, None, t=0.0, measured=meas,
                 expected="frame 0 that is not a flat frame unlike the frame at 1 s", basis=basis,
                 message_key="first_frame_blank.look")
    else:
        r = row("FK-R-10", "first_frame_blank", "content", "PASS", None, measured=meas, basis=basis, where="picture",
                milestone="M2", message_key="first_frame_blank.ok")
    r["values"] = values            # the numbers behind the row, for the calibration corpus
    return [r]


def _animation_rows(record, dur) -> list[dict]:
    ls = (record or {}).get("last_success") or {}
    fr = ls.get("frames") or {}
    live = fr.get("live_animations")
    if record is None or not ls:
        return [undet("FK-R-11", "live_animations", "content", "no render record describes this file")]
    if not isinstance(live, list) or not live:
        return [undet("FK-R-11", "live_animations", "content", "render.json lists no per-frame animation counts")]
    fps = (ls.get("expected") or {}).get("fps") or 30
    hot = [i for i, v in enumerate(live) if v]
    basis = "document.getAnimations() after each seek (render.json frames.live_animations)"
    if hot:
        return [row("FK-R-11", "live_animations", "content", "WARN", "look",
                    measured=(f"{len(hot)} of {len(live)} frames had a running animation (first at frame {hot[0]}, "
                              f"t={hot[0] / fps:.2f} s; at most {max(live)} at once)"),
                    expected="no running animation in any frame", basis=basis, duration=dur, milestone="M2",
                    message_key="live_animations.look")]
    return [row("FK-R-11", "live_animations", "content", "PASS", None,
                measured=f"0 of {len(live)} frames had a running animation", basis=basis, milestone="M2",
                message_key="live_animations.ok")]


def _seek_rows(record, dur) -> list[dict]:
    ls = (record or {}).get("last_success") or {}
    fr = ls.get("frames") or {}
    if record is None or not ls:
        return [undet("FK-R-12", "seek_determinism", "content", "no render record describes this file")]
    rs = fr.get("resample") or []
    if not rs:
        return [undet("FK-R-12", "seek_determinism", "content", "render.json holds no re-seek sample")]
    fps = (ls.get("expected") or {}).get("fps") or 30
    bad = [x for x in rs if not x.get("match")]
    basis = "frames re-captured in shuffled order after the last frame, sha256 compared (render.json frames.resample)"
    if bad:
        listing = ", ".join(f"{x['i']} ({x['i'] / fps:.2f} s)" for x in sorted(bad, key=lambda x: x["i"])[:6])
        return [row("FK-R-12", "seek_determinism", "content", "WARN", "look",
                    measured=f"{len(bad)} of {len(rs)} re-visited frames differ from their first capture: frames {listing}",
                    expected="every re-visited frame identical to its first capture", basis=basis, duration=dur,
                    milestone="M2", message_key="seek_determinism.look")]
    return [row("FK-R-12", "seek_determinism", "content", "PASS", None,
                measured=f"{len(rs)} of {len(rs)} re-visited frames identical to their first capture", basis=basis,
                milestone="M2", message_key="seek_determinism.ok")]


def _declared_rows(decls: list[dict], log: dict, facts: ProbeFacts, dur) -> list[dict]:
    """FK-R-14: one info row per declaration, then the totals row (no plan -> no row)."""
    if not decls:
        return []
    rows = []
    for i, d in enumerate(decls):
        e = log.get(i, {"rows": [], "seconds": 0.0})
        where = "audio" if d["type"] == "silence" else "picture"
        rows.append(trow(f"FK-R-14#{i + 1}", "declared_exemptions", "content", "PASS", "info", where, d["t0"], d["t1"],
                         measured=(f"{d['type']} {_tspan(d['t0'], d['t1'])}: \"{d['why']}\"; it exempted "
                                   f"{len(e['rows'])} row(s), {e['seconds']:.2f} s"),
                         basis=f"film_plan.json {d['source']}", message_key="declared_exemptions.item"))
    tot = _exemption_totals(decls, facts, dur)
    share = f"{tot['share_of_film'] * 100:.1f} %" if tot["share_of_film"] is not None else "share unknown"
    rows.append(row("FK-R-14", "declared_exemptions", "content", "PASS", "info",
                    measured=f"{tot['declarations']} declarations cover {tot['seconds']:.2f} s of the film ({share})",
                    basis="film_plan.json holds, blacks and silences", milestone="M2",
                    message_key="declared_exemptions.total"))
    return rows


def _conflict_rows(plan: dict | None, decls: list[dict], facts: ProbeFacts, fps: float) -> list[dict]:
    """FK-R-15 (D27): a silences declaration over a narration line; a declaration ending past the film (P-21c)."""
    lines = (plan or {}).get("narration_lines") or []
    if not decls and not lines:
        return []
    eps = 1.0 / (2 * fps)
    end = video_end_of(facts)
    rows, k = [], 0
    for d in decls:
        if d["type"] == "silence":
            for ln in lines:
                lo, hi = max(d["t0"], float(ln["t0"])), min(d["t1"], float(ln["t1"]))
                if hi - lo > eps:
                    k += 1
                    rows.append(trow(f"FK-R-15#{k}", "exemption_conflict", "content", "WARN", "look", "audio", lo, hi,
                                     measured=(f"silences declaration {_tspan(d['t0'], d['t1'])} overlaps narration line "
                                               f"{ln['id']} ({float(ln['t0']):.2f}–{float(ln['t1']):.2f} s) for {hi - lo:.2f} s"),
                                     expected="no silences declaration over a narration line",
                                     basis="film_plan.json silences and narration_lines", message_key="exemption_conflict.overlap"))
        if end is not None and d["t1"] > end + eps:
            k += 1
            rows.append(row(f"FK-R-15#{k}", "exemption_conflict", "content", "WARN", "look",
                            measured=f"{d['source']} declaration {_tspan(d['t0'], d['t1'])} ends after the film ({end:.2f} s)",
                            expected="every declaration inside the film", basis="film_plan.json and the video length",
                            duration=end, milestone="M2", message_key="exemption_conflict.beyond"))
    if not rows:
        rows.append(row("FK-R-15", "exemption_conflict", "content", "PASS", None,
                        measured=f"{len(decls)} declarations and {len(lines)} narration lines: no overlap, none past the end of the film",
                        basis="film_plan.json", milestone="M2", message_key="exemption_conflict.ok"))
    return rows


# ---------------------------------------------------------------------------------------------------- rules
SELECT_SOURCES = ("black", "frozen", "silent")
SELECT_ANCHORS = ("start", "end", "any", "first")


def select_intervals(rule: dict, scan: ScanEvents, video_end: float, film_end: float) -> list[Interval]:
    """Intervals of the rule's source that satisfy its anchor. `end`: black and frozen compare with video_end,
    silent with film_end (R-7a); `max_gap_s` is the largest allowed reference - t1. `start`: t0 within `max_gap_s` of
    frame 0. `first` (W33): the single earliest interval whose t0 is at most `max_t0_s`. `any`: every interval."""
    sel = rule["select"]
    src = sel["source"]
    anchor = sel.get("anchor", "any")
    gap = float(sel.get("max_gap_s", 0))
    ivs = {"black": scan.black, "frozen": scan.frozen, "silent": scan.silent}[src]
    ref = film_end if src == "silent" else video_end
    if anchor == "end":
        return [iv for iv in ivs if -EPS <= ref - iv.t1 <= gap + EPS]
    if anchor == "start":
        return [iv for iv in ivs if -EPS <= iv.t0 <= gap + EPS]
    if anchor == "first":
        inside = [iv for iv in ivs if iv.t0 <= float(sel["max_t0_s"]) + EPS]
        return [min(inside, key=lambda iv: iv.t0)] if inside else []
    return list(ivs)


def _rule_problem(rule: dict) -> str | None:
    sel = rule.get("select")
    if not isinstance(sel, dict):
        return "rule has no select object"
    if sel.get("source") not in SELECT_SOURCES:
        return f"rule selector source not supported by this kit: {sel.get('source')}"
    if sel.get("anchor", "any") not in SELECT_ANCHORS:
        return f"rule selector anchor not supported by this kit: {sel.get('anchor')}"
    if sel.get("anchor") == "first":
        mt = sel.get("max_t0_s")
        if not (isinstance(mt, (int, float)) and not isinstance(mt, bool) and mt >= 0):
            return "rule selector anchor first needs max_t0_s (a number of seconds, not below 0)"
    rg = rule.get("range_s")
    if not (isinstance(rg, list) and len(rg) == 2 and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in rg)
            and rg[0] <= rg[1]):
        return "rule range_s is not [low, high]"
    return None


def range_compare(rule: dict, scan: ScanEvents, video_end: float, film_end: float, floors: dict) -> tuple[list[dict], list[tuple]]:
    """The only rule logic in the kit (PSM 6.6). One row per interval the selector matches (`anchor: any` may match
    several, M2 reading 6); none matched -> one WARN/look row naming the detection floor. Returns (rows, matches)
    where matches = [(source, Interval)] so the caller can drop the FK-R-8 / FK-R-10 rows of the same interval.
    Declarations never enter here: a declared hold does not excuse the length (design 7.5)."""
    rid = rule.get("id", "?")
    prob = _rule_problem(rule)
    if prob:
        return [undet(f"FK-R-16#{rid}", "range_rule", "rule", prob)], []
    src = rule["select"]["source"]
    anchor = rule["select"].get("anchor", "any")
    where = "audio" if src == "silent" else "picture"
    lo, hi = float(rule["range_s"][0]), float(rule["range_s"][1])
    floor_key = src
    if src == "frozen" and anchor == "end" and "frozen_end" in floors:
        floor_key = "frozen_end"
    elif src == "frozen" and anchor in ("start", "first") and "frozen_start" in floors:
        floor_key = "frozen_start"
    floor = floors.get(floor_key)
    fl = f"{floor:g}" if floor is not None else "?"
    basis = str(rule.get("basis") or "")
    suffix = PROVISIONAL_SUFFIX if rule.get("provisional") else ""
    hits = select_intervals(rule, scan, video_end, film_end)

    def say(key, **kw):
        tpl = rule.get(key)
        if not tpl:
            return None
        return tpl.format(floor_s=fl, basis=basis, **kw) + suffix

    rows = []
    try:
        if not hits:
            ok_missing = rule.get("missing_ok") is True        # PSM 4.5: nothing matched is a legal state for this rule
            r = row(f"FK-R-16#{rid}", "range_rule", "rule", "PASS" if ok_missing else "WARN", None if ok_missing else "look",
                    measured="not detected", expected=f"{lo:g}–{hi:g} s", basis=basis or f"rules file entry {rid}",
                    where="file", duration=video_end, milestone="M2",
                    message_key="range_rule.missing_ok" if ok_missing else "range_rule.missing")
            r["provisional"] = bool(rule.get("provisional"))
            r["text_zh"] = say("missing_zh", measured="", t0="", t1="")
            rows.append(r)
            return rows, []
        for k, iv in enumerate(hits, 1):
            d = iv.t1 - iv.t0
            ok = lo - EPS <= d <= hi + EPS
            r = trow(f"FK-R-16#{rid}" + (f"#{k}" if anchor == "any" else ""), "range_rule", "rule",
                     "PASS" if ok else "WARN", None if ok else "look", where, iv.t0, iv.t1,
                     measured=_tspan(iv.t0, iv.t1) + (", runs to the end of the film" if iv.open_at_end else ""),
                     expected=f"{lo:g}–{hi:g} s", basis=basis or f"rules file entry {rid}",
                     message_key="range_rule.ok" if ok else "range_rule.out")
            r["provisional"] = bool(rule.get("provisional"))
            r["open_at_end"] = bool(iv.open_at_end)
            r["text_zh"] = say("sentence_zh", measured=f"{d:.2f}", t0=f"{iv.t0:.2f}", t1=f"{iv.t1:.2f}")
            rows.append(r)
    except (KeyError, IndexError, ValueError) as e:
        return [undet(f"FK-R-16#{rid}", "range_rule", "rule", f"rule sentence uses a placeholder this kit does not know: {e}")], []
    return rows, [(src, iv) for iv in hits]


PROVISIONAL_SUFFIX = PARTIAL_WORD


def _rule_rows(rules, rules_error, spec, scan, video_end, film_end, th) -> tuple[list[dict], list[tuple]]:
    if rules_error:
        return [undet("FK-R-16", "range_rule", "rule", f"rules file unreadable: {rules_error}")], []
    if rules is None:
        return [], []
    ft = spec.film_type
    vocab = rules.get("film_types")
    if ft is not None and isinstance(vocab, list) and ft not in vocab:
        return [undet("FK-R-16", "range_rule", "rule", f"film type not in vocabulary: {ft}")], []
    floors = {"black": float(th.get("black", {}).get("min_duration_s", 0)),
              "frozen": float(th.get("freeze", {}).get("min_duration_s", 0)),
              "frozen_end": freeze_floor(th, at_end=True),
              "silent": float(th.get("silence", {}).get("min_duration_s", 0))}
    if start_window(th) is not None:       # without a window no still is held to the head floor, so none is named
        floors["frozen_start"] = freeze_floor(th, at_start=True)
    rows, matched = [], []
    for rule in rules.get("rules") or []:
        if not isinstance(rule, dict) or rule.get("owner") != "filmkit":
            continue                           # other owners' entries are never evaluated and produce no row (P-19a)
        rid = rule.get("id", "?")
        if rule.get("kind") != "range":
            rows.append(undet(f"FK-R-16#{rid}", "range_rule", "rule", f"rule kind not supported by this kit: {rule.get('kind')}"))
            continue
        types = rule.get("film_types")
        if types is not None:
            if ft is None:
                rows.append(undet(f"FK-R-16#{rid}", "range_rule", "rule",
                                  f"no film type given; the rule applies to: {', '.join(map(str, types))}"))
                continue
            if ft not in types:
                continue
        r, m = range_compare(rule, scan, video_end, film_end, floors)
        rows += r
        matched += m
    return rows, matched


# ---------------------------------------------------------------------------------------------------- assembly
def _content_rows(*, decls, facts, scan, spec, plan, plan_decls, record, rules, rules_error, profile, dur, target=None):
    """FK-R-7..12, FK-R-15, FK-R-16 and FK-R-17 for one evaluation. `decls` are the declarations that exempt (empty in the
    second BR-6 run); FK-R-15 reads the plan's declarations either way (M2 reading 1)."""
    th = profile.get("thresholds", {})
    log: dict = {}
    state, reason, unfinished = _scan_state(facts, scan)
    has_audio = bool(facts.audio)
    fps = facts.fps_avg or spec.fps or 30
    video_end, film_end = video_end_of(facts), film_end_of(facts)
    c712, c16 = [], []
    if state != "ok":
        c712 = _undet_content(facts, reason, unfinished, has_audio, state)
        if rules is not None or rules_error:
            c16 = [undet("FK-R-16", "range_rule", "rule", reason, unfinished)]
        if has_audio or state in ("timeout", "unreadable"):
            c16.append(undet("FK-R-17", "loudness", "rule", reason, unfinished))
    else:
        c16, matched = _rule_rows(rules, rules_error, spec, scan, video_end or 0.0, film_end or 0.0, th)
        c16 += _loudness_rows(facts, scan, rules, rules_error, target, dur)
        rule_frozen = [iv for src, iv in matched if src == "frozen"]
        rule_cover0 = any(iv.t0 <= 0.5 / fps and iv.t1 > 0 for src, iv in matched if src in ("frozen", "black"))
        black_rows = _interval_rows("black", scan.black, decls, th, dur, log)
        fz_floor = float(th.get("freeze", {}).get("min_duration_s", 0))

        def frozen_skip(iv) -> bool:
            if any(abs(iv.t0 - m.t0) < EPS and abs(iv.t1 - m.t1) < EPS for m in rule_frozen):
                return True                       # the interval is listed by a rule row (design 7.5 priority)
            rest = _subtract(iv.t0, iv.t1, [(b.t0, b.t1) for b in scan.black])
            return not any(b - a >= fz_floor - TOL for a, b in rest)       # covered by FK-R-7

        c712 += black_rows
        c712 += _local_motion_rows(scan, th)
        long_frozen = [iv for iv in scan.frozen if iv.t1 - iv.t0 >= fz_floor - TOL]   # shorter = end-only (D18)
        c712 += _interval_rows("frozen", long_frozen, decls, th, dur, log, skip=frozen_skip)
        c712 += _silent_rows(facts, scan, spec, decls, th, dur, log)
        covered = rule_cover0 or any(iv.t0 <= 0.5 / fps and iv.t1 > 0 for iv in list(scan.black) + long_frozen)
        c712 += _first_frame_rows(facts, scan, th, covered)
    c712 += _animation_rows(record, dur) + _seek_rows(record, dur)
    c15 = _conflict_rows(plan, plan_decls, facts, fps)
    return c712, c15, c16, log


M0_ROW_IDS = [("FK-R-1", "container_readable", "format"), ("FK-R-2", "duration", "format"),
              ("FK-R-3", "frame_geometry", "format"), ("FK-R-4", "pixel_format_codec", "format"),
              ("FK-R-5", "audio_presence", "format"), ("FK-R-6", "page_load_errors", "content"),
              ("FK-R-13", "render_provenance", "content")]
ALL_ROW_IDS = M0_ROW_IDS[:6] + CONTENT_ROW_IDS + M0_ROW_IDS[6:] + [("FK-R-17", "loudness", "rule")]

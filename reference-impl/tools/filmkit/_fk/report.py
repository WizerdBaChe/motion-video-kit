"""check.json, check.md (zh) from it, events projection (PSM 4.3, 6.6; FK-INV-11)."""
from __future__ import annotations

import re
from pathlib import Path

from . import messages_zh as mz
from .common import EXIT_BLOCKING, EXIT_INCOMPLETE, EXIT_OK, write_bytes_atomic, write_json_atomic
from .types import CheckResult, CheckSummary, OutputNames, ReportMeta, SheetResult

ORDER = ("blocking", "confirmed", "look", "undetermined")
PLACEHOLDER_RE = re.compile(r"<(?:page|new-out|S|WxH|audio)>")


def summarize(rows: list[dict], internal_error: str | None, look_without: int | None = None) -> CheckSummary:
    """look_without: the second BR-6 count (rows that would be 'look' with no declarations); None -> equals look."""
    c = {b: sum(1 for r in rows if r["bucket"] == b) for b in ORDER}
    incomplete = any(r.get("unfinished") for r in rows) or internal_error is not None
    return CheckSummary(blocking=c["blocking"], look=c["look"], undetermined=c["undetermined"],
                        confirmed=c["confirmed"],
                        look_without_exemptions=c["look"] if look_without is None else look_without,
                        incomplete=incomplete, internal_error=internal_error)


def code_for(summary: CheckSummary) -> int:
    if summary.blocking:
        return EXIT_BLOCKING
    if summary.incomplete:
        return EXIT_INCOMPLETE
    return EXIT_OK


def events_of(rows: list[dict]) -> list[dict]:
    """Projection of timed rows; whole-file rows (where == file) never enter events (design 5.7)."""
    ev = []
    for r in rows:
        if r.get("where") == "file":
            continue
        if r.get("t0") is not None and r.get("t1") is not None:
            ev.append({"kind": "span", "start": r["t0"], "end": r["t1"], "t": (r["t0"] + r["t1"]) / 2,
                       "event": r["name"], "row": r["id"]})
        elif r.get("t") is not None:
            ev.append({"t": r["t"], "event": r["name"], "row": r["id"]})
    return ev


def build_check_json(rows: list[dict], meta: ReportMeta, names: OutputNames, font_moments: list | None) -> dict:
    summary = summarize(rows, meta.internal_error, meta.look_without_exemptions)
    return {
        "schema_version": 1, "generator": "filmkit", "file": meta.file, "render_record": meta.render_record,
        "plan": meta.plan, "expected": meta.expected, "profile": meta.profile, "kit_hash": meta.kit_hash,
        "rules": meta.rules, "outputs": {"json": names.json, "md": names.md, "sheet": names.sheet},
        "probe": meta.probe, "rows": rows, "events": meta.events or events_of(rows), "exemptions": meta.exemptions,
        "exemption_totals": meta.exemption_totals,
        "font_sampling": {"moments": font_moments} if font_moments else None,
        "summary": summary.to_json(), "exit_code": code_for(summary),
    }


def _sentence(r: dict) -> str:
    key = r.get("message_key") or ""
    f = {"measured": mz.zh(r.get("measured")), "expected": mz.zh(r.get("expected")), "basis": mz.zh(r.get("basis")),
         "reason": mz.zh(r.get("reason")), "name": mz.NAMES.get(r.get("name"), r.get("name"))}
    if key.startswith("pixel_format_codec.mismatch:"):
        parts = key.split(":", 1)[1].split("+")
        f["clauses"] = "；".join(mz.CLAUSES.get(p, p) for p in parts)
        key = "pixel_format_codec.mismatch"
    if r.get("text_zh"):
        return r["text_zh"]            # a rule row: the sentence comes from the rules file (it carries its own basis)
    tpl = mz.TEMPLATES.get(key) or mz.TEMPLATES["undetermined"]
    return tpl.format(**f)


def _num(x) -> str:
    return f"{x:.2f}" if isinstance(x, (int, float)) else "?"


def _declared_section(check_json: dict) -> list[str]:
    """Section five (design 6.1): every declaration the author made, what it exempted, and the two counts (BR-6)."""
    out = [mz.SECTIONS["declared"], ""]
    ex = check_json.get("exemptions") or []
    if not ex:
        return out + [mz.NONE, ""]
    for e in ex:
        ids = "、".join(e.get("exempted_rows") or [])
        out.append("- " + mz.SECTION5_ITEM.format(
            t0=_num(e.get("t0")), t1=_num(e.get("t1")), type=mz.DECL_TYPES.get(e.get("type"), e.get("type")),
            why=e.get("why"), n=len(e.get("exempted_rows") or []), ids=mz.IDS_NOTE.format(ids=ids) if ids else "",
            secs=_num(e.get("exempted_s"))))
    tot = check_json.get("exemption_totals")
    if tot:
        share = f"{tot['share_of_film'] * 100:.1f} %" if tot.get("share_of_film") is not None else mz.SECTION5_SHARE_UNKNOWN
        s = check_json.get("summary") or {}
        out.append("- " + mz.SECTION5_TOTAL.format(n=tot["declarations"], secs=_num(tot["seconds"]), share=share,
                                                    look=s.get("look"), look_without=s.get("look_without_exemptions")))
    return out + [""]


def render_md(check_json: dict) -> str:
    """Pure function of check.json (FK-INV-11)."""
    lines = [mz.FIRST_LINE, "", f"檔案：`{check_json['file']['name']}`（sha256 {str(check_json['file'].get('sha256'))[:12]}）", ""]
    rows = check_json.get("rows", [])
    moments = (check_json.get("font_sampling") or {}).get("moments")
    for b in ORDER:
        lines.append(mz.SECTIONS[b])
        lines.append("")
        sel = [r for r in rows if r["bucket"] == b and not r["id"].startswith("FK-R-14")]   # FK-R-14 is section five
        if not sel:
            lines.append(mz.NONE)
        for r in sel:
            prefix = ""
            if b == "look":
                where = mz.WHERE.get(r.get("where"), r.get("where"))
                if r.get("where") == "file":
                    prefix = mz.WHOLE_FILE.format(t0=_num(r.get("t0")), t1=_num(r.get("t1"))) + f"／{where}／"
                elif r.get("t0") is None and r.get("t") is not None:
                    prefix = f"第 {_num(r.get('t'))} 秒／{where}／"
                else:
                    prefix = f"第 {_num(r.get('t0'))}–{_num(r.get('t1'))} 秒／{where}／"
            lines.append(f"- {prefix}{_sentence(r)}")
            if r.get("rerun"):
                lines.append(f"  {mz.RERUN_LABEL}`{r['rerun']}`")
                ph = sorted(set(PLACEHOLDER_RE.findall(r["rerun"])), key=r["rerun"].index)
                if ph:
                    note = mz.PLACEHOLDER_NOTE.format(names="、".join(f"`{p}`" for p in ph))
                    if "<new-out>" in ph:
                        note += mz.NEW_OUT_NOTE
                    lines.append(f"  {note}")
            if r.get("rerun_note"):             # a file written by transform.py has no re-render command (PSM 4.3 rule 7)
                lines.append(f"  {mz.zh(r['rerun_note'])}")
            if r["id"] == "FK-R-6" and moments:
                lines.append(f"  {mz.FONT_COVERAGE.format(moments='、'.join(moments))}")
        lines.append("")
    lines += _declared_section(check_json)
    return "\n".join(lines).rstrip("\n") + "\n"


def write_report(rows: list[dict], meta: ReportMeta, out_dir: Path, names: OutputNames, retry: dict | None = None,
                 font_moments: list | None = None) -> CheckResult:
    cj = build_check_json(rows, meta, names, font_moments)
    out_dir = Path(out_dir)
    write_json_atomic(out_dir / names.json, cj, retry, make_fk_dir=False)
    write_bytes_atomic(out_dir / names.md, render_md(cj).encode("utf-8"), retry, make_fk_dir=False)
    summary = summarize(rows, meta.internal_error, meta.look_without_exemptions)
    return CheckResult(rows=rows, summary=summary, exit_code=code_for(summary), outputs=names,
                       sheet=SheetResult(False, None, "not run"), check_json=cj)

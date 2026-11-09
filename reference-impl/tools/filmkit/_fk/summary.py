"""The five stdout lines and the exit code (design 5.2, 7.4; FK-INV-13)."""
from __future__ import annotations

from pathlib import Path

from .common import EXIT_BLOCKING, EXIT_INCOMPLETE, EXIT_NO_OUTPUT, EXIT_OK, one_line
from .types import CheckResult, RunSummary

DONE_STATES = ("DONE", "CHECKED")


def _at(folder: str, name: str) -> str:
    # an absolute --out-prefix makes the output name absolute; checkrun joins it the same way (Path / absolute)
    return Path(name).as_posix() if Path(name).is_absolute() else folder + name


def _fmt(v, spec="{}", unknown="?"):
    return unknown if v is None else spec.format(v)


def _steps(state: RunSummary) -> str:
    parts = [name if ok else f"{name} (failed)" for name, ok in state.steps]
    s = " -> ".join(parts) if parts else "none"
    if not state.published and state.final_state not in DONE_STATES:
        s += "; nothing published"
    return s


def _notes(items) -> str:
    items = [one_line(x, 400) for x in items if x]
    return one_line("; ".join(items), 1500) if items else "none"


def five_lines(state: RunSummary, check: CheckResult | None) -> list[str]:
    if state.final_state in DONE_STATES:
        if state.final_state == "CHECKED" and state.n_frames is None and state.width is None:
            head = f"Done: checked {state.out_path} — container not readable"
        else:
            verb = "checked " if state.final_state == "CHECKED" else ""
            head = (f"Done: {verb}{state.out_path} — {_fmt(state.duration_s, '{:.2f}')} s, {_fmt(state.n_frames)} frames, "
                    f"{_fmt(state.width)}x{_fmt(state.height)}, {_fmt(state.fps, '{:g}')} fps, "
                    f"{_fmt(state.video_codec)}/{_fmt(state.pix_fmt)}, {state.audio_desc or 'no audio'}")
        if check is None:
            chk = "Check: not run"
            look = "Look: not available (check did not run)"
        else:
            s = check.summary
            jpath = _at(state.display_dir, check.outputs.json)
            where = jpath if check.check_json is not None else f"{jpath} not written"
            chk = f"Check: {s.blocking} blocking, {s.look} need a look, {s.undetermined} undetermined — {where}"
            if check.sheet.ok:
                look = f"Look: sheet at {_at(state.display_dir, check.outputs.sheet)} (pixels not judged by this tool)"
                if check.sheet.note:
                    look += f"; {check.sheet.note}"
            else:
                look = f"Look: sheet failed: {one_line(check.sheet.error or 'unknown', 200)}"
        notes = list(state.notes)
        if check is not None:
            notes += list(check.notes)
            if check.summary.internal_error:
                notes.append(f"internal error after publish: {check.summary.internal_error}")
        return [one_line(head, 400), f"Steps: {_steps(state)}", chk, look, f"Notes: {_notes(notes)}"]
    kind = state.kind or "internal"
    msg = state.message or kind
    notes = [f"hint: {state.hint}"] if state.hint else []
    if state.previous_kept:
        notes.append(f"previous {state.out_path} kept, marked stale")
    notes += list(state.notes)
    return [one_line(f"Failed: {kind} — {msg}", 600), f"Steps: {_steps(state)}", "Check: nothing to verify",
            "Look: not needed", f"Notes: {_notes(notes)}"]


def exit_code(state: RunSummary, check: CheckResult | None) -> int:
    if state.final_state not in DONE_STATES:
        return EXIT_NO_OUTPUT
    if check is None:
        return EXIT_INCOMPLETE
    if check.summary.blocking:
        return EXIT_BLOCKING
    if check.summary.incomplete:
        return EXIT_INCOMPLETE
    return EXIT_OK


def audio_desc(audio: dict | None) -> str:
    if not audio:
        return "no audio"
    ch = audio.get("channels")
    lay = {1: "mono", 2: "stereo"}.get(ch, f"{ch}ch")
    return f"{audio.get('codec')} {lay}"

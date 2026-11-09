"""kind -> English message/hint templates for the Failed: and Notes: lines (PSM 6.7, design 5.3).

Templates take fields from the raised error; a field the error did not give falls back to the default text.
"""
from __future__ import annotations

KINDS: dict[str, dict[str, str]] = {
    "spec_invalid": {
        "message": "{detail}",
        "hint": "fix the flag or plan field named above; see --help for the full flag list",
    },
    "output_foreign": {
        "message": "{detail}",
        "hint": "choose another output name, or move the existing file away yourself",
    },
    "busy": {
        "message": "another filmkit process holds {folder}",
        "hint": "wait for it to finish, or end that process, then rerun",
    },
    "env": {
        "message": "{detail}",
        "hint": "install or repair the missing program; check with: ffmpeg -version, ffprobe -version, python -m playwright install chromium",
    },
    "page_contract": {
        "message": "{detail}",
        "hint": "define window.__setTime(t) that sets the state for time t (seconds)",
    },
    "asset_load": {
        "message": "{detail}",
        "hint": "put the file under the page folder and reference it with a relative URL",
    },
    "not_ready": {
        "message": "{detail}",
        "hint": "make window.__ready settle within --ready-timeout seconds (now {ready_timeout_s} s), or raise --ready-timeout",
    },
    "page_runtime": {
        "message": "{detail}",
        "hint": "the page threw at the frame named above; reproduce it by calling window.__setTime(t) with that t",
    },
    "encode": {
        "message": "{detail}",
        "hint": "ffmpeg stopped; its last stderr lines are quoted above",
    },
    "verify": {
        "message": "{detail}",
        "hint": "the encoded file did not match the expected frame count or size; rerun, and report it with render.json if it repeats",
    },
    "publish": {
        "message": "{detail}",
        "hint": "close the program that has the output file open (player, antivirus, sync software) and rerun",
    },
    "timeout": {
        "message": "{detail}",
        "hint": "the output name was not taken; raise --timeout (now {timeout_s} s) or shorten the film",
    },
    "interrupted": {
        "message": "{detail}",
        "hint": "the output name was not taken; rerun the same command to finish",
    },
    "internal": {
        "message": "{detail}",
        "hint": "attach render.json to a bug note",
    },
}


class _Default(dict):
    def __missing__(self, key):
        return "?"


def render(kind: str, message: str | None = None, hint: str | None = None, **fields) -> tuple[str, str]:
    t = KINDS.get(kind, KINDS["internal"])
    f = _Default(fields)
    f.setdefault("detail", message or kind)
    msg = message if message else t["message"].format_map(f)
    h = hint if hint else t["hint"].format_map(f)
    return msg, h

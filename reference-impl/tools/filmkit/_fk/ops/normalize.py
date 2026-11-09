"""normalize: bring the integrated loudness and the true peak of the audio to targets the caller names (M3).

Explicit opt-in only (BR-14, FK-INV-17): transform.py runs it when called by name, always into a new file. The targets
come from the caller: `--target-lufs X --true-peak Y`, or `--rules F --target NAME` (a named entry of the rules file).
This module holds no target value and no default (FK-INV-12). The only numbers here are the ranges ffmpeg's loudnorm
filter accepts (ffmpeg -h filter=loudnorm: I from -70 to -5, TP from -9 to 0, LRA from 1 to 50).

Method (two passes, validated on synthetic signals before it was written): pass 1 measures the input with the same
`ebur128` filter the checks use; pass 2 runs `loudnorm` in linear mode with those measured values, so the loudness the
check reports is the loudness the filter aimed at. loudnorm's own first pass reads a different gating and missed the
target by 0.8 LU on a two-level signal. The audio is resampled back to the input's rate (loudnorm works at 192 kHz).
"""
from __future__ import annotations

import json
import math
import re
import subprocess
import time
from pathlib import Path

from ..common import SpecInvalid, Timeout, sha256_file
from ..scan import EBUR128_AF, parse_loudness
from ..types import ProbeFacts

NAME = "normalize"
HELP = "bring integrated loudness and true peak to named targets (new file; video copied unchanged)"

I_RANGE = (-70.0, -5.0)         # ffmpeg loudnorm option limits, not targets
TP_RANGE = (-9.0, 0.0)
LRA_RANGE = (1.0, 50.0)
JSON_RE = re.compile(r"\{[^{}]*\"output_i\"[^{}]*\}", re.S)


def add_arguments(parser) -> None:
    parser.add_argument("--target-lufs", type=float, metavar="X", help="integrated loudness target, LUFS")
    parser.add_argument("--true-peak", type=float, metavar="Y", help="true peak ceiling, dBTP")
    parser.add_argument("--rules", metavar="F", help="rules file holding named loudness targets")
    parser.add_argument("--target", metavar="NAME", help="name of a loudness target in --rules")


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def validate(ns, rules: dict | None) -> dict:
    explicit = ns.target_lufs is not None or ns.true_peak is not None
    named = ns.target is not None or getattr(ns, "rules", None) is not None
    if explicit and named:
        raise SpecInvalid("both explicit targets and a named rules-file target were given",
                          hint="give --target-lufs and --true-peak, or --rules and --target, not both")
    from_rules = None
    if named:
        if ns.target is None or getattr(ns, "rules", None) is None or rules is None:
            raise SpecInvalid("a named target needs both --rules and --target",
                              hint="give --rules <rules file> and --target <name of an entry in its targets>")
        entry = (rules.get("targets") or {}).get(ns.target) if isinstance(rules.get("targets"), dict) else None
        if not isinstance(entry, dict) or not _num(entry.get("lufs")) or not _num(entry.get("true_peak")):
            raise SpecInvalid(f"target {ns.target!r} is not a complete entry (lufs, true_peak) in the rules file",
                              hint="name an entry of the rules file's targets, or give --target-lufs and --true-peak")
        lufs, tp = float(entry["lufs"]), float(entry["true_peak"])
        from_rules = {"rules": Path(ns.rules).resolve().as_posix(), "rules_sha256": sha256_file(Path(ns.rules)),
                      "target": ns.target}
    elif explicit:
        if ns.target_lufs is None or ns.true_peak is None:
            raise SpecInvalid("--target-lufs and --true-peak must be given together", hint="give both values")
        lufs, tp = float(ns.target_lufs), float(ns.true_peak)
    else:
        raise SpecInvalid("no loudness target given (there is no default)",
                          hint="give --target-lufs X --true-peak Y, or --rules F --target NAME")
    if not (I_RANGE[0] <= lufs <= I_RANGE[1]) or not (TP_RANGE[0] <= tp <= TP_RANGE[1]):
        raise SpecInvalid(f"target {lufs:g} LUFS / {tp:g} dBTP is outside what the loudnorm filter accepts "
                          f"(LUFS {I_RANGE[0]:g} to {I_RANGE[1]:g}, true peak {TP_RANGE[0]:g} to {TP_RANGE[1]:g})",
                          hint="give a target inside those ranges")
    return {"target_lufs": lufs, "true_peak": tp, "from_rules": from_rules}


def check_input(params: dict, facts: ProbeFacts) -> None:
    if not facts.audio:
        raise SpecInvalid("the input has no audio stream to normalize", hint="give a file that has an audio track")


def measure(file: Path, deadline: float) -> dict:
    """ebur128 summary of the first audio stream: {integrated_lufs, threshold_lufs, lra_lu, true_peak_db}."""
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise Timeout("transform exceeded --timeout before the loudness measurement")
    argv = ["ffmpeg", "-hide_banner", "-nostats", "-i", str(file), "-map", "0:a:0", "-af", EBUR128_AF, "-f", "null", "-"]
    try:
        r = subprocess.run(argv, capture_output=True, timeout=remaining)
    except subprocess.TimeoutExpired:
        raise Timeout("transform exceeded --timeout during the loudness measurement")
    text = r.stderr.decode("utf-8", "replace")
    got = parse_loudness(text)
    if r.returncode != 0 or got is None:
        tail = [x for x in text.strip().splitlines() if x.strip()]
        raise SpecInvalid(f"loudness measurement failed: {tail[-1] if tail else 'no ebur128 summary'}",
                          hint="the audio could not be measured; check it with check.py")
    return got


def analyse(src: Path, params: dict, facts: ProbeFacts, deadline: float) -> dict:
    m = measure(src, deadline)
    i = m["integrated_lufs"]
    if not math.isfinite(i) or i <= I_RANGE[0]:
        raise SpecInvalid(f"the input audio is silent (integrated loudness {i:g} LUFS): nothing to normalize",
                          hint="give an input whose audio is not silent")
    return {"measured_i": i, "measured_tp": m["true_peak_db"], "measured_lra": m["lra_lu"],
            "measured_thresh": m["threshold_lufs"]}


def build_filter(params: dict, facts: ProbeFacts) -> list[str]:
    a = params["analysis"]
    lra = min(LRA_RANGE[1], max(LRA_RANGE[0], round(a["measured_lra"] + 0.1, 1)))
    flt = (f"loudnorm=I={params['target_lufs']:g}:TP={params['true_peak']:g}:LRA={lra:g}"
           f":measured_I={a['measured_i']}:measured_TP={a['measured_tp']}:measured_LRA={a['measured_lra']}"
           f":measured_thresh={a['measured_thresh']}:linear=true:print_format=json")
    out = ["-af", flt]
    rate = (facts.audio or {}).get("sample_rate")
    if rate:
        out += ["-ar", str(rate)]
    return out


def result(partial: Path, params: dict, analysis: dict, stderr: str, deadline: float) -> dict:
    """What the filter reported and what the written partial measures; facts for the record, no verdict."""
    m = JSON_RE.search(stderr or "")
    filt = None
    if m:
        try:
            j = json.loads(m.group(0))
            filt = {"normalization_type": j.get("normalization_type"), "output_i": j.get("output_i"),
                    "output_tp": j.get("output_tp")}
        except ValueError:
            filt = None
    after = measure(partial, deadline)
    fin = lambda v: v if math.isfinite(v) else None          # -inf is not valid JSON
    note = (f"measured after: integrated {after['integrated_lufs']:.1f} LUFS, true peak {after['true_peak_db']:.1f} dBTP "
            f"(aimed at {params['target_lufs']:g} LUFS, {params['true_peak']:g} dBTP)")
    return {"loudnorm": filt, "note": note,
            "after": {"integrated_lufs": fin(after["integrated_lufs"]), "true_peak_db": fin(after["true_peak_db"]),
                      "lra_lu": fin(after["lra_lu"])}}

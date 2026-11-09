"""Operations of transform.py (PSM 6.8, design 7.2). One module per operation, one entry per module in OPERATIONS.

Adding an operation = a new module here + one line in the table below; transform.py and transform_core.py do not
change (D24). An operation module provides:

    NAME: str                                   the sub-command name
    HELP: str                                   one line for --help
    add_arguments(parser) -> None               its own flags; no flag has a default target value (FK-INV-17)
    validate(ns, rules) -> dict                 the params to record; SpecInvalid when a required value is missing
    build_filter(params, facts) -> list[str]    ffmpeg output options (filters, audio rate); params carries "analysis"

and may provide, all optional:

    check_input(params, facts) -> None          SpecInvalid when this input cannot take the operation
    analyse(src, params, facts, deadline) -> dict   measured values the filter needs (a first pass over the input)
    result(partial, params, analysis, stderr, deadline) -> dict   facts about the written partial, for the record

The caller (transform_core) owns the lock, the record, the partial file, the format verification and the publish
sequence; an operation only decides what ffmpeg does to the audio. The video stream is always copied unchanged.
"""
from __future__ import annotations

from . import normalize

OPERATIONS = {
    normalize.NAME: normalize,
}

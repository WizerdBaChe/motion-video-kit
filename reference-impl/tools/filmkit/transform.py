"""filmkit transform.py: run one explicitly named operation on a video file and write the result as a new file.

Thin entry: everything is in _fk/transform_core.py and the operation modules under _fk/ops/ (D24: a new operation is a
new module plus one table entry; this file does not change). render.py and check.py never reach this code (FK-INV-17).
"""
from __future__ import annotations

import sys
from pathlib import Path

KIT = Path(__file__).resolve().parent
if str(KIT) not in sys.path:
    sys.path.insert(0, str(KIT))

from _fk.transform_core import main

if __name__ == "__main__":
    sys.exit(main())

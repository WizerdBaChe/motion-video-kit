"""Production defaults (runtime-hashed). Provisional, model-chosen (design D-T10, D-T23; PSM 4.4, 4.10).

Thresholds that belong to the shared rules file (params.timeline) are NOT here (BR-14 single source).
"""

# Narration and film edges (design 6.3 step 2, D-T10; tail D-T23). Per-film overrides live in meta.
LEAD_S = 1.0
TAIL_S = 2.0
LINE_GAP_S = 0.45
SECTION_GAP_S = 1.2

# Rate estimate for narration lines without audio (PSM 4.4): only for the dashed preview; never approvable.
EST_HAN_PER_S = 4.0
EST_OTHER_PER_S = 12.0
EST_MIN_S = 0.8

# SEM-4 cut tolerance: a semantic constant of the format (T08), kept in code so TV-2 runs without the rules file.
CUT_TOLERANCE_S = 0.15

# Comparison slack for unsnapped quantities (PSM 6.7 step 7) and the TV-7 endpoint tolerance (PSM 7).
SLACK_S = 1e-9
RANGE_TOL_S = 1e-6

# TV-1: an author-written fixed duration counts as whole frames within this many frames (PSM 4.1).
WHOLE_FRAME_TOL = 1e-3

# Changelog

All notable changes to this repository. Versions follow semantic versioning: minor = new capability,
patch = fix. Format after Keep a Changelog.

## [1.0.0] - 2026-11-10

First public release.

### Added

- Skill `motion-video`: router, the ten-step order of work, five method documents (whole-film rules, film
  types, rhythm / transitions / camera, build and export, evidence and instruments) and the element-level
  motion-parameter table, as a byte copy of the origin (`reference-impl/`).
- `tools/timeline/`: the director-sheet layer (`tl.py` validate --static / resolve / validate --timed / view /
  approve), schema, components and a selftest (201 checks).
- `tools/filmkit/`: `render.py`, `check.py`, `transform.py`, the rules file with its selftest (43 checks) and
  the filmkit smoke selftest (45 checks).
- `tools/review/`: the review loop (gates G0-G3, refusal rules) with a selftest (43 checks).
- `tools/edit/`: the edit route (EDL / OTIO, asset provenance) with a selftest (16 controls).
- 27 measuring instruments, each with `--selftest`.
- Worked example film `films/fanout-pool-explainer/` (director sheet, page, bundled fonts).
- Design and production documents under `reference-impl/docs/`.
- README (Traditional Chinese and English), `docs/DEVELOPER.md`, `docs/BUILD-SPEC.md`, `docs/EVIDENCE.md`,
  `AGENTS.md`, `llms.txt`.
- `docs/assets/`: scripts that regenerate every README image (workflow diagram, director sheet and storyboard,
  showcase animations).
- `verify/run_controls.py`: eight two-sided control groups K1-K8; `verify/controls_run.txt`: the recorded run.

### Changed from the origin (declared edits, spec section 9)

- Machine paths of the origin environment are replaced by neutral tokens; project and round names that
  identify a third party or a private location are replaced by a neutral description.
- One selftest expectation that reads the git history of the origin (a 40-hex commit id) is conditioned on a git
  checkout being present, so it holds in a plain archive.

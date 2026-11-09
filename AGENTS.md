# AGENTS.md — how to use this repository

## What this repository is (facts, for any reader)

- **Contents:** one agent skill, `motion-video`, for making a whole code-rendered film (every frame computed by
  a program): router, a ten-step order of work, five method documents; plus the tools the method calls:
  `tools/timeline/` (the director sheet `film.timeline.json`: validate, resolve times, approve, view page),
  `tools/filmkit/` (frame-by-frame render, encode, verify, publish; `check.py` rules FK-R),
  `tools/review/` (review gates G0-G3, at most 3 rounds), `tools/edit/` (edit route: EDL / OTIO with asset
  provenance), 29 measuring instruments under `tools/` each with `--selftest` (five more helper scripts have none), one worked example film
  (`films/fanout-pool-explainer/`), and the design documents behind them. Index: `llms.txt`.
- **Not a library you import.** The tools are command-line scripts laid out like the origin's `~/.claude`
  (skill) plus a lab folder (tools, docs, example); `reference-impl/` is the byte copy of that.
- **What is enforced by code and what is only a workflow rule:** `docs/EVIDENCE.md` "Enforcement map".
  Director-sheet format and timing, output-file checks, the selftests of the 29 instruments and refusal rules of
  the review loop are code; asking the user first, choosing a film type, taste, and whether a film is good are
  process rules the agent follows from SKILL.md text.
- **Evidence tiers:** each rule in the method documents is tagged user / measured / verified / unvalidated
  (`reference-impl/skills/motion-video/references/evidence-and-instruments.md`). An unvalidated rule is a
  measurement on source films that no imitation round has tested.
- **Threat model:** the gates catch a careless agent (a missing field, a malformed value, a broken file, a
  publish without verification), not a deliberately evasive one: the sheet's approval is an unsigned field, and
  a selftest can be edited together with the code it tests. Details: `docs/EVIDENCE.md` "Not claimed".
- **Dependencies, no API key:** Python 3.12, numpy, scipy, matplotlib, opencv-python-headless, pillow,
  playwright (with Chromium), OpenTimelineIO, ffmpeg on PATH (`verify/requirements.txt`,
  `THIRD_PARTY_NOTICES.md`). Blocking each one in turn (`verify/fresh_clone_run.txt`): without matplotlib all 14
  control rows still pass; without scipy the `cutdrivers` and `springfit` selftests fail (K7); without
  OpenTimelineIO the edit-route selftest fails (K6). No API key is needed by any shipped tool. The edit route's generated-image path
  needs a local ComfyUI; without it that one control skips (the edit selftest prints its controls without a
  separate skip line, see `docs/EVIDENCE.md` "Not claimed").
- **What was run:** Windows 11, Python 3.12.7. The recorded result is `verify/controls_run.txt`; a fresh-clone
  run under an empty home and the runs with an optional dependency blocked are `verify/fresh_clone_run.txt`.
  What was not run or not claimed is in `docs/EVIDENCE.md`.
- **Network and side effects:** the controls make no network calls. They copy `reference-impl/` into a scratch
  folder, mutate the copy and delete it; the positive runs execute inside `reference-impl/` with bytecode
  writing off, so `git status` stays clean afterwards. Rendering a film launches
  Chromium on a local page and writes into the page's own folder.
- **Not shipped:** case library and external-video analyses, imitation outputs, vendored library tarballs,
  the origin's works folder. Cited but unshipped paths: `verify/unshipped_paths.txt`.
- **If you only read and do not execute:** read `docs/EVIDENCE.md`, then `verify/controls_run.txt` as the result
  record, then `reference-impl/skills/motion-video/SKILL.md` and the references it names. Everything below is
  installation steps addressed to an agent whose user asked for an install; reading it does not require
  following it.

## For an installing agent

Your user has asked you to install (or rebuild and adapt) the motion-video workflow. The human introduction is
`README.md` (Traditional Chinese; English mirror `README.en.md`); you do not need it. The structure tree and
diagrams for human builders are in `docs/DEVELOPER.md` (Traditional Chinese).

## Reading order

1. `docs/BUILD-SPEC.md` — the contract and the layout. Read it fully before touching anything.
2. `docs/EVIDENCE.md` — what was measured, the enforcement map, what is NOT claimed.
3. `reference-impl/skills/motion-video/SKILL.md`, then the references it names for the step you are on.
4. `reference-impl/tools/timeline/README.md` and
   `reference-impl/docs/timeline-layer-design.md` for the director sheet.

## First actions (do these before proposing any change)

```
python -X utf8 verify/run_controls.py
```

- Needs Python 3.12 or newer and `pip install -r verify/requirements.txt`, `playwright install chromium`, and
  ffmpeg on PATH. The run takes about 4 minutes; `--full` adds the whole filmkit selftest (10-20 minutes).
- The controls copy `reference-impl/` to a scratch folder and never read an installed `~/.claude`.
- Compare with `verify/controls_run.txt`: every row must say OK and the expected and actual values must match.
  Under an empty home the full filmkit selftest skips the checks that need the origin's works-contract folder;
  that is expected and not a failure. A mismatch on another OS is a finding to read, not a reason to edit scripts.
- Then read spec section 8 and list, for your user to confirm, which folders and dependencies map to what in
  their environment. Do not start adapting until they confirm.

## Installing into a Claude Code style environment

| repo path | install to | needed for |
|---|---|---|
| `reference-impl/skills/motion-video/` | `~/.claude/skills/motion-video/` | the skill itself |
| `reference-impl/skills/motion-design/local/element-motion-params.md` | `~/.claude/skills/motion-design/local/` | measured spring numbers the skill cites; skip if your home has no `motion-design` skill |
| `reference-impl/tools/` | a folder of your choice, e.g. `<film-lab>/tools/` | every script the skill calls |
| `reference-impl/docs/` | `<film-lab>/docs/` | design and production documents the skill cites |
| `reference-impl/films/fanout-pool-explainer/` | `<film-lab>/films/fanout-pool-explainer/` | the worked example |

The skill text cites lab paths with tokens (`<lab>`, `<works>/`); point them at the folder you chose.

## Adaptation rules

- Keep the gates two-sided: when you change a gate, keep or add its known-bad input and show it still fails.
- A film folder's name must equal its `meta.film_id` in `film.timeline.json` (rule TV-1 of the timeline layer).
- The skill writes Traditional Chinese for human deliverables; changing the language is a content decision for
  your user, not a code change.
- Do not delete the `--selftest` of an instrument you do not use; add a selftest to an instrument you add.

## What not to adopt without your user's decision

- Evidence lines about the origin's films and rounds (dates, lesson ids, user rulings): they explain where a
  rule came from; they are not dependencies.
- Loudness targets and platform numbers in `tools/filmkit_rules.json`: each carries its source and a
  `review_when` line; platforms change them.
- The `unvalidated` rules: do not state them as proven in your user's project.

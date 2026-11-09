# timeline layer (`tools/timeline/`)

Lives in motion-video-lab until a second project calls it; then it moves out into its own repository (design §3.1 upgrade condition).
Format and timing checked, pictures not judged: no command here looks at a rendered frame.

One file (`films/<film_id>/film.timeline.json`) holds a film's decisions and timing. `tl.py` checks it, resolves every
anchor to frames, shows it as a page, and approves a version. Stdlib only; Python 3.12; Windows first (the film lock is
a Windows byte lock). Contract: `docs/timeline-layer-psm.md` (§3–§7); design: `docs/timeline-layer-design.md`.

## Commands (TL-0)

```
python -X utf8 tools/timeline/tl.py validate <film> --static    # TV-1/3/4a/5/8/9a/15/17 -> build/validate.json, candidate files
python -X utf8 tools/timeline/tl.py resolve <film>              # anchors -> frames -> build/timeline.resolved.json
python -X utf8 tools/timeline/tl.py validate <film> --timed     # TV-2/4b/7/10/14/19 on the resolved file
python -X utf8 tools/timeline/tl.py view <film>                 # build/timeline.html (data-page-class="dashboard")
python -X utf8 tools/timeline/tl.py approve <film> --by user --note "<the user's words>"
python -X utf8 tools/timeline/tl.py approve <film> --by model --questions build/questions.md
python -X utf8 tools/timeline/tl.py at <film> <seconds> [--version n]   # which clip and line at that second (read-only)
python -X utf8 tools/timeline/tl.py mark <film> --abandoned --note "<why>" [--version n]
python -X utf8 tools/timeline/tl.py readback <film> <n> <m>     # versions n vs m, per clip/line -> appends 作者修改紀錄.md
python -X utf8 tools/timeline/tl.py index [--check]             # rebuild components/INDEX.md and index.json
python -X utf8 tools/timeline/selftest.py [--only NAME,..] [--list] [--keep] [--verbose]
```

Common flags: `--rules F` (default `tools/filmkit_rules.json`; a missing file is not an error, the rows that need it
become `undetermined`), `--components DIR` (default `tools/timeline/components`), `--json` (one JSON document instead of
the five lines).

Order: `validate --static` → `resolve` → `validate --timed` → `view` → `approve`. A command never runs a missing step
itself; it refuses with `not_current` and names the step to run. Any edit to the timeline, `clips/`, `voice/lines.json`
or the component index turns a `VALID` draft back into `DRAFT`.

## Output

Every command prints five lines (filmkit's shape):

```
Done: <command> <film> — <result>        |  Failed: <kind> — <message>
Steps: <step> -> <step> ...
Check: <n> blocking, <n> need a look, <n> undetermined — <validate.json>
Look: <page to open, or "not needed">
Notes: <notes>; format and timing checked; pictures not judged
```

Exit codes: 0 ok; 1 refused (`spec_invalid`, `not_current`, `not_approved`, `missing_required`, `fingerprint_mismatch`,
`edited_output`, `voice_mismatch`, `env`, `busy`, `illegal_transition`, `instrument_unavailable`, `internal`);
2 blocking rows; 3 a check started but did not finish.

## Files

- `film.timeline.schema.json` documents the format; `_tl/model.py` is the authoritative validator (selftest keeps the two in
  agreement on every fixture of `schema_fixtures()`).
- `versions/<n>/` of a film is read-only and fingerprinted in its `approval.json`; an edited version file stops every command
  with `fingerprint_mismatch` until it is restored or the version is marked abandoned.
- Films live in the production root `<works>/films/<film_id>/` (2026-10-11); `<film>` is that path.
  `state.json` carries an append-only `made_by[]` (works contract W-2: stage, lab commit, dirty flag, inputs) written by
  `resolve` and `approve`; a re-resolve on unchanged inputs and an unchanged lab adds no row. `readback` (W-5) appends a
  draft to `<film>/作者修改紀錄.md`; it is evidence, never a rule by itself.
- A Claim (`<asset id>:<text>`) is checked against its `claims_ref` file (TV-9a, 2026-10-14): the text, with `**`
  removed and whitespace collapsed on both sides, must appear on one line of the source. Not found -> `look` at
  `validate`, blocking at `approve`; an unreadable source -> `undetermined`, never a pass.
- Product state and required assets (2026-10-24, `docs/convergence-build-design.md` §3), all optional:
  top-level `product_state: [{id, facts, source}]`, clip `shows_state: [ids]`, asset `required: {min_visible_s,
  no_crop}`. TV-20: a product film that declares `product_state` names a state on every `feature` clip and gives each
  state facts and a source (`look` at `validate`, blocking at `approve`; without the table one `info` row). TV-21:
  unknown state ids or non-scalar facts, blocking. TV-22: a required asset no clip names (`device.params`, `visual`,
  `what`, `speed.asset`), blocking. The page side is `filmkit/pagescan.py --timeline <film>` (QF-7, QF-8).
- `MANIFEST.txt` lists every library file; an unlisted file fails the selftest.
- After any edit under `tools/timeline/`, run `selftest.py` before committing (lab INV-8); an edit to `params.timeline` in
  `tools/filmkit_rules.json` also runs INV-7.

## Not in TL-0

Clip programs are not executed (TV-6 and TV-9b are always `undetermined`), nothing is compiled or rendered, there is no
narration recording, no music track and no component in the library yet (TL-1 onward).

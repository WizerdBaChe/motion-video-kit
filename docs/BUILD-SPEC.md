# BUILD-SPEC — motion-video-kit

Machine-read build specification (English). It is the contract of this repository: what each component must do,
how to know it does, how to adapt it, and what differs from the origin. Human introduction: `README.md`.

## 0. What it is, in one paragraph

A method and a toolchain for making a whole video whose every frame is computed by a program. The method is the
skill `motion-video` (ten steps, five reference documents, evidence-tiered rules). The toolchain is: the
director-sheet layer (`tools/timeline/`), the renderer and file checker (`tools/filmkit/`), the review loop
(`tools/review/`), the edit route (`tools/edit/`), and 29 measuring instruments (`tools/*.py`), each with a
`--selftest` (five helper or comparison scripts have none). One worked example film ships (`films/fanout-pool-explainer/`). The core artifact is the director
sheet `film.timeline.json`: decisions (who decided, on what evidence) plus per-section timing, freedom, motion
intent and key frames; everything after it is checked against it.

## 1. Components and who calls whom

| component | path | input | output | called by |
|---|---|---|---|---|
| skill | `skills/motion-video/` | the user's request | the order of work; routes to references | the agent |
| director-sheet layer | `tools/timeline/tl.py` | `films/<film_id>/film.timeline.json` | `build/validate.json`, `build/timeline.resolved.json`, `build/timeline.html`, approval state | skill step 4 |
| renderer | `tools/filmkit/render.py` | a page exposing `window.__setTime(t)` | an MP4, `render.json`, check rows | skill step 7 |
| file checker | `tools/filmkit/check.py` | an MP4 | five-line verdict, FK-R rows | render.py, or by hand |
| transform | `tools/filmkit/transform.py` | an MP4 | a derived MP4 with a reconciled record | by hand |
| review loop | `tools/review/review.py` | a film folder, gate G0-G3 | round records, verdict file | skill step 8 |
| edit route | `tools/edit/edit.py`, `edl.py` | an EDL, registered assets | a rendered cut, provenance | skill routing table |
| instruments | `tools/<name>.py` | an MP4 or a JSON | numbers with indices and time codes | skill "Verdicts" table |
| rules | `tools/filmkit_rules.json` | - | film types, rule rows, targets (each with source and `review_when`) | filmkit, timeline |

Components communicate through files in the film folder. A command that needs an earlier step refuses with
`not_current` and names the step (timeline README).

## 2. Director-sheet contract (normative; source: `docs/timeline-layer-psm.md`, schema `tools/timeline/film.timeline.schema.json`)

- One file per film, in a folder named exactly `meta.film_id` (rule TV-1).
- `decisions`: keys `film_type`, `audience`, `energy` (`calm|lively|hype`), `rhythm_source` (`narration|content`),
  `remember_one`, `ground` (`#rrggbb`), `voice`, `presentation`, `purpose`, `shown_where`, ... Each is
  `{value, source: user|model|default, evidence}`. A decision left unset is reported as a note (`decisions unset: ...`)
  and does not block.
- `sections[]`: `at`, `dur` (or an anchor), `freedom` (`locked|guided|free`), `motion_intent` lines, camera goal and
  method from fixed vocabularies, `keys[]` (`role: key|breakdown`, optional `hold`). Section seams are derived,
  never written.
- Order of commands: `validate --static` -> `resolve` -> `validate --timed` -> `view` -> `approve`. Exit 0 = no
  blocking row, exit 2 = at least one blocking row.
- Format and timing are checked; pictures are not judged.

## 3. Renderer and checker contract (normative; source: `docs/filmkit-psm.md`)

- Output is five lines (`Done|Failed`, `Steps`, `Check`, `Look`, `Notes`), or JSON with `--json`.
- `render.py` captures frame by frame from the page, encodes, verifies, and only then publishes the output name.
  Exit codes: 0 published and no blocking row; 2 published with a blocking row; 3 published but some rows could
  not finish; 1 nothing new published (previous output kept, marked stale).
- `check.py` rows have ids `FK-R-n`; severity is `blocking`, `need a look`, `info` or `undetermined`. A gate rules only
  on what it can determine; the rest is `undetermined`, never a veto.
- Profiles: `lab-round` (format fields only) and `delivery-web` (adds FK-R-18 / FK-R-19, which need the origin's
  works-contract folder and are skipped without it).

## 4. Review-loop contract (normative; source: `docs/agent-review-kbt-design.md`)

- Gates: G0 storyboard, G1 key stills, G2 key/transition windows, G3 whole film; at most 3 rounds per gate (INV-R6).
- A BLOCKER may rest only on: the fail list, a filmkit blocking row, product fidelity, a defect seen once before
  (INV-R4). Any other basis is refused. Feel is polish and never blocks.
- After round 3 the best version ships with the open items listed; the verdict file's first line names the
  reviewer (`reviewer: ...`) and states `user_watched`.

## 5. Gate design (applies to every gate here)

- A gate rules only on what it can determine; anything else is downgrade-and-forward.
- Every gate carries a known-true and a known-false input in the same invocation as the real check
  (`--selftest`); a control is proven by the asserted VALUE differing between the correct and the defective build.
- A verdict from a run that could not read a needed input says so (`undetermined` / skip), never PASS.

## 6. Build order that worked

1. `tools/filmkit/` with its smoke selftest (frame-pure page, capture, encode, verify, publish).
2. `tools/filmkit_rules.json` and its selftest.
3. `tools/timeline/` (schema first, then static validation, resolve, timed validation, view, approve).
4. The instruments, one question each, each with a synthetic known-true / known-false selftest.
5. `tools/review/` (after filmkit rows and the timeline's key frames exist).
6. `tools/edit/` (a separate route; assets must carry provenance).
7. The skill text last, citing the tools by path.

## 7. Acceptance (`verify/run_controls.py`; every row prints expected and actual values)

| id | what | expected | mutant |
|---|---|---|---|
| K1 | `reference-impl/` bytes equal `verify/reference-impl.sha256` | 141 files, 0 differ | K1-neg: one appended byte in a temp copy -> 1 file differs |
| K2 | `filmkit/selftest.py --smoke` (K2f: `--full`) | exit 0, 0 fail | built in (`[negative]` arms) |
| K3 | `filmkit_rules_selftest.py` | exit 0, 0 fail | K3-neg: rules file without the `hype-ad` film type -> non-zero |
| K4 | `tools/timeline/selftest.py` | exit 0, 0 fail | K4-neg: schema `schema_version` const changed to 2 -> non-zero |
| K5 | `tools/review/selftest.py` | exit 0, 0 fail | K5-neg: refusal id `INV-R4` renamed everywhere in review.py -> non-zero |
| K6 | `tools/edit/selftest.py` | exit 0, all controls hold | built in |
| K7 | 29 instrument `--selftest` | 29 exit 0 | K7-neg: phaselock `lock()` always answers not-locked -> non-zero |
| K8 | worked example through `tl.py validate --static`, `resolve`, `validate --timed` | exit 0 x3, 0 blocking | K8-neg: `decisions.energy.value` set to `frantic` -> exit 2, 1 blocking |

Recorded run: `verify/controls_run.txt`. Fresh-clone runs (empty HOME, USERPROFILE and CLAUDE_CONFIG_DIR; once more with
each optional dependency blocked): `verify/fresh_clone_run.txt`.

## 8. Adapt to your environment (re-check before trusting)

- **Folders.** The origin kept the skill under `~/.claude/skills/motion-video/` and the tools, docs and films in a
  lab folder. Method text cites the lab with tokens (`<lab>`, `<works>/`, `<prompt-shelf>`, `<arms-root>`,
  `<arms>/`); decide where yours live and keep the tokens consistent.
- **Dependencies.** `verify/requirements.txt`, Chromium via `playwright install chromium`, ffmpeg on PATH.
- **Works-contract folder.** `works_contract.py` of the origin (formal-item mounting; FK-R-18/19) is not shipped.
  Without it, use profile `lab-round`, or write your own contract and keep the same two rows.
- **Fonts.** Formal films bundle their fonts with `@font-face`; the example bundles Noto Sans TC and IBM Plex Mono
  subsets (OFL).
- **Loudness and platform targets** in `filmkit_rules.json` are claims with a source and `review_when`; re-check.
- **Language.** The skill writes Traditional Chinese for human deliverables; that is a content decision.
- **Generated assets.** The edit route's ComfyUI adapter needs a local ComfyUI; the mock adapter needs nothing.

## 9. Declared edits relative to the origin (everything else is byte-identical)

The maintainer's build script (kept outside this repository, in a local-only control folder) builds `reference-impl/` from three origin roots by a manifest of
`root:relpath` entries, flattened under `reference-impl/` by relative path (a collision is refused). Edits are
applied with an expected hit count; a count that does not match stops the build.

**Path tokens (regex rules, counts pinned):**

| token | stands for | replaced occurrences |
|---|---|---|
| `<lab>` | the origin's lab folder | 12 |
| `<works>/` | the origin's works folder | 9 |
| `<prompt-shelf>` | a prompt-library project folder | 3 |
| `<arms-root>` | the folder of imitation experiment rounds | 1 |
| `<arms>/` | a drive folder of experiment arms | 3 |

**Neutral wording (regex rules, counts pinned):** a book-project name (5 occurrences) -> "a book project"; the
upper-case identifier derived from that name in one selftest (4 occurrences) -> `BOOK_V1`; two other private
project names (3 occurrences each) -> neutral descriptions.

**Declared edits (single anchors, count 1 each; E1 to E7):**

| id | file | what changed |
|---|---|---|
| E1 | `tools/filmkit/selftest.py` | an optional test input pointing at a private book project's folder -> a neutral token path (the control already falls back to a fixture) |
| E2 | `tools/filmkit_rules_selftest.py` | the path of `film-types.md` -> relative to the file (`skills/` sits beside `tools/` in the kit) |
| E3 | `tools/edit/README.md` | a local ComfyUI install folder -> a placeholder |
| E4 | `docs/axes-and-pairing.md` | a third-party creator's handle and the path of its analysis -> a neutral description (an external case, not shipped) |
| E5 | `docs/agent-review-kbt-design.md` | a provenance cell naming a private research project -> "a research project"; the date is kept |
| E7 | `tools/shotstats.py` | a docstring example naming an episode of a third-party series -> "one measured episode" (the numbers are kept) |
| E6 | `tools/timeline/selftest.py` | the control that expects a 40-hex commit id in a stamp is conditioned on a git checkout, so it holds in a plain source archive |

**Derived file:** `films/fanout-pool-explainer/assets/research.md` is generated from the `research:` claim texts of the
shipped timeline; `films/fanout-pool-explainer/assets/simulation.md` is added with a declared edit. Neither is a copy of an origin file.

**Not shipped:** case library, external-video analyses, imitation outputs, vendored library tarballs, the works folder
and its contract tool, any file whose cited path is listed in `verify/unshipped_paths.txt`.

**Screen:** the build reads a private names list (not part of this repository), plants one positive for every excluded
name in the same run and requires it to fire, then requires 0 hits over all shipped text; a list that cannot be read
stops the build.

## 10. Invariants the origin records and this kit keeps

- INV-7: filmkit has a selftest with positive and negative arms. INV-8: the timeline layer has a selftest with positive
  and negative arms and a schema-agreement check. INV-9: the review loop has a selftest and refuses non-listed blockers.
- Rules carry an evidence tier (user / measured / verified / unvalidated); an unvalidated rule is never stated as proven.
- Models: the method states which model tier may make a film and which may only do mechanical steps (see SKILL.md
  "Models").

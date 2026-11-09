# tools/review — agent review loop

Design: `docs/agent-review-kbt-design.md`. The maker subagent builds the film, and the dispatching main-loop session (the director) reviews it. The two talk only through files under `<film>/review/`; the director never edits the film's code. This tool renders what gets reviewed from the film's own page, stamps each findings file with the artefacts it judges, and refuses files that break the design's rules. It never judges a picture.

## Commands

```
python -X utf8 tools/review/review.py stills  <film>             # G1: one still per key frame (role key)
python -X utf8 tools/review/review.py windows <film> [--only ID] # G2: K windows (key ±1.5 s), T windows (boundary −1.0/+1.5 s), R windows (relations)
python -X utf8 tools/review/review.py new     <film> G0|G1|G2|G3 # opens round n: findings skeleton + artefact hashes
python -X utf8 tools/review/review.py check   <film>             # refuses any file breaking INV-R4/R5/R6/R9/R10, P-4
python -X utf8 tools/review/review.py status  <film>             # per gate: NOT_STARTED / OPEN / PASSED / PASSED_WITH_OPEN
python -X utf8 tools/review/review.py log     <film>             # writes review/LOG.md (generated)
python -X utf8 tools/review/review.py verdict <film> --note F    # deliver/_review/verdict.md (reviewer: dispatcher-main-loop)
```

- **Inputs.** The film folder must have `build/timeline.resolved.json`, written by `tl.py resolve` with `keys[]` on its clips, and a time-driven page. The page defaults to `build/index.html`; pass `--page` to use another.
- **Rendering.** Each window or still is rendered from a temporary sibling copy of the page folder, because filmkit allows one output per folder. It uses `render.py --start`, is silent, and keeps its frames.
- **Strips.** A strip is the window sampled at 8 fps, six thumbnails per row, with the key or boundary frame boxed in red. Strips and stills are named by their content hash (`strip-<sha8>.png`). A re-render therefore never changes a picture an earlier round already judged.
- **G0 and G3 snapshots.** At G0 the artefact is a copy of `film.timeline.json` at `review/storyboard/film.timeline-<sha8>.json`, because the director edits the live storyboard in answer to the findings. At G3 the artefacts are copies of `build/check.md`, `build/sheet_1fps.png` and `deliver/_review/side-by-side.png` under `review/film/<name>-<sha8>.<ext>`, because a re-render rewrites them.
- **Window lengths.** The window lengths are provisional (design §8 Q3).
- **R windows (inter-shot relations, design §7b).** A K or T window shows one place in the film; a relation joins two places far apart (a callback, a bookend, a replay, a motif, a setup and its payoff), so neither window shows it. `review/relations.json` declares them: `{"relations": [{"id", "a", "b", "kind", "source", "what"}]}` with `a` < `b` in seconds, `kind` one of `callback|bookend|replay|motif|setup-payoff`, `source` `declared` (the maker's intent, written at G0) or `detector` (a candidate from `experiments/probe-inter-shot-relation-2026-11-03/relsim.py` / `textrec.py`), and `what` = what B answers in A. A film with none writes `{"relations": [], "none_reason": "..."}`. `new G2` refuses without the file (default-on). `windows` renders each relation as `R-<id>/pair-<sha8>.png`: row A = frames at a −0.5 / 0 / +0.5 s, row B = the same at b. The director reads the pair and answers it like any window (INV-R9): does B still answer A after the build, and is the change between them the intended one (shrunk, relit, new ground)? A small figure inside a frame (a chart, a label) is easy to miss at this size; name it in `what` so the reader looks for it.

## Files

- **`G<g>-<n>.findings.json`.** Round n of gate g. At G0 the maker writes it about the storyboard; at G1–G3 the director writes it. It holds:
  - `artefacts`, stamped by `new`;
  - `findings[]`: `id`, `window`, `at_s`, `where`, `change`, `severity BLOCKER|POLISH`, `basis {kind, ref}`;
  - `none[]`: `window`, `looked_at`.
- **`G<g>-<n>.response.json`.** `responses[]`: `id`, `status fixed|declined|rebutted`, `note`.

## What `check` refuses

- A BLOCKER whose basis is not `fail_list`, `filmkit_row`, `fidelity` or `seen_once` (INV-R4).
- A declined BLOCKER, or a declined/rebutted finding with no reason (INV-R5).
- A fourth round (INV-R6).
- A window with no line, meaning no finding and no `none` entry with `looked_at` (INV-R9). R windows included.
- A G2 round with no `review/relations.json`, an empty list without `none_reason`, or a relation with `b` ≤ `a`, past the film end, an unknown `kind` or an empty `what`.
- A finding whose `where` is empty or names the whole film, or whose `change` is empty (INV-R10).
- An artefact whose bytes changed after the findings were written (P-4).

## Selftest

`python -X utf8 tools/review/selftest.py` renders real windows and stills of a two-colour page. It then runs a known-good file and a known-bad file for every refusal. Run it after any edit here, before committing.

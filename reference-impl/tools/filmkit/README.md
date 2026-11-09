# filmkit

Upgrade condition: when a second project (not motion-video-lab and not one of its arms) actually calls filmkit,
evaluate moving it to `~/.claude/tools/` or AssetVault. Until then it lives in motion-video-lab.

filmkit turns a time-driven HTML page into a verified MP4 and states facts about the file. It never judges
pixels, pacing, colour or quality; exit 0 means "no blocking row", nothing more.

## Requirements

Python 3.12, Playwright for Python with Chromium (`python -m playwright install chromium`), `ffmpeg` and
`ffprobe` on PATH. Only the standard library and Playwright are imported; the folder is self-contained.

## The page contract

- `window.__setTime(t)` sets the picture for time `t` in seconds. The picture must depend on `t` only
  (no timers, no running CSS animations, no `Math.random()` without a fixed seed).
- `window.__ready` is optional: a Promise, `true`, or `false` that later becomes `true`.
- Only files inside the page folder load; any other request (other folders, the network) stops the render.
  Bundle fonts with `@font-face` and a file in the page folder; do not rely on fonts installed on the machine.
  The bundled file must be openly licensed (for example Noto Sans TC, SIL Open Font License). Never copy a file
  out of the operating system's font folder (`C:\Windows\Fonts` and the like): those licences do not allow
  shipping the file with your page.

## Render

```
python -X utf8 kit/filmkit/render.py build/index.html -o build/final.mp4 --duration 30 --size 1280x720
python -X utf8 kit/filmkit/render.py build/index.html -o build/final.mp4 --duration 30 --size 1280x720 --audio build/mix.wav
python -X utf8 kit/filmkit/render.py build/index.html -o build/final.mp4 --plan build/film_plan.json
```

- The output must sit directly in the page folder (one output per page folder). Drafts or a second version
  are rendered from a copy of the page in another folder.
- `--duration` times `--fps` (default 30) must be a whole number of frames; `--size` must be even.
- `--audio` attaches the file unchanged (re-encoded to the profile's audio codec, channels and rate kept).
- `--start S` renders a window: frame i shows page time S + i/fps, so `--start 12 --duration 3` is seconds
  12–15 of the film. Silent only (refused with `--audio`); used for review windows, where a still is a one-frame
  window with `--keep-frames`. Under any profile but `delivery-web` its end-hold and length rows are information.
- `--gpu` captures on the hardware GPU (Direct3D 11, high-performance adapter) instead of the default software
  renderer. Use it for heavy WebGL shading. `render.json` `env.webgl_renderer` records which adapter WebGL
  actually used; without `--gpu` it names the software renderer.
- Run in the foreground and give your own command timeout more time than the render needs.
- The output name is written only after the file is verified. A failed or interrupted run keeps the previous
  output untouched; it is then reported as stale until a run succeeds.
- Next to the output: `render.json` (how the file was made), `check.json`, `check.md`, `sheet_1fps.png`,
  and a `.filmkit/` folder for the lock and partial files.

stdout is always five lines: `Done:` or `Failed: <kind> — <message>`, `Steps:`, `Check:`, `Look:`, `Notes:`.
`--json` prints one JSON document instead.

Exit codes: 0 published, no blocking row; 2 published with a blocking row; 3 published, some rows could not
finish; 1 nothing new published.

## Check

```
python -X utf8 kit/filmkit/check.py build/final.mp4 --duration 30 --size 1280x720 --audio-expected yes
```

Writes `check.json`, `check.md` and `sheet_1fps.png` beside the file (`<name>.check.*` when the file is not the
output named by a same-folder `render.json`). It never changes the checked file and refuses to overwrite
outputs it did not write. Expected values that are not given make the matching rows "undetermined".

One decode pass reads black picture, still picture and silence as intervals (open at the end of the film is
closed at the film's end and flagged), the peak level of the audio, and frame 0 against the frame one second in.
`render.json` supplies the per-frame animation counts and the re-seek sample (after the last frame the render
visits twelve frames again in a shuffled order and compares hashes). Detected intervals are matched against the
`holds`, `blacks` and `silences` of a `film_plan.json` given with `--plan`; a declared interval is reported as
declared, an undeclared one needs a look. The summary carries two look counts, with and without the declarations.
`narration_lines` in the plan are read only to find a `silences` declaration that lies over a spoken line.

`check.md` sections: blocking, confirmed by the machine, needs a look, undetermined, declared exemptions. One row states whether the
file was written by this kit with the `render.json` beside it, and whether the inputs and the kit still match
what that record says (`--mounted-kit-hash` names the kit the caller mounted, or `none`). A format failure carries a
re-render command (`rerun`) with absolute paths; placeholders such as `<page>` or `<new-out>` must be replaced
before running it.

Loudness: every file with audio gets one information row with its integrated loudness (LUFS), loudness range and true
peak (dBTP), read by ffmpeg's `ebur128` filter. Nothing is compared unless the caller names a target: `--rules F
--target NAME` compares against the entry NAME of the rules file's `targets` (the loudness, the true-peak ceiling and,
when the entry gives one, a tolerance in LU). The comparison is a look (WARN) when the loudness is outside the
tolerance or the true peak is above the ceiling; it is undetermined when the entry gives no tolerance, is malformed,
is missing, or the file has no audio. `--target` without `--rules` is refused.
`narration_lines` in the plan are also read against the audio: a line whose time span has a peak at or below the
profile's silence level is listed as a look.

Formal path (2026-10-11, `~/.claude/references/formal-path-governance-design.md` §4.4): two rows say whether the
shared design layer reached this film and whether the act that made it is stamped. They read files beside the page,
never pixels. The page folder is the folder of the `render.json` (else of the checked file); the works item is the
first folder at or above it that holds a `state.json`.

- FK-R-18 `provenance_mount`: `<item>/inputs/design-axes.md` (without an item: `../inputs/design-axes.md` or
  `design-axes.md` beside the page) must exist and equal the current `mount/video.md` (the shared layer's
  `digest.py check --medium video`). Missing or stale is a failure; an unknown current mount is undetermined. A
  plan or `state.json` carrying `mount_design_axes: false` with `mount_design_axes_why` gives an info row quoting
  the why (a control arm).
- FK-R-19 `provenance_stamp`: the item's last `made_by` row of stage open / generate / build / adopt carries every
  W-2 key plus `actor` and `toolbox`. No `state.json` above the page is "not a works item".

Severity: `--profile delivery-web` makes both blocking; any other profile reports them as information (a lab round
does not live in works). `render.py` writes `render.json.provenance = {item, mount_sha, canon_sha, actor, toolbox}`
(nulls without an item), and the Notes line names the item and mount when the formal path is in play. A works item
is opened by `~/.claude/tools/design-axes-mount/works_contract.py open` (or `adopt` for a finished foreign film).

## Page scan

```
python -X utf8 kit/filmkit/pagescan.py build/index.html --duration 30 --size 1080x1350 --plan film_plan.json
```

Reads the page itself (never the MP4) at every frame and writes `<page>.pagescan.json`, `.md` and
`.raw.json` (the per-frame reads; `--from-raw` re-analyses them without a browser). Run it after a render and fix
what it lists before the film is shown. Every row says what was read; none says whether the picture is good, and
none blocks. Exit 0 read, 3 a row is undetermined, 1 the page did not load.

- QF-1c `slow_scale_on_text`: a text element whose effective scale keeps changing at a slow rate (0.2 % to 15 %
  per second, 5-frame mean) for at least 1 s. This is the "breathing" stage push; under this kit's seek-and-capture
  every frame re-rasterises the glyphs at a new scale and they jump (`experiments/probe-text-shimmer-2026-10-24`).
- QF-1 `text_shimmer`: inside each QF-1c segment, the glyphs' ink centroid relative to their box, minus a smooth
  trend; listed at a median of 0.25 px or more (provisional, one real page).
- QF-2 `one_frame_pop`: a text element going from absent or opacity < 0.1 to opacity >= 0.9 between two frames.
  A hard cut declared in the plan's `cuts` (`t0`, `t1`, `why`) is reported as declared. Needs `--stride 1`.
- QF-3 `font_node`: for every visible text element every `--font-stride` frames, the platform font that renders
  most of its glyphs, against the first family of its `font-family` (an `@font-face` family must be rendered by a
  custom font). Generic first families are undetermined.
- QF-6 `pulse`: an element whose scale (>= 1 %) or opacity (>= 0.1) swings back and forth at least 3 cycles within
  4 s. A content-driven pulse declared in the plan's `pulses` is reported as declared.

With `--timeline <film folder>` (its `film.timeline.json`, and `build/timeline.resolved.json` from `tl.py resolve`)
two more rows appear:

- QF-7 `state_text`: for each clip with `shows_state`, every string or number fact of those `product_state` entries
  must appear in the page text read inside the clip's resolved window (case and whitespace ignored, substring
  match). Without resolved times the row is undetermined; a window no frame fell into is reported as unread.
- QF-8 `required_asset`: for each asset with `required`, the elements carrying `data-asset="<id>"`: seconds visible
  (opacity >= 0.5, some of the box inside the frame), the smallest visible share of the box, the aspect drift against
  the image's natural size. Listed below `min_visible_s`, cropped under `no_crop`, or drift over 1 %. Mark every
  placement of a required asset with `data-asset`; an unmarked one reads as never on screen.

Blind spots: text painted into canvas or WebGL has no DOM node (the text rows read undetermined when canvas covers
half the frame or more); a pulse made by a filter or a canvas is not seen; QF-1 reads pixels only where QF-1c found
a drift.

## Profiles

`--profile NAME` picks a named group of format fields (codec arguments, detection thresholds, timeouts) from
`profiles.json`. `lab-round` is the default; `delivery-web` carries format fields only. A profile holds no target
value and no design rule.

## Transform

```
python -X utf8 kit/filmkit/transform.py normalize build/final.mp4 --out build/final.norm.mp4 --target-lufs -20 --true-peak -2
python -X utf8 kit/filmkit/transform.py normalize build/final.mp4 --out build/final.norm.mp4 --rules rules.json --target NAME
```

`transform.py <operation> <input> --out <new file> ...` runs one explicitly named operation and always writes a new
file, never over the input; `--out` is required and must differ from the input. `render.py` and `check.py` never call
it. Nothing about an operation is a default: `normalize` has no target of its own, so the caller gives both
`--target-lufs` and `--true-peak`, or a named entry of a rules file. The video stream is copied unchanged; the audio
is measured with `ebur128`, then brought to the target by the `loudnorm` filter in linear mode, and the new file is
measured again (the figures go to the transform record, not to a verdict).

Beside the new file it writes `<out>.transform.json` (input path and hash, parameters, kit hash, the measured
loudness before and after, status). The record, the lock and the publishing steps are the same as `render.py`'s:
the file is written under `.filmkit/`, verified, then renamed; a stopped run leaves the previous output in place
and `check.py` reads it as stale. `check.py` on the new file reports the transform record and whether the input
file is still the one it was made from. A format failure on a new file names the transform record instead of a
re-render command.

An operation is one module under `_fk/ops/` plus one line in `_fk/ops/__init__.py` (the table); `transform.py` and
`_fk/transform_core.py` do not change. The module protocol is in that file's docstring.

Exit codes: 0 new file published; 1 nothing new published (`--json` prints one document instead of the five lines).

## Rules files

`--rules F` names a rules file kept outside this folder; the kit ships no rules of its own. It evaluates the entries
whose owner is filmkit with one generic comparison (a detected interval selected by source and anchor, measured
against a range) and takes the sentence, the basis and the provisional mark from the file. An entry of another
kind or another owner is not evaluated. `--film-type T` (or `film_type` in the plan) picks the entries that apply.
Loudness targets are read by name from the file's `targets`; the kit holds no target value.

## Known blind spots

- The content scan reports what ffmpeg's detectors report with the profile's thresholds, which are not calibrated.
  A still picture shorter than the threshold plus one frame is not reported. A black picture ended by a single
  bright last frame reads as black to the end (one frame of error). A still that runs shorter than the general
  floor is kept only when it starts inside the start window at the head (the profile's `start_window_s`) or runs to
  the end of the film (each has its own floor in the profile). So a short still of 1 to 2 seconds in the first few
  seconds is seen, and one of the same length later in the film is not.
- A span in the middle of the film that the detector reads as a still gets one more pass: the picture is cut into a
  16 x 9 grid, the largest tile's frame-to-frame change is taken for every frame, and the median over the span is
  compared with the profile's limit. A span over the limit is not counted as a still; it is listed as an info row
  (`FK-R-8L`) with its median. A span that starts at the head or runs to the end of the film never goes through this
  pass and is never left out: a held head or end is a hold whatever moves in a corner of it. Motion that stays under
  the limit in the median (a small element that moves now and then, a slow change) is still read as a still. When
  the pass fails or runs out of time the span is kept as a still and a note says so.
- Silence and "all samples zero" are read from the audio only; words spoken or music playing are not recognised.
- Loudness is the file's own audio as ffmpeg's `ebur128` reads it (gated integrated loudness, 4x oversampled true peak
  from the first audio stream only). A file with digital silence measures at the filter's floor and a true peak of
  minus infinity. Whether a number is right for a delivery platform is the rules file's claim, not the kit's.
- `normalize` aims at a target; it does not promise to reach it. The measurement of the new file is in the record, and
  `check.py --target` is the comparison. Only stereo sources with one audio stream have been exercised.
- The re-seek sample checks twelve frames. A page that differs only on other frames passes.
- The animation count sees animations the browser lists (CSS animations and transitions, Web Animations); a
  canvas or timer that keeps running is not seen.

- Font check (fingerprint against a missing-family baseline, Latin and CJK probes, family level): an operating
  system alias to another installed font (for example `Helvetica` mapped to Arial on Windows) reads as present.
- On a machine where the Latin baselines coincide but the CJK ones do not, a Latin-only family used in CJK
  text reads as substituted.
- Fonts are sampled at the first frame, the middle frame and the last frame only; text shown only between
  those moments is not checked. `check.md` names the moments.
- The selftest's bundled-font control copies `NotoSansTC-VF.ttf` from `C:\Windows\Fonts` at run time (the file
  is not part of the kit); when that font is not installed the control reports `skipped (font not installed)`.

## Selftest

```
python -X utf8 kit/filmkit/selftest.py
python -I -X utf8 selftest.py --smoke
```

The second form, run from a copy of this folder, checks that the kit is self-contained.

# Third-party notices

Checked on 2026-11-10. Everything else in this repository is the author's own work (see `LICENSE`,
`LICENSE-DOCS`). Facts below were checked against the shipped files of `reference-impl/` and against the
installed package metadata on the machine that produced `verify/controls_run.txt`.

## Shipped third-party files

| file | what | licence | where the licence text is |
|---|---|---|---|
| `reference-impl/films/fanout-pool-explainer/page/fonts/NotoSansTC-VF-subset.woff2` | Noto Sans TC (variable, subset) | SIL Open Font License 1.1 | `.../page/fonts/LICENSE-OFL-NotoSansTC.txt` |
| `reference-impl/films/fanout-pool-explainer/page/fonts/IBMPlexMono-500-latin.woff2`, `IBMPlexMono-600-latin.woff2` | IBM Plex Mono (latin subset) | SIL Open Font License 1.1 | `.../page/fonts/LICENSE-OFL-IBMPlexMono.txt` |

Both fonts are embedded by the example page with `@font-face`, so the render does not depend on fonts
installed on the exporting machine.

## Libraries the origin used but this repository does not ship

The vendored tarballs of the origin environment are NOT included. Pages of the origin's films load them from
a local folder; the shipped example page uses none of them. If you build a film that needs one, obtain it
from its project and check its licence yourself.

| library | version used at the origin | licence |
|---|---|---|
| GSAP | 3.15.0 | GreenSock Standard "no charge" License (not an OSI licence; read its terms before commercial use) |
| three.js | 0.170.0 and 0.186.1 | MIT |
| glTF Transform | 4.5.1 | MIT |
| glTF Validator | 2.0.0-dev.3.10 | Apache-2.0 |

## Ideas and methods re-implemented, no code copied

- `reference-impl/tools/shotstats.py`: the hard-cut detector re-implements, in numpy and OpenCV, the published
  method of PySceneDetect's AdaptiveDetector (a content score from HSV frame differences, compared with the
  average of the neighbouring frames). No PySceneDetect source is included and `scenedetect` is not a dependency.
  PySceneDetect is BSD-3-Clause; the file states the one change made to the method (hue compared only where
  both pixels are saturated). The colour-barcode idea is credited in the file's docstring to the tool
  CadensView; no code of it is used.
- `reference-impl/tools/filmkit_rules.json`: the loudness target values cite the published EBU R128
  recommendation and platform documents as sources, each with a `review_when` line; they are numbers, not copied text.

## Runtime dependencies you install yourself (not included)

| package | role | licence (as installed when the controls were run) |
|---|---|---|
| Python 3.12 | interpreter | PSF License |
| numpy 2.5.2 | all measurement tools | BSD-3-Clause |
| scipy 1.18.0 | two instruments (filters, statistics) | BSD-3-Clause |
| matplotlib 3.11.1 | figures of some instruments | Matplotlib licence (PSF-based) |
| opencv-python-headless 4.12.0.88 | frame reading and image maths | Apache-2.0 (the wheel bundles FFmpeg libraries under LGPL-2.1+) |
| pillow 12.3.0 | image composition | MIT-CMU (HPND) |
| playwright 1.62.0 | drives Chromium for frame capture and README images | Apache-2.0 |
| Chromium (installed by `playwright install chromium`) | page renderer | BSD-3-Clause and bundled components |
| OpenTimelineIO 0.18.1 | edit route (EDL / OTIO) | Apache-2.0 |
| ffmpeg (on PATH) | encoding, probing, GIF cutting | LGPL-2.1+ or GPL-2+ depending on the build you install |
| pytest 9.1.1 | not required by the controls | MIT |

Versions are those present on the machine that produced the recorded run; other versions were not tested.

## Quoted or paraphrased origin material

The documents under `reference-impl/docs/` and `reference-impl/skills/` are the author's own working documents.
They cite measurements taken on third-party films as numbers and short descriptions (a shot count, a duration,
a ratio); no frames, audio or text of those films are included, and the films themselves are not shipped.

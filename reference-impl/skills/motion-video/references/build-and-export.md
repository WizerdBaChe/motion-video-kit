# Build, export, fidelity, review

Evidence: `<lab>\docs\workflow.md` step ⓪ and ⑥,
`docs/production-order.md` nodes I/J, card T05. Tags: [lab] = used in lab rounds;
[C20] = a source tutorial's claim, not tested here; [reelmimic] = an external repo's
practice, not tested here.

## §1 Build — every frame is a function of time [lab, r5 onward]

- One HTML page. Expose `window.__setTime(t)`; everything on screen is computed from `t`.
  No `setTimeout`, no `requestAnimationFrame` wall-clock time, no CSS transitions or
  animations left to the browser's live tweening.
- Springs in closed form (step response), not simulated per frame; parameters in
  `motion-design/local/element-motion-params.md`.
- Keep tunables in one block at the top (durations, colours, section times, beat grid).
- Beat-locked events carry `// beat-locked: <t>s` comments (see `rhythm-transitions-camera.md` §1).
- Asset and font failures show a visible notice on the page plus a structured console
  error; a silent blank frame is a defect.
- Speed map for demos (user r14: real waits drag; unvalidated, first used in r15). Speed
  changes the mapping from film time to demo time, not the frame rate. Only the demo layer
  reads the mapped time; headlines and captions stay on film time, so their reading hold
  never shrinks.

```js
// demo speed map: [demo_start, demo_end, speed]; speed 1 = real time. Global = one row.
const SPEED = [[0, 3.0, 1], [3.0, 11.0, 6], [11.0, 14.0, 1]];   // e.g. an 8 s download at 6x
const RAMP = 0.25;                       // s of film time to ease between speeds
function demoTime(tf) {                  // film seconds since the demo started -> demo seconds
  let td = 0, left = tf;
  for (const [a, b, v] of SPEED) {
    const film = (b - a) / v;            // film seconds this span takes
    if (left <= film) return td + left * v;
    td += b - a; left -= film;
  }
  return td + left;                      // past the table: real time
}
// Easing: blend neighbouring speeds over RAMP (integrate a smoothstep of v), or keep hard
// changes only where the picture cuts anyway.
```

  Capture the demo densely in real time (about 10 fps of screenshots with their
  timestamps, or a screen recording), then pick the frame nearest `demoTime(t)`; a few
  stills played faster jump (r14 S used a handful of stills at 1.6x). Mark "加速" on
  screen only where the speed would mislead (a download rate, a remaining time).

## §2 Export [lab]

- Export with filmkit, not a hand-written capture script [lab, filmkit M0 built and checked
  on synthetic controls; mounted in lab rounds from M1]:
  `python -X utf8 <lab>/tools/filmkit/render.py <page> -o <the page's own folder>/final.mp4 --duration S --size WxH [--audio F] [--plan film_plan.json]`.
  Frame `i` is captured at `t = i / fps` through `__setTime`, encoded with the `lab-round`
  profile (`tools/filmkit/profiles.json`), verified (frame count, size, codec), and only then
  published under the output name; `render.json`, `check.json`, `check.md` and
  `sheet_1fps.png` are written beside it. A heavy WebGL page (PBR, SSAO, bloom, many draw
  calls) adds `--gpu`: capture runs on the hardware adapter instead of the software renderer,
  and `render.json` `env.webgl_renderer` names the adapter actually used [lab, af2b127, controls:
  SwiftShader without the flag, RTX 5070 with it]. The output must sit in the page's own folder; a
  draft or a second version is rendered from a copy of the page. Lab round frames use
  1280x720 (1080x1350 for vertical) at 30 fps and write the exact duration into
  `build/plan.md` (`rounds/frame_*.md`).
- A 3D shot's layers (`mesh` / `scene` / `vfx` / `post` / `sequence`) and the reusable-`mesh`
  gate are owned by `~/.claude/rules/scene-asset-layers.md`. Export tools in the lab
  `tools/vendor/`: three.js scenes via `GLTFExporter` (`three-0.186.1/`), raw WebGL scenes via
  glTF Transform (`gltf-transform-4.5.1/`), checked by `gltf-validator-2.0.0-dev.3.10/` [lab
  probe 94eefd5, n=1 per route: both reload in three 0.186 with effects off; r35 B1 failed the
  validator on an HDR base colour driving bloom — emissive + emissive strength instead].
  A trademark sign is extruded from its vector file in headless Blender and checked against the
  browser render of that file on BOTH aspect error and per-colour IoU: IoU after fitting to one box
  is blind to a squashed sign [lab probe b8a0aec, n=1: aspect -0.18 %, IoU >= 0.975; squashed
  control caught by aspect only, missing-stripe control by IoU only;
  `experiments/probe-blender-sign-2026-10-24/`]. Blender runs as headless `bpy` when no human works
  in its GUI; its MCP is for interactive sessions only [user ruling 2026-10-24: route proven, no
  further probes until a film needs it].
- Vertical = 1080x1350 (4:5), the IG feed spec [user ruling 2026-10-11]: never 1080x1920
  — a full-height FHD frame is a burden for most viewers and platforms rarely show it
  uncropped. Lay out on the 1080x1350 canvas from frame 0; never compose wider and crop
  at export (negative case C38: labels, numbers and paths cut at both edges). Keep
  subtitles and screenshots inside the frame with margin; a quoted screenshot is pushed
  in until its quoted line is phone-readable. Rule checks (`--rules`, M2) and the
  `delivery-web` profile (format fields only, M3) are available. `transform.py normalize`
  is opt-in, always writes a new file next to a `.transform.json`, and on a formal film is
  asked first, naming the new file (BR-14, D21).
- Formal-path rows [lab, filmkit 2026-10-11; `tools/filmkit/README.md` 〈Check〉]: FK-R-18 says
  whether the works item's `inputs/design-axes.md` equals the current shared mount, FK-R-19
  whether the item's last generating `made_by` row carries the W-2 keys + `actor` + `toolbox`
  (item = the first folder at or above the page with `state.json`). Under `--profile
  delivery-web` both are blocking, so a formal film not opened with `works_contract.py open`
  (or a stale mount) cannot pass export; a tl film made before 2026-10-11 (resolve rows only)
  is stamped with `works_contract.py attach <item> --actor ...` instead, never by hand-editing
  `state.json`; under `lab-round` they are information. A control
  arm declares `mount_design_axes: false` + `mount_design_axes_why` in its plan (info row).
  `render.json.provenance` records item, mount sha, actor and toolbox. Neither row looks at
  the picture.
- Content scan [lab, filmkit M2; severities ruled D18 2026-10-10: all stay look rows]: black/still/silence
  intervals (open-at-end intervals are closed at the film end and flagged), frame 0 vs the
  frame at 1 s (a flat start shorter than 0.2 s is info only; a dark frame with small text is not black),
  a still running to the end, or starting in the first 5 s, is detected from 1.0 s (elsewhere 2.0 s), FK-R-11 running-animation count, FK-R-12 re-seek of 12 frames.
  A mid-film still whose busiest 80-px tile keeps changing (median > 0.0005, e.g. a moving progress
  bar) is not a still: it leaves the still list as an info row `FK-R-8L` (W32, D31 2026-10-10; stills
  touching the film start or end are never excluded, so a quiet end hold stays an end hold). Findings are
  look rows, except the one blocking case of all-zero audio when sound is expected.
  Declared holds/blacks/silences (with why) are listed in `check.md` section 5, and the
  summary gives two look counts (with and without declarations). `--rules` evaluates
  `tools/filmkit_rules.json` as FK-R-16 rows, and a provisional rule is marked （暫定）. Rules today:
  `end_hold` 1.5-2.5 s (W30) and `head_hold`: the first still starting in the first 5 s, after any
  opening animation, at most 1.5 s (W33, D32 2026-10-10, user: a 2.1 s hold after the opening is too long).
- Fonts: filmkit waits for `@font-face` files and checks that each named font family
  exists on the machine (FK-R-6). A formal film bundles its fonts with `@font-face` and
  does not depend on installed ones (lab D26). The bundled file is openly licensed; never
  copy one out of the system font folder (lab r23 A2 copied Georgia from
  `C:\Windows\Fonts`). [C20 lists "exported before fonts loaded" as a common error.]
- A render is finished only when filmkit prints `Done:` (the output name appears only after
  verification); a background render that ends early leaves no output name (a lab run once
  ended early, r8 B2).
- Audio: a known-beat track (generated with the lab's `tools/make_beat_track.py --bpm 120
  --bars 24 --out <wav>`, which also writes the beat-time JSON and, from 2026-10-18, a stereo
  file — filmkit FK-R-5 blocks a mono track; convert an older mono input with `ffmpeg -ac 2`; or a real track measured
  with `tools/beatgrid.py`) before the timeline is laid out; narration generated first
  when the film is narrated. Voice: Windows SAPI only as a stable test voice; a film a
  person will watch uses a TTS model, picked by checking the options current at the time
  (user r18: SAPI "太難聽").
- Voice, author-recorded route (user 2026-10-28, X01 campus-system-failures; n=1 film): the
  author reads the script in takes; an abandoned ending is re-read in the next take and the
  old ending is cut. Steps:
  1. Speech recognition per take, with word timestamps.
  2. An edit list (`edl.json`) names each take's kept range(s); cuts fall on word boundaries,
     padded but never into a discarded word.
  3. Leak guard before building: every recognised line before a take's abandoned ending must lie
     inside a kept range unless the edit list declares it dropped; an undeclared drop refuses
     the build. (X01 v1 cut a line that should have stayed, T02 / S02-11, because the check only
     sampled the lines beside each cut point; tested by re-running the old T02 range, which the
     guard blocks.)
  4. Loudness: each take gets ONE gain to the common target, and isolated peaks are caught by a
     limiter; never lower a whole take for one peak. What the author hears is level jumps
     between takes, not absolute loudness.
  5. After joining, re-run recognition on the whole narration and check line by line that every
     kept line is present and whole at each cut point, not just the lines beside it.
  Reference implementation: `<works>/explainers\X01-campus-system-failures\voice\_scripts\`
  (`asr_batch.py`, `build_narration.py`); record: `…\X01-campus-system-failures\錄音紀錄.md`.
  A filmkit narration-cut operation waits for a second author-recorded film (one case so far).
- Cover (user 2026-09-29): a separately designed image, never a frame grabbed from the film.
  Only for YouTube, burn the cover into frame 0 (the platform's frame-0 thumbnail is an
  external claim, unchecked); replace frame 0's pixels only — length, frame count and sound
  unchanged. No other platform gets this.
- YouTube upload text (YouTube Data API `videos` reference, checked 2026-10-28): title max 100 characters,
  description max **5000 UTF-8 bytes**, both without `<` `>`. Studio's counter shows characters, so a CJK
  description (3 bytes a character) reads "3200 / 5000" at 4956 bytes; budget about 1,666 CJK characters.
  Count bytes in any generator (X01 kit: `<works>/films\campus-system-failures-explainer\_scripts\youtube_kit.py`,
  which also emits chapters, SRT from the narration line times, and the cover).

## §3 Review loop [lab + reelmimic]

0. Start from the file check: `check.md` beside the film (blocking rows, then "needs a look"
   rows with their seconds). It states file facts only and never judges the picture.
   Section 5 lists the author's declared exemptions (holds, blacks, silences with why).
   Then the page scan, before any human sees the film (lab convergence build 2026-10-24):
   `tools/filmkit/pagescan.py <page> --duration S --size WxH --plan film_plan.json [--timeline <film>]`
   reads the page itself and lists build errors — slow scale drift / shimmer on live text
   (QF-1c / QF-1), one-frame pops outside declared `cuts` (QF-2), substituted fonts (QF-3),
   pulses outside declared `pulses` (QF-6), state facts missing from their clip (QF-7), required
   assets too brief, cropped or stretched (QF-8). Fix what it lists and rescan; it never judges looks.
1. Whole-film sheet next: 1 fps, 6 x 5 per sheet (`tools/sheets.py --fps 1 --cols 6 --rows 5`),
   then boundary rows (`--boundaries <segments.json>`: before / mid-transition / after).
2. Feedback as "second / where / change"; one change at a time. [C20]
3. Two severities: BLOCKER (seen once at normal size and speed: broken limb, white flash,
   clipped or wrong text, wrong number) and POLISH (needs pause or zoom). Only blockers fail
   a round. [reelmimic]
4. From round 2, first check last round's fixes (before/after frames at the same second and
   spot), then new blockers only. Items only the user can give (assets, rulings, product
   facts) are listed under "waiting for you", not as defects. At most 3 rounds, then hand
   the decision to the user. [reelmimic, 3 is its default, not validated here]
5. The reviewer is not the session that built the film. [reelmimic]
6. Comparing two versions: show them back to back with sound (`compare_sequential.mp4`);
   side by side only for overall style (sections are out of sync). Ask for per-section
   picks, not one winner (r10: the best sections were spread over five films).
7. Good-looking / matching is the user's call after watching (lab INV-6).
8. Motion intent (`whole-film-rules.md` §2a): read the build against the storyboard's
   intent lines; a moving element, stock device or effect layer with no line is a POLISH
   finding (cut it or write the line), not a BLOCKER. No tool checks this yet.
9. Formal film, before delivery: compare SIDE BY SIDE with an approved film of the same type,
   never a lone look (creative-brief CB-6) [2026-10-11, formal-path design
   `~/.claude/references/formal-path-governance-design.md` §4.3].
   `python -X utf8 ~/.claude/tools/design-axes-mount/works_contract.py review <item>` writes
   `deliver/_review/side-by-side.png` (candidate 1 fps sheet left, the tag-picked approved sheet
   right; `reference: none (…)` when no same-type approved film exists — then the verdict says
   「無對照」) and `report.md` with the mount's fail list as a checklist. The approved film is a
   comparison only: its frames and code never enter the workspace. The verdict
   (`deliver/_review/verdict.md`, first line `reviewer:`) comes from someone other than the
   building session — in one session, a clean-context subagent reading the side-by-side
   (item 5). `works_contract.py deliver <item>` refuses until the verdict is newer than the
   candidate.
10. **Agent-review path** (user 2026-10-19, U-1..U-4 of lab `docs/agent-review-kbt-design.md`;
    replaces items 5 and 7 on this path only; item 9's side-by-side stays, as a reference that never
    blocks). The user gives direction and design content and leaves the loop. Roles: the maker
    subagent builds; the dispatching main-loop session (director) reviews from artefacts only and
    never edits the film; the maker reviews the director's storyboard at G0. Messages are files,
    driven by the lab's `tools/review/review.py` (README there):
    - G0 storyboard (`film.timeline.json` with `keys[]`; no positions or px in it, CB-2) → G1 one
      still per key frame, hard items only → G2 K windows (key ±1.5 s) and T windows (seam
      −1.0/+1.5 s) as 8 fps strips, plus `blurdip` / `shapematch` / `density` as hints → G3 the
      whole film once (`check.md`, 1 fps sheet, side-by-side).
    - Relations (user 2026-11-03, lab design §7b): at G0 the maker writes `review/relations.json`,
      the non-adjacent relations the film intends (callback, bookend, replay, motif, setup-payoff; a,
      b seconds; what B answers in A), or an empty list with `none_reason`; `new G2` refuses without
      it. Each relation is reviewed as an R window (both ends side by side, ±0.5 s), one line each.
    - BLOCKER only on a fail-list item, a filmkit blocking row, T05 fidelity, or a seen-once defect
      (incl. unreadable text measured by contrast or visible seconds); taste, feel and principles
      are POLISH, which the maker may decline with a one-line reason.
    - Every window rendered in a round gets a line (a finding or `none` + what was looked at); a
      finding names one element and its amount, never a whole-film rule (the r22 rubber-stamp and
      "nothing fully static" → jitter failures).
    - At most 3 rounds per gate; open BLOCKERs after round 3 ship with the film, listed in the verdict
      (`reviewer: dispatcher-main-loop`, `user_watched: no`, `unresolved:`). Tool-level blocks
      (filmkit `delivery-web`, TV-18, `deliver`) still stop delivery; model overrides stay ineffective.
    - Review lens: lab `docs/research/motion-principles-beyond-twelve-2026-10-19.md` §4 (where to look,
      how to word POLISH) and §5 (principles that mislead when applied mechanically).

## §4 Product fidelity (T05) — user rulings 2026-09-27; checked by `tools/fidelity.py`

1. Product screens are real captures (run the product locally with demo data; Playwright
   screenshots or frame-by-frame recording). If a redraw is unavoidable, every label on it
   is a string the product really has.
2. Operations shown are operations the product really does, captured doing them.
3. Numbers come only from the product: docs, demo data, or computed by the app and visible
   in a capture. No sourceless "80% faster".
4. Headlines state what the current version does; optional / separately installed features
   are marked as optional; planned features are left out.
5. No scope inflation: scope words (all / any / entirely / always / 全程 / 所有) only when
   the docs claim the same scope; otherwise write the exact scope.
6. Illustrations of a pain point that are not the product are marked "illustration"
   (示意); invented numbers never look like real data.
7. Pain points and emphasis come from the docs or the owner; if absent, ask the owner, or
   (unattended) write `build/questions.md` and state only what the feature does. The same
   goes when the docs contradict each other or the running product (a button, flow or
   label the docs name is not in the app): that is a question for the owner, and the film
   shows and words what the running product does, never the docs' stale version. Check
   every headline's wording against the capture before rendering. A paragraph to append
   to any product-video prompt: `<lab>\techniques\T05-addon-ask-owner.md`.
   [lab r14: the skill arm headlined README's 「先分析」 over a 2.0.3 GUI that has no 分析
   button and wrote no questions; the arm given T05-addon listed the mismatch]
8. Deliver `build/claims.json`:

```
claims.json: [{"t": 12.0, "text": "<on-screen text>", "kind": "feature|number|ui|pain|illustration",
               "source": "<file#section | capture file + action | owner answer | 'illustration'>"}]
```

9. An interactive component whose motion IS the subject (a menu that opens, a wheel that fans
   out) is mounted LIVE in the film page, not shown as a capture sequence: static captures
   leave only a drawn cursor moving and break continuity (user 2026-10-24, wheel-promo v1
   failed; v2 method "修正通過"). Recipe (works `films/wheel-promo-hype`, commit 7ecd19e):
   - a frozen copy of the component's files in the film's `assets/` with a provenance.json
     (origin path@commit, sha256); host data inlined as a JS global (no fetch);
   - ONE instance for the whole film; each `__setTime(t)` resets it through the component's
     own reset path (here an Escape keydown) and replays the active input's synthetic events
     from that input's start up to t, sampled every 1/60 s from the start (pure in t);
     recreating the instance per frame gives new DOM nodes every frame and floods pagescan
     QF-2 with false "text appeared in one frame" rows;
   - the component's CSS animations / transitions are switched off in the film CSS and the
     ones that matter (open pop, fade) are replayed from t with the same duration and easing;
     instant changes the real component makes (hover text, a fan that appears at once) stay
     instant — never add motion the product does not have;
   - the drawn cursor and file chip are scaled by 1/zoom so they keep frame size under the camera.

## §5 Music sourcing for films (user 2026-10-24, wheel-promo; research note
`~/.claude/outputs/radial-wheel-promo-20261024/配樂來源候選_20261024.md`)

- Default source: Pixabay Music. Licence summary (pixabay.com/service/license-summary/, read
  2026-10-24; full terms §5-6 not read clause by clause): free commercial use, no attribution,
  modification allowed, no standalone resale or redistribution, no warranty on third-party
  rights inside a track. Re-check the page before relying on it (volatile fact).
- Content ID: most popular Pixabay tracks carry a "Content ID Registered" label (12 of 14
  checked 2026-10-24). Prefer tracks without the label for social posts; a labelled track's
  claim is cleared with Pixabay's licence certificate.
- Not used until checked: Mixkit (licence text not obtained), Uppbeat free tier (attribution per
  track, 3 downloads then 1 per month), YouTube Audio Library (per-track CC BY, off-YouTube use
  disputed), FMA / Incompetech (CC BY per track, some non-commercial).
- Access: pixabay.com sits behind a Cloudflare challenge (curl and headless Playwright get 403).
  Never bypass it; read track pages in the user's Chrome with their approval (Claude in Chrome)
  and fetch the file from the CDN (cdn.pixabay.com is not challenged).
- Per film keep `assets/music/provenance.json`: source page, CDN URL, sha256, licence line,
  Content ID / AI label as seen on the page, measured BPM / period / phase, the film's offset
  and duration with the reason. The mp3 itself is git-ignored.
- Beat alignment: lab `tools/beatgrid.py` needs a video; for an mp3 call its
  `onset_envelope` / `estimate_grid` on audio loaded with `avio.load_audio`. Trim at
  offset = phase + k beats so film beats sit at k * period.
- Level: stock masters measured about -9.5 LUFS with true peak above 0 dBTP after AAC; apply a
  mix gain in the film's own build (wheel-promo: -4.5 dB -> -14 LUFS, peak about -3 dBTP), not
  filmkit `transform.py normalize` (that needs the user's yes, BR-14).

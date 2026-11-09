---
name: motion-video
description: >-
  Making a whole code-rendered video (every frame computed by a program): intro ads, hype ads, product tours, showreels, narrated explainers — audience,
  tone, sections, transitions, camera moves, export. Trigger on
  「做一支產品介紹片/宣傳片/廣告」「酷炫、抓眼球的廣告」「做 showreel」「做旁白說明動畫」「影片怎麼分段、換段、轉場、運鏡」「這支片的基調/受眾」.
  NOT one UI animation's easing (→ motion-design), studying reference videos
  (→ case-library).
---

# motion-video — making a whole code-rendered film

Router skill for FILM-level work. Element-level motion (duration, easing, springs,
colour swaps inside one component) stays in `motion-design`; read
`~/.claude/skills/motion-design/local/element-motion-params.md` for the measured spring
numbers. Evidence lives in the lab `<lab>` (cards `techniques/Tnn`,
docs, measurements); the tools stay there too (user 2026-09-30), so this skill cites
their paths instead of copying them.

Every rule in the references carries an evidence tier (`references/evidence-and-instruments.md`
§Tiers): **user** (the user judged it watching films), **measured** (a calibrated
instrument read it on source films), **verified** (a blinded A/B round moved it, ranges
disjoint), **unvalidated** (measured on sources, never tested by imitation). Do not
state an unvalidated rule as a proven one.

## Routing table

| If the task is about… | Read |
|---|---|
| What to decide first; audience, tone, ground colour, what info belongs; device-tone pairing; materials and text | `references/whole-film-rules.md` |
| Which film type; section skeletons (intro ad, hype ad, product tour, data showreel, narrated explainer); storyboard vs one paragraph | `references/film-types.md` |
| Section changes on the bar or on the narration line; beat alignment; transitions (shape-to-shape, dim, wipe); camera moves | `references/rhythm-transitions-camera.md` |
| Building the page, time-driven rendering, export to MP4, product fidelity (claims file), filming a live interactive component (§4 item 9), cover, review loop, music sourcing and licences (§5) | `references/build-and-export.md` |
| Evidence tiers; which lab instrument measures what; where each number comes from | `references/evidence-and-instruments.md` |
| Footage or generated media (local ComfyUI images, clips), cutting to music beats, an exchangeable EDL — the edit route, not a time-driven page (user ruling 2026-10-18); every asset carries a provenance file or the render is refused | lab `tools/edit/README.md`, design lab `docs/edit-route-design.md` |
| A continuous physical or algorithmic process (a front growing, a field spreading, a wave travelling) — a manim ASSET (PNG sequence + provenance) composed into the time-driven page, never a whole manim film. Whole-film production and edit-and-compose (assets that must be used) are separate layers (user ruling 2026-10-20); compose rules are thin, first probe in progress | lab `experiments/probe-manim-insert-ow2010/README.md`; proposal `~/.claude/outputs/manim-explainer-route-20261020/` |
| Spring / colour-swap parameters for one element | `motion-design/local/element-motion-params.md` |
| **Before the storyboard, every film**: the shared design layer as this film's own copy — the fail list in it is binding (author-rejected work; never repeat it) | `<item>/inputs/design-axes.md`, copied by `works_contract.py open` (step 0); a lab arm gets the same file from `run_arm.py` |
| The same principle in posts, decks or web pages (cross-medium form, axes A–I, generation axes J/K, named schools) — theory, read when choosing | `~/.claude/references/design-axes/` |

## Order of work (each step before the next)

0. **Confirm before anything** (`whole-film-rules.md` §0): purpose / film type (intro
   ad, hype ad, product tour, explainer, profile), where it will be shown, what the viewer
   should do after watching, the audience, the ONE thing to remember, the ENERGY (calm /
   lively / hype; asked, never inferred from the product alone) and ground, the
   materials and limits, the content voice (marketing vs light technical) and the
   presentation form (paged vs continuous-stage). A user present → ask these and wait. Unattended → write each
   open one to `build/questions.md` and take the request's most literal reading, stated
   in `build/plan.md`. "產品介紹片" alone does not settle ad vs tour (user r14); "廣告" alone does not settle intro
   vs hype (user r15). A genre or form name in the request (MAD, PV, showreel, …) is a film type
   AND the product name the film serves its topic under: resolve it against `film-types.md`
   §Naming and confirm that definition with the user before the storyboard; a name with no entry
   there is asked, never inferred — an unconfirmed name is the wrong-target / under-expectation
   failure (user 2026-10-19: one-line MAD request whose first round came back a pure-code MV).
   **Formal item or lab round?** (formal = something the author will send out or hand to someone; the one
   definition lives in `<works>/README.md`). Formal → the FIRST write of the task is
   `python -X utf8 ~/.claude/tools/design-axes-mount/works_contract.py open <works>/films/<film_id> --medium video --actor main-loop [--toolbox PATH:ROLE:FACET ...]`,
   whatever folder the request came from; paste the 創作輸入 line it prints into the boundary contract, and
   build inside the item. A generator, component or page from ANOTHER deliverable (a book's illustration
   script, a previous film) is a toolbox entry with its role and facet, never a default (a book project 2026-10-11:
   the book's line-art generator scaled to 1080p was rejected, now a negative reference). Lab round →
   `run_arm.py` mounts the same layer.
1. **Whole film first** (`whole-film-rules.md` §1): name the ONE audience, what that
   audience needs to know, the tone (the energy named in step 0; only if none, from product + audience), and the ONE
   ground colour (a hype ad loosens it, `whole-film-rules.md` §6).
   These four are fixed before any device is chosen. If the product's documents do not
   say what a feature solves, ask the owner (`build-and-export.md` §4 item 7); unattended, write
   `build/questions.md` instead of inventing a pain point.
2. **Film type** (`film-types.md`): intro ad, hype ad, product tour, data showreel, narrated explainer,
   or profile reel — from step 0's purpose, never from which skeleton is closest to hand. Pick the skeleton; decide storyboard (fixed content) vs one paragraph
   (screen many runs).
3. **Rhythm source** (`rhythm-transitions-camera.md` §1): music only → section changes on
   bar lines; narration or lyrics present → section changes on line starts, and the music
   is not also hard-locked. Whether a film gets narration at all follows the film type and
   tone (step 1-2); a quiet film may still use music with slow sections.
4. **Storyboard table before code**: read `inputs/design-axes.md` first (routing table, "Before the storyboard" row). Per section `t`, headline, visual, data, layout,
   transition in/out, camera goal, **motion intent** (one line per moving element and per
   stacked effect layer: what the motion says; an element with no line stays still or
   goes, `whole-film-rules.md` §2a; a named effect gets that line as a description, since
   a name alone whose catalogue and industry meanings collide is built as the industry
   meaning — lab r28, 3/3 runs, blinded reader; lab `docs/text-motion-vocabulary.md` §3/§5), **key frames**
   (timeline `keys[]`: at least one `role: key` per section — the moment a viewer must read or see clearly,
   with an optional `hold`; `role: breakdown` for an in-section pose that decides how motion travels; the
   seams between sections are derived, never written; lab `docs/agent-review-kbt-design.md` §3), and **參考角色 K／工具箱** (`none` by default; a reused
   generator or component names its role K and the facet borrowed, and must match a
   `--toolbox` entry of `open`). Show it to the user and wait for confirmation when a
   user is present. Record each design decision you make yourself with
   `python ~/.claude/tools/process-ledger/ledger.py add` at the moment you make it.
   The table's carrier is ruled (user 2026-10-08, lab `docs/production-order.md` last
   section): a JSON `film.timeline.json` plus a generated read-only timeline page;
   required at approval = film_type, audience, energy, rhythm_source and per section
   at, dur, freedom (locked / guided / free), motion_intent; camera goal / method take
   the fixed D1 / D2 vocabularies. The tool (`tools/timeline/`, lab
   `docs/timeline-layer-design.md`) is NOT built before its TL-1 milestone — until then
   keep the markdown table, using those field names (shot-record names that changed are
   mapped in the design's §6.1 table).
5. **Devices**: each device has its own tone; a device that clashes with step 1's tone is
   dropped, the tone is never changed to fit the device (user 2026-09-30). A stock device
   (particle burst, tunnel, floating card pile, glitch, big-text-as-design, fake HUD
   numbers) is used only with a motion-intent line tying it to content (§2a).
6. **Build** (`build-and-export.md` §1): one HTML page whose every frame is a pure
   function of time (`window.__setTime(t)`); no timers, no CSS transitions.
7. **Export** (`build-and-export.md` §2): export with filmkit, the lab's `tools/filmkit/render.py`
   (profile `lab-round`), never a hand-written capture script. It captures frame by frame,
   encodes, verifies, and only then publishes the output name; its `check.py` decides whether
   the FILE is deliverable. Formal films bundle their fonts with `@font-face` (one openly
   licensed sans family that covers CJK and Latin, e.g. Noto Sans TC; never rely on the
   fonts installed on the exporting or viewing machine, lab D26). A formal film exports
   with `--profile delivery-web` (format fields, plus FK-R-18 / FK-R-19 blocking when the
   film is not a works item opened with `open` or its mount is stale). Loudness and true peak are reported
   by `check.py` as a fact (FK-R-17, info). To judge them against a platform, pass
   `--rules <rules file> --target <name>`; a target is a claim in the rules file with its
   source and `review_when`, never assumed by the skill.
8. **Review** (`build-and-export.md` §3): 1 fps whole-film sheet first, then details;
   feedback as "second / where / change"; one change at a time; at most 3 rounds. A formal
   film is then reviewed SIDE BY SIDE: `works_contract.py review <item>` puts the candidate's
   sheet beside a same-type approved film picked by tags (or writes `reference: none`), and
   the reviewer is not the builder (§3 item 9) — in a single session a clean-context
   subagent reads `deliver/_review/side-by-side.png` and the verdict's first line is
   `reviewer: subagent-clean-context`. `works_contract.py deliver <item>` refuses until
   `deliver/_review/verdict.md` is newer than the candidate.
   **Agent-review path** (user 2026-10-19, lab `docs/agent-review-kbt-design.md`; the user gives
   direction and design content only): a maker subagent builds, the dispatching main-loop session
   reviews and never edits the film; they talk through files (`tools/review/review.py`), gates
   G0 storyboard (maker reviews the director) → G1 key stills (hard items only) → G2 K/T windows
   (feel = POLISH) → G3 whole film, at most 3 rounds each; only the fail list, filmkit blocking
   rows, product fidelity and seen-once defects may BLOCK; after round 3 the best version ships
   with the open items listed, and the verdict says `reviewer: dispatcher-main-loop`,
   `user_watched: no` (`build-and-export.md` §3 item 10).
9. **Deliver** with the acceptance shape below. Destination: a works item
   (`<works>/films\<film_id>\`, predicate in `<works>/README.md`); the project
   the user named keeps a pointer (`_MOVED_<date>.txt`) or only its own book / data. A film built
   in its own project and adopted (generator foreign) re-enters with `works_contract.py adopt <same
   root> --id <id> --revise` after each accepted round. Where every item stands:
   `<works>/STATUS.md` (read it first). A lab round goes to
   `<lab>\experiments\<round>\`.

Models (user 2026-10-10, lab CLAUDE.md Rulings; causes `experiments/r22-haiku/REPORT.md`):
Haiku never makes a film, neither as conductor nor as worker on any step above; a
component's fixed content counts as production (lab D-T12).

## Verdicts this skill may give, and how each is verified

- "Section changes sit on the bar / line" → `tools/measure_product.py` or
  `tools/narrlock.py` on the rendered MP4 (lab paths).
- "Motion is continuous under narration" → `tools/density.py` moving share and still runs.
- "Every number / feature is real" → `tools/fidelity.py` + `build/claims.json` (T05).
- "There is a camera move" → `tools/camflow.py`; `at_boundary` runs need a frame look.
- "The file is deliverable" (readable, the expected length, size and codec, sound present
  when expected, written by filmkit from the inputs now on disk) → `tools/filmkit/check.py`
  (`render.py` runs it itself). Exit 0 means no blocking row, nothing about the picture.
- "Looks good / matches the reference" → NEVER from numbers. A model-read frame sheet
  AND the user's own viewing (lab INV-6). Numbers prove the data path, not the picture.
  On the agent-review path this verdict is never given: the film is "delivered under agent
  review, not watched by the user" (verdict `user_watched: no`).
- "Loudness is on target" → `check.py --rules F --target NAME`; an UNDET for a target
  without a tolerance is a rules-file gap, not a pass.

## Delivery shape (a human must watch the film)

Paste `check.md` sections 1-4 (blocking / confirmed / needs a look / undetermined) verbatim
(section 5, the author's declared exemptions, stays in the file) — for a formal film from
the `--profile delivery-web` check, so the FK-R-18 (design-axes mount) and FK-R-19 (works
stamp) rows are among them, plus the `reference:` line of `deliver/_review/report.md`,
including the `rerun` lines, before the checklist; the session's own questions follow
separately and are never mixed into the pasted sections. Any `transform.py` operation
(`normalize` exists since filmkit M3: `transform.py normalize <in> --out <new> --target-lufs X --true-peak Y`
or `--rules F --target NAME`; duck and convert are not built) on a formal film is
asked first, naming the new file it would write (BR-14, D21). Then end every delivery with
an unasked checklist, ranked by consequence:

- `A 必驗` (≤ 7): audience right; energy is the one asked for (a hype ad stops the eye
  in the first second); ground colour locked (hype ad: only hit runs may alternate); a
  separate cover delivered; every on-screen number and feature traceable and meaningful
  to the viewer; nothing unreadable (text held long enough — a titled page/level ~3.2 s
  and up, user r19 — labels large and high-contrast, nothing cut at the frame edge); end card resolves the logo fully and holds 1.5-2.5 s (user W30 2026-10-10, replacing
  r14's 2.5-3.5 s).
- `B 體驗`: transitions feel smooth; pace fits the tone; camera moves read as intended;
  demos do not drag (waits sped up, `build-and-export.md` §1 speed map); nothing moves
  for the sake of moving (each motion matches its storyboard intent line).

Name the likely runtime failures and what the user would see: fonts not loaded (fallback
glyphs in early frames; filmkit reports a missing font family as a "needs a look" row), a
background render that ended early (filmkit never publishes the output name for it), a
blank frame from a failed asset (filmkit stops with `asset_load`). The page itself announces load failures on screen, not silently.

## Extensions (not scope)

Unvalidated items worth an imitation round, only when a film needs them: T08 line-locked
sections, T09 camera parameters, T10 shape-to-shape, T11 guide character with concept
cards and screenshots (r18, n=1; user rulings in `whole-film-rules.md` §2), and C19
click-and-grow inside a full product film (never tried). Each needs a blinded A/B before its tier is raised.

## Prior art consulted when this skill was made (2026-09-30)

`motion-design` (hub; its `local/extending.md` split criterion), `case-library` (studies
streams of cases; this skill makes films), `<prompt-shelf>` (library of past
prompts + test videos; point the user there to reuse a prompt), a post-format project
`docs/video-design.md` (carousel-to-video; its cover ruling matches §2 here), memory
`promo-video-core-rules` (now a pointer to this skill).

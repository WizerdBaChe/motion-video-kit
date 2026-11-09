# Whole-film rules — decided before any device

The lab leads; this file follows. Rules are born and ruled in
`<lab>\docs\axes-and-pairing.md` §一 (evidence per row) and
`docs/production-order.md` nodes A/F, then written back here in the same change (lab
`CLAUDE.md`; `lab-sync` marker in `evidence-and-instruments.md`; a missed write-back is
flagged by `~/.claude/tools/lab-skill-sync`). On a mismatch with a lab commit newer than the
marker, the lab wins until written back. This is the agent-facing English operating copy;
no third copy (memory, other skills) restates these rules (user ruling 2026-09-30).
Cross-medium forms of these rules (posts, decks, web pages): `~/.claude/references/design-axes/`.
Tiers: see `evidence-and-instruments.md` §Tiers.
Origin: user reviews of lab rounds r10-r13 (2026-09-29/30), stated by the user as the big
problems of ALL ad/product/promo films.

## §0 Confirm first (user r14, 2026-09-30)

Before Layer 1, settle these with the user (unattended: `build/questions.md` + the
request's most literal reading, stated in `build/plan.md`):

| # | Item | Why |
|---|---|---|
| 1 | Purpose / film type: intro ad, hype ad, product tour, explainer, profile | picks the skeleton; r14 made two detailed tours when an ad was wanted; r15 made an intro ad when a hype ad was wanted (`film-types.md` §1) |
| 2 | Where it is shown (feed, site hero, talk, YouTube) | length, ratio, sound-off reading, cover |
| 3 | What the viewer does after (download, remember the name, read docs) | the end card and its hold |
| 4 | Audience: the five reader premises defined once in `~/.claude/references/design-axes/part-principles.md` §1; record their values in `build/plan.md` (unattended) or the approval record | §1; 2026-11-02: a deck with no fixed narrator or address mixed 她/你/我 |
| 5 | The ONE thing to remember | an ad hits one point; a tour walks each feature |
| 6 | Energy (calm / lively / hype) and ground. ASK it; never infer it from the product alone | §1; r14-r15 inferred "calm" for a privacy tool and the user wanted hype; r16: naming the energy moved tone and pace (moving share 0.41 -> 0.70) |
| 7 | Materials and limits (real screens, logo, forbidden claims) | `build-and-export.md` §4 |
| 8 | Content voice: marketing / social (slogans, a closing hook) or a light technical explainer | the same content reads either way; it is a choice made per film, not a film type (user r18, 2026-10-01). Cross-medium form: axis **I register** in `~/.claude/references/design-axes/axes.md` (marketing / social = `marketing`; which explainer value a light technical explainer maps to is not yet ruled); narration-script principles in `part-principles.md` §17 [added by a science-explainer project 2026-10-10, pointer only] |
| 0 | Formal item or lab round? (formal = the author will send it out or hand it to someone; the one definition is in `<works>/README.md`) | a formal film is opened in works with `works_contract.py open` as the task's first write and must pass filmkit `--profile delivery-web` FK-R-18/19; it never lives only in the requesting project's folder (a book project 2026-10-11, formal-path design §4.5) |
| 9 | Presentation form: paged (fixed page title per section, items appear and hold, section change = page change) or continuous-stage (one continuous stage, things enter, move, leave; the eye is led by camera, dimming or a moving character) | user r18: preferred the continuous-stage arm for its presentation, not its content (n=1); lab axis `presentation`. A film may also MIX the two; named mixes (stage-led opening then pages on the dimmed same stage, pages placed in one stage world, stage bookends around paged middle, anthology, beat-cut montage) with their fail conditions are in the lab's `docs/presentation-combinations.md` — case readings only, no effect evidence yet (user 2026-10-02) |

"介紹片" alone does not settle ad vs tour, and "廣告" alone does not settle intro vs hype: ask.

## §1 Layer 1 — the whole film (fix these four first)

| Decision | Rule | Tier |
|---|---|---|
| Audience | Name the ONE group the film speaks to. Every section, including the end, speaks to it. Content on the site aimed at someone else (listing fees for shop owners in a film for readers) is a major failure, not extra value. | verified (r12: owner-facing sections 0/3 with the rule vs 3/3 without; r13 same) |
| Only what the viewer needs | How the film or data was made (sort order, data source) is noise in an ad. Every number needs a meaning for the viewer. A highlighted item needs copy saying why it is highlighted. | user (r12; r22: the user read it as a shared defect of the 10 bookcorner films, whose prompt predated and omitted this rule) |
| Tone | The energy the user named in §0 item 6 wins. Only when none is named, judge the character from product + audience (a bookshop directory = quiet, relaxed, unhurried). Pace, motion and sound follow it. | user (r10: all 9 arms too lively; r15: a privacy tool read as calm, user wanted hype); r12 arms self-judged tone correctly |
| Ground colour | One background colour for the whole film (a hype ad loosens this, §6). Accent and data colours may vary; the ground may not. A transition (a full-frame colour wipe) never counts as a ground change; only a shot's resident ground does. | verified (r12: 0-2 ground switches with the rule vs 8-11 without); transition clause user 2026-09-30 |

**Candidate, not a rule — one film-wide concept / metaphor** (lab `axes-and-pairing.md`
layer 1, waiting item W29). After the four above, a film MAY name one shared metaphor (e.g.
"film premiere") from which each device's motion intent is derived, to keep devices one
system. It does NOT loosen §2a: "fits the metaphor" is a style reason, never the content
reason a stock device still needs. On a clash with the tone, drop the metaphor. Tier:
claim, n=1, from a web-portfolio screen recording (not a film), unmeasured; user ruled it
candidate-only 2026-10-09. Do not apply it as a requirement.

The audience, tone and ground rules were given together in r12, so which rule caused which
difference is not separated; "verified" means the bundle moved the measure, not each rule
alone.

## §2 Devices carry a tone

Every device has the tone it fits. Choose devices against Layer 1's tone. **When a device
clashes with the tone, drop the device, never the tone** (user 2026-09-30). The device→tone
list is proposed by the model during later work; the user is not its first reviewer.

| Device | Fits | Tier |
|---|---|---|
| Heavy-hit punch: one full-strength hit per second, a full-frame statement on each (recipe: `film-types.md` §1b) | energetic, upbeat, hype ad; never in a quiet film | user (r10 A1 promise section, chosen again as a hype reference 2026-09-30) |
| Dark translucent dim overlay to single out a selected item | a tension device; clashes with a light, calm film | user |
| Blurred / dimmed photo as background | "not busy, more alive"; tone fit not yet judged | user |
| Book-spine colour-bar wipe | neutral-to-lively; slow it 1.25-1.5x for a calm film | model proposal (r13) |
| Red blocks stacking bottom-up (transition) | neutral; slow it for a calm film | model proposal (r13) |
| Books falling like dominoes | lively, playful; fit in a calm film unjudged | model proposal (r13) |
| Giant outline "ghost" word drifting behind a statement | none: reads hollow, ugly | user (r17) |
| 3D tilt push-in of a product screen | hype ad; text stays readable when cropped | user (r17: readable) |
| Guide character (small mascot reacting to the narration with ! ? ✓ ♥ …; T11) | a logo / brand watermark, 1/8-1/6 of frame height, never covering text; appears only where it has work (opening, chapter change, a key or turning line), otherwise leaves or shrinks to a corner mark; which moments it leaves is not yet ruled | user (r18, 2026-10-01; n=1) |
| Pointer dot moving to what is being said | none when on-screen motion already cues the point: redundant, noisy | user (r18) |
| Split-flap numbers, tilted card wall, rotating list, whoosh on every transition | not yet judged | — |

## §2a Motion intent — nothing moves for the sake of moving (adopted 2026-10-01)

Tier: claim (a motion designer's public critique of AI-made motion graphics, poyin.work on
Threads 2026-09-30, adopted by the user 2026-10-01; not measured or A/B-tested here). Lab
source: `docs/production-order.md` E and the storyboard field `motion_intent`.

- Every moving element in the storyboard has one line saying what its motion says: it
  points at data, an order, a cause, or the emphasis. No line → the element holds still or
  is cut. Example with intent: T07's particles are one point per data record; the same
  burst as decoration has none.
- Stock devices need that line before they are used: particle burst into a "universe",
  tunnel / vortex transition, floating tilted card pile, glitch / RGB split, big text
  standing in for design, randomly ticking numbers or fake HUD metadata. No line tying it
  to the content → not used. (The §2 tone check still applies on top.)
- Stacked effects: each extra layer on one element (glow, grain, blur, shake, chromatic
  split) carries its own intent line. No numeric cap yet — set one only after measuring.

## §3 Pairing principles (user, after r12/r13)

- Transitions: a fade disturbs least; many-colour transitions disturb and read as ground
  changes; a transition may carry ONE image (gathering the shops into the brand name).
- Items at once: at a fast pace, many items at once is reading load. Either one item at a
  time, or hold longer.
- Section seams: the incoming transition never covers the outgoing section's last beat.
- Ending: replay nothing without a reason; resolve the logo fully; hold it 1.5-2.5 s
  (user W30 2026-10-10 after seeing 7 film ends; r14's 2.5-3.5 s is replaced, 5.8 s and 7.4 s were too long).
  Do not hold the opening either: a 2.1 s still opening should be 1.5 s at most (user W30, no instrument yet). The
  last line pushes the viewer to act (r18 A1's "你來做吧" beat B1's ending, user r18).
- More content is not better: pick devices by film type and tone; using every borrowed
  device made r14 L's big-text verb-card transitions ugly (user r14). The same holds for
  devices the model found itself by web research: r21 D1 executed every reference it named,
  and its full-frame black/white barcode transition was unrelated to the song and abrupt
  (user r21). A researched device gets the same intent line as a stock device.
- BANNED in every film type (user 2026-10-24, wheel-promo intro + hype both failed): cutting
  away from the subject to a large-word card — a full-frame verb / title / keyword card, or a
  camera jump to a brand title mid-demo. It breaks the action the viewer is following ("跳到
  大廳標題", "快速切標題讓畫面很割裂"). Words ride ON the running shot (small caption anchored
  to the action, or the product's own UI text); the brand lives in frame and in the end card,
  never as an interrupting beat. Continuity comes from one subject and one camera path carried
  across sections; a section boundary is not a restart. Supersedes the verb card (C17) in
  `film-types.md` and §6 "ONE word per hit" as a full-frame card. Negatives:
  `design-axes/negatives.md` wheel-promo-intro / wheel-promo-hype rows (2026-10-24).
- The subject the user named stays the subject (user 2026-10-24): when the remember-one is a
  component ("展示輪盤"), the frame is that component, not the host product around it. Shots of
  the host (its title, its other tools, a list of what it contains) are context at most; a
  section whose content is the host's catalogue turns the subject into a mere carrier.
- A change of input must read as a change (user 2026-10-24, wheel-promo-hype v2): when a section
  says "a different X gives a different result" (file kind, mode, dataset), each X gets a
  prominent, distinct visual mark at the subject (its own icon / colour / large type-name
  beside the subject); a small chip plus the product's centre text read as "the same thing
  done three times". The live-component, one-take method itself passed (user: 修正通過).
- Captions sit at the subject, not in a band away from it (user 2026-10-24, v2): a step label
  parked under the subject far from where the action happens is missed at film speed; place
  it next to the acting part, clear of the subject's own text.
- Landing on the beat is not a reason to use a device (user r21): the beat map is a
  calculation aid. Decide the device from the content first, then whether to lock it. A
  target box scaling + background flash on every beat was on time and wholly unsuitable.
- Local and global agree: a transition that changes only the demo area while the
  headline card around it stays put reads as two layers doing separate things; move both,
  or use a whole-frame transition (user r14).
- Crop product screens so their text reads at film size (r14 S's type and scale preferred
  over L's, user).
- Demos never drag: real waits (probing, downloading) are sped up with the speed map in
  `build-and-export.md` §1 (user r14).
- Readability beats beat-locking: when a lock would pull a line of text off screen too
  early, give up that lock (T01 "做片時" (b), user ruling; no seconds threshold yet).
- Dwell per page / level must let the viewer finish reading: r19 A1 held each level
  ~2.15 s and the user could not finish; at least +1 s per page (~3.2 s and up; user r19,
  n=1, provisional). More text or lower contrast needs more time — fix the text first.
- In a one-take scale dive, a hard camera surge into each level (rotation + rush, r19 A1)
  was preferred over C28's same-angle soft cross-fade (user r19: 衝擊感好; tone fit open).

## §4 Materials and text

| Decision | Rule | Tier |
|---|---|---|
| Site has pictures | Use them: related, colour-unified, blurred or dimmed as background; never pasted raw | verified (r10: with/without images); treatment user |
| Short-section headline | The headline is the biggest text in its section; the shorter the section, the more it must read at first glance. Set it as ONE block: big title + one small caption line, nothing competing beside it (C28 has it; r19 A1's 40 px title crowded by status line, labels and legend read as having none, user r19) | user (r11, r19) |
| Leader-line labels | Large and high-contrast enough to be recognised at first glance; r19 A1's 11-14 px monospace on a dim ground slowed recognition | user (r19) |
| Numbers on screen | Traceable to the product; optional features marked; illustrations marked; scope words as the docs say | measured (T05, `tools/fidelity.py`) |
| Material consistency | No material type the film has not used before appears mid-film; no text colour the film has not used for text (a data colour is not a text colour) | user (r12, r13) |
| Emphasis contrast | The emphasised item needs enough contrast. How to get it on a locked LIGHT ground is still open | user (r13); open |
| Declaration line | A promise / declaration subtitle is set large: it is a declaration, not an explanation | user (r12) |
| Saturation | Fits the tone; oversaturation glares | user (r12) |

## §5 Multi-arm contests (when several versions compete)

Keep ONE arm that deliberately ignores the tone rule and plays free (user 2026-09-29).
Ask the user for per-section picks, not one overall winner.

## §6 What loosens in a hype ad (user r15/r16 reviews; r17 watched and accepted, 2026-09-30)

The §3 principles came from calm films (a bookshop directory, a privacy tool). In a hype ad
(`film-types.md` §1b) a model that follows them literally rebuilds an intro ad (r16: one
dark ground, a 12 s step-by-step GUI walk, fades, cuts on bar lines only). In a hype ad:

| Calm-film rule | In a hype ad |
|---|---|
| One ground for the whole film | a hit run (<= 4 s) may alternate or invert the ground on each hit, rotating the product's theme colours (r10 A1; C06 invert; user r17: ok); outside hit runs the ground holds |
| A fade disturbs least | hard cut, white flash, invert, slam, wipe; each kind at most once or twice (C06 uses seven kinds, each once). Negative C42 (user 2026-10-11, "轉場一直閃讓人印象很差", fatigue): one lift + blur + RGB-split flash on all 29 accent cuts of a 31 s dark-UI ad, incl. same-frame additions, peak on the incoming shot's first frame, 14.5 % of frames in decay, flashwash 40.3/min (lab card T19) |
| Lock only strong beats | every cut on a beat, section lengths 2 / 4 / 8 beats (C06, +-12 ms) |
| Features as action -> result | the product is MATERIAL: a screen is shown as one striking frame per hit (3D-tilted, pushed in, cropped to one number), never walked step by step; a real wait never appears |
| More content is not better | still holds: ONE word or number per hit, carried on the shot — never a full-frame word card (banned all types, user 2026-10-24, §3) |
| Local and global agree | still holds: a hit moves the whole frame |

Audience, only-what-the-viewer-needs, real numbers (T05) and the end-card hold are NOT
loosened.


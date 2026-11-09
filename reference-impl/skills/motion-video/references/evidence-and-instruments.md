# Evidence tiers and lab instruments

The lab is `<lab>` (case library + technique cards + isolated
imitation rounds). Its `CLAUDE.md` §Commands is the authoritative list of instruments,
their flags, real controls and limits; this page only maps questions to tools. Tools stay
in the lab (user 2026-09-30); run them from the lab root with `python -X utf8 tools/<name>.py`.
Every instrument has `--selftest`; run it before trusting a number after any edit.

## Tiers (how sure each rule is)

| Tier | Meaning | Where it comes from |
|---|---|---|
| user | the user judged it after watching films | round reviews, `experiments/*/Human_feedback.txt`, ledger rows |
| measured | a calibrated instrument read it on source films | card "量到的數字" sections, `measurements/<case>/` |
| verified | a blinded A/B round moved it, ranges disjoint (usually n=3 per arm) | `experiments/<round>/REPORT.md` |
| unvalidated | measured on sources, never tested by imitation | cards T08, T09, T10 (2026-09-30), T11 (r18 n=1); r27 (2026-10-12, bundled cards, n=3 per arm) imitated T08-T10, T13-T16, T18 once: instrument / model-reader separation only for T13 (light or window changes A 0/0/0, B 2/6/5) and T18 (problem staged before the product, model read A 0/3, B 3/3); the rest overlapped. No tier moves until the user's blind viewing (lab `experiments/r27-untested-cards/REPORT.md`) |
| observed | a model read frame sheets of source films; no calibrated instrument, no imitation (lab tag 〔候選卡〕/〔人讀〕) | cards T14-T16 (2026-10-04, still-image MADs C32-C34); T17 citation card (2026-10-11, C38); T20 argument props carried across chapters (2026-10-24, C50; carry read by eye, density/segments/blurdip measured; r37 imitation 3 v 3 disjoint on a model blind read, and the user's unblinded viewing preferred the carried version); T12 and T13 rose to measured the same day (blurdip / flashwash / framebox) |
| claim | a source author's or practitioner's statement, not measured here (lab tag 〔說法〕) | `whole-film-rules.md` §2a (2026-10-01) |

A rule rises a tier only through the next row's evidence. "Looks good" is never a tier:
it is the user's viewing (lab INV-6).

## Which instrument answers which question

| Question | Instrument (lab `tools/`) | Main limit |
|---|---|---|
| Real BPM, beats, cuts | `beatgrid.py` | bar downbeat unknown (grid x4 only) |
| Are events phase-locked to the beat | `phaselock.py` | small n is weak (random R ~ 1/sqrt(n)) |
| Section boundaries | `segments.py` (`--crop` for headline-only changes) | cannot tell a section change from an in-section push-in or a dialog |
| Section changes vs narration lines | `narrlock.py` | dense lines weaken the test; machine transcript timing ±0.1-0.2 s |
| Each narration line vs what the picture does inside it (in-section card entries, line sheets) | `avsync.py --exclude <subtitle band>` | burned subtitles fake lock unless excluded; blind to what an onset is (read the line sheets) and to continuous motion |
| Moving share, still runs, frame fill | `density.py` | pixels changing, not meaning; noise counts as motion |
| Product-intro checks (bar lock, end hold) | `measure_product.py` | boundary = midpoint of the change run |
| Narrated explainer bundle | `measure_narrated.py` | as its parts |
| Data showreel bundle | `measure_showreel.py` | as its parts |
| On-screen text and numbers vs the product | `fidelity.py` (`--viewport WxH` for vertical); needs a corpus spec pinned to the product commit the film saw — copy the shape of `rounds/r14-mfp-corpus.json` (root, globs, number_globs, optional_features; demo data in `globs` only) | review list, not a verdict |
| Camera moves (zoom/pan/rotate per section) | `camflow.py` | screen space only; transitions read as moves (`at_boundary` = look); blind to a push-in on one part of the frame (a card's own tilt, a screenshot zooming inside a window frame, C25) |
| Guide character moving while the rest is still (T11) | `guidechar.py --key R,G,B` | colour, not identity; real controls overlap (C25 0.285 vs C20 0.148), so descriptive only |
| Shape-to-shape at a transition | `shapematch.py` | mask overlap, not identity; blind to a one-frame ground swap |
| Ground colour switches | `bgswitch.py` | full-bleed illustration unmeasurable |
| Spring fits | `springfit.py` | only `spring_consistent: true` fits are cited |
| Contact sheets | `sheets.py` | — |
| How a whole film is cut and coloured: shot count, ASL vs MSL (mean vs median shot length), longest/shortest shot, colour barcode, side-by-side compare; swatch sheets pairing each shot's frame with its colour (`--swatches`, gap > 40 = colour moves inside the shot) | `shotstats.py` (`--compare`, `--swatches`) | hard cuts + fades through white/black only; over-splits hand-drawn fast action with impact frames; misses dissolves that never go near-blank; motion graphics need `segments.py` events via `--cuts-json`; colour is a mean, not a palette (a many-coloured frame averages to a colour it does not contain), so never cite it as a film's palette |
| Blur transitions: blurred-then-sharp vs crossfade vs flash (T12) | `blurdip.py` (`--auto` or `--events`) | why a frame is soft is unknown (filter, defocused source, fast pan); a heavy blur of a low-contrast still reads flat-dip; `crossfade-like` is a depth class, not a dissolve |
| White flashes, colour washes, black dips, mono-to-colour (T13) | `flashwash.py` | a tint over a still-visible picture is missed; a flash decaying slowly into a bright shot is missed; pale washes read white-flash; a cut through an empty pale ground (cream paper) reads white-flash — `shapematch.py`'s dip-through-ground is the right label there (C39 7.38 s); a colour change confined to one small object is not seen (C39 6.7 s icon grey to orange read none) |
| Frame window: letterbox / pillarbox / strip (T13) | `framebox.py` | side edges only (no slanted top/bottom); a dark straight picture edge at the side reads as an inset; a window over a dark but not pure-black band reads full (r27 MB1, #141218) |
| Staggered entrances per section; lyric line placement (T14, T16; our own pages only) | `domlayers.py <index.html>` (DOM reads through `__setTime`, not the video) | canvas content invisible (a section >= 50 % canvas reads undetermined); clip-path masks not modelled; real controls r3 B1 3 layers vs r20 A1 1; the centred-subtitle rule has no real positive control yet; lyric lit glyph by glyph (karaoke) counts each glyph as a layer, so read `layers_excl_lyric` beside it (r27 MA2); subtitle placement is position only — a styled per-glyph reveal centred low reads "subtitle" (r27 MB1) |
| Which music stream the cuts follow (beat, accent, loudness change, section, harmonic change, lyric lines) | `cutdrivers.py` | streams from the mix overlap (a section bound is also a beat); lyric lines need a transcript, and `lyriclines.py` (speech recognition on singing) is PROVISIONAL: it fails its selftest |
| When a new line of on-screen text appears (lyric / subtitle line starts as candidate cut drivers) | `screenlines.py` (Windows OCR, `--lang ja` etc.) | PARTIAL: C31 control recall 0.54 within 0.5 s, onsets ~0.26 s late (reads a word once settled); cannot tell lyrics from manga balloons, titles or UI, so pair it with a model frame read of the text events |

Rejected: `sfxlock.py` (missed its real positive control); do not cite it. Provisional:
`lyriclines.py` (fails its selftest; numbers go to case notes only); `sfxclap.py` (whoosh on
transitions via CLAP, 2026-10-20: 8 of 9 real controls on r9 arm scripts, thin margins, blind to
booms and impacts, never tried on recorded sfx; cite with those limits, never as a card number). Partial: `screenlines.py`
(candidates only, never a card number).

## Sync with the lab

The lab leads; this skill follows. lab-sync: `54478e5` (2026-10-10: D18 thresholds and end hold 1.5-2.5 s; r22 blind ratings, evidence on the viewer-info rule; 2026-10-09: filmkit M2-M3, licensed fonts; 2026-10-01: r18 rulings, T11,
§2a motion intent, presentation renamed paged / continuous-stage; the lab's
`material_source` axis is case labelling only, not taken into the skill). Watched by `~/.claude/tools/lab-skill-sync` (pair `motion-video`,
system-hmi point `lab-skill-sync.motion-video`): a lab commit after that sha touching
`techniques/` or `docs/{axes-and-pairing,production-order,taxonomy}.md` turns it warn at
session start. After writing back, move the marker in the same change:
`python -X utf8 tools/lab-skill-sync/sync.py mark motion-video` (from `~/.claude`).

## Reuse before rebuilding

- Past prompts and the test videos they produced: `<prompt-shelf>` (GUI library).
- Source cases and their analyses: `<lab>\cases\INDEX.md`
  (generated; tags per `tools/taxonomy.json`, including the `camera` goal axis).
- Studying a NEW stream of reference videos is the `case-library` skill, not this one.

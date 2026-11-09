---
layer: cross-round instrument
audience: builder
status: active
date: 2026-10-24
origin: ~/.claude/outputs/motion-video-convergence-20261018/提案單_影片出片收斂_20261018.md (ruled 2026-10-18); user 2026-10-24 order and scope rulings (session ledger 2c5b9dda rows 1-3)
---

# Convergence build: quality floor, product state table, required assets

## 0. 給你的摘要（使用者裁定的部分，中文）

- 這一輪只做產品類（你 2026-10-24）：品質底線、產品狀態表、指定素材保證。時機依據欄等下一支音樂類片再做（範圍暫縮，解除事件＝下一支音樂類片開案）。
- 第一支驗收片：大廳拖放輪盤的宣傳片，社群貼文、直式 1080x1350、20–30 秒；大廳實景為主，獨立示範頁只補手勢特寫；獨立素材做在 AssetVault 候選卡旁，不進 `assets/`（U1–U3）。
- 基調：吸睛而且愉悅，**不能有心跳脈動或抽動**；可以加純程式渲染的轉場與資訊補充頁，可當不同組別比較（你 2026-10-24）。
- 片型與能量（你 2026-10-24）：兩支片，介紹型廣告走活潑、炒熱型廣告走高能；每張導演表各做 2 次；記住的一句＝輪盤怎麼操作；只配樂＋畫面字卡，不配旁白。
- 抽動的成因已查明（`experiments/probe-text-shimmer-2026-10-24/REPORT.md`）：技巧卡 T09 的「背景呼吸型」整台慢推，讓即時文字每格重新點陣化而跳動。這一輪把它從卡片和 skill 改掉，品質底線也會量它。
- 品質底線只報量到什麼，不判斷好不好看（INV-6）；抓到就由做片的對話修好再出片，修好才給你看。

## 1. Scope and order

| Milestone | What | Gate |
|---|---|---|
| M1 | `tools/filmkit/pagescan.py`: per-frame page scan, rows QF-1 shimmer, QF-2 one-frame pop, QF-3 font per node, QF-6 pulse | each row fires on its known-true control and stays silent on its known-false control (§4); `filmkit/selftest.py` + `filmkit_rules_selftest.py` green |
| M2 | timeline schema: `product_state[]`, clip `shows_state`, asset `required`; `tl validate` rows TV-20..TV-22; pagescan rows QF-7 state text, QF-8 required asset | DIT `film.timeline.json` still validates unchanged; synthetic positive/negative per row; `timeline/selftest.py` green |
| M3 | write-backs: T09 breathing type, skill `rhythm-transitions-camera.md` Breathing line, `film-types.md` §1b per-beat ring pulse; design-axes `negatives.md` rows for shimmer and pulse | `lab-skill-sync` marker moved; `digest.py check` passes |
| M4 | acceptance films (radial-wheel promo): two director tables, intro ad at energy lively and hype ad at energy hype, each built 2 times; the code-rendered transition / info pages ride as a separate group inside one build of each (user 2026-10-24, replaces "one table built 3 times") | measures of proposal §7 for the product class; user watches |

Deferred (degradation order declared in the boundary contract): QF-4 floating and QF-5 alignment need declared attach relations; they are not built this round and are listed in §6 as gaps. Lift event: a product film whose picture is page-drawn UI (not real footage) is opened.

## 2. pagescan (M1)

CLI: `python -X utf8 tools/filmkit/pagescan.py <page> --duration S --size WxH [--fps N] [--plan film_plan.json] [--stride K] [--out-prefix P] [--json]`.
Reads the page through the kit's `PlaywrightBackend` (same seek and load contract as `render.py`); never reads the MP4, never writes beside the page except `<prefix>.pagescan.json` / `.md`. Every row is `look` or `info`; nothing blocks (INV-6). Exit 0 ran, 3 some rows undetermined, 1 page failed to load.

Per sampled frame it reads, for every visible element that owns a text node: id (stamped once as `data-qf`), own text, client rect, effective opacity (product over ancestors), effective scale (rect width / offsetWidth), and the screenshot.

| Row | Measures | Fires when (initial, provisional) | Declared exemption |
|---|---|---|---|
| QF-1c `slow_scale_on_text` (cause, DOM only) | per text element, the 5-frame mean of its per-frame relative scale rate, with unchanged text and opacity >= 0.95 | rate stays in [0.002, 0.15) /s for >= 1.0 s | none: a hold is still or it moves on purpose |
| QF-1 `text_shimmer` (pixels, inside QF-1c segments only) | ink centroid normalised by the element's rect, minus a quadratic trend, converted back to px; ink density residual | median residual >= 0.25 px | none |
| QF-2 `one_frame_pop` | text element going from absent or opacity < 0.1 to opacity >= 0.9 between two consecutive frames | any, outside a declared cut window | `film_plan.json` `cuts[]` (times, +-1 frame) |
| QF-3 `font_node` | `CSS.getPlatformFontsForNode` for every visible text element, every `--font-stride` frames (default 15) | the platform font used is not the first family in the element's computed `font-family` | none |
| QF-6 `pulse` | per element, effective scale and opacity series; count of alternating extrema with amplitude >= 1 % scale or >= 0.1 opacity | >= 3 cycles within 4 s on one element | `film_plan.json` `pulses[]` with `why` (a content-driven pulse, T12) |

Calibration facts (probe 2026-10-24): smooth push residual on r33 B2 0.54 px median vs 0 with the push removed; the 0.25 px threshold sits between them and is provisional until §4's controls are run.

Design correction during M1 (2026-10-24): the first build read pixels over every moving run of a text element. On r27 PB1 (user r32: no build error) it listed 27 runs with residuals up to 9 px: long runs span eased camera moves and other elements passing over the rect, so whole-run pixel residuals cannot separate jitter from contamination. The gate now rules only on what it can determine: the DOM drift (QF-1c) decides, pixels are read inside drift segments only. Result on PB1: 0 findings in 0-27 s (fast punctuation pushes, drags), 4 findings in its closing "breath" pull-out 27.3-31.3 s (rate -4.7 %/s, residual up to 1.1 px). PB1's ending therefore carries the same cause and is not a known-false for QF-1c; its first 27 s are.

Blind spots, stated in every report: canvas and WebGL text (no DOM node; rows read `undetermined` for a page whose visible text area is >= 50 % canvas); an element that changes text mid-run is split into runs; fonts sampled every stride frames.

## 3. Director-table fields (M2)

All additive and optional in schema v1 (no `schema_version` bump; absent fields keep today's behaviour).

```json
"product_state": [
  {"id": "ST1", "facts": {"wheel_open": true, "slots": 5, "file_kind": "image"},
   "source": "claim ref, e.g. lobby:drop-wheel.test.mjs#open"}
],
"tracks": {"picture": [{"id": "S2", "shows_state": ["ST1"], "...": "..."}]},
"assets": [{"id": "lobby-cap", "kind": "capture", "path": "...", "sha256": "...",
            "required": {"min_visible_s": 2.0, "no_crop": true}}]
```

| Row | Stage | Check | Severity |
|---|---|---|---|
| TV-20 | static | product film (the validator's `PRODUCT_FILM_TYPES` in `tools/timeline/_tl/validate_static.py`, or an asset with `claims_ref`) that declares `product_state`: every picture clip of role `feature` names `shows_state`; every state has `source` and non-empty `facts`. A product film without `product_state` gets one info row (opt-in, so DIT-era films keep today's behaviour; ledger 2026-10-24) | look (validate) / blocking (approve) |
| TV-21 | static | `shows_state` ids exist; `facts` values are scalars | blocking |
| TV-22 | static | an asset with `required` is referenced by at least one clip (`device.params`, `visual`, `what` ids) | blocking |
| QF-7 `state_text` (pagescan) | timed | for each clip with `shows_state`, the declared fact values that are strings or numbers appear in the DOM text of that clip's window | look |
| QF-8 `required_asset` (pagescan) | timed | each element carrying `data-asset="<id>"` for a required asset: visible seconds, smallest visible fraction of its own box inside the viewport (crop), aspect drift vs natural size | look when below `min_visible_s`, cropped with `no_crop`, or aspect drift > 1 % |

`compile` (TL-1) is still not built: for M4 the page author copies `cuts`, `pulses` into `film_plan.json` and marks required assets with `data-asset`; `tl.py` stays the validator. QF-7 and QF-8 read the director table itself (`pagescan.py --timeline <film>`: `film.timeline.json` plus `build/timeline.resolved.json` for the clip windows), so states and required assets are never copied into the plan.

Built 2026-10-24: model whitelists + shape checks (TV-1), TV-20/21/22 in `validate_static.py`, TV-20 in `approve`; controls `tv20_22` and two schema fixtures in `timeline/selftest.py` (201 pass); pagescan QF-7/QF-8 with controls QF-STATE (page) and QF-TL. DIT `film.timeline.json` read with the new rows: 0 blocking, one TV-20 info row (no table).

## 4. Controls (must be run before any row is cited)

| Row | Known-true | Known-false |
|---|---|---|
| QF-1/1c | r33 B2 21.0-22.8 s as built (user: 「sheet的畫面一直在抖」) | same page with `PUSH = 0` (probe copy) |
| QF-2 | synthetic page: text opacity 0 -> 1 in one frame | synthetic page: 0.3 s fade; and the same one-frame cut declared in `cuts` |
| QF-3 | synthetic page: `font-family: "NoSuchFace", serif` on CJK text | same page with an installed family; r27 PB3 (FK-R-6 passed it; user saw 「字體也有一部分跑掉」) is reported as found or not found, not used to tune |
| QF-6 | synthetic page: scale 1 -> 1.05 -> 1 every beat (0.5 s) for 4 s | synthetic page: one 0.4 s scale-in then hold |
| QF-7 | synthetic page missing a declared fact string | same page with it |
| QF-8 | synthetic page showing the asset 1.0 s with `min_visible_s` 2 | 2.5 s, uncropped |

Real-page known-false for QF-1: r27 PB1 22-28 s (user r32: 「沒什麼"錯誤"」), reported, threshold not tuned on it.

Real-page results, full 32 s at stride 1 (2026-10-24; r27 pages as built, no threshold tuned on them):

| Page | User's words (r32 / r27) | QF-1c | QF-1 | QF-2 | QF-3 | QF-6 |
|---|---|---|---|---|---|---|
| r33 B2 21.0-22.8 s | 「sheet的畫面一直在抖」 | 14 (0.87 %/s) | 5 | 0 | 0 | 0 |
| same, push removed | (control) | 0 | 0 | 0 | 0 | 0 |
| r27 PB1 | 「沒什麼"錯誤"」 | 4, all in the closing breath pull-out 27.3-31.3 s | 4 | 0 | 0 | 0 |
| r27 PB2 | 「幾乎都沒有過渡幀，很多文字的呈現是flash in?」 | 4, closing pull-out | 4 | 5 | 3 (Consolas stack falling back to Noto Sans TC for CJK; one Noto line rendered by Consolas) | 0 |
| r27 PB3 | 「畫面嚴重抖動」「字體也有一部分跑掉」 | 31 (9.5-16.7 s drift x1.55 -> x1.61, plan 「slow drift to x1.61 until 16.66」) | 12 | 2 | 0 | 0 |

- The first build read pixels with OpenCV; filmkit allows only the standard library and Playwright (FK-INV-7 failed), so pixels are now read in a second pass, only for frames inside QF-1c segments, from clipped screenshots decoded by a standard-library PNG reader (control QF-PNG). Rescan of r33 B2 21.0-22.8 s: push 14 / 5, no push 0 / 0, the same counts; per-segment residuals moved by at most 0.08 px (BT.601 luma instead of OpenCV grey).
- QF-2 first read every frame of a page that rebuilds its text nodes each frame as a pop (PB3 「計時中」 at every frame from 20.2 s); fixed by tracking an element across frames by text and position (`track_ids`), then PB3 2, PB2 5, PB1 0.
- PB3's font complaint is not located: QF-3 lists nothing, and r27's filmkit render and r32's `subframe_render.py` render match at 1.0 s. Open gap; the row is not tuned to find it.
- QF-6 lists nothing on any r27 page although the user heard 「還是有奇怪的HEART BEAT」 in all of them (r27 M-group notes, not P): the r27 heartbeat was a T12 short blur (a filter), which this DOM row does not see (stated blind spot). r27 PA2 did not load from the experiments folder (fonts live in the arm workspace) and its complaint is an alignment one (QF-5, deferred).

## 5. Not doing

No new imitation round; no TL-1 compiler; no aesthetic verdict; no change to `render.py` / `check.py` defaults this round (pagescan is called by the maker session after render; wiring it into `render.py` waits until M4 shows the rows are stable); no music timing column.

## 6. Gaps carried

- QF-4 floating / QF-5 alignment: user evidence r27 PA1 13-15 s, r33 B1 conflict scene, r32 PA2 header, r33 月報表 left-aligned; needs declared attach relations or a state table that names the geometry. Lift event in §1.
- Translucent overlay "dirty" picture (r27 PA1, r33 A3): pixel-perceptual, no instrument.
- Whether a pre-rasterized image scaled slowly stays smooth is untested; until tested a hold keeps text still.

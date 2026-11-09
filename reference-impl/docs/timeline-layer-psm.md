---
layer: PSM (build spec)
audience: builder (an implementing session); §0, §10.2's acceptance list and §15 are for the user
version: v1.2 (2026-10-11)
design: docs/timeline-layer-design.md v4.5 (v4.3 + the PSM write-backs listed in §14.3; v4.5 = the user's D-T12 Haiku ruling)
verification: design v4.1 -> verification_timeline-layer-design-v4.1_2026-10-09.md (pass-with-fixes, 0 BLOCK, Z-1/Z-3..Z-9 to this table); PSM v1 -> verification_timeline-layer-psm-v1_2026-10-10.md (BLOCKED: 2 BLOCK P-1/P-2, 8 should-fix P-3..P-10, 2 user rulings U-1/U-2); v1.1 applies P-1..P-10 (§14.5)
host baseline: lab main 931c4cd (filmkit M0-M3 + D18 + FK-W32-33 merged: rules file has end_hold and head_hold; v1 was written on 9def87b and rebased, P-9)
status: written; timeline layer not built
---

# timeline layer PSM: build spec

This is the platform-specific build spec for the timeline layer (`tools/timeline/`, entry `tl.py`). The design (`docs/timeline-layer-design.md`, cited as "design §n") owns the WHY, the business rules (BR-n), the semantics (SEM-n), the invariants (TL-INV-n), the check rows (TV-n), the state machines and the decisions (D-Tn). This document owns the HOW: files, schemas, function signatures, CLI, algorithms, error paths, rollback and test mapping. A line that settles something the design left open says `PSM decision` and names what it closes. Where this spec would contradict the design it does not: the design wins, and the builder stops and reports.

Every interface with filmkit is bound to the code on lab main 931c4cd (re-read after the rebase from 9def87b), read for this spec, not to the design's description of it: `tools/filmkit/film_plan.schema.json`, `tools/filmkit/_fk/spec.py` (`PLAN_KEYS`, `validate_plan`), `tools/filmkit/_fk/common.py` (exit codes), `tools/filmkit/_fk/guard.py` (`OutputLock`), `tools/filmkit/_fk/summary.py` (five lines), `tools/filmkit/render.py --help`, `tools/filmkit/profiles.json`, `tools/filmkit_rules.json`, `tools/filmkit_rules_selftest.py` (`TOP_KEYS`, `rule_tokens`). Where filmkit's PSM text and its code differ, the code is cited.

Language: English by contract (build spec). §0, the A/B acceptance lists in §10.2 and §15 are in Traditional Chinese because the user rules on them. User-facing strings the tool prints into human pages (`timeline.html`, `questions.md` headings) are Traditional Chinese; machine output (five lines, JSON) is English.

Completeness labels: TL-0 is specified to the build bar and has its work card (§10.2). TL-1 is specified at contract level (§8.1); its work card is written after TL-0 lands, from this section. TL-2 … TL-5 are **SKELETON** (§8.2–§8.5): they name files and contracts but leave forks the design itself left open (TTS engine, music analysis shape); an implementing session must not build them from this document.

## §0 給使用者的摘要與待裁決事項

- 這份是時間軸層的施工規格 v1.1，對應設計 v4.3（本 PSM 把驗證報告要求寫回設計的幾處小字一併改成 v4.4，對照在 §14.3）。TL-0 有完整施工卡（§10.2），TL-1 寫到介面契約，TL-2 以後標為骨架。
- **和 filmkit 的介面以 main 上的程式為準**：filmkit 已經建到 M3，並套用了你 W30 的 D18 裁決。所以設計裡「filmkit M2 之前省略 `--rules`、`--film-type`」那一套分階段已經不需要：出片指令一律帶這兩個旗標（規則檔不在時只省略 `--rules`）（X-5）。`film_plan.json` 的欄位照 filmkit 的 schema 檔逐欄對好，不加任何 schema 以外的欄位（§8.1.4）。
- **片型詞彙**：本層直接用 filmkit 規則檔的七個英文代號（`intro-ad`、`hype-ad`、`product-tour`、`data-showreel`、`narrated-explainer`、`profile-reel`、`music-video`），來源是 motion-video skill 的 `film-types.md` 各節；對照表在 §4.3，不另造一套。
- **片尾停留 2.0 s**（D-T23）落在你 W30 裁定的 1.5–2.5 s 中間；TV-7 讀的是規則檔裡 filmkit 同一個 `end_hold` 範圍，不另存一份數字。
- **我替你定的（皆可逆，記在 §15 與 process ledger）**：正式片的工作資料夾放在 lab 的 `films/<片名>/`（DIT 是第一個），影音與 `build/` 不進 git（`build/questions.md` 除外，使用者 2026-10-11）；A/B 輪掛載時間軸庫改成 **arm 層** `timeline_lib: true`（驗證報告 Z-1 的建議，同一輪可以交錯「有／沒有」，預設仍是不掛，符合你 2026-10-08 的裁決）；TL-0 用「字數 ÷ 每秒 4 字」估算旁白長度，只用來畫虛線預覽，估算版本一律不能核可。
- **你的裁決**（2026-10-11 TL-0 施工 session 問答；v1.2 記入，每題下方是你的回答）：
  1. **DIT 第一份時間軸要不要有旁白？** 設計（§6.7、TL-1、TL-2）一路假設 DIT 片有旁白（九句），但 DIT 的 brief 草稿和 r7 兩支片都是**配樂、沒有旁白**（r7 V1：120 BPM 合成配樂）；配樂小節當節奏來源要到 TL-4 才有。建議：**有旁白**，句子只取 README／USER_GUIDE 原文的說法（每句帶出處），由 TL-0 施工時起草、你在時間軸頁上看過再定。若選「不要旁白」：DIT 在 TL-0～TL-3 只能用 `rhythm_source: content`（換段不對句首，也還不能對小節），TL-1／TL-2 的「DIT 有旁白出片」證據要換一支片。
     → **有旁白**（建議項）。片型 product-tour、受眾「想知道到底ai都在做什麼的agent使用者」（人物特性，不是身分標籤）、能量 lively、節奏來源照設計走（narration）。
  2. **A/B 掛載放 arm 層還是 round 層**（Z-1）：我已採 arm 層（理由見上）。如果你在意「防止整輪誤掛」，那是一個值得記下的價值判斷，說一聲就改回 round 層。
     → **arm 層**（建議項）。
  3. **哪些片算「產品片」**（驗證 U-1）：我定為 `intro-ad`、`hype-ad`、`product-tour`、`data-showreel` 四種，加上任何掛了宣稱出處 (`claims_ref`) 素材的片；產品片的標題、數據、旁白裡出現數字卻沒寫出處時，`validate` 只標「要看」，`approve` 會擋。這會改變你核可一支片的條件。建議：先照這樣，第一支 DIT 片做完再決定要不要放寬（例如 `data-showreel` 不擋）。
     → **照建議**：四種片型＋掛 `claims_ref` 的片；第一支 DIT 片做完再看要不要放寬。
  4. **D-T12「元件固定內容可用 Haiku」還算不算數**（驗證 U-2）：你 2026-10-10 裁定 Haiku 不用於影片製作；元件庫的固定內容撰寫（W28 潔淨分析抽取）算不算在內，要你說。在你回答前，本層任何里程碑都不派 Haiku（設計 D-T12 已加註）。
     → **跟全域一樣**：Haiku 只用於蒐集、盤點這類有硬驗收閘的機械任務；元件固定內容的撰寫是製作，不派 Haiku（設計 v4.5 D-T12 已改）。
- 驗證（`docs/verification_timeline-layer-psm-v1_2026-10-10.md`）判 BLOCKED：2 個 BLOCK（秒數捨入會讓三分之二的片長過不了 filmkit 的整數格檢查；一項檢查放錯階段）與 8 個 should-fix，v1.1 全部修了（§14.5）。
- TL-0 不需要 filmkit 出片，可以馬上開工；TL-1 依賴 filmkit M0（已完成）。

## §1 Scope and order of work

Build order is fixed: TL-0 → TL-1 → TL-2 → TL-3 → TL-4 → TL-5 (design §9). Each milestone is one work card with its own branch (`feat/timeline-tlN`), acceptance gates and commit set. A later milestone never edits an earlier milestone's acceptance evidence; it adds its own under `measurements/timeline/tlN-evidence-<date>.md`.

Degradation order (design §9): cut TL-4 first, then TL-3's `revise`, then TL-2's music mixing. Never cut: TL-0's format, validation and resolution; TL-1's `ClipContract`.

Out of scope (design §1.4): an editing GUI, generative video, auto-composed music, online TTS, any quality judgement (INV-6), re-implementing anything filmkit does, replacing lab instruments, mounting the component library in an arm by default.

Off-limits while building any milestone: every finished `experiments/<round>/` folder (read-only evidence; reading inputs such as `experiments/r4-dit/inputs/README.md` is allowed, writing is not), and `rounds/r22*`.

## §2 Platform pins

| Item | Pinned | Source |
|---|---|---|
| OS | Windows 11, NTFS | design §2.5 |
| Python | 3.12.7, **stdlib only** for `tools/timeline/` in TL-0 (no numpy: the library is mounted into arm workspaces in TL-5, like the filmkit kit, FK-INV-7) | PSM decision (closes design §2.5 "versions pinned in the PSM" for TL-0) |
| ffprobe | 8.1 (gyan.dev essentials), used by TL-0 only for `Asset.duration_s` (TV-17) | design §2.5; filmkit PSM §2 |
| Playwright (Python) + Chromium | 1.62.0, used from TL-1 (`texts()` in `validate --timed`, TG-15) | filmkit PSM §2 |
| filmkit | lab main 931c4cd: M0–M3 + D18 + FK-W32-33 (head hold, local motion) built; `render.py` flags as printed by `--help` (§8.1.5) | read 2026-10-10, rechecked 2026-10-11 |
| Local TTS, faster-whisper, Breeze-ASR-25 | not pinned: TL-2 trial (D-T11) | SKELETON |
| beat_this | not pinned: TL-4 | SKELETON |

`timeline.resolved.json` and `approval.json` record the runtime hash (§4.12); `validate.json` records the Python and ffprobe versions. A version different from this table is recorded, not an error; §13 says which controls must then be re-run.

Platform-conditional gaps (design §10) re-run for TL-0 on the pinned versions: TG-7 (frame snapping), TG-8 (normalized hashing), TG-16 (read-only + rename), TG-17 (paths), TG-18 (byte lock). Each is a selftest control (§10.1); a control that no longer holds stops the milestone and goes back to the design. TG-9, TG-10, TG-14, TG-15, TG-19 are re-run in TL-1; TG-1, TG-11, TG-12, TG-13 in TL-2; TG-2 in TL-4.

## §3 File layout

### 3.1 Library (`tools/timeline/`; mountable as one folder in TL-5)

```
tools/timeline/
  README.md                    English usage; first lines = upgrade condition (design §3.1) and "format and timing checked, pictures not judged"
  MANIFEST.txt                 file list; library hash and runtime hash inputs (§4.12)
  tl.py                        CLI entry (argparse sub-commands, §5.1); first lines insert its own folder into sys.path (works under python -I)
  film.timeline.schema.json    JSON Schema (draft 2020-12) for film.timeline.json; documentation + fixture agreement (§4.1)
  selftest.py                  every control of §10.1/§10.2; fixtures generated into a temp dir at run time; same sys.path insert as tl.py
  _tl/__init__.py
  _tl/common.py                exit codes, TlError hierarchy (one class per kind, §5.3), atomic write with retry, five lines
  _tl/nhash.py                 normalized hashing, folder hash, library and runtime hash (§4.12, TL-INV-1)
  _tl/lock.py                  FilmLock: OS byte lock on <film>/.tl.lock (TG-18)
  _tl/defaults.py              production defaults (lead/line_gap/section_gap/tail, estimate rate); runtime-hashed
  _tl/model.py                 load + validate film.timeline.json (stdlib validator agreeing with the schema file), typed views
  _tl/timeref.py               TimeRef / dur grammar parser (§4.2)
  _tl/rules.py                 read the shared rules file: end_hold range, film_types, params.timeline (§4.10)
  _tl/components.py            component.json validation, library index build/load (`tl.py index`), evidence.json merge
  _tl/select.py                design §6.8 tables A and B, candidate files
  _tl/uses.py                  `uses` extractor for clip programs (§6.5); TV-13 scan added in TL-1
  _tl/validate_static.py       static rows (§7)
  _tl/resolve.py               anchor resolution (§6.7)
  _tl/validate_timed.py        timed rows (§7)
  _tl/state.py                 state.json, transitions (§4.7), version integrity check
  _tl/approve.py               versions/<n>/ and approval.json (§4.8)
  _tl/view.py                  build/timeline.html (§6.11)
  _tl/at.py                    seconds -> clip/line query (§6.12)
  _tl/currency.py              "is the previous step's product current?" (§5.4)
  _tl/messages_zh.py           Traditional Chinese message templates for timeline.html, keyed by message_key (§7)
  components/INDEX.md          GENERATED by `tl.py index`; never hand-edit
  components/index.json        GENERATED by `tl.py index`; never hand-edit
  components/evidence.json     component evidence states and flags, keyed id@version (§4.9); written by tools only
  components/<family>/<name>.v<version>/   one folder per component version (TL-1 on): component.json, component.js, selftest fixture
```

TL-1 adds `_tl/compile.py`, `_tl/mix.py`, `_tl/voice_import.py`, `_tl/plan.py`, `runtime/filmpage.js`, `runtime/page.html.tmpl`; TL-2 `_tl/voice.py`; TL-3 `_tl/intent.py`, `_tl/revise.py`. A file is listed in `MANIFEST.txt` from the milestone that creates it; an unlisted file under `tools/timeline/` (except `__pycache__/`, `*.pyc`) fails `selftest.py`.

PSM decision (closes design §2.3 "lock 沿用 filmkit"): `_tl/lock.py` **duplicates** filmkit's `OutputLock` mechanism (`os.lseek(fd, 0, 0)` before `msvcrt.locking(fd, LK_NBLCK, 1)`, same before unlock; `fcntl.flock` off Windows) instead of importing `tools/filmkit/_fk/guard.py`: filmkit's `_fk` is private to a self-contained kit, and the timeline library must stay mountable without it. A comment in `lock.py` names `tools/filmkit/_fk/guard.py` as the source of the `lseek` detail.

### 3.2 Lab-side files (never copied into a workspace)

| Path | Purpose | Milestone |
|---|---|---|
| `tools/filmkit_rules.json` | shared rules file (D-T18). The timeline layer reads `film_types`, `rules[id=end_hold].range_s` and its own `params.timeline` (§4.10); TL-0 adds `params.timeline` (filmkit never reads `params`, filmkit PSM §4.5; `filmkit_rules_selftest.py` checks top-level keys only, `TOP_KEYS`) | TL-0 (add keys), TL-1/TL-2 (more keys) |
| `films/<film_id>/` | formal films' working folders (§3.3); DIT = `films/dit-promo/` | TL-0 |
| `measurements/timeline/` | per-milestone evidence notes | TL-0+ |
| `tools/density.py` | `end_hold` measurement extension (RG11, Z-5) | TL-3 |
| `tools/run_arm.py` | `timeline_lib` mounting (RG5, Z-1) | TL-5 |

PSM decision (design §3.1 left the parent folder of `<film>/` open): formal films live in the lab under `films/<film_id>/`; arms keep their own workspaces. `.gitignore` gains (TL-0): `films/*/build/*` with the exception `!films/*/build/questions.md` (hand-written, tracked; user ruling 2026-10-11), `films/*/.tl.lock`, `films/*/voice/*.wav`, `films/*/versions/*/voice/`, `films/*/assets/**/*.mp4` (the root `*.mp4` rule already covers it; the line documents intent), and a comment that every other file under `films/` is tracked text. Upgrade condition unchanged (design §3.1): a second project calling the layer moves it out.

### 3.3 Per-film folder and ownership

```
films/<film_id>/
  film.timeline.json          author (human or AI); tl never writes it
  clips/<clip_id>.js          author: guided/free clip programs (classic scripts, §8.1.1)
  assets/                     author: everything the film uses (text tracked, media ignored)
  voice/lines.json            author (TL-0: est_dur) / voice + voice --import (TL-1+); §4.4
  voice/<line_id>-<key8>.wav  voice (TL-2) / voice --import (TL-1)
  state.json                  tl (state.py) only
  versions/<n>/               approve only; read-only after writing (§4.8)
  .tl.lock                    lock.py (byte lock; empty file, stays)
  build/                      see the owner table below
```

| `build/` file | Owner (sole writer) | In `MANIFEST.json` | Milestone |
|---|---|---|---|
| `validate.json` | `validate` | no | TL-0 |
| `clips/<id>.candidates.json`, `clips/<id>.transition.candidates.json` | `validate --static` | no | TL-0 |
| `timeline.resolved.json` | `resolve` | no | TL-0 |
| `timeline.html` | `view` | no | TL-0 |
| `questions.md` | the author (model) when the user is absent; `approve --by model` reads it | no | TL-0 |
| `index.html` + its flat dependencies, `film_plan.json`, `events.json`, `captions.srt`, `mix.wav`, `render.cmd.txt`, `MANIFEST.json` | `compile` | yes (all but `MANIFEST.json` itself) | TL-1 |
| `intent.json`, `intent.md` | `intent` | no | TL-3 |
| `revisions.md` | `revise` | no | TL-3 |
| `final.mp4`, `render.json`, `check.json`, `check.md`, `sheet_1fps.png`, `<file>.check.*`, `*.transform.json` and transform outputs, `.filmkit/` | filmkit | no; tl never writes, deletes, moves or replaces them, and never replaces `build/` as a folder | — |

Every tl write is atomic (`.tmp` beside the target under `build/.tl/` or `<film>/.tl/`, `fsync`, `os.replace`, retry as filmkit's `write_retry`: 10 attempts × 0.05 s on `PermissionError`). The temp folders are never at `build/`'s top level, so `run_arm.py`'s `copy_build()` (top level only) never copies one.

## §4 Data schemas

All JSON files are UTF-8 without BOM. Author-written files (`film.timeline.json`, `voice/lines.json`, `component.json`) reject unknown keys; tool-written files of a known `schema_version` ignore unknown keys with a note. Repeated runs must be byte-identical (BR-16), so numbers are written in one fixed way (P-1 of the PSM v1 verification): **frame-snapped times are integers of frames** (`*_f` fields, `n_frames`) and that integer is authoritative; their seconds (`t0`, `e`, `film_end_s`, `window`, `cut_moment`, `d`, `d_author`, `tail_hold`) are written as `frames / fps` with no rounding (Python's shortest round-trip `repr`, deterministic), so `abs(s · fps − frames) ≤ 1e-9` always holds and filmkit's whole-frame test (`tools/filmkit/_fk/spec.py frame_count`, tolerance 1e-6) passes for every length — `round(470/30, 6)` = 15.666667 would fail it (×30 = 470.00001). Values that are never snapped (line times, `*_raw`, `extension_s`/`by_s`, measured durations) are rounded to 6 decimals.

### 4.1 `film.timeline.json` (author-written; `film.timeline.schema.json`)

Top level: `meta` (required), `decisions` (optional, default `{}`), `assets` (optional, default `[]`), `tracks` (required). `schema_version` lives in `meta`.

**`meta`**

| Field | Type / range | Default | Notes |
|---|---|---|---|
| `schema_version` | const 1 | — | D-T16: one global version |
| `film_id` | `^[a-z0-9][a-z0-9-]{0,39}$` | — | equals the folder name under `films/` (TV-1) |
| `format.size` | `^[0-9]+x[0-9]+$`, both even, both ≥ 16 | — | same rule as filmkit `expected.size` |
| `format.fps` | integer 1–120 | — | |
| `format.duration_policy` | `fit` \| `fixed` | — | |
| `format.duration_s` | number > 0, whole frames at `fps` | required iff `fixed`, forbidden iff `fit` | PSM decision: an author writes seconds to a few decimals (15.666667 for 470 frames at 30 fps), so TV-1 accepts `abs(d·fps − round(d·fps)) ≤ 1e-3` and from then on the integer `round(d·fps)` is authoritative; every second the tools write is `frames / fps` (§4 preamble), which passes filmkit's stricter `spec.frame_count` (1e-6) |
| `lead`, `tail` | number ≥ 0 | 1.0, 2.0 (D-T10, D-T23) | `tail` = still last frame + full mute (D-T19) |
| `line_gap`, `section_gap` | number ≥ 0 | 0.45, 1.2 (D-T10) | PSM decision: per-film override of the provisional defaults; absent = `_tl/defaults.py` |

**`decisions`** — exactly these keys, each optional in a draft: `film_type`, `audience`, `energy`, `rhythm_source`, `remember_one`, `ground`, `voice`, `presentation`, `purpose`, `shown_where`, `viewer_action`. Each value is `{value, source, evidence?}` with `source` ∈ {`user`, `model`, `default`} and `evidence` a free string. Value types: `film_type` a slug of §4.3; `energy` ∈ {`calm`, `lively`, `hype`}; `rhythm_source` ∈ {`narration`, `content`} in TL-0..TL-3 (`music-bar` accepted from TL-4; before that it is `spec_invalid` with hint "music-bar anchors arrive in TL-4"); `voice` ∈ {`marketing`, `light-technical`}; `presentation` ∈ {`paged`, `continuous-stage`}; `ground` `^#[0-9a-fA-F]{6}$`; the rest non-empty strings. Required at `approve`: `film_type`, `audience`, `energy`, `rhythm_source` (D-T8, TV-18). tl never writes a decision (PSM decision closing X-13 / SEM-10: "最字面解讀" is the author's act; a missing decision only changes how table A filters, §6.4).

**`assets[]`**

| Field | Type | Notes |
|---|---|---|
| `id` | `^[a-z0-9][a-z0-9._-]{0,39}$`, unique | |
| `kind` | `capture` \| `logo` \| `font` \| `music` \| `image` \| `data` | |
| `path` | relative to `<film>/`, must start with `assets/`, forward slashes, no `..`, no two paths equal case-insensitively (TG-17) | file must exist (TV-1) |
| `sha256` | optional, 64 hex | when present must equal the file's normalized hash (TV-1); fingerprints always recompute |
| `license` | string, optional | recorded only (shown on the page) |
| `claims_ref` | optional path under `assets/` | the T05 claims source; an asset with it is a claims source (§4.1 claims) |
| `portrays` | optional `{subject_name: str}` or `{subject_logo: str}` | sole source of identity strings (BR-12) |

`duration_s` is derived, never authored: `validate --static` runs `ffprobe -v error -show_entries format=duration:stream=codec_type -of json <file>` on an asset whose extension is `.mp4`, `.mov`, `.webm` or `.mkv` and records it in `validate.json.assets[].duration_s` (TV-17).

**`tracks`** — keys `picture` (array, ≥ 1 clip), `overlay` (array), `narration` (array), `music` (`null` until TL-4; non-null → `spec_invalid` "music track arrives in TL-4"), `sfx` (array), `captions` (`null` or `{from: "narration", style: "<component ref>"}`).

**`Clip`** (picture track; array order = time order, TV-2 blocks a resolved order that differs)

| Field | Type | Required | Notes |
|---|---|---|---|
| `id` | `^[A-Z][A-Za-z0-9-]{0,15}$`, unique across picture + overlay | yes | |
| `role` | §4.3 role vocabulary | yes | |
| `at` | TimeRef (§4.2) | yes (draft may omit → blocking "missing at") | |
| `dur` | dur form (§4.2) | yes (same) | |
| `motion_intent` | array of strings | the KEY must exist (TV-1); empty array → TV-5 | |
| `freedom` | `locked` \| `guided` \| `free` | no; absent → `guided` applied in memory and listed (SEM-10) | tl never writes it into the author file; `approve` materializes it in the version copy (§4.8) |
| `device` | `locked`: `{component: "<ref>", params: {}}`; `guided`: `{family, tone?}`; `free`: absent | per freedom | `component` with absent `freedom` → blocking "write freedom: locked" |
| `transition_in` | `"cut"` \| `{component: "<ref>", dur: number > 0}` | no | absent ≡ `"cut"` for every freedom (Z-7b). For `guided`, absent also means "open: the clip author picks from the transition candidates"; `approve` lists every still-absent one as a hard cut (D-T14, Z-7c) |
| `headline`, `visual`, `data`, `layout`, `what` | string | no | `layout` under `guided` is an instruction to the clip author (TG-3) |
| `claims` | `{headline?: Claim, data?: Claim}` | no | Claim = `"<asset id>:<locator>"`, the asset must have `claims_ref` (TV-9a); the locator is the quoted text, verbatim on one line of the `claims_ref` file after removing `**` and collapsing whitespace (TV-9a source check, 2026-10-14) |
| `camera` | `{move?, pace?, goal?, method?}`, `goal`/`method` from design §7.4 | no | instruction only (TG-3) |
| `ref_seg`, `ref_what` | string | no | imitation provenance |
| `evidence` | `{"<field>": "<text>"}` | no | the shot record's `src` (design §6.1) |
| `override` | `{why, source: "user"\|"model", confirmed, date: YYYY-MM-DD}` | no | `confirmed` required non-empty when `source: user`; `model` is always ineffective (A5) |
| `declares` | `{holds?: [], blacks?: [], silences?: []}`, each `{t0, t1, why}` in clip time, `0 ≤ t0 < t1`, `why` non-empty | no | `t1 ≤ d_author` checked in TV-2 (timed) |
| `ground_exception` | `{color?, why?}` | no | missing/empty `why` is TV-8 look, not a schema error (design §8.1 TV-8 row) |
| `speed` | `{asset, start_lt ≥ 0, table: [[demo_start, demo_end, speed], ...]}` | no | TV-17 |
| `intents` | `[{kind, expect, tolerance?, moment?}]`, `kind` from design §7.5 | no | consumed by `intent` (TL-3); schema-checked from TL-0 |
| `keys` | `[{id: ^K[A-Za-z0-9-]{1,15}$ unique film-wide, at: number ≥ 0 in clip time, role: key\|breakdown, hold?: number ≥ 0, what: non-empty}]` | no | added 2026-10-19 (`docs/agent-review-kbt-design.md` §3, M1). `resolve` writes film-level `keys[]` (`id`, `clip`, `role`, `what`, `t_f`, `t`, `hold`) only when some clip declares keys, so older films resolve byte-identically; seams are derived by readers from `picture`. `at` > `d_author` → TV-2 blocking; a picture clip with no `role: key` → TV-20 look |

**`OverlayClip`** (overlay track): `id`, `role` (must be `overlay`), `at`, `dur`, `z` (integer ≥ 1), `motion_intent`, `freedom`, `device`, plus the optional text/claims/evidence/override/declares fields above; `transition_in` and `speed` forbidden (SEM-13).

**`Line`** (narration track; array order = speaking order): `id` `^L[0-9]{1,3}$` unique; `text` (non-empty; captions); `say` (optional; spoken form); `asr` (optional; expected transcript, default `say`, then `text`); `section` (a picture clip id, required); `gap_after` (optional number ≥ 0); `claim` (optional Claim — PSM decision: BR-12's "時間軸裡的宣稱文字帶出處" covers spoken claims too, so TV-9a checks narration text like `headline`).

**`SfxEvent`**: `at` (TimeRef), `sound` (string id), `gain_db` (number −60…+6), `why` (non-empty), `target` (optional clip id). Resolved in TL-0, mixed from TL-2.

`selftest.py` asserts that `model.validate_timeline(obj)` and `film.timeline.schema.json` agree on 8 valid and 14 invalid fixtures (missing `motion_intent` key, `transition_in: {family: …}` (family-only, Y-1), `fixed` without `duration_s`, `fit` with `duration_s`, odd size, unknown key, `music` non-null, override `source: user` without `confirmed`, declares without `why`, bad clip id, bad TimeRef string, `film.end` in `fit` (SEM-11; the schema expresses it with `x-tl-` keywords, the validator implements it), `rhythm_source: music-bar` before TL-4, two assets differing only by case).

### 4.2 TimeRef and `dur` grammar (`_tl/timeref.py`)

- **TimeRef**: a number ≥ 0 (film seconds), or `{anchor: A, offset?: number}` (offset default 0). `A` matches `^(line:(L[0-9]{1,3})\.(start|end)|clip:([A-Z][A-Za-z0-9-]{0,15})\.(start|end)|film\.end)$`. `film.end` is legal only under `fixed` (SEM-11). TL-4 adds `bar:N`, `beat:N`, `downbeat:N` (D-T17); before TL-4 they are `spec_invalid`.
- **`dur`** (PSM decision; the design writes "`at`、`dur` 皆 TimeRef" without saying what an anchor means for a length): one of
  - a number > 0 — the clip's length in seconds;
  - `{anchor: A, offset?}` — an **end anchor**: the clip ends at the anchor's time + offset;
  - `{lines: "La-Lb", pad_after?: number ≥ 0}` — the clip ends at `Lb.t1 + pad_after` (SEM-3; `La..Lb` must all have `section` = this clip, TV-1);
  - TL-4: `{bars: N}`.
- `transition_in.dur` is a number only (`tdur`, SEM-1).

### 4.3 Vocabularies and the film-type mapping

**Film types** (single source: the rules file's `film_types`, which `filmkit_rules_selftest.py` already holds equal to the section headings of `~/.claude/skills/motion-video/references/film-types.md`, filmkit PSM §4.5, Q-10/R-11). The timeline layer has **no vocabulary of its own**: `decisions.film_type.value`, `Component.tone.film_types`, `film_plan.json.film_type` and `render.py --film-type` all carry the same slug.

| `film-types.md` section | Slug (`decisions.film_type`, `--film-type`) | Product film (TV-9 applies) | Typical `rhythm_source` (a hint on the page, never a check) |
|---|---|---|---|
| §1a Intro ad | `intro-ad` | yes | `content` (TL-4: `music-bar`) |
| §1b Hype ad | `hype-ad` | yes | `content` (TL-4: `music-bar`) |
| §1c Product tour | `product-tour` | yes | `narration` or `content` |
| §2 Data-driven showreel | `data-showreel` | yes | `content` |
| §3 Narrated explainer | `narrated-explainer` | no, unless an asset has `claims_ref` | `narration` |
| §4 Profile / showreel reel | `profile-reel` | no, unless an asset has `claims_ref` | `content` |
| §5 Music PV / MV | `music-video` | no | `music-bar` (TL-4) |
| §0, §1 (no film type) | — | — | — |

PSM decision: "product film" (design TV-9 "產品片") = slug ∈ {`intro-ad`, `hype-ad`, `product-tour`, `data-showreel`} OR any asset declares `claims_ref`. When the rules file is absent (arm mount, TL-INV-10) the slug is checked against the pattern `^[a-z0-9-]{1,40}$` only, and `validate.json` notes "film-type vocabulary unavailable: rules file not present". Lab case `purpose` values in `tools/taxonomy.json` are a different axis and are never accepted as film types (the same exclusion filmkit makes, filmkit PSM §4.5). A new film type in the skill reaches the timeline layer through the rules file with no timeline edit.

**Roles** (PSM decision, closes design §6.1 "opening／feature／chapter-card／end-card／…"): picture `role` ∈ {`opening`, `feature`, `chapter-card`, `end-card`, `interlude`}; overlay `role` = `overlay`; table A uses `transition` for a transition component's role. Only `feature` is checked by SEM-4. Adding a role value is additive (no `schema_version` bump); renaming or removing one bumps it.

**Families, `stock_devices`, camera vocabularies**: as design §7.4. `stock_devices` values live in `params.timeline.stock_devices` (§4.10), not in code.

**Evidence tiers** (BR-7; parameter and component tiers): `unverified` < `user-viewed` = `measured` < `verified` (design §6.5 order; on the page: 未驗證／使用者看片／已量／已驗證).

### 4.4 `voice/lines.json` (author-written in TL-0; tool-written from TL-1)

```json
{"schema_version": 1,
 "lines": {"L1": {"est_dur": 3.0}, "L2": {"est_dur": 2.0}}}
```

TL-0 accepts only `est_dur` (number > 0, author-filled estimate). TL-1 (`voice --import`) and TL-2 (`voice`) add tool-written entries `{state, wav, wav_nsha, dur_s, key, transcript?}` (§8.1.3, §8.2); an entry with `est_dur` and `state` together is `spec_invalid`. The file is optional: a narrated film without it gets every line estimated by rate.

Duration source per line, first match (PSM decision; closes design §6.3 "手填或估算"):

1. inside `versions/<n>/` (approved): `voice_lock.json` → `dur_s`, `estimated: false`;
2. `voice/lines.json` entry with `state` ∈ {`checked`, `imported`} → `dur_s`, `estimated: false` (TL-1+);
3. `voice/lines.json` entry with `est_dur` → `estimated: true`, `dur_source: "est_dur"`;
4. otherwise the rate estimate → `estimated: true`, `dur_source: "rate"`: `est = max(0.8, n_han / 4.0 + n_other / 12.0)` rounded to 0.01 s, where `n_han` counts characters of Unicode script Han, Hiragana, Katakana or Bopomofo in `say` (else `text`) and `n_other` counts ASCII letters and digits. Constants live in `_tl/defaults.py` (provisional, model; only for the dashed preview).

`resolve` never writes `voice/`. `approve` refuses any `estimated: true` line (TV-18, design §6.3 last paragraph).

### 4.5 `build/timeline.resolved.json` (tool-written; `resolve` is the sole writer)

```json
{
  "schema_version": 1, "generator": "tl", "film_id": "dit-promo",
  "inputs": {"timeline_nsha": "…", "lines_nsha": "…|null", "clips_nsha": "…", "components_nsha": "…", "runtime_hash": "…"},
  "format": {"size": "1920x1080", "fps": 30, "duration_policy": "fit"},
  "film_end_s": 15.7, "n_frames": 471,
  "lead": 1.0, "tail": 2.0, "line_gap": 0.45, "section_gap": 1.2,
  "ground_preroll": null,
  "tail_hold": {"t0": 13.7, "t1": 15.7},
  "lines": [{"id": "L1", "section": "S1", "t0": 1.0, "t1": 4.0, "dur_s": 3.0, "dur_source": "est_dur", "estimated": true}],
  "picture": [{"id": "S2", "role": "feature", "freedom": "guided", "freedom_defaulted": false,
               "t0_raw": 5.05, "t0_f": 152, "t0": 5.066666666666666, "e_raw": 12.9, "e_author_f": 387, "e_f": 387, "e_author": 12.9, "e": 12.9,
               "d_author": 7.833333333333333, "d": 7.833333333333333, "extension_s": 0.0,
               "transition": {"kind": "component", "component": "transition.dim-through-ground@1", "tdur": 0.3, "tdur_frames": 9},
               "window": [5.066666666666666, 5.366666666666666], "cut_moment": 5.216666666666667, "first_line": "L2",
               "anchors": {"at": "line:L2.start-0.15", "dur": "lines:L2-L4+0.3"}}],
  "overlay": [{"id": "O1", "z": 1, "t0": 0.0, "e": 13.7, "d": 13.7}],
  "sfx": [{"index": 0, "t": 4.3, "sound": "tick", "gain_db": -12, "why": "…"}],
  "extensions": [],
  "defaults_applied": ["S2.freedom=guided"],
  "notes": []
}
```

- The example is illustrative (it shows the §10.2 base film, which has no gap fill); exact seconds in it are `frames / 30` as Python prints them, and the builder's fixture files are generated, not copied from here.
- `t0`/`e` are frame-snapped (§6.7 step 6); `t0_raw`/`e_raw` are the pre-snap values (SG-1, TG-7); `e_author` is the snapped end before gap filling; `e` after (D-T22). An extension row is `{clip, by_s, to_f, to}` with `to` = the next picture clip's `t0`. `d_author = (e_author_f − t0_f) / fps`, `d = (e_f − t0_f) / fps` — every derived second is computed from integer frames, never by subtracting two float seconds (Z-4: TV-4b and TV-6 read `d_author`; `draw` receives `d`).
- `transition.kind` ∈ {`component`, `cut`, `open`} (`open` = guided with no `transition_in`; resolved as a cut, `tdur` 0).
- `window` is `[t0_f, t0_f + tdur_frames) / fps` when `tdur > 0`, else null; `cut_moment = (t0_f + tdur_frames / 2) / fps` (SEM-4).
- Line times are never snapped (TG-1/TG-7).

### 4.6 `build/validate.json` (tool-written; `validate` is the sole writer)

```json
{"schema_version": 1, "generator": "tl", "film_id": "…",
 "stage": "static|timed",
 "inputs": {"timeline_nsha": "…", "clips_nsha": "…", "lines_nsha": "…", "components_nsha": "…", "rules_sha": "…|null", "runtime_hash": "…", "resolved_nsha": "…|null"},
 "env": {"python": "3.12.7", "ffprobe": "8.1|null"},
 "static": {"rows": [], "summary": {"blocking": 0, "look": 0, "info": 0, "undetermined": 0}},
 "timed": {"rows": [], "summary": {}} ,
 "assets": [{"id": "…", "nsha": "…", "duration_s": null}],
 "uses": {"S2": ["ui-demo.cursor-click@1"]},
 "defaults_applied": [], "decisions_unset": ["energy"],
 "freedom_share": {"locked_s": 0.0, "guided_s": 0.0, "free_s": 0.0},
 "notes": []}
```

A row: `{"id": "TV-2#S2", "check": "TV-2", "stage": "timed", "bucket": "blocking|look|info|undetermined", "where": "S2|L3|film|asset:<id>", "measured": "…", "expected": "…", "basis": "SEM-4 / T08", "provisional": bool, "reason": "…|null", "message_key": "…"}`. Every `blocking`/`look` row has `measured` and `basis`; every `undetermined` row has `reason` (gate rule; selftest scan like filmkit FK-INV-5). `validate --static` writes `stage: static` and an empty `timed` block; `validate --timed` keeps the static block of the current static run and fills `timed`.

### 4.7 `state.json` (tool-written; `state.py` is the sole writer)

```json
{"schema_version": 1, "generator": "tl", "film_id": "dit-promo",
 "draft": {"n": 2, "parent": 1, "state": "DRAFT|VALID|ABANDONED", "inputs": {"timeline_nsha": "…", "clips_nsha": "…", "lines_nsha": "…", "components_nsha": "…"}, "history": [{"state": "VALID", "at": "…", "note": "…"}]},
 "versions": [{"n": 1, "parent": null, "state": "APPROVED", "approved_by": "user", "approval_nsha": "…", "history": []}]}
```

- The **draft** is the working folder's version-in-progress. `draft` is `null` when the working inputs equal the latest version's copies (just after `approve`); the first command that sees different inputs creates `{n: last+1, parent: last, state: DRAFT}` (design §6.4 "任何修改 → 新版本 n+1 的 DRAFT").
- Transitions implemented in TL-0 (design §6.4): `DRAFT → VALID` (static and timed both current with 0 blocking); `VALID → DRAFT` (inputs changed, or a later validate fails); `VALID → APPROVED` (as version n; draft → null); `DRAFT|VALID → ABANDONED` and `APPROVED → ABANDONED` (`tl.py mark --abandoned`). Refusals: `approve` on `DRAFT` → `not_current` (hint names the step); `approve` with TV-18 failures → `missing_required`, state stays `VALID`; `--by model` with an override → `missing_required` (TV-18). TL-1 adds `COMPILED`, TL-3 `RENDERED`/`REVIEWED`/`DELIVERED` and `mark --delivered|--watched`.
- PSM decision (design §6.4 lists "放棄 → ABANDONED" but no command): `tl.py mark <film> (--abandoned [--version n]) --note "<words>"`; no `--version` = the draft. Terminal states never change (`illegal_transition`).
- Version integrity (TL-INV-6): every command except `at` first runs `state.verify_versions(film)`: for each version listed, recompute every fingerprinted file of `versions/<n>/` against `approval.json`, and `approval.json`'s own nsha against `state.json.versions[].approval_nsha`. Any difference → `fingerprint_mismatch` naming the file; hint "restore versions/<n>/ from git, or mark the version abandoned". This is tamper evidence against accidents, not an adversary (both files are writable by the same user).
- Crash recovery on start: a `versions/<n>.tmp/` folder → deleted with a note; a `versions/<n>/` folder not in `state.json` whose `approval.json` verifies → added as `APPROVED` with a note "approval recovered after interruption"; one that does not verify → `fingerprint_mismatch`.

### 4.8 `versions/<n>/` and `approval.json` (written by `approve` only; read-only afterwards)

```
versions/<n>/
  timeline.json             normalized author timeline + materialized defaults (freedom)
  timeline.resolved.json    copy of the resolved file approve validated
  clips/<id>.js             copies of every guided/free clip program
  components/<family>/<name>.v<version>/   copies of every used component folder, `requires` closure included (Z-9)
  voice_lock.json, voice/   TL-1+ (narrated films)
  approval.json
```

```json
{"schema_version": 1, "generator": "tl", "film_id": "…", "n": 1, "parent": null,
 "approved_by": "user|model", "note": "<the user's words>|null",
 "questions": {"path": "build/questions.md", "nsha": "…"} ,
 "approved_at": "2026-10-11T10:00:00+08:00",
 "fingerprint": {
   "timeline": {"path": "timeline.json", "nsha": "…"},
   "resolved": {"path": "timeline.resolved.json", "nsha": "…"},
   "clips": [{"id": "S2", "path": "clips/S2.js", "nsha": "…"}],
   "components": [{"ref": "chapter-card.verb@1", "path": "components/chapter-card/verb.v1", "dir_nsha": "…"}],
   "assets": [{"id": "dit-readme", "path": "assets/README.md", "nsha": "…"}],
   "voice": [],
   "runtime_hash": "…"},
 "product_film": true,
 "pending_confirmation": [{"clip": "S4", "component": "…", "why": "…", "confirmed": "…"}],
 "hard_cuts": ["C1", "S3"],
 "undetermined": ["TV-6", "TV-9b"],
 "defaults_applied": ["S2.freedom=guided"]}
```

- Fingerprint scope = design `VersionFingerprint` + TV-16 (X-11a unified): timeline, every clip program copy, every used component (`id@version` + folder hash), every asset (hash only; assets are not copied, design §3.1), every narration audio copy, the runtime hash. The shared rules file is **not** in it (D-T24); its hash goes to `MANIFEST.json` (TL-1).
- `undetermined` lists the rows that could not run at approval time (Z-8): in TL-0 always `TV-6` and `TV-9b` (no clip execution). `compile` (TL-1) refuses a version with `product_film: true` whose `undetermined` contains a row that is blocking at approve (`TV-9b`) → `not_approved`, hint "re-validate and approve with TL-1's validate --timed".
- `pending_confirmation` = every A4 pass (user override); `hard_cuts` = every picture clip whose `transition.kind` ∈ {`cut`, `open`} after the first clip, with `open` ones marked (Z-7c). The five-line output's first line names them (§5.2).
- Write sequence (TG-16): build everything in `versions/<n>.tmp/`, write `approval.json` last, clear write permission on every file (`os.chmod(p, stat.S_IREAD)`), `os.replace` the folder to `versions/<n>/`, then update `state.json` atomically. Recovery: §4.7.

### 4.9 Components: `component.json`, `components/index.json`, `components/evidence.json`

`component.json` (author-written; one per `components/<family>/<name>.v<version>/`):

```json
{"schema_version": 1,
 "id": "chapter-card.verb", "version": 1, "family": "chapter-card",
 "card": "T04", "card_tier": "unverified",
 "tone": {"energy": ["calm", "lively"], "film_types": "any"},
 "when": {"roles": ["chapter-card"], "rhythm_sources": "any"},
 "conflicts": ["chapter-card.flash"],
 "params": {"verb": {"type": "string", "evidence": "user-viewed"},
            "hold_s": {"type": "number", "default": 0.9, "min": 0.5, "max": 1.5, "evidence": "user-viewed"}},
 "emits": ["card-in", "card-out"],
 "intents": [],
 "label_type": true, "hold_range": [0.5, 1.5],
 "stock": false,
 "requires": [],
 "license": "own", "provenance": "self-written from T04/C17",
 "impl": "component.js"}
```

- `id` = `<family>.<name>`; a reference is `<id>@<version>` (`^[a-z0-9-]+\.[a-z0-9-]+@[0-9]+$`). Folder name `<name>.v<version>` (PSM decision: `@` avoided in folder names, TG-17).
- `params.<name>.type` ∈ {`number`, `integer`, `string`, `boolean`, `asset`, `line`, `color`}; `asset`/`line` values must name an existing asset/line id (TV-4a); `min`/`max`/`enum` optional; `evidence` required (BR-7). Optional `source: "clip_dur"` (type `number` only) marks a param whose value is the clip's own length: the runtime passes `d`, TV-4b checks `d_author` against `min`/`max` (Z-4; design §7 TV-4 "例：章節卡 `dur`").
- `label_type: true` requires `hold_range: [a, b]`, `0 < a ≤ b` (D-T15).
- `conflicts` lists component ids (any version).
- **Evidence state is NOT in `component.json`** (PSM decision; a state change would alter the folder hash and break every approved version's fingerprint). It lives in `components/evidence.json`: `{"schema_version": 1, "entries": {"chapter-card.verb@1": {"state": "draft|candidate|in-use|verified", "watched": false, "measured": false, "log": [{"at": "…", "event": "…", "film": "…"}]}}}`, written only by `tl.py index` (selftest result → `candidate`) and later by `compile`/`intent` (TL-1/TL-3). A component without an entry is `draft`.
- `components/index.json` (generated by `tl.py index`): `{"schema_version": 1, "generator": "tl", "components": [<component.json fields> + {"ref", "path", "dir_nsha", "state", "watched", "measured", "claim_tier"}]}`; `claim_tier = min(component tier, card_tier)` per design §6.5 (TL-INV-7). `INDEX.md` is its human table (Traditional Chinese headings).
- Table A/B (design §6.8) read only `components/index.json`; `--components DIR` (§5.1) points a run at another library (selftest fixtures; TL-5 arms).
- Only `state` ∈ {`candidate`, `in-use`, `verified`} components are eligible as guided candidates (A7) or as `locked` components; a `draft` component referenced by a `locked` clip → TV-3 blocking "component not selectable yet (draft)".

### 4.10 Shared rules file: what the timeline layer reads and adds

Read (all optional; absent file or key → the dependent rows are `undetermined` with `reason: "rules file not present"` or `"rules key <k> absent"`, TL-INV-10):

| Key | Used by | Milestone |
|---|---|---|
| `film_types` | TV-1 film-type vocabulary | TL-0 |
| `rules[id == "end_hold"].range_s` | TV-7 (same key as filmkit FK-R-16, D-T18) | TL-0 |
| `params.timeline.free_share_max` | TV-10 | TL-0 |
| `params.timeline.stock_devices` | TV-5 / table B2 | TL-0 |
| `params.timeline.read_time` `{cjk_cps, other_cps, base_s, headline_page_min_s}` | TV-6 | TL-1 |
| `params.timeline.mix` `{peak_cap_dbfs, narration_over_music_db}` | `Mix` (BR-15); fallback values in `_tl/defaults.py` when absent (design §6.9) | TL-1 (`peak_cap_dbfs`), TL-2 (`narration_over_music_db`) |

TL-0 adds, keeping every other byte of the file:

```json
"params": {
  "timeline": {
    "free_share_max": 0.30,
    "stock_devices": ["particle-burst", "tunnel", "floating-card-pile", "glitch", "big-text-as-design", "fake-hud"],
    "basis": {"free_share_max": "D-T9 暫定 30%（設計 §5.2）", "stock_devices": "production-order E；使用者可增減"}
  }
}
```

- filmkit never reads `params` (filmkit PSM §4.5; code: `judge.py` evaluates only `owner == "filmkit"` rules; `filmkit_rules_selftest.py` checks `set(rules) == TOP_KEYS` and scans the kit for rule ids/sentences/numbers from `rules`/`targets` only, `rule_tokens()`), so adding `params.timeline` changes no filmkit behaviour. INV-7 still applies: after the edit run `python -X utf8 tools/filmkit/selftest.py` and `python -X utf8 tools/filmkit_rules_selftest.py`.
- Single source (BR-14): `selftest.py` fails if any file under `tools/timeline/_tl/` contains a `params.timeline` key assigned a literal number (regex `<key>["']?\s*[:=]\s*<number>`) or a `stock_devices` value as a string literal; `_tl/defaults.py` mix fallbacks are the design's named exception (§6.9) and are exempt by path.
- The ±0.15 s of SEM-4 is a semantic constant of the format (T08, TV-2 blocking-fixed), not a design rule; it lives in `_tl/defaults.py` as `CUT_TOLERANCE_S` so TV-2 still runs in an arm without the rules file (PSM decision).

### 4.11 Candidate files (`validate --static`)

`build/clips/<id>.candidates.json` (picture device candidates, A7) and `build/clips/<id>.transition.candidates.json` (transition candidates, Z-7a): `{"schema_version": 1, "clip": "S2", "kind": "device|transition", "decided_by": "A7", "decision_inputs": {"energy": "calm", "film_type": "product-tour", "rhythm_source": "narration", "role": "feature", "decisions_unset": []}, "candidates": [{"ref": "…", "family": "…", "label_type": false, "claim_tier": "…"}], "note": "…|null"}`. Written for every `guided` clip (empty list + note when none qualify). These are the only lists a clip author may draw from (SEM-6, r10).

### 4.12 Normalized hashing, `MANIFEST.txt`, library and runtime hash (`_tl/nhash.py`)

- **File nsha**: text files (extension in `.json .js .html .css .svg .md .txt .srt .csv .tmpl`) → decode UTF-8 (strip a BOM), CRLF and lone CR → LF; `.json` additionally parsed and re-dumped with `json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))`; then sha256 of the UTF-8 bytes. Any other file → sha256 of raw bytes. A text file that is not valid UTF-8 → `spec_invalid` naming the file (TG-8).
- **Folder hash**: sha256 over lines `relpath\0nsha\n`, `relpath` relative to the folder with `/`, lines sorted by their UTF-8 bytes, `__pycache__/` and `*.pyc` skipped (same line format as filmkit `inputs_sha256`, filmkit PSM §4.2).
- `clips_nsha` = folder hash of `clips/` (`*.js` only); `components_nsha` = nsha of the `components/index.json` in use; `lines_nsha` = nsha of `voice/lines.json` or null; `timeline_nsha` = nsha of `film.timeline.json`.
- `MANIFEST.txt`: one path per line relative to `tools/timeline/`, `/`, sorted, lists itself, no comments (filmkit PSM §4.7 format). **Library hash** (`timeline_lib_hash`, TL-5) = filmkit's kit-hash algorithm over every listed file. **Runtime hash** (TL-INV-12, X-11b) = the same algorithm over the listed files matching `tl.py`, `film.timeline.schema.json`, `_tl/**`, `runtime/**` — i.e. everything that changes what `compile` would produce; `selftest.py`, `README.md` and `components/**` are excluded (components are fingerprinted per use).
- Two paths in one hashed set equal case-insensitively → `spec_invalid` (TG-8 path case).

## §5 Interfaces and CLI

### 5.1 Sub-commands and flags (authoritative; `--help` is compared to this table by a selftest control)

Common flags on every sub-command: `--rules F` (default `<tools>/filmkit_rules.json` resolved from `tl.py`'s own folder: `Path(__file__).resolve().parents[1] / "filmkit_rules.json"`; a missing file is not an error), `--components DIR` (default `tools/timeline/components`), `--json`. `<film>` is the film folder path.

| Command | Milestone | Shape |
|---|---|---|
| `validate <film> --static` | TL-0 | static rows; writes `validate.json`, candidate files |
| `validate <film> --timed` | TL-0 (TL-1 adds TV-6/9b execution) | timed rows on the current resolved file |
| `resolve <film>` | TL-0 | writes `timeline.resolved.json` |
| `view <film>` | TL-0 | writes `timeline.html` |
| `approve <film> --by user --note "<words>"` \| `--by model --questions build/questions.md` | TL-0 | writes `versions/<n>/`, `state.json` |
| `at <film> <seconds> [--version n]` | TL-0 | read-only query (BR-11) |
| `mark <film> --abandoned [--version n] --note "<words>"` | TL-0 (TL-3 adds `--delivered`, `--watched`) | state event |
| `index [--check]` | TL-0 | rebuilds `components/INDEX.md`, `index.json` (+ evidence entries for selftest results); `--check` exits 1 when stale |
| `voice <film> --import <dir>` | TL-1 | §8.1.3 |
| `compile <film> [--version n] [--discard-edits] [--rebase]` | TL-1 | §8.1 |
| `voice <film>` | TL-2 (SKELETON) | §8.2 |
| `intent <film>`, `revise <film>` | TL-3 (SKELETON) | §8.3 |
| `music <film>` | TL-4 (SKELETON) | §8.4 |

A sub-command of a later milestone is absent from `--help` until built (no stubs).

### 5.2 Five stdout lines, `--json`, exit codes

Same shape as filmkit (`tools/filmkit/_fk/summary.py`), so callers parse one format:

```
Done: <command> <film> — <one-line result>            | Failed: <kind> — <message>
Steps: <step> -> <step> ...                            (failures: "... (failed); nothing written" when true)
Check: <b> blocking, <l> need a look, <u> undetermined — <path of validate.json or approval.json>   | Check: not run
Look: <path of timeline.html> (pictures not judged by this tool) | Look: not needed
Notes: <items joined by "; "> | none
```

- Line 1 of `approve` (design §5.1, Z-7c, Z-8): `Done: approve <film> — version <n>; pending your confirmation: <k> override(s) [<clip>…]; hard cuts: <clip>…; open transitions now cut: <clip>…; not checked yet: TV-6, TV-9b`. Empty parts are omitted.
- Every output of every command carries "format and timing checked; pictures not judged" in `Notes:` (design §5.2) and never contains a TL-INV-8 word: zh {好看, 漂亮, 完美, 很棒, 完成, 成功了}, en {looks good, beautiful, perfect, great job, polished, finished film}. "Done:" is the command status word (as in filmkit) and is allowed.
- `--json`: one JSON document: `{"command", "status": "done|failed", "kind", "message", "hint", "exit_code", "outputs": {…paths…}, "summary": {…}}` plus the command's main file content under `"result"`.
- Exit codes (filmkit `_fk/common.py` values): 0 done with no blocking row; 1 refused or failed (any `kind`); 2 done with ≥ 1 blocking row (`validate`); 3 a check started but did not finish (an exception inside a row evaluator after other rows ran: rows `undetermined` with `reason: "evaluator error: <last line>"`). `undetermined` rows for missing information never set exit 3.

### 5.3 Failure kinds (`_tl/common.py`; design §6.10 completed)

| `kind` | When | Hint (shape) |
|---|---|---|
| `spec_invalid` | schema, grammar, unknown key, anchor parse, missing file, non-UTF-8 text, argparse error | names the field/path |
| `not_current` | a previous step's product is missing or stale (§5.4); `approve` on a non-`VALID` draft; `intent` before a render (TL-3) | names the step to run |
| `not_approved` | `compile` without an `APPROVED` version, or a product-film version with an undetermined approve-blocking row (Z-8) | "run approve" / "re-validate" |
| `missing_required` | TV-18 | lists every missing item |
| `fingerprint_mismatch` | version integrity (§4.7), TV-16 | names the file |
| `edited_output` | TV-11 (TL-1) | "edit film.timeline.json or the clip program, not build/" |
| `voice_mismatch` | TV-12 (TL-1/TL-2) | per line: heard text |
| `env` | ffprobe / Chromium / TTS / ASR missing | the missing program and how to check it |
| `busy` | another tl process holds `<film>/.tl.lock` | "another tl command runs on this film" |
| `illegal_transition` | a state event the table forbids (terminal state, unknown version) — PSM decision, design §6.4's "工具擋" cases not covered by the kinds above | names state and event |
| `instrument_unavailable` | `intent` (TL-3) | instrument name |
| `internal` | anything else | last line of the exception |

### 5.4 Currency ("does the previous step's product match the current inputs?") — `_tl/currency.py`

| Command | Requires current | Compared fields |
|---|---|---|
| `validate --static` | — | — |
| `resolve` | static `validate.json` with 0 static blocking | `timeline_nsha`, `clips_nsha`, `components_nsha`, `rules_sha`, `runtime_hash` |
| `validate --timed` | static `validate.json` (as above) and `timeline.resolved.json` | resolved `inputs` = current inputs (incl. `lines_nsha`) |
| `view` | `timeline.resolved.json` and a timed `validate.json` (any result, so the author can see a failing timeline) | as above |
| `approve` | draft `VALID` (static + timed current, 0 blocking) | all of the above |
| `at` | the resolved file it reads (current draft or `versions/<n>/`) | none: answers from the file and prints in `Notes:` whether it is current |

A stale or missing product → `not_current` with `hint: "run tl.py <step> <film>"`; tl never runs a missing step itself (design §4). `rules_sha` takes part only in validate currency (rows depend on it), never in fingerprints (D-T24).

### 5.5 Lock (TG-18)

Every command that writes (`validate`, `resolve`, `view`, `approve`, `mark`, later `voice`, `compile`, `intent`, `revise`) holds `FilmLock(<film>)` (byte 0 of `<film>/.tl.lock`, retry 2.0 s every 0.05 s) for its whole run; `at` takes none. Not acquired → `busy`, nothing written. `tl.py index` locks `components/.tl.lock`.

## §6 Module contracts (signatures are binding; bodies are the builder's)

### 6.1 `nhash`

```python
def file_nsha(path: Path) -> str                       # §4.12; raises SpecInvalid on non-UTF-8 text
def folder_nsha(folder: Path, pattern: str = "**/*") -> str
def json_nsha(obj: dict) -> str                        # canonical dump, for in-memory objects
def library_hash(lib_dir: Path) -> str                 # MANIFEST-listed files
def runtime_hash(lib_dir: Path) -> str                 # MANIFEST-listed runtime subset (§4.12)
```

### 6.2 `model`, `timeref`

```python
def load_timeline(film: Path) -> tuple[dict, list[Row]]   # parse + validate (§4.1); rows are TV-1 static rows
def validate_timeline(obj: dict, *, rules: Rules | None) -> list[Row]
def parse_timeref(v) -> TimeRef                            # number | Anchor(kind, ref, edge, offset)
def parse_dur(v) -> Dur                                    # Length(s) | EndAnchor(TimeRef) | Lines(a, b, pad)
```

### 6.3 `rules`

```python
@dataclass(frozen=True)
class Rules:
    path: Path | None; sha: str | None
    film_types: list[str] | None
    end_hold_range: tuple[float, float] | None
    timeline: dict                        # params.timeline or {}
def load_rules(path: Path) -> Rules       # absent file -> Rules(path=None, sha=None, None, None, {})
```

A present but unparsable rules file → `spec_invalid` (an author error, unlike absence).

### 6.4 `components`, `select` (design §6.8)

```python
def load_index(components_dir: Path) -> Index
def build_index(components_dir: Path) -> Index             # tl.py index; validates every component.json
def table_a(clip: ClipView, decisions: Decisions, index: Index, locked_components: set[str]) -> ADecision
def transition_table_a(clip: ClipView, decisions: Decisions, index: Index, locked_components: set[str]) -> ADecision
def table_b(clip: ClipView, uses: list[str], candidates: list[str], rules: Rules) -> list[Row]
```

Table A, top-down, first match (design §6.8 v4.3 order; A3 continues into A4–A6, X-15b):

| # | Condition | Result |
|---|---|---|
| A1 | `freedom: free` | no component filter; any component the program uses must be `tone`-compatible (A4/A5 judgement on `uses`) |
| A2 | `locked`, `device.component` not in the index (or `draft`) | blocking "component not found", lists same-family components |
| A3 | `energy` or `film_type` unset | `locked`: component `tone` not `any` on the missing axis → blocking "decide energy/film_type first"; `any` → continue at A4 with that axis treated compatible, `when` still judged. `guided`: A7 with "only `any` on the missing axis". Either way `decisions_unset` is recorded (SEM-10) |
| A4 | `locked`, incompatible, `override.source == "user"` and `confirmed` non-empty | pass, add to `pending_confirmation`; under `approve --by model` → blocking (TV-18) |
| A5 | `locked`, incompatible, no effective override (incl. `source: model`) | blocking (TV-3) |
| A6 | `locked`, compatible | pass; parameters → TV-4a (static), TV-4b (timed) |
| A7 | `guided` | candidates = family match ∧ `tone.energy` ∋ energy (or `any`) ∧ `tone.film_types` ∋ film_type (or `any`) ∧ `when.roles` ∋ role ∧ `when.rhythm_sources` ∋ rhythm_source ∧ no `conflicts` with any **locked** clip's component ∧ state selectable; written to the candidate file; empty → info "no qualifying component; clip written from scratch" |

Compatibility: `tone.energy` is a list or `any`; `device.tone` (guided) narrows `energy` only (design §7.4). Transitions (X-2): `transition_table_a` runs the same table with `role = transition`, `family = transition`, the owning clip's `freedom`; a `locked` or `free` clip's `transition_in.component` goes A2–A6 (A1 for free = tone only); a `guided` clip's written component must be in its transition candidate file (TV-15); a guided clip with no `transition_in` → info "open transition" (listed at approve).

### 6.5 `uses` extractor (`_tl/uses.py`; SEM-6, TV-15)

Clip programs reach components only through the runtime call `TL.component("<ref>")` with a single string-literal argument (§8.1.1). Extraction (stdlib, no JS engine):

1. Strip comments with a small state machine that tracks `'…'`, `"…"`, `` `…` `` and regex-literal-free code (a `/` after `(`, `,`, `=`, `:`, `[`, `!`, `&`, `|`, `?`, `{`, `}`, `;` or line start begins a regex literal and is skipped to its closing `/`).
2. In the comment-free text, every occurrence of the token `TL.component` must be followed (after optional whitespace) by `(`, then a `'…'` or `"…"` literal without escapes, then `)`. Each match yields one ref.
3. Any other occurrence (`TL.component` not called, called with a template literal, a variable, concatenation, or bracket access `TL["component"]`) → TV-15 blocking "component reference not statically resolvable at <line>:<col>".
4. `uses` = sorted unique refs. The same function runs in `validate --static` and (TL-1) `compile` (SEM-6).

Controls (§10.2): literal call; call inside a comment (ignored); call inside a string (ignored); template literal (blocking); alias `const c = TL.component` (blocking); bracket access (blocking).

### 6.6 `validate_static`

```python
def run_static(film: Path, rules: Rules, index: Index) -> ValidateResult
```

Order: schema (TV-1) → if schema has blocking rows, stop and write them (later rows would misread the file) → asset existence/hash/ffprobe → `uses` extraction → table A for every clip and transition (TV-3) → TV-4a → TV-5 → TV-8 → TV-9a (look) → TV-13 (TL-1) → TV-15 → TV-17 → candidate files. Rows per §7.

### 6.7 `resolve` (design §6.3; Y-2, Z-4)

```python
def resolve(film: Path, timeline: dict, lines_src: LineDurations, *, order_seed: int = 0) -> Resolved
```

1. **Fixed quantities**: `fps`, `lead`, `tail`, `line_gap`, `section_gap`, `duration_s` (fixed).
2. **Narration**: lines in array order. TV-1 (static) has already required that lines are grouped by `section` and that the sections appear in picture-array order. `t0(L_first) = lead`; for each next line: `gap = section_gap` if its `section` differs from the previous line's (the previous `gap_after` is ignored with a note), else `prev.gap_after` if set, else `line_gap`; `t0 = prev.t1 + gap`; `t1 = t0 + dur` (§4.4 source order).
3. **Clips and overlays**: build the anchor graph — nodes `clip:<id>.start`, `clip:<id>.end` for picture and overlay clips; edges from every anchor a node's `at` or `dur` reads; lines and `film.end` (fixed) are constants. Kahn's algorithm; `order_seed` permutes the initial queue (TL-INV-2 control: two seeds → identical output). A cycle → TV-1 blocking listing the cycle's nodes in order (the static phase detects it from the parsed refs without any times). `start = value(at)`; `end` = `start + n` (number), `value(anchor) + offset` (end anchor), or `Lb.t1 + pad_after` (lines). All anchors read **pre-extension, pre-snap** values (step 7 runs last, Y-2).
4. **sfx**: each `at` evaluated (may read clip or line anchors).
5. **Snap** (to integer frames): `snapf(t) = floor(t·fps + 0.5 + 1e-9)` for every clip start/end → `t0_f`, `e_author_f` (PSM decision: half-up with an epsilon, so 5.05 s at 30 fps — `151.49999999999997` in binary — snaps to frame 152 on every machine; design §6.3 "round" fixed to one tie rule). `tdur_frames = floor(tdur·fps + 0.5 + 1e-9)`; `tdur > 0` with `tdur_frames == 0` → TV-2 blocking "transition shorter than one frame". Seconds are derived per §4 (`frames / fps`). Lines are not snapped.
6. **Film length** (frames): `last_f = max(e_author_f over picture)`. `fit`: `n_frames = last_f + snapf(tail)`. `fixed`: `n_frames = round(duration_s · fps)` (whole by TV-1); `last_f > n_frames` → TV-19 blocking. `film_end_s = n_frames / fps`. `tail_hold = [last_f, n_frames]` (frames; seconds derived) when `n_frames > last_f`, else null (D-T19).
7. **Gap fill** (D-T22): for consecutive picture clips `k−1, k` (array order): if `e_f(k−1) < t0_f(k)`: `e_f(k−1) := t0_f(k)`, record `{clip, by_s, to_f, to}` in `extensions` (`by_s` = frame difference / fps, rounded to 6 decimals). Overlays are never extended (SEM-13). A first clip with `t0_f > 0` → `ground_preroll = [0, t0_f]`. Comparisons between snapped quantities are integer comparisons; comparisons that involve unsnapped values (SEM-4, TV-14, TV-19 lines) use a 1e-9 slack.
8. Write `timeline.resolved.json` (§4.5).

### 6.8 `validate_timed`

```python
def run_timed(film: Path, resolved: Resolved, timeline: dict, rules: Rules, *, execute_clips: bool) -> ValidateResult
```

`execute_clips` is False in TL-0 (TV-6, TV-9b rows are `undetermined`, `reason: "clip programs are not executed before TL-1"`). Rows per §7: TV-2, TV-4b, TV-6, TV-7, TV-9b, TV-10, TV-12 (TL-1), TV-14, TV-19.

### 6.9 `state`

```python
def load_state(film: Path) -> State
def current_inputs(film: Path, rules: Rules, index: Index) -> dict
def verify_versions(film: Path, state: State) -> None          # raises FingerprintMismatch
def recover(film: Path, state: State) -> list[str]             # notes; §4.7 crash recovery
def transition(state: State, event: str, **info) -> State       # raises IllegalTransition / NotCurrent
def save_state(film: Path, state: State) -> None                # atomic
```

### 6.10 `approve`

```python
def approve(film: Path, *, by: str, note: str | None, questions: Path | None, rules: Rules, index: Index) -> ApproveResult
```

Sequence: lock → `recover` → `verify_versions` → currency (§5.4; draft must be `VALID`) → TV-18 (§7) → collect copies (timeline normalized + materialized defaults; every guided/free clip program; used components + `requires` closure; resolved) → write per §4.8 → `state.transition(…, "approve")` → five lines with the §5.2 line 1.

`--by model` requires `--questions F` naming an existing non-empty file under `<film>/build/`; its nsha goes into `approval.json.questions`. `--by user` requires a non-empty `--note`.

### 6.11 `view` (`build/timeline.html`; design §5.1)

```python
def render_view(film: Path, resolved: Resolved, validate: dict, state: State, timeline: dict) -> str   # returns HTML text
```

- One self-contained file: inline CSS, no script required to read it (a small inline script may add hover highlighting; the page reads fully without it), no external URL, no font download (system serif stack). `<html lang="zh-Hant" data-page-class="dashboard">` (page-fill-gate class registry, `~/.claude/tools/page-fill-gate/page_classes.json`). Light theme (`prefers-color-scheme: dark` adjusts colours; content identical).
- Top band: film id, draft/version state, "格式與時機已檢查，畫面未判斷" (TL-INV-8), the approve-time list (pending confirmations, hard cuts, open transitions, not-yet-checked rows) and every blocking/look row with its clip id.
- Decision cards: each decision's value and its source as 你說的／模型定的／預設; unset required decisions marked 未定.
- Tracks (one shared time axis, positions as percentages of `film_end_s`): picture lane (blocks with id, seconds, role, freedom, device/family, transition marker and window, extension hatch, tail-hold region, ground pre-roll), one overlay lane per `z`, narration lane (lines; `estimated` lines dashed with 估算 label), sfx points, caption note.
- Clip table below the lanes (readable at narrow widths): id, role, `t0`–`e` (and `d_author` when extended), anchors as written, freedom (with 預設 when defaulted), device, `motion_intent` lines, fixed fields under `guided` (`transition_in`, `layout`, `camera.*`: 已指定／放開), override status, claims, candidates count.
- No thumbnails or intent results before TL-3 (the slots say 出片後才有).
- Generated only; never hand-edited (TL-INV-9).

### 6.12 `at` (BR-11)

```python
def at(resolved: Resolved, t: float) -> AtAnswer   # {picture: [ids], in_transition: bool, overlays: [ids], line: id|None, lt: {id: seconds}}
```

`t` in a transition window → both clip ids and `in_transition: true`; `t` in `tail_hold` → the last clip with `lt = d` and "tail hold"; `t` in `ground_preroll` → no clip, "ground"; `t` outside `[0, film_end)` → `spec_invalid`.

## §7 Check rows: build detail

Stage `static` = `validate --static`; `timed` = `validate --timed`; `approve` = inside `approve`; `compile` = TL-1. Severity "fixed" rows are invariant-backed; "provisional" rows are D-T9's, ruled by the user after the first DIT film. Every row cites its `basis`.

| ID | Stage | Milestone | Determinable mechanics (what the code checks) | Severity |
|---|---|---|---|---|
| TV-1 | static | TL-0 | §4.1 schema incl. `motion_intent` key present, unique ids, `film_id` = folder name, TimeRef grammar, anchor targets exist, anchor graph acyclic (cycle listed), `film.end` only under `fixed`, numeric `tdur ≤` numeric `dur` when both are numbers (else TV-2), SEM-3 lines belong to the clip, narration grouped by section in picture order, asset files exist and match a given `sha256`, film type in `film_types` (or note when the rules file is absent), `fixed` duration whole frames, missing `at`/`dur` named (X-13) | blocking (fixed) |
| TV-2 | timed | TL-0 | resolved picture order = array order; every `d_author > 0`; `0 < tdur ≤ d_author` and `tdur_frames ≥ 1`; SEM-4: for each `feature` clip with ≥ 1 line that is not the first picture clip, `abs(cut_moment − t0(first line)) ≤ 0.15 + 1e-9` (`rhythm_source: narration` only); `music-bar` with narration non-empty (TL-4); SEM-2 `e_prev(snapped, pre-extension) ≤ t0 + tdur + 1e-9`; SEM-1 `t0_next ≥ t0 + tdur − 1e-9` (X-14, Y-7a); SEM-13 same-`z` overlay overlap; declares `t1 ≤ d_author` | blocking (fixed) |
| TV-3 | static | TL-0 (fixtures), TL-1 (real components) | table A A2/A3/A5 for every clip's device and every `transition_in.component`; A4 passes are collected for `pending_confirmation` | blocking (fixed) |
| TV-4a | static | TL-0 (fixtures) | `locked` params as written: unknown name, type, min/max/enum, asset/line references exist; a param with `source: "clip_dur"` must not be written by the author; every component in the `requires` closure exists and is selectable (X-10) | blocking (fixed) |
| TV-4b | timed | TL-0 (fixtures) | length-bound params (P-2 of the PSM v1 verification): for each `locked` clip, every component param with `source: "clip_dur"` takes the value `d_author` and is checked against its `min`/`max` (Z-4: the author's length, not the extended `d`; the extension is TV-19's info row). Needs the resolved file, so it runs in `validate --timed` | blocking (fixed) |
| TV-5 | static | TL-0 | `motion_intent == []` → look (provisional); clip `device.family`, its locked component `stock: true`, or any `uses` component with `stock: true` or family in `stock_devices` and `motion_intent == []` → blocking (fixed). `stock_devices` absent → the family part is `undetermined` | blocking (stock) / look |
| TV-6 | timed | TL-1 (TL-0: `undetermined`) | per text returned by `texts(lt)` sampled on every frame of the clip's `d_author` (the last picture clip also counts `tail_hold`, PSM decision for v4 report item 7): non-label: visible ≥ `n_han/cjk_cps + n_other/other_cps + base_s`; a clip with non-empty `headline` visible ≥ `headline_page_min_s`; label-type components: visible within `hold_range` | look (provisional) |
| TV-7 | timed | TL-0 | `end_hold_declared = (film_end − e_last) + Σ` last clip's `declares.holds` intervals that end at `d_author` (within one frame) and are contiguous back from it; compare with `end_hold.range_s`, endpoints inclusive with a 1e-6 tolerance (all terms come from integer frames, §4); absent rule → `undetermined`. Same quantity filmkit FK-R-16 measures on the film (freeze at the end, filmkit `end_min_duration_s` 1.0 floor) | look (provisional) |
| TV-8 | static | TL-0 | every `ground_exception` listed (info); missing/empty `why` → look; no static check of colours (X-9a: `ground_locked` in TL-3 measures the film) | look (provisional) |
| TV-9a | static / approve | TL-0 | product films only (§4.3): a `headline`, `data` or narration `text` containing a digit (`[0-9０-９]` or a Han numeral run of length ≥ 2 adjacent to a unit/percent sign — PSM decision, the determinable part of "數字") without a Claim → row; a Claim whose asset lacks `claims_ref` → row; no asset declares `portrays` while the film is a product film → row "identity source not declared"; a well-formed Claim whose text is not found in its `claims_ref` file → row (id `TV-9a#<where>.source`), an unreadable source → `undetermined` (2026-10-14: a fabricated claim had passed `validate --static`). Feature words are not determinable and go to the page's claim column for a human (gate rule) | look at `validate`, blocking at `approve` |
| TV-9b | timed / approve | TL-1 (TL-0: `undetermined`) | same rule on every clip's `texts()` output (TG-19: what a Canvas clip does not report is invisible) | look at `validate`, blocking at `approve` |
| TV-10 | timed | TL-0 | `free_s / Σ picture d` > `free_share_max`; absent key → `undetermined` | look (provisional) |
| TV-11 | compile | TL-1 | `MANIFEST.json` content hash ≠ file → refuse before any write | blocking (fixed) |
| TV-12 | timed / approve | TL-1 (`imported` counts as checked, marked 未回驗), TL-2 | every narration line `checked` or `imported` | blocking before approve (fixed) |
| TV-13 | static | TL-1 | comment-free scan (§6.5 step 1) of clip programs and components for `Date`, `performance.now`, `Math.random` (unless `TL.random(seed)`), `setTimeout`, `setInterval`, `requestAnimationFrame`, `fetch`, `XMLHttpRequest`, `@keyframes`/`animation:`/`transition:` in injected CSS, `.to(` | look (provisional) |
| TV-14 | timed | TL-0 | for a clip with `tdur > 0`: the last line whose `t0 < t0_clip`; if `t0_clip < that line's t1 − 1e-9` → look | look (provisional) |
| TV-15 | static | TL-0 (fixtures) | guided `uses` ⊆ device candidates; a guided clip's written `transition_in.component` ∈ its transition candidates; non-literal `TL.component` reference (§6.5) → blocking; two guided clips whose `uses` conflict → look | blocking / look |
| TV-16 | compile | TL-1 | `versions/<n>/` copies, assets and runtime hash vs `approval.json` | blocking (fixed) |
| TV-17 | static | TL-0 | `speed.asset` exists, is a video asset (extension list, ffprobe video stream), `table` rows `[a, b, s]` with `a < b`, `s > 0`, first `a == 0`, each `a == previous b` (no hole), last `b ≤ Asset.duration_s`; ffprobe absent → length part `undetermined` | look (provisional) |
| TV-18 | approve | TL-0 | required decisions present; every clip has `at`, `dur`, `motion_intent` (freedom is defaulted); no `estimated` line; every guided/free clip has `clips/<id>.js`; `--by model` → no override and `--questions` present; TV-9a/9b blocking parts (an `undetermined` TV-9b is recorded, not passed, Z-8) | blocking (fixed) |
| TV-19 | timed | TL-0 | `fixed`: last picture end beyond `film_end` → blocking; under `fit` and `fixed` alike, a narration line ending after `e_last` (it would be muted by D-T19's full-mute tail) → blocking (PSM decision: D-T19 consequence the design did not row); an overlay ending after `film_end` → blocking; every gap-fill extension → info (D-T22) | blocking / info |
| TV-20 | timed | 2026-10-19 | a picture clip without a `keys[]` entry of `role: key` (agent-review INV-R1: a section with nothing to read clearly is merged or cut) | look (provisional) |

Row `id`s are `TV-n#<where>` (e.g. `TV-2#S2`, `TV-19#ext:C1`). Messages for `timeline.html` are Traditional Chinese templates keyed by `message_key` in `_tl/messages_zh.py` (§3.1). RG12 and RG13 in §9 are PSM additions (the design's list ends at RG11).

## §8 Later milestones

### 8.1 TL-1 — components and compile (contract level; card written after TL-0)

**8.1.1 `ClipContract` / `TransitionContract` (JS, classic scripts; TG-9: no ES modules over `file://`)**

```js
// clips/<id>.js
TL.defineClip("S2", {
  draw(ctx, lt, d, p) {},        // ctx = {g: CanvasRenderingContext2D, el: HTMLElement, w, h, demoTime(lt)}
  texts(lt) { return [{text, x, y, claim}]; },
  events() { return [{t, kind}]; }
});
// a component: components/<family>/<name>.v<version>/component.js
TL.defineComponent("chapter-card.verb@1", {draw, texts, events});
TL.defineComponent("transition.dim-through-ground@1", {drawTransition(ctx, u, from, to, p) {}});
// inside a clip program: the only way to reach a component (§6.5)
const card = TL.component("chapter-card.verb@1");
```

`lt ∈ [0, d]` always; `draw` is a pure function of `(lt, d, p)` (TL-INV-3): no clock, no stored state across calls, no network. `el` is the clip's own container; the runtime shows it only while the clip is active; DOM text there is readable by `fidelity.py` (TG-19). `from(ctx2)`/`to(ctx2)` draw the previous/current clip into an offscreen canvas at the SEM-1 `lt` values.

**8.1.2 `FilmPage` runtime (`runtime/filmpage.js`, `build/index.html`)** — exposes `window.__setTime(t)` (synchronous; returns `undefined`) and `window.__ready` (a Promise resolved after fonts and images load), per filmkit's page contract (`render.py` help: "the HTML page (defines window.__setTime)"). At `t`: clear; `t < t0_first` → ground (`decisions.ground` or black); else the last picture clip with `t0 ≤ t`: inside its window → `drawTransition(u = (t − t0)/tdur, from = prev at min(t − t0_prev, d_prev), to = this at t − t0)`, else `draw(lt = min(t − t0, d))` (after `e_last`: `lt = d`, the tail hold); then overlays with `t0 ≤ t < e` in ascending `z`, `lt = t − t0`; then the caption component. An exception propagates (filmkit `page_runtime`, SG-5).

**8.1.3 `voice --import <dir>` (D-T25, Y-8b)** — `<dir>/<line_id>.wav` per line (any local source); each converted with ffmpeg to 48 kHz mono PCM s16, leading/trailing silence trimmed (`silenceremove`, threshold −50 dB, PSM decision mirroring filmkit's silence floor), stored as `voice/<line_id>-imp<sha8>.wav` (`sha8` = first 8 hex of the source file's sha256); `voice/lines.json` entry `{state: "imported", wav, wav_nsha, dur_s, key: null}` (Z-9: `key` null, the content hash is the identity). `VoiceLock` (`versions/<n>/voice_lock.json`): `{line_id: {path, nsha, key, dur_s, state}}`; `approve` copies the wavs into `versions/<n>/voice/`. `imported` lines satisfy TV-12 and are marked 未回驗 on the page and in `approve` line 1.

**8.1.4 `film_plan.json` from the resolved version (bound to `tools/filmkit/film_plan.schema.json` and `_fk/spec.py PLAN_KEYS`)**

| filmkit key | Value | Notes |
|---|---|---|
| `schema_version` | 1 | |
| `expected.duration_s` | `film_end_s` | whole frames by construction (§6.7 step 5) |
| `expected.size`, `expected.fps` | `meta.format` | |
| `expected.audio_expected` | true iff `mix.wav` is produced | no sound tracks → false and `--audio` omitted (X-4c) |
| `film_type` | `decisions.film_type.value` | §4.3 identity mapping |
| `sections` | picture clips `{id, t0, e}` after snap and gap fill | overlays not listed (they overlap by design) |
| `holds` | tail hold `{t0: e_last, t1: film_end, why: "tail hold (D-T19)"}` + each clip's `declares.holds` shifted by the clip's `t0` (SEM-9) | zero-length intervals omitted (filmkit rejects `t0 ≥ t1`; e.g. `fixed` with `e_last == film_end`) |
| `blacks` | `declares.blacks` shifted | |
| `silences` | (X-6) every interval where `mix.wav` is silent by construction: `[0, t0(L_first)]` "lead", each `[t1(L_i), t0(L_i+1)]` "line gap" or "section gap", tail `[e_last, film_end]` "tail silence (D-T19)", + `declares.silences` shifted; once music/sfx sound in an interval (TL-2/TL-4) that interval is not written, except the tail (always silent, D-T19, Z-2) | filmkit's silence floor (`profiles.json` `silence.min_duration_s` 2.0) means most gaps are below detection; declaring them is harmless and FK-R-14 lists them (v4 report item 8) |
| `narration_lines` | `{id, t0, t1}` per line (unsnapped) | filmkit FK-R-15 / FK-R-9 line branch |

No other key is ever written (filmkit validates strictly: `spec_invalid` in `render.py`, `plan.mode: unusable` in `check.py`). Selftest control: every generated plan passes `tools/filmkit/_fk/spec.validate_plan` (imported from the lab's `tools/filmkit` in the selftest only, never in `_tl`).

**8.1.5 `render.cmd.txt`** — one line, absolute paths with `/` (filmkit R-2 reasoning), quoted with `subprocess.list2cmdline`:
`python -X utf8 <lab>/tools/filmkit/render.py <film>/build/index.html -o <film>/build/final.mp4 --plan <film>/build/film_plan.json [--audio <film>/build/mix.wav] [--rules <lab>/tools/filmkit_rules.json] --film-type <slug>`.
`--duration`/`--size` come from the plan (filmkit D15). filmkit M0–M3 are built, so `--rules` and `--film-type` are always given (X-5 closed by fact); `--rules` is omitted only when the rules file is absent, and Notes then says "filmkit rule checks not enabled". `-o` sits directly in the page folder (filmkit D30). No `--target` (loudness is never this layer's, BR-15).

**8.1.6 `compile`** — reads only `versions/<n>/` (+ assets); order: lock → `verify_versions` → TV-16 → TV-11 over every `MANIFEST.json` entry → only then write (all files atomically, one by one; never replacing `build/`) → `MANIFEST.json` last. `--discard-edits` overwrites `edited` artifacts and records it in `revisions.md`. `--rebase` (Z-6, Y-4): when TV-16 fails only on `runtime_hash` or asset hashes, and the working timeline and clip programs equal `versions/<n>/` copies, `compile --rebase` writes nothing into `versions/` and nothing into `build/`; it records draft `n+1` (`parent n`, `DRAFT`) in `state.json` and prints the steps (`validate --static` → … → `approve`) that create version `n+1` with the current runtime/assets; if the working files differ, it refuses (`not_current`, "your working folder already is draft n+1; approve it"). Versions stay written only by `approve` (design §6.9 ownership).

**8.1.7 `Mix` (narration only in TL-1)** — inputs `versions/<n>/voice/*.wav` placed at each line's `t0`; output `build/mix.wav` 48 kHz stereo PCM s16 (mono duplicated), padded with silence to `film_end`, everything after `e_last` zeroed (D-T19 full mute); peak above `params.timeline.mix.peak_cap_dbfs` (fallback −1.0 dBFS in `_tl/defaults.py`, MANIFEST + Notes say "fallback used") → linear gain down to the cap, recorded. stdlib `wave`/`array` summing, ffmpeg only for format conversion (TG-13: `-filter_complex_script` when a graph is needed).

**8.1.8 TL-1 controls** (design §8.1 rows tagged TL-1, plus Z-items): TV-4/6/9a/9b/11/13/16, TL-INV-4/9/12, BR-16 (compile twice → byte-identical `compile` products), tail hold in `film_plan.json`, `compile` refusals (`VALID` → `not_approved`; product version with `undetermined: [TV-9b]` → `not_approved`, Z-8), TV-12 with `imported` (Z-8), `--rebase` both branches (Z-6), plan vs `validate_plan`, `render.cmd.txt` pasted in PowerShell and Git Bash (filmkit R-2 control shape), component selftests (30 out-of-order seeks identical; parameter range; event shape; `intents` fields), `end-card.restate@1` with `label_type: true` and a `hold_range` whose source is named in its `component.json` (X-17; fork listed for the TL-1 card: no measured value exists for the card's own visible time, only for the end hold after it).

### 8.2 TL-2 — narration (SKELETON)

Files: `_tl/voice.py` with `synthesize(line) -> wav` and `transcribe(wav) -> {text, words}` behind one interface each (design §6.2 weak points); `VoiceKey` = nsha of `{say, engine_id, engine_version, voice, rate, params}`; cache `voice/<line_id>-<key8>.wav` + transcript; Line state machine design §6.6 incl. `synthesized → failed(env)` and `asr` default `say` → `text` (X-16b); normalization before comparison (Traditional/Simplified folding, punctuation, digit readings; TG-12); `Mix` adds music with `narration_over_music_db`. **Open forks**: the TTS engine (D-T11 trial: BreezyVoice / Qwen3-TTS / Fun-CosyVoice3 on Windows), the ASR model (faster-whisper / Breeze-ASR-25 on the RTX 5070 or CPU), the Traditional/Simplified folding table. Not buildable from this document.

### 8.3 TL-3 — intent and revise (SKELETON)

`intent` runs lab instruments as subprocesses and copies each instrument's limits verbatim (design §7.5, X-7): `cut_on_line` = `segments.py` events + `narrlock.py --srt build/captions.srt`, pairing each declared cut to the nearest measured event within ±0.5 s (unpaired → `undetermined`; fewer than 3 events or lines → whole kind `undetermined`; events before 2.0 s skipped, as `narrlock.py`; overlays lower `segments.py` coverage, `--crop` for headline-only changes); `end_hold` = `density.py` after **RG11** (Z-5: `tools/density.py` gains a still-run list with positions and a `--selftest` with a 2.0 s still-tail synthetic film (positive) and an always-moving tail (negative); lab `CLAUDE.md` instrument entry updated; before RG11 the row is `undetermined`); `ground_locked` = `bgswitch.py`; `claims_traceable` = `fidelity.py` (Canvas text invisible, TG-19). `revise` compares two versions' resolved files and fingerprints; the per-section extension of design §11 starts from its output. Open forks: `intent.json` row shape, `density.py` output field names (decided in RG11's own change).

### 8.4 TL-4 — music, PV/MAD (SKELETON)

`tl.py music` (beat_this + `first_downbeat` override), `bar:`/`beat:`/`downbeat:` anchors, `cut_on_bar`, sfx mixing, T12/T13 transitions, T15 motifs, T16 lyric treatment. `MusicCue.analysis` deliberately unfrozen (design §13). Depends on W24 for lyric anchors.

### 8.5 TL-5 — lab A/B (SKELETON; RG5 per Z-1)

`tools/run_arm.py` on lab main at that time (re-read first; main moved after r22 and filmkit M1): arm-level `timeline_lib: true` (no round-level key; a round-level `timeline_lib` → exit 1 "set it per arm"); `mount_timeline_lib(cfg, arm, ws)` modelled on `mount_skills` (copy the MANIFEST-listed files to `<ws>/tools/timeline/`, never the rules file; assert copy hash == source hash); `run.json` top-level `timeline_lib_mounted` (bool) and `timeline_lib_hash` (full sha256 = library hash, `null` when not mounted); selftest: mounted arm has the folder, an arm in the same round without the key has none, the key lifts only this mount, round-level key refused. BR-10 wording "round 檔中該 arm 明寫" (design v4.4). §8.3 of the design (stability measures) defines the round.

## §9 Host changes (registrations RG1–RG11)

| # | Change | Milestone |
|---|---|---|
| RG1 | lab `CLAUDE.md`: Commands += `python -X utf8 tools/timeline/tl.py <validate --static\|resolve\|validate --timed\|view\|approve\|at\|mark\|index> …` and `python -X utf8 tools/timeline/selftest.py`; Invariants += INV-8 "after any edit under `tools/timeline/` run `python -X utf8 tools/timeline/selftest.py` before committing; an edit to `params.timeline` in `tools/filmkit_rules.json` also runs INV-7"; Layout += `tools/timeline/` (the library; `components/INDEX.md`, `index.json` generated by `tl.py index`), `films/<film_id>/` (formal films; `build/`, `voice/*.wav`, `versions/*/voice/` ignored) | TL-0 |
| RG2 | production-order last section | done (2026-10-08) |
| RG3 | skill `motion-video` steps 4, 6, 7, 8, `build-and-export.md` §1–§3 | TL-1 |
| RG4 | `~/.claude/tools/lab-skill-sync/pairs.json` motion-video `watch` += `tools/timeline`; mark | TL-1 |
| RG5 | `tools/run_arm.py` arm-level `timeline_lib` (§8.5, Z-1) | TL-5 |
| RG6 | `~/.claude/references/PROJECTS.md` lab row: tool list += timeline layer | TL-1 |
| RG7, RG8 | W08 closed; W28 opened | done |
| RG9, RG10 | none needed | — |
| RG11 | `tools/density.py` still-run list + selftest; lab `CLAUDE.md` instrument entry (Z-5) | TL-3 |
| RG12 | `.gitignore` lines of §3.2 | TL-0 |
| RG13 | `tools/filmkit_rules.json` += `params.timeline` (§4.10); it is a lab-skill-sync watched path (`motion-video` pair): after merging, run `python -X utf8 tools/lab-skill-sync/sync.py check` from `~/.claude`; `params.timeline` carries no film-level ruling, so the expected action is `sync.py mark motion-video` with no skill text change (state that in the commit body) | TL-0 |

## §10 Work cards

Each card: branch `feat/timeline-tlN` from lab main; commits by path, Conventional Commits; a checkpoint with incomplete gates is `wip(timeline): …`; evidence in `measurements/timeline/tlN-evidence-<date>.md`. Every gate runs its positive AND negative control, and each positive control is shown to fire (a control that cannot fail is not a control).

### 10.1 Invariant and gap controls

| Item | Control (positive / negative) | Milestone |
|---|---|---|
| TL-INV-1 | normalized hash: the same timeline as CRLF+BOM and as LF → equal nsha / one character changed → different; key order permuted → equal | TL-0 (TL-1: MANIFEST) |
| TL-INV-2 | anchor cycle `S2.at → clip:S3.end`, `S3.at → clip:S2.end` → TV-1 lists both / chain S1 → S2 → S3 resolves; `order_seed` 0 vs 7 → byte-identical resolved file | TL-0 |
| TL-INV-3 | — | TL-1 |
| TL-INV-4 | — | TL-1 |
| TL-INV-5 | table A A5 (`source: model` override still blocks) / A4 with `source: user` passes and is listed | TL-0 (fixtures) |
| TL-INV-6 | write to `versions/1/timeline.json` → `PermissionError` / clear the attribute, edit, run `tl.py view` → `fingerprint_mismatch` naming the file; an untouched version → commands run | TL-0 |
| TL-INV-7 | fixture component with `measured` flag and `card_tier: unverified` → index `claim_tier: unverified` / `card: null` component → own tier | TL-0 (index) |
| TL-INV-8 | every selftest stdout and file scanned for the §5.2 word list / a fixture message template containing 完成 fails the scan | TL-0 |
| TL-INV-9 | `timeline.html` regenerated from the same inputs → byte-identical / a hand edit is overwritten by the next `view` (not protected: `view` output is not a `compile` product, §3.3) | TL-0 |
| TL-INV-10 | `--rules <missing>` → TV-5 (family part), TV-7, TV-10 `undetermined` with reason / the real rules file → determined | TL-0 |
| TL-INV-11, 12 | — | TL-1/TL-2 |
| TG-7 | 5.05 s at 30 fps snaps to frame 152 (`5.066667`) / 5.0 s → frame 150 | TL-0 |
| TG-8 | two assets `assets/A.png`, `assets/a.png` → `spec_invalid` / distinct names pass | TL-0 |
| TG-16 | kill `approve` after writing `versions/2.tmp/` → next command deletes it with a note; kill after the rename, before `state.json` → next command recovers version 2 as `APPROVED` with a note / normal approve → no note | TL-0 |
| TG-17 | film folder under a path with a space and CJK characters → all commands work, outputs use `/` / — | TL-0 |
| TG-18 | process A holds the film lock (test helper), B runs `validate` → `busy`, nothing written / A released → B runs; A hard-killed → B acquires within 2 s | TL-0 |
| BR-14 single source | a fixture `_tl` file with `free_share_max = 0.3` → selftest scan fails / real `_tl` passes | TL-0 |
| `--help` | `tl.py --help` sub-command list equals §5.1's TL-0 rows / a fixture parser missing `at` fails | TL-0 |

### 10.2 TL-0 — the timeline file, its checks, resolution, page and approval

- **Severity / confidence**: blocker for TL-1…TL-5 (everything compiles from the resolved, approved timeline) / spec v1 under one independent verification this session; the card's controls are the first check of everything this PSM decided.
- **Objects** (new unless noted):
  - `tools/timeline/`: `README.md`, `MANIFEST.txt`, `tl.py`, `film.timeline.schema.json`, `selftest.py`, `_tl/{__init__, common, nhash, lock, defaults, model, timeref, rules, components, select, uses, validate_static, resolve, validate_timed, state, approve, view, at, currency, messages_zh}.py`, `components/INDEX.md`, `components/index.json`, `components/evidence.json` (empty library: `"components": []`).
  - `tools/filmkit_rules.json` (edit): `params.timeline` per §4.10 only; no other byte changes.
  - `films/dit-promo/`: `film.timeline.json`, `voice/lines.json` (only if the user chose narration and wants hand estimates), `assets/README.md` and `assets/USER_GUIDE.md` copied from `experiments/r4-dit/inputs/` (text; the copy is the film's own; the source folder is not written), `build/questions.md` if any decision is model-filled, `state.json`.
  - `.gitignore` (edit): RG12 lines.
  - `CLAUDE.md` (edit): RG1 lines.
  - `measurements/timeline/tl0-evidence-<date>.md`.
  - NOT touched: `tools/filmkit/` (any file), `tools/run_arm.py`, any `experiments/` or `rounds/` file, `docs/timeline-layer-design.md` (the design changes only through a PSM revision), the motion-video skill text.
- **Why**: TL-0 is the carrier the pain lacks (design §1.1): one file that holds the film's decisions and timing, checked and resolved by a program, shown to the user as a page.
- **Change** (build to §3–§7 exactly; suggested order, one `wip(timeline): …` checkpoint commit after each step whose controls pass):
  1. `common`, `nhash`, `lock`, `defaults`, `messages_zh`; the TL-INV-1, TG-8, TG-18, TL-INV-8 controls.
  2. `film.timeline.schema.json`, `timeref`, `model`, `rules`; the 22 schema fixtures (§4.1); `params.timeline` added to the rules file, then INV-7 (`python -X utf8 tools/filmkit/selftest.py`, `python -X utf8 tools/filmkit_rules_selftest.py`) both exit 0.
  3. `components` (+ `tl.py index`), `select`, `uses`, `validate_static`, `currency`; TV-1/3/4a/5/8/9a/15/17 controls with fixture libraries.
  4. `resolve`, `validate_timed`; TV-2/4b/7/10/14/19, SEM, gap-fill, whole-frame (470 frames), tail-hold, `film.end`, TG-7 controls.
  5. `state`, `approve`, `mark`, `at`; TV-18, TL-INV-6, TG-16 controls.
  6. `view`; TL-INV-9 control; page-fill gate on a fixture page.
  7. The DIT timeline (below), RG1, RG12, README, then the final `feat(timeline): …` commit.
- **The DIT timeline (`films/dit-promo/film.timeline.json`)**: at session start ask the user the skill's step-0 questions that fill `film_type`, `audience`, `energy`, `rhythm_source` and §0 question 1 (narration), and write their answers with `source: user`; anything they leave open is written with `source: model` + `evidence`, and listed in `build/questions.md` (skill step 0). Structure from `rounds/brief-dit-promo-v1-draft.md`: an opening clip (shape to name, C07), one verb-card clip per chapter (3–4, C17; verbs from the USER_GUIDE's own wording), one feature clip after each card, an end card restating the key line (C17). Every clip `guided` with its `device.family` (no component exists before TL-1, so `locked` would only produce A2 blocks); the intended TL-1 component goes into `what`. Every identity string from an asset's `portrays` (the README copy, `subject_name` as the README writes the product name); every narration line and headline quoting a document carries a Claim pointing at `assets/README.md` or `assets/USER_GUIDE.md` (`claims_ref` = the file itself). If the user chose narration: lines drafted only from the two documents' wording, durations estimated (§4.4). The film must reach `VALID`: `validate --static` and `validate --timed` with 0 blocking (look rows allowed and listed in the evidence), then `view`. `approve --by user` on it must be **refused** with `missing_required` (estimated durations) when narrated, or (not narrated) with `missing_required` for the missing clip programs — the first real-data run of TV-18; record the five lines.
- **Interpretation forks** the spec does not settle → stop and report with the options; do not pick. Known non-forks: severities stay as §7 until D-T9; TV-6/TV-9b are `undetermined` in TL-0 by design.
- **Blast radius**: new files, plus the four edits named above. Must not change: any existing tool's behaviour, `tools/filmkit/selftest.py` and `tools/filmkit_rules_selftest.py` results, `run_arm.py --selftest`, `build_index.py --check`, `waiting_pool.py --check`.
- **Rollback**: delete branch `feat/timeline-tl0` (nothing merged until acceptance 6). After merge: `git revert` the TL-0 commits; `params.timeline` removal restores the rules file byte-for-byte (filmkit never read it); no other tool depends on `tools/timeline/` until TL-1.
- **Acceptance** (machine-checkable first):
  1. `python -X utf8 tools/timeline/selftest.py` exit 0, output pasted into the evidence file; every control in §10.1 (rows tagged TL-0) and in the table below ran with BOTH arms, each positive arm shown to fire. Skipped controls listed with their reason (only the non-Windows lock skip is allowed).
  2. INV-7 after the rules edit: `python -X utf8 tools/filmkit/selftest.py` and `python -X utf8 tools/filmkit_rules_selftest.py` exit 0 (outputs pasted); `python -X utf8 tools/run_arm.py --selftest`, `python -X utf8 tools/build_index.py --check`, `python -X utf8 tools/waiting_pool.py --check` exit 0.
  3. Library self-containment: copy the MANIFEST-listed files of `tools/timeline/` to an empty temp folder; `python -I -X utf8 selftest.py` there exits 0 (`-I` drops the script folder from `sys.path`; `tl.py` and `selftest.py` insert their own folder themselves, §3.1) (no import from the lab, no rules file → the TL-INV-10 `undetermined` rows appear and are counted as expected).
  4. DIT: the five lines of `validate --static`, `resolve`, `validate --timed`, `view`, and the refused `approve` pasted; `films/dit-promo/build/timeline.html` passes `python -X utf8 ~/.claude/tools/page-fill-gate/fill_gate.py films/dit-promo/build/timeline.html` (declared class `dashboard`), output pasted.
  5. `tl.py at films/dit-promo <t>` for three times (inside a clip, inside a transition window if any, inside the tail hold) pasted.
  6. User acceptance (A 必驗 below) — the executor prepares it, the user rules; TL-0 is not merged before it.
  7. After merge (RG13): `sync.py check` from `~/.claude`; mark `motion-video` with no skill text change, or report the warn if the check says otherwise.
- **Commit**: `wip(timeline): <step>` checkpoints, then `feat(timeline): add TL-0 timeline format, checks, resolver, page and approval`; merge to main only after acceptance 6 (local ff-merge, no remote).

A 必驗（交給使用者，依後果排序）：
1. 打開 `films/dit-promo/build/timeline.html`：不看 JSON，你說得出每一段「是哪段（ID）、幾秒到幾秒、用什麼手法、為什麼動」；看不懂的地方就是 TL-0 沒做到。
2. 頁面最上方的決策卡：哪些是你說的、哪些是模型定的，標得對不對；模型定的那幾項你同不同意。
3. 若有旁白：每一句都取自 README／USER_GUIDE 的說法、虛線標「估算」，沒有編出文件沒說的功能或名稱。
4. 跑一次 `tl.py at films/dit-promo 12`（或任一秒數）：回答的片段 ID 和你在頁面上看到的同一段。

B 體驗：頁面在你的螢幕寬度下好不好讀（片段表與軌道是否擠在一起）；中文訊息的措辭；五行輸出看不看得懂下一步要做什麼。

Controls (design §8.1 rows for TL-0, design §9 TL-0 list, plus the Z/X/Y items this PSM settles). Fixture base = design §7.1 with `voice/lines.json` `est_dur` L1 3.0, L2 2.0, L3 2.5, L4 2.0, 30 fps, `fit`, `section_gap` 1.2, `lead` 1.0, `tail` 2.0. Resolved base values (computed with §6.7): L1 [1.0, 4.0], L2 [5.2, 7.2], L3 [7.65, 10.15], L4 [10.6, 12.6]; S1 [0, 4.3]; C1 [4.3, 5.7]; S2 `t0_raw` 5.05 → `t0` 5.066667, window [5.066667, 5.366667], cut moment 5.216667; S2 end 12.9; E1 [12.9, 13.7]; `film_end` 15.7, 471 frames, tail hold [13.7, 15.7].

| Control | Positive (must fire) | Negative (must not fire) | Closes |
|---|---|---|---|
| schema/validator agreement | 14 invalid fixtures rejected by both | 8 valid fixtures accepted by both | §4.1, Y-1 |
| TV-1 cycle | S2.at → clip:S3.end, S3.at → clip:S2.end → blocking, both nodes listed | chain S1 → S2 → S3 | TL-INV-2 |
| TV-1 `film.end` | `fit` + E1 `at: {anchor: film.end, offset: -3}` → blocking | same under `fixed` 20.0 s → resolves, E1 at 17.0 | SEM-11 |
| TV-1 SEM-3 | S2 `dur: {lines: "L2-L4"}` with L3.section = S3 → blocking | all three in S2 | SEM-3 |
| TV-1 missing fields (X-13) | clip without `at` → blocking "missing at"; without the `motion_intent` key → blocking | clip without `freedom` → no row; `defaults_applied` has `S2.freedom=guided`; the page shows 預設 | SEM-10, X-13 |
| TV-2 SEM-2 overlap | §7.1 as written: C1 ends 5.7 > window end 5.366667 → blocking | C1 `dur` 0.9 → ends 5.2 ≤ 5.366667 | SEM-2 |
| TV-2 SEM-4 | S2 `at: line:L2.start + 0.25` with 0.3 s transition → cut moment 5.6 vs 5.2 → blocking | base S2 (deviation 0.016667); S1 (first picture clip) and a `feature` clip with no lines are not checked | SEM-4, X-1 |
| TV-2 SEM-1 windows | clip A window [10, 11), next clip `t0` 10.5 → blocking | next `t0` 11.0 | X-14, Y-7a |
| TV-2 one-frame transition | `tdur` 0.01 at 30 fps → blocking | `tdur` 0.04 (1 frame) | §6.7 step 6 |
| TV-2 SEM-13 | two `z: 1` overlays overlapping → blocking | `z: 1` and `z: 2` overlapping; an overlay across S1→S2 keeps `lt` counting from its own `t0` (resolved `t0` unchanged, no extension) | SEM-13 |
| gap fill (D-T22) | — (no blocking) | C1 ends 0.2 s before S2's start → `extensions` has C1 +0.2 s, TV-19 info row, the page hatches it | D-T22, TV-19 |
| anchors read pre-extension (Z-4, Y-2) | the same variant resolved by a test double that re-reads extended ends → its `E1.t0_f` ≠ 402 (the selftest asserts the double's value differs; the real resolver must not equal the double) | variant: E1 `at: {anchor: clip:S2.end, offset: 0.5}`, `dur` 0.8 → S2 `e_author_f` 387 (12.9 s), E1 `t0_f` 402 (13.4 s), S2 extended by 0.5 s (`extensions` = `[{clip: S2, by_s: 0.5, to_f: 402}]`), E1 `e_f` 426, `n_frames` 486 (16.2 s); resolve converges in one pass | Y-2, Z-4, P-3 |
| TV-4b reads `d_author` (Z-4; runs in `validate --timed`) | the same fixture clip authored at 1.2 s → `TV-4b#<clip>` blocking, measured 1.2 vs max 1.0 | fixture component param `card_s` with `source: "clip_dur"`, `max` 1.0; locked clip authored `dur` 0.9, followed by a 0.3 s gap so gap fill extends it to 1.2 s → no TV-4b row (judged on 0.9), TV-19 info row for the extension | Z-4, P-2 |
| whole frames (P-1) | a test double that writes `round(film_end_s, 6)` for the 470-frame variant → `abs(15.666667·30 − 470)` = 1e-5 > 1e-6, the selftest's filmkit-equivalent check rejects it | variant E1 `dur` 0.766667 → E1 `e_author_f` 410, `n_frames` 470, `film_end_s` = 470/30 → `abs(s·30 − 470) ≤ 1e-6` passes; every snapped second in the resolved file passes the same check; `fixed` with `duration_s` 15.666667 → accepted by TV-1, `n_frames` 470 | P-1 |
| tail hold (resolve side) | `fixed` 13.7 with `e_last` 13.7 → `tail_hold` null (no zero-length interval) | `fit` + `tail` 2.0 → `tail_hold` [13.7, 15.7] | D-T19, X-4a |
| TV-7 | `tail` 5.8 → look, measured 5.8 vs [1.5, 2.5] | `tail` 2.0 → no row | D-T23, X-6c |
| TV-7 with declared end holds | E1 declares holds [0.2, 0.6] (not at the end) + `tail` 1.0 → 1.0 → look | E1 declares holds [0.2, 0.8] (ends at `d_author` 0.8) + `tail` 1.0 → 1.6 → no row | Y-7b, P-6 |
| TV-19 fixed overrun | `fixed` 13.0 with `e_last` 13.7 → blocking | `fixed` 15.7 | X-15c |
| TV-20 / keys (`kbt_keys`) | base → `TV-20#S1`…`#E1` look; `E1` key `at` 5.0 → `TV-2#E1.keys` blocking; resolve `K-S2.t_f` = S2 `t0_f` + 6 | every clip keyed → no TV-20; no keys → no `keys` field in the resolved file | agent-review design M1 |
| TV-19 narration into the tail (`fit` and `fixed` both) | variant S2 `dur: 6.0` → S2 `e_f` 332, E1 `e_f` 356 (11.866667 s) < L4.t1 12.6 → `TV-19#L4` blocking | base (L4.t1 12.6 ≤ `e_last` 13.7) | PSM (D-T19), P-10 |
| TV-10 | `free` clips 40 % of picture time → look | 10 % → no row; rules absent → `undetermined` | BR-3 |
| TV-14 | S2 `at` 3.6 (before L1 ends at 4.0) with 0.3 s transition → `TV-14#S2` look (assert this row id only; the variant also trips TV-2 rows, not compared) | base (window starts at 5.066667, 1.066667 s after L1 ends) | TV-14, P-5 |
| TV-5 | `glitch` family clip with `motion_intent: []` → blocking; a non-stock clip with `[]` → look | the glitch clip with one intent line | BR-6 |
| TV-8 | `ground_exception` without `why` → look | with `why` → info only | X-9a |
| TV-9a | product film headline "支援 3 種格式" without Claim → look at validate and blocking at approve; no asset with `portrays` → row; Claim text absent from the source → look, blocking at approve; unreadable source → undetermined | Claim present, `portrays` declared; a `narrated-explainer` without `claims_ref` assets → no TV-9a rows | BR-12, X-9b |
| TV-3 table A (fixture library) | A2 `chapter-card.verb@9` → blocking + lists `@1`; A3 `energy` unset + non-`any` component → blocking; A5 incompatible + `source: model` → blocking; `hype`-only component in a `calm` film → blocking | A3 `energy` unset + `any` component → passes to A4–A6 and `when` is still judged; same component in a `lively` film; A4 `source: user` + `confirmed` → pass, listed in `pending_confirmation` | TV-3, X-15b |
| TV-3 transitions (X-2) | `calm` film, locked clip `transition_in` with a `hype`-only transition → blocking | a compatible transition | X-2 |
| TV-4a (fixture library) | `hold_s` 2.0 > max 1.5 → blocking; component `requires` a missing component → blocking; author writes a `clip_dur` param → blocking | in range; `requires` present | TV-4a, X-10 |
| TV-15 (fixture clip programs) | guided S2 program calls a component outside `S2.candidates.json` → blocking; S2 writes a transition outside `S2.transition.candidates.json` → blocking; template literal / alias / bracket access → blocking | only candidates; comment and string occurrences ignored | SEM-6, Z-7a |
| A7 candidate files | — | guided clip → both candidate files written with `decision_inputs`; empty library → empty lists + note | A7, Z-7a |
| TV-17 | table with a hole, or beyond `duration_s` (a 2 s generated test mp4), or `speed.asset` a PNG → look | contiguous from 0 within length; ffprobe absent (PATH emptied for the call) → length part `undetermined` | X-8 |
| TV-18 | approve with `energy` unset; with an estimated line; `--by model` with an A4 override; a guided clip without its program → each `missing_required` listing the item | narration-free fixture with all decisions, locked fixture components and one guided clip with its program → `APPROVED` | TV-18, Z-8 |
| approve line 1 (Z-7c, Z-8) | — | fixture with one A4 override, one open guided transition and one explicit cut → line 1 names all three and "not checked yet: TV-6, TV-9b"; `approval.json` has `undetermined: ["TV-6", "TV-9b"]`, `hard_cuts`, `pending_confirmation` | Z-7c, Z-8 |
| approve copies (Z-9) | — | used component with `requires` → both folders under `versions/1/components/`; the version's `timeline.json` has `freedom` materialized | Z-9, X-11c |
| currency (§5.4) | edit `film.timeline.json` after `resolve`, run `validate --timed` → `not_current` "run tl.py validate --static"; `approve` on a `DRAFT` → `not_current` | unchanged inputs → runs | design §4 |
| state transitions | `mark --abandoned` on an `ABANDONED` draft → `illegal_transition` | `VALID` → inputs edited → next command shows `DRAFT`; approve → draft null; edit → draft n+1 `parent` 1 | §6.4 |
| `at` (BR-11) | `at 5.2` → S2 and C1, `in_transition: true` | `at 9.0` → S2, line L3, `lt` 3.933333; `at 14.5` → E1 tail hold | BR-11 |
| page (`view`) | a validate row of `look` → shown in the top band with its clip id | every clip id and line id present in the HTML; estimated lines carry the dashed class; no `http://`/`https://` in the file; `data-page-class="dashboard"` | design §5.1, TL-INV-9 |
| DIT real data | `approve` refused (`missing_required`) | `validate --static`/`--timed` 0 blocking; page passes the fill gate | TV-18, design §9 TL-0 |

## §11 Error paths and rollback

| Failure | Behaviour | Rollback |
|---|---|---|
| any refusal (`kind`) | nothing written except `.tl.lock` (and the state change the refusal itself defines, e.g. `VALID → DRAFT` on stale inputs) | none |
| exception inside one row evaluator | the row `undetermined` with the exception's last line; other rows still run; exit 3 | rerun after fixing |
| exception elsewhere | `Failed: internal`; partial `.tmp` files under `build/.tl/` cleaned on the next start | attach `validate.json` / stderr to a bug note |
| `approve` killed | §4.7 recovery | none |
| versions folder edited | `fingerprint_mismatch` on every command but `at` | `git checkout -- films/<id>/versions/<n>`, or `mark --abandoned --version n` |
| rules file unparsable | `spec_invalid` on every command | fix the JSON; INV-7 |
| a milestone gate fails | branch not merged | main untouched |
| TL-0 rules edit breaks filmkit selftests | do not merge; revert the `params.timeline` hunk | byte-identical restore |

## §12 Gap register: platform bindings (design §10)

| TG | TL-0 binding |
|---|---|
| TG-7 | §6.7 step 6 snap formula; resolved records raw and snapped values; control §10.1 |
| TG-8 | §4.12 nsha; case-collision refusal; controls §10.1 |
| TG-16 | §4.8 write sequence; §4.7 recovery; control §10.1 |
| TG-17 | ids separate from file names; folder names `<name>.v<version>`; `-X utf8`; `/` in every printed path; control §10.1 |
| TG-18 | §5.5; duplicated lock (§3.1); control §10.1 |
| TG-3, TG-19 | partial distortions stand: the page shows `layout`/`camera`/family next to each clip for a human; TV-9a covers only determinable digits and identity sources |
| TG-1, 2, 4, 5, 6, 9–15 | bound in TL-1/TL-2/TL-4 (§8) |

## §13 Re-verification triggers (review-when)

Inherits design review-when. Also: `tools/filmkit/film_plan.schema.json` or `_fk/spec.py PLAN_KEYS` changes → recheck §8.1.4; filmkit `render.py` flags change → recheck §8.1.5; `tools/filmkit_rules.json` gains a `rules[]` entry the timeline layer should mirror → recheck §4.10. Known case, open: FK-W32-33's `head_hold` (W33, merged in 931c4cd: the first still within the first 5 s ≤ 1.5 s, detection floor 1.0 s, `missing_ok`) has no timeline-side row; a `ground_preroll` or an opening clip that holds still longer than 1.5 s would be reported by filmkit only after rendering. A design-time TV row mirroring it (like TV-7 mirrors `end_hold`) is a design change for the next design revision, not added here; `film-types.md` gains or renames a film type → nothing to edit here (rules file is the source), but rerun the TV-1 film-type control; `filmkit_rules_selftest.py` starts validating `params` → recheck §4.10; Python leaves 3.12 or ffprobe leaves 8.1 → rerun §10.1 TG controls; the page-fill gate's class registry renames `dashboard` → update §6.11.

## §14 Traceability

### 14.1 X-4 … X-18 (design v3 report; design §13 requires item-by-item closure)

| X | Item | Closed in |
|---|---|---|
| X-4 | milestone dependencies: (a) TL-0 tail hold from `resolve`; (b) TL-1 narration by `voice --import`; (c) TL-1 mix narration-only, `--audio` omitted without sound; (d) RG1 in TL-0; (e) TV-8 in TL-0 | (a) §6.7 step 5, §10.2 "tail hold"; (b) §8.1.3; (c) §8.1.4, §8.1.7; (d) §9 RG1, §10.2; (e) §7 TV-8, §10.2 |
| X-5 | `--rules`/`--film-type` staging | §8.1.5: filmkit M0–M3 on main, flags always given; `--rules` only when the file exists |
| X-6 | D-T19 consequences: (a) auto silences; (b) superseded by Z-2 (full mute, user); (c) `tail` vs end-hold range and two measurements | (a) §8.1.4 `silences`; (b) §8.1.7 tail zeroed, §8.1.4 tail silence always; (c) `tail` 2.0 in [1.5, 2.5] (D-T23), TV-7 = filmkit FK-R-16 quantity (§7), control §10.2 |
| X-7 | instrument limits; Canvas text; overlays vs `segments.py` | §8.3 (verbatim limits, pairing rule), §8.1.1 DOM container note, §12 TG-19, TV-9b mechanics (§7) |
| X-8 | `speed` fields, contiguous table, asset length | §4.1 `speed`, `duration_s` derivation; §7 TV-17; control §10.2 |
| X-9 | TV-8 unreadable field; TV-9 severity by stage | §7 TV-8 (exceptions only), TV-9a/9b look at validate, blocking at approve |
| X-10 | `requires` consumer; overlay ancestor | §7 TV-4a (closure), §4.9; overlay ancestor is design BR-3 (v4) |
| X-11 | fingerprint lists, runtime hash, copies | §4.8 (one list), §4.12 runtime hash, §4.8 copies; rules not fingerprinted (D-T24) |
| X-12 | filmkit-owned files; check-all-before-write | §3.3 owner table (`sheet_1fps.png`, `.filmkit/`, transform files); §8.1.6 order |
| X-13 | draft fill-in only for `freedom` | §4.1 `decisions` note, `Clip.freedom`; §7 TV-1, TV-18; control §10.2 |
| X-14 | windows must not overlap; `tdur` naming | §7 TV-2; §4.2 `tdur`; control §10.2 |
| X-15 | (a) A2 and TL-INV-8 controls; (b) A3 → A4–A6; (c) `fixed` overrun owner | (a) §10.2 TV-3, §10.1 TL-INV-8; (b) §6.4 table A; (c) §7 TV-19 |
| X-16 | evidence two flags; Line `synthesized → failed(env)`, `asr` default | §4.9 `evidence.json` (`watched`, `measured`), `claim_tier`; §8.2 (TL-2 SKELETON names both) |
| X-17 | restating end card is label type | §8.1.8 (`end-card.restate@1` `label_type: true`; hold_range source named in the TL-1 card) |
| X-18 | small items: (a) D-T10 wording; (b) D-T9 list; (c) BR-11 `at`, `cut_on_line` only for SEM-4 clips; (d) historic note; (e) `override.source` domain | (a)(b)(d) design v4; (c) §6.12, §8.3 pairing only for TV-2/SEM-4 clips; (e) §4.1 `override` |

### 14.2 Design v4 report §5 items 1–11 (`verification_timeline-layer-design-v4_2026-10-09.md`)

| # | Item | Closed in |
|---|---|---|
| 1 | Y-2 extension order and anchor reads (+ §8.1 pair) | §6.7 steps 3/7; §10.2 "anchors read pre-extension" |
| 2 | Y-3 `end_hold` measurement source | §8.3 RG11 (Z-5); TV-7 design-side check in TL-0 |
| 3 | Y-4 old versions after runtime/asset change | §8.1.6 `--rebase` (Z-6) |
| 4 | Y-5 guided transition candidates and enforcement | §4.11, §7 TV-15, §5.2 approve line 1 (Z-7) |
| 5 | Y-7 TV-2 window rule; TV-7 under `fixed` | §7 TV-2, TV-7; controls §10.2 |
| 6 | Y-8 `voice --import` shape; FK-R-8 at filmkit M2 | §8.1.3; filmkit M2 built (main), so the design's §8.1 tail-hold row is observable from TL-1 |
| 7 | `end-card.restate` `hold_range`; does TV-6 count `tail` | §7 TV-6 (last clip counts `tail_hold`); §8.1.8 (hold_range in the TL-1 card) |
| 8 | auto-declare `line_gap` silences | §8.1.4 `silences` (yes; below filmkit's 2.0 s silence floor, harmless) |
| 9 | TL-0 approve and TV-9b; TV-12 with `imported` | §4.8 `undetermined`, compile refusal; §7 TV-12; §8.1.8 (Z-8) |
| 10 | film-type mapping; new rules keys into the schema | §4.3; §4.10 (`params.timeline`, filmkit PSM §4.5 `params` shape) |
| 11 | Y-9 text residues | design v4.4 (§14.3 Z-9) |

### 14.3 Z-1 … Z-9 (design v4.1 report)

| Z | Severity | Closed in | Design write-back (v4.4) |
|---|---|---|---|
| Z-1 | should-fix | §8.5 arm-level `timeline_lib`, `mount_timeline_lib` like `mount_skills`, `run.json` top-level keys, full sha256; §0 question 2 | RG5, §4 table row, TL-INV-10, BR-10 wording |
| Z-2 | user ruling | resolved in design v4.2 (full mute); §8.1.4, §8.1.7 implement it | — |
| Z-3 | should-fix | `from` draws the previous clip's (extended) last frame: §8.1.2 | SEM-2, §8.1 gap-fill row, v4 change note "any gap" |
| Z-4 | should-fix | §4.5 `d_author` vs `d`; §7 TV-4b/TV-6; §10.2 two controls | §6.3 step 7 sentence |
| Z-5 | should-fix | §8.3 RG11; §9 RG11 | §3.2 RG11, §9 TL-3 dependency |
| Z-6 | should-fix | §8.1.6 `--rebase` (state only; versions written by `approve`) | §3.1 versions row |
| Z-7 | should-fix | (a) §4.11 transition candidate file; (b) §4.1 absent ≡ `"cut"`; (c) §5.2 line 1, §4.8 `hard_cuts` | SEM-1 default |
| Z-8 | should-fix | §4.8 `undetermined`; compile refusal; §10.2 approve controls; TV-12 in TL-1 (§8.1.8) | §9 TL-0 row sentence |
| Z-9 | should-fix | `requires` copied by `approve` (§4.8); `imported` VoiceLock `key` null (§8.1.3) | `Component.requires` text, v3 change note 2.5 → 3.0 → 2.0, §14.5 Y-6 note |

### 14.4 PSM elements → ancestors (new in this PSM)

| Element | Ancestor |
|---|---|
| `dur` end-anchor form (§4.2) | design §6.1 `TimeRef`; SEM-3 |
| role vocabulary (§4.3) | design §6.1 `role`; SEM-4 |
| product-film set (§4.3) | BR-12; TV-9 |
| rate estimate (§4.4) | design §6.3 last paragraph |
| snap tie rule (§6.7) | TG-7 / SG-1 |
| `evidence.json` outside component folders (§4.9) | BR-7, BR-8 (fingerprints stay stable) |
| `uses` literal-only rule (§6.5) | SEM-6; gate rule "rule only on what it can determine" |
| `Line.claim`, TV-9a digit rule (§4.1, §7) | BR-12 |
| TV-19 narration-into-tail row | D-T19; BR-1 |
| `mark` command, `illegal_transition` kind | design §6.4 `ABANDONED` events; §6.10 |
| duplicated lock (§3.1) | TG-18; filmkit FK-INV-7 (kit stays private) |
| `CUT_TOLERANCE_S` in code (§4.10) | SEM-4 (format constant), TL-INV-10 (works without rules) |
| `films/` location (§3.2) | design §3.1 "round output／formal film" |
| page class `dashboard` (§6.11) | global rule: human-read HTML declares a class and passes the fill gate |

### 14.5 PSM v1 verification (`verification_timeline-layer-psm-v1_2026-10-10.md`) → v1.1

| # | Severity | Applied in v1.1 |
|---|---|---|
| P-1 | BLOCK | §4 preamble: snapped times are integer frames, seconds = `frames / fps` unrounded; §4.5 example and fields `*_f`; §6.7 steps 5–7 in frames; §4.1 `duration_s` tolerance 1e-3 then integer; §10.2 "whole frames" control (470 frames, 6-decimal test double must fail) |
| P-2 | BLOCK | §7 TV-4 split into TV-4a (static) and TV-4b (timed, `source: "clip_dur"` params read `d_author`); §4.9 `source`; §6.6/§6.8 order; §10.2 controls; design v4.4 TV-4 row |
| P-3 | should-fix | §10.2 "anchors read pre-extension": E1 anchored to `clip:S2.end + 0.5`, extension 0.5 s, exact frames 387/402/426/486, test double asserted to differ |
| P-4 | should-fix | §4.5 example `extensions` emptied (base film has no gap fill) and marked illustrative; extension row shape `{clip, by_s, to_f, to}` |
| P-5 | should-fix | §10.2 TV-14 row: 1.066667 s; positive arm asserts the row id only |
| P-6 | should-fix | §7 TV-7 endpoints inclusive, tolerance 1e-6; §10.2 values moved off the boundary (1.0 / 1.6) and arms put in the right columns |
| P-7 | should-fix | §3.1 `tl.py`/`selftest.py` insert their own folder into `sys.path`; §10.2 acceptance 3 says why |
| P-8 | should-fix | design v4.4 §6.9 flag staging replaced by "filmkit built, flags always given"; D-T12 Haiku clause annotated pending the user (U-2) |
| P-9 | should-fix | branch rebased onto main 931c4cd; front matter, §1, §2, §13 updated; `params.timeline` re-checked against `filmkit_rules_selftest.structure_problems` and `kit_violations` on 931c4cd (both empty) |
| P-10 | should-fix | §7 TV-19 under `fit` and `fixed`; §10.2 variant S2 `dur: 6.0` → `TV-19#L4` |
| U-1 | user ruling | kept as the PSM default (§4.3); asked in §0 question 3 |
| U-2 | user ruling | asked in §0 question 4; answered 2026-10-11 (v1.2): Haiku only for collection-type mechanical tasks with a hard gate, as the global dispatch rule; component fixed-content writing gets no Haiku (design v4.5 D-T12) |

## §15 使用者裁決紀錄與本 PSM 的模型決定

- 照錄不改：D-T1～D-T4、D-T8、D-T11～D-T15、D-T17、D-T19（全片尾靜音，Z-2 還原）、D-T20、D-T22；2026-10-10 W30 片尾停留 1.5–2.5 s（D-T23 的依據）；2026-10-10 Haiku 不用於影片製作；2026-10-11 補充：與全域派工規則一致，Haiku 只用於蒐集、盤點這類有硬驗收閘的機械任務，元件固定內容撰寫不派 Haiku（§0 第 4 題）。
- 本 PSM 的模型決定（皆可逆，記在本文 `PSM decision` 與 process ledger）：分支從 main 9def87b 開、驗證後 rebase 到 931c4cd；正式片放 `films/<片名>/`；A/B 掛載改 arm 層（Z-1，見 §0 第 2 題）；`dur` 的錨點寫法＝「在這個錨點結束」；片段角色五個值；產品片的定義；旁白長度估算公式（只供虛線預覽）；格點取整採四捨五入加極小餘量；元件證據狀態另存 `evidence.json`；片段程式只能用字面字串呼叫元件；旁白文字也要帶出處；TV-19 補「旁白延伸進片尾」為擋件；新增 `tl.py mark` 與 `illegal_transition`；鎖的程式複製一份而不引用 filmkit 內部；SEM-4 的 ±0.15 s 寫在程式常數（不放規則檔，讓 arm 內也能檢查）；`compile --rebase` 只改狀態、不寫版本資料夾；`timeline.html` 宣告為 `dashboard` 類頁面。
- 已裁決（2026-10-11，v1.2）：§0 的四題，答案寫在各題下方；另裁定 `films/*/build/questions.md` 進 git。D-T9（暫定門檻與嚴重度）照設計等第一支 DIT 片之後。

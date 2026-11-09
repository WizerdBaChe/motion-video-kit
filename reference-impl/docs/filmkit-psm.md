---
layer: PSM (build spec)
audience: builder (an implementing session); §0 and §14 are for the user
version: v1.3 (2026-10-09)
design: docs/filmkit-design.md v4.4
verification: v1 -> verification_filmkit-psm-v1_2026-10-09.md (pass-with-fixes, P-1..P-25); v1.1 -> verification_filmkit-psm-v1.1_2026-10-09.md (fail, 1 BLOCK, Q-1..Q-20); v1.2 -> verification_filmkit-psm-v1.2_2026-10-09.md (pass-with-fixes, 0 BLOCK, R-1..R-13); v1.3 settles R-1..R-13 (table §13.4); user ruling 2026-10-09: no further re-verification, M0's controls verify v1.3
host baseline: tools/run_arm.py @ 00acb20 (branch feat/r22-haiku; not yet on main at the time of writing)
status: written; filmkit not built
---

# filmkit PSM: build spec

This is the platform-specific build spec for filmkit. The design (`docs/filmkit-design.md` v4.4, cited below as "design §n") owns the WHY, the business rules (BR-n), the invariants (FK-INV-n), the check rows (FK-R-n), the state machines and the decisions (D-n). This document owns the HOW: files, function signatures, schemas, error paths, rollback and test mapping. Where this spec settles something the design left open, the line says `PSM decision` and names the design item it closes. Where it would contradict the design, it does not: the design wins and the builder stops and reports. (v1 had five decisions that changed design text; design v4.2 now carries them, P-10.)

Language: English by contract (build spec). §0 and §14 are in Traditional Chinese because the user rules on them.

## §0 給使用者的摘要與待裁決事項

- 這份是 filmkit 的施工規格 v1.3，對應設計 v4.4 的 M0–M3。驗證三輪：v1 列 25 項（P-n）、v1.1 列 20 項（Q-n，1 個擋件）、v1.2 通過但附 13 項（R-n，0 擋件）；v1.3 全部處理，對照表在 §13.3、§13.4。你裁決 v1.3 不再重驗，由 M0 施工卡的正反控制來驗。
- v1.3 主要修正：重出片指令改由紀錄裡的欄位重組、路徑一律用 `/`（Git Bash 會吃掉沒加引號的 `\`）；外來檔的指令輸出一律是佔位 `<new-out>`；字型探針加進擷取介面；片尾規則分清楚畫面比視訊終點、聲音比片長。
- v1.2 最重要的修正：字型指紋改成**字族層級**判定。v1.1 會把 `Arial` 這種只有英文字形的字型，在純中文的字上誤報成「被替換」；現在只要中文或英文任一種量得到就算存在（Q-1）。另一個我替你定的（D30，可逆）：`render.py -o` 的輸出必須直接放在頁面資料夾，不能放子資料夾；草稿請用另一個頁面資料夾。
- 你 2026-10-09 的裁決已寫進設計（D25–D28）與本規格：
  - **P-1 片尾**：目標是片子最後一段畫面靜止、聲音安靜（多出來你自己剪）。掃描會把「持續到片尾」的靜止／黑場／靜音當成完整區間量出來（§6.5、SG-15）。
  - **P-4 字型**：不再比對字型名稱（Windows 回傳「微軟正黑體」這種在地化名稱，會誤報），改成「指紋」：同一個字族配三種後備字型各量一次，和一個不存在的字族比。中文和英文各量一次（§6.3）。正式片另外有一條交付規則：頁面附上字型檔（建議 Noto Sans TC：本機已裝、授權開放；Linux 雲端常見的是同一家族的 Noto Sans CJK TC，名稱不同，所以要附檔而不是靠系統字型）。這條只對正式片（R5），不進 kit、不進受測 arm（D12）。
  - **P-2 重出片指令**：格式類擋件列帶一行可照做的 `render.py` 指令，`check.md` 第一段照印（§4.3）。
  - **P-7**：FK-R-15 留在 M2（§9）。
  - **P-5 faststart（你交給我評估）**：在編碼那一步就由設定檔帶 `+faststart`，有音軌時 mux 再帶一次。理由：無音軌的片（例如 M0 要比對的 r20 A3）也必須能被網頁直接串流，而這樣只有一個來源決定這個旗標（D29）。
- **待你裁決（都不擋 M0）**：
  1. D18：M2 語料校準後，FK-R-7、8、10、12 的門檻與是否升為「擋件」，以及 FK-R-14 例外比例要不要設門檻。
  2. r22a／r22b 若在 M1 上線後續跑：保護機制會讓它們拒跑，直到 round 檔明寫 `"export_kit": false`（建議：續跑時寫 false，維持原條件）。要不要另做一個命令列旗標，我判斷不需要。
  3. （已裁決 2026-10-09：v1.3 不再重驗。）
- M1 前置條件不變：`feat/r22-haiku` 要先合進 main。

## §1 Scope and order of work

Build order is fixed: M0 → M1 → M2 → M3 (design §10). Each milestone is one work card (§9) with its own branch, acceptance gates and commit set. A later milestone never edits an earlier milestone's acceptance evidence; it adds its own.

Degradation order (design §10, D24): cut M3 first, then FK-R-11. Never cut: atomic publish, format rows, record-first, five-line output, `check.md`, FK-R-12.

Out of scope (design §1.4): quality judgement, design advice, auto-fix, changing the author's page or audio, replacing lab instruments, `duck` and `convert` (SKELETON).

Off-limits while building: `rounds/r22a-*`, `rounds/r22b-*`, `experiments/r22-*` and their workspaces while that test runs; every finished `experiments/<round>/` folder (read-only evidence).

## §2 Platform pins

| Item | Pinned | Source |
|---|---|---|
| OS | Windows 11, NTFS | design §2.5 |
| Python | 3.12.7, stdlib only + Playwright | D17 |
| Playwright (Python) | 1.62.0 with its bundled Chromium; version read via `importlib.metadata.version("playwright")` (the module has no `__version__`) | design §2.5, P-25 probe |
| ffmpeg / ffprobe | 8.1 (gyan.dev essentials), filters `blackdetect`, `freezedetect`, `silencedetect`, `astats`, `ebur128`, `loudnorm`, `volumedetect` | design §2.5, SG-14 |
| Encoder | `libx264`, `aac` | D7 |

`render.json` records the actual versions (`env`, §4.2). A different version is recorded, not an error; §11 says which probes must then be re-run.

SG-1 … SG-15 (design §11) are platform-conditional except SG-4 (host behaviour of `run_arm.py`) and SG-5 (who writes the plan), which are design-level and are covered by selftests, not probes. M0 re-runs the probes for SG-1, SG-2, SG-6, SG-7, SG-9, SG-10, SG-12, SG-13, SG-14 and SG-15 on the pinned versions and writes `measurements/filmkit-calibration/sg-probes-<date>.md` (one row per SG: probe, result, still holds yes/no). The verifier's probe scripts (report §7) may be reused but must be re-run on the builder's machine. SG-3 and SG-8 are re-run in M2. A probe that no longer holds stops the milestone and goes back to the design.

## §3 File layout

### 3.1 Kit (copied into arm workspaces; self-contained, FK-INV-7)

```
tools/filmkit/
  README.md                 English, neutral usage only; first lines = upgrade condition (design §3.1)
  MANIFEST.txt              kit file list; kit hash input (FK-INV-15)
  profiles.json             format fields, detection thresholds, timeouts, caps; no targets (FK-INV-12)
  film_plan.schema.json     JSON Schema (draft 2020-12) for film_plan.json; documentation + fixture agreement
  render.py                 CLI entry: RenderJob
  check.py                  CLI entry: CheckRun
  transform.py              CLI entry: Transform (M3)
  selftest.py               kit selftest; fixtures generated into a temp dir at run time
  _fk/__init__.py
  _fk/common.py             exit codes, FilmkitError hierarchy, atomic JSON write with retry, sha256 helpers
  _fk/kinds.py              kind -> English message/hint templates for Failed:/Notes: (P-11)
  _fk/types.py              in-memory dataclasses of §4.10
  _fk/manifest.py           kit hash
  _fk/profile.py            profile loading, resolve_profile()
  _fk/spec.py               ExpectedSpec, N, plan validation (shared by all entries)
  _fk/guard.py              start decision table, OS lock, ownership, input hashes, D20
  _fk/store.py              RecordStore: atomic record file with pending/promote (render.json, transform.json)
  _fk/record.py             render-record semantics on top of RecordStore (sole writer of render.json)
  _fk/capture.py            CaptureBackend protocol + PlaywrightBackend + font fingerprint probe
  _fk/encode.py             frame pipe -> video partial
  _fk/mux.py                video partial + author audio -> publish partial
  _fk/verify.py             ffprobe check of a partial, publish sequence
  _fk/summary.py            the five stdout lines and the exit code
  _fk/probe.py              ProbeFacts via ffprobe
  _fk/scan.py               one decode pass: black / frozen / silent / astats / ebur128
  _fk/judge.py              row table (design §7.5), generic range comparator
  _fk/rerun.py              re-render command for format FAIL rows (D11, D28)
  _fk/report.py             check.json, check.md (zh), events projection
  _fk/messages_zh.py        message_key -> zh sentence templates (report's table)
  _fk/sheet.py              contact sheet
  _fk/checkrun.py           CheckRun orchestration (check.py; in-process from render)
  _fk/transform_core.py     Transform orchestration, operation table (M3)
  _fk/ops/__init__.py       OPERATIONS = {"normalize": normalize}
  _fk/ops/normalize.py      add_arguments / validate / build_filter (M3)
```

`transform.py`, `transform_core.py`, `ops/*` are created in M3 and are absent from `MANIFEST.txt` before then. Every other file is created in M0; M2 rows are added inside the same files.

### 3.2 Lab-side files (never copied into a workspace)

| Path | Purpose | Milestone |
|---|---|---|
| `tools/filmkit_rules.json` | design rules, `film_types`, other layers' `params`, (M3) loudness targets; outside the kit (D12). PSM decision (P-21b): the DATA file is created in M0 with `end_hold` and `film_types`, so the timeline layer (TL-0, TL-1) can read the shared key before filmkit evaluates it; filmkit evaluates rules from M2 | M0 (data), M2 (evaluated) |
| `tools/filmkit_rules_selftest.py` | FK-INV-12 scan of the kit against the rules file (from M0); FK-INV-10 scan of rule sentences; `film_types` equals the slug list derived from `film-types.md` headings (R-11; skipped with a note when the skill file is absent); FK-R-16/17 controls on the real rules file (M2, M3) | M0, M2, M3 |
| `tools/filmkit_corpus.py` | runs `check.py` over every readable arm `final.mp4`, writes the distribution and a sampling list | M2 |
| `measurements/filmkit-calibration/` | SG probe notes, M0 side-by-side, corpus distribution and sample judgements, per-milestone evidence notes | M0+ |
| `tools/run_arm.py` | R2 changes | M1 |

### 3.3 Per-render files (in the page folder, normally `build/`)

The output's parent folder must BE the page folder (D30, Q-8): `-o build/preview/x.mp4` for `build/index.html` → `spec_invalid` with the hint "render drafts from a copy of the page in another folder". So record, lock and check outputs always sit next to the output, and `copy_build()` (top level only) sees all of them.

| Path | Writer | Notes |
|---|---|---|
| `<out>` (e.g. `final.mp4`) | `verify.publish` by rename only | FK-INV-1 |
| `render.json` | `record` only (FK-INV-6) | one per folder (D20) |
| `check.json`, `check.md`, `sheet_1fps.png` or `<file>.check.*` | `report`, `sheet` | names per §5.6 |
| `.filmkit/lock` | `guard` | OS byte lock on byte 0; no content |
| `.filmkit/lock.json` | `guard` | `{pid, proc_start, tool, run_id, started_at}`; diagnostics only (design §7.4 row 2, v4.2); written only after `CREATED`, never on `busy` or any `REJECTED` (Q-18) |
| `.filmkit/<out stem>.<run_id>.video.mp4` | `encode` | video-only partial |
| `.filmkit/<out name>.<run_id>.partial` | `mux`, or the video partial renamed when there is no audio | publish candidate |
| `.filmkit/frames/` | `capture` with `--keep-frames` | PNG per frame |
| `.filmkit/*.tmp` | `common.write_*_atomic` | temp file for every atomic write, including `check.*` and the sheet (Q-9); same volume as the target, so `os.replace` stays atomic; never in the page folder's top level, so `copy_build()` never copies one. `guard` deletes stale `*.tmp` on `CREATED` |

Partials carry `run_id` (P-25d): a hard-killed run's orphan ffmpeg cannot collide with the next run. On entering `CREATED`, `guard` deletes partials of other run_ids under `.filmkit/` (retry as §6.0; a still-locked orphan file is left and noted, it does not fail the run).

## §4 Data schemas

All JSON files are UTF-8 and written by `common.write_json_atomic()` (§6.0). Author-written files (`film_plan.json`, rules file) reject unknown keys; tool-written files of a known `schema_version` ignore unknown keys with a note.

### 4.1 `film_plan.json` (author-written, optional; `film_plan.schema.json`)

```json
{
  "schema_version": 1,
  "expected": {"duration_s": 30.0, "size": "1280x720", "fps": 30, "audio_expected": true},
  "film_type": "product-tour",
  "sections": [{"id": "S1", "t0": 0.0, "t1": 4.5}],
  "holds":    [{"t0": 26.4, "t1": 30.0, "why": "end card"}],
  "blacks":   [{"t0": 0.0,  "t1": 0.3,  "why": "fade-in from black"}],
  "silences": [{"t0": 0.0,  "t1": 1.0,  "why": "cold open"}],
  "narration_lines": [{"id": "L1", "t0": 1.2, "t1": 3.4}]
}
```

| Field | Type / range | Read from |
|---|---|---|
| `schema_version` | integer, must be 1 | M0 |
| `expected.duration_s` | number > 0, a whole number of frames (§5.2) | M0 |
| `expected.size` | `^[0-9]+x[0-9]+$`, both even, both >= 16 | M0 |
| `expected.fps` | integer 1–120 | M0 |
| `expected.audio_expected` | boolean | M0 |
| `film_type` | `^[a-z0-9-]{1,40}$`, must be in the rules file's `film_types` when a rules file is given (else not checked) | M2 |
| `sections[]` | `id` string, `t0` < `t1`, numbers >= 0 | M2 (carried for reviewers) |
| `holds[]`, `blacks[]`, `silences[]` | `t0` < `t1`, numbers >= 0, `why` non-empty (FK-INV-8) | M2 |
| `narration_lines[]` | `id` string, `t0` < `t1` | M2 (FK-R-15, D27); M3 adds FK-R-9's line branch |

All top-level keys except `schema_version` are optional. M0 validates the whole file strictly even though it reads only `expected`: unknown keys and zero-length intervals are `spec_invalid` in `render.py` and `plan.mode: unusable` in `check.py`. The timeline layer generates this file (its §6.9, updated with this rule); a schema change bumps `schema_version` and updates that section in the same change.

Validation: `spec.validate_plan(obj) -> list[str]` (empty = valid), stdlib only. `selftest.py` asserts agreement with `film_plan.schema.json` on 6 valid and 10 invalid fixtures (missing `why`, `t0 >= t1`, odd size, unknown key, wrong `schema_version`, non-integer frame count, ...). Intervals beyond the film length are not a schema error; FK-R-15 reports them.

### 4.2 `render.json` (tool-written; `record` is the sole writer)

```json
{
  "schema_version": 1,
  "generator": "filmkit",
  "run_id": "20261009T101500-7f3a",
  "pid": 12345, "proc_start": "2026-10-09T10:15:00.123+08:00",
  "status": "running|done|failed|interrupted",
  "phase": "load|capture|encode|mux|verify|checking|complete",
  "kind": null, "message": null, "hint": null,
  "notes": [],
  "output": "final.mp4",
  "page": "index.html",
  "audio": "mix.wav",
  "cli": ["render.py", "build/index.html", "-o", "build/final.mp4", "--duration", "30", "--size", "1280x720"],
  "expected": {"duration_s": 30.0, "n_frames": 900, "width": 1280, "height": 720, "fps": 30, "audio_expected": true,
               "source": {"duration_s": "flag", "size": "flag", "fps": "profile", "audio_expected": "flag"}},
  "profile": {"name": "lab-round", "video_args": ["..."], "audio_args": ["..."], "container_args": ["-movflags", "+faststart"]},
  "inputs": [{"path": "index.html", "sha256": "..."}, {"path": "fonts/NotoSansTC.ttf", "sha256": "..."}],
  "inputs_sha256": "...",
  "kit_hash": "...",
  "env": {"python": "3.12.7", "playwright": "1.62.0", "chromium": "...", "ffmpeg": "8.1", "os": "..."},
  "load_report": {"ready_shape": "promise|true|flag|absent", "fonts": [], "font_families": [],
                  "local_files": [], "blocked_requests": [], "console": [], "console_truncated": false},
  "frames": {"n": 900, "t": ["0", "1/30"], "sha256": ["..."], "live_animations": [0],
             "resample": [{"i": 417, "match": true}]},
  "timings_s": {"load": 1.2, "capture": 80.4, "encode_close": 3.1, "mux": 0.8, "verify": 0.3, "check": 4.0},
  "per_frame_ms": 89.3,
  "progress": {"frames_done": 450, "eta_s": 41},
  "pending_publish": null,
  "last_success": {"output": {"name": "final.mp4", "sha256": "...", "bytes": 12345678},
                   "page": "index.html", "audio": "mix.wav", "plan": "film_plan.json", "rules": "<lab>/tools/filmkit_rules.json",
                   "film_type": "product-tour", "profile": "lab-round", "inputs": [], "inputs_sha256": "...",
                   "kit_hash": "...", "run_id": "...", "load_report": {}, "cli": [], "expected": {},
                   "frames": {"n": 900, "live_animations_max": 0, "live_animations": [0], "resample": []}}
}
```

- `last_success` (Q-3) is a full snapshot of the run that produced the published file: everything `check.py` reads about "how this file was made" (`page`, `audio`, `inputs`, `inputs_sha256`, `kit_hash`, `load_report`, `cli`, `expected`, `frames`) comes from `last_success`, never from the top-level fields, which describe the latest attempt and may belong to a failed rerun. `promote()` copies them from the top level in one write. Paths: `page`, `audio`, `plan` relative to the page folder (`audio`/`plan` absolute with `/` when outside it), `rules` absolute with `/`; `film_type`, `profile` as given. These structured fields (not `cli`) are what `rerun` rebuilds from (R-1).

- `inputs` (Y-9, P-8) = the page file + every entry of `load_report.local_files` + the audio file; paths relative to the page folder with `/` separators, sorted by their UTF-8 bytes (Q-20a); the page file is recorded by the route handler like any other local file, and the list is de-duplicated before sorting (R-10a). Change during capture (R-10b): the page and audio are hashed at `LOADING` and all inputs again at the end of `CAPTURING`; any difference adds the note "inputs changed while rendering" and the record keeps the END hashes, so the next `owner_state` reads `STALE` only if they change again; the note tells the user to rerun. `local_files` is every `file://` request the route handler allowed, accumulated through load AND capture (a page that loads an image at frame 50 lists it). `inputs_sha256` = sha256 over the lines `path\0sha256\n` in order.
- Write timing (P-8): `inputs`, `inputs_sha256`, `frames.n`, `frames.t`, `frames.sha256` are written when `CAPTURING` ends, before `VERIFYING`. `pending_publish` is `{sha256, bytes}`. So everything `reconcile()` needs to promote a pending file (`output`, `inputs_sha256`, `kit_hash`, `run_id`, `load_report`, `cli`) is in the record before the rename.
- `frames.t[i]` is the exact time as a fraction string (`"i/fps"` reduced) actually passed to `seek()` (FK-INV-3 control, P-12). `frames.live_animations[i]` from M2.
- `cli` is the argv as given (paths as the caller wrote them), kept for humans; `rerun` (§4.3) does NOT parse it (R-1).
- Caps (P-25a): `console` keeps the first 200 entries, each truncated to 500 characters, then sets `console_truncated: true`; `notes` keeps 50.
- `last_success.load_report` is the report of the run that produced the published file; FK-R-6 reads it (§7.2), FK-R-11/12 read `last_success.frames`.

### 4.3 `check.json` (tool-written; `report` is the writer)

```json
{
  "schema_version": 1,
  "generator": "filmkit",
  "file": {"name": "final.mp4", "sha256": "...", "bytes": 12345678},
  "render_record": {"name": "render.json", "sha256": "..."},
  "plan": {"name": "film_plan.json", "mode": "full|exemptions_only|absent|unusable", "sha256": "..."},
  "expected": {"duration_s": 30.0, "n_frames": 900, "width": 1280, "height": 720, "fps": 30,
               "audio_expected": true, "film_type": null},
  "profile": "lab-round",
  "kit_hash": "...",
  "rules": {"name": "filmkit_rules.json", "sha256": "..."},
  "outputs": {"json": "lab.check.json", "md": "lab.check.md", "sheet": "lab.sheet_1fps.png"},
  "probe": {},
  "rows": [
    {"id": "FK-R-3", "name": "frame_geometry", "category": "format", "verdict": "FAIL", "severity": "blocking",
     "bucket": "blocking", "t0": null, "t1": null, "t": null, "where": "file",
     "measured": "1279x720", "expected": "1280x720", "basis": "expected value from flag --size",
     "provisional": false, "reason": null, "unfinished": false,
     "rerun": "python -X utf8 <arms>/r30/A1/kit/filmkit/render.py <arms>/r30/A1/build/index.html -o <arms>/r30/A1/build/final.mp4 --duration 30 --size 1280x720 --fps 30 --profile lab-round",
     "message_key": "frame_geometry.size_mismatch", "milestone": "M0"}
  ],
  "events": [{"kind": "span", "start": 26.4, "end": 30.0, "t": 28.2, "event": "frozen_interval", "row": "FK-R-8#1"}],
  "exemptions": [{"type": "hold", "t0": 26.4, "t1": 30.0, "why": "end card", "exempted_rows": ["FK-R-8#1"]}],
  "summary": {"blocking": 1, "look": 2, "undetermined": 1, "confirmed": 9, "look_without_exemptions": 3,
              "incomplete": false, "internal_error": null},
  "exit_code": 2
}
```

- Row ids: `FK-R-n`, repeated interval rows `FK-R-n#k`, sub-rows with their own identity `FK-R-n#<name>` (e.g. `FK-R-5#length`, P-18).
- `where` ∈ {`picture`, `audio`, `file`}. Whole-file rows (design §5.7 v4.2): `where: "file"`, `t: null`; when the bucket is `look`, `t0 = 0` and `t1 = <measured duration>` (null when unknown); otherwise `t0 = t1 = null`. Whole-file rows never enter `events`.
- `unfinished` (P-18): true when the row is UNDET because the check did not finish (scan failure, `--check-timeout`, Ctrl-C, an exception after publish). `summary.incomplete = any(unfinished) or internal_error is not None` (Q-5); `internal_error` is the last line of a post-publish exception (`promote`, `finish`, report writing), else null. A UNDET for missing information (no expected value, no record, rule checks not built) has `unfinished: false` and does not set exit code 3.
- `rerun` (D11, D28, P-2, Q-4): on every `format` row with verdict FAIL, else null. Rules for `rerun.build(record, file, args, kit_dir)`:
  1. The record "describes" the checked file only when the file's sha256 equals `last_success.output.sha256` (after `reconcile`). Then the command is rebuilt from `last_success`'s structured fields, never parsed from a `cli` (whose relative paths depend on a cwd nobody recorded, R-1): `page`, `output.name`, `audio`, `plan` (resolved against the folder of the record), `rules`, `film_type`, `profile`, plus the expected values.
  2. Otherwise (no record, FOREIGN, or a derived file without a page) the base is the template `render.py <page> -o <new-out> --duration <S> --size <WxH>`. `<new-out>` is always a placeholder, never the checked file (that file is not filmkit's, so rendering onto it would be `REJECTED(output_foreign)`; R-3); the placeholder line says "the output must sit in the page's own folder (D30) and must not be this file".
  3. Expected values override the base where they differ (the expected values are the authority, not the bad file). An expected value the check does not know stays a placeholder (`<S>`, `<WxH>`); required flags are never dropped.
  4. FK-R-5 (audio missing or mono): the command carries `--audio <audio>` (the base's value, or the placeholder); the hint states that a rerun keeps the channel count of the given file.
  5. All paths are absolute and written with `/` separators (`Path.as_posix()`; Python, ffmpeg, PowerShell and cmd accept them, and Git Bash does not eat them as it eats unquoted backslashes, R-2); prefix `python -X utf8 <absolute path of the running kit>/render.py`.
  6. Quoting by `subprocess.list2cmdline` (double quotes only when an argument has a space; with `/` separators the result pastes into PowerShell and Git Bash alike).
  7. A file produced by `transform.py` (M3) gets `rerun: null`; the hint names the transform record instead.
  `check.md` section 1 prints it verbatim under the row, with one line naming any placeholders to fill (OQ-1: a template with explicit placeholders counts as followable).
- `outputs` (P-3): the three paths `check.py` actually wrote; `run_arm.py` reads them instead of assuming names.
- `summary.look_without_exemptions` is BR-6's second count (from M2; equals `look` before).

### 4.4 `profiles.json` (kit; FK-INV-12: no targets, no design rules)

```json
{
  "schema_version": 1,
  "profiles": {
    "lab-round": {
      "video": {"codec": "libx264", "crf": 16, "preset": "slow", "pix_fmt": "yuv420p", "faststart": true},
      "audio": {"codec": "aac", "bitrate": "192k", "channels": 2},
      "fps_default": 30,
      "timeouts_s": {"render": 3600, "ready": 30, "check": 600, "transform": 900},
      "progress_every_frames": 150,
      "resample_count": 0,
      "write_retry": {"attempts": 10, "step_s": 0.05},
      "sheet": {"columns": 10, "thumb_width": 192, "max_frames": 300},
      "thresholds": {
        "black":  {"min_duration_s": 2.0, "picture_ratio": 0.98, "pixel_threshold": 0.10, "calibrated": false},
        "freeze": {"noise": 0.001, "min_duration_s": 2.0, "calibrated": false},
        "silence": {"noise_db": -50, "min_duration_s": 2.0, "calibrated": false},
        "first_frame": {"max_luma_stddev": null, "min_diff_to_1s": null, "calibrated": false},
        "av_length_tolerance_s": 0.1,
        "duration_tolerance_frames": 1
      }
    }
  }
}
```

- D7 values. `delivery-web` is added in M3 with format fields only (D22).
- Thresholds are exploratory (design §13): black/freeze = ffmpeg defaults, silence −50 dB. `first_frame` values are set by the M2 synthetic controls, then the corpus calibration revisits all of them; D18 decides severity.
- `freeze` keys added after the first listing (the example above shows the M0 shape): `end_min_duration_s` 1.0 (D18, a still that runs to the end), `start_min_duration_s` 1.0 and `start_window_s` 5.0 (W33, a still that starts within `start_window_s` of frame 0 is kept down to `start_min_duration_s`; the window key is required for the head floor to apply at all) and `local_tile_median_max` 0.0005 (W32, §9.6); each is optional, an absent key switches its branch off, and `calibrated: false` stays. `freezedetect` runs at the smallest of the applicable floors.
- `resample_count` 0 in M0–M1; M2 sets 12.
- `av_length_tolerance_s` = 0.1 s (SG-9, PSM decision): used by `FK-R-5#length`.
- `sheet` (P-25b): one thumbnail per second up to `max_frames`; longer films sample evenly to `max_frames` and say so in the row's `measured`.
- Timeouts are defaults, not promises (design §3.5).
- `selftest.py` asserts no key matches `/target|lufs|true_?peak|platform/i` (Y-16(c)).

### 4.5 `tools/filmkit_rules.json` (lab-side; M0 data, M2 evaluated, M3 targets)

```json
{
  "schema_version": 1,
  "film_types": ["intro-ad", "hype-ad", "product-tour", "data-showreel", "narrated-explainer", "profile-reel", "music-video"],
  "rules": [
    {
      "id": "end_hold",
      "owner": "filmkit",
      "kind": "range",
      "film_types": null,
      "select": {"source": "frozen", "anchor": "end", "max_gap_s": 0.1},
      "range_s": [2.5, 3.5],
      "sentence_zh": "片尾畫面靜止 {measured} 秒（{t0}–{t1} 秒）。依據：{basis}",
      "missing_zh": "片尾沒有偵測到長於 {floor_s} 秒（偵測下限）的靜止。依據：{basis}",
      "basis": "片尾停留 1.5–2.5 秒（W30 你 2026-10-10 裁決；先前 r14、r17 為 2.5–3.5 秒）",
      "provisional": true,
      "review_when": "the end-hold ruling changes (design review-when)"
    }
  ],
  "params": {},
  "targets": {}
}
```

- Allowed top-level keys (P-19b): exactly `schema_version`, `film_types`, `rules`, `params`, `targets`.
- `film_types`: the vocabulary for `rules[].film_types`, `--film-type`, `film_plan.json.film_type`, round `expect.film_type`. Source (Q-10): the section headings of `~/.claude/skills/motion-video/references/film-types.md`, one slug per film type: `intro-ad` (§1a), `hype-ad` (§1b), `product-tour` (§1c), `data-showreel` (§2), `narrated-explainer` (§3), `profile-reel` (§4), `music-video` (§5). The list in the example above is illustrative only; the M0 data file uses these slugs. Do not scan `rounds/` for it (`tools/taxonomy.json` has no film-type axis, and some round files are off-limits). A new film type in the skill adds a slug in the same change. The timeline layer's own vocabulary, if different, is mapped in the timeline PSM.
- The kit implements one rule kind: `range` with selector `source` ∈ {`black`, `frozen`, `silent`}, `anchor` ∈ {`start`, `end`, `any`, `first`}, `max_gap_s`, `max_t0_s` (with `first` only). Rule ids, ranges, sentences, bases, provisional flags live only here (FK-INV-12).
- Evaluation scope (P-19a): filmkit evaluates only `owner == "filmkit"` entries. An owner-filmkit entry with a kind the kit does not implement → one UNDET row `FK-R-16#<id>` (`reason: "rule kind not supported by this kit: <kind>"`). Entries of other owners are never evaluated and produce no row.
- `params`: `{"<owner>": {...}}` for other layers' scalar settings (the timeline layer's free-clip share, narration-over-music gap, peak cap, `stock_devices`); filmkit never reads it.
- Provisional wording (P-19c): when `provisional: true`, `range_compare` appends `（暫定）` to the rendered sentence; `basis` strings therefore never contain the word themselves.
- `targets` (M3): `{"<name>": {"lufs": X, "true_peak": Y, "tolerance_lu": T, "source": "<official doc URL + date>", "review_when": "..."}}`, filled from official documents in M3. `tolerance_lu` is optional and taken from the source document (added in M3); a target without it gives an UNDET loudness comparison, while a true peak above the ceiling is still WARN/look.
- `anchor: end` reference point (R-7a): `black` and `frozen` intervals are compared with `video_end` (`n_frames / fps`), `silent` intervals with `film_end` (§6.5). `max_gap_s` is the largest allowed `reference − t1`. `anchor: start`: the largest allowed `t0` (the reference is 0). `anchor: first` (W33, user ruling 2026-10-10): of the intervals whose `t0` is at most `max_t0_s`, the single earliest by `t0`; none → nothing matched. `max_t0_s` is required with `first` (a number ≥ 0, not a bool); without it the rule is one UNDET row ("rule selector anchor first needs max_t0_s ..."), nothing is guessed. The kit knows the key only; the value lives in the rules file.
- `missing_ok` (W33, additive): optional boolean on a rule, default false. When true and the selector matches nothing, the row is `PASS` (bucket confirmed) with `measured: "not detected"` and the rule's `missing_zh` sentence, instead of `WARN` / look. It never excuses an interval that matched and lies outside the range. Only a literal `true` counts. `filmkit_rules_selftest.py` requires a boolean when the key is present.
- Sentence placeholders: `{measured}`, `{t0}`, `{t1}`, `{basis}`, and `{floor_s}` = the selector source's `min_duration_s` from the active profile (R-7b); `range_compare` receives the profile's thresholds for this. For `source: frozen` the floor is the end floor (`frozen_end`) with `anchor: end` and the head floor (`frozen_start`) with `anchor: start` or `first` (W33); `frozen_start` exists only when the profile has `freeze.start_window_s`, otherwise the general floor is named.
- `head_hold` (W33): second entry of the file, `select {source: frozen, anchor: first, max_t0_s: 5.0}`, `range_s [0, 1.5]`, `missing_ok: true`; the timeline layer does not read it. It measures the first still that starts within the first 5 s (user ruling 2026-10-10, replacing the first pass's frame-0 anchor), so W30 E14 (3.93–6.03 s, 2.10 s) is measured and reads WARN; a still that starts after 5 s is not a head hold and stays a plain FK-R-8 row. The 5.0 in the rules file and the profile's `freeze.start_window_s` 5.0 are two numbers kept equal by hand: the window decides which short (1.0–2.0 s) stills are detected at all, the rule's `max_t0_s` decides which of the detected ones is the head.
- `id` `end_hold` is the key the timeline layer's TV-7 reads (D-T18). Its selector closes the open-at-end interval (§6.5), so a film that ends still and silent (D25) measures correctly.
- `check_rules_hash` = sha256 of the file bytes.
- Because the FK-INV-12 scan compares the whole kit against this file's ids and sentences, no kit file (README included) may quote a rule's `basis` or sentence (Q-20d); the README describes the rule mechanism, never a rule.

### 4.6 `<out>.transform.json` (M3; written through `RecordStore`)

```json
{
  "schema_version": 1, "generator": "filmkit",
  "op": "normalize", "params": {"target_lufs": "<given>", "true_peak": "<given>", "from_rules": null},
  "input": {"name": "final.mp4", "sha256": "..."}, "input_render_record_sha256": "...",
  "run_id": "...", "status": "running|done|failed|interrupted", "kind": null, "message": null, "hint": null,
  "pending_publish": null,
  "last_success": {"output": {"name": "final.norm.mp4", "sha256": "...", "bytes": 0},
                   "inputs": [{"path": "final.mp4", "sha256": "..."}], "inputs_sha256": "..."},
  "kit_hash": "...", "env": {}
}
```

`last_success.inputs` holds the one source file, path relative to the folder of `<out>`, hashed as in §4.2; so `current_inputs()` and `owner_state` rows 3–4 work on both record kinds (R-8).

### 4.7 `MANIFEST.txt` and the kit hash (FK-INV-15)

- One path per line, relative to `tools/filmkit/`, forward slashes, UTF-8, LF, no blank lines, no comments; kept sorted; lists itself.
- `kit_hash = sha256( concat over lines of: utf8(path) + b"\0" + file_bytes + b"\n" )`, hex. The repo pins `eol=lf`; the mount copies bytes.
- Ignored for completeness: `__pycache__/`, `*.pyc`. Any other unlisted file under `tools/filmkit/` fails `selftest.py`.

### 4.8 `run.json` additions (R2; existing fields and the `status` vocabulary unchanged, D14)

| Field | Value |
|---|---|
| `export_kit` | bool (the round's value) |
| `kit_hash` | mounted kit hash, or null when not mounted |
| `check_kit_hash` | lab kit hash at check time |
| `check_rules_hash` | sha256 of `tools/filmkit_rules.json` when `--rules` was passed (M2 on), else null |
| `check_summary` | `{status: "ok"\|"error"\|"skipped", reason, exit_code, blocking, look, undetermined, look_without_exemptions, blocking_rows: [ids with bucket == "blocking"], outputs: {json, md, sheet}}` (P-24c, P-3) |
| `kit_source_reads` | `{calls: [{tool, target}], instrument_limits: "<text of §8.3 blind spots>"}` (Y-22, P-16) |

### 4.9 `experiments/<round>/kit_hash.txt` (R2)

Tab-separated `hash<TAB>first_arm<TAB>reason`; the first line's reason is `first`. Comparison is against the LAST line, done before any workspace exists (§8.2, P-15). A changed hash without `kit_change_reason` → refuse; with it → the new line is appended after that arm's workspace is created.

### 4.10 In-memory types (P-11; `_fk/types.py`, frozen dataclasses unless noted)

| Type | Fields |
|---|---|
| `ExpectedSpec` | `duration_s`, `n_frames`, `width`, `height`, `fps`, `audio_expected`, `film_type`, `source: dict[str,str]` |
| `Decision` | `result: "REJECTED"\|"CREATED"`, `kind`, `message`, `hint`, `notes: list[str]`, `previous: dict\|None` (reconciled record) |
| `LoadReport` (mutable during capture) | `ready_shape`, `fonts: list[FontLoad]`, `font_families: list[FamilyCheck]`, `local_files: list[str]`, `blocked_requests: list[str]`, `console: list[str]`, `console_truncated: bool` |
| `FontLoad` | `family`, `src`, `status: "loaded"\|"error"` |
| `FamilyCheck` | `family`, `result: "present"\|"substituted"\|"undetermined"` (family level, Q-1), `decided_by: "latin"\|"cjk"\|None` (the script whose probe decided `present`, or None), `per_script: dict[str, str]` (each script's own result), `lists: dict[str, dict[str, list[str]]]`, `baselines: dict[str, dict[str, list[str]]]`, `sampled_at: list[str]` (Q-7) |
| `RenderArgs` | the parsed `render.py` flags of §5.1 as typed fields (`page`, `out`, `duration_s`, `size`, `fps`, `audio`, `audio_expected`, `plan`, `profile`, `rules`, `film_type`, `timeout_s`, `ready_timeout_s`, `check_timeout_s`, `keep_frames`, `json_out`) plus `argv: list[str]` |
| `ReportMeta` | `file: {name, sha256, bytes}`, `render_record`, `plan`, `expected`, `profile`, `kit_hash`, `rules`, `probe`, `events`, `exemptions`, `internal_error` — the non-row fields of §4.3 |
| `CheckSummary` | the §4.3 `summary` fields |
| `RunEvent` | `state`, `at` (ISO time), `kind`, `message`, `hint`, `progress` |
| `RunSummary` | `final_state`, `kind`, `hint`, `n_frames`, `duration_s`, `width`, `height`, `video_codec`, `pix_fmt`, `audio_desc`, `steps: list[(name, ok)]`, `out_path`, `published: bool`. For standalone `check.py` (no render), `final_state = "CHECKED"`, `steps = []`, and the file fields come from `ProbeFacts` (Q-6f) |
| `ProfileArgs` | `name`, `video_args: list[str]`, `audio_args: list[str]`, `container_args: list[str]` (incl. `-movflags +faststart` when the profile says so); all four go to `render.json.profile` |
| `ProbeFacts` | `readable`, `n_frames`, `video_duration_s`, `audio_duration_s`, `width`, `height`, `fps_avg`, `fps_r`, `fps_constant`, `video_codec`, `pix_fmt`, `faststart`, `audio: {codec, channels, sample_rate}\|None`, `error` |
| `Interval` | `t0`, `t1`, `open_at_end: bool` |
| `ScanEvents` | `black: list[Interval]`, `frozen: list[Interval]`, `silent: list[Interval]`, `audio_peak_db: float\|None` (`-inf` allowed), `loudness: {integrated_lufs, true_peak_db}\|None`, `error`, `finished: bool`, `frozen_local_motion: list[(t0, t1, median)]` (W32), `notes: list[str]` (W32; a skipped local-motion pass, appended to the check notes) |
| `CheckRow` | the §4.3 row fields |
| `OutputNames` | `json`, `md`, `sheet` (relative to the checked file's folder) |
| `SheetResult` | `ok`, `path`, `error` |
| `CheckResult` | `rows`, `summary: CheckSummary`, `exit_code`, `outputs: OutputNames`, `sheet: SheetResult` |
| Errors (`common.py`) | `FilmkitError(kind, message, hint)` base; `Busy`, `SpecInvalid`, `OutputForeign`, `EnvError`, `PageContract`, `AssetLoad`, `NotReady`, `PageRuntime`, `EncodeError`, `VerifyError`, `PublishError`, `Timeout`, `Interrupted`, `Internal` — each fixes its `kind`; `RecordWriteError` subclasses `Internal` (`kind == "internal"`) (Q-6e) |

## §5 Interfaces and CLI

### 5.1 Flags (authoritative list, design §4; FK-INV-16 compares `--help` to it)

`render.py <page> -o <out> --duration S --size WxH [--fps N] [--audio F] [--audio-expected yes|no] [--plan F] [--profile NAME] [--rules F [--target NAME]] [--film-type T] [--timeout S] [--ready-timeout S] [--check-timeout S] [--keep-frames] [--start S] [--gpu] [--json]` (`--start` added 2026-10-19: frame i shows page time S + i/fps, silent only; `docs/agent-review-kbt-design.md` M2. `--gpu` added 2026-10-24 for r36: Chromium launched with the Direct3D 11 high-performance adapter instead of the software renderer; `render.json` `env.gpu_requested` and `env.webgl_renderer` record the request and the adapter WebGL reported)

`check.py <file> [--duration S] [--size WxH] [--fps N] [--profile NAME] [--audio-expected yes|no] [--plan F] [--plan-exemptions-only] [--render-record F] [--mounted-kit-hash H|none] [--out-prefix P] [--rules F [--target NAME]] [--film-type T] [--check-timeout S] [--json]`

`transform.py <op> <input> --out F [op params] [--profile NAME] [--timeout S] [--json]`; op params are registered by the op module (§6.8); `normalize`: `--target-lufs X --true-peak Y`, or `--rules F --target NAME`.

- `--duration`/`--size` required for `render.py` unless `--plan` provides them (D15).
- `--audio` implies `--audio-expected yes`; together with `--audio-expected no` → `spec_invalid`.
- `--rules`/`--film-type` exist from M0; before M2 a given `--rules` is hashed and recorded and yields one UNDET row `FK-R-16` (`reason: "rule checks not built in this kit version"`, `unfinished: false`, P-18); `--film-type` is recorded only. Matches the timeline layer's staging.
- `--target NAME` (added in M3, `m3-evidence-2026-10-09.md`): names a `targets` entry of the `--rules` file for FK-R-17; without `--rules` → `spec_invalid`.
- `--mounted-kit-hash` (P-24b): flag absent ⇒ `None` (no comparison); literal `none` ⇒ the round did not mount a kit (FK-R-13 info when there is no record); a hex hash ⇒ compare.
- `--help` examples (Y-16(b)): three for `render.py`, one each for the others; target numbers are placeholders (`<LUFS>`, `<dBTP>`).
- argparse errors exit 1, printing the five lines with `Failed: spec_invalid` (subclassed `ArgumentParser.error()`).

### 5.2 Expected spec and frame count (one function for all entries)

```python
def build_expected_spec(flags, plan: dict | None, plan_mode: str, profile: dict) -> ExpectedSpec
def frame_count(duration_s: float, fps: int) -> int     # raises SpecInvalid
```

- Per field: flag > plan (only when `plan_mode == "full"`) > profile default (fps only) > absent. `--plan-exemptions-only` contributes nothing (D19). `Transform` builds its spec from the input's `ProbeFacts` (`source = "probe"`, Y-8).
- `N` (P-9): `N = round(duration_s * fps)` (Python `round`, half to even); if `abs(duration_s * fps - N) > 1e-6` → `SpecInvalid` with hint "duration must be a whole number of frames at <fps> fps (e.g. <N/fps> s)". `render.py` rejects; `check.py` treats the expected duration as unusable: FK-R-2 UNDET with that reason.

### 5.3 In-process check call

```python
@dataclass(frozen=True)
class CheckArgs:                    # exactly the check.py flag set
    file: Path; duration_s: float | None; size: tuple[int, int] | None; fps: int | None
    profile: str; audio_expected: bool | None; plan: Path | None; plan_exemptions_only: bool
    render_record: Path | None; mounted_kit_hash: str | None; out_prefix: str
    rules: Path | None; film_type: str | None; check_timeout_s: float; json_out: bool
    rows_subset: frozenset[str] | None = None   # Transform: format rows only

def check_run(args: CheckArgs, deadline: float) -> CheckResult
```

`check.py` parses flags into `CheckArgs`. `RenderJob` builds it from its own flags: `file = <out>`, expected values from its `ExpectedSpec`, `plan` in full mode, `render_record = <page dir>/render.json`, `mounted_kit_hash = None`, `out_prefix = ""`, plus its `--rules`, `--film-type`, `--profile`, `--check-timeout`. There is no second path from `spec` to `judge`.

### 5.4 Dependency direction (P-23)

`render.py`, `check.py`, `checkrun` and every module they import never import `transform_core` or `_fk/ops`. `transform.py → transform_core → ops`, and `transform_core → checkrun` (format rows only). `checkrun` imports nothing from `encode`, `mux`, `capture`, `record` or `transform_core`. `selftest.py` asserts this with an `ast` import graph, and exercises Transform only by running `transform.py` as a subprocess (so the selftest itself does not break the rule).

### 5.5 Five stdout lines, `--json`, exit codes

Lines exactly as design §5.2. `REJECTED(*)`, `FAILED(*)`, `INTERRUPTED` print `Failed: <kind> — <message>` (`interrupted` for `INTERRUPTED`), and `Notes:` carries the hint from `kinds.py` (P-11).

`--json`: one JSON document on stdout. `render.py`: final `render.json` content + `{"check": <check.json or null>, "exit_code": n}`; `check.py`: the `check.json` content; `transform.py`: `transform.json` + `exit_code`. When nothing was written (`REJECTED`, argparse error), the document is `{"status": "rejected", "kind", "message", "hint", "exit_code": 1}` (P-24a).

Exit codes (design §7.4): 1 no new verified output (or the check could not run) → 2 any blocking row → 3 `summary.incomplete` (any row with `unfinished: true`, or a post-publish internal error, Q-5) → 0. After publish step 3, no path returns 1 (P-20, §6.2). `transform.py` returns only 0 or 1 (design v4.2).

### 5.6 Check output names and ownership (Y-13, P-3, P-25c)

| Checked file | Output names |
|---|---|
| The file a same-folder `render.json` names as `last_success.output.name` (or as the top-level `output` while `pending_publish` is set; R-13b) | `<prefix>check.json`, `<prefix>check.md`, `<prefix>sheet_1fps.png` |
| Any other file | `<prefix><file name>.check.json`, `<prefix><file name>.check.md`, `<prefix><file name>.sheet_1fps.png` |

`check.json.outputs` records the names used; callers read them (P-3). Ownership is checked on all three before writing anything: the `.json` must parse with `"generator": "filmkit"`; the `.md` must start with the filmkit first line (`messages_zh.FIRST_LINE`); the `.png` must be listed as `outputs.sheet` in that same `.json`. Any of the three present and not owned → `Failed: output_foreign`, exit 1, nothing written. Owned files are replaced as a set.

## §6 Module contracts (signatures are binding; bodies are the builder's)

### 6.0 common: atomic write with retry (P-17)

```python
def write_json_atomic(path: Path, obj: dict, retry: dict) -> None   # raises RecordWriteError
```

Write `.filmkit/<name>.<pid>.tmp` (the `.filmkit/` folder beside the target, created if missing; Q-9), `fsync`, then `os.replace`; `write_bytes_atomic(path, data, retry)` does the same for `check.md` and the sheet. `check.py` on a file in a folder that has no `.filmkit/` (a folder filmkit never rendered into) does not create one: it writes `<target>.filmkit-tmp` beside the target and removes it right after the replace (R-12); the README says `check.py` writes only its three output files there; on `PermissionError` retry `retry["attempts"]` times every `retry["step_s"]` (a reader polling `render.json` briefly blocks the replace on NTFS, verifier probe). Still failing → `RecordWriteError`. The same retry wraps the rename in `publish` and partial cleanup.

### 6.1 guard (start decision, lock, ownership, input hashes, D20)

```python
class OutputLock:                                   # context manager
    def __init__(self, folder: Path, retry_s: float = 2.0, step_s: float = 0.05): ...
    def __enter__(self) -> "OutputLock": ...        # os.lseek(fd, 0, 0) then msvcrt.locking(fd, LK_NBLCK, 1); raises Busy after retry_s
    def __exit__(self, *exc) -> None: ...           # lseek 0, LK_UNLCK, close; lock file stays
def try_lock_free(folder: Path) -> bool             # acquire-and-release probe
def read_record(path: Path) -> tuple[dict | None, str | None]
def reconcile(record: dict, out_path: Path) -> dict  # pending -> last_success if file {sha256, bytes} match, else drop (Y-2)
def owner_state(record: dict | None, out_path: Path, current_inputs_sha: str | None, lock_held_by_other: bool) -> str
    # record MUST be the output of reconcile() (in memory; check.py never writes it back) (Q-3b)
    # current_inputs_sha is None  <=>  some file in last_success.inputs is missing (row 3) (Q-3d)
def current_inputs(page_dir: Path, last_success: dict) -> str | None   # rehash the paths listed in last_success.inputs
def start_decision(args: RenderArgs, page_dir: Path, out_path: Path) -> Decision   # design §7.4 table, top-down first match
def input_hashes(page_dir: Path, page: Path, load_report: LoadReport, audio: Path | None) -> tuple[list[dict], str]
def write_lock_info(folder: Path, run_id: str, tool: str) -> None   # lock.json; only after CREATED (Q-18)
```

`msvcrt.locking` locks at the CURRENT file position, so `lseek(fd, 0, 0)` precedes lock and unlock (verifier probe). Non-Windows: `fcntl.flock(fd, LOCK_EX | LOCK_NB)`, same retry; unprobed, so selftest reports the lock controls `skipped (non-Windows)` and the README says so.

`owner_state` truth table (design §7.4b v4.2, P-6), evaluated top-down:

| # | Condition | State |
|---|---|---|
| 1 | no file at `out_path` | `ABSENT` |
| 2 | no readable record, or file sha256 ≠ `last_success.output.sha256` and ≠ `pending_publish.sha256` | `FOREIGN` |
| 3 | any listed input file missing | `UNDET_INPUTS` (FK-R-13 UNDET, "input file not present", Y-9) |
| 4 | inputs sha (rehashed from `last_success.inputs`) ≠ `last_success.inputs_sha256` | `STALE` |
| 5 | `status ∈ {failed, interrupted}` | `STALE` |
| 6 | `status == running` and `lock_held_by_other` | `STALE` |
| 7 | otherwise (incl. `status == done` at any `phase`) | `CURRENT` |

A `running` record whose lock is free means the last run died; the start decision handles it (design §7.4 row 6); `check.py` treats it as row 7. A file owned only through `pending_publish` (killed between rename and `promote`) is CURRENT when its inputs match, because `reconcile()` has already promoted it in memory (Q-3b). Because rows 3–4 read `last_success.inputs`, a failed rerun with different flags (another `--audio`) does not change what the published file is compared against (Q-3a).

Lock interleavings (each a selftest control):

| # | Interleaving | Expected |
|---|---|---|
| L1 | A holds; B starts | B retries 2 s → `REJECTED(busy)` |
| L2 | A finishes normally; B starts | B acquires at once |
| L3 | A hard-killed (`Popen.kill()`), handle kept; B starts at once | B acquires within the retry window → `CREATED`, note "previous run interrupted" |
| L4 | A in `CHECKING` (lock held); lab probe `try_lock_free` | false → lab writes `skipped/render_in_progress` |
| L5 | `render.py` holds; `transform.py` on the same folder | `REJECTED(busy)` |
| L6 | lab probe acquires then releases; `render.py` starts right after | acquires |
| L7 | A hard-killed while its grandchild ffmpeg still runs | B acquires (the lock is not inherited; verifier probe) and its partial names differ by `run_id` |

### 6.2 store and record (P-20, P-23)

```python
class RecordStore:                                  # one JSON record file with publish bookkeeping
    def __init__(self, path: Path, retry: dict): ...
    def load(self) -> tuple[dict | None, str | None]
    def write(self, rec: dict) -> None              # write_json_atomic; RecordWriteError on failure
    def set_pending(self, sha256: str, nbytes: int) -> None
    def promote(self, out_meta: dict) -> None       # pending -> last_success, status done
    def reconcile(self, out_path: Path) -> dict

class Record:                                       # render.json semantics
    def __init__(self, store: RecordStore, previous: dict | None, kit_hash: str, env: dict, run_id: str): ...
    def start(self, expected: ExpectedSpec, profile: ProfileArgs, out_name: str, page: str, audio: str | None, cli: list[str]) -> None
    def event(self, ev: RunEvent) -> None           # RecordWriteError propagates
    def progress(self, frames_done: int, eta_s: float) -> None   # best effort; failure noted once
    def capture_done(self, inputs: list[dict], inputs_sha: str, frames: dict, load_report: LoadReport) -> None   # before VERIFYING (P-8)
    def set_pending(self, sha256: str, nbytes: int) -> None      # RecordWriteError -> do NOT rename
    def promote(self, out_meta: dict) -> None                    # step 3; status done, phase checking
    def finish(self, phase: str = "complete", notes: list[str] = ()) -> None
    def fail(self, kind: str, message: str, hint: str) -> None   # best effort; never raises
```

Exception policy (design §7.4 v4.2): before the rename, `RecordWriteError` or any unexpected exception → `FAILED(internal)` (rename never attempted after a failed `set_pending`). After `promote()` succeeded: any exception (in `checkrun`, `report`, `sheet`, or `finish`) → the run is `DONE`; rows not produced are UNDET with `unfinished: true`; `summary.internal_error` = the exception's last line (Q-5), which `Notes:` quotes; exit 2 if any blocking row exists, else 3 (via `summary.incomplete`); the record keeps `status: done` (a failed `finish` leaves `phase: checking`, which `owner_state` ignores). When the exception prevents writing `check.json` at all, the CLI still computes the exit code from the in-memory summary. `promote()` itself failing after the rename: the file is owned via `pending_publish` (design §7.4b), so the run reports `DONE` with note "record not finalised; next run reconciles", `internal_error` set, exit 3.

### 6.3 capture (SG-1, SG-2, SG-3, SG-6, SG-10, SG-12; FK-INV-3, FK-INV-9)

```python
class CaptureBackend(Protocol):
    def open(self, page_path: Path, width: int, height: int) -> None: ...
    def load(self, ready_timeout_s: float) -> LoadReport: ...
    def seek(self, t: Fraction) -> None: ...
    def snapshot(self) -> bytes: ...               # PNG
    def live_animations(self) -> int: ...
    def sample_font_families(self, moment: str) -> list[FamilyCheck]: ...   # item 3; capture unions the results into LoadReport.font_families (R-5a)
    def close(self) -> None: ...
```

`PlaywrightBackend`:
1. Viewport = expected size, `device_scale_factor = 1`. Route handler: allow `file://` URLs resolving inside the page folder (append to `local_files`), abort everything else and append to `blocked_requests` (FK-INV-9). `data:`, `blob:`, `about:` never reach the handler (verifier probe) and are allowed.
2. Load: wait for `load`; `document.fonts` entries each get `load()`; any `error` → `AssetLoad` (SG-10).
3. Font fingerprint (design SG-12 v4.3, D26, P-4, Q-1, Q-7, Q-16).
   - When: runs after steps 4 and 5 (so a page without `__setTime` fails `PageContract` before any sampling, R-5d), at `t = 0`, and again after the frames at 50 % and at the last frame are captured (before the next `seek`); the family set is the union of the three samples. `FamilyCheck.sampled_at` lists them; a family that appears only between samples is not seen. The coverage statement is a fixed sentence in `check.md` (FK-R-6's section, printed whenever `font_families` is non-empty), not in stdout `Notes:` (R-5c).
   - Families: the first family of every computed `font-family` on text nodes. Not probed: CSS generic families (`serif`, `sans-serif`, `monospace`, `cursive`, `fantasy`, `system-ui`, `ui-serif`, `ui-sans-serif`, `ui-monospace`, `ui-rounded`, `emoji`, `math`, `fangsong`) and the platform aliases `-apple-system`, `BlinkMacSystemFont`.
   - Probes: each family gets BOTH scripts (`latin`: `"Hamburgefonstiv 0123"`; `cjk`: `"永和九年歲在癸丑"`), regardless of which scripts its nodes contain (R-5b). Baselines: a sentinel family `"fk-missing-<run_id>"`; for each script three probes with `font-family: "<sentinel>", serif` / `sans-serif` / `monospace`. For each family F the same three probes with F first. Read `CSS.getPlatformFontsForNode`.
   - Probe elements live in an open shadow root (reached via CDP `DOM.getDocument` with `pierce: true`) of one host element appended to `document.documentElement` (so page selectors such as `body span` or `:nth-child` never match it); the host is removed after reading, and every style property is set with `style.setProperty(name, value, "important")`: first `all: initial` on the host (so inherited `font-synthesis`, `font-variant`, `text-transform` from `:root` do not reach the probes, R-13e), then `font-family`, `font-size: 16px`, `visibility:hidden`, `position:absolute`, `left:-10000px`. One `DOM.getDocument(depth: -1, pierce: true)` per sampling moment, not per probe. Never `display:none` (empty list). Force layout (`getBoundingClientRect`) and await two `requestAnimationFrame` before reading. FK-INV-14 holds because sampling happens outside the frame snapshot: the host is removed before the next `snapshot()`.
   - Per script: all three lists equal their baselines → `substituted`; any differs → `present`; the three baselines identical to each other → `undetermined`.
   - Family result (Q-1): any script `present` → `present` (`decided_by` = that script); else all decidable scripts `substituted` → `substituted`; else `undetermined`. So `Arial` in pure-Chinese text is `present` via its Latin probe; a CJK-only family is `present` via its CJK probe.
   - Names are never compared, so localized names ("微軟正黑體") do not matter. Known blind spots, listed in the README: (Q-16) an OS alias to another installed font (`Helvetica` → Arial on Windows) reads `present`; (R-9) on a machine where the Latin baselines coincide but the CJK ones do not, a Latin-only family in CJK text reads `substituted` (accepted: treating any undetermined script as undetermined would blind the check on Linux, where the CJK baselines usually coincide). D26's bundled-font rule is the real guard.
   - Results go to `LoadReport.font_families`; substituted families are named in `Notes:`; they never fail the load (FK-R-6 look).
4. `__ready`: Promise → await with timeout (rejection → `NotReady` quoting the reason); `true` → ready; `false` → poll 50 ms; absent → fonts loaded + two animation frames (D16).
5. No `window.__setTime` → `PageContract`.
6. `pageerror` → `PageRuntime` ("frame: loading" or index and t). A blocked or failed request during capture → `AssetLoad` with the frame index.
7. Frame i: `t = Fraction(i, fps)`; `seek(t)` passes `float(t)` to `__setTime` and records `str(t)` into `frames.t`; await two `requestAnimationFrame`; `snapshot()`; `live_animations()` counts `document.getAnimations()` with `playState == "running"` (paused animations driven by `currentTime` are legal, SG-3).
8. Resample (M2): after the last frame and `encoder.close_stdin()`, pick `resample_count` distinct indices with `random.Random(run_id)`, visit shuffled, re-snapshot, compare sha256, record `{i, match}`. An exception here kills ffmpeg first, then `PageRuntime`.

### 6.4 encode, mux, verify (Y-7(b), Y-18, D29, P-5, P-22)

```python
def resolve_profile(profile: dict, fps: int, has_audio: bool) -> ProfileArgs   # FK-INV-4; the only argv source
def open_encoder(args: ProfileArgs, width: int, height: int, fps: int, video_partial: Path) -> Encoder
class Encoder:
    def write(self, png: bytes) -> None            # BrokenPipe / exit -> EncodeError
    def close_stdin(self) -> None
    def wait(self, timeout_s: float) -> None       # nonzero -> EncodeError(last stderr lines)
    def kill(self) -> None
def mux(video_partial: Path, audio: Path, args: ProfileArgs, publish_partial: Path, timeout_s: float) -> None
def verify_partial(partial: Path, expected: ExpectedSpec, profile: dict) -> ProbeFacts   # raises VerifyError
class Publishable(Protocol):                       # Record and the transform record both implement it (Q-13)
    def set_pending(self, sha256: str, nbytes: int) -> None: ...
    def promote(self, out_meta: dict) -> None: ...
def publish(partial: Path, out_path: Path, record: Publishable) -> str   # set_pending -> os.replace (retry) -> promote
```

- Encoder: `-f image2pipe -c:v png -framerate <fps> -i -`, video args, then `container_args` = `-movflags +faststart` when `profile.video.faststart` (D29), `-f mp4`. So a film without audio is published with `moov` first (P-5).
- Sequence inside `CAPTURING` (Y-7(b), P-22): last frame → `close_stdin()` → resample (M2) → `wait()`; nonzero → `FAILED(encode)`. Then `MUXING` (audio) or `VERIFYING` (no audio; the video partial is renamed to the publish partial within `.filmkit/`).
- `mux`: `-i video_partial -i audio -map 0:v:0 -map 1:a:0 -c:v copy -c:a <codec> -b:a <bitrate> -movflags +faststart -f mp4`. Never `-af`, `-filter:a`, `-ac`, `-ar`, `-shortest`, `-t` (design §1.4). Mono stays mono (FK-R-5 then FAIL/blocking with a hint to supply stereo); sample rate unchanged; no trim or pad (`FK-R-5#length` reports the difference).
- `verify_partial`: frame count exactly `expected.n_frames`, size equal, codec and `pix_fmt` per profile, faststart per profile (tolerance 0).
- Timeout or Ctrl-C after the rename completes step 3 and ends `DONE` (Y-7a).

### 6.5 probe, scan (P-1, D25, SG-15)

```python
def probe(file: Path, deadline: float) -> ProbeFacts
def scan(file: Path, facts: ProbeFacts, profile: dict, want: set[str], deadline: float) -> ScanEvents
```

- `n_frames`: `ffprobe -count_packets` on `v:0`. faststart: walk the top-level atoms by their size fields (32-bit size, `size == 1` → 64-bit `largesize`, `size == 0` → to end of file) and require `moov` before `mdat` (stdlib; Q-20b).
- `scan` runs one `ffmpeg -i <file> -vf blackdetect=...,freezedetect=... -af silencedetect=...,astats=metadata=1:reset=0,ebur128=peak=true:framelog=quiet -f null -` (`ebur128` only from M3; `framelog=quiet` or stderr carries one line per 100 ms, Q-19) and parses stderr into intervals. A file without an audio stream ignores `-af` (exit 0, no audio lines; verifier probe).
- Open-at-end closure (SG-15): after the pass, any `freeze_start` without a matching `freeze_end` becomes `Interval(t0, video_end, open_at_end=True)` with `video_end = n_frames / fps`; a `black_end` within one frame of the last frame's pts is extended to `video_end` and flagged `open_at_end`; an unmatched `silence_start` closes at `audio_duration_s`. Every closed interval's `t1` is then clamped to `film_end = max(video_end, audio_duration_s)` (Q-12: AAC pads to a whole frame, so a tail `silence_end` reads 5.013333 on a 5.0 s film at 48 kHz); a silent interval whose clamped `t1` is within one audio frame (`1024 / sample_rate`) of `film_end` is flagged `open_at_end`. `black_end` cannot tell "black to the end" from "black ended by one bright last frame"; both read as the last frame's pts and are treated as open, an error of one frame (Q-14, accepted). Intervals shorter than the threshold's `min_duration_s` after closure are dropped. This is what makes a film that ends still and silent (D25) measurable, and what `end_hold` (`anchor: end`) selects.
- Head floor (W33, 2026-10-10): a still whose `t0` is at most `freeze.start_window_s` (5.0 s) is kept down to `freeze.start_min_duration_s` (1.0 s), as an end still is kept down to `end_min_duration_s`; `freezedetect`'s `d=` is the smallest of the three floors; a still elsewhere is still dropped under 2.0 s. Side effect: a 1.0–2.0 s still that starts inside the window is now detected (it was dropped under the first pass's 0.1 s window). FK-R-8 lists only stills of the general floor or more, so a short head or end still appears only through a rule row.
- Local motion (W32, 2026-10-10): after closure, each **mid-film** `frozen` interval (one that neither starts within 0.1 s of frame 0 nor is `open_at_end`; user ruling 2026-10-10 — a head or end hold is a hold whatever moves in a corner of it, so those intervals are kept without a pass and without a note) gets one more ffmpeg pass over `[t0, t1]` (`local_motion_levels` / `split_local_motion` in `scan.py`; stdlib only): `-ss t0 -t (t1−t0) -i FILE -an -vf "scale=320:180,format=gray,format=gray16le,tblend=all_mode=difference,scale=16:9:flags=area" -f rawvideo -pix_fmt gray16le -`, 144 little-endian uint16 per frame pair, the maximum divided by 65535 is the largest tile's mean absolute luma difference. On this build (ffmpeg 8.1) `tblend` yields one value fewer than there are frames, so no first value is dropped (control `W32-fail` pins the count). The statistic is the median over the span; above `freeze.local_tile_median_max` the interval leaves `frozen` and is kept in `ScanEvents.frozen_local_motion`. `judge` writes one info row `FK-R-8L#<n>` per excluded span (its own id family so the corpus reader and the FK-R-8 listing never take it for a still). A pass that fails or times out keeps the interval, adds a note, never raises (fault point `local_motion`).
- All-zero audio: `astats` overall `Peak level dB` is `-inf` (SG-14).
- Detection floor (Q-15): `freezedetect` reports a still only when it lasts at least `min_duration_s` plus one frame (a 2.0 s still at d=2 is not reported). D18 (2026-10-10): a still that runs to the end of the film has its own floor `end_min_duration_s` (1.0 s; `freezedetect` runs at d=1.0 and stills elsewhere are still dropped under 2.0 s), because `end_hold`'s lower bound is now 1.5 s; the rule's `missing_zh` sentence names the detection floor via `{floor_s}` so a 2.0 s tail is not read as "no hold".
- Clamping applies only to an interval whose end is at or past `film_end − one audio frame`; a silent interval ending mid-film (even on an AAC frame boundary) keeps its reported `t1` and is never flagged (R-7c).
- Scan failure or deadline → content rows UNDET, `unfinished: true`, `reason: "scan failed: <last stderr line>"` or `"check timed out"`.

### 6.6 judge, rerun, report, sheet, summary

```python
def judge(facts: ProbeFacts, scan: ScanEvents | None, spec: ExpectedSpec, plan: dict | None, plan_mode: str,
          record: dict | None, transform_rec: dict | None, rules: dict | None, profile: dict,
          mounted_kit_hash: str | None, kit_hash: str, lock_held_by_other: bool) -> list[CheckRow]
def range_compare(rule: dict, scan: ScanEvents, video_end: float, film_end: float, floors: dict[str, float]) -> CheckRow   # the only rule logic in the kit
def build(record: dict | None, file: Path, args: CheckArgs, kit_dir: Path) -> str    # rerun.build
def write_report(rows, meta, out_dir: Path, names: OutputNames) -> CheckResult      # check.json then check.md from it
def render_md(check_json: dict) -> str                                              # pure function (FK-INV-11)
def make_sheet(file: Path, out_png: Path, profile: dict, deadline: float) -> SheetResult
def five_lines(state: RunSummary, check: CheckResult | None) -> list[str]
def exit_code(state: RunSummary, check: CheckResult | None) -> int
```

`make_sheet` → `SheetResult` → `CheckResult.sheet`; `five_lines`/`exit_code` read `CheckResult`; the CLI entry prints and calls `sys.exit`.

`check.md` sections, fixed order: 擋件 / 機器已確認 / 要你看 / 無法判定 / 作者宣告的例外 (fifth from M2). First line (`messages_zh.FIRST_LINE`) states that pixels and quality were not judged. Sentences come from `messages_zh.py` via `message_key`, or from the rules file for rule rows. Section 1 prints each row's `rerun` on its own line in a code span.

FK-INV-10 scan targets: `messages_zh.py` rendered with fixture values, the five-line templates, `kinds.py` hints (kit selftest), and every rules-file sentence (`filmkit_rules_selftest.py`, P-19d). Exempt tokens: kind names, flag names, file names, and `rerun` lines. Positive control: a fixture sentence containing "建議" fails.

### 6.7 kinds (P-11)

`kinds.py` maps each kind of design §5.3 (`spec_invalid`, `output_foreign`, `busy`, `env`, `page_contract`, `asset_load`, `not_ready`, `page_runtime`, `encode`, `verify`, `publish`, `timeout`, `interrupted`, `internal`) to `message_template` and `hint_template` (English, placeholders filled from the error). Every `FilmkitError` subclass has an entry; selftest asserts the mapping is total and runs one five-line control per kind (FK-INV-13).

### 6.8 transform (M3; P-23, Y-8)

```python
class Operation(Protocol):
    name: str
    def add_arguments(self, parser: argparse.ArgumentParser) -> None
    def validate(self, ns: argparse.Namespace, rules: dict | None) -> dict     # params; SpecInvalid when no target given
    def build_filter(self, params: dict, facts: ProbeFacts) -> list[str]      # ffmpeg argv fragment
def run_transform(op: Operation, ns, kit_hash: str) -> int
```

`transform.py` builds a sub-parser per entry of `OPERATIONS`; adding `duck` = a module + one table entry, no change to `transform.py` (D24). `run_transform` uses `RecordStore` for `<out>.transform.json`, the same `OutputLock`, `write_json_atomic`, `publish` sequence and five-line output. Start rows top-down (design §7.4d v4.2): params → input missing/unreadable → lock → `--out` FOREIGN → `CREATED`. `normalize`: `-c:v copy`, `loudnorm` two-pass with the given targets, audio per profile; verify = video stream identical to the input's (codec, pix_fmt, size, frame count), audio per profile, duration within `av_length_tolerance_s` of the input, input sha256 unchanged.

## §7 Check rows: build detail

Row semantics are design §7.5. This section settles only what the design left open.

### 7.1 Severities fixed until D18

FK-R-7, 8, 10, 12 → `look`; FK-R-14 → `info`, no threshold.

### 7.2 Settled details

| Row | PSM detail |
|---|---|
| FK-R-2 | Measured = video frame count vs `expected.n_frames`; standalone tolerance `duration_tolerance_frames` (1). Unusable expected duration (§5.2) → UNDET. |
| FK-R-3 | Size, even dimensions, constant fps; no expected size → even/constant judged, extra row `FK-R-3#size` UNDET. |
| FK-R-4 | Sub-checks codec, `pix_fmt == yuv420p`, faststart, each its own message. |
| FK-R-5 | Presence/codec/channels per design. Separate row `FK-R-5#length` (P-18): `abs(audio_duration - video_duration) > av_length_tolerance_s` → WARN/look; otherwise PASS; no audio → no row. |
| FK-R-6 | Reads `last_success.load_report`. FAIL: that report lists failed/blocked resources (reachable only on an edited or foreign record). `font_families[].result == "substituted"` → WARN/look naming the family (family level, Q-1); `undetermined` → UNDET row `FK-R-6#font` (`unfinished: false`); no record → UNDET. |
| FK-R-8 / FK-R-8L | FK-R-8 lists the stills that stayed in `frozen` and are at least the general floor long (§6.5). W32: each mid-film span left out for local motion (never a head or end still) is one info row `FK-R-8L#<n>` (PASS / info, bucket confirmed) stating the span, the median and the limit; it is not an FK-R-8 row. |
| FK-R-9 | All-zero = `audio_peak_db == -inf` when audio expected → FAIL/blocking. Narration-line branch from M3. |
| FK-R-13 | Order (report §4(d) vii): first `--mounted-kit-hash none` + no record → info and stop; else `owner_state` table (§6.1) on the reconciled record; kit-hash branch only with a hash. Derived file: follow `transform.json.input` to the source and its `render.json`; any broken link → WARN/look. |
| FK-R-14 | One `info` row per declaration + totals `{seconds, share_of_film}`; no plan → no row. |
| FK-R-15 | M2 (D27). Overlap = open-interval intersection longer than `eps = 1/(2·fps)`; "beyond film length" = `t1 > video_end + eps` (P-21c). |
| FK-R-16 | `range_compare` per owner-filmkit rule; film type from flag, else plan (full mode); no film type given + restricted rule → UNDET; a film type not in `film_types` → one UNDET `FK-R-16` "film type not in vocabulary: <value>" and no rule rows (R-11); a known type the rule does not list → no row; selector reads `open_at_end` intervals like any other; not suppressed by declarations. Nothing matched: WARN/look, or PASS when the rule carries `missing_ok: true` (W33). Before M2: the single UNDET of §5.1. |

### 7.3 Two counts (BR-6)

With declarations, `judge` evaluates content rows twice (with and without declarations); `summary.look` from the first, `look_without_exemptions` from the second; only the first run's rows are written.

## §8 Host changes (registrations R1–R8)

### 8.1 R1 lab `CLAUDE.md`

M0: Commands += `python -X utf8 tools/filmkit/render.py ...`, `.../check.py ...`, `python -X utf8 tools/filmkit/selftest.py`, `python -X utf8 tools/filmkit_rules_selftest.py`; Invariants += INV-7 "after any edit under `tools/filmkit/` or to `tools/filmkit_rules.json`, run both selftests before committing". M3: Commands += `python -X utf8 tools/filmkit/transform.py <op> <input> --out <new> ...` (P-23).

### 8.2 R2 `tools/run_arm.py` (M1; against 00acb20)

Precondition: `git merge-base --is-ancestor 00acb20 main` exits 0. Otherwise stop and report; do not rebase r22 work.

| Where (00acb20) | Change |
|---|---|
| constants | `KIT_SRC`, `RULES`, `KIT_USAGE_MARK = "kit/filmkit/README.md"` |
| `kit_hash(folder)` | §4.7 algorithm, duplicated on purpose |
| `round_kit_checks(cfg, round_dir)` | called in `main()` after `round_dir` is defined (L477) and before `mkdir`/lock/any workspace (P-15): (a) arm-level `export_kit` → exit 1; (b) `export_kit` (default true) and an arm's frame lacks `KIT_USAGE_MARK` → exit 1; (c) SG-4 guard: `round_dir/*/run.json` exists without an `export_kit` field and the round file has no `export_kit` key → exit 1 "round started before filmkit; set export_kit explicitly"; (d) when mounting: `kit_hash(KIT_SRC)` vs the last line of `kit_hash.txt`; differs and no `kit_change_reason` → exit 1 |
| `mount_kit(cfg, arm, ws, round_dir)` | after `mount_agents`: copy MANIFEST paths to `ws/kit/filmkit/`; assert copy hash == source hash; append to `kit_hash.txt` when it is the first line or a reasoned change |
| `run()` env | when mounted, `PYTHONDONTWRITEBYTECODE=1` on top of `child_env()` |
| `expect_for(cfg, arm)` | arm-level `expect` overrides round-level key by key; absent → `{}`; `audio` accepts `true`/`false` only and becomes `--audio-expected yes|no` (P-24d) |
| `render_lock_free(build)` | `msvcrt` probe with `lseek` 0 on `build/.filmkit/lock`; missing file → free |
| `lab_check(ws, cfg, arm, mounted_hash)` | after the status lines, BEFORE `copy_build()`. No `final.mp4` → `skipped/no_output`; lock held → `skipped/render_in_progress`; else `check.py` from `KIT_SRC` on `ws/build/final.mp4` with the design §4 flag set (`--plan ... --plan-exemptions-only` only if the arm wrote one; `--rules RULES` from M2), `--out-prefix lab.`, `--json`, timeout = profile check timeout + 60 s; reads `outputs` from the JSON (P-3). Exit 1 or timeout → `{status: "error", message}`. Never changes `status` (D14). |
| `kit_source_reads(events)` | §8.3 |
| `rec` | §4.8 fields |
| `--selftest` | `kit_selftest()` joins the `&` chain |

`kit_selftest()` controls: mounted / not mounted; arm-level `export_kit` refused; copy holds no rules file; frame without usage line refused; SG-4 guard fires on a fake round dir with an old `run.json` and passes with an explicit key; kit hash mismatch refused AND `ARMS_ROOT/<round>/<arm>` does not exist afterwards (P-15); passes with `kit_change_reason` and appends a line; kit edited in the workspace → FK-R-13 in the lab output; `check.py` exit 1 leaves `status` unchanged; lab outputs do not overwrite the arm's `check.json`; an arm without `render.json` gets `lab.final.mp4.check.json` and `check_summary.outputs` names it (P-3); no `final.mp4` → `skipped`; held lock → `skipped/render_in_progress`; `kit_source_reads` controls of §8.3.

### 8.3 `kit_source_reads` (Y-22, P-16)

From the arm's parsed stream events (`transcript.jsonl` is the stored form), an assistant `tool_use` counts as a read when: (a) `Read` targets a path under `kit[\\/]+filmkit[\\/]` ending in `.py`; (b) `Grep` or `Glob` has a `path` (or pattern) under `kit[\\/]+filmkit` regardless of suffix; (c) `Bash`/`PowerShell` `command` contains a path under `kit[\\/]+filmkit` together with a reader (`cat`, `type`, `more`, `less`, `head`, `tail`, `sed`, `awk`, `grep`, `rg`, `findstr`, `Get-Content`, `gc`, `Select-String`, `cp`, `copy`, `Copy-Item`, `open(`). Matching is by token (Q-11): the command is split with `shlex.split(posix=False)` and then on `|`, `;`, `&&`, `||`; a pipeline segment counts when one of its tokens EQUALS a reader verb (case-insensitive; `open(` matched as a substring only inside a `-c` argument) and another token in the same segment is a path under `kit[\\/]+filmkit`. So `--film-type` never matches `type`, and `--target-lufs` never matches `rg`. Running a kit script, `ls`/`dir` of the folder, and reading `README.md` are not reads. Repeated `tool_use` ids count once. Blind spots, stored as `instrument_limits`: paths built from variables, indirect reads through a script the arm wrote, any reader verb not listed, and reads by a relative path after `cd kit/filmkit` (R-13d). Controls: positive — Read `kit/filmkit/render.py`, Bash `cat kit\filmkit\_fk\judge.py`, Grep with `path: kit/filmkit`, Bash `python -c "print(open('kit/filmkit/check.py').read())"`, Bash `cp kit/filmkit/render.py x.py`; negative — `python -X utf8 kit/filmkit/render.py --help`, Read `kit/filmkit/README.md`, `ls kit/filmkit`, a full render command `python -X utf8 kit/filmkit/render.py build/index.html -o build/final.mp4 --duration 30 --size 1280x720 --plan build/film_plan.json --audio build/mix.wav --film-type product-tour --keep-frames`, and `python -X utf8 kit/filmkit/transform.py normalize build/final.mp4 --out build/n.mp4 --target-lufs -20 --true-peak -1`. M1 acceptance wording: "this instrument found no source reads (limits: ...)".

### 8.4 R3–R8

| # | Change | Milestone |
|---|---|---|
| R3 | New-round frame files only: ENVIRONMENT gains `Video export: see kit/filmkit/README.md (your page must define window.__setTime(t)).` A new round reusing `frame_imitate.md`/`frame_product.md` gets a new frame file with `__setTime`, never an edit of a frame a finished round used. | M1 |
| R4 | Scan (inline in the M1 commit message): JSON files under `rounds/` with a `round` key whose arms lack `run.json`. 2026-10-09: `r9-lock-count.json` (0/12, closed) → `"export_kit": false`; `dit-promo-v1-draft.json` (0/1, draft) → unchanged; `r22a-haiku-c21.json`, `r22b-haiku-dit.json` (in progress) → not edited; the SG-4 guard refuses them until the user sets the key on resuming (§0 item 2). Re-run at M1 time. | M1 |
| R5 | `~/.claude/skills/motion-video`: `references/build-and-export.md` §2 → export with filmkit (`lab-round`); §3 review starts from `check.md`; `SKILL.md` step 7 and Verdicts: "file deliverable" decided by `check.py`; delivery list pastes `check.md` sections 1–4 verbatim (including `rerun` lines), then the session's own questions separately; any `transform.py` operation on a formal film is asked first, naming the new file (BR-14, D21); formal films bundle their fonts with `@font-face` (D26: one locally available, cross-platform, openly licensed sans family such as Noto Sans TC for both CJK and Latin; never rely on installed system fonts). `delivery-web` and `normalize` lines in M3. | M1 (+M3) |
| R6 | `~/.claude/tools/lab-skill-sync/pairs.json`, pair `motion-video`: `watch` += `tools/filmkit`, `tools/filmkit_rules.json`; then `sync.py mark motion-video` from `~/.claude` after R5. | M1 |
| R7 | `docs/workflow.md` ⓪ export step and ⑥; `docs/production-order.md` F (font-load row: add D26) and J. `docs/workflow.md` is watched by `case-library`: update that skill's §Starting paths and mark it. | M1 |
| R8 | `~/.claude/references/PROJECTS.md` motion-video-lab row: tool list += filmkit. No AssetVault entry (D3). | M1 |

## §9 Work cards

Each card: branch `feat/filmkit-mN` from main; commits by path, Conventional Commits; a checkpoint with incomplete gates is `wip(filmkit): ...`. Every gate runs with its positive AND negative control; output goes into `measurements/filmkit-calibration/mN-evidence-<date>.md`.

### 9.1 Invariant controls (P-12)

| FK-INV | Control (positive / negative) | Milestone |
|---|---|---|
| 1 | ffmpeg killed mid-run → no output / clean page publishes | M0 |
| 2 | foreign file, record with wrong hash → rejected / rerun overwrites own file | M0 |
| 3 | fake `CaptureBackend` records `seek()` args; equal to `Fraction(i, fps)` and to `frames.t` / a backend that drifts by float accumulation fails | M0 |
| 4 | selftest fixture profile `fixture-b` (other CRF) → different recorded argv / same profile twice → identical argv | M0 |
| 5 | scan of every selftest `check.json`: FAIL/WARN rows have `measured`+`basis`, UNDET rows `reason` / fixture row with empty `basis` fails | M0 |
| 6 | interrupt right after start → record exists, valid, `running` / normal run → `done` | M0 |
| 7 | copy kit to an empty temp folder, run `selftest.py --smoke` with `python -I` → passes / a fixture module importing `tools.avio` fails the import scan | M0 |
| 8 | missing `why` rejected / three declarations → three md lines | M0 (schema), M2 (md) |
| 9 | external URL, parent-folder file, output outside the page folder → blocked/rejected / same-folder image loads | M0 |
| 10 | §6.6 scan; fixture sentence with "建議" fails / real templates pass | M0 (+M2 rules sentences) |
| 11 | delete `check.md`, regenerate from `check.json` → byte-identical / edited json → different md | M0 |
| 12 | `profiles.json` key scan (M0); kit scan vs rules file ids and sentences / fixture kit file containing `end_hold` fails | M0 |
| 13 | five lines for success and for every kind of §6.7; `--json` once / extra stdout line fails | M0 |
| 14 | clean page rendered twice → identical `frames.sha256` / `Math.random()` page differs (also FK-R-12) | M0 (+M2) |
| 15 | hash before/after a render run unchanged / unlisted file fails | M0 |
| 16 | `--help` vs §5.1 / fixture help missing a flag fails | M0 |
| 17 | render+check leave no derived file / `normalize` writes new file + record, source unchanged; `--out` = input and missing target → `spec_invalid` | M3 |

### 9.2 FK-M0 — `render.py` + `check.py` turn a time-driven page into a verified MP4 with a five-line result and a `check.md`

- Severity/Confidence: blocker for M1–M3 (everything mounts on it) / spec verified three rounds (v1 pass-with-fixes, v1.1 fail→fixed, v1.2 pass-with-fixes 0 BLOCK); v1.3 fixes not re-verified by user ruling, so this card's controls are their first check.
- Objects (new unless noted):
  - `tools/filmkit/`: every file of §3.1 except `transform.py`, `_fk/transform_core.py`, `_fk/ops/*`. `MANIFEST.txt` lists exactly the files created.
  - `tools/filmkit/profiles.json`: `lab-round` only (`fixture-b` lives inside `selftest.py`).
  - `tools/filmkit_rules.json` (data only, §4.5; `film_types` from `~/.claude/skills/motion-video/references/film-types.md` — grep `^## §` there for the seven headings).
  - `tools/filmkit_rules_selftest.py` (FK-INV-12, FK-INV-10 rule-sentence scan, `film_types` vs `film-types.md`).
  - `CLAUDE.md` (edit): R1 M0 lines (§8.1).
  - `measurements/filmkit-calibration/sg-probes-<date>.md`, `measurements/filmkit-calibration/m0-evidence-<date>.md`, `measurements/filmkit-calibration/m0-sidebyside/` (sheets; mp4 copies git-ignored if the repo ignores media — check `.gitignore` first).
  - NOT touched: `tools/run_arm.py` (M1), any `rounds/` file, any `experiments/` folder (read-only; r20 A3 is read, never written), `rounds/r22a-*`, `rounds/r22b-*`, `experiments/r22-*` (a test is running — do not read, list or glob them).
- Why: the lab has no shared export or file check; every arm wrote its own `capture.py` (design §1). M0 is the core the later milestones mount on.
- Change: build to PSM §2–§7 exactly; the design (v4.4) wins on any contradiction → stop and report. Suggested order, one `wip(filmkit): …` checkpoint commit after each step whose controls pass:
  1. SG probes (§2) on this machine → `sg-probes-<date>.md`. A probe that no longer holds → stop.
  2. `common`, `kinds`, `types`, `manifest`, `profile`, `spec` (+ `film_plan.schema.json`, plan validator fixtures).
  3. `guard`, `store`, `record` (lock, `owner_state`, reconcile, write retry) with their unit controls.
  4. `capture` (Playwright backend, route handler, font fingerprint), `encode`, `mux`, `verify`, `render.py`.
  5. `probe`, `judge` (FK-R-1…6, `FK-R-5#length`, `FK-R-6#font`, the M0 `FK-R-16` UNDET), `rerun`, `report`, `messages_zh`, `sheet`, `summary`, `checkrun`, `check.py`.
  6. `selftest.py` complete, `filmkit_rules.json` + `filmkit_rules_selftest.py`, R1 lines in `CLAUDE.md`, README (usage + upgrade condition + blind spots Q-16/R-9 + the font file note R-13f).
  7. Field evidence (below), then the final `feat(filmkit): …` commit.
- Interpretation forks the spec does not settle → stop and report with the options; do not pick. Known open item that is NOT a fork: severities stay §7.1 until D18.
- Blast radius: new files only, plus R1 lines in `CLAUDE.md`. Must not change: any existing tool, `run_arm.py --selftest` result, any `experiments/` or `rounds/` file, the lab-skill-sync markers (R5/R6 are M1).
- Rollback: delete the branch `feat/filmkit-m0` (nothing merged until the user accepts). After merge: `git revert` the M0 commits; no other file depends on filmkit until M1.
- Acceptance (machine-checkable first):
  1. `python -X utf8 tools/filmkit/selftest.py` exit 0 and `python -X utf8 tools/filmkit_rules_selftest.py` exit 0, output pasted into `m0-evidence-<date>.md`; every control in §9.1 (rows tagged M0) and in the table below ran with BOTH arms, and each positive control is shown to fire (a control that cannot fail is not a control). Skipped controls listed with their reason (only the §6.1 non-Windows lock skip and R-13f font skip are allowed).
  2. `python -X utf8 tools/run_arm.py --selftest` and `python -X utf8 tools/build_index.py --check` still exit 0 (nothing else broke).
  3. Kit self-containment: copy `tools/filmkit/` to an empty temp folder, `python -I -X utf8 selftest.py --smoke` there exits 0 (FK-INV-7).
  4. Field evidence: copy `experiments/r20-t12-blur/A3/index.html` and `grain.png` (and any other file its route log shows) into a scratch folder OUTSIDE `experiments/`; `render.py <copy>/index.html -o <copy>/final.mp4 --duration 30 --size 1280x720` (silent, 30 fps); `check.py` on the result exits 0 or 2 with every row explained; FK-R-4 faststart PASS although silent; sheets of the new and the original `final.mp4` side by side in `m0-sidebyside/`; `per_frame_ms` recorded. The page uses `Georgia`, so FK-R-6 font rows are expected to be absent — record what was observed.
  5. User acceptance (A 必驗, below) — the executor prepares it, the user rules; M0 is not merged before it.
- Commit: `wip(filmkit): <step>` checkpoints, then `feat(filmkit): add M0 render and check core`; merge to main only after acceptance 5 (local ff-merge, no remote).

A 必驗（交給使用者，依後果排序）：
1. 新舊並排（r20 A3）：你看兩份 sheet，新出片和原片畫面一致、沒有跳格或少格（INV-6，你點頭才算）。
2. 打開一份 `check.md`：第一段擋件看得懂、`rerun` 那行貼進 PowerShell 能直接跑。
3. 故意給一個奇數寬度（`--size 1279x720`）跑一次：五行輸出第三行說清楚錯在哪，沒有產生半成品。
4. 跑到一半按 Ctrl-C：舊的成片還在、沒被弄壞，再跑一次會正常完成。

B 體驗：五行輸出與 `check.md` 的中文讀起來順不順；出片速度（`per_frame_ms`）能不能接受。

Rows: FK-R-1 … FK-R-6 (+ `FK-R-5#length`, `FK-R-6#font`); `check.md` sections 1–4; `rerun`.
Controls: §9.1 rows tagged M0; design §9 rows tagged M0 except the two moved to M2 (P-14); plus:

| Control | Expected | Closes |
|---|---|---|
| L1–L3, L7; `try_lock_free` unit (held → false, free → true) | §6.1 table (L4, L6 in M1; L5 in M3, Q-2) | lock |
| `owner_state` unit: one input per row 1–7, incl. `lock_held_by_other=True` and a failed rerun (FK-R-13 the ROW is M1) | each row's state / a row-7 record with one edited input → `STALE` | P-6, Q-2 |
| killed between rename and `promote`, page unchanged | `owner_state` on the reconciled record → `CURRENT` | Q-3b |
| success with `--audio a.wav`, then a failed rerun with `--audio b.wav` | rows 3–4 still compare against `last_success.inputs` (a.wav); `last_success.frames` unchanged by the failed rerun (FK-R-11/12 themselves in M2, R-6c) / a successful rerun with b.wav replaces both | Q-3a, Q-3c |
| FK-R-6 FAIL: hand-edited record with non-empty `last_success.load_report.blocked_requests` / clean record | FAIL blocking / no row | Q-2 |
| `-o build/preview/x.mp4` for `build/index.html` / `-o build/x.mp4` | `REJECTED(spec_invalid)` with the D30 hint / accepted | Q-8, D30 |
| hard kill during a `render.json` write | no `*.tmp` in the page folder's top level; the next `CREATED` removes `.filmkit/*.tmp` | Q-9 |
| `REJECTED(busy)` while A runs | A's `lock.json` unchanged (same pid, run_id) | Q-18 |
| silent page published (no `--audio`) | FK-R-4 faststart PASS (moov before mdat) / a file encoded without the flag → FAIL | P-5 |
| odd-size mp4 with a `render.json` / clean mp4 | md section 1 contains the full `render.py` line with the expected size, absolute paths, `list2cmdline` quoting / no `rerun` | P-2, Q-4 |
| odd-size mp4 without a record; unreadable mp4 with no expected values | template with `<page>`, `<new-out>` placeholders; template still has `--duration <S> --size <WxH>` | P-2, OQ-1, Q-4(iii) |
| success, then a failed rerun with other flags, then an odd-size check | `rerun` built from `last_success` fields, not the failed run's | Q-4(i) |
| render from cwd A (`render.py build/index.html ...`), check from cwd B, read `rerun` from cwd C | every path in `rerun` is absolute and `Path.exists()` (except the output) | R-1 |
| foreign odd-size mp4 | `rerun` has `-o <new-out>`, never the checked file | R-3 |
| FK-R-5 FAIL (audio expected, none) with and without a record | `rerun` contains `--audio` (value or `<audio>`) | Q-4(v) |
| two page folders (with a space and CJK characters; without a space) × two shells | `rerun` run through PowerShell `Invoke-Expression` and Git Bash `eval` on a stub `render.py` that prints `sys.argv` → argv equal item by item in all four (no `shlex` round trip: it eats backslashes) | Q-4(vi), R-2 |
| font: `Arial` mixed node; `Arial` pure-CJK node; `Segoe UI` pure-CJK node; `Microsoft JhengHei` CJK node; `Microsoft JhengHei` Latin node | no row (5 cases) | P-4, Q-1, D26 |
| font: `NoSuchFontXYZ` Latin node; `NoSuchFontXYZ` CJK node | `substituted`, WARN (2 cases) | P-4, Q-1 |
| font: `@font-face` family with `unicode-range: U+4E00-9FFF` in a CJK node (fixture `FkCjkOnly`) | `present`, `decided_by == "cjk"`, no row | R-6b |
| font: fake backend returning three identical baselines / distinct baselines | `undetermined` → UNDET `FK-R-6#font` / decided normally | R-6a |
| font: page with `* {font-family: "Segoe UI" !important}` and a `Times New Roman` node | probes still decide (`important` probe styles), TNR `present` | Q-7c |
| font: `font-family: -apple-system, "Segoe UI"` | `-apple-system` not probed; `Segoe UI` present; no row | Q-7d |
| font: node added by JS after `__ready` that exists from frame 0 / one shown only between sampling moments | probed / not probed, and `Notes:` names the sampling moments | Q-7a |
| font probe on a page whose script draws `document.querySelectorAll('span').length` every frame | frame hashes equal to a run with the probe disabled / a fixture probe that appends to `body` (the unsafe placement) changes them, so the control can fail | Q-7b, FK-INV-14, R-6e |
| page bundling `NotoSansTC-VF.ttf` (copied at run time from `C:\Windows\Fonts`, not committed) via `@font-face` / same `@font-face` pointing to a missing file | loads, FK-R-6 no row / `FAILED(asset_load)`; when the source font is not installed, the control reports `skipped (font not installed)` and the README names the file (R-13f) | D26 |
| hidden probe uses `display:none` (fixture backend) | selftest fails (empty list guard) | P-4c |
| `--duration 10.05 --fps 30` / `--duration 30.0000000001` | `REJECTED(spec_invalid)` with frame hint / N = 900 | P-9 |
| page loads `img/late.png` at frame 50 | listed in `inputs`; editing it makes `owner_state` `STALE` | P-8 |
| killed after `set_pending`, before rename; after rename before `promote` | first: file absent, rerun clean; second: next run promotes pending | Y-2, P-8 |
| a reader holds `render.json` open for 100 ms during a transition / for 5 s | render succeeds / `FAILED(internal)`, output untouched | P-17 |
| exception injected into `judge` after publish | output present, `last_success` correct, rows UNDET `unfinished`, exit 3 | P-20 |
| exception injected into `promote()` after the rename; into `finish()` | `DONE`, `internal_error` set, exit 3, next run reconciles / `DONE`, exit 3 | Q-5 |
| `ffprobe` deadline hit (tiny `--check-timeout`) | FK-R-2…5 UNDET `unfinished`, exit 3 | P-14 |
| failed rerun with unchanged inputs / check while another process renders | `owner_state` `STALE` / `STALE` | P-6, P-13 |
| check of a copy missing `img/late.png` / same copy with the file restored | `owner_state` `UNDET_INPUTS` / `CURRENT` | P-13, R-6e |
| page or image edited during `CAPTURING` | note "inputs changed while rendering"; record keeps the end hashes | R-10b |
| FK-R-2 off by 1 frame / by 2 (standalone) | PASS / FAIL | P-13 |
| FK-R-3 wrong expected size; variable-fps file | FAIL; FAIL | P-13 |
| `FK-R-5#length` audio 0.05 s longer / 0.5 s longer; no expectation | PASS / WARN; FK-R-5 info only | P-13, P-18 |
| `--rules` given in M0 | one `FK-R-16` UNDET, `unfinished: false`, exit 0 | P-18 |
| mux argv and output (stereo 48 kHz; mono) | no banned flags, channels/rate unchanged, `volumedetect` mean ±0.5 dB / mono → FK-R-5 FAIL, exit 2 | Y-18 |
| derived/foreign file checked; then render output checked; pre-existing foreign `check.md` | `<name>.check.*` and `check.*` coexist / `output_foreign`, nothing written | Y-13, P-25c |
| whole-file look row | `where: file`, `t0 = 0`, `t1 = duration`, `t = null`, not in `events` | Y-20 |
| `ABSENT` + external file; page edited while `STALE` | `owner_state` `FOREIGN`; still `STALE` | Y-7(c) |
| ffmpeg killed during `wait()` | `FAILED(encode)` | Y-7(b) |
| 300 `console.log` per frame page | `console` capped at 200, `console_truncated: true` | P-25a |
| `--json` on `REJECTED` | `{"status": "rejected", ...}` only | P-24a |
| import graph (§5.4) | pass / fixture violation fails | P-23 |
| plan validator vs schema fixtures | agree on all 16 | §4.1 |

Field evidence and acceptance: see the card fields above (Acceptance 4–5).

### 9.3 M1 mounting

Precondition §8.2. Files: `tools/run_arm.py`, R3–R8 targets, FK-R-13 complete in the kit.
Controls added in M1 (Q-2): FK-R-13 as a row over the M0 `owner_state` cases (`STALE`, `UNDET_INPUTS`, `FOREIGN`, `none` + no record → info, kit-hash mismatch); lock interleavings L4 and L6 against `run_arm.py`'s `render_lock_free`.
Acceptance: `run_arm.py --selftest` passes (old controls unchanged + `kit_selftest`); one real round the user approves with the kit mounted; lab outputs present for every arm with output, at the names in `check_summary.outputs` (`lab.check.*` for arms with a record, `lab.final.mp4.check.*` otherwise, P-3); `measure_arm.py`, `retro.py` rerun with no difference; "`kit_source_reads` instrument found no reads (limits: ...)" for every arm, or the reads are recorded and README/`--help` fixed (BR-12); the first real output is read before any number goes into a report, control arms excluded.

### 9.4 M2 content scan

Files: `scan.py` black/freeze/silence/astats with SG-15 closure; FK-R-7 … 12, 14, 15 (D27, reads `narration_lines`), 16; resample; `check.md` section 5; two counts; rules evaluated; `filmkit_corpus.py`; lab check gains `--rules`.
Controls: §9.1 rows tagged M2; design §9 rows tagged M2 (incl. "`silences` on a narration line → FK-R-15"); moved from M0: "blocking row and scan failure together → exit 2", "scan deadline → content rows UNDET, exit 3" (P-14); plus:

| Control | Expected | Closes |
|---|---|---|
| 5 s synthetic: last 3 s still (open at end) | `frozen = [(2.0, 5.0, open_at_end)]`; `end_hold` with a 2.5–3.5 fixture range → PASS | P-1, D25 |
| 5 s: 3 s still in the middle, then motion | one closed interval | P-1 |
| 5 s: motion throughout | no interval | P-1 |
| last 3 s black; last 3 s silent (AAC 48 kHz) | black interval extended to 5.0, flagged; silent interval `t1` clamped to 5.0, `abs(t1 − 5.0) ≤ 1024/48000`, flagged | P-1, Q-12 |
| same at 60 fps | same result (tolerance is one audio frame, not `1/(2·fps)`) | Q-12 |
| silence 1.0–3.0 s mid-film; sound resumes 20 ms before `film_end` | mid-film interval unclamped, not flagged; tail not flagged | R-7c |
| audio 0.2 s longer than video, silent tail; still tail | `end_hold` silent selector compares with `film_end` → PASS; frozen with `video_end` → PASS | R-7a |
| FK-R-11/12 after a failed rerun | read `last_success.frames` | R-6c |
| `--rules` given and `--film-type product-intro` (not in `film_types`) | one UNDET `FK-R-16` "film type not in vocabulary" | R-11 |
| black tail ended by one bright last frame | treated as open (one-frame error, accepted) | Q-14 |
| 1.0 s still at the end (end floor d=1, D18) | no interval; `end_hold` missing sentence names the end floor | Q-15 |
| timeline-shaped film: tail hold 3.0 s declared as `holds` + `silences` (D-T19) | FK-R-8/9 info (declared), FK-R-16 PASS, not suppressed | D25, P-21 |
| FK-R-7 interval fully inside a declared black / outside | info / look | P-13 |
| FK-R-9 silence inside a declared `silences` | info | P-13 |
| FK-R-10 vs FK-R-7 on a black first second | only FK-R-7 | P-13 |
| FK-R-11 page with a paused animation driven by `currentTime` / a running CSS transition | no row / look | P-13 |
| FK-R-14 three declarations / no plan | three md lines + totals / no row | P-13 |
| FK-R-15 declaration ending at `video_end + 1e-9` / at `video_end + 0.1` | no row / look | P-21c |
| owner-filmkit rule with kind `ratio` / owner-timeline `range` rule | one UNDET `FK-R-16#<id>` / no row | P-19 |
| provisional rule sentence | ends with `（暫定）` | P-19c |

Calibration: `filmkit_corpus.py` over every readable arm `final.mp4` without a plan → distribution (including how many end with an open-at-end still), a random sample of 30 events with contact-sheet rows for a human true/false call; `measurements/filmkit-calibration/corpus-<date>.md`. Severity stays §7.1 until D18.

### 9.5 M3 audio, transform, delivery

Files: `ebur128` in `scan.py`, FK-R-17, FK-R-9 narration-line branch, `delivery-web` (format fields only), `transform.py`, `transform_core.py`, `ops/normalize.py`, rules `targets` (official documents, `source`, `review_when`), R1 and R5 M3 lines.
Controls: §9.1 FK-INV-17; design §9 rows tagged M3, with FK-R-17's control in `filmkit_rules_selftest.py` on neutral numbers (−26 measured, target −20.5); `CREATED` × timeout → `FAILED(timeout)`; timeout after rename → `DONE`; lock interleaving L5 (`transform.py` while `render.py` holds → `REJECTED(busy)`, Q-2); `transform.json` and `render.json` both pass through `owner_state` and `publish` (`Publishable`, `inputs_sha256`, Q-13); `ebur128` with `framelog=quiet` leaves only the summary in stderr (Q-19); derived file whose source was moved away → `UNDET_INPUTS`, whose source was re-rendered → `STALE` (R-8); adding a fixture op module to `OPERATIONS` needs no edit of `transform.py` (D24).
Field evidence: one formal film delivered through filmkit; the user asked before any `transform.py` use (BR-14); fonts bundled (D26).

### 9.6 FK-W32-33 — local motion inside a still, and the head hold (user rulings 2026-10-10)

Rulings (process ledger, origin user, 2026-10-10): **W32** build the max-change-tile criterion, threshold 0.0005, excluding only intervals with local change throughout, W30 events as the first controls; **W33** add a head-anchored range rule, upper bound 1.5 s, head detection floor 1.0 s, provisional. Record both as design decisions (next free id after D30) and close W32/W33 in `waiting/pool.json` (`status` decided, evidence = this card's controls).

Fork rulings (process ledger, origin user, 2026-10-10, after the first build reported two readings the card did not settle): **A (W32)** the local-motion pass applies **mid-film only** — a `frozen` interval that starts within 0.1 s of frame 0 or runs to the end (`open_at_end`) is never passed and never excluded, so the corpus end holds E08 and E24 stay true end holds; **B (W33)** `head_hold` measures **the first still that starts within the first 5 s** instead of a still anchored at frame 0: new generic selector anchor `first` with `max_t0_s` (the kit knows the key, the number lives in the rules file), new profile key `freeze.start_window_s` 5.0 used by `keep()` in place of the 0.1 s test, floor 1.0 s inside the window; W30 E14 must read WARN. The text below is the card as ruled; the first-pass wording is in git history (5d38ecf).

**W32 — local motion.** After `close_intervals`, every mid-film `frozen` interval gets one extra ffmpeg pass over `[t0, t1]` (same deadline handling as `line_peaks`; stdlib only, the kit must not import numpy):
`-ss t0 -t (t1−t0) -i FILE -an -vf "scale=320:180,format=gray,format=gray16le,tblend=all_mode=difference,scale=16:9:flags=area" -f rawvideo -pix_fmt gray16le -` → 144 little-endian uint16 per frame; per frame `max/65535` = the largest 20-px tile's mean absolute luma difference (= 80 px at 1280×720). Statistic = **median over frames**, never max (true stills reach 0.027 for a single frame at the edges). Median `>` `freeze.local_tile_median_max` (new profile key, 0.0005, both profiles, `calibrated: false` stays) → the interval leaves `frozen` (so FK-R-8, FK-R-16 rules on `frozen`, and the head/end selectors never see it) and is kept in a new `ScanEvents.frozen_local_motion` as `(t0, t1, median)`; `check.md` lists each as an info line stating the excluded span, the median and the threshold. The pass failing or timing out keeps the interval (conservative) and adds a note; it never raises.
Calibration already done (model, 2026-10-10, scratchpad probe vs `measurements/filmkit-calibration/w30_probe.py`): this chain reproduces the numpy measure — E22 median 0.00166 (numpy 0.00164), E02 0.00005, E14 0.00002, E06 0.00000. Check whether `tblend`'s first output frame is a real difference on this build (the chain returned one frame more than numpy's diff count); drop it if it is not.

**W33 — head hold.** Rules file entry `head_hold`: owner `filmkit`, kind `range`, `select {source: frozen, anchor: first, max_t0_s: 5.0}`, `range_s [0, 1.5]`, `provisional: true`, basis naming W30 E14 and the user's 2026-10-10 ruling, `sentence_zh` / `missing_zh` in the style of `end_hold`, `review_when`. A film with no still at the head must not produce a look row: add an optional generic rule key `missing_ok` (bool, default false; PSM §4.5 additive) — when true and nothing matched, the row is `PASS` with the missing sentence. Head floor: profile `freeze.start_min_duration_s: 1.0` and `freeze.start_window_s: 5.0`; `freeze_floor()` gains `at_start`; `keep()` applies it to an interval with `t0 ≤ start_window_s` (no window key → no head floor); the freezedetect `d=` becomes the minimum of the applicable floors; `range_compare` names `frozen_start` as the floor for `anchor: start` and `first`. Selector: `anchor: first` takes the earliest interval with `t0 ≤ max_t0_s` (the key is required; absent → UNDET). FK-INV-12 holds: the kit never contains `head_hold`, its numbers or its sentences.

Controls (INV-7: kit `selftest.py` and `filmkit_rules_selftest.py`, each with a positive arm that fires on the pre-card code and a negative arm):

| Control | Expected |
|---|---|
| 4 s synthetic: still 0.5–4.0 s with an 80×8 px bar growing every frame in one corner | interval excluded, `frozen_local_motion` has it with median > 0.0005, no FK-R-8 row, info line in `check.md` / the same film without the bar → interval kept, FK-R-8 as before |
| local-motion pass forced to fail (fault point) | interval kept, note present, exit unchanged |
| 1.2 s still at the head, then motion (real rules file) | `FK-R-16#head_hold` PASS / 2.0 s still at the head → WARN look, and no duplicate FK-R-8 row for it |
| motion from frame 0 | `head_hold` PASS via `missing_ok` / the same rule with `missing_ok` removed → WARN look (positive arm for the key) |
| 1.2 s still mid-film | no interval (general 2.0 s floor) |
| (fork A) the bar still placed mid-film with motion after it / the same bar still running to the end / starting at frame 0 | mid-film: excluded; end and head: NOT excluded (the end rule sees the end one); an expired deadline gives a note only for a mid-film interval |
| (fork B) E14-shaped synthetic: 2 s motion, 2.1 s still, motion | `head_hold` WARN look, no FK-R-8 row |
| (fork B) 1.2 s still at 3 s / 1.2 s still from frame 0 | `head_hold` PASS |
| (fork B) still starting at 6 s / 1.2 s still at 8 s | not selected (`missing_ok` PASS; the 6 s one stays an FK-R-8 row) / no interval (2.0 s floor) |
| (fork B) two stills inside the window / `first` without `max_t0_s` | only the earliest is measured / one UNDET row, nothing guessed |
| lab-side real control (git-ignored mp4s, run on the main checkout): W30 E22 → excluded; E02, E06, E10, E14, E18, E26, E30 → kept; the 7 end holds → kept without a pass; E14's film → `head_hold` WARN | evidence file `measurements/filmkit-calibration/w32-evidence-<date>.md` with the medians |

Docs in the same change: this PSM (§4.5 `missing_ok`, profile keys, §7 rows touched), `docs/filmkit-design.md` decision rows, `tools/filmkit/README.md` if it lists check rows, lab `CLAUDE.md` only if a command changes. Not in scope: the motion-video skill write-back (the dispatcher does it), W31, W34.

Landed (2026-10-10; design D31, D32; rewritten after the two fork rulings above). Control ids: kit `selftest.py` `W32-local`, `W32-fail`, `W33-floor`, `W33-first`, `W33-missing-ok`; `filmkit_rules_selftest.py` `head-hold`, the two extra `FK-INV-12` arms and the `missing_ok` structure arm; lab real control `measurements/filmkit-calibration/w32_evidence.py` → `w32-evidence-2026-10-10.md`. Where the build differs from the card text: (1) the excluded span leaves one `FK-R-8` row, the usual "none found" PASS, not zero rows, and its info row is `FK-R-8L#<n>`; (2) the bar fixture is 80×8 px growing 2 px per frame **at 1280×720**, because on a 160×90 version the same bar ended the still for `freezedetect` (observed: it broke the still every 1.1 s at noise 0.005 and found none at 0.001; the change seems to add up over the still, a cause not isolated), while at 1280×720 the span stays one still; (3) `tblend` on this build returns one value fewer than frames, so nothing is dropped. Two forks the card did not settle were reported and ruled (above): the first build excluded E08 and E24 (medians 0.00093 and 0.00273, user-labelled true end holds) from `end_hold` and could not see E14 (a still that starts at 3.93 s) from a frame-0 head anchor. Now: end and head stills never go through the pass, E08 and E24 are kept, and E14's film reads `head_hold` WARN (`w32-evidence-2026-10-10.md`, tables 2 and 3). Known side effect of the 5 s window: a 1.0–2.0 s still that starts inside it is now detected (W30's `r15-mfp-ad/S` has a 1.20 s one at 0.67 s, `head_hold` PASS).

## §10 Error paths and rollback

| Failure | Behaviour | Rollback |
|---|---|---|
| any `REJECTED` | nothing written except the empty `.filmkit/lock` (rows 2–5 take the lock first; Q-18) | none |
| `FAILED(*)` before rename | partial stays in `.filmkit/`, record `failed`, previous output `STALE` | rerun |
| `FAILED(publish)` | as above; hint names the locking program | close it, rerun |
| `FAILED(internal)` (before rename only) | five lines with the exception's last line; best-effort record | attach `render.json` to a bug note |
| exception after publish | `DONE`, exit 3 (or 2), rows `unfinished` | rerun `check.py` |
| lab check error | `check_summary.status = "error"`; arm `status` unchanged | rerun `check.py` on the workspace |
| a milestone gate fails | milestone branch not merged | main untouched |
| M1 misbehaves in a real round | new rounds set `"export_kit": false`; revert the M1 commits | finished `experiments/` never edited |

## §11 Re-verification triggers (review-when)

Inherits design review-when. Also: Playwright, Chromium or ffmpeg version differs from §2 → rerun the §2 SG probes and selftest; `run_arm.py` on main changes in `run()`, `main()` or `rec` after 00acb20 → recheck §8.2 before M1; the timeline layer changes its use of `film_plan.json` or the rules file → recheck §4.1, §4.5; `sheets.py --boundaries` input changes → recheck §4.3 `events`; the machine's installed fonts change (Noto Sans TC, Microsoft JhengHei, Arial, Segoe UI) → rerun the §9.2 font controls; `film-types.md` gains or renames a film type → update `film_types` (§4.5).

## §12 Traceability additions (Y-21)

| Element | Ancestor |
|---|---|
| exit-code rule (§5.5) | BR-12b; BR-10c via D14 |
| `--timeout`, `--ready-timeout`, `--check-timeout`, `INTERRUPTED` | BR-8a; global rule "every waiting state has a timeout" |
| `--keep-frames` | BR-12b |
| `--start` | agent-review design M2 (review windows and stills; FK-WIN-1) |
| `--gpu` | r36 (heavy WebGL shading; software capture of the reference page timed out a 30 s screenshot) |
| `--json` | BR-12; D14 |
| record write policy and retry (§6.0, §6.2) | BR-8b; FK-INV-6 |
| lock and `lock.json` (§6.1) | BR-8b; D23; design §7.4 row 2 (v4.2) |
| `kit_source_reads` | BR-12a |
| SG-4 guard (§8.2 c) | BR-10a; SG-4 |
| `FK-R-5#length` | BR-11c; SG-9 |
| `--audio` + `--audio-expected no` → `spec_invalid` | FK-R-5 semantics; BR-2e |
| `FK-R-16` UNDET before M2 | BR-3; timeline §6.9 staging |
| rules `owner`/`params`/`film_types` | BR-15; timeline D-T18, §6.9 |
| `PYTHONDONTWRITEBYTECODE` | FK-INV-15 |
| `rerun` | D11, D28; BR-8a |
| SG-15 closure | D25; BR-3 |
| font fingerprint, D26 font rule | SG-12 (v4.2); BR-3; D26 |
| frame count rule | BR-2b; BR-13 |

## §13 Coverage

### 13.1 Y-items carried from design §13

| Y-item | Where settled |
|---|---|
| Y-7(b) | §6.4 sequence; §9.2 |
| Y-7(c) | §6.1; §9.2 |
| Y-8 | §5.2, §5.5, §6.8 |
| Y-13 | §5.6; §9.2 |
| Y-16(b)(c)(d) | §5.1; §4.4; §8.1 |
| Y-18 | §6.4; design FK-INV-17 (v4.2); §9.2 |
| Y-20 | §4.3; design §5.7 (v4.2); §9.2 |
| Y-21 | §12 |
| Y-22 | §8.3; §9.3 |
| Y-23 | §6.1; §9.1–9.4 |
| Y-24 | §5.2–5.4, §6 |

### 13.2 PSM v1 findings (`verification_filmkit-psm-v1_2026-10-09.md`)

| P | Settled in |
|---|---|
| P-1 | §6.5 closure, `Interval.open_at_end`; design SG-15, D25; §9.4 |
| P-2 | §4.3 `rerun`, §6.6, `_fk/rerun.py`; D28; §9.2 |
| P-3 | §4.3 `outputs`, §4.8, §8.2 `lab_check`, §9.3 wording |
| P-4 | §6.3 item 3; design SG-12 (v4.2), D26; R5; §9.2 |
| P-5 | §6.4 encoder `container_args`; D29; §9.2 |
| P-6 | §6.1 truth table; design §7.4b, FK-R-13 (v4.2); §9.2 |
| P-7 | §4.1, §7.2 FK-R-15 in M2; D27; timeline §6.9 updated |
| P-8 | §4.2 `local_files`, write timing, `pending_publish {sha256, bytes}`; §6.2 `capture_done`; §9.2 |
| P-9 | §5.2 `frame_count`; §9.2 |
| P-10 | design v4.2 (five write-backs) |
| P-11 | §4.10; §6.7 `kinds.py` |
| P-12 | §9.1 |
| P-13 | §9.2, §9.4 tables |
| P-14 | §9.2 (M0 ffprobe-timeout version), §9.4 (moved controls) |
| P-15 | §8.2 `round_kit_checks` (d); §8.2 selftest |
| P-16 | §8.3; §4.8 `instrument_limits`; §9.3 wording |
| P-17 | §6.0 retry; §4.4 `write_retry`; §9.2 |
| P-18 | §4.3 `unfinished`, `FK-R-5#length`, `FK-R-16` UNDET before M2 |
| P-19 | §4.5 scope, keys, provisional suffix; §6.6 sentence scan; §9.4 |
| P-20 | §6.2 exception policy; design §7.4 (v4.2); §9.2 |
| P-21 | (a)(d)(e) timeline §6.9 updated; (b) §3.2 rules data in M0; (c) §7.2 FK-R-15 eps |
| P-22 | §6.4 `close_stdin`/`wait`/`kill` |
| P-23 | §5.4, §6.2 `RecordStore`, §6.8 op interface, §8.1 M3 line |
| P-24 | §5.5 (a), §5.1 (b), §4.8 (c), §8.2 (d) |
| P-25 | (a) §4.2 caps; (b) §4.4 `sheet`; (c) §5.6; (d) §3.3 run_id partials; (e) §2; (f) §12 citation |

v1.1 re-verification (`verification_filmkit-psm-v1.1_2026-10-09.md`) graded P-1, 2, 4, 6, 11, 13, 16, 20, 21, 23 partial; each remainder is a Q-item below.

### 13.3 PSM v1.1 findings (`verification_filmkit-psm-v1.1_2026-10-09.md`)

| Q | Severity | Settled in |
|---|---|---|
| Q-1 | BLOCK | §6.3 item 3 family-level result; §4.10 `FamilyCheck`; §7.2 FK-R-6; §9.2 Arial/Segoe UI pure-CJK controls; design SG-12 (v4.3), §9 font row |
| Q-2 | FIX M0 | §9.2 `owner_state` unit controls, FK-R-6 FAIL control, lock row split; §9.3 FK-R-13 row, L4, L6; §9.5 L5 |
| Q-3 | FIX M0 | §4.2 `last_success` snapshot; §6.1 `owner_state` contract, `current_inputs`; §9.2 controls |
| Q-4 | FIX M0 | §4.3 `rerun` rules 1–7; §9.2 controls |
| Q-5 | FIX M0 | §4.3 `summary.internal_error`, `incomplete`; §5.5; §6.2; §9.2 control |
| Q-6 | FIX M0 | §4.10 `RenderArgs`, `ReportMeta`, `CheckSummary`, `ProfileArgs.name`, `RunSummary` for check, `Timeout`/`Interrupted`; §4.2 `ffmpeg_container_args`; §6.1 `input_hashes(page)` |
| Q-7 | FIX M0 | §6.3 item 3 (when, skip list, shadow root, `important`); §9.2 controls |
| Q-8 | FIX M0 | §3.3 (D30); design §5.3 hint, D30; §9.2 control |
| Q-9 | FIX M0 | §3.3 `.filmkit/*.tmp`; §6.0; §9.2 control |
| Q-10 | FIX M0 | §4.5 `film_types` from `film-types.md`; examples; timeline §6.9/§12 pointer |
| Q-11 | FIX M1 | §8.3 token matching and negative controls |
| Q-12 | FIX M2 | §6.5 clamp and one-audio-frame tolerance; §9.4 controls; design SG-15 (v4.3) |
| Q-13 | FIX M3 | §4.6 `inputs_sha256`; §6.4 `Publishable`; §9.5 |
| Q-14 | NOTE | §6.5 (accepted, one frame); §9.4 control |
| Q-15 | NOTE | §6.5 detection floor; §9.4 control |
| Q-16 | NOTE | §6.3 blind spot, README; design SG-12 |
| Q-17 | NOTE | design v4.3: old SG-12 row marked superseded, §9 scan row M2, §7.1 time fields, `FAILED(internal)` scope, lab output names |
| Q-18 | NOTE | §3.3 `lock.json` timing; §6.1 `write_lock_info`; §10; design §7.4 row 1 |
| Q-19 | NOTE | §6.5 `framelog=quiet`; §9.5 |
| Q-20 | NOTE | (a) §4.2 path form and sort; (b) §6.5 atom walk; (c) timeline §6.9 names `narration_lines`; (d) §4.5 README rule |

v1.2 re-verification (`verification_filmkit-psm-v1.2_2026-10-09.md`): pass-with-fixes, 0 BLOCK; Q-4, Q-8, Q-13, Q-15 graded partial, their remainders are R-1/R-2/R-3, R-4, R-8, R-7b below.

### 13.4 PSM v1.2 findings (`verification_filmkit-psm-v1.2_2026-10-09.md`)

| R | Severity | Settled in |
|---|---|---|
| R-1 | FIX M0 | §4.3 rule 1 (structured fields, not `cli`); §4.2 `last_success` path fields, `cli` note; §4.3 example; §9.2 three-cwd control |
| R-2 | FIX M0 | §4.3 rules 5–6 (`/` separators); §9.2 two folders × two shells control |
| R-3 | FIX M0 | §4.3 rule 2 `<new-out>`; §9.2 control |
| R-4 | FIX M0 | design v4.4: §7.4b draft text, D20, §7.4 row 1, FK-INV-9 aligned with D30 |
| R-5 | FIX M0 | §6.3 `sample_font_families`, "regardless of which scripts", coverage sentence in `check.md`, order after steps 4–5 |
| R-6 | FIX M0 | §9.2 undetermined, `decided_by == cjk`, restored-input, probe-placement controls; counts fixed; FK-R-11/12 part moved to §9.4 |
| R-7 | FIX M2 | §4.5 anchor reference points and `{floor_s}`; §6.6 `range_compare` signature; §6.5 mid-film clamp rule; §9.4 controls; design SG-15 (v4.4) |
| R-8 | FIX M3 | §4.6 `last_success.inputs`; §9.5 controls |
| R-9 | NOTE | §6.3 blind spots (README); design SG-12 (v4.4) |
| R-10 | NOTE | §4.2 de-duplication, change-during-capture note; §9.2 control |
| R-11 | NOTE | §7.2 FK-R-16 unknown film type → UNDET; §3.2 rules selftest compares with `film-types.md`; §9.4 control |
| R-12 | NOTE | §6.0 `check.py` temp file without creating `.filmkit/` |
| R-13 | NOTE | (a) design v4.4 post-publish paragraph; (b) §5.6; (c) §4.2 profile keys = `ProfileArgs`; (d) §8.3 blind spot; (e) §6.3 `all: initial`, one `getDocument` per moment; (f) §9.2 skip rule |

Not independently re-verified (user ruling 2026-10-09); M0's controls are the check.

## §14 使用者裁決紀錄（本 PSM 引用）

- D1–D4、D11–D15、D21、D24：設計 §12，照錄不改。
- 2026-10-09（PSM v1 驗證後）：D25 片尾目標「靜止、安靜」，掃描量得到持續到片尾的區間（P-1）；D26 字型改用指紋判定、中英文都查，正式片附開放授權的黑體字型檔（P-4）；D27 FK-R-15 留在 M2（P-7）；D28 補重出片指令（P-2）；D29 faststart 交由模型評估後定在編碼步驟（P-5）。
- 2026-10-09（PSM v1.1 重驗後，模型決定、可逆）：D30 `render.py -o` 的上層資料夾必須就是頁面資料夾，草稿用另一個頁面資料夾（Q-8）；字型改字族層級判定（Q-1，屬 D26 的作法修正，不改你的方向）。
- 2026-10-09（v1.2 重驗後）：使用者裁決出 v1.3、不再重驗，由 M0 施工卡的控制驗證。
- D18：待 M2 語料校準後裁決。
- 本 PSM 的模型決定（皆可逆，已記入 process ledger 或本文標 `PSM decision`）：以 00acb20 版 `run_arm.py` 為基準；SG-4 保護；規則資料檔 M0 建立；音視訊長度差容差 0.1 秒並獨立成 `FK-R-5#length`；片長必須是整數格；紀錄寫入重試 10 次、每次 0.05 秒；partial 檔名帶 `run_id`。

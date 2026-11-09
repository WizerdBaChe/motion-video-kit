# 分鏡分層 K/B/T ＋ 代理互審（設計，W35）

狀態：**設計 v1，M1–M5 已建成並試行，你已驗收試行**（2026-10-19；§8 已裁：Q1 試行片 `dit-promo`、Q2 你看試行片一次來判斷流程、Q3 片段窗長度維持暫定，等候池 W46；試行結果見 §7a）。模式：product-design-thinking Mode B（增能），層級：標準 (Standard)。
上游：`docs/storyboard-frame-roles-note.md`（K/B/T 構想，本文取代其 §4 的待決事項）、`docs/team-dispatch-notes.md`、`docs/timeline-layer-psm.md`、`~/.claude/skills/motion-video/references/build-and-export.md` §3。
動態原則研究：`docs/research/motion-principles-beyond-twelve-2026-10-19.md`（審查視角的來源，§5）。

## 0. 你的裁決（2026-10-19，process ledger 已記）

| # | 裁決 | 原話 |
|---|---|---|
| U-1 | 審查只在**製作代理**與**派工的主 session**之間互審，你不在審查迴圈裡 | 「製作代理以及"你"(畢竟是由你發派製作的項目窗)互審就好」 |
| U-2 | 重點是自由發揮；**只有禁止清單 (fail list) 是明確否定項**；每個重點幀改看它**前後幾秒的短片段**，看感覺即可，不要變成重做好幾次全片 | 「重點仍是自由發揮，只拿禁止清單當明確否定項…」 |
| U-3 | 核准過的片型／參考片是**白名單**，不是必須照做 | 「核准片型是白名單，但不是"必須照做"」 |
| U-4 | 3 輪後仍有擋件 → **交出最好的一版並標註** | 「出最好的一版並標註」 |

這些裁決在這條路徑上取代：lab INV-6 的「使用者驗收」、build-and-export §3 第 5 項（乾淨 context 子代理審）與第 7 項（好不好看由使用者看過決定）。CB-6（交付前要並排比對）保留，但並排結果只當參考，不擋件（U-2、U-3；CB-5 本來就寫「核准作品是審查參考，不是生成模板」）。

## 1. 第一性原理框架 (Phase 0)

1. **要解掉的痛點**：現在審查只在成片之後，而且要你看；分鏡是文字表，「這一段要被看清楚的那一刻」無處可指，所以每次修改都得重算整支片、重看整支片。
2. **不做會怎樣**：每一輪都要渲染並看整支片，你被綁在每一輪；團隊測試已經看到指揮只看靜止畫格、看不到時間上的問題（team-dispatch-notes 第四節）。
3. **核心（最小可用）**：
   - (a) timeline 的段 (Clip) 可以標出 K（關鍵畫面）／B（中間姿態）；段與段之間的接縫自動就是 T（過渡）。
   - (b) 審查單位是**片段窗 (window)**：每個 K 前後幾秒、每個 T 接縫前後幾秒，從**同一份成片頁面**渲染，不另畫示意稿。這樣就不會有「示意稿無法 100% 重現」的問題。
   - (c) 兩方互審協定：意見寫成檔案，嚴重度有明確規則，最多 3 輪。
4. **繼承下來的設計物件，逐一檢討**：

   | 既有物件 | 處理 | 理由 |
   |---|---|---|
   | 乾淨 context 審查子代理 | 換成派工主 session（U-1） | 派工者沒有寫程式，仍符合「審查者不是建置者」；代價是它和簡報 (brief) 有同一份偏見，所以審查只能讀成品產物，不能讀製作者的自述（INV-R3） |
   | 靜態 style frame 核准（構想筆記 §3） | 降級成 G1「只查硬項目」；感覺改在 G2 的片段窗看 | U-2：靜止畫格看不到感覺 |
   | 並排比對 (works_contract review) | 保留，只當參考 | U-3 |
   | INV-6「像不像要使用者驗收」 | 這條路徑上不再宣稱「像」，只宣稱「代理互審後交付」，並標明你沒看過 | U-1、U-4 |
   | 3 輪上限後交給使用者 | 改成交出最好一版＋標註 | U-4 |
5. **不做的事**：不加第三個審查者；不做自動品味分數；每一輪不重算整支片（整支片只在 G3 算一次，有 G3 修改才再算）；不強制模仿參考片；不新增聊天通道；Haiku 不參與（lab 裁決 2026-10-10）。
6. **層級**：標準 (Standard)。驅動因素：有持久化的狀態（審查紀錄、timeline 欄位）、外部消費者（skill、works_contract）、兩個執行者（但依序交替，沒有並行搶資源，所以不到全梯）。

## 2. 參考過的既有做法 (Phase 1)

- **內部**（決定：延伸，不另起一套）：timeline TL-0 已有 `approve --by model --questions`、`declares.holds`、`view`；filmkit `render.py`（頁面是時間的純函數 `__setTime`）、`sheets.py --boundaries`（前／中／後三格）；build-and-export §3 的審查規則（BLOCKER／POLISH、第幾秒／哪裡／怎麼改、從第 2 輪起先檢查上輪的修正）；works_contract `review`／`deliver`（`reviewer:` 只記錄、不判斷，所以新值不用改程式）；team-dispatch-notes（指揮看不到時間問題；SendMessage 恢復不會換模型；契約裡的泛用要求會被套到每個元素）。
- **外部**：動態設計流程裡 style frame → animatic 的順序、手繪動畫 key／breakdown／in-between（見構想筆記的來源）。用 `psearch` 搜尋 generator–critic 代理審查：只找到幾個小 repo，沒有可借鏡的成熟做法（依「借概念不借小 repo」的原則，不採用）。
- **差異**：外部流程的審查者都是人；我們要讓兩個代理互審，又要守住「只用禁止清單否決」，所以嚴重度規則（§4.3）是自己定的。

## 3. 概念模型（PIM-lite）

### 3.1 名詞表 (Glossary)

| Term | 中文 | 定義 |
|---|---|---|
| `Key` (role `key`) | 關鍵畫面 K | 一段裡要被看清楚、讀完的那一刻；可以帶 `hold` |
| `Key` (role `breakdown`) | 中間姿態 B | 同一段裡，決定動作怎麼走的那一刻（選填） |
| `Seam` | 過渡 T | 兩個相鄰畫面段之間的接縫；由 timeline 推導，不手寫 |
| `Window` | 片段窗 | `[t-pre, t+post]` 的短片，K 預設 1.5 s / 1.5 s，Seam 預設 1.0 s / 1.5 s（暫定，見 §8 Q3） |
| `Strip` | 畫格條 | 一個片段窗以 8 fps 取格排成的縮圖表；代理就是靠它「看」片段 |
| `Director` | 派工者 | 派工的主 session：寫簡報與分鏡、審製作者的產物，從不改片子的程式 |
| `Maker` | 製作者 | 子代理：審分鏡、寫頁面、渲染片段窗、回覆意見 |
| `Finding` | 意見 | 一條審查意見，寫在檔案裡 |
| `Gate` | 關卡 | G0 分鏡互審、G1 關鍵靜止畫面、G2 片段窗、G3 整片 |

### 3.2 不變式 (Invariants)

- **INV-R1** 每個畫面段至少有一個 `role: key`；沒有的段要合併或刪掉（構想筆記 §3）。檢查列 TV-19，先標 look（暫定）。
- **INV-R2** 片段窗與靜止畫面一律由成片頁面在對應的 t 渲染，絕不另外手畫或另寫示意稿。
- **INV-R3** Director 只根據產物（strip、still、check.md、片段窗 mp4）提出意見，不能引用 Maker 的自述來當成證據。
- **INV-R4** BLOCKER 的依據 (`basis`) 只能是：禁止清單的一項、filmkit 的擋件列、T05 產品忠實，或 §3 第 3 項列出的「正常大小與速度看一次就看得出」的瑕疵（斷肢、白閃、字被切到或寫錯、數字錯；另加「字讀不到」：由研究檔的 MG-5 對比與 MG-3 可見秒數量出失敗才算，那兩條原則在這裡借用為量測，不是品味）。感覺、品味、原則視角 → 只能是 POLISH。
- **INV-R5** Maker 可以拒絕 POLISH，但要附一行理由（U-2 自由發揮）；不能拒絕 BLOCKER，只能反駁 (`rebutted`) 依據不成立，由 Director 決定。
- **INV-R6** 每個關卡最多 3 輪；第 3 輪結束還有未解的 BLOCKER → 往下走並標註，交付的 verdict 列出全部未解項目（U-4）。
- **INV-R7** 整片渲染只在 G3 發生；G2 每輪只重算被改到的片段窗。
- **INV-R9** 涵蓋率：每輪 findings 對本輪渲染的每個片段窗都有一行（意見，或 `none` 加上看了什麼）（§8b P-1）。
- **INV-R10** 一條意見只指一個元素並寫出幅度，不寫全片泛用規則（§8b P-3）。
- **INV-R8** 交付的 `verdict.md` 第一行是 `reviewer: dispatcher-main-loop`，並帶 `user_watched: no` 和 `unresolved:` 清單。

### 3.3 流程狀態機 (statechart)

```
BRIEF ─G0─> STORYBOARD_AGREED ─G1─> KEYS_OK ─G2─> WINDOWS_OK ─G3─> DELIVERED
  each gate: OPEN → (round n: findings → response → recheck)* → PASSED | PASSED_WITH_OPEN (n = 3)
  any edit to film.timeline.json after STORYBOARD_AGREED that adds/removes a Key or Seam
  → back to G1 for the touched clips only
```

| 關卡 | 誰審誰 | 看什麼 | 能擋什麼 |
|---|---|---|---|
| **G0 分鏡互審** | Maker 審 Director 的 `film.timeline.json`（這就是「互審」的反方向） | 能不能做、哪裡寫得模糊、有沒有違反禁止清單、每段有沒有 K；片型骨架的必備列有沒有寫進分鏡（科普片：約 3 秒內宣告主題、從屬類比、結尾呼籲＋結尾卡，`film-types.md` §3；2026-10-19 fanout v1 三項全漏而四關都沒抓到） | 違反禁止清單、做不到的要求；其餘是問題，不是擋件 |
| **G1 關鍵靜止畫面** | Director 審 Maker | 每個 K 在其 t 的靜止畫面：字讀得到、沒被切到、產品畫面正確、禁止清單；類比物件在這個姿態下仍符合自己的物理構造（2026-10-20 v2.1：半收的扇子扇骨和扇面分家，G1 漏看）；結尾幾拍有沒有同一句重複出現 | INV-R4 的硬項目；**不判斷好不好看** |
| **G2 片段窗** | Director 審 Maker | 每個 K 窗與 Seam 窗的 strip（加上原則視角 §5）＋ 量測工具：`blurdip`／`shapematch` 量接縫、`density` 量畫面滿度 | 硬項目 BLOCKER；感覺 → POLISH |
| **G3 整片** | Director 審 Maker | `check.md`、1 fps 縮圖表、`works_contract review` 並排圖（參考） | filmkit 擋件列、硬項目 |

## 4. 互審訊息怎麼傳（你問的「代理之間的安排與 message 方式」）

### 4.1 載體：檔案，不是對話

所有意見都寫在片子資料夾的 `review/` 底下；派工呼叫 (Agent／SendMessage) 只說「讀哪個檔、回到哪個檔」。理由：
- **可稽核**：每一輪留下紀錄，壓縮上下文 (compaction) 後也不會遺失。
- **審查只看產物**：Director 不需要讀 Maker 的對話內容。
- **符合現況限制**：SendMessage 恢復時不會換模型，而且 lab 的 arm 不保留 session（team-dispatch-notes 1d）。
- **同一套協定兩處通用**：在 lab arm 裡和正式片裡都能用。

Maker 在同一支片內用 SendMessage 接續，保留它的建置上下文；換片就開新的 Maker。

### 4.2 檔案

```
<film>/review/
  G<g>-<n>.findings.json    Director → Maker  (gate g, round n)
  G<g>-<n>.response.json    Maker → Director
  G0-<n>.findings.json      at G0 the roles swap: Maker writes findings on the storyboard
  windows/<id>.mp4, windows/<id>.strip.png, stills/<key id>.png   rendered by review.py
  LOG.md                    GENERATED by review.py log; never hand-edited
```

### 4.3 Finding schema (English; quoted verbatim downstream)

```json
{"schema_version": 1, "gate": "G2", "round": 1, "author": "director|maker",
 "artefacts": [{"path": "review/windows/K-S03a.strip.png", "sha256": "…"}],
 "findings": [{
   "id": "G2-1-03",
   "at_s": 12.4, "where": "headline, upper left", "change": "hold the headline 0.4 s longer before the cards enter",
   "severity": "BLOCKER|POLISH",
   "basis": {"kind": "fail_list|filmkit_row|fidelity|seen_once|principle|feel", "ref": "<fail id | FK-R-n | claim id | defect name | principle id | ->"},
   "recheck_of": null}]}
```

回覆檔 `response.json`：每條意見對應 `{id, status: fixed|declined|rebutted, note}`；`declined` 只能用在 POLISH（INV-R5）。`review.py check` 會拒絕下列情況：BLOCKER 的 `basis.kind` 是 `principle` 或 `feel`（INV-R4）、對 BLOCKER 回 `declined`、artefact 的 hash 跟現在的檔案對不上、進到第 4 輪。

### 4.4 一輪怎麼走

1. Maker 渲染（G1：still；G2：被動到的片段窗；G3：整片），然後回報「已完成」，不附自評。
2. Director 依 §3.3 的表讀產物，寫 `findings.json`；從第 2 輪起，先用同一秒、同一位置的前後對照檢查上一輪的修正（build-and-export §3 第 4 項）。
3. Director 用 SendMessage 呼叫 Maker：「讀 `review/G2-1.findings.json`，修改後回 `review/G2-1.response.json`」。
4. 沒有未解的 BLOCKER → 這一關通過；第 3 輪後仍有 → `PASSED_WITH_OPEN`，未解項目帶到交付（INV-R6）。

## 5. 審查視角：動態原則

研究結果（十二法則以外的動態設計、UI 動態、剪接、知覺、構圖原則）寫在 `docs/research/motion-principles-beyond-twelve-2026-10-19.md`。每條原則標出它能在哪裡看到：`K`、`B`、`T`、`FILM`。施工時把排名前段的原則濃縮成 `docs/review-lens.md` 的一張表：G1 用 K 欄、G2 用 B/T 欄、G3 用 FILM 欄。原則只決定**要看哪裡、POLISH 怎麼寫**，從不構成 BLOCKER（INV-R4）。只有被收進禁止清單的項目，才會變成否決依據。

研究結果（84 條實列，前 15 名見該檔 §4）：可機械計算的 MG-5（動底對比）、MG-3（字的可見秒數）、MG-2（同時一個主角）、MG-9（畫面方向）、COMP-5（網格對齊）、UXM-1（緩動）、GST-5（共同命運）先做成 G1／G2 的提示檢查，其餘當提問式提示。每條上線前先用已知真、假樣本各一確認會觸發（gate 校準）。研究檔 §5「機械套用會誤導」的清單（例如「什麼都不能完全靜止」→ 全片抖動，這是 lab 自己的失敗）也列入 `review-lens.md`。未取得原文的列標 `unfetched`，引用前要補查。

## 6. 登記清單 (registration set)

| 位置 | 改什麼 |
|---|---|
| lab `CLAUDE.md` 〈Rulings〉 | U-1…U-4 一列，`home:` build-and-export §3 |
| `~/.claude/skills/motion-video/SKILL.md` 第 4、8 步 | 分鏡帶 K；審查改為 G0–G3、兩方互審 |
| `build-and-export.md` §3 | 加上代理互審路徑（第 5、7 項的例外）、片段窗、嚴重度規則 |
| `docs/timeline-layer-psm.md` | 增補 `keys[]` 與 TV-19 |
| `tools/filmkit` | `render.py --start`、`--still`（INV-7） |
| `works_contract.py` review 頁的說明文字 | 允許 `reviewer: dispatcher-main-loop` 與 `user_watched: no` |
| `waiting/pool.json` W35 | 改成「設計中 → 施工中」 |
| `docs/storyboard-frame-roles-note.md` | 狀態行改成「已由 agent-review-kbt-design.md 取代 §4」 |
| `lab-skill-sync` | 寫回 skill 之後執行 `sync.py mark motion-video` |

## 7. Build section (PSM-lite, English spec body)

**M1 — timeline `keys[]` (INV-8 selftest).**
- Files: `tools/timeline/_tl/model.py`, `tools/timeline/film.timeline.schema.json`, `_tl/validate_static.py`, `_tl/resolve.py`, `_tl/view.py`, `selftest.py`, `docs/timeline-layer-psm.md` §4.1 / §7.
- Contract: Clip and OverlayClip gain optional `keys: [{id: ^K[A-Za-z0-9-]{1,15}$ unique film-wide, at: number in clip time 0 ≤ at ≤ d_author, role: "key"|"breakdown", hold?: number ≥ 0, what: non-empty string}]`.
- `resolve` emits `keys[]` with film time (`t_f` frames) and `seams[]` = every picture boundary `{id: "T-<prev>-<next>", t_f, transition: <resolved transition_in of next>}`.
- New row TV-19: a picture clip without a `role: key` entry → look (provisional).
- `view` lists keys and seams per clip.
- Selftest: +3 valid fixtures (with keys, breakdown only + key, overlay keys), +4 invalid (duplicate key id, `at` > d_author at timed, empty `what`, unknown role); TV-19 positive (clip without key fires) and negative (clip with key silent).
- Rollback: the field is optional; reverting the commit leaves old timelines valid.

**M2 — filmkit windows (INV-7 both selftests).** *As built (2026-10-19), three deviations, each smaller than the spec:*
- only `--start S` was added; there is no `--still`, because a still is a one-frame window with `--keep-frames`;
- `--start` refuses `--audio`: windows are silent, since agents read them as frames;
- there is no new `window` profile, because `lab-round` already reports length and end-hold rows as info.

Filmkit allows one output per page folder, so `tools/review` renders from a temporary sibling copy of the page folder.

*Original spec:*
- `render.py` gains `--start S` (frame k renders `__setTime(S + k/fps)`; `--audio` trimmed with `ffmpeg -ss S -t D`, the original untouched) and `--still T` (one PNG, no MP4, no check).
- New profile `window` in the rules file: format rows only; end-hold, loudness and length rows `info`.
- Controls:
  - positive: a page drawing `t` as text, `--start 5 --duration 1` → first frame OCR/pixel reads 5.00;
  - negative: without `--start` → 0.00;
  - `--still 2.5` equals frame 75 of a 30 fps full render (pixel hash).

**M3 — `tools/review/` (new; selftest required before commit).** *As built: strips and stills are named by their content hash (`strip-<sha8>.png`). Without that, a re-render had overwritten the strip an earlier round had judged, and P-4 then refused every earlier round; the selftest caught this.*
- CLI `review.py`:
  - `windows <film> [--only id,..] [--pre/--post]` renders the windows plus `strip.png` (8 fps, 6 cols) from `build/timeline.resolved.json`;
  - `stills <film>`;
  - `new <film> G<g>` creates an empty findings file with artefact hashes;
  - `check <film>` enforces §4.3 (exit 1 on violation);
  - `log <film>` generates `LOG.md`;
  - `verdict <film>` writes `deliver/_review/verdict.md` with `reviewer: dispatcher-main-loop`, `user_watched: no`, `unresolved:` (INV-R8).
- Selftest controls:
  - a BLOCKER with `basis.kind: feel` → exit 1;
  - `declined` on a BLOCKER → exit 1;
  - a stale artefact hash → exit 1;
  - a round 4 → exit 1;
  - a window rendered this round with no findings line (INV-R9) → exit 1;
  - a finding whose `where` is empty or names the whole film (INV-R10) → exit 1;
  - a clean round → exit 0.

**M4 — write-backs.** Every row of §6, plus `docs/review-lens.md` built from the research file's ranked list (K/B/T/FILM columns, `principle` ids).

**M5 — pilot.** One formal film end to end on this path. Recorded in `review/LOG.md` plus a one-page report:
- rounds per gate;
- number of whole-film renders (target ≤ 2);
- unresolved count at delivery;
- Director/Maker token totals.

**Acceptance (machine):** INV-7, INV-8 and the review selftest exit 0; on the pilot, `review.py check` exits 0 and `works_contract.py deliver` accepts the verdict.
**Acceptance (process, §8 Q2):** the pilot report.

## 7a. 試行結果（M5，dit-promo，2026-10-19）

| 項目 | 結果 |
|---|---|
| 各關輪數 | G0 1、G1 3、G2 2、G3 2 |
| 整片出片次數 | 3（製作者自測 1、G3 正式 1、FK-R-19 修好後重出 1；後兩次畫面相同）；目標 ≤ 2，多出的 1 次來自工具擋件，不是審查 |
| 交付時未解項 | 0（G3 第 1 輪的 FK-R-19 擋件在工具層修好：`works_contract.py attach`） |
| 審查者（主 session）意見 | 8 條（G1 4、G2 4），全部修好；從沒出過擋件。r22 的「審查照單全收」失效條件沒有觸發 |
| 製作者 token | G0 約 19 萬、建片約 26 萬、每輪修改 30 萬以上 |
| 試行找到的工具缺陷 | review.py 4 個（G0 分鏡快照、LF 換行、片長精度、G3 成片快照），各有控制組；works_contract 缺 attach 1 個 |
| 偏離設計 | 製作者用 sonnet＋high（opus 被 model_cap_guard 擋）；沒跑 fidelity.py（沒有語料庫，畫面文字由審查者逐條讀）；授權行出處寫在 E1 `what`（W44） |
| 你的判斷（Q2） | 「完成度很高，雖然沒什麼創意性(這類片的通病)，但說明的節奏跟內容算是完整。可能分鏡有效。我已驗完。」 |

## 7b. 關係窗 R（2026-11-03，鏡頭間關係探針之後）

- **你的裁決**（2026-11-03，s:675370d5）：「可以先進審查階段」。探針報告在 `experiments/probe-inter-shot-relation-2026-11-03/REPORT.md`。時間軸 schema 先不動。
- **為什麼要有 R 窗**：K 窗和 T 窗只看片中的一個地方。關係是兩個相隔很遠的地方互相呼應，例如回呼、首尾呼應、回放、母題、伏筆與回收，所以這兩種窗都看不到。探針的結果是：便宜的重現偵測只抓到 4/8；把兩端並排讀時，種類判對 12/14，偵測器漏掉的變形回歸也讀回來了。
- **怎麼運作**：
  - Maker 在 G0 寫 `review/relations.json`，宣告這支片「想要」的關係。片子沒有關係時寫空清單，並附上 `none_reason`。
  - G2 開輪前一定要有這個檔（預設開啟，不靠記得）。
  - `windows` 為每條關係產生一張配對圖：A 列、B 列各三格。Director 照 INV-R9 對每張配對圖寫一行。
- **擋不擋件**：R 窗的意見照 INV-R4 走。「關係沒做到」屬於感覺或原則，只能是 POLISH，除非分鏡把這條關係寫成交付項目。
- **還沒做的**：
  - 偵測器候選目前只能手動貼進檔案；探針程式留在 `experiments/`，不進 `tools/`，因為召回還不夠。
  - 接縫方向（T 窗量 A 入、B 出的方向與速度）已經在 C57 實測可行，見同一份探針報告的〈補充〉，但還沒接進 T 窗。

## 8. 留給你的問題

- **Q1 試行用哪支片**：建議 `dit-promo`。它已經有 timeline，而且是產品片，T05 的硬項目能真正被測到。
- **Q2 試行片要不要看一次**：你看的是「這套流程有沒有用」，不是在審這支片。建議看一次；之後的片都照 U-1，你不在迴圈裡。
- **Q3 片段窗長度**：K 前後各 1.5 s、接縫前 1.0 s／後 1.5 s 是暫定值，試行後用實際輪數再調。

## 8b. 前例與衝突（2026-10-19 補查：statelint grep、recall、lessons、lab 實驗紀錄）

結論：沒有找到使用者**否決過**「代理互審」或「模型核可」的裁決。找到的是一個**實測失敗前例**和幾條既有規則的衝突，處置如下。

| # | 前例／規則 | 出處 | 跟本設計衝突在哪 | 處置 |
|---|---|---|---|---|
| P-1 | **指揮審 worker 等於蓋章**：16 個團隊臂退件全是 0，指揮看到問題也沒有退回 | `experiments/r22-haiku/REPORT.md` 第 81 行；`docs/team-dispatch-notes.md` 第四節 | 本設計的 Director 正是同一種角色，最可能失效的點就在這裡 | 新增 **INV-R9**（涵蓋率）：每一輪的 findings 必須對本輪渲染的**每一個**片段窗寫一行，可以是一條意見，也可以是 `none` 加上「看了什麼」，否則 `review.py check` 拒絕（exit 1）。試行時，Director 三關合計 0 條意見就判定設計失效，回到設計（§9） |
| P-2 | **指揮只看靜止畫格，看不到時間上的問題** | 同上 | 原本的 style frame 審查也是靜止的 | 已處理：G2 改看片段窗的 8 fps 畫格條，加上量測工具（U-2） |
| P-3 | **契約裡的泛用要求被套到每個元素**（「停留時不能完全靜止」→ 全片抖動） | team-dispatch-notes 第四節；研究檔 §5 第 1 條 | POLISH 意見如果寫成泛用規則，會重演這個失敗 | 新增 **INV-R10**：一條意見只能指一個元素，並寫出幅度（`where` 加 `change`），不能寫「整片都要…」；`review.py check` 拒絕 `where` 為空或寫成全片的意見 |
| P-4 | **手寫的審查紀錄宣稱跑過其實沒跑的檢查** | lessons L-135、L-012 | Director 可能只寫了 verdict，沒有真的打開畫格條 | 已處理：artefact hash 對得上才放行（§4.3），加上 INV-R9 的涵蓋率 |
| P-5 | **模型寫的覆寫一律無效**；`approve --by model` 遇到任何覆寫都擋 | `docs/timeline-layer-design.md` 第 287、293 行（D-T21） | 你不在場時，元件衝突沒有人能放行 | **保留不放寬**。這條路徑上覆寫等於不可用；元件衝突只能改內容來解決，解不掉就算 BLOCKER |
| P-6 | **U-4「出最好一版」的範圍** | 你的 U-4；filmkit `delivery-web` 擋件列、TV-18、`works_contract deliver` | 工具層的擋件（尺寸、單聲道、核可必填欄位）如果也被「出最好一版」帶過，就會交出格式錯誤的檔案 | 我的判定（可逆，已記 ledger）：U-4 只涵蓋**審查意見**；工具層擋件照樣擋。它們都是機械性的錯誤，一定修得好 |
| P-7 | **CB-2**：看不到渲染的階段只能寫「出現什麼」，不能寫位置 | `~/.claude/rules/creative-brief.md` | Director 在 BRIEF／G0 階段寫分鏡時看不到渲染畫面 | Director 的分鏡不寫位置和 px；位置只出現在看過 still 或片段窗之後的 findings 裡。CB-2 的 `review-when`（生成階段看得到自己的渲染時收窄）就是被 G1 觸發的事件，M4 時回寫該規則 |
| P-8 | **CB-3**：方向性規則要同時寫出反向界線 | 同上 | 反覆出現的 POLISH 被收進禁止清單時，可能只寫了單一方向 | 從意見升級成禁止清單的那一刻，必須同時寫出反向界線，並用一支核准片、一支否決片校準 |
| P-9 | **INV-F6**：審查者 ≠ 建置者；同一 session 時由乾淨 context 的子代理審 | `~/.claude/references/formal-path-governance-design.md` 第 183 行 | 你的 U-1 把審查者改成派工的主 session | **不衝突於第一句**：建置者是 Maker 子代理，主 session 不是建置者。只有「乾淨 context」這個形式被 U-1 取代；`reviewer:` 欄位工具只記錄、不判斷，所以不用改程式 |
| P-10 | **外部意見不能取代獨立驗證；沒有儀器的缺陷類別要先造儀器** | memory `external-review-vs-verifier-pass`（a research project, 2026-09-13） | 你退出迴圈後，「時間上的問題」只剩代理用眼睛看 | M3 先把 `blurdip`、`shapematch`、`density` 接到 G2，當成提示；抖動目前沒有儀器，列為已知缺口（§9） |

## 9. 這份設計什麼時候成立、什麼時候會被推翻

- **成立條件**：代理能從 8 fps 的畫格條判斷出節奏與接縫的問題。
- **會被推翻的情況（一）**：試行時，Director 三關合計 0 條意見（r22 的蓋章模式重演）。
- **會被推翻的情況（二）**：試行時，你看片發現的時間類問題（抖、拖、轉場突兀），兩方互審都沒抓到。這正是 team-dispatch-notes 記錄過的盲點；真的發生的話，G2 要加上量測工具的硬門檻，或改用更密的取格。
- **證據等級**：上面兩點都是主張 (claim)，尚未量測。

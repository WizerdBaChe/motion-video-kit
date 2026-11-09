# 證據（EVIDENCE）

這份說明這次發版實際量了什麼、每條方法規則從哪來、哪些由程式強制、哪些不宣稱。
行號以 v1.0.0 的 `reference-impl/` 為準，每次發版重新核對（發版步驟 2）。

## 實測（v1.0.0）

環境：Windows 11、Python 3.12.7、numpy 2.5.2、scipy 1.18.0、matplotlib 3.11.1、opencv-python-headless 4.12.0.88、pillow 12.3.0、
playwright 1.62.0、OpenTimelineIO 0.18.1、ffmpeg 在 PATH。以上為 `verify/controls_run.txt` 環境行印出的版本；授權見 `THIRD_PARTY_NOTICES.md`。

**驗收控制（`verify/controls_run.txt`）：14 列全部 OK。** 每一列都印出「應有值」與「實際值」，突變版必須讓實際值改變：

| id | 正確版（實際值） | 突變版（實際值） |
|---|---|---|
| K1 | `reference-impl/` 141 個檔案的位元組與 `verify/reference-impl.sha256` 相同：141 files, 0 differ | K1-neg：在暫存副本多附 1 個位元組：1 file differs |
| K2 | `filmkit/selftest.py --smoke`：45 pass, 0 fail, 0 skipped；陽性對照 23 個確實觸發 | 內含（selftest 的每個 `[negative]` 臂都跑已知為假的輸入） |
| K3 | `filmkit_rules_selftest.py`：43 pass, 0 fail；陽性對照 27 | K3-neg：規則檔拿掉 hype-ad 片種：42 pass, **1 fail**，exit 1 |
| K4 | `tools/timeline/selftest.py`：201 pass, 0 fail；陽性對照 114 | K4-neg：schema 的 `schema_version` const 改為 2：selftest exit 1，`schema agreement` 臂報出 validator `[]` 對 schema `['$.meta.schema_version: const']` 的差異 |
| K5 | `tools/review/selftest.py`：43 pass, 0 fail；陽性對照 33 | K5-neg：拒絕規則 id INV-R4 在 review.py 全部改名：41 pass, **2 fail**，exit 1 |
| K6 | `tools/edit/selftest.py`：16/16 controls hold | 內含 |
| K7 | 27 支量測儀器的 `--selftest`：27 exit 0 | K7-neg：phaselock 的 `lock()` 永遠回「未鎖定」：selftest exit 1（KeyError `mean_phase_ms`） |
| K8 | 範例片經 `tl.py validate --static` / `resolve` / `validate --timed`：exit 0 x3，blocking 0 與 0 | K8-neg：`decisions.energy.value` 改成 `frantic`（不在 calm / lively / hype）：exit 2，1 blocking |

`--full` 另跑完整的 filmkit 自我測試（原環境 441 項；乾淨環境下需要作品契約目錄的檢查會回報 skip，所以數字不同，不計入）。

**K7 的 27 支儀器各自證明了什麼：** 每支的 `--selftest` 餵入一個已知為真的合成輸入與一個已知為假的合成輸入（例如 phaselock 的合成節拍序列：鎖定與未鎖定），
要求兩者的判定相反。這證明的是儀器在合成資料上辨得出差別，**不是**它在真實影片上量得準；真實影片上的量測紀錄是原環境的，沒有隨附（見「不宣稱」）。

## 規則來源（origin records）

這些規則不是一次寫成的，而是原作者在一輪輪實際做片、被使用者看片後退回、再把退回原因寫成規則留下的。來源紀錄留在各檔案的出處行（provenance line），日期與 lesson id 保留：

- **證據等級**（`skills/motion-video/references/evidence-and-instruments.md` §Tiers）：每條規則標 user（使用者看片判斷）、measured（校準過的儀器在來源影片上量到）、
  verified（盲測 A/B 讓指標移動、區間不重疊）、unvalidated（量過但沒被模仿驗證）。
- **導演表層**（`docs/timeline-layer-design.md`、`docs/timeline-layer-psm.md`）：2026-10-08 使用者定案「分鏡表的載體是 JSON 加一頁產生的唯讀檢視頁」，
  再由後續幾輪補上關鍵幀（key / breakdown）、轉場視窗、`uses` 與核准紀錄。
- **渲染與驗片**（`docs/filmkit-psm.md`）：「每一格是時間的純函式、通過驗證才發佈檔名」來自手寫截圖腳本輸出壞檔仍被當成成品的事件。
- **審片迴圈**（`docs/agent-review-kbt-design.md`）：2026-10-19 使用者定案「使用者只給方向與設計內容；製作者建、派工者審且不改片」，
  G0–G3 四關、最多 3 輪、只有四類依據可以擋（INV-R4）。
- **剪輯路線**（`docs/edit-route-design.md`）：2026-10-18 使用者定案素材與生成媒體走剪輯路線、不是時間驅動頁面；沒有出處檔就拒絕渲染。
- **字的動態語彙**（`docs/text-motion-vocabulary.md`）：2026-10 一輪盲測發現「動態的名字」在目錄與業界的意思衝突時，會被做成業界的意思；因此名字要附描述。
- **量測儀器**：每支儀器的來源紀錄在其 docstring（例如 `tools/shotstats.py` 開頭）；其中一支的鏡頭切點偵測重新實作了 PySceneDetect 公開方法，並說明改了哪一處。

## Enforcement map

「程式強制」= 違反時腳本判 FAIL / blocking / 拒絕（只警告的就標 note）；「process only」= 寫在 SKILL.md 或設計文件裡，靠代理人遵守，沒有腳本判。路徑皆在 `reference-impl/` 之下。

| 方法規則（出處） | 強制方式 | 位置 |
|---|---|---|
| 導演表的 `energy` 只能是 calm / lively / hype（whole-film-rules §0） | 程式強制（schema 驗證，blocking） | `tools/timeline/film.timeline.schema.json:68`；K8-neg |
| 導演表所在資料夾名稱必須等於 `meta.film_id`（TV-1） | 程式強制（blocking） | `tools/timeline/_tl/model.py:196` |
| 導演表的時間關係成立（無循環、段落不越過片尾，TL-INV-2、SEM-11） | 程式強制（blocking） | `tools/timeline/selftest.py:697`、`:722` 驗證其行為；檢查在 `tools/timeline/_tl/validate_static.py` 與 `tools/timeline/_tl/model.py` |
| 必填的決定（受眾、能量…）沒填 | 只是備註，不擋：`tl.py validate` 印 `decisions unset: ...`，exit 0 | `tools/timeline/tl.py:160` |
| 導演表經使用者核准才開始建頁面 | 部分：核准是檔案裡的紀錄（`tl.py approve`），沒有簽章；「沒核准不准建」是流程規則 | `tools/timeline/_tl/approve.py:90`；SKILL.md「Order of work」第 4 步 |
| 動手前先問使用者用途、受眾、能量；沒人可問時寫 `build/questions.md` | process only | `skills/motion-video/SKILL.md` 步驟 0 |
| 每支片先定一個受眾、一個基調、一個底色 | process only（導演表只檢查格式，不判斷選得好不好） | `skills/motion-video/references/whole-film-rules.md` §1 |
| 成品檔先驗證、通過才發佈檔名；失敗時保留前一版並標為過時 | 程式強制（exit 1 = 沒發佈新檔） | `tools/filmkit/render.py:3`、`:55`；`tools/filmkit/_fk/verify.py` |
| 成品檔的容器、長度、畫面尺寸、像素格式與編碼、音訊在場（FK-R-1 至 5） | 程式強制（FAIL / blocking） | `tools/filmkit/_fk/judge.py:94`–`:101` |
| 正式片（delivery-web）必須是作品庫開過的項目且掛載未過期（FK-R-18、FK-R-19） | 程式強制（blocking），需要原環境的作品契約目錄，乾淨環境下 skip | `tools/filmkit/selftest.py:2052` 驗證其行為 |
| 響度只回報事實；對照平台目標要明示規則檔與目標名（FK-R-17） | 程式強制（info）；平台目標數字是規則檔裡有來源與 `review_when` 的主張 | `tools/filmkit_rules.json`；`tools/filmkit_rules_selftest.py` |
| 片種清單（intro / hype / tour / showreel / explainer / profile reel）與規則檔一致 | 程式強制（rules selftest 比對 `film-types.md`） | `tools/filmkit_rules_selftest.py`；K3 / K3-neg |
| 審片只有四類依據可以擋片：失敗清單、filmkit 列、產品真實性、重複出現的缺陷（INV-R4） | 程式強制（拒絕其他依據的 BLOCKER） | `tools/review/review.py:36`、`:400`；K5-neg |
| 每一關最多 3 輪，之後帶著未結項目放行（INV-R6） | 程式強制（Refused） | `tools/review/review.py:33`、`:350` |
| 審片者不是製作者；判定首行寫 `reviewer:` | 部分：review.py 寫入判定檔首行，但不驗證真有第二個身分 | `tools/review/review.py:525`；`skills/motion-video/references/build-and-export.md` §3 |
| 剪輯路線每個素材都帶出處檔，否則拒絕渲染 | 程式強制（`ValueError` / verify 回報缺檔） | `tools/edit/assets.py:66`、`:88` |
| 每支量測儀器對已知為真與已知為假的合成輸入給出相反的判定 | 程式強制（`--selftest`，K7） | 各 `tools/<name>.py` 的 `--selftest`；例：`tools/phaselock.py:61` |
| 「段落換在拍子上」「旁白下運動不中斷」「鏡頭有動」等判語要用儀器量成品檔 | process only：SKILL.md 規定用哪支儀器，沒有腳本強迫你跑 | `skills/motion-video/SKILL.md`「Verdicts this skill may give」 |
| `reference-impl/` 與發佈的位元組一致 | 程式強制（K1，sha256 逐檔） | `verify/run_controls.py:90` |
| 規則的證據等級要如實標示，不把 unvalidated 說成已證明 | process only | `skills/motion-video/references/evidence-and-instruments.md` §Tiers |
| 器件基調與整片基調衝突時換器件、不換基調 | process only | `skills/motion-video/SKILL.md` 步驟 5 |
| 影片好不好看、是否抓住眼球 | 不宣稱（沒有儀器；要人看） | — |

## 不宣稱

- 不宣稱影片品質：量測儀器回答的是可量化的問題（節拍對齊、運動密度、鏡頭是否在動、數字是否真實）；是否好看、是否打動目標受眾，沒有任何控制項驗過。
- 不宣稱儀器在真實影片上量得準：K7 只證明儀器在合成的已知輸入上辨得出真與假；原環境在真實影片上的校準紀錄沒有隨附。
- 不宣稱 `unvalidated` 等級的規則成立：它們是在來源影片上量到的現象，沒有被模仿實驗驗證過。
- 不宣稱核准有防偽：導演表的核准、審片判定的 `reviewer:` 行都是檔案裡的文字；**威脅模型：這些閘門是防代理人粗心的安全帶，不是防蓄意規避的圍欄。**
  代理人可以自己寫核准紀錄、改掉 selftest 與被測程式碼。閘門擋得住漏填、格式錯、壞檔、沒驗證就發佈；擋不住刻意繞路。
- 不宣稱在 Windows 以外能跑；macOS / Linux 沒有實測。
- 不宣稱完整 filmkit 自我測試在乾淨環境的數字：需要原環境作品契約目錄的檢查（FK-R-18、FK-R-19）在乾淨環境 skip，所以 `--full` 的通過數與原環境的 441 不同。
- 不宣稱生成素材路線可用：需要本機 ComfyUI 與模型檔；公開版只驗證 mock 轉接器與出處檔的檢查。
- 不宣稱公開的五支成品影片可由本 repo 完全重現：只有說明動畫的頁面隨附；其餘四支只提供成品。
- 影片的音軌在公開版已移除（宣傳片、產品介紹），所以節拍對齊與旁白相關儀器沒有在公開的 MP4 上示範。

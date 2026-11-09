---
layer: design
audience: user + builder
version: v4.5 (2026-10-11)
status: Concept Note + PIM-lite (with DSL semantic contract); v1 BLOCKED (verification_timeline-layer-design-v1, 10 BLOCK); v2 BLOCKED (verification_timeline-layer-design-v2, 5 BLOCK W-1..W-5); v3 applies the v2 report's minimum action set 1–7, closes W-8..W-21 in text, and records user rulings W-6/W-7/W-21; v3 BLOCKED (verification_timeline-layer-design-v3, 2 BLOCK X-1/X-2 + user ruling X-3); v4 fixes X-1/X-2, applies user rulings X-3 (D-T22) and X-17, closes X-4..X-18 in text; v4 focused re-verification BLOCKED on one leftover line (Y-1); v4.1 removes it and closes Y-2..Y-9 in text; per the v4 report, v4.1 re-verified PASS-WITH-FIXES (verification_timeline-layer-design-v4.1, 0 BLOCK, 8 should-fix Z-1/Z-3..Z-9 to the PSM trace table); v4.2 applies user ruling Z-2 (D-T19 restored to full mute); v4.3 applies D-T23 (`tail` 3.0 → 2.0 s after the user's W30 end-hold ruling 1.5–2.5 s) and records the per-section rework extension (§11); v4.4 writes back the text residues Z-1/Z-3..Z-9 that the PSM settles (§14.7); v4.5 applies the user's 2026-10-11 Haiku ruling to D-T12 (PSM §0 q4, U-2); PSM v1 = docs/timeline-layer-psm.md
tier: 標準 Standard (product-design-thinking Mode B) — see §0.4
host: motion-video-lab; sits UPSTREAM of filmkit (docs/filmkit-design.md v4.1 + docs/filmkit-psm.md v1, on main)
---

# 時間軸層 (timeline layer) 設計：導演表 → 時間軸 → 元件 → 出片

這份文件設計 motion-video 的**製作層**：把「整支片的決策＋每一段放什麼、何時、用什麼手法」寫成一份有格式、可驗證的時間軸檔，再由確定性的程式組成頁面、排好聲音，交給 filmkit 出片與檢查。目標是讓同一份需求反覆做出來的片，**結構、時機、基調穩定**（§8.3 給出量法），只把該自由的部分留給模型發揮。

讀法：結論在 §0；業務層 §1；先例 §2；放在哪、誰呼叫 §3–§4；交互 §5；內部架構 §6；語意契約 §7；驗證、里程碑、缺口、決策在 §8–§12。英文的 ID、欄位名、狀態名給程式與後續規格引用，不翻譯。

**v2 變更**（依驗證報告 `verification_timeline-layer-design-v1_2026-10-09.md`，以下 V-n、SG-n 皆指該報告）：

- **孤兒補祖先**：新增 BR-13 意圖對量測（V-1）、BR-14 設計規則檢查（V-2c）、BR-15 混音音量（V-2b）、BR-16 可重現（TL-INV-3）；`markers` 軌刪除（V-2a）。意圖宣告有了詞彙、儀器、容差、宣告時刻與儀器限制條款（§7.5，V-1、V-33）。
- **覆寫只認使用者**：`Clip.override` 帶 `source: user` 與確認紀錄，判定表列 4 只在 `source=user` 時放行（V-3）。
- **雜湊與產生物**：正規化雜湊；`build/MANIFEST.json` 分開記「內容雜湊」（偵測手改）與「來源雜湊」（判斷過期），回饋重做不再死鎖；`status` 移出被雜湊的檔（V-4、V-15、SG-2）。
- **聲音進版本**：旁白音檔移出 `build/`，以快取鍵命名，核可時鎖進 `voice_lock`（V-5、SG-6）。
- **錨點語意**：`film.end` 只在 `fixed` 下可用；`fixed` 的結尾空檔只能是宣告的停留或黑場（V-6）。
- **一條順序**：`validate --static` → `voice` → `resolve` → `validate --timed` → `view`；`VALID`＝兩段都過（V-7、V-28）。
- **狀態機補齊**：版本狀態機補缺格、`ABANDONED`、無儀器時的 `REVIEWED` 路徑；新增旁白句與產生物兩張狀態表；元件證據狀態機改寫（V-8、V-9、V-16、V-17、V-27）。
- **使用者裁決**（2026-10-08/09）：TTS 只用本機（D-T11）；元件以技巧卡為主，HyperFrames 與 gl-transitions 之後以潔淨分析抽取（D-T12、D-T13，等待池 W28）；製作單四項定案（D-T8）；`guided` 的轉場、排版、運鏡「填了就固定、空著就放開」（D-T14）；讀字時間依元件類別豁免（D-T15）。
- **事實更正**：r8／r18 停頓的實際數值、librosa 與 `measure_narrated` 的描述、「欄位名稱不改」改為對照表（V-23、V-34）；模組數改為 7（v3 更正為 8，見 §0.4）。
- **filmkit 介面**：頁面資料夾封閉（Compile 扁平複製相依檔）、`-o`、`film_plan.json` 欄位與 filmkit 里程碑分階段生效、共用規則檔（V-24、V-25）。
- 其餘 should-fix（V-18～V-22、V-26、V-29～V-32、V-35）在 v2 已一併處理；逐項對照見 §14。

**v4 變更**（依 `verification_timeline-layer-design-v3_2026-10-09.md`，以下 X-n 指該報告；逐項對照 §14.4）：

- **片中不留空檔**（使用者 2026-10-09，X-3，D-T22）：畫面軌上任何空檔（`e_prev < t0`；v4.4 更正，Z-3），`resolve` 把前一段延長到下一段起點（硬切接上）並列出；作者可改成轉場。底色只出現在第一段之前。
- **轉場也走元件篩選**（X-2）：`transition_in` 只能寫具體元件或 `"cut"`；轉場元件照表 A 判基調與時機；`guided` 的轉場「空著就放開」＝寫片段的 AI 從候選挑一個、核可前寫下。
- **對照與語意一致**（X-1）：不檢查換段時刻的是「全片第一個畫面片段」與「沒有句子的 feature 片段」。
- **結尾**：重述主句的結尾卡算標語型（使用者，X-17）；`end_hold`＝結尾卡收完之後的靜止時間（對齊使用者 r14 的說法與 filmkit FK-R-16），改用 `density.py` 量，`tail` 預設改 3.0 s（X-6）；v4.3 再改為 2.0 s（D-T23：使用者 2026-10-10 在 W30 把片尾停留改為 1.5–2.5 s）。
- **版本內容進版本資料夾**（X-11）：片段程式與元件資料夾複製進 `versions/<n>/`，`compile` 從副本編譯；`tools/timeline` runtime 雜湊入指紋；共用規則檔不入指紋。
- **里程碑解環**（X-4）：TL-1 用匯入的預錄旁白（`voice --import`，標「未回驗」）出片；TL-2 才加本機 TTS 與回驗。
- **其餘**（X-5～X-18）：旗標隨 filmkit 里程碑分階段、自動宣告靜音、儀器限制補齊（含 Canvas 文字讀不到，TG-19）、倍速表連續、TV-8／TV-9 改寫、`requires` 檢查、狀態機與證據旗標、轉場窗不相疊、`tdur` 改名、TV-19。

**v3 變更**（依 `verification_timeline-layer-design-v2_2026-10-09.md`，以下 W-n 指該報告；逐項對照 §14.3）：

- **轉場只有一種讀法**（W-1）：`transition_in` 只剩 `dur`，`overlap` 欄位刪除；轉場窗＝`[t0, t0+dur)`，前一段最多延伸到窗尾；換段時刻＝窗中點；片段內時間一律 ≥ 0。示意與對照改成離邊界至少一格。
- **版本指紋**（W-2、W-11）：`approval.json` 記片段程式、元件內容、素材、規則檔的雜湊與 `parent`；核可的旁白音檔複製進版本資料夾；`compile` 與 `revise` 都以指紋為準。
- **停頓數值重查**（W-3）：8 組腳本的實測表取代 v2 的錯誤範圍；預設值改稱「選定值」（開頭 1.0、句間 0.45、段間 1.2、結尾 2.5 s；結尾 v4 更正為 3.0，v4.3 再改 2.0，D-T23）。
- **檢查階段只有一張表**（W-4）：以 §7.3 為準；TV-11 只在 `compile`；新增 TV-15（片段程式呼叫了候選外的元件）放進 `validate --static`；TV-9 拆靜態與時間相依兩段。
- **補祖先**（W-5）：展示倍速併入 BR-14（「展示不能拖」，使用者 r14，未驗證），加 TV-17；只記錄的欄位明寫「僅記錄」。
- **使用者裁決**（2026-10-09）：片尾空檔停在最後一格並由工具自動宣告為停留（W-7，D-T19）；小節錨點延到 TL-4 確認（W-6，D-T17 改為使用者決定）；新增常駐層軌 `overlay`（W-21，D-T20）。
- **介面對齊**（W-8～W-10）：`end_hold`＝片長減最後一次換段，改用 `segments.py` 量（v4 再改，見 v4 變更）；`build/` 內各檔的擁有者分開寫；出片指令補 `--rules`、`--film-type`；混音缺規則檔時用明寫的後備值並記錄。
- **其餘 should-fix**（W-12～W-20）：覆寫改為「核可點列出、由使用者確認」；版本與元件狀態機補格；里程碑相依修正；舊參照修正（元件 8 個）；補對照列；判定表 A 順序調整；`layout`／`camera` 明寫是給片段作者的指示。

## §0 結論

### 0.1 一句話

**決定可以固定，呈現可以抽卡**（使用者 2026-10-08）：時間軸檔固定「何時、放什麼、什麼基調、用哪一類手法」，每個片段再用三級自由度（`locked`／`guided`／`free`）決定畫法交給誰。

### 0.2 核心五件事

1. **時間軸檔 `film.timeline.json`**：整片決策＋軌道（畫面段、旁白、音樂、音效、字幕）。時間可以寫成**錨點**（「第 3 句句首」「S2 結束」，TL-4 起加「第 12 小節」），由解析器算成秒數。它是整支片的唯一真實來源：頁面、混音、字幕、filmkit 的 `film_plan.json` 都由它產生。
2. **元件庫**：把技巧卡（T01–T16）變成帶參數、時間純函數的程式元件，每個元件標**基調**、**適用時機**、**可量的意圖**、**證據等級**。
3. **編譯器**：解析錨點 → 選元件 → 組成一個 `__setTime(t)` 頁面＋事件表＋字幕＋`film_plan.json`＋混音。
4. **旁白路徑**：本機 TTS → 語音辨識回驗 → 句子時間（旁白先於畫面，T08）。音樂分析的小節錨點在 TL-4 加入；出片、合成、響度由 filmkit 負責。
5. **意圖對量測**：時間軸宣告了「換段落在句首」「結尾停 3 秒」，出片後用 lab 已校準的儀器量成品，列出每條意圖量到多少、在不在容差內，以及該儀器的限制。

### 0.3 不做什麼（摘要；完整見 §1.4）

不做可編輯的 GUI（第一版只有唯讀時間軸頁）、不用生成式影片模型、不自動作曲、不用線上 TTS、不判斷好不好看（INV-6）、不重做 filmkit、不取代 lab 儀器。

> 2026-10-18 加註（使用者裁定「另開剪輯路線」）：「不用生成式影片模型」只限時間軸層本身。生成素材、現成影片片段走剪輯路線 `tools/edit`（[edit-route-design.md](edit-route-design.md)），本設計不變。

### 0.4 設計等級與宿主

- **標準 (Standard)**，附 DSL 語意契約（§7）。驅動因素：8 個元件（§6.2：Validate、Voice、Resolve、View、Approve、Compile、Intent、Revise）、持久資料（時間軸版本、旁白音檔、元件庫版本）、外部消費者（做片的對話、filmkit、受測 arm、使用者）、AI 是第二個執行者（填時間軸、寫 `guided`／`free` 片段）。**沒有設計上的併發**（理由同 filmkit D5）；意外的併發（同一支片兩個 `tl` 行程）由一把作業系統位元組鎖互斥（沿用 filmkit 的 `msvcrt.locking` 做法，§10 TG-18）。升級條件：平行出片、或兩個執行者同時編輯同一份時間軸 → 全梯 (Full-ladder)。略過：獨立 CIM 文件、ADR 檔、Petri 分析。
- **宿主關係：延伸，不新建平行系統**。filmkit（頁面 → MP4 → 檢查 → 改動類操作）已設計到 v4.1、PSM v1 已寫（`docs/filmkit-psm.md`，未驗證）、未建。時間軸層放在它**上游**，產出它要的輸入；filmkit 的設計不改。

## §1 Concept Note（業務層）

### 1.1 不可再化約的痛點

**做一支片的決定沒有載體**：受眾、基調、片型、何時換段、用哪個手法，散在 prompt、`plan.md`、分鏡表 markdown 和模型的當下判斷裡。所以：

- 同一份需求每次做出來，結構和時機都會飄（r11：分鏡組照秒數 3/3，一段話組 0.33–0.67 整數秒比例）；決定沒被寫下，就無法檢查、無法重用、無法只改一處。
- 出片的「水管」每輪重寫：r8、r18 每一組各寫一支排旁白時間的腳本，停頓參數各不相同（§6.3）；r13 自己寫 `timeline.json` 片段時間映射；filmkit §1.1 盤點到約 140–155 份手寫 `capture.py`／`render.py`。
- 已經量過、驗證過的手法（T01 對拍、T04 骨架、T08 換段對句首），每次都要靠模型讀卡片後「重新寫一次」，卡片本身不會執行；寫完也沒有東西確認「宣告的節奏」真的出現在成片裡。

### 1.2 不做會怎樣、第一個使用者

不做的話，lab 的研究成果停在「卡片＋儀器」，做正式片仍然是一次一次的抽卡。第一個使用者是**使用者本人做 DIT 宣傳片**（使用者 2026-10-08 選定）；之後是音樂 PV／MAD（lab 正在研究的片型），再之後可能是動畫。

| 使用者 | 怎麼用 | 現況 |
|---|---|---|
| 使用者本人 | 在對話裡回答導演表的問題；看唯讀時間軸頁；用「第幾秒／哪段／改什麼」回饋 | 看 `plan.md`／分鏡 markdown，靠模型手寫 |
| 做片的對話（AI，motion-video skill） | 填時間軸、跑驗證與編譯、寫 `guided`／`free` 片段 | 每次從零寫整個頁面 |
| filmkit | 讀時間軸產生的 `film_plan.json`、頁面、`mix.wav` | 讀作者手寫的計畫檔（選填） |
| lab 主流程 | 專門的 A/B 輪掛載元件庫，測「有元件庫會不會更穩」 | 無 |

### 1.3 核心與延伸

核心（缺一就沒解決痛點）：

1. 時間軸檔格式＋驗證器＋錨點解析器（句子錨點、片段錨點、秒數）。
2. 元件契約＋第一批元件（DIT 用到的：C07 形狀收成名稱開場、C17 動詞章節卡、結尾重述主句＋停留）。
3. 編譯器：時間軸 → 頁面、事件表、字幕、`film_plan.json`、混音。
4. 旁白路徑：本機 TTS → 回驗 → 句子時間 → 錨點。
5. 唯讀時間軸頁（給使用者看與回饋）。
6. 意圖對量測（包裝 lab 既有儀器，不新寫儀器）。

延伸（不在第一版，TL-4 以後）：音樂分析與小節錨點、音效庫、混音閃避（filmkit 的 `duck`）、歌詞錨點（等 W24）、潔淨分析抽取的外部元件（W28）、可編輯 GUI、逐段快取重出、升級為全域能力。

### 1.4 不做什麼

- **不做可編輯 GUI**（第一版）。時間軸檔就是導演表；頁面只是它的視圖。太早做編輯器會把格式鎖死。
- **不用生成式影片、不自動作曲**。音樂由使用者提供或從本機音樂庫選；合成音效可以有。
- **不用線上 TTS**（使用者 2026-10-08：只用本機）。
- **不判斷好不好看**（INV-6）。驗證器和意圖對量測只說「宣告了什麼、量到什麼、儀器的限制」。
- **不改基調去遷就手法**（使用者 2026-09-30）：元件和整片決策衝突時，元件出局。
- **不把元件庫硬塞給受測 arm**：元件庫本身是受測變因，預設不掛載（使用者 2026-10-08）。
- **不重做 filmkit 的事**：出片、編碼、合成、檢查、響度正規化都在 filmkit；本層的混音不訂響度目標。
- **不承諾抽象實驗片**：藝術片的範圍是音樂 PV、MAD、之後的動畫；大膽發揮的部分走 `free` 片段，不擴充格式去描述它（使用者 2026-10-08）。

### 1.5 業務規則

| ID | 規則 |
|---|---|
| BR-1 | 一支片的每一個時間值（換段、句子、音效、字幕、停留宣告）都從同一份時間軸算出來；產生的檔案看得出是從哪一版時間軸來的，也看得出有沒有被手改。 |
| BR-2 | 整片決策（受眾、記住的一件事、能量、底色、片型、節奏來源）先於手法；手法和決策衝突時，手法出局，除非**使用者**明確覆寫並寫下理由。 |
| BR-3 | 每個片段都有自由度：`locked`（元件＋參數固定）、`guided`（時間、內容、基調、手法類別固定；轉場、排版、運鏡填了就固定、空著就放開；畫法由模型寫）、`free`（只固定時間窗、基調、動作意圖）。作者沒指定時，工具填入 `guided`。跨好幾段一直存在的元素（常駐錨點、母題、背景）放常駐層，只畫一次（D-T20；T04、T15）。 |
| BR-4 | 自由度只放開「畫法」，不放開「規則」：三級片段都遵守同一個片段契約，都要報出畫面文字與事件，都經過同樣的檢查；工具執行不了的欄位（`guided` 的排版、運鏡）明寫是給片段作者的指示，交人看。 |
| BR-5 | 有旁白時先有句子時間，再排畫面（T08）；有配樂且沒有旁白時，換段落在小節線上（T04，TL-4 起）；兩種節奏來源擇一當主。 |
| BR-6 | 每個會動的元素、每層疊上去的效果，都有一句動作意圖；老梗手法沒有意圖就不用（production-order E）。 |
| BR-7 | 元件的每個參數標證據等級（使用者看片／已量／已驗證／未驗證）；元件不能宣稱比它的技巧卡更高的等級。 |
| BR-8 | 使用者確認過的版本不再被改——時間軸、片段程式、元件內容、素材、旁白音檔一起；修改產生新版本，記得它從哪一版來、改了哪些片段。 |
| BR-9 | 給人看的時間軸頁、字幕、修改紀錄由檔案生成，不手寫第二份。 |
| BR-10 | 受測 arm 只有在 round 檔中該 arm 明寫時才拿到元件庫；拿到的版本記在 `run.json`。 |
| BR-11 | 回饋以「第幾秒／哪個片段／改什麼」進來，對應到片段 ID 後才修改。 |
| BR-12 | 產品片的畫面文字與數字照 T05 可追溯；時間軸裡的宣稱文字帶出處；產品名、標誌等身分資訊只能取自素材宣告，不可由 AI 自創。 |
| BR-13 | 時間軸宣告的每一條可量意圖，出片後都由一支具名的 lab 儀器量過，報出量到的值、宣告的容差、儀器的限制；量不了的說量不了。這是事實對照，不是好壞判斷。 |
| BR-14 | 檢查對照 lab 已裁決的設計規則（讀字時間、結尾停留、單一底色、轉場不蓋前一段最後一句、展示不能拖），每條規則標明來源與是否暫定；規則的數值只有一個來源（和 filmkit 共用規則檔）。 |
| BR-15 | 混音交出的聲音不削波，旁白在有配樂時清楚可聽（旁白高於音樂的差距由規則檔宣告）；響度目標不在本層。 |
| BR-16 | 同一版時間軸、同一份旁白音檔、同一版元件，編譯兩次得到位元組相同的頁面與相同的畫面（同機同版）；差異只能來自版本指紋涵蓋的輸入。 |

## §2 先例盤點（Phase 1）

### 2.1 假設表（動筆前寫下，查證後標出過時的）

| # | 假設 | 查證結果 |
|---|---|---|
| H1 | 剪輯軟體的時間軸資料模型以 OpenTimelineIO 為事實標準；它只有絕對時間，沒有「錨在另一個事件上」的時間 | **成立**。OTIO、MLT、FCPXML、剪映草稿都沒有「錨在拍點或句首」的時間；最接近的是 FCPXML 的子片段相對父片段位移（未在原文確認）。錨點只存在於作者層：HyperFrames `data-start="intro + 0.5"`（只能錨片段結束）、GSAP 位置字串、Motion Canvas 具名時間事件。**本設計的 `TimeRef` 錨點沒有現成格式可用**。 |
| H2 | CapCut／剪映的草稿是一份 JSON，有社群工具能寫它，但格式不公開、會變 | **成立且更糟**：剪映 6 以上加密草稿；pyJianYingDraft（Apache-2.0）只能在舊版剪映、Windows 上自動匯出，成品要在封閉的桌面程式裡出片。不適合確定性出片。 |
| H3 | 「JSON 描述 → 影片」的開源工具（editly 等）多半是剪既有素材 | **成立**，而且 editly 自 2025-05 停更。 |
| H4 | HyperFrames 有組成模型可借，但不處理「決策 → 時機」 | **部分過時**：HyperFrames（Apache-2.0，v0.8.141，2026-10-08）現在有 180 個元件的註冊庫、帶 `role` 的型別變數、lint 規則集，以及 `music-to-video` 技能（`audiomap.json`＋`STORYBOARD.md`＋`validate-plan.mjs` 硬檢查：片長相等、片段無縫鋪滿）。它的錨點在分鏡裡寫成**絕對秒數**（從 audiomap 抄來），沒有「決策」層，元件沒有證據等級。 |
| H5 | 中文旁白：edge-tts 仍可用但需網路；本機開源 TTS 有可用的中文模型；faster-whisper 給得出字級時間 | **成立，且有台灣專用選項**：edge-tts 7.2.8 仍列 3 個 zh-TW 聲音（2026-10-09 查；使用者裁決不用線上服務）；本機有 BreezyVoice（聯發科，台灣華語、可用注音控破音字，Apache-2.0）、Qwen3-TTS、Fun-CosyVoice3（皆 Apache-2.0，Windows 適配未驗證）；ASR 有 Breeze-ASR-25（台灣華語、強化時間對齊，Apache-2.0）。 |
| H6 | 拍點分析：librosa 可用；madmom 難裝；有較新的神經網路模型 | **成立**：beat_this 1.1.0（MIT，程式與權重，pip 可裝）給拍點與強拍；madmom 的模型是 CC BY-NC-SA；librosa 已到 1.0.0（需 Python ≥ 3.12）。lab 現有的 `beatgrid.py` 只給固定週期網格，沒有強拍與段落。 |
| H7 | 可 seek 的動畫函式庫可以在純時間函數頁面裡用 | **成立，有陷阱**：GSAP 3.15 以 Webflow 免費授權（非 OSI）；`.to()` 在亂序 seek 時可能和順播不同（未在原文確認），HyperFrames 的 lint 因此建議 `fromTo`。gl-transitions（125 個 GLSL 轉場，每檔 MIT 標頭）只吃 `progress` 與兩張畫面。 |

### 2.2 外部先例（2026-10-08/09 查證；每項出處網址在 `docs/research/timeline-layer-prior-art-2026-10-09.md`）

**最接近的先例是兩個 2026 年的新專案**，和本設計同一種架構（頁面是 t 的函數、Chromium 擷取、ffmpeg、TTS → ASR 回驗 → 時間、音效掛事件）：HeyGen HyperFrames 與 lemo-opuscar。兩者都很年輕、變動快，只當想法來源。

| 候選 | 授權／維護 | 和我們的契合 | 結論 |
|---|---|---|---|
| HyperFrames（heygen-com/hyperframes） | Apache-2.0；v0.8.141（2026-10-08），7 個月約 140 版；Windows 有 36 個開放問題 | 高：元件註冊庫、型別變數、lint、`music-to-video` 分鏡驗證 | **只借概念**（沿用 filmkit D1 的理由：頁面契約不同，採用＝換掉出片層）。已借：註冊項目欄位（`license`、`requires`，§6.1 `Component`）、變數的 `portrays`（`Asset.portrays`，防止 AI 編造產品名）、分鏡驗證的「片段無縫鋪滿」（SEM-2）。元件程式：**之後以潔淨分析抽取核心（D-T12，W28）**。 |
| lemo-opuscar | MIT（2026-09-26 建） | 高：同一條管線 | 只借概念（D-T7）。 |
| OpenTimelineIO | Apache-2.0；0.18.1（2025-11）；Windows wheel 齊 | 中：資料模型（`RationalTime`、`Transition{type, in_offset, out_offset, parameters}`、每型別 schema 版本、命名空間化的 `metadata`） | 借概念（`transition_in` 是帶參數的物件、§7.2 SEM-1）；**不當依賴**（不能表達錨點與元件參數）。每型別 schema 版本延後：第一版只有全域 `schema_version`（D-T16）。 |
| Remotion | 自訂授權（非 OSI；4 人以上公司要付費） | 低：React | 借概念：用 schema 驅動參數驗證（`Component.params`、TV-4）。 |
| Motion Canvas／editly／Theatre.js | MIT／MIT／Apache-2.0；分別 2024-12、2025-05、2024-04 後無發版 | 低 | 借概念：`defaults` 繼承（editly）延到 PSM 決定是否需要（D-T16）；具名時間事件不借（v1 的 `markers` 已刪）。 |
| gl-transitions | 每檔 MIT 標頭；npm 1.71.0（2026-06） | 高：轉場是 `progress` 的純函數 | **不直接採用；併入 W28 潔淨分析**（使用者 2026-10-09，D-T13）。第一版不依賴 WebGL。 |
| GSAP／anime.js | Webflow 免費授權（非 OSI）／MIT | 中 | 允許在片段程式裡用，限「建立即暫停、只用 seek」；靜態掃描對 `.to(` 列「要你看」（TV-13）。 |
| beat_this | MIT（程式＋權重）；1.1.0（2026-04） | 高：拍點＋強拍 | TL-4 的小節錨點來源（本機），加人工指定第一個強拍的覆寫（D-T17）。 |
| librosa | ISC；1.0.0（2026-08） | 中：起音、能量 | TL-4 候選（lab 目前**沒有**任何工具用 librosa；`cutdrivers.py` 只用 numpy、scipy）。 |
| BreezyVoice／Qwen3-TTS／Fun-CosyVoice3 | 皆 Apache-2.0；Windows 未驗證 | 高：本機、台灣華語（BreezyVoice） | **TL-2 前本機試跑**，選一個當主力（D-T11）。 |
| faster-whisper＋Breeze-ASR-25 | MIT／Apache-2.0 | 高：回驗與字級時間 | 候選依賴；Breeze 需轉 CTranslate2、RTX 5070 未試。lab 的 `lyriclines.py` 已用 faster-whisper；`measure_narrated.py` 用的是外部 `speech-subtitle`。 |
| Montreal Forced Aligner | MIT；台灣華語字典與聲學模型 CC BY 4.0 | 中：最精準的強制對齊，但走 conda／Kaldi | 有條件採用：只在 TG-1 的裁切法不夠準時。 |
| edge-tts | LGPL-3.0；需網路 | — | **不用**（使用者 2026-10-08：只用本機）。 |
| ffmpeg `loudnorm` | ffmpeg 本身 | 高 | 由 filmkit M3 使用，本層不重做。 |

**要避開的**：F5-TTS 權重、ctc-forced-aligner 預設模型、madmom 模型、fish-speech（皆非商用或研究授權）；IndexTTS（bilibili 自訂授權，下游義務）；essentia（AGPL、沒有 Windows wheel）；allin1（需從原始碼編譯、停更）；pyJianYingDraft（依賴封閉 App）。

**過時的常識**（一個 2024 年的模型會這樣以為）：GSAP 外掛要付費；Remotion 是 MIT；madmom 是強拍分析的標準；F5-TTS 可商用；沒有台灣華語的本機 TTS；OTIO 沒有 Windows wheel。以上都已不成立（出處見研究檔）。

### 2.3 內部先例（延伸或新建的判定：**延伸**）

| 位置 | 是什麼 | 和時間軸層的關係 |
|---|---|---|
| `docs/filmkit-design.md`（v4.1，驗證通過；PSM v1 `docs/filmkit-psm.md` 已寫、未驗證） | 頁面 → MP4 → 檢查 → 改動類操作 | **下游**。時間軸層產生它的 `film_plan.json`、頁面、`mix.wav`。不改 filmkit 的任何決策；介面條目見 §6.9。 |
| `docs/production-order.md` | 製作單節點，帶證據標記 | **被收編**：節點變成時間軸檔的欄位，證據標記變成欄位的 `evidence` 與元件參數等級。最後一節的四個「還沒決定」已由使用者 2026-10-08 裁定（D-T8）。 |
| `docs/shot-record-trial.md`、production-order〈分鏡紀錄的欄位〉 | 逐段欄位 | **片段 (Clip) 欄位的來源**；名稱有改的列在 §6.1 對照表，讓原片鏡頭表、計畫、成品量測三邊仍能逐欄對照。 |
| `techniques/T01–T16` | 技巧卡：參數區、證據、工具限制 | **元件的來源**。每個元件指回一張卡；卡的參數區變成元件的參數 schema 與預設值，卡的「工具限制」變成意圖報告的儀器限制條款。 |
| skill `motion-video` 步驟 0–9、`whole-film-rules.md`、`film-types.md`、`build-and-export.md` §1 | 先問什麼、片型骨架、分鏡表欄位、展示倍速表 | **`decisions` 區與片型骨架的來源**；步驟 4 的分鏡表改由時間軸頁呈現；倍速表成為 `Clip.speed`。 |
| r8／r18 各 arm 的排旁白時間腳本（`<arms-root>\r8-c20\*`、`r18-c25-guide\*`） | 量每句 wav 長度 → 加開頭靜音、句間、段間、結尾靜音 → `timeline.js` | 旁白錨點解析的**同一個演算法**，各寫各的、參數不同（§6.3）；時間軸層把它變成一支共用的解析器。 |
| `experiments/r13-c21-assemble/MR2` | 一個頁面，片段時間映射（film t → source t）寫在 `timeline.json` | **組裝頁面的先例**：編譯器的段落時鐘＝片段內時間 `lt`，再經 `Clip.speed` 映射成展示時間。 |
| `a post-format project/post.py` | 貼文工作流：計畫 → 封存腳本 → 核可 → 生成 → 匯出 → 作者手改 → 重出 | **工作流形狀的先例**：核可前後分版（§6.4）、作者手改受保護（TV-11）。PROJECTS 記使用者要把貼文工作流做成「全域能力」——見 review-when。 |
| `<prompt-shelf>` | prompt 版本 ↔ 測試片 ↔ 輪次結論的書架；雜湊用「LF 正規化」 | 正規化雜湊的做法照它（TL-INV-1）；版本雜湊之後可進書架。 |
| lab `tools/` 量測儀器 | `narrlock`、`segments`、`measure_product`、`density`、`bgswitch`、`fidelity`… | **意圖對量測**的量測端，不重寫（§7.5）。 |
| lemo-opuscar（GitHub，MIT，2026-10-08 讀 `DIRECTOR.md`、`TECHNIQUE.md`、`core/README.md`） | 一個 `timeline.js` 驅動畫面、配樂、音效、字幕；頁面契約 `render(t)`、`EV`、`TEXTS`；`readcheck`、`asr_check`、`mux` 響度 | **只借概念**：`TEXTS` → `ClipContract.texts`；`EV` → `ClipContract.events`；`readcheck` → TV-6；`asr_check` → TV-12；「不要再做一次 demo」→ §11 延伸。它的時間軸每支片自由格式、轉場每次重寫——這正是本設計要補的層。 |

### 2.4 差異化（誠實版）

和 lemo-opuscar、HyperFrames、Remotion 相比，時間軸層不會在畫風或算繪能力上更強。它存在的理由：

1. **決策是一級資料**：受眾、基調、能量、節奏來源寫在檔案裡，元件依它們被篩選（§6.8）；外部工具把這些留在 prompt 裡。
2. **元件帶證據**：每個元件指回 lab 量過的案例與 A/B 結果，參數有等級（BR-7、§6.5）。
3. **意圖對量測**：時間軸宣告的節奏，出片後由 lab 已校準的儀器量（BR-13、§7.5）；外部工具只查檔案層。
4. **可做受測變因**：可以整包掛或不掛，版本可追（BR-10）。

如果這四點都不再成立（例如 lab 停止研究、只剩做片），應評估改用外部框架（review-when）。

### 2.5 環境

同 filmkit §2.5（Windows 11、Python 3.12.7、Node 24、ffmpeg 8.1、Playwright 1.62、RTX 5070 Laptop）。新增依賴（本機 TTS、faster-whisper、TL-4 的 beat_this）的授權已在 2.2 查證；版本在 PSM 釘死，Windows 可用性由 TL-2 前的本機試跑確認。

## §3 全域狀況

### 3.1 存放與命名

| 項目 | 層級 | 位置 | 理由 |
|---|---|---|---|
| 時間軸工具本體 | cross-round instrument | `tools/timeline/` | 和 filmkit 同層；資料夾形式，A/B 輪可整包掛載。 |
| 時間軸格式 | 同上 | `tools/timeline/film.timeline.schema.json` | 驗證器與編譯器共用；檔名刻意不叫 `timeline.json`，避免和 arm 自己產生的 `timeline.js`／`timeline.json`（r8、r13、r18）同名。 |
| 入口 | 同上 | `tools/timeline/tl.py`：子命令 `validate`（`--static`／`--timed`）、`voice`、`resolve`、`view`、`approve`、`compile`、`intent`、`revise`、`at`（秒數 → 片段 ID 查詢，BR-11）；TL-4 加 `music` | 前八個對應 §6.2 的元件；`at` 是唯讀查詢。 |
| 元件庫 | 同上 | `tools/timeline/components/<family>/<id>/`（`component.json`＋`component.js`＋selftest） | 每個元件一個資料夾，可單獨版本化。 |
| 元件索引 | 同上（生成） | `tools/timeline/components/INDEX.md`、`index.json` | 由工具產生，不手改。 |
| 設計規則 | 共用規則檔 | `tools/filmkit_rules.json`（filmkit 設計 §3.1 已定位置與擁有者） | **和 filmkit 共用同一個檔**（D-T18）：TV-7 和 filmkit FK-R-16 讀同一個鍵。缺檔時相關檢查回「無法判定」並說明（§7.3）。 |
| 每支片的工作資料夾 | round output／formal film | `<film>/film.timeline.json`（作者檔）、`<film>/clips/<clip_id>.js`（`guided`／`free` 片段程式）、`<film>/assets/`、`<film>/voice/`（旁白音檔）、`<film>/build/`（生成物；各檔擁有者見 §6.9） | 作者只改時間軸檔與片段程式；`build/` 內 `tl` 產生的檔都可由「版本指紋涵蓋的輸入」重生；filmkit 產生的檔（`final.mp4`、`render.json`、`check.*`）由 filmkit 管，`tl` 不動。 |
| 版本 | 同上 | `<film>/versions/<n>/`：`timeline.json`（核可時的正規化副本）、`voice_lock.json`、`voice/`（被引用的旁白音檔副本）、`clips/`（片段程式副本）、`components/`（用到的元件資料夾副本）、`timeline.resolved.json`、`approval.json`（版本指紋，§6.1 `VersionFingerprint`） | 核可過的版本不可變（BR-8）；`compile` 只讀這裡（素材除外：素材只核雜湊，不複製，避免大檔重複）；在 `tools/timeline` runtime 與素材都沒變時，舊版本可以重新編譯；runtime 升級或素材改動後，`compile` 擋（TV-16），出路是 `compile --rebase`：它不寫 `versions/`，只在 `state.json` 開草稿 `n+1`（`parent` n，`DRAFT`），再照常 `validate` → `approve` 以目前 runtime／素材重新核可（Y-4；版本仍只由 `approve` 寫，Z-6）；`revise` 比對兩版的 `resolved`、指紋與片段程式內容。 |
| 狀態 | 同上 | `<film>/state.json`：目前版本號、各版狀態（§6.4） | 狀態**不**寫進被雜湊的時間軸檔（V-15）。 |
| 設計文件 | design | `docs/timeline-layer-design.md`（本檔） | 人讀，中文。 |

升級條件：第二個專案（例如貼文工作流的影片版、或一支不屬於 lab 的正式片專案）實際呼叫時，評估搬到 `~/.claude/tools/` 或 AssetVault；和 filmkit D3 同一種觸發。

### 3.2 註冊清單（設計時列出，收尾時逐項核對）

| # | 要改的地方 | 改什麼 | 里程碑 |
|---|---|---|---|
| RG1 | lab `CLAUDE.md` Commands、Invariants、Layout | 加 `tl.py` 子命令、`tools/timeline/` 版面、TL-INV 摘要、「改元件要跑元件 selftest」 | TL-0 |
| RG2 | `docs/production-order.md` 最後一節 | 四個「還沒決定」改為已裁定，指向 §12 D-T8 | **已完成**（2026-10-08） |
| RG3 | skill `motion-video`：`SKILL.md` 步驟 4、6、7、8；`references/build-and-export.md` §1–§3 | 步驟 4「分鏡表」→ 填時間軸＋看時間軸頁；步驟 6 → `tl.py compile`；步驟 8 回饋格式指向片段 ID；Verdicts 加「意圖對量測」 | TL-1 |
| RG4 | `~/.claude/tools/lab-skill-sync/pairs.json` | motion-video 這一對的 `watch` 加 `tools/timeline`；改完移 `lab-sync` 標記 | TL-1 |
| RG5 | `tools/run_arm.py` | **arm 層**鍵 `timeline_lib: true`（預設不掛；round 層同名鍵被拒，Z-1）；照 `mount_skills` 的方式複製 `tools/timeline/` 到工作區，`run.json` 頂層記 `timeline_lib_mounted`、`timeline_lib_hash`；selftest 加掛／同輪不掛／round 層被拒；以 TL-5 當時 main 上的 `run_arm.py` 為基底 | TL-5 |
| RG6 | `~/.claude/references/PROJECTS.md` motion-video-lab 列 | 工具清單加時間軸層 | TL-1 |
| RG7 | `waiting/pool.json` W08 | 結案 | **已完成**（ee74a2b） |
| RG8 | `waiting/pool.json` W28 | 潔淨分析施工卡 `docs/clean-room-component-extraction.md`（含 gl-transitions，D-T13） | **已開**（2026-10-08） |
| RG9 | 總入口頁 All-View-Pages-Launcher | **不需要**：時間軸頁是每支片生成的頁面，不是常駐檢視頁 | — |
| RG10 | skill-trigger-dict | **不需要**：沒有新 skill | — |
| RG11 | `tools/density.py`；lab `CLAUDE.md` 儀器條目 | 輸出靜止段清單（含位置）＋ `--selftest` 正反對照（片尾靜止的合成片／片尾一直在動的合成片）；條目同步（Z-5） | TL-3 |

### 3.3 和既有規則與宿主行為的關係

| 既有規則或行為 | 時間軸層的立場 |
|---|---|
| INV-6（像不像要看片＋使用者驗收；數字要來自具名儀器並說明限制） | 不判斷畫面；意圖報告每條都附儀器名與限制（§7.5、TL-INV-8）。 |
| workflow ⑤「框架給了什麼，那一項就測不出效果」；r10「原則裡寫出的名稱會被照做」 | 元件庫是受測變因：arm 預設不掛（D-T4）；`guided` 片段只拿到合格候選清單（§6.8 A7）。 |
| r11 使用者裁決「分鏡固定內容、順序、秒數；轉場、排版、動態留給模型」 | `guided` 是預設；轉場、排版、運鏡空著就交給模型（D-T14）。`guided` 固定「手法類別」超出 r11 的字面，這是使用者 2026-10-08 選定三級自由度時一併接受的；r11 自己註明「明寫放開會不會讓相似度下降，還沒測」，TL-5 的量法會回答。 |
| 使用者 2026-09-30「手法和基調衝突時，丟手法，不改基調」 | BR-2、TL-INV-5、§6.8 表 A 的 A4–A5。 |
| 使用者 2026-09-27 DIT 拼接簡報「每張卡不到 1 秒」 | 章節卡屬標語型元件，豁免讀字公式（D-T15、TV-6）。 |
| r13 使用者判讀「下一段的轉場不能蓋掉上一段的最後一拍」 | TV-14。 |
| filmkit D12（設計規則不進 arm 側 kit） | 時間軸層的驗證器會讀共用規則檔——它是**作者端**工具；A/B 輪掛載時，規則檔不隨掛載複製，arm 內相關檢查回「無法判定」（TL-INV-10、§7.3）。 |
| filmkit D15（計畫檔選填） | 不變。時間軸層**產生**計畫檔；沒有用時間軸層的片照舊。 |
| `run_arm.py` 的 `copy_build()`（只複製頂層） | `build/` 扁平：頁面與其相依檔全在頂層（§6.9），lab 記載過 r18／r19 分檔頁面複製後開出空白。 |
| skill 步驟 0 的「使用者在場就問、等答；不在場寫 `questions.md`、採最字面解讀」 | 不變；答案寫進 `decisions`，每欄記 `source: user|model|default`（SEM-10）。 |

## §4 調用面：誰、何時、怎麼呼叫

固定順序（V-7）：`validate --static` → `voice` → `resolve` → `validate --timed` → `view` →（使用者確認）→ `approve` → `compile` → filmkit → `intent`。`tl.py` 每個子命令都檢查前一步的產物是否與目前時間軸相符，不符就說出缺哪一步（`kind: not_current`，不自動補跑）。`tl.py at <film> <秒數>` 隨時可用：回該秒的片段 ID、句子 ID 與片段內時間（BR-11）。

| 呼叫者 | 時機 | 指令形狀（PSM 定稿） | 讀什麼結果 |
|---|---|---|---|
| 做片的對話 | skill 步驟 0–4 | 問答 → 寫 `film.timeline.json` → `tl.py validate --static` | 五行輸出；`build/validate.json` |
| 做片的對話 | 有旁白時 | `tl.py voice <film>`：每句本機 TTS → 回驗 → `voice/` | 每句通過／未通過；未通過的句子列出聽成什麼 |
| 做片的對話 | 之後 | `tl.py resolve` → `tl.py validate --timed` → `tl.py view` | `build/timeline.resolved.json`、`validate.json`、`build/timeline.html` |
| 使用者 | 看時間軸頁 | 不呼叫；在對話裡用「第幾秒／哪段（片段 ID）／改什麼」回饋，或說「OK」 | — |
| 做片的對話 | 使用者說 OK 後 | `tl.py approve <film> --by user --note "<使用者原話>"`（不在場：`--by model --questions build/questions.md`） | 新版本 `versions/<n>/`；五行的第一行列出所有覆寫與「待你確認」的項目 |
| 做片的對話 | 核可後 | `tl.py compile` → filmkit `render.py build/index.html -o build/final.mp4 --plan build/film_plan.json --audio build/mix.wav --rules <lab>/tools/filmkit_rules.json --film-type <對照後的片型>`（`compile` 把這行完整指令寫進 `build/render.cmd.txt`，照抄即可） | filmkit 的五行與 `check.md` |
| 做片的對話 | 出片後 | `tl.py intent <film>`：呼叫 lab 儀器量成品，對照宣告 | `build/intent.json`、`build/intent.md` |
| 做片的對話 | 收到回饋 | 編輯時間軸檔或片段程式 → 從 `validate --static` 重走；`tl.py revise <film>` 產生兩版差異 | `build/revisions.md` |
| `run_arm.py` | A/B 輪且該 arm `timeline_lib: true` | 掛載 `tools/timeline/` 到工作區 | `run.json.timeline_lib_hash` |

沿用 filmkit 的交互慣例：stdout 固定五行、完整資料進 JSON、失敗帶 `kind`＋`hint`（種類表見 §6.10）、一律 `-X utf8`、複雜輸入走檔案、只在前景執行。

## §5 交互設計

### 5.1 與使用者

- **填寫靠對話**（D-T3）：skill 步驟 0 的問題逐項問，答案寫進 `decisions`；使用者不必看 JSON。
- **看的是時間軸頁**：一頁 HTML（生成），上半部是整片決策卡（每項標「你說的／模型定的／預設」），下半部是軌道：畫面段、旁白句、音效點、字幕（TL-4 起加音樂小節格）；每個片段顯示 ID、秒數、錨點、自由度、手法、動作意圖、哪些欄位是固定的、有沒有覆寫；出片後每個片段附一張該段中點的縮圖，並列出意圖報告的結果。**唯讀**，不做拖拉編輯。
- **回饋格式**：「12 秒／S3／標題太小」或「S3／換成淡出」。片段 ID 印在時間軸頁和縮圖表上，讓使用者不必算秒數。
- **確認點只有一個**：使用者在場時，時間軸頁給使用者看、等確認，再核可、編譯出片（skill 步驟 4 不變）。不在場時，照 skill 寫 `build/questions.md`，由模型核可並在 `approval.json` 記「模型核可，理由見 questions.md」。
- **覆寫要你說**：一個元件和整片決策衝突時，只有你在對話裡同意（原話記進 `override.confirmed`）才放行；模型不能自己覆寫（V-3）。工具無法確認「原話」真的是你說的（W-12），所以每條覆寫在時間軸頁頂端與 `approve` 輸出的第一行逐條列出，標「待你確認」；你在核可點看到它、說 OK，才算確認。不在場時模型核可的版本，覆寫一律不放行。

### 5.2 與 AI（做片的對話、受測 arm）

- **AI 最可能的偏移**：把 `guided` 片段當 `free` 寫，忽略手法類別；或為了過驗證，把每段都標成 `free`。對策：驗證器報出各級片段的秒數比例，`free` 超過整片 30% 列「要你看」（門檻暫定，D-T9）。
- **自己寫覆寫來過關**：`override` 必須 `source: user` 並附確認原話；模型寫的覆寫一律無效（TV-3 照擋）。AI 自填 `source: user` 並捏造原話，工具擋不住，只能讓它在核可點被你看見（§5.1）；`--by model` 核可時一律擋。
- **把驗證通過當成片子好**：五行輸出、時間軸頁、意圖報告都寫明「格式與時機已檢查，畫面未判斷」。
- **核可後偷改片段程式**：`compile` 只從 `versions/<n>/` 的副本編譯，工作目錄的 `clips/*.js` 改了也不會被用到——那是下一版的草稿；副本或素材與指紋不符就拒絕並說出哪個檔（TV-16）。
- **改產生物而不是改時間軸**：`build/MANIFEST.json` 記 `compile` 每個產生物的內容雜湊；編譯時發現內容雜湊不符（被手改），拒絕覆蓋並提示「改 `film.timeline.json` 或片段程式，不要改 build/」（TL-INV-1、TV-11）。
- **元件選擇**：`guided` 片段，編譯器給 AI 的是 §6.8 表 A 的 A7 合格候選清單，不是整個元件庫；片段程式只能呼叫清單內的元件（SEM-6），這也是 r10「寫出名稱會被照做」的對策。
- **身分資訊不可編造**：產品名、標誌只能取自 `Asset.portrays`（借自 HyperFrames `portrays`）；片段畫面文字中出現產品名而素材沒有宣告，列「要你看」（TV-9）。

## §6 內部架構（PIM-lite）

### 6.1 詞彙表 (Glossary)

| Term | 定義 |
|---|---|
| `FilmTimeline` | 作者檔 `film.timeline.json`：`meta`、`decisions`、`assets`、`tracks`。唯一真實來源。**不含狀態**（狀態在 `state.json`）。 |
| `meta` | `schema_version`、`film_id`、`format`（`size`、`fps`、`duration_policy`：`fixed` 秒數，或 `fit`＝由內容決定）、`lead`、`tail`（開頭、結尾秒數，§6.3；`tail` 期間畫面停在最後一格、聲音全部靜音（旁白、音樂、音效都停），D-T19）。 |
| `Decisions` | 整片決策：`film_type`、`audience`、`energy`（calm／lively／hype）、`rhythm_source`（narration／music-bar／content；`lyric-line` 等 W24）、`remember_one`、`ground`（底色）、`voice`（marketing／light-technical）、`presentation`（paged／continuous-stage）、`purpose`、`shown_where`、`viewer_action`。每欄帶 `value`、`source`（user／model／default）、`evidence`。核可時必填：`film_type`、`audience`、`energy`、`rhythm_source`（D-T8）；`ground` 不必填：片中不留空檔（D-T22），底色只用在第一段之前（若第一段不從 0 開始），缺值時那一段畫黑。其餘是給時間軸頁與做片對話的上下文，沒有檢查消費它們（刻意的：它們是使用者回答的紀錄）。 |
| `Asset` | 片中用到的素材：`id`、`kind`（capture／logo／font／music／image／data）、`path`（`assets/` 內）、`sha256`、`license`、`claims_ref`（產品片，T05）、`portrays`（選填：`subject_name`／`subject_logo`，身分資訊的唯一來源）。`license` 僅記錄（時間軸頁與交付清單列出，無檢查）。`duration_s`（衍生欄位：影片類素材由 `validate` 以 ffprobe 取得，TV-17 用）。 |
| `Track` | 一條軌：`picture`、`overlay`、`narration`、`music`、`sfx`、`captions`。（v1 的 `markers` 已刪。） |
| `Clip` | 畫面軌上的一段，欄位見下方對照表。 |
| `OverlayClip` | 常駐層軌上的一段（D-T20）：欄位同 `Clip`（不含 `transition_in`），另有 `z`（疊層順序，整數）；可以跨好幾個畫面段、可以和畫面段重疊；同一個 `z` 上不得重疊（SEM-13）。用途：T04 一直留在畫面上的錨點、T15 母題回調、PV／MAD 的背景。畫在畫面段之上、字幕之下；進出場由元件自己在 `lt` 開頭與結尾處理。 |
| `Line` | 旁白軌的一句：`id`（L1…）、`text`（字幕用）、`say`（念的版本，數字念法；缺省＝`text`）、`section`（屬於哪個片段）、`gap_after`（缺省依 §6.3）、`asr`（選填：回驗時期望聽到的文字；缺省＝`say`，`say` 也缺＝`text`）。另可由 `voice --import` 匯入預錄音檔（TL-1 起，狀態 `imported`，§6.6）。解析後得到 `t0`、`t1`、字級時間。 |
| `VoiceLock` | 核可時寫進 `versions/<n>/voice_lock.json`：每句 `line_id` → 音檔副本路徑（`versions/<n>/voice/`）、內容 sha256、快取鍵、長度。核可後 `resolve` 與 `Mix` 只讀這份副本（W-11）。 |
| `VersionFingerprint` | `versions/<n>/approval.json`：`parent`（上一版號或 null）、核可者與原話、時間；正規化 sha256 清單：時間軸、每個片段程式副本、每個用到的元件（`id@version`＋資料夾內容雜湊）、每個素材、每個旁白音檔副本、`tools/timeline` runtime（`FilmPage` runtime、`uses` 抽取器、混音後備值）。共用規則檔**不**入指紋（他片調門檻不該讓已核可版本失效），它的雜湊只記在 `MANIFEST`。`compile` 逐項比對（TV-16），`revise` 比對兩版。 |
| `VoiceKey` | 旁白音檔的快取鍵＝`say`（或 `text`）、引擎 id 與版本、聲音、語速、全部合成參數的正規化雜湊；音檔存為 `voice/<line_id>-<key8>.wav`（統一轉成 48 kHz 單聲道 PCM）。鍵不變就不重新合成。快取同時存轉寫結果；命中時不重新合成，但用目前的 `text`／`asr` 重新比對轉寫（W-11）。 |
| `MusicCue` | 音樂軌（TL-4）：`asset`、`offset`（音樂第 0 秒對到影片第幾秒）、`analysis`（分析檔路徑與雜湊，由 `tl.py music` 產生；欄位形狀在 TL-4 的 PSM 才凍結）、`first_downbeat`（選填：人工指定第一個強拍的秒數）。 |
| `SfxEvent` | 音效軌的一個點：`at`（`TimeRef`）、`sound`（音效 ID）、`gain_db`、`why`。也可由元件的 `events()` 自動產生。 |
| `TimeRef` | 時間的寫法：影片秒數，或錨點 `{anchor, offset}`。錨點種類：`line:L3.start`／`.end`、`clip:S2.start`／`.end`、`film.end`（只在 `fixed` 下可用，SEM-11）；TL-4 起加（D-T17，使用者確認） `bar:12`、`beat:48`、`downbeat:12`。`dur` 另可寫 `{lines: "L3-L5", pad_after}`（涵蓋這幾句）、TL-4 起 `{bars: 4}`。 |
| `ResolvedTimeline` | 解析器輸出 `build/timeline.resolved.json`：所有 `TimeRef` 換成秒數（並記對齊到格點後的值，SG-1），帶時間軸與 `VoiceLock` 的正規化雜湊。生成物，不手改。 |
| `Freedom` | `locked`：`device.component`＋`params`，編譯器直接產生；`guided`：`device.family`（＋選填更窄的 `device.tone`），畫法由 AI 在 `clips/<id>.js` 寫，只能呼叫候選清單內的元件；`free`：只有時間窗、能量、動作意圖，畫法不限。三級都遵守 `ClipContract`。 |
| `Component` | 元件：`id`、`version`、`family`（§7.4 詞彙表）、`card`（Tnn 或 null）、`card_tier`（建元件時照技巧卡正文抄下的等級；卡沒有機器可讀欄位，卡改版時由 review-when 重核）、`tone`（適用的 `energy` 集合或 `any`、片型集合或 `any`）、`when`（適用時機：`role` 集合、`rhythm_source` 集合）、`conflicts`、`params`（schema：型別、預設、範圍、每個參數的證據等級）、`emits`（事件種類）、`intents`（可量意圖，§7.5）、`label_type`（布林：標語型文字，豁免讀字公式，D-T15）、`hold_range`（標語型的停留範圍）、`license`、`provenance`（自寫／潔淨分析出處；兩者僅記錄，列在元件索引）、`requires`（相依元件；`approve` 據此一併複製進 `versions/<n>/components/`（含遞移相依），缺則 TV-4 擋）、`evidence_state`（§6.5）、`impl`（`component.js`）。 |
| `ClipContract` | 每個片段的程式（元件或 `clips/<id>.js`）必須提供：`draw(ctx, lt, d, p)`（`lt`＝片段內時間，恆在 `[0, d]`；`d`＝片段長度；`p`＝參數；純函數，不讀時鐘、不留狀態、不取網路）；`texts(lt)` → 畫面文字、位置，選填 `claim`（出處 id）；`events()` → 事件（相對片段起點的秒數、種類）。轉場**不**在這裡宣告（只在時間軸的 `transition_in`，SEM-1）。 |
| `TransitionContract` | 轉場元件（`family: transition`）提供 `drawTransition(ctx, u, from, to, p)`：`u`＝轉場進度 0→1；`from(ctx2)`、`to(ctx2)` 是 runtime 給的回呼，分別把前後兩片段畫到離屏畫布：`to` 用本段的 `lt = t − t0`；`from` 用前一段的 `lt = min(t − t0_prev, d_prev)`（前一段已結束就停在它的最後一格）。兩者的 `lt` 都 ≥ 0（SEM-1）。 |
| `FilmPage` | 編譯器產生的 `build/index.html`：暴露 `window.__setTime(t)`（filmkit 契約）、`window.__ready`；內含 runtime：由 t 找出當下有效的片段與轉場，依序呼叫 `draw`／`drawTransition`，再依 `z` 畫常駐層，最上層畫字幕（`captions.style` 指定的字幕元件）。片段丟出例外＝整片失敗（filmkit `page_runtime`），不吞掉（SG-5）。 |
| `IntentDecl` | 一條可量意圖：`kind`（§7.5 詞彙）、`target`（片段或全片）、`expect`（值或範圍）、`tolerance`、`moment`（量哪一刻）、`source`（由決策推導／由元件宣告／作者手寫）。 |
| `IntentReport` | `build/intent.json`／`intent.md`：每條 `IntentDecl` → 儀器名、量到的值、在不在容差內（`within`／`outside`／`undetermined`＋原因）、儀器限制原文。 |
| `Manifest` | `build/MANIFEST.json`：**`compile` 的**每個產生物（清單見 §6.9）的路徑、內容 sha256、來源（版本號＋`VersionFingerprint` 的雜湊）。`MANIFEST.json` 本身、`validate`／`resolve`／`view` 的輸出、filmkit 的輸出不在其中（W-9）。 |

**`Clip` 欄位**（和 production-order〈分鏡紀錄的欄位〉的對照；v1 說「名稱不改」不實，以此表為準）：

| 分鏡紀錄欄位 | `Clip` 欄位 | 說明 |
|---|---|---|
| `seg` | `id` | S1、S2…；章節卡 C1… |
| `t` | `at`、`dur`（皆 `TimeRef`） | 解析後的秒數在 `ResolvedTimeline` |
| — | `role` | 片型骨架中的角色：opening／feature／chapter-card／end-card／… |
| `headline`、`visual`、`data`、`layout`、`what` | 同名 | `layout` 在 `guided` 下：填了就固定、空著就放開（D-T14）；「固定」是給片段程式作者的指示，工具無法驗證有沒有照做，時間軸頁與縮圖表並列供人看（TG-3） |
| `motion_intent` | `motion_intent[]` | 每個會動的元素、每層效果一句（BR-6） |
| `driver` | 全片 `decisions.rhythm_source` | 個別片段不同時不支援（試填時 13 段都一樣） |
| `transition_in`／`transition_out` | `transition_in`（只在進場那段寫） | `{component, dur}` 或 `"cut"`（不接受只寫 family 的形式，§6.8「轉場元件」）；一個轉場只寫一次（SEM-1）；`guided` 下填了就固定，空著由寫片段的 AI 從候選挑選並寫下 |
| `camera.move`／`camera.pace`／`camera.goal`／`camera.method` | `camera.{move, pace, goal, method}` | `goal`／`method` 是 D1／D2 的固定詞彙表（D-T8）；`guided` 下填了就固定（同上，給作者的指示，人看） |
| `sound` | 音效軌的 `SfxEvent`（`target` 指回片段） | 不放在片段內 |
| `ref_seg`、`ref_what` | 同名 | 模仿時填 |
| `src` | 每欄的 `evidence` | — |
| — | `freedom`、`device`、`uses`（`guided`／`free` 片段程式實際呼叫的元件，由 `validate --static` 從程式靜態抽出，`compile` 用同一支抽取器再核一次）、`override`、`declares`、`ground_exception`、`speed` | 見 SEM 與 §6.8 |

`override` ＝ `{why, source, confirmed: "<使用者原話>", date}`，`source` 值域 `user`／`model`，`model` 一律無效（表 A A5）；`declares` ＝ 片段內的刻意 `holds`／`blacks`／`silences`，片段內時間＋`why`；`speed` ＝ `{asset, start_lt, table}`：`asset` 指向被加速的影片類素材，`start_lt` 是展示在片段內開始的時刻，`table` 是展示倍速表 `[[demo_start, demo_end, speed]]`（展示時間，自 0 起連續鋪滿；skill `build-and-export.md` §1；規則來源 lab `docs/axes-and-pairing.md`「展示不能拖」，使用者 r14，未驗證），runtime 提供 `demoTime(lt)` 給片段程式；檢查見 TV-17。

### 6.2 元件與契約

```
Legend:  A ==call==> B   control (process / function call)
         A ~~file~~> B   A writes the named file, B reads it
External: [author] (AI builder session or human), [user], [filmkit], [lab instruments], [TTS engine], [ASR engine], [disk]

[author] ~~film.timeline.json, clips/*.js, assets/*~~> Validate.static
Validate.static : schema, IDs, anchor graph acyclic, components exist, TV-1/3/4/5/8/9a/13/15/17 (`uses` extracted from clips/*.js here)
                  reads ~~components/index.json, tools/filmkit_rules.json~~      ~~build/validate.json~~> [author], View
Voice           : per line, VoiceKey -> cached wav or synthesize -> ASR check
                  Voice ==synthesize(line)==> [TTS engine];  Voice ==transcribe(wav)==> [ASR engine]
                  ~~voice/<line>-<key8>.wav, voice/lines.json~~> Resolve
Resolve         : TimeRef -> seconds (order §6.3).  reads film.timeline.json, voice/lines.json (or VoiceLock), [TL-4: music analysis]
                  ~~build/timeline.resolved.json~~> Validate.timed, View, Compile, Intent, Revise
Validate.timed  : TV-2/6/7/9b/10/12/14 on resolved times; TV-6 / TV-9b run clip texts() in the capture browser
                  ~~build/validate.json~~> [author], View
View            : reads timeline.resolved.json, validate.json, [after render: sheet frames, intent.json]
                  ~~build/timeline.html~~> [user]   (read-only)
Approve         : copies normalized timeline + VoiceLock + voice wav copies + clips/ + used component folders + resolved, writes VersionFingerprint
                  into ~~versions/<n>/~~ (approval.json); writes ~~state.json~~
Compile         : versions/<n>/ (clips/, components/, voice/ copies) + assets, all checked against approval.json (TV-16) ->
                  ~~build/index.html (FilmPage) + its flat deps, build/film_plan.json, build/render.cmd.txt~~> [filmkit]
                  ~~build/events.json~~> Mix (inside Compile);  ~~build/captions.srt~~> Intent, [user] (delivery)
                  Mix : versions/<n>/voice/*.wav + [music] + sfx(events.json), levels from rules file or stated fallback
                        -> ~~build/mix.wav~~> [filmkit]
                  ~~build/MANIFEST.json~~> Compile (next run, TV-11), Intent
[filmkit]       : render.py -> final.mp4, render.json, check.json, check.md        (unchanged, filmkit-design v4.1)
Intent          : reads final.mp4, timeline.resolved.json, captions.srt, MANIFEST.json
                  Intent ==CLI==> [lab instruments] (segments, narrlock, density, bgswitch, fidelity; TL-4: measure_product)
                  ~~build/intent.json, build/intent.md~~> [author], View
Revise          : reads versions/<n>/approval.json -> parent p; compares versions/<p>/ and versions/<n>/
                  (timeline.resolved.json + VersionFingerprint: which clips' times, programs or assets changed)
                  ~~build/revisions.md~~> [author], [user]
```

元件之間只透過檔案溝通，任何一塊可以單獨重寫。可以跳過的：沒有旁白的片不跑 `Voice`；不在 lab 的電腦上 `Intent` 回「儀器不在」，版本狀態照 §6.4 帶標記前進（V-8）。

**可替換的弱點**

| 弱點 | 為什麼存疑 | 隔離點 | 已知替代品 |
|---|---|---|---|
| TTS 引擎 | 中文 TTS 選項變動快；使用者 r18 判 SAPI「太難聽」；本機候選在 Windows 都未驗證 | `Voice` 的 `synthesize(line) -> wav` 介面；`VoiceKey` 含引擎 id 與版本 | BreezyVoice、Qwen3-TTS、Fun-CosyVoice3（2.2） |
| ASR 回驗 | 短中文句一個字聽錯是常態（lemo 的經驗）；簡繁、標點、數字寫法不同 | `transcribe(wav) -> text, words[]`；比對前雙邊正規化（SG-7）；逐句 `asr` 欄覆寫期望文字 | faster-whisper（lab `lyriclines.py` 已用）、Breeze-ASR-25 |
| 音樂分析（TL-4） | `beatgrid.py` 沒有強拍、不處理變速；W24 說剪點可能跟歌詞或曲式走 | `MusicCue.analysis` 是檔案契約；`first_downbeat` 人工覆寫 | beat_this（拍點＋強拍）、librosa（起音、能量） |
| 頁面合成 | 多片段疊層用 canvas 或 DOM 都可以 | `FilmPage` runtime 只呼叫 `draw`／`drawTransition`；DOM 片段用一個容器元素；常駐層各占一個 `z` | — |
| `texts()` 的執行環境 | Python 的 `tl.py` 不能直接執行 JS；Node 沒有 DOM 與字型量測 | `Validate.timed` 用 filmkit 同一個 Playwright／Chromium 執行片段程式取 `texts()`（SG-11） | Node（若片段不需 DOM） |

### 6.3 錨點解析的順序（Resolve）

1. 固定量：`format`、`lead`、`tail`；TL-4 起加音樂分析（分析檔存在才可用 `bar:`／`beat:`／`downbeat:`）。
2. 旁白：第一句從 `lead` 開始；句子依片段順序排列，每句長度＝`VoiceLock`（核可後）或 `voice/lines.json`（核可前）的實際 wav 長度（已裁掉頭尾靜音）；同一片段內句間＝`gap_after`，缺省 `line_gap`；換片段時，`section_gap` **取代**句間（是相鄰兩段之間的總靜音）。預設值是**選定值，不是中位數**（D-T10，暫定）：`lead` 1.0 s、`line_gap` 0.45 s、`section_gap` 1.2 s、`tail` 2.0 s。依據是 r8／r18 八組 arm 腳本（v2 驗證報告 W-3 逐檔查證）：

   | 組 | 開頭 | 句間 | 段間總靜音 | 結尾 | 段間寫法 |
   |---|---|---|---|---|---|
   | r8 A1 | 1.6（其後每段 1.0） | 0.45 | 2.3 | 3.0 | 段尾 1.3＋段首 1.0 分開記 |
   | r8 A3 | 1.2 | 0.45 | 2.5 | 1.3 | 段尾 1.3＋段首 1.2 分開記 |
   | r8 B1 | 1.0 | 0.45 | 1.1 | 3.0 | 取代 |
   | r8 B2 | 0.8 | 0.35 | 0.9 | 2.2 | 取代 |
   | r8 B3 | 1.2 | 0.35 | 1.1 | 3.0 | 取代（補差額） |
   | r8 B4 | 0.6 | 0.35 | 0.8 | 1.6 | 取代 |
   | r18 A1 | 1.0 | 0.45 | 1.75 | 3.5 | 累加（句間＋1.3） |
   | r18 B1 | 1.8 | 0.35 | 2.85 | 1.85 | 分開記 |

   範圍：開頭 0.6–1.8、句間 0.35–0.45、段間 0.8–2.85、結尾 1.3–3.5 s；八組中位數：開頭 1.1、句間 0.40、段間 1.43、結尾 2.6。選定值不依任何單一組，取在八組範圍內、靠近中位數的整齊數字；`tail` 取 2.0 是為了讓結尾停留落在使用者 W30（2026-10-10）裁定的 1.5–2.5 s 中間（§7.5 `end_hold`；v4 曾取 3.0 對齊先前 r14 的 2.5–3.5 s，D-T23）。第一支 DIT 片後由使用者聽過再調。三組把「段尾停留」與「段首空白」分開記；本設計不分（只有一個 `section_gap`），需要時在片段的 `declares.silences` 加（D-T10）。
3. 畫面片段：依 `at`／`dur` 求值；`at` 只能指向已求出的量（句子、前面的片段；TL-4 起小節），**禁止循環**，驗證器以拓樸排序檢查（TL-INV-2）。
4. 音效、字幕：最後求值。
5. 片長：`fit` 時＝最後一個片段結束＋`tail`，且 `film.end` 不可被引用（SEM-11）；`fixed` 時＝宣告值，最後一個片段超出片長是錯誤。兩種情形下，最後一個片段結束到片尾的時間，畫面都停在最後一格、聲音全部靜音（`mix.wav` 在這段把旁白、音樂、音效都截掉），由 `compile` **自動**寫成 `film_plan.json` 的一筆 `holds`（`why: "tail hold (D-T19)"`），不需要作者宣告（使用者 2026-10-09，W-7）；不自動伸縮。
6. 格點：所有片段邊界對齊到最近的影格（`round(t·fps)/fps`），句子時間保留原值；`ResolvedTimeline` 兩個值都記（SG-1）。
7. 接上片中空檔（D-T22）：步驟 3–6 全部求完之後才做；畫面軌上 `e_prev < t0` 的前一段延長到 `t0`，延長量記在 `ResolvedTimeline` 並列出。**錨點一律讀延長前的值**（`clip:S2.end` 指作者寫的結束），避免延長回頭改變錨點而不收斂（Y-2）。常駐層不延長：常駐層之間的空檔是正常的（SEM-13）。延長後的 `d` 只給 `draw`；TV-4（元件參數範圍）與 TV-6（讀字時間、`hold_range`）一律用延長前的作者值，延長量另由 TV-19 列出（Z-4）。

**TL-0 沒有旁白音檔時**（TTS 在 TL-2，V-28）：`Resolve` 接受 `voice/lines.json` 裡手填或估算的 `est_dur`（估算＝字數 ÷ 暫定語速），標記 `estimated: true`；時間軸頁以虛線顯示，`approve` 拒絕核可含估算時長的版本。

### 6.4 狀態機一：時間軸版本 (TimelineVersion)

狀態存在 `state.json`，不在時間軸檔內。

| 狀態 | 意思 | 事件 → 下一狀態 |
|---|---|---|
| `DRAFT` | 作者正在填 | `validate --static` 失敗 → `DRAFT`（附錯誤）；`--static` 過、`voice`／`resolve` 完成、`--timed` 過 → `VALID`；`--timed` 失敗 → `DRAFT`；TTS／ASR 引擎起不來 → `DRAFT`（`kind: env`，說出缺什麼）；放棄 → `ABANDONED` |
| `VALID` | 靜態與時間相依檢查都過，且產物與目前時間軸相符 | 時間軸、片段程式或旁白改動 → `DRAFT`；`approve`（使用者，或不在場時模型＋`questions.md`）→ `APPROVED`；`approve` 遇到估算時長 → 拒絕，留 `VALID`；`compile` → 拒絕（`kind: not_approved`）；放棄 → `ABANDONED` |
| `APPROVED` | `versions/<n>/` 寫入，唯讀屬性＋雜湊核對（BR-8、SG-12） | `compile` 成功 → `COMPILED`；`compile` 失敗 → 留 `APPROVED`（附 `kind`）；任何修改 → 新版本 `n+1` 的 `DRAFT`（本版不動）；放棄 → `ABANDONED` |
| `COMPILED` | `build/` 產物的來源雜湊＝本版 | 再次 `compile` → `COMPILED`（產物未變則不重寫）；filmkit 發佈了 `final.mp4` 且 0 擋件 → `RENDERED`；filmkit 失敗或有擋件 → 留 `COMPILED`（附 filmkit 的 `kind` 與擋件列）；修改 → 新版本 `DRAFT`；放棄 → `ABANDONED` |
| `RENDERED` | 有成片 | `intent` 跑完 → `REVIEWED`；`intent` 遇到儀器不在或失敗 → `REVIEWED`，標 `intent: skipped(<原因>)`，時間軸頁與交付清單明寫「意圖未量」；修改 → 新版本 `DRAFT`；放棄 → `ABANDONED` |
| `REVIEWED` | 成片＋意圖報告（或「意圖未量」）；等使用者看片 | 使用者看片後接受 → `DELIVERED`；使用者看片後回饋 → 新版本 `DRAFT`（本版標 `watched: true`）；放棄 → `ABANDONED` |
| `DELIVERED` | 終態 | — |
| `ABANDONED` | 終態；檔案保留不刪 | — |

不可能的轉移（工具擋）：`DRAFT`／`VALID` 直接 `compile`；`APPROVED` 原地修改；`MANIFEST` 內容雜湊不符時覆寫（TV-11）；指紋不符時 `compile`（TV-16）。

補充的格（W-13）：`approve` 遇到 D-T8 必填欄位缺值（TV-18）→ 拒絕，留 `VALID`；`APPROVED`／`COMPILED` 下 `intent` → 拒絕（`kind: not_current`：還沒有成片）；`RENDERED`／`REVIEWED` 下再 `compile` → 指紋與產物都相同，不重寫，狀態不變（BR-16）；`--by model` 核可的版本含任何覆寫 → 拒絕。filmkit 的失敗與時間軸無關時（例如字型素材漏列），補素材也是改輸入，照樣開新版本並重新核可——這是刻意的：核可的是「一組輸入」，不是「一份時間軸」。`parent` 存在 `approval.json`。

### 6.5 狀態機二：元件 (Component) 的證據狀態

| 狀態 | 意思 | 進入條件 |
|---|---|---|
| `draft` | 初始：有程式，selftest 還沒過 | 新建 |
| `candidate` | 可被選用 | selftest 過：亂序重跳 30 格同畫面、參數範圍、事件形狀、`intents` 欄位合格 |
| `in-use` | `candidate` 之上、至少一支用它的片已出片 | 該片進 `RENDERED` |
| `verified` | **單一元件**的盲化 A/B：同一份時間軸，只換「用它」與「不用它（同族另一元件或 `guided` 從零寫）」，各 3 次，量它宣告的意圖，範圍不重疊 | lab A/B 輪（TL-5 的元件層設計，§9） |

降級：技巧卡降級、或元件新版本（`version` 加一）→ 回 `candidate`，舊版本的證據保留在舊版本上（證據以「id＋版本」為單位）。之後任一支片的意圖報告對它宣告的意圖量到 `outside` → 清掉 `measured` 旗標；`verified` 退回 `in-use`；都在元件索引記下是哪支片；`undetermined` 不改狀態。

**兩個獨立旗標**（X-16：看片與量測是兩軸，進入順序是先量後看）：`watched`（用它的某支片離開 `REVIEWED`，即使用者看過）、`measured`（元件宣告了至少一條 `intents`，用它的片段經 `intent` 量過且全部 `within`；`intents` 為空的元件永遠不會有此旗標）。兩者都記在「id＋版本」上；之後量到 `outside` 時清掉 `measured`。

**對外宣稱的等級**（衍生）＝`min(元件等級, card_tier)`（`card: null` 時只看元件等級）。元件等級：`verified` → 已驗證；否則有 `watched` 或 `measured` → 「使用者看片」「已量」（有哪個標哪個，兩個都有就兩個都標，同一階）；否則 → 未驗證。順序：未驗證 < 使用者看片／已量 < 已驗證（BR-7、TL-INV-7）。

整包元件庫的 A/B（「有元件庫 vs 沒有」）結果記在元件庫層級，不提升任何單一元件。

### 6.6 狀態機三：旁白句 (Line) 與產生物 (BuildArtifact)

**Line**（`tl.py voice` 逐句）

| 狀態 | 事件 → 下一狀態 |
|---|---|
| `pending` | `VoiceKey` 有快取 → 用快取的轉寫和目前的 `text`／`asr` 重新比對 → `checked` 或 `mismatch`；無快取 → 合成 → `synthesized`；引擎失敗 → `failed(env)` |
| `synthesized` | 回驗相符（正規化後）→ `checked`；不符 → `mismatch`（列出聽成什麼）；ASR 引擎起不來 → `failed(env)` |
| `imported` | `voice --import` 的預錄音檔（TL-1）：長度可用、未回驗；TV-12 視同 `checked`，但 `approve` 輸出與時間軸頁標「未回驗」；TL-2 起可對它跑回驗 → `checked` 或 `mismatch` |
| `mismatch` | 作者改 `say` 或 `asr` → `pending`；重合成同鍵不會改變結果（鍵相同即同檔），要換參數才重做 |
| `checked` | `text`／`say`／`asr`／聲音參數改動 → `pending` |
| `failed(env)` | 引擎恢復 → `pending` |

TV-12：核可前每句都須 `checked`（作者用 `asr` 改了期望文字後重新比對相符，也是 `checked`）。核可時被引用的音檔複製進 `versions/<n>/voice/`；`voice/` 的快取可以清，已核可版本不受影響（TL-INV-11）。

**BuildArtifact**（`MANIFEST.json` 中每一列；只涵蓋 `compile` 的產物，§6.9）

| 狀態 | 判定 | `compile` 的行為 |
|---|---|---|
| `absent` | 檔案不存在 | 產生 |
| `current` | 內容雜湊相符、來源雜湊＝目前版本 | 不重寫 |
| `stale` | 內容雜湊相符、來源雜湊≠目前版本 | 覆寫 |
| `edited` | 內容雜湊不符 | 拒絕覆蓋（TV-11 blocking），提示改時間軸或片段程式；`--discard-edits` 才覆寫，並在 `revisions.md` 記一筆 |

### 6.7 時序：一支 DIT 片（成功一條；跨界失敗與重試一條）

```
成功：
author: 問答 → decisions → film.timeline.json
author: tl validate --static → ok
author: tl voice → L1–L9 checked（本機 TTS）
author: tl resolve → tl validate --timed → VALID → tl view → timeline.html
user  : 看時間軸頁 → 「OK」
author: tl approve --by user --note "OK" → versions/1, APPROVED
author: tl compile → COMPILED；filmkit render.py → final.mp4（check.md：0 擋件）→ RENDERED
author: tl intent → intent.md（cut_on_line 4/4 within ±0.15 s；end_hold 2.1 s within 1.5–2.5 s；各附儀器限制）→ REVIEWED
user  : 看片 → 接受 → DELIVERED

跨界失敗與重試：
author: tl voice → L5 mismatch（念成「載入點 jsonl」）；L7 failed(env)：TTS 模型載入失敗
        → 五行：Failed: voice — 1 mismatch, 1 env；hint：L5 加 say 欄位；L7 檢查 TTS 安裝（指令）
author: L5 加 say；修好 TTS → tl voice → L5、L7 checked（其餘 7 句走快取）
author: tl resolve → S3、S4 時間跟著移 → tl validate --timed → VALID → user OK → APPROVED → compile
filmkit: render.py → Failed: asset_load（字型不在頁面資料夾）→ 狀態留 COMPILED
author: 查 build/render.cmd.txt 與頁面資料夾：字型素材漏列在 assets → 補 Asset → 輸入改動 → 新版本 2 DRAFT（parent 1）→ … → RENDERED
author: tl intent：lab 儀器不在這台電腦 → REVIEWED，intent: skipped(instruments unavailable)；交付清單寫「意圖未量」
user  : 回饋「S3／標題太小」→ 改 clips/S3.js → 新版本 3 DRAFT（versions/2 不動）→ … → tl revise → revisions.md：S3 片段程式指紋不同；所有片段時間平移 0
author: （若有人在 APPROVED 之後直接改 clips/S3.js 再 compile → TV-16 擋：「clips/S3.js 與版本 3 的指紋不符，請開新版本」）
```

### 6.8 元件篩選決策表（`validate` 與 `compile` 共用）

輸入：片段的 `freedom`、`role`、`device`、`override`；`decisions` 的 `energy`、`film_type`、`rhythm_source`；元件的 `family`、`tone`、`when`、`conflicts`。**兩張表都要過**：表 A 決定元件可不可用，表 B 是獨立檢查，不受表 A 的停止規則影響（V-18）。

**表 A：元件可用性**（由上往下，第一列成立即停；v3 把「元件不存在」移到「決策缺值」之前，W-19(b)）

| # | 條件 | 結果 |
|---|---|---|
| A1 | `freedom: free` | 不篩選元件；只檢查 `ClipContract`、時間窗、底色例外宣告（SEM-7）；片段程式若呼叫元件，該元件仍須 `tone` 相容（同 A4／A5 的判法） |
| A2 | `freedom: locked`，`device.component` 不存在 | blocking：「元件不存在」，列出同 `family` 的現有元件 |
| A3 | 片段需要的決策（`energy` 或 `film_type`）缺值 | `locked`：指定的元件 `tone` 不是 `any` → blocking「先定 energy／film_type」，是 `any` → 往 A4–A6 判（`tone` 視為相容，`when` 照判）。`guided`：照 A7 篩，但 `tone` 條件改為「只收 `any`」。`validate.json` 記「決策未定，依最字面解讀」（SEM-10） |
| A4 | `freedom: locked`，元件 `tone` 或 `when` 與決策不相容，`override.source = user` 且有 `confirmed` | 通過並標「待你確認」：時間軸頁頂端與 `approve` 第一行逐條列出；`approve --by model` 時改為 blocking（W-12） |
| A5 | `freedom: locked`，不相容（無有效覆寫） | blocking（TV-3、TL-INV-5）；模型寫的覆寫視同無效 |
| A6 | `freedom: locked`，相容 | 通過；參數範圍交給 TV-4 |
| A7 | `freedom: guided` | 候選＝`family` 相符 ∧ `tone` 含 `energy` ∧ `film_type` 相容 ∧ `when(role, rhythm_source)` 成立 ∧ 不與任何 **`locked`** 片段的元件 `conflicts`；寫進 `build/clips/<id>.candidates.json`。候選為空 → info：「這一類沒有合格元件」，AI 從零寫，仍受 `ClipContract` 約束 |

`guided` 片段之間的 `conflicts` 不在候選階段判（AI 的選擇有先後，會循環，V-18(5)）；改由 `validate --static` 從程式抽出 `uses` 後一次判定（TV-15）：兩個片段 `uses` 互相衝突 → look，列出兩段。常駐層片段（`overlay`）照同一張表判，`role` 取 `overlay`。

**轉場元件**（X-2）：`transition_in.component` 照表 A 判，`freedom` 取所屬片段的值、`role` 取 `transition`：`locked` 片段的轉場走 A2–A6（`tone`／`when`／`conflicts`、使用者覆寫）；`guided` 片段的 `transition_in` 空著時（D-T14「空著就放開」），寫片段的 AI 從 A7 的轉場候選清單挑一個寫進 `transition_in`（或明寫 `"cut"`＝硬切）——片段程式拿不到前一段，轉場只能由 runtime 畫，所以「放開」指的是「由 AI 選、選好就寫下來」；到 `approve` 還空著＝硬切，並在 `approve` 第一行列出（Y-5）。`guided` 片段寫下的轉場元件必須在它的轉場候選清單內（TV-15）。`free` 片段的轉場照 A1 的判法（只看 `tone` 相容）。

**表 B：獨立檢查**

| # | 條件 | 結果 |
|---|---|---|
| B1 | `guided` 片段的 `uses` 含不在候選清單的元件 | blocking（SEM-6、TV-15；在 `validate --static`，核可之前） |
| B2 | 任一級，元件或片段屬老梗手法族（§7.4 `stock_devices`） | `motion_intent` 必填（TV-5 blocking） |
| B3 | `free` 片段秒數比例 > 規則檔門檻（暫定 30%） | look（TV-10） |

### 6.9 和 filmkit 的介面條目（V-24）

| 介面 | 本層的承諾 |
|---|---|
| 頁面資料夾封閉（filmkit FK-INV-9） | `compile` 把頁面用到的每個檔（素材、字型、片段程式、元件 js 及其 `requires`、runtime）複製到 `build/` 頂層（扁平、檔名用安全別名，§10 TG-17），`MANIFEST` 列全；`copy_build()` 只複製頂層也不會開出空白頁。 |
| `build/` 的擁有者（W-9） | `compile` 擁有：`index.html` 與其扁平相依檔、`film_plan.json`、`events.json`、`captions.srt`、`mix.wav`、`render.cmd.txt`、`MANIFEST.json`。`validate`／`resolve`／`view`／`intent`／`revise` 擁有各自的輸出（`validate.json`、`timeline.resolved.json`、`timeline.html`、`intent.*`、`revisions.md`、`clips/*.candidates.json`），隨時可重寫，不進 `MANIFEST`。filmkit 擁有 `final.mp4`、`render.json`、`check.*`、`<檔名>.check.*`、`sheet_1fps.png`、`*.transform.json` 與 `transform.py` 產生的新檔、子資料夾 `.filmkit/`（暫存、鎖檔與 `lock.json`）：`tl` 不寫、不刪、不搬，也不整個替換 `build/` 資料夾（filmkit 以 `render.json` 判斷成片歸屬）。`compile` 先核對全部自己的產物（TV-11）與版本內容（TV-16），全部通過才開始寫第一個檔；寫入逐檔原子替換（寫 `.tmp` 再改名）。 |
| 指令 | `render.py build/index.html -o build/final.mp4 --plan build/film_plan.json --audio build/mix.wav --rules <lab>/tools/filmkit_rules.json --film-type <對照後的片型>`（`-o` 依 filmkit §4 權威旗標；`--rules` 讓 FK-R-16 生效，W-10）；`compile` 把完整指令寫進 `build/render.cmd.txt`。規則檔不在時省略 `--rules`，`render.cmd.txt` 與五行 Notes 寫明「filmkit 規則檢查未啟用」。 |
| `film_plan.json` 欄位 | 預期值（`duration_s`、`size`、`fps`、`audio_expected`）、`film_type`（本層詞彙到規則檔片型詞彙的對照表在 PSM）、段落（片段 id 與起訖）、`holds`／`blacks`／`silences`（**影片時間**，每段有 `why`，FK-INV-8）、旁白句時間（鍵名 `narration_lines`，每句 `id`、`t0`、`t1`）。schema 以 filmkit PSM 的 `film_plan.schema.json` 為準——**filmkit PSM 是 TL-1 的前置**。 |
| `--plan` 與旗標分階段生效 | filmkit M0 只讀預期值；M2 起讀宣告欄位與旁白句（FK-R-15 的宣告重疊檢查，filmkit D27），並才有 `--rules`、`--film-type` 與規則檢查（FK-R-16）；M3 起再用旁白句判 FK-R-9 的旁白句靜音。filmkit M0 起就嚴格驗證整份計畫檔：`compile` 不得加 schema 以外的欄位（要擴充走 `schema_version`），也不得寫零長度區間（`fixed` 片長而最後一段恰好結束於片尾時，片尾停留與片尾靜音那兩筆要省略；filmkit PSM 驗證 P-21）。filmkit M0–M3 已在 main 建成（2026-10-10），所以 `render.cmd.txt` 一律帶 `--film-type`，規則檔存在時帶 `--rules`；規則檔不在時省略 `--rules`，Notes 寫「filmkit 規則檢查未啟用」（X-5，v4.4；上面的分階段說明保留為歷史）。TL-1 的完成證據只依賴 M0 的部分（§9）。 |
| 規則檔 | 共用 `tools/filmkit_rules.json`（D-T18）；TV-7 與 FK-R-16 讀同一個鍵；鍵的 schema 由 filmkit PSM 擁有，本層新增的鍵（`free` 比例門檻、旁白高於音樂的差距、峰值上限、`stock_devices`）在本層 PSM 提出、併入同一份 schema。 |
| 沒有聲音軌時 | 片子沒有旁白、音樂、音效時不產生 `mix.wav`，`render.cmd.txt` 省略 `--audio`，`film_plan.json` 的 `audio_expected` 為 false。 |
| 混音長度與規格 | `mix.wav` 48 kHz 立體聲 PCM，長度補靜音到片長（filmkit SG-9 的容差另由 filmkit 處理）。混音是**產生**步驟，規則檔不在時不能回「無法判定」：改用本層 PSM 寫死的後備值（峰值上限、旁白高於音樂的差距），並把「用了後備值」寫進 `MANIFEST` 與五行 Notes（W-10）。 |
| 片尾停留（D-T19） | `compile` 把「最後一個片段結束 → 片尾」自動寫成一筆 `holds`（影片時間，`why: "tail hold (D-T19)"`），filmkit 不會把它當成未宣告的凍結。 |
| 自動宣告的靜音（X-6） | `compile` 依 `mix.wav` 實際無聲的區間（開頭 `lead`、句間 `line_gap`、段間 `section_gap`、片尾）自動寫 `silences`（`why` 指出是哪一種停頓）；有音樂時這些區間不是靜音，就不寫。片尾例外：D-T19 規定片尾全部靜音，所以片尾一定寫一筆 `silences`（`why: "tail silence (D-T19)"`）。 |

### 6.10 失敗種類（五行輸出的 `kind`；PSM 定完整表）

`spec_invalid`（schema、錨點、元件不存在）、`not_approved`、`not_current`（前一步的產物和目前時間軸不符，說出該先跑哪一步）、`env`（TTS／ASR／Chromium／ffmpeg 起不來）、`voice_mismatch`、`edited_output`（TV-11）、`fingerprint_mismatch`（TV-16）、`missing_required`（TV-18）、`busy`（另一個 `tl` 行程持有鎖，§0.4）、`instrument_unavailable`（`intent`）、`internal`。任何降級（例如 `texts()` 取不到而 TV-6 回無法判定）都寫進五行的 `Notes:` 與 `validate.json`（SG-14）。

## §7 DSL 語意契約

### 7.1 時間軸檔的骨架（示意；完整 schema 在 PSM）

```json
{
  "meta": {"schema_version": 1, "film_id": "dit-promo",
           "format": {"size": "1920x1080", "fps": 30, "duration_policy": "fit"},
           "lead": 1.0, "tail": 2.0},
  "decisions": {
    "film_type": {"value": "product-tour", "source": "user"},
    "audience":  {"value": "第一次聽說 DIT 的 AI 工具使用者", "source": "user"},
    "energy":    {"value": "calm", "source": "user"},
    "rhythm_source": {"value": "narration", "source": "default", "evidence": "T08 / BR-5"},
    "ground":    {"value": "#f6f1e7", "source": "model", "evidence": "whole-film-rules §1"}
  },
  "assets": [
    {"id": "cap-sidebar", "kind": "capture", "path": "assets/sidebar.png", "sha256": "…", "license": "own"},
    {"id": "dit-name", "kind": "logo", "path": "assets/dit-wordmark.svg", "sha256": "…", "license": "own",
     "portrays": {"subject_name": "DIT"}}
  ],
  "tracks": {
    "narration": [
      {"id": "L1", "text": "從一直按同意，到看懂這次是怎麼做出來的", "section": "S1"},
      {"id": "L2", "text": "…", "section": "S2"}, {"id": "L3", "text": "…", "section": "S2"},
      {"id": "L4", "text": "…", "section": "S2"}
    ],
    "picture": [
      {"id": "S1", "role": "opening", "at": 0, "dur": {"lines": "L1-L1", "pad_after": 0.3},
       "freedom": "locked", "device": {"component": "opening.shape-to-name@1", "params": {"source_asset": "cap-sidebar", "name_asset": "dit-name"}},
       "motion_intent": ["結構符號一個個畫出：產品看的就是這個結構", "收成產品名：結構＝產品"]},
      {"id": "C1", "role": "chapter-card", "at": {"anchor": "clip:S1.end"}, "dur": 1.4,
       "freedom": "locked", "device": {"component": "chapter-card.verb@1", "params": {"verb": "看懂", "index": "01 / 03"}},
       "motion_intent": ["動詞卡：標出下一段要做的事"]},
      {"id": "S2", "role": "feature", "at": {"anchor": "line:L2.start", "offset": -0.15}, "dur": {"lines": "L2-L4", "pad_after": 0.3},
       "transition_in": {"component": "transition.dim-through-ground@1", "dur": 0.3},
       "freedom": "guided", "device": {"family": "ui-demo"},
       "headline": "…", "motion_intent": ["游標點下時間軸：指出這一步在哪裡"]},
      {"id": "E1", "role": "end-card", "at": {"anchor": "clip:S2.end"}, "dur": 0.8,
       "freedom": "locked", "device": {"component": "end-card.restate@1", "params": {"line": "L1", "name_asset": "dit-name"}},
       "motion_intent": ["重述主句後收成產品名：記住的是這一句"]}
    ],
    "overlay": [],
    "music": null, "sfx": [], "captions": {"from": "narration", "style": "caption.bottom-band@1"}
  }
}
```

（示意驗算，`section_gap` 1.2：S1 結束＝L1.t1＋0.3；L2 起點＝L1.t1＋1.2；C1＝[L1.t1＋0.3, L1.t1＋1.7)；S2 起點 t0＝L2.t0−0.15＝L1.t1＋1.05，轉場窗＝[L1.t1＋1.05, L1.t1＋1.35)，換段時刻＝窗中點＝L1.t1＋1.2＝L2.t0，TV-2 偏差 0（離 ±0.15 的邊界 4.5 格）。SEM-2：C1 最晚只能延伸到窗尾 L1.t1＋1.35，實際到 L1.t1＋1.7，**超出 0.35 s（10.5 格），這份示意應該被 SEM-2 擋下**，在 §8 當正對照用；把 C1 的 `dur` 改成 0.9（延伸 0.15 s，離窗尾 0.15 s＝4.5 格）即合法。TV-14：轉場窗起點 L1.t1＋1.05 晚於前一句 L1 結束 L1.t1，不蓋句。S1→C1、S2→E1 都首尾相接，沒有片中空檔（D-T22）。結尾：E1 用 0.8 s 收成產品名，之後 `tail` 自動停留 2.0 s，`end_hold`＝2.0 s，在 TV-7 的 1.5–2.5 s 中間；E1 是標語型（D-T15），不套讀字公式。）

### 7.2 語意（每一條都是規則，不是建議）

| ID | 語意 |
|---|---|
| SEM-1 | 轉場只寫在進場片段的 `transition_in`（`{component, dur}` 或 `"cut"`；缺省＝`"cut"`，任何 `freedom` 都一樣，Z-7；以下 `tdur`＝`transition_in.dur`，硬切時 `tdur`＝0；`0 < tdur ≤` 本段長度）。轉場窗＝`[t0, t0 + tdur)`（`t0`＝本段起點）；窗內 runtime 以 `TransitionContract` 呼叫轉場元件，`to` 畫本段（`lt = t − t0`），`from` 畫前一段（`lt = min(t − t0_prev, d_prev)`）；兩者 `lt` 恆 ≥ 0。下一段的轉場窗不得在本段的轉場窗結束前開始：`t0_next ≥ t0 + tdur`（X-14）。 |
| SEM-2 | 同一條畫面軌上，前一段的結束 `e_prev` 必須 ≤ `t0 + tdur`；超出是 blocking。**片中不留空檔**（使用者 2026-10-09，D-T22）：`e_prev < t0` 時，`resolve` 把前一段延長到 `t0`（硬切接上；延長後的 `d_prev` 就是 `draw` 拿到的 `d`），並在 `validate.json` 與時間軸頁列出「S2 延長 0.75 s 接上 C1」，作者可改成宣告轉場。所以轉場窗內 `from` 畫的是前一段延長後的最後一格（不會出現與前一段無關的畫面；v4.4 更正，Z-3）。底色只出現在第一個片段開始之前（若第一段不從 0 開始）。最後一個片段結束到片尾：畫面停在最後一格，由 `compile` 自動宣告為停留（D-T19，§6.3 步驟 5）。常駐層另見 SEM-13。 |
| SEM-3 | `dur: {lines: "La-Lb", pad_after}` ＝從片段開始到 Lb 結束，再加 `pad_after`；涵蓋的句子必須屬於這個片段（`Line.section`）。 |
| SEM-4 | `rhythm_source: narration` 時，`role` 為 feature、本段至少有一句（`Line.section`）、且不是全片第一個畫面片段的片段，其「換段時刻」必須在本段第一句句首 ±0.15 s 內（T08）。換段時刻＝`t0 + tdur/2`（`tdur`＝轉場長度，不是片段長度；硬切時就是 `t0`；中點是「最劇烈的一刻」的近似）。`at` 可寫成任何錨點，判的是解析後的時刻（TV-2）。`music-bar`（TL-4）同理，對象是小節線（T04）；`content` 不檢查換段時刻。`rhythm_source: music-bar` 而旁白軌非空 → blocking（BR-5「擇一當主」）。 |
| SEM-5 | `locked` 片段同一元件版本、同一參數，在同一個 `format` 下逐格相同（TL-INV-3，同機同版，SG-4）。 |
| SEM-6 | `guided` 片段的程式只能呼叫該片段候選清單內的元件；`validate --static` 從程式抽出 `uses` 並核對（表 B1、TV-15），`compile` 用同一支抽取器再核一次。 |
| SEM-7 | `free` 片段只受 `ClipContract`、時間窗、`decisions.energy` 與底色約束；底色例外必須宣告（`ground_exception` 帶 `why`）。 |
| SEM-8 | `captions.from: narration` 時，字幕＝每句 `text` 與其 `t0/t1`；字幕不得手寫第二份（BR-1、BR-9）。 |
| SEM-9 | 片段的 `declares`（片段內時間）由 `compile` 換成影片時間後寫入 `film_plan.json`，每段保留 `why`（filmkit FK-INV-8）。 |
| SEM-10 | 決策缺值：草稿階段由 `tl` 填入（`freedom` 缺 → `guided`；決策缺 → 最字面解讀，`source: default` 或 `model`），並在 `validate.json` 與時間軸頁標出；核可時 D-T8 的必填欄位必須存在（`source` 可以是 `model`，但不可缺）。片段的 `at`、`dur`、`motion_intent` 推不出來，`tl` **不補**：缺值時 `validate` 回 blocking 並指出缺哪一欄（X-13）。 |
| SEM-11 | `film.end` 只在 `duration_policy: fixed` 下可被引用，值＝宣告片長；`fit` 下引用 `film.end` 是 schema 錯誤（避免「以自己的結束定義自己」的循環）。 |
| SEM-12 | `Clip.speed` 只改變片段程式拿到的 `demoTime(lt)`；標題、字幕與讀字時間一律以影片時間計（skill `build-and-export.md` §1）。倍速表的形狀由 TV-17 檢查；「展示有沒有拖」本身量不了，交使用者看片（BR-14）。 |
| SEM-13 | 常駐層（`overlay`）片段可以和畫面段、和其他 `z` 的常駐層重疊；同一個 `z` 上不得重疊（常駐層沒有轉場）；常駐層之間的空檔是正常的，不套 D-T22 的延長。畫的順序：畫面段（含轉場）→ 常駐層依 `z` 由小到大 → 字幕。常駐層的 `lt` 從它自己的 `t0` 起算，跨越畫面段的換段不重置（D-T20）。 |

### 7.3 驗證規則

`static`＝不需秒數即可判；`timed`＝吃 `ResolvedTimeline`；`intent`＝成片後由 `Intent` 量（不是驗證器）。嚴重度：invariant 支撐的列固定；其餘標「暫定」者由第一支 DIT 片後使用者裁決（D-T9）。規則檔缺席時，依賴它的列回「無法判定：規則檔不在」，不靜默通過（TL-INV-10、V-25）。

| ID | 階段 | 檢查 | 依據 | 嚴重度 |
|---|---|---|---|---|
| TV-1 | static | schema 合格（含 `motion_intent` 欄位必須存在）；ID 唯一；錨點可解析、無循環；`film.end` 只在 `fixed`；`transition_in.dur` 在 `(0, 本段長度]`；SEM-3 涵蓋的句子屬於本段 | TL-INV-2、SEM-1、SEM-3、SEM-11 | blocking（固定） |
| TV-2 | timed | 換段時刻落在句首 ±0.15 s（SEM-4）；`music-bar` 與旁白並存；SEM-2 的段間重疊、SEM-1 的轉場窗相疊（`t0_next < t0 + tdur`）與 SEM-13 的同 `z` 重疊 | BR-5、T08、BR-1 | blocking（固定） |
| TV-3 | static | 表 A 的 A2／A3／A5，對象含每個片段的 `transition_in.component`（§6.8「轉場元件」） | BR-2、TL-INV-5 | blocking（固定） |
| TV-4 | static（TV-4a）／timed（TV-4b） | 參數在元件宣告的範圍內；元件的 `requires` 全部存在。與片段長度綁定的參數（例：章節卡 `dur`）要解析後才有值，拆到 timed，讀延長前的作者值（v4.4，PSM 驗證 P-2） | 元件 schema（BR-3）、BR-16 | blocking（固定） |
| TV-5 | static | 每個片段 `motion_intent` 非空（欄位存在由 TV-1 管）；老梗族非空（表 B2） | BR-6 | blocking（老梗，固定）／look（其他空白，暫定） |
| TV-6 | timed | 讀字時間：非標語型文字停留 ≥ 中文字數 ÷ 4.5 ＋ 其他字元 ÷ 15 ＋ 1.5 s（lemo `readcheck`，**未在 lab 驗證**）；有標題的頁 ≥ 約 3.2 s（使用者 r19）；標語型元件（`label_type`：章節卡、動詞卡、拍點字卡、重述主句的結尾卡）改核 `hold_range`（D-T15） | BR-14 | look（暫定） |
| TV-7 | timed | 結尾停留＝最後一個片段結束到片尾的時間（`fit` 時就是 `tail`；`fixed` 時是剩下的時間），加上最後一個片段宣告在結尾的 `holds`（與 §7.5 `end_hold` 同一定義：結尾卡收完之後靜止的時間，使用者 r14「收完標誌、停 2.5–3.5 s」，W30 2026-10-10 改為 1.5–2.5 s），在規則檔的範圍 | BR-14 | look（暫定） |
| TV-8 | static | 底色：列出所有 `ground_exception`（帶 `why`）；片段沒有「宣告底色」欄位，靜態端只能檢查例外有沒有寫理由，實際底色由成片後的 `ground_locked` 量（X-9） | BR-14（使用者 r10、r12） | look（暫定） |
| TV-9a | static | 產品片：`headline`、`data` 的數字與功能文字有 `claim`；產品名只來自 `Asset.portrays` | BR-12、T05 | `validate` 時 look；`approve` 時 blocking（X-9） |
| TV-9b | timed | 產品片：**每個**片段 `texts()` 回傳的數字與功能文字有 `claim`；`texts()` 是否如實報告畫出的字無法驗證（TG-19），成片後再由 `claims_traceable` 補查 DOM 文字 | BR-12、T05 | `validate` 時 look；`approve` 時 blocking |
| TV-10 | timed | `free` 片段秒數比例（BR-3 的「預設 `guided`」不被架空） | BR-3、BR-4 | look（門檻暫定） |
| TV-11 | compile | `MANIFEST` 內容雜湊不符（被手改） | TL-INV-1 | blocking（固定） |
| TV-12 | timed | 每句 `Line` 為 `checked` | BR-5（句子時間＝念出來的時間）、BR-16；橫切「失敗要自己說出來」 | blocking（核可前，固定） |
| TV-13 | static | 片段程式靜態掃描：`Date`、`Math.random`（未用 lib 的種子版）、`setTimeout`／`setInterval`／`requestAnimationFrame`、`fetch`、CSS 動畫宣告、GSAP `.to(` | TL-INV-3、BR-16 | look（暫定；亂序重跳是最終判準） |
| TV-14 | timed | 轉場窗起點不早於它之前最後一句的結束（使用者 r13 判讀「下一段的轉場不能蓋掉上一段的最後一拍」） | BR-14 | look（暫定） |
| TV-15 | static | `guided` 片段程式抽出的 `uses` 都在候選清單內（表 B1）；`guided` 片段寫下的 `transition_in.component` 在轉場候選清單內；兩個 `guided` 片段的 `uses` 互相 `conflicts` | BR-2、BR-3、SEM-6 | blocking（候選外，固定）／look（互相衝突） |
| TV-16 | compile | `versions/<n>/` 內的片段程式與元件副本、素材、旁白音檔副本、`tools/timeline` runtime 與 `approval.json` 的版本指紋不符 | BR-8、BR-16、TL-INV-12 | blocking（固定） |
| TV-17 | static | 倍速表：`speed.asset` 存在且是影片類素材；展示時間區間自 0 起連續、無洞、不超過 `Asset.duration_s`；倍速 > 0 | BR-14（展示不能拖，使用者 r14，未驗證）、SEM-12 | look（暫定） |
| TV-18 | approve | D-T8 必填欄位存在；無估算時長；`--by model` 時無覆寫；TV-9a／9b 的 blocking 部分 | BR-2、BR-3、BR-12、SEM-10 | blocking（固定） |
| TV-19 | timed | `fixed` 片長下最後一個片段超出片長；`resolve` 為接上空檔而延長的片段（D-T22，列出供作者決定是否改成轉場） | BR-1、BR-3 | blocking（超出）／info（延長） |

### 7.4 詞彙表（固定值）

- `Component.family`：`opening`、`chapter-card`、`end-card`、`feature-frame`、`ui-demo`、`data-viz`、`text-treatment`、`transition`、`camera`、`background`、`motif`、`caption`。
- `stock_devices`（老梗族，存在規則檔，可由使用者增減）：`particle-burst`、`tunnel`、`floating-card-pile`、`glitch`、`big-text-as-design`、`fake-hud`（production-order E）。元件以 `stock: true` 標記；片段的 `device.family` 也可以是其中之一。
- `camera.goal`（D1）：`lead-eye`、`section-change`、`show-product`、`opening-in`、`ambience`、`none`；`camera.method`（D2）：`stage-2d`、`card-3d`、`scene-3d`、`single-layer`、`footage`。
- 基調只由 `decisions.energy` 定；`device.tone`（選填）只能比它更窄。

### 7.5 意圖宣告與量測（BR-13）

意圖有三種來源：由決策推導（例：`rhythm_source: narration` → 每個受 SEM-4 檢查的 feature 片段一條 `cut_on_line`）、由元件宣告（`Component.intents`，例：結尾卡 → `end_hold`）、作者手寫（片段的 `intents`）。

| `kind` | 宣告時刻 `moment` | 預設容差 | 儀器 | 儀器限制（照錄 lab 文件，報告必附） |
|---|---|---|---|---|
| `cut_on_line` | 換段時刻（SEM-4） | ±0.15 s（T08） | `segments.py` 取換段事件 ＋ `narrlock.py --srt build/captions.srt`；`Intent` 把每個宣告的換段配對到 ±0.5 s 內最近的量到事件，配不到＝`undetermined` | 分不出換段和段內的大型展開；句子很密時檢定變弱（T08 工具限制、lab CLAUDE.md）；事件或句子少於 3 個時整條回 `undetermined`，預設略過 2.0 s 以前的事件（`narrlock.py`）；常駐層（`overlay`）會讓 `segments.py` 漏掉換段，只換標題時要加 `--crop`（`segments.py` 檔頭） |
| `cut_on_bar`（TL-4） | 換段時刻 | 依 T04（PSM 定） | `measure_product.py` | 拍點網格分不出哪一拍是小節第一拍（T04） |
| `end_hold` | 結尾卡收完之後到片尾的靜止時間（與 TV-7 同一定義；filmkit FK-R-16 量的也是這一段） | 規則檔範圍 | `density.py`，**需先擴充**：它目前只輸出靜止段的統計（`n`、中位數、p90、最大值），沒有位置，取不到「最後一段」；TL-3 為它加上靜止段清單輸出並補正反對照（片尾靜止 2.0 s 的合成片／片尾一直在動的合成片）。擴充前此列回 `undetermined`（Y-3） | `density.py` 自述：比 `--thr` 灰階／每格更慢的變化（很慢的淡變、次像素漂移）讀成靜止，停留會讀成**偏長**；看縮圖確認 |
| `ground_locked` | 全片 | 0 次未宣告換色 | `bgswitch.py` | 全幅插畫片量不了；轉場不算換色（0.5 s 代理）（lab CLAUDE.md） |
| `claims_traceable` | 全片 | 0 筆無出處 | `fidelity.py` | 只列清單不下判定；語意誇大與非產品 UI 要人讀（lab CLAUDE.md）；**畫進 `<canvas>` 的文字讀不到**（`fidelity.py` 檔頭），Canvas 片段只能靠 `texts()` 自報（TG-19） |

報告規則：每條寫「儀器名、量到的值、宣告的範圍、`within`／`outside`／`undetermined`＋原因、儀器限制原文」；「對上」只表示「量到的值落在宣告的範圍內」；全文第一行寫「畫面好壞未判斷」（INV-6、TL-INV-8）。

### 7.6 不變式

| ID | 不變式 |
|---|---|
| TL-INV-1 | `compile` 的每個產生物（§6.9 擁有者清單）在 `MANIFEST` 有內容雜湊與來源雜湊；內容雜湊不符時工具拒絕覆蓋並說明（BR-1）。雜湊一律正規化後計算：UTF-8 無 BOM、LF、JSON 排序鍵、正斜線路徑（SG-2）。 |
| TL-INV-2 | 錨點圖是有向無環圖；解析結果與求值順序無關（BR-1、BR-5）。 |
| TL-INV-3 | 元件與片段程式是 `lt` 的純函數：亂序重跳同一格得到同一畫面（同機同版）（BR-16）。 |
| TL-INV-4 | 三級片段都經過同一套 `ClipContract` 與 filmkit 檢查；沒有任何片段繞過檢查（BR-4）。 |
| TL-INV-5 | 元件與整片決策衝突時，元件出局；只有使用者覆寫（`source: user`＋確認原話）才例外（BR-2）。 |
| TL-INV-6 | `versions/<n>/` 寫入後不可變（唯讀屬性＋雜湊核對）；每個新版本在 `approval.json` 記 `parent`（BR-8）。 |
| TL-INV-7 | 對外宣稱的元件等級 ≤ 技巧卡等級；工具輸出的每個參數都帶等級（BR-7）。 |
| TL-INV-8 | 工具不輸出「好看」「完成」之類的字；意圖報告每條附儀器限制（INV-6、BR-13）。 |
| TL-INV-9 | 時間軸頁、字幕、`film_plan.json`、修改紀錄都由檔案生成，不手寫第二份（BR-9）。 |
| TL-INV-10 | 受測 arm 只在 round 檔中該 arm 寫 `timeline_lib: true` 時拿到 `tools/timeline/`；規則檔不隨掛載，相關檢查回「無法判定」；`run.json` 記版本雜湊（BR-10、BR-14）。 |
| TL-INV-11 | 核可版本的時間只由 `versions/<n>/` 的時間軸、`VoiceLock` 與音檔副本決定；之後再跑 `voice` 或清掉 `voice/` 快取，都不會改變已核可版本的任何時間或聲音（BR-8、BR-16）。 |
| TL-INV-12 | `compile` 只用 `versions/<n>/` 的副本與指紋相符的素材；任一不符就不產生任何檔（BR-8、BR-16）。 |

## §8 驗證設計

### 8.1 工具自己的正反對照

| 對象 | 正對照（應該觸發） | 反對照（不應觸發） |
|---|---|---|
| 錨點循環（TV-1） | S2.at → S3.end、S3.at → S2.end | 一條鏈 S1 → S2 → S3 |
| `film.end`（TV-1、SEM-11） | `fit` 下結尾卡 `at: film.end − 3` | `fixed` 下同一寫法 |
| 重疊（SEM-2、TV-2） | §7.1 示意原樣（C1 超出轉場窗尾 0.35 s） | C1 `dur` 改 0.9（延伸 0.15 s，在 0.3 s 窗內，離邊界 4.5 格） |
| 節奏（TV-2、SEM-4） | `narration`，S2 換段時刻在句首後 0.4 s | §7.1 的 S2：句首 −0.15 s 起 0.3 s 轉場，中點正在句首（偏差 0）；全片第一個**畫面**片段（不論 `role`，例如 S1）與沒有句子的 feature 片段不檢查 |
| 片中空檔（D-T22、TV-19） | — | C1 結束早於 S2 起點 0.2 s → `resolve` 把 C1 延長到 S2 起點並列出；S2 若有轉場，窗內 `from` 畫 C1 延長後的最後一格（Z-3） |
| 錨點讀延長前的值（Y-2、Z-4） | 讀延長後值的實作（測試替身）→ S3 起點不同或不收斂，selftest 比對抓得到 | S3 `at: clip:S2.end + 0.5`、S2 被延長 0.3 s → S3 從 S2 作者寫的結束＋0.5 開始，解析收斂 |
| 轉場元件（X-2、表 A） | `energy: calm` 的片，`locked` 片段的 `transition_in` 用 `hype` 專屬轉場 → TV-3 擋；`guided` 片段 `transition_in` 空著到 `approve` → 列為硬切 | 相容的轉場 → 過 |
| 轉場窗相疊（SEM-1） | 前一段轉場窗 [10, 11)，下一段 `t0` 10.5 → 擋 | 下一段 `t0` 11.0 |
| 元件不存在（表 A A2） | `locked` 指定 `chapter-card.verb@9` → 擋並列出同族元件 | `@1` |
| 不輸出評語（TL-INV-8） | 輸出含「好看」「完成」字樣 → selftest 失敗 | 五行與意圖報告只有量值與限制 |
| 相依元件（TV-4） | 元件 `requires` 一個不存在的元件 → 擋 | 存在 |
| 常駐層（SEM-13） | 兩個 `z: 1` 的常駐層時間重疊 | `z: 1` 與 `z: 2` 重疊；常駐層跨過 S1→S2 換段，`lt` 不重置 |
| 片尾停留（D-T19） | — | `fit`＋`tail` 2.0：`timeline.resolved.json` 有片尾停留區間（TL-0）；`film_plan.json` 出現 `why: "tail hold (D-T19)"` 的停留（TL-1）；filmkit 不報未宣告凍結（filmkit M2 起才有 FK-R-8，之前無從觀察） |
| 涵蓋句子（SEM-3、TV-1） | `dur: {lines: "L2-L4"}` 但 L3 屬於 S3 | 全屬本段 |
| 宣告換算（SEM-9） | — | 片段 `t0` 5.0 s、宣告 `holds` 片段內 1.0–2.0 s → `film_plan.json` 寫 6.0–7.0 s，帶 `why` |
| 草稿補值（SEM-10） | 核可時缺 `energy` → TV-18 擋 | 草稿缺 `freedom` → 填 `guided`、標 `source: default`、時間軸頁顯示 |
| 決策缺值（表 A A3） | 缺 `energy`，`locked` 指定非 `any` 元件 → 擋 | 缺 `energy`，`locked` 指定 `any` 元件 → 過；`guided` 候選只剩 `any` |
| 基調衝突（TV-3） | `energy: calm` 的片 `locked` 用 `hype` 專屬元件 | 同元件用在 `lively` |
| 覆寫（TV-3、A4） | 不相容＋`override.source: model` → 仍擋；不相容＋`source: user`＋`confirmed`，但 `approve --by model` → 擋 | 不相容＋`source: user`＋`confirmed`，`--by user` → 過，且 `approve` 第一行列出「待你確認」 |
| 參數範圍（TV-4） | 章節卡 `dur` 參數超出元件範圍 | 範圍內 |
| 動作意圖（TV-5） | `glitch` 族片段 `motion_intent: []` | 同片段寫一句意圖 |
| 讀字時間（TV-6） | 非標語文字 18 字停 2.0 s | 同文字停 6.0 s；標語型章節卡 0.9 s 在 `hold_range` 內 |
| 結尾停留（TV-7） | `tail` 5.8 s（r14 判太長的值） | §7.1 的 `tail` 2.0 s |
| 底色（TV-8） | `ground_exception` 沒有 `why` | 有 `why` |
| 宣稱（TV-9a／9b） | 畫面數字無 `claim`；產品名不在 `portrays`；`locked` 元件 `texts()` 回傳的數字無 `claim` | 都有出處 |
| 候選外元件（TV-15） | `guided` S2 的程式呼叫了不在 `S2.candidates.json` 的元件 → `validate --static` 擋（核可前） | 只呼叫候選內元件 |
| 版本指紋（TV-16、TL-INV-12） | 核可後改 `clips/S3.js` 一個字再 `compile` → 擋並說出檔名；改元件資料夾內容但不改 `version` → 擋 | 未改時 `compile` → 過 |
| 倍速表（TV-17） | 展示區間有洞、或超出 `Asset.duration_s`、或 `speed.asset` 不是影片 | 自 0 起連續、在長度內 |
| 必填（TV-18） | 缺 `rhythm_source`；含估算時長 | 全部存在 |
| 版本不可變（TL-INV-6） | 對 `versions/1/timeline.json` 寫入 → 唯讀拒絕；繞過唯讀改內容 → 下次啟動雜湊核對報錯 | — |
| 等級上限（TL-INV-7） | 元件有 `measured` 旗標但 `card_tier` 未驗證 → 對外標「未驗證」 | `card: null` 的元件只看自己的狀態 |
| 同等檢查（TL-INV-4） | `free` 片段的程式丟例外 → 整片 `page_runtime` 失敗 | `free` 與 `locked` 片段走同一個 filmkit 檢查清單 |
| 生成不手寫（TL-INV-9） | 手改 `build/captions.srt` → TV-11 擋 | 字幕只由旁白軌生成 |
| 混音（BR-15） | 音樂比旁白響、差距小於規則值 → 列出；加總後峰值超過上限 → 限峰並記錄 | 差距足夠、峰值在上限內；缺規則檔 → 用後備值並寫進 Notes |
| 可重現（BR-16） | — | 同一版本 `compile` 兩次 → `build/` 內 `compile` 產物位元組相同 |
| 秒數查詢（BR-11） | `tl.py at dit 12.0` 落在 C1 與 S2 的轉場窗 → 回兩個片段 ID 並標「轉場中」 | 落在 S2 中段 → 回 S2、句子 ID、片段內時間 |
| 快取重比（W-11） | 改 `asr` 期望文字使之與快取的轉寫不同 → `mismatch` | 改成相符 → `checked`，不重新合成 |
| 自由度比例（TV-10） | `free` 佔 40% | 10% |
| 手改（TV-11、TL-INV-1） | 改 `build/index.html` 一個字後 `compile` → 擋；改時間軸後 `compile` → `stale` 正常覆寫 | 未改時 `compile` → 不重寫 |
| 正規化雜湊 | 同一時間軸 CRLF 與 LF 兩份 → 雜湊相同 | 改一個字 → 不同 |
| 回驗（TV-12） | 一句合成音故意與稿子不同字 → `mismatch` | 相符 → `checked`；簡繁不同但正規化後相同 → `checked` |
| 聲音鎖（TL-INV-11） | 核可後改 TTS 語速再跑 `voice` → `versions/1` 的時間不變 | — |
| 靜態掃描（TV-13） | 片段程式含 `Date.now()` | 只用 `lt` |
| 純函數（TL-INV-3） | 一個讀 `Date.now()` 的測試元件亂序重跳 → 畫面不同 | 正常元件亂序 30 格 → 相同 |
| 轉場蓋句（TV-14） | 轉場窗起點早於它之前最後一句的結束 | 不早於（§7.1 的 S2：窗起點晚於 L1 結束 1.05 s） |
| 不可能的轉移（§6.4） | `VALID` 直接 `compile` → `not_approved`；`APPROVED` 下 `intent` → `not_current` | `APPROVED` → `compile`；`RENDERED` 下再 `compile` → 不重寫、狀態不變 |
| 意圖對量測（§7.5） | r8 一支 arm 成片（換段鎖句首）配自己的字幕 → `within` | 同成片配另一支片的字幕（T08 的真實反對照方法）→ `outside` |

### 8.2 端到端

用時間軸重做 r7 的 DIT 片：和 r7 原片並排給使用者看；`intent` 全部 `within` 或明寫 `undetermined` 的原因。

### 8.3 「穩定」怎麼量（TL-5）

同一份時間軸（同一 `APPROVED` 版本），重跑 `guided`／`free` 片段的撰寫 3 次：

1. **時機**：`cut_on_line`、`end_hold` 等意圖的 `within` 比例（目標 100%，`locked` 片段必須 100%）。
2. **結構**：`segments.py` 量到的換段次數與時刻，3 次之間的範圍。
3. **相似度**：`runsim.py` 的組內視覺相似度——**不設目標**，只記錄；它和「呈現抽卡」的取向互相拉扯，高低由使用者看片判斷。

元件庫 A/B（整包）：對照組＝無時間軸層、同一份 brief；比 1、2 的組間範圍是否不重疊（lab 的 `variance.py` 形式）。單一元件的 `verified` 用 §6.5 的設計。

## §9 里程碑與降級順序

| 里程碑 | 內容 | 完成的證據 | 依賴 |
|---|---|---|---|
| TL-0 格式與視圖 | schema（含 `overlay` 軌）、`validate --static`、`resolve`（秒數＋句子錨點＋片段錨點；旁白時長可手填或估算）、`validate --timed`（不需執行片段程式的列：TV-2／7／10／14／19）、`view`、`approve`（含 `VersionFingerprint`）、`at`、`state.json`、正規化雜湊；RG1；把 DIT 草稿（`rounds/brief-dit-promo-v1-draft.md`）寫成第一份時間軸 | §8.1 中 TV-1／2／5／7／8／10／14／17／18／19、SEM-1／2／3／10／13、片中空檔、片尾停留（`resolve` 端）、`film.end`、正規化雜湊、TL-INV-6、秒數查詢的正反對照過；TV-3／4／15 用**測試夾具**（假的 `components/index.json` 與假片段程式）跑對照；使用者看 DIT 的時間軸頁，說得出「哪段、何時、用什麼」 | 無（可和 filmkit PSM 並行）；TL-0 沒有片段程式執行環境，TV-6／9b 回「無法判定」，`approve` 第一行列出並記進 `approval.json` 的 `undetermined`；TL-0 的 `approve` 用不含旁白或不含估算時長的測試夾具驗證（DIT 草稿含估算時長，`approve` 拒絕＝真資料正對照）；產品片版本帶著未判定的 TV-9b 時，TL-1 `compile` 拒絕（`not_approved`，Z-8） |
| TL-1 元件與編譯 | `ClipContract`、`TransitionContract`、`FilmPage` runtime（含常駐層）、`compile`（含扁平相依、`film_plan.json`、`events.json`、`captions.srt`、`render.cmd.txt`、片尾停留與靜音宣告、只有旁白的 `Mix`）、`voice --import <dir>`（資料夾內每句一個 `<line_id>.wav`，來源是使用者錄的或任何本機產生的音檔；轉成 48 kHz 單聲道、裁頭尾靜音；狀態 `imported`）與 `VoiceLock`、TV-4／6／9a／9b／11／13／16；三個 `locked` 元件（opening.shape-to-name、chapter-card.verb、end-card.restate）＋一個轉場元件＋ `guided` 片段；字幕元件 | 元件 selftest；TV-6／9b／11／12（`imported` 算過、標未回驗）／16、TL-INV-4／9／12、BR-16、片尾停留（`film_plan.json` 端）、不可能的轉移（`compile` 那幾格）的正反對照；DIT 片以匯入的預錄旁白出片（標「未回驗」；filmkit M0：只用到預期值）；RG3、RG4、RG6 | **filmkit PSM（`film_plan.schema.json`）＋ filmkit M0** |
| TL-2 旁白 | 本機 TTS 試跑選定（D-T11）、`voice` 合成（`VoiceKey` 快取與轉寫快取、回驗、`Line` 狀態機）、`Mix` 加音樂（48 kHz、不削波、旁白高於音樂的規則差距、缺規則檔的後備值；不閃避） | 一支有旁白的 DIT 片；TV-12、TL-INV-11、快取重比、混音的正反對照 | 本機 TTS 在 Windows 可用；TL-1 |
| TL-3 意圖對量測與修改 | `intent`（§7.5 的四種，`cut_on_bar` 除外）、`revise`（兩版 `resolved`＋指紋差異） | §8.1 意圖對量測的正反對照；一次完整的回饋重做；§8.2 | lab 儀器（已存在）＋ `density.py` 擴充（RG11：lab 儀器改動，須跑 selftest，片尾靜止與片尾一直在動兩個合成片，Z-5）；TL-1 |
| TL-4 音樂與 PV／MAD | `tl.py music`（beat_this＋`first_downbeat` 覆寫）、`bar:`／`beat:`／`downbeat:` 錨點、`cut_on_bar`、音效事件、T12／T13 轉場元件、T15 母題回調、T16 歌詞字處理；歌詞錨點等 W24；外部元件等 W28 | 一支短 MAD 片 | W24（歌詞時間） |
| TL-5 lab A/B | `run_arm.py` 的 `timeline_lib`；§8.3 的量法；單一元件 `verified` 的輪次設計 | 盲化比較，§8.3 的 1、2 範圍重不重疊 | TL-1＋TL-2＋TL-3 |
| 延伸 | 可編輯 GUI、逐段快取、相似度提醒、全域升級 | 觸發條件見 §11 | — |

預算不夠時砍的順序：先砍 TL-4，再砍 TL-3 的 `revise`（回饋改由手動編輯時間軸、不產生差異報告），再砍 TL-2 的音樂混音（只出旁白軌）。**TL-0 的格式、驗證、解析與 TL-1 的 `ClipContract` 永遠不砍**：它們就是痛點本身。

## §10 語意缺口登記

**全部 platform-conditional**，寫給這個平台類別：Windows 11＋NTFS；Python `tl.py`；頁面由 filmkit 以 Playwright（Python）驅動 Chromium 擷取；ffmpeg 8.1；片段程式是瀏覽器內 JS（Canvas 2D／DOM，第一版不用 WebGL）；本機 TTS 與 faster-whisper。PSM 選定版本後逐條重跑。

| ID | 語意 | 缺口 | 橋接 | 是否扭曲語意 |
|---|---|---|---|---|
| TG-1 | 句子時間＝念出來的時間 | TTS 音檔頭尾有靜音；ASR 字級時間約 0.1 s 誤差（T08 工具限制） | 裁掉頭尾靜音（r8 各組腳本都有裁切）；句首以裁切後音檔起點為準，不用 ASR 時間；字級時間只作診斷 | 不扭曲 |
| TG-2 | 小節線（TL-4） | `beatgrid.py` 沒有強拍、不處理變速；beat_this 可能錯拍 | beat_this ＋ `first_downbeat` 人工覆寫；分析檔可人工修 | 不扭曲；分析錯誤由人看 |
| TG-3 | `guided`＝只放開畫法 | AI 在片段程式裡可以畫任何東西，包括偷換底色、塞老梗、不照手法類別 | 底色由 `Intent` 的 `ground_locked` 在成片上量（`bgswitch`）；老梗只能讀宣告（TV-5）與程式掃描；手法類別、`layout`、`camera.*` 有沒有照做只能人看：時間軸頁把這些欄位與該段縮圖並列 | **部分扭曲**：工具抓得到底色與文字，抓不到「手法類別、排版、運鏡有沒有照做」（D-T14 的「填了就固定」對這三者只是給作者的指示，只有 `transition_in` 由 runtime 執行）、也抓不到「每個元素各有意圖」（TV-5 只查非空） |
| TG-4 | 元件純函數＝逐格相同 | 字型柵格化、GPU 合成可能讓同一格跨機器有像素差 | 純函數檢查在同機比對編碼前 PNG；跨機器不保證 | **部分扭曲**：SEM-5／TL-INV-3 只保證同機同版 |
| TG-5 | 讀字時間公式 | lemo 的 4.5 字／秒是簡中、英文受眾的經驗值，lab 沒量過；混排的換算是假設 | 列 look，不擋；標語型豁免（D-T15）；第一支片後使用者校準 | 可能扭曲，待使用者裁決 |
| TG-6 | 片段程式是 `lt` 的純函數 | GSAP `.to()` 起始值在第一次渲染時才取，亂序 seek 可能和順播不同（外部說法，未在原文確認） | TV-13 靜態掃描列 look；亂序重跳（TL-INV-3）是最終判準 | 不扭曲 |
| TG-7（SG-1） | 時間是連續秒 | filmkit 以格為單位（`i/fps`）；0.45 s ≠ 整數格；邊界那一格屬誰取決於浮點 | 片段邊界對齊格點、句子時間保留原值，`ResolvedTimeline` 記兩值（§6.3 步驟 6） | 不扭曲（誤差 ≤ 半格，遠小於 ±0.15 s） |
| TG-8（SG-2） | 雜湊＝同一內容 | CRLF／LF、BOM、鍵順序、路徑大小寫 | 正規化雜湊（TL-INV-1）；清單記完整 sha256 | 不扭曲 |
| TG-9（SG-3） | 頁面只讀自己資料夾 | 素材、字型、片段程式在 `build/` 外；ES module 在 `file://` 受限 | `compile` 扁平複製並改寫參照；runtime 不用 ES module 跨檔載入（PSM 探針確認） | 不扭曲 |
| TG-10（SG-5） | 片段程式不留狀態、不取網路 | AI 寫的程式可用禁用 API；一個片段例外讓整片失敗 | TV-13；filmkit 擋網路請求；例外＝整片 `page_runtime` 失敗並說出哪一格、哪個片段 | 不扭曲 |
| TG-11（SG-6） | 核可後時間不變 | TTS 非決定性、引擎更新 | `VoiceKey`＋`VoiceLock`（TL-INV-11） | 不扭曲 |
| TG-12（SG-7） | 回驗＝念的和稿子一樣 | 簡繁、標點、數字寫法；RTX 5070 上 CTranslate2 未驗、退回 CPU 的耗時未知 | 比對前雙邊正規化（繁簡轉換、去標點、數字讀法）；`asr` 覆寫 | 不扭曲 |
| TG-13（SG-9） | 混音＝按時間疊聲音 | 音效多時濾鏡圖超過 Windows 命令列長度；取樣率不一；相加削波 | `-filter_complex_script` 寫檔；統一 48 kHz；加總前留餘量並限峰值（不訂響度，BR-15） | 不扭曲 |
| TG-14（SG-10） | 字型就緒與文字量測 | 系統 CJK 後備字型讓字數與實際換行不同 | 字型隨頁複製（TG-9）；TV-6 以字元數計，不以行數計 | 不扭曲 |
| TG-15（SG-11） | `texts()` 可在驗證時取得 | 需要 JS 引擎與字型 | `Validate.timed` 用 filmkit 的 Playwright／Chromium；取不到時 TV-6 回無法判定並說明 | 不扭曲；成本是驗證變重 |
| TG-19（X-7） | 畫面上的每段文字都可追溯（BR-12） | Canvas 2D 畫出的字沒有 DOM，`fidelity.py` 讀不到；`texts()` 是片段程式自報，報少了工具不知道 | `locked` 元件的 `texts()` 由元件 selftest 對照畫面確認；`guided`／`free` 片段的文字建議走 DOM 容器（`fidelity.py` 讀得到），走 Canvas 時只能靠 `texts()` 自報＋人看縮圖 | **部分扭曲**：Canvas 片段的 BR-12 只到「自報有出處」，不到「畫出的字都有出處」 |
| TG-16（SG-12） | 核可版不可變 | NTFS 只能靠唯讀屬性與雜湊核對；多檔寫入非原子 | 唯讀＋啟動時核對；`approve` 先寫 `versions/<n>.tmp/` 再整體改名；`compile` 在 `build/` 內逐檔原子替換，不整個替換 `build/`（filmkit 的檔在裡面，§6.9） | 不扭曲 |
| TG-17（SG-13） | 路徑與編碼 | 中文路徑、260 字元上限、`@`、`:` 不能當檔名 | 檔名用安全別名，ID 與檔名分開；一律 `-X utf8` | 不扭曲 |
| TG-18（SG-15） | 同時只有一個執行者寫 `build/`、`versions/` | 使用者手動重跑與對話中的 `tl` 可能重疊 | 沿用 filmkit 的 `msvcrt.locking` 位元組鎖於 `<film>/.tl.lock`；取不到 → `busy` | 不扭曲 |

（驗證報告的 SG-4 併入 TG-4、SG-8 併入 TG-2、SG-14 併入 §6.10。）

## §11 延伸與開始建置的時機

| 延伸 | 開始的時機 |
|---|---|
| 可編輯 GUI（拖拉片段、改錨點） | 使用者連續兩支片都反映「在對話裡改太慢」，或時間軸格式連續兩支片沒有改動（格式穩定） |
| 逐段快取重出（做法備註 2026-10-10，借 Videomass 的無損串接想法、不用其程式：每段以 filmkit 同一編碼規格各自編碼、段首必為關鍵格，改過的段重出後以 ffmpeg concat 直接複製串流組回；聲音整片另混一次再封裝，不逐段接音軌） | filmkit 的「逐格快取」觸發條件成立 |
| 逐段候選版本與受影響段清單（2026-10-10 借 Toonflow 的做法：一段一節點、每段保留各次生成結果可挑選；它沒有的「上游改了標出哪些段要重做」由本層補上：`revise` 已有兩版指紋差異，延伸成「受影響的段」清單，並保留同一段的舊版本供選回）。只借概念，不採用 repo（Toonflow 是生成式 API 的無限畫布，和本層的時間軸主幹、逐格算繪不同典範） | TL-3 的 `revise` 做完之後，且第一支 DIT 片的回饋重做中，出現「改一段卻得整支重做」或「想回到上一版的某一段」至少一次 |
| 相似度提醒（和上一支片比，借 lemo「不要再做一次 demo」） | 同一片型做到第 3 支 |
| 歌詞錨點 | W24 的歌詞時間工具通過 selftest |
| HyperFrames／gl-transitions 的潔淨分析元件 | W28 的觸發條件（使用者說開始，或 TL-1 後某支片需要卡片沒涵蓋的元件） |
| 每型別 schema 版本、`defaults` 繼承（D-T16） | 時間軸格式第一次需要不相容改版，或同一欄位在 3 個以上片段重複填 |
| 全域升級（`~/.claude/tools` 或 AssetVault） | 第二個專案實際呼叫；或貼文工作流的全域化設計回合要合併影片版 |

## §12 決策登記

| # | 決策 | 狀態 | 決定者 | 日期 |
|---|---|---|---|---|
| D-T1 | 第一支驗證片＝DIT 宣傳片，之後 PV／MAD | 已定 | 使用者 | 2026-10-08 |
| D-T2 | 片段三級自由度 `locked`／`guided`／`free`，預設 `guided`；元件庫的價值不因藝術片而下降——選用時機與基調可決定，呈現可抽卡；藝術片範圍＝lab 研究中的 PV、MAD、之後的動畫；保留自由接口（`free`） | 已定 | 使用者 | 2026-10-08 |
| D-T3 | 第一版：對話填導演表＋生成的唯讀時間軸頁；可編輯 GUI 延後 | 已定 | 使用者 | 2026-10-08 |
| D-T4 | 正式片先；受測 arm 只在 A/B 輪掛載元件庫（預設不掛）；filmkit 維持它的 D2 | 已定 | 使用者 | 2026-10-08 |
| D-T5 | 設計等級標準 (Standard)，附 DSL 語意契約 | 已定（可逆） | 模型 | 2026-10-08 |
| D-T6 | 延伸 filmkit，不另建出片層；時間軸層產生 filmkit 的輸入 | 已定（可逆） | 模型 | 2026-10-08 |
| D-T7 | lemo-opuscar 只借概念；不引入程式；W08 結案 | 已定 | 使用者讀了 repo；模型判定借用範圍 | 2026-10-08 |
| D-T8 | 製作單四項：載體＝JSON 時間軸檔＋生成的時間軸頁（替代方案：Markdown 表格無法驗證、表單＝GUI 已延後）；核可時必填＝決策的 `film_type`、`audience`、`energy`、`rhythm_source`，與每個片段的 `at`、`dur`、`freedom`、`motion_intent`（草稿階段可缺：`freedom` 由 `tl` 填入並標示；`at`、`dur`、`motion_intent` 推不出來，缺值時 `validate` 指出缺哪一欄，SEM-10）；D1／D2 運鏡值是固定詞彙表（§7.4）；節點升成預設值＝元件到〔已量〕以上 | 已定 | 使用者 | 2026-10-08 |
| D-T9 | **只限暫定（look）列**的嚴重度與門檻：`free` 比例（暫定 30%）、讀字時間公式、TV-5（其他空白）／6／7／8／10／13／14／15（互相衝突）／17；有不變式支撐的 blocking 列不在此列 | 待定：第一支 DIT 片後由使用者裁決 | 使用者 | — |
| D-T10 | 停頓預設：`lead` 1.0、`line_gap` 0.45、`section_gap` 1.2、`tail` 2.0 s（v4 由 2.5 改為 3.0，X-6；v4.3 依 W30 改為 2.0，D-T23）——**選定值，不是中位數**（八組腳本實測表在 §6.3；v1 的「0.35／0.8」與 v2 的「中位數 1.1／2.0」都不實）；不分段首段尾，需要時用片段的 `declares.silences` | 暫定（可逆；第一支 DIT 片後使用者聽過再調） | 模型 | 2026-10-09 |
| D-T11 | TTS 只用本機；TL-2 前在本機試跑 BreezyVoice、Qwen3-TTS、Fun-CosyVoice3 選一個；ASR 用 faster-whisper，試 Breeze-ASR-25；edge-tts 不用 | 已定 | 使用者 | 2026-10-08 |
| D-T12 | 元件以技巧卡為主；HyperFrames 的資料先記著，之後以潔淨分析（Clean Room Analysis）抽取核心，固定內容的撰寫不派 Haiku：它是製作，不是機械性任務（使用者 2026-10-11，PSM §0 第 4 題：Haiku 的用法與全域派工規則一致，只用於蒐集、盤點這類有硬驗收閘的機械任務；影片製作的指揮與工人都不用，見 2026-10-10 裁決。v4.5）；W28＋`docs/clean-room-component-extraction.md` | 已定 | 使用者 | 2026-10-08 |
| D-T13 | gl-transitions 不直接採用，併入 W28 潔淨分析；第一版不依賴 WebGL | 已定 | 使用者 | 2026-10-09 |
| D-T14 | `guided` 的轉場、排版、運鏡：填了就固定，空著就放開（轉場的「放開」＝寫片段的 AI 從轉場候選挑一個或選硬切，核可前寫下，§6.8；排版、運鏡是給作者的指示，TG-3） | 已定 | 使用者 | 2026-10-09 |
| D-T15 | 讀字時間依元件類別豁免：標語型（章節卡、動詞卡、拍點字卡；2026-10-09 加重述主句的結尾卡，X-17）改核元件的停留範圍；要讀的文字才套公式，仍只列「要你看」 | 已定 | 使用者 | 2026-10-09 |
| D-T16 | 每型別 schema 版本（OTIO）、`defaults` 繼承（editly）延後；第一版只有全域 `schema_version` | 已定（可逆） | 模型 | 2026-10-09 |
| D-T17 | 小節錨點不進 TL-0～TL-3；TL-4 用 beat_this（本機，MIT）＋人工指定第一個強拍 | 已定（可逆） | 模型提出，使用者確認（W-6） | 2026-10-09 |
| D-T18 | 設計規則只有一個檔：和 filmkit 共用 `tools/filmkit_rules.json`；缺檔時相關檢查回「無法判定」，混音改用明寫的後備值 | 已定（可逆） | 模型 | 2026-10-09 |
| D-T19 | 片尾空檔（`fit` 的 `tail`、`fixed` 最後剩下的時間）：畫面停在最後一格、聲音全部靜音（旁白、音樂、音效），工具自動宣告為停留與靜音 | 已定 | 使用者（W-7；v4.1 曾誤改為「只靜旁白」，使用者 2026-10-09 再裁決還原，Z-2） | 2026-10-09 |
| D-T20 | 新增常駐層軌 `overlay`：可和畫面段重疊、同樣遵守片段契約與檢查；T04 常駐錨點、T15 母題、PV／MAD 背景用它 | 已定 | 使用者（W-21） | 2026-10-09 |
| D-T21 | 覆寫的「使用者原話」工具無法驗證：A4 改為「通過並標待你確認」，在核可點列出；`--by model` 核可時一律擋 | 已定（可逆） | 模型 | 2026-10-09 |
| D-T22 | 片中不留空檔：空檔要嘛插轉場、要嘛硬切把兩段接起來（硬切也是一種轉場）；畫面軌上任何 `e_prev < t0` 的空檔（有沒有轉場都一樣），`resolve` 自動延長前一段到 `t0` 並列出；延長後若有轉場，轉場窗內 `from` 停在前一段延長後的最後一格 | 已定 | 使用者（X-3） | 2026-10-09 |
| D-T23 | `end_hold`＝結尾卡收完之後的靜止時間，以 `density.py` 量；`tail` 預設 2.0 s。使用者 2026-10-10 在 W30 把片尾停留改為 1.5–2.5 s，原本的 3.0 s 落在範圍外；v4.3（2026-10-10）改為 2.0 s，§5 的示意輸出、§6.3、§7.1 範例與示意驗算、§7 TV-7、§7.5 對照合成片、§8.1 兩列同步改 | 已定（可逆） | 模型 | 2026-10-10 |
| D-T24 | 片段程式與元件資料夾複製進 `versions/<n>/`、`compile` 從副本編譯；runtime 雜湊入指紋；共用規則檔不入指紋 | 已定（可逆） | 模型 | 2026-10-09 |
| D-T25 | TL-1 以 `voice --import` 匯入預錄旁白出片（標「未回驗」），TL-2 才加本機 TTS 與回驗，解開 TL-1／TL-2 的循環 | 已定（可逆） | 模型 | 2026-10-09 |

## §13 尚未完成的部分（SKELETON 聲明）

- **v4.1 未再跑驗證**：v4 聚焦重驗（`verification_timeline-layer-design-v4_2026-10-09.md`）只擋 Y-1 一行（`Clip` 欄位表殘留的 family-only 轉場寫法），判定「刪掉且無新擋件即 PASS-WITH-FIXES」；v4.1 刪了它並處理 Y-2～Y-9（§14.5）。PSM 的追溯表要逐項關閉 v4 報告 §5 列出的項目。
- **v4 只做了聚焦重驗**：v3 報告（`verification_timeline-layer-design-v3_2026-10-09.md`）判定「X-1～X-3 修好且沒有新擋件即為 PASS-WITH-FIXES」；v4 修了 X-1、X-2，X-3 由使用者裁決，X-4～X-18 在文中處理（§14.4）。PSM 開寫前，PSM 的追溯表仍要逐項關閉 X-4～X-18。
- **PSM 未寫**：完整 schema、`tl.py` 子命令的旗標與退出碼、`ClipContract`／`TransitionContract` 的 JS 介面、`FilmPage` runtime、混音規格、`film_type` 詞彙對照、失敗種類完整表、測試對應，都在驗證通過後另寫英文 `docs/timeline-layer-psm.md`。
- **filmkit 尚未建置；PSM v1.3 已寫（2026-10-09；經三輪獨立驗證，v1.2 為 pass-with-fixes，v1.3 依使用者裁決不再重驗）**：片型詞彙以 motion-video skill 的 `film-types.md` 為準，filmkit 規則檔 `film_types` 用其章節對應的英文代號（filmkit PSM §4.5），本層詞彙若不同，對照表放本層 PSM。TL-1 之後的里程碑都依賴 filmkit PSM 的 `film_plan.schema.json`（PSM §4.1）、規則檔 schema（PSM §4.5：本層的鍵放 `params.timeline`、片型詞彙對到 `film_types`）與 filmkit M0。建議順序：filmkit PSM → filmkit M0 ∥ TL-0 → TL-1。
- **本機 TTS 未試跑**：TL-2 依賴 D-T11 的試跑結果；三個候選在 Windows 都未驗證。
- **`MusicCue.analysis` 的欄位形狀**刻意不凍結，到 TL-4 的 PSM 才定（避免假精確，V-35）。

## §14 追溯表

### 14.1 業務規則 → PIM 元素

| 業務規則 | PIM 元素 |
|---|---|
| BR-1 單一來源、可追、可偵測手改 | `ResolvedTimeline`、`Manifest`、§6.6 BuildArtifact、TL-INV-1、TL-INV-2、TV-11、SEM-8 |
| BR-2 決策先於手法、只認使用者覆寫 | `Decisions`、`Clip.override`、§6.8 表 A、TV-3、TL-INV-5 |
| BR-3 三級自由度、預設 guided、guided 的填了就固定 | `Freedom`、`Clip` 欄位對照表、SEM-5／6／7／10、§6.8 A1／A6／A7、TV-4、TV-10 |
| BR-4 自由度不放開規則 | `ClipContract`、`TransitionContract`、TL-INV-4、TG-3 |
| BR-5 節奏來源、擇一當主 | §6.3、SEM-4、TV-2、`IntentDecl.cut_on_line` |
| BR-6 動作意圖、老梗 | `Clip.motion_intent`、§7.4 `stock_devices`、§6.8 B2、TV-5 |
| BR-7 參數證據等級、不高於卡 | `Component.params`、§6.5、TL-INV-7 |
| BR-8 核可版不可變（含旁白） | §6.4、`VoiceLock`、`versions/<n>/`、TL-INV-6、TL-INV-11、TV-12 |
| BR-9 生成不手寫 | `View`、`Revise`、SEM-8、TL-INV-9 |
| BR-10 arm 掛載 | RG5、TL-INV-10 |
| BR-11 回饋對到片段 | §5.1 回饋格式、時間軸頁的片段 ID、`tl.py at`、`Revise` |
| BR-12 宣稱可追溯、身分不可編造 | `Asset.claims_ref`、`Asset.portrays`、`ClipContract.texts.claim`、TV-9、`claims_traceable` |
| BR-13 意圖對量測 | `IntentDecl`、`IntentReport`、`Intent`、§7.5、`Component.intents`、TL-INV-8、TL-3 |
| BR-14 設計規則檢查 | TV-6／7／8／14、共用規則檔（D-T18）、`ground_locked`、TL-INV-10 |
| BR-15 混音音量 | `Mix`、`SfxEvent.gain_db`、TG-13 |
| BR-16 可重現 | TL-INV-3、TL-INV-11、TL-INV-12、SEM-5、TV-13、TV-16、`VoiceKey`、`VersionFingerprint` |

**v3 補列的 PIM 元素 → 業務規則**（v2 報告 W-5：§14.1 原本不窮盡）

| PIM 元素 | 業務規則 |
|---|---|
| SEM-1、`TransitionContract`、TV-14 | BR-4（轉場也走同一套契約）、BR-14（轉場不蓋句） |
| SEM-2、SEM-13、`OverlayClip`、TV-19 | BR-1（時間只有一種算法、片中不留空檔 D-T22）；常駐層：BR-3 末句（跨段常駐元素只畫一次，D-T20、T04、T15） |
| TG-19 | BR-12（Canvas 文字的追溯限制） |
| SEM-3 | BR-5（片段長度跟著句子） |
| SEM-9、片尾停留（D-T19） | BR-1、BR-9（宣告由檔案生成） |
| SEM-11、TV-1 | BR-1、TL-INV-2 |
| SEM-12、`Clip.speed`、TV-17 | BR-14（展示不能拖，使用者 r14，未驗證） |
| TV-15 | BR-2、BR-3 |
| TV-16、`VersionFingerprint`、TL-INV-12 | BR-8、BR-16 |
| TV-18 | BR-2、BR-3、SEM-10 |
| `tl.py at` | BR-11 |
| `MusicCue` | BR-5（TL-4 的小節節奏來源） |
| `Asset.license`、`Component.license`／`provenance` | 僅記錄，無業務規則消費（刻意：給人看的出處） |
| `Component.requires` | BR-16（缺相依就出不了同一個頁面），由 TV-4 檢查 |
| `Component.card_tier` | BR-7、TL-INV-7 |

橫切規則（不屬業務層，引名稱）：**失敗要自己說出來**（global CLAUDE.md「deliverable can fail at runtime」）→ 五行輸出、§6.10 失敗種類、TV-12、`page_runtime` 不吞例外；**可替換的弱點**（design-rules）→ §6.2 弱點表；**語意缺口登記** → §10；**閘門只裁決能確定的事**（global CLAUDE.md「automated gate」）→ 規則檔缺席回「無法判定」、TV-13 只列 look。

`Decisions` 的非必填欄位（`purpose`、`shown_where`、`viewer_action`、`voice`、`presentation`、`remember_one`）沒有檢查消費者：它們是使用者在步驟 0 的回答紀錄，呈現在時間軸頁（BR-2 的「決策」本身）；刻意不檢查。

### 14.2 驗證報告 v1 的最小行動集合 → v2 處理

| 行動 | 處理 |
|---|---|
| 1 意圖宣告語意（V-1、V-33） | BR-13、§7.5、`IntentDecl`、`IntentReport` |
| 2 其餘孤兒（V-2） | `markers` 刪除；BR-15（混音）；BR-14（設計規則） |
| 3 覆寫（V-3、V-19） | `Clip.override`、§6.8 A4／A5、§5.1、§8.1 對照 |
| 4 產生物清單與雜湊（V-4、V-15、SG-2） | `Manifest`、§6.6 BuildArtifact、TL-INV-1、`state.json` |
| 5 聲音進版本（V-5、SG-6） | `VoiceKey`、`VoiceLock`、TL-INV-11、`voice/` 移出 `build/` |
| 6 `film.end` 與片長（V-6） | SEM-11、SEM-2、§6.3 步驟 5 |
| 7 驗證順序（V-7、V-28、SG-11） | §4 固定順序、`validate --static`／`--timed`、§6.3 估算時長、TG-15 |
| 8 版本狀態機缺格（V-8、V-16） | §6.4 改寫、`ABANDONED`、`intent: skipped` |
| 9 元件證據（V-9、V-17） | §6.5 改寫、`Component.intents`、等級對照 |
| 10 使用者裁決（V-10～V-14） | D-T8（必填與預設調和：SEM-10）、D-T17（V-11）、D-T13（V-12）、D-T15（V-13）、D-T14（V-14） |
| 11 不實前提（V-23、V-34） | D-T10、§6.3、§2.2 librosa／faster-whisper、§6.1 欄位對照表、版本與模組數 |
| 12 缺口登記（V-31、SG-1…15） | §10 標 platform-conditional、TG-4 改部分扭曲、TV-13 對應 TG-6、TG-3 改由 `Intent` 量、TG-7～TG-18 |
| 13 filmkit 介面（V-24、V-25） | §6.9、D-T18 |

其餘 should-fix：V-18 → §6.8 拆表 A／B；V-19 → §6.1 欄位、§7.4 詞彙；V-20 → SEM-4 改判換段時刻與容差、`lyric-line` 移出現有值；V-21 → SEM-1、`TransitionContract`、TV-14；V-22 → §7.1 示意改寫並當反對照；V-26 → §6.2 改邊；V-27 → §6.6 兩張新狀態表、§6.7 跨界失敗序列；V-29 → `Revise` 讀兩版 `resolved`、`texts.claim`、TG-3 限制、SEM-9 換算；V-30 → `Clip.speed`、`Component.license`／`requires`、`Asset.portrays`、D-T16；V-32 → §8.1 補列、§8.3；V-35 → D-T8 替代方案、§13 `MusicCue` 不凍結。

### 14.3 驗證報告 v2 的發現 → v3 處理

| 發現 | 處理 |
|---|---|
| W-1 轉場重疊兩種讀法 | SEM-1／SEM-2／SEM-4 重寫；`overlap` 欄位刪除；§7.1 示意與 §8.1 兩組對照離邊界 ≥ 4.5 格 |
| W-2 版本不含片段程式 | `VersionFingerprint`（`approval.json`）、TV-16、TL-INV-12、`Revise` 讀 `parent` |
| W-3 停頓數值 | §6.3 八組實測表、D-T10 改稱選定值 |
| W-4 檢查階段矛盾 | §6.2 以 §7.3 為準；TV-11 只在 `compile`；TV-15 進 `validate --static`；TV-9 拆 a／b |
| W-5 孤兒 | BR-14 加「展示不能拖」、TV-17、SEM-12 補句、§14.1 補列、只記錄的欄位明寫 |
| W-6 小節錨點 | 使用者確認 D-T17 |
| W-7 片尾空檔 | 使用者裁決 D-T19；§6.3 步驟 5、SEM-2、§6.9 |
| W-8 `end_hold` | §7.5 與 TV-7 同一定義；改用 `segments.py`，限制寫明 |
| W-9 `build/` 擁有權 | §6.9 擁有者列、TL-INV-1 限 `compile` 產物、TG-16 |
| W-10 `--rules` 與混音後備 | §4、§6.9 指令與規則檔列 |
| W-11 音檔保存與快取重比 | `VoiceLock` 副本、`VoiceKey` 轉寫快取、§6.6 Line 表、TL-INV-11 |
| W-12 覆寫身分 | §5.1、§5.2、表 A A4、D-T21 |
| W-13 版本狀態機 | §6.4 `REVIEWED` 改義、補充的格、TV-18 |
| W-14 元件證據 | `card_tier`、`measured` 需非空 `intents`、`outside` 退級 |
| W-15 示意 | §7.1 改轉場元件 id、加 E1、`overlay` |
| W-16 里程碑相依 | §9 TL-0 改用夾具、TL-1 收 `compile` 相關對照、TL-2／3／5 依賴 |
| W-17 舊參照 | §0.4 元件 8 個、§2.3／§3.3／§5.2 改指 §6.8、§0.4 鎖指 TG-18；`docs/production-order.md` 末節「名稱不改」改指對照表 |
| W-18 檢查覆蓋 | §8.1 補 BR-11／15／16、SEM-3／9／10／13、TL-INV-4／6／7／9、表 A A3／A4 |
| W-19 邊角 | SEM-4 限有句且非第一段；表 A 順序；`ground` 條件必填；TV-9b 在 timed；TV-1 管欄位存在 |
| W-20 `layout`／`camera` | BR-4 補句、§6.1 欄位說明、TG-3 |
| W-21 常駐層 | 使用者裁決 D-T20；`OverlayClip`、SEM-13 |

### 14.4 驗證報告 v3 的發現 → v4 處理

| 發現 | 處理 |
|---|---|
| X-1 對照與 SEM-4 不一致 | §8.1 節奏列改為「第一個畫面片段、沒有句子的 feature 片段」 |
| X-2 轉場 family-only 與 BR-2 | `transition_in` 只能寫元件或 `"cut"`；§6.8「轉場元件」段；D-T14 補註；§8.1 轉場元件列 |
| X-3 片中空檔 | 使用者裁決 D-T22；SEM-2、TV-19、§8.1 片中空檔列；`ground` 不再條件必填 |
| X-4 里程碑 | TL-0 片尾停留看 `resolve` 輸出；TL-1 加 `voice --import`、只有旁白的 Mix、無聲音軌時省略 `--audio`；RG1 移回 TL-0；TV-8 進 TL-0（D-T25） |
| X-5 旗標分階段 | §6.9 分階段列 |
| X-6 D-T19 收尾 | 自動宣告靜音、片尾「旁白靜音」（v4.2 依 Z-2 撤回）、`end_hold` 改義與 `tail` 3.0（D-T23；v4.3 依 W30 改為 2.0） |
| X-7 儀器限制 | §7.5 `cut_on_line` 配對規則與 `narrlock`／`segments` 限制、`claims_traceable` 的 Canvas 限制、TG-19 |
| X-8 倍速表 | `speed.asset`、`Asset.duration_s`、TV-17 自 0 起連續 |
| X-9 TV-8／TV-9 | TV-8 只查例外理由；TV-9 以 `validate`／`approve` 分嚴重度 |
| X-10 消費者 | TV-4 查 `requires`；BR-3 末句給常駐層祖先 |
| X-11 版本指紋 | 副本進版本、runtime 入指紋、規則檔不入（D-T24） |
| X-12 filmkit 擁有檔 | §6.9 補 `sheet_1fps.png`、`.filmkit/`；全部核對後才寫第一個檔 |
| X-13 草稿補值 | SEM-10、D-T8 註：`at`／`dur`／`motion_intent` 不補 |
| X-14 轉場邊角 | `t0_next ≥ t0 + tdur`；`tdur` 改名 |
| X-15 表 A 與覆蓋 | A3 往 A4–A6；§8.1 補 A2、TL-INV-8；TV-19 擁有 `fixed` 超長 |
| X-16 狀態機 | §6.5 `watched`／`measured` 兩旗標＋衍生等級；Line 補 `synthesized → failed(env)`、`imported`、`asr` 預設 |
| X-17 結尾卡 | 使用者裁決：重述主句的結尾卡算標語型（D-T15 補） |
| X-18 小項 | D-T10 措辭、D-T9 補 TV-15／17、v2 變更說明的「7」註明、`override.source` 值域 |

### 14.5 驗證報告 v4 的發現 → v4.1 處理

| 發現 | 處理 |
|---|---|
| Y-1 `Clip` 欄位表殘留 family-only | 刪除，改為「元件或 `"cut"`」 |
| Y-2 延長與錨點 | §6.3 步驟 7：延長在最後做，錨點讀延長前的值 |
| Y-3 `density.py` 取不到最後一段 | §7.5 `end_hold`：TL-3 先擴充 `density.py` 輸出靜止段清單（含正反對照），擴充前 `undetermined`；限制改為「偏長」；`Intent` 儀器列表補 `density` |
| Y-4 runtime 雜湊與重新編譯 | §3.1 版本列：runtime／素材改動後擋，`compile --rebase` 開新版本 |
| Y-5 `guided` 轉場的檢查與「必須填好」矛盾 | TV-3 含轉場元件、TV-15 查轉場候選；「到 `approve` 還空著＝硬切並列出」 |
| Y-6 D-T22 措辭、`from`、常駐層 | D-T22 改為「任何空檔」、`from` 停在延長後最後一格；SEM-13 與 §6.3 步驟 7：常駐層不延長（SEM-2、§8.1 片中空檔列與 v4 變更說明的同義句當時漏改，v4.4 補，Z-3） |
| Y-7 轉場窗相疊無 TV、TV-7 措辭 | TV-2 擁有 `t0_next ≥ t0 + tdur`；TV-7 改「最後片段結束到片尾」 |
| Y-8 里程碑殘留 | §8.1 片尾停留標 filmkit M2；`voice --import` 形狀；TL-0 的 TV-6／9b 無法判定、TL-0 核可不出片；句間靜音也自動宣告 |
| Y-9 舊文字 | §6.2 Approve 補副本；`meta`、§6.3、D-T19 改「旁白靜音」（此項已由 §14.6 Z-2 撤回）；BR-11 補 `tl.py at`；v3 變更說明註明 v4 再改 |

### 14.6 驗證報告 v4.1 的發現 → v4.2 處理

報告：`docs/verification_timeline-layer-design-v4.1_2026-10-09.md`，PASS-WITH-FIXES，0 BLOCK。

| 發現 | 處理 |
|---|---|
| Z-2 D-T19 措辭被改（使用者裁決列） | 使用者 2026-10-09 裁決還原「聲音全部靜音」：`meta`、§6.3 步驟 5、§6.9 自動靜音列、D-T19 同步改回；片尾一定寫 `silences` |
| Z-1、Z-3..Z-9 | should-fix，留到本層 PSM 追溯表逐項關閉；Z-1（`timeline_lib` 改 arm 層 opt-in、沿用 `mount_skills` 式掛載、`run.json` 頂層鍵）以合併 r22 之後的 `run_arm.py` 為基底 |

### 14.7 v4.4：PSM 定案的文字寫回

PSM：`docs/timeline-layer-psm.md` v1（2026-10-10）。逐項關閉在 PSM §14.3；這裡只列設計裡改了哪幾句，讓設計與 PSM 不互相矛盾。

| 發現 | 設計裡改的地方 |
|---|---|
| Z-1 | BR-10、RG5、§4 `run_arm.py` 列、TL-INV-10：arm 層 `timeline_lib` |
| Z-3 | v4 變更說明「任何空檔」、SEM-2 與 §8.1 片中空檔列：`from` 畫前一段延長後的最後一格 |
| Z-4 | §6.3 步驟 7：TV-4／TV-6 用延長前的作者值；§8.1 補「錨點讀延長前的值」一對 |
| Z-5 | RG11；§9 TL-3 依賴 |
| Z-6 | §3.1 版本列：`compile --rebase` 只開草稿，版本仍由 `approve` 寫 |
| Z-7 | SEM-1 缺省＝`"cut"`；轉場候選檔名與 `approve` 第一行的擁有者在 PSM §4.11、§5.2 |
| Z-8 | §9 TL-0 列（核可的夾具、`undetermined`、`compile` 拒絕）、TL-1 列（TV-12） |
| PSM v1 驗證 P-2、P-8 | TV-4 拆 static／timed 兩段；§6.9 旗標分階段改為「filmkit 已建成，一律帶旗標」；D-T12 的 Haiku 子句加註待確認 |
| 使用者 2026-10-11（PSM §0 第 4 題，U-2；v4.5） | D-T12：元件固定內容撰寫不派 Haiku；Haiku 只用於蒐集、盤點這類有硬驗收閘的機械任務，與全域派工規則一致 |
| Z-9 | `Component.requires`（`approve` 複製）、v3 變更說明結尾數值、§14.5 Y-6 列；`imported` 句的 `VoiceLock` 欄位在 PSM §8.1.3 |

## review-when

- filmkit 設計改版（`film_plan.json` 欄位、頁面契約、`--plan`／`--rules` 語意、規則檔位置或 schema、`render.json` 的歸屬判斷任一改變）→ 重核 §6.9、SEM-9、D-T18、D-T19。
- 任一技巧卡的等級措辭改變 → 對應元件的 `card_tier` 重抄（卡沒有機器可讀等級欄位）。
- lab 儀器的命令列或輸出格式改變（`segments`、`narrlock`、`measure_product`、`bgswitch`、`fidelity`）→ 重核 §7.5 與 `Intent`。
- 貼文工作流的「全域能力」設計回合開始（PROJECTS a post-format project 列的 NEXT DESIGN ROUND）→ 重核 §3.1 升級條件與 §11。
- lab 任一技巧卡的參數區或等級改變 → 對應元件的參數與等級同步（BR-7）。
- W24 結案 → TL-4 的歌詞錨點；W28 開始 → §11。
- §2.4 的四點差異化任一不再成立（例如 lab 停止研究）→ 評估改用外部框架。
- 本機 Python／Node／ffmpeg／Chromium 大版本升級 → §2.5、§10 全部重跑。

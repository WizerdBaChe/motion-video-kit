# 分鏡畫面分層：關鍵畫面、中間姿態、過渡（設計筆記）

狀態：2026-10-19 起由 `docs/agent-review-kbt-design.md` 接手；本文 §4 的待決事項在該設計裡定案（過渡改由接縫自動推導，style frame 審查改為 G1 靜止硬項目＋G2 片段窗）。原狀態：**構想筆記，未施工**（使用者 2026-10-11）。等 `docs/timeline-layer-psm.md` 與 TL 建置跑完，再用 product-design-thinking 的增能模式 (Mode B) 把這份併進 timeline 設計；在那之前不改 `film.timeline.json` 的欄位、不改 skill 步驟 4。

證據等級：本文的外部概念是**主張 (claim)**（教科書與業界流程說法，見文末來源），lab 尚未量測或 A/B；對到 lab 現有卡片的部分照各卡自己的等級。

## 1. 為什麼要分

現在分鏡的最小單位是「段」（timeline 的片段 Clip）：每段寫 headline、visual、layout、轉場進出、運鏡目標、motion intent。一段裡「哪一刻要停下來被讀」「哪幾格只是在走路」沒有分開寫，結果：

- 讀字時間 (TV-6)、產品忠實 (T05)、構圖這類檢查，只該套在「要被看清楚的那一刻」，卻沒有那一刻可以指。
- 轉場技法卡（T10、T12、T13、T15）跟段內動態卡（T02、T09、T14）用的是不同資源、不同檢查，現在混在同一欄「transition in/out ＋ motion intent」。

## 2. 三個領域的現成概念

| 領域 | 概念 | 對我們的意思 |
|---|---|---|
| 手繪動畫（Williams《The Animator's Survival Kit》章節：Keys、Extremes and Breakdowns、Timing and Spacing） | **key**（說故事的姿態）→ **extreme**（動作端點、轉向點）→ **breakdown**（決定兩個 key 之間走哪條路：弧線、過衝）→ **in-between**（補格，決定順不順、快慢）。pose-to-pose：先定 key，再補中間。key 由主動畫師畫，補格交給助手——**分工與資源本來就不同**。timing／spacing chart 記補格怎麼分布。 | 程式動畫裡 in-between 是插值自動算的；人（或模型）真正要決定的是 **key 與 breakdown**，加上緩動曲線（＝spacing chart）。 |
| 動態設計 (motion design) 流程 | brief → storyboard（說什麼、順序）→ **style frames**（每個主場景一張全彩定稿畫面，定外觀）→ animatic（配聲音看時間）→ 動畫。 | 關鍵畫面要「先做成一張靜態定稿」再動；過渡在 animatic 階段才看得出太長、太突兀。外部資料沒有把 "transition frame" 當成獨立交付物，它被歸在 animatic／動畫階段——**這是我們要自己補的一層**。 |
| 電影拍攝與剪接 | storyboard 只畫關鍵鏡頭的構圖（what／why），shot list 列全部鏡頭與運鏡（how／when）；轉場分**剪接方式**（硬切、match cut、溶接、J／L cut）與**橋接鏡頭**（establishing、cutaway、insert）。 | 「過渡」有兩種：只發生在接縫的剪接手法，和自己佔時間的橋接畫面。兩者的資源與檢查不同。 |

## 3. 換到程式渲染影片：三種畫面角色（草案）

| 角色 | 定義 | 主要檢查 | 對到的 lab 卡／規則 | 資源 |
|---|---|---|---|---|
| **K 關鍵畫面** (key frame / style frame) | 一段裡要被**看清楚、讀完**的那一刻（版面到位、字可讀、產品畫面正確）；可以停（hold）。 | 讀字時間 TV-6、標語型 `hold_range`、產品忠實、構圖；每個 K 先出一張靜態截圖給人過目（＝style frame） | T05 產品忠實、T17 引用卡、T04 骨架的每一拍；axes-and-pairing「同時出現的項目數」 | 文案、產品截圖／素材、版面；**這是素材清單的主要來源** |
| **B 中間姿態** (breakdown) | 兩個 K 之間、**同一段內**決定動作怎麼走的那一刻：進場順序、過衝、弧線、運鏡的中途點。補格交給插值。 | motion intent 一行（whole-film-rules §2a）、緩動／彈簧參數、錯時間隔 | T02 彈簧、T14 分層錯時、T09 運鏡、T06 旁白下的連續動態 | 元件參數（`Component.params`），不需要新素材 |
| **T 過渡** (transition) | **段與段之間**的接縫。分兩型：**T-cut** 只在接縫發生（硬切、模糊橋接、換色）；**T-bridge** 自己佔時間、有內容（形狀接形狀、母題回調、品牌收束的那一張圖）。 | 換段時刻對齊（cut_on_line／cut_on_bar）、轉場窗長度、**不蓋住前一段最後一拍**（whole-film-rules §3）、色彩不換地 | T10 形狀接形狀、T12 模糊橋接、T13 換窗換光換色、T15 母題回調、T08 換段對句、T01 對拍 | 轉場元件；T-bridge 另需它自己的素材（例：要收束成品牌名的那些店） |

補充：

- **Hold（停格）不是第四種角色**，是 K 的屬性（停多久）。timeline 已有 `declares.holds` 與片尾停留，K 的停留可以直接接上。
- 「一段至少一個 K」可以當結構規則：沒有 K 的段，表示這段沒有要讓人看清楚的東西，應該合併或刪掉——呼應 §2a「沒有理由就不動」。
- K 要先成立（靜態定稿），B、T 才排；這是 pose-to-pose 的順序，也跟動態設計「style frame 先於動畫」一致。

## 4. 之後併進 timeline 時要決定的事（增能模式時處理）

1. 欄位形狀：Clip 內加 `keys[]`（`at`、`role: key|breakdown`、`hold`、`what`），過渡從 Clip 的 transition in/out 升成自己的物件，還是維持在 Clip 上只加 `kind: cut|bridge`。
2. 檢查掛載：TV-6、產品忠實改成只量 K 的時刻；轉場檢查只量 T 的窗。
3. style frame 審查點：approve 前是否強制每個 K 出一張截圖頁（filmkit 縮圖表能否直接沿用）。
4. 技法卡要不要加一個機器可讀欄位 `role: K|B|T`（timeline `Component.family` 詞彙表 §7.4 是否已足夠）。
5. 案例分析回頭補：原片鏡頭表（shot-record）是否也標 K／B／T，讓「參考片的 K 間距」變成可量的節奏指標。

## 來源

- Williams, *The Animator's Survival Kit*（章節目錄：Keys、Extremes and Breakdowns、Timing and Spacing）— https://dn721807.ca.archive.org/0/items/taskav-01/The__Animator%27s_Survival_Kit%5B1%5D_text.pdf
- Foundry Modo, Spacing Chart — https://learn.foundry.com/modo/content/help/pages/animation/tools/spacing_chart.html
- BMCC 2D 動畫課程頁（key／breakdown／in-between）— https://openlab.bmcc.cuny.edu/ani-260-1300-intro-2d-animation-sp-2021/?p=86
- Boords, What are Style Frames — https://boords.com/blog/what-are-style-frames-definition-and-examples
- Pixune, Animatics in the animation pipeline — https://pixune.com/?p=37210
- Coverage, storyboard and shot list — https://capture.emagined.com.au/pre-production/coverage-storyboard-and-shot-list
- match cut、J／L cut、cutaway、insert 的定義來自一般知識，搜尋未取得專文；併入設計前要補查。

---
layer: reference
audience: user
date: 2026-10-17
---

# 文字動態詞彙對照：80 招 × 業界通稱 × 既有技法卡

來源：C43（日文「文字演出40選」，編號 J01–J40）、C44（中文「文字動態 40 招」，編號 Z01–Z40）。業界通稱的查證紀錄（每列網址、吻合度、是 fetched 還是只有搜尋摘要）在 [research/aka-terms-text-motion-2026-10-17.md](research/aka-terms-text-motion-2026-10-17.md)；接續 2026-10-13 的 [aka-terms-2026-10-13.md](research/aka-terms-2026-10-13.md)（W41）。

吻合度沿用 W41 的四級：exact（同一件事）／broader（業界詞較寬）／narrower（業界詞較窄）／adjacent（相關但不同，只當搜尋詞）。〔未查到〕＝搜過，沒有任何頁面用這個名稱指這個效果——這時提示詞要用**描述**，不要用名稱。

## 一、總稱

- **kinetic typography（キネティックタイポグラフィ）**〔broader〕：整類的通稱。Wikipedia 底下再分 motion typography（含 scrolling typography、dynamic layout）與 fluid typography。
- **text animation presets / text animation pack**〔exact〕：C43、C44 這種「一招一格的樣品目錄」在素材市集（Envato 等）的叫法。
- **テキストアニメーション**〔broader〕：日文常用說法；「文字演出」「動態文字」當類別名沒查到來源。
- 做法層的術語（不是效果名）：After Effects 的 **Text Animator＋Range Selector**（日：アニメーター／範囲セレクター），網頁端的 **GSAP SplitText**。大多數逐字效果都是「拆字＋錯開時間」再套一種變形。

## 二、15 族對照

| 族 | 業界通稱（吻合度） | C43（日） | C44（中） | 相關的既有技法卡 |
|---|---|---|---|---|
| F1 逐字錯開／波浪 | staggered animation（broader）；wavy text effect（exact，J09）；bouncy text（exact，J18） | J09 Wave Letters、J18 Letter Bounce、J14 Domino〔未查到〕、J26 Swing〔未查到〕、J40 Float Drift（Wiggly selector，adjacent） | Z02 逐字敲擊 | **T14** stagger〔exact〕 |
| F2 放大衝擊 | zoom punch（exact，但來源是鏡頭推近、低權威）；overshoot（adjacent） | J06 Heartbeat Zoom〔未查到〕、J08 Number Slam〔未查到〕 | Z01 文字爆開〔未查到〕、Z03 印章〔未查到〕、Z04 衝擊放大 | **T09** push in（Z04 其實是字在推近）；**T02** 彈簧（overshoot） |
| F3 擠壓伸展 | **squash and stretch**（exact，School of Motion 用在文字字元） | J35 Elastic Wave Stretch、J34 Jitter Settle（overshoot／follow-through，adjacent） | Z06 伸縮字、Z08 擠壓彈跳 | **T02** spring／damped spring |
| F4 破壞消失 | **disintegration effect**（exact，J05）；Shatter（narrower，AE 特定效果） | J04 Explode Out、J05 Disintegrate、J39 Crumble Down、J27 Pixel Dissolve〔未查到〕、J02 Laser Cut〔未查到〕 | Z32 上下裂開〔未查到〕 | — |
| F5 換字循環 | **ScrambleText**（exact，J13）；**split-flap display**（exact，Z25，指實體翻牌板）；**odometer effect**（exact）；**slot text**（exact）；**flip text**（exact）；**animated headlines / rotating words**（exact，Z30） | J13 Scramble Decode、J03 Coin Flip〔未查到〕、J32 Shuffle Letters〔未查到〕、J38 Text Mosaic〔未查到〕 | Z25 翻牌、Z26 翻卡、Z28 拉霸、Z29 計數器、Z30 標題切換 | — |
| F6 寫出／填滿 | **typewriter effect／打字機效果**（exact）；**karaoke text**（narrower：只有色塊 wipe，不含跳球）；**highlight / marker sweep**（exact）；**liquid fill text**（exact）；**variable font animation**（exact，J23） | J25 Karaoke Ball、J23 Weight Grow、J36 Ink Bleed〔未查到〕、J15 Gradient Flow〔未查到〕 | Z27 打字機、Z37 液體填滿、Z38 螢光筆 | **T06** write-on reveal；**T16** lyric video（karaoke） |
| F7 帶狀捲動 | **marquee／infinite marquee**（exact）；跑馬燈（exact）；scrolling typography（broader）；parallax grid（adjacent） | — | Z09 巨字滑過、Z10 直書逆走 Vertical Typography（版式叫 tategaki／縦書き，adjacent；逆向捲動的動作〔未查到〕）、Z11 重複波浪、Z12 斜線帶、Z13 緞帶、Z14 跑馬燈、Z15 直書三層、Z16 封鎖膠帶〔未查到〕 | **continuity `persistent-anchor`**（跑馬燈常當常駐元素） |
| F8 路徑／圓環 | **text on a path**（exact，AE Path Options）；kaleidoscope（exact，CC Kaleida，但來源用在圖不是字） | J16 Circle Text、J07 Text Kaleido、J28 Rotating Words（**撞名**，見下）、J33 Spiral／J31 Roller Path／J24 Fan〔未查到〕 | Z22 軌道〔未查到〕 | — |
| F9 3D 文字空間 | **text cylinder**（exact）；**extrude text**（exact）；**zoom-through / fly-through text**（exact，Z07）；隧道只有 3D text tube（adjacent） | — | Z07 穿越放大、Z17 文字隧道、Z18 走廊、Z19 圓柱、Z20 漩渦、Z21 圓環隧道、Z23 方塊〔未查到〕、Z24 立體字 | **T09** 運鏡（Z07 等於字當遮罩的推軌） |
| F10 物理／變形 | Wave Warp（narrower，整層變形）；magnet text（exact，但業界版是游標驅動） | J19 Text Flag、J21 Magnet Pull、J17 水面／J12 放大鏡／J20 重力反轉／J22 Pulse Grid／J30 市松〔未查到〕、J11 Letter Rain（Matrix digital rain，exact，摘要層級） | — | — |
| F11 故障與光 | **glitch text／故障文字／グリッチ**（exact）；**dot matrix / LED**（exact） | J01 Lightning Strike〔未查到〕 | Z31 LED 看板、Z34 故障切片 | **T19**（反例：每個重音都閃白／RGB split）；**T13** dip to white |
| F12 字形外觀 | **outline／stroke text + Trim Paths**（exact）；**text mask／track matte**（exact）；**long shadow**（exact） | J37 Letter Assemble〔未查到〕 | Z33 空心字、Z35 圖案遮罩、Z36 長陰影、Z39 雙色反轉〔未查到〕 | **T03** 黑白對調（Z39 是斜切一刀兩邊對調，T03 是經灰階內插） |
| F13 殘影與格率 | **Echo effect**（exact）；trail（adjacent）；**stop-motion style／Posterize Time／animating on twos**（exact） | J29 Blur Trail、J10 Stop Motion | Z40 殘影 | **T12** whip pan／動態模糊 |
| F14 排版堆疊 | **dynamic layout**（narrower，kinetic typography 的子類） | — | Z05 動態堆疊 | **T14** stagger（逐行進場） |
| F15 整份目錄 | kinetic typography（broader）；text animation presets pack（exact） | 全 40 | 全 40 | T16（kinetic typography 已列為相關搜尋詞） |

兩份目錄的偏重不同：C43 集中在 F1、F4、F10（字元級的物理與破壞），C44 集中在 F5、F7、F9、F12（版面、換字、3D 空間、外觀）。同一招兩邊都有的很少（F1、F3 有交集）。

## 三、撞名（同一個名稱，業界意思不一樣）

| 名稱 | 目錄裡的意思 | 業界意思 |
|---|---|---|
| Rotating Words（J28） | 字沿圓環轉、換字 | 一個字原地翻轉換成另一個字（＝Z30 標題切換） |
| Marquee／跑馬燈（Z14） | 一條持續橫跑的字帶 | HTML `<marquee>` 已淘汰的元素；中文跑馬燈另指元宵走馬燈 |
| Split Flap（Z25） | 模擬翻牌 | 指實體的 Solari／Pragotron 翻牌顯示器，不是特效名 |
| Karaoke Ball（J25） | 跳球＋變色 | karaoke text 只有變色 wipe，跳球是另一個標記 |
| Wave Warp（J19 vs J09） | J09 是逐字波浪 | AE 的 Wave Warp 是整層變形，對應 J19 旗子，不是 J09 |
| Shatter（J04／J39） | 爆散、崩落 | AE Shatter 是特定的碎片效果；粒子消散叫 disintegration（J05） |
| Punch Zoom（Z04） | 字猛然放大 | zoom punch 的來源指鏡頭推近，不是字 |
| Slot Text（Z28） | 拉霸 | 業界 slot text 是逐字滾動替換，和 odometer 幾乎同一件事 |
| Kinetic Stack（Z05） | 一行行飛入堆疊 | kinetic typography 是整類總稱；這招在 Wikipedia 分類裡屬 dynamic layout |

## 四、既有技法卡的業界通稱（2026-10-13 已寫進卡片，這裡只列摘要）

| 卡 | 業界通稱（吻合度） | 這次的關聯 |
|---|---|---|
| T01 拍點對齊 | edit to the beat（broader）；anticipation（adjacent） | — |
| T02 彈簧動態 | spring animation／damped spring（exact） | F2、F3 的 overshoot、squash and stretch |
| T03 黑白對調 | 無；invert transition（adjacent） | F12 Z39 雙色反轉（不同做法） |
| T04 產品介紹骨架 | product explainer／demo（broader） | — |
| T05 產品忠實度／加購問業主 | 無 | — |
| T06 旁白連續動態 | whiteboard animation／write-on（narrower） | F6 打字機、F12 描邊 Trim Paths |
| T07 資料驅動展示片 | 無；animated data visualization（adjacent） | F5 odometer（數字滾動） |
| T08 換段落在句子上 | 無；J-cut／L-cut（adjacent） | — |
| T09 運鏡 | push in／pull out、whip pan、Ken Burns（narrower） | F2 Z04、F9 Z07 |
| T10 形狀接形狀 | match cut／graphic match（broader） | — |
| T11 導覽角色 | animated pedagogical agent（narrower） | — |
| T12 模糊橋接轉場 | rack focus／whip pan transition（narrower） | F13 Blur Trail |
| T13 窗型、光、色彩轉換 | aspect-ratio switch、dip to white（narrower） | F11 Lightning Strike |
| T14 錯開進場 | stagger／cascade（exact） | F1、F14 |
| T15 母題與回呼 | visual motif、callback（exact） | — |
| T16 靜止畫上的歌詞字 | lyric video（broader）；kinetic typography（adjacent） | F15 總稱、F6 karaoke |
| T17 引用卡 | 無；lower third（adjacent） | — |
| T18 問題鉤→解法接力 | Problem-Agitate-Solution（broader） | — |
| T19 每個重音都閃白（反例） | flash transition、RGB split glitch（broader） | F11 glitch text |

## 五、怎麼用在提示詞

- 有 exact 通稱的招：寫**通稱＋一句描述**（例：「split-flap display：每個字元像車站翻牌一格一格翻到定位」）。只寫名稱有撞名風險（見第三節）。
- 〔未查到〕的招：只寫描述，不要寫目錄裡的英文名——那些名稱是目錄作者取的，模型不見得認得同一件事。
- C44 貼文主張「把名字寫進提示詞，模型就會做出那一招」：**這裡沒測過**。要驗證得跑一輪模仿實測（同一個提示詞、有名稱 vs 只有描述，各 ≥3 次）。
  - 2026-10-18 r28 初篩（6 招、每種寫法 3 次、模型盲讀）：只寫描述 6／6 滿分；有 exact 通稱的 4 招只寫名稱也 12／12；**撞名的 2 招只寫名稱 0／6**，三組都做成業界的意思（Rotating Words 變成原地翻滾換字、Shatter 變成玻璃碎片）。名稱＋描述沒有比只寫描述更好（天花板）。所以撞名的招一定要附描述。[r28 報告](../experiments/r28-w43-textname/REPORT.md)

## 六、還沒做

- 19 列〔未查到〕沒有逐頁補查；68 列有來源的裡面，只有 15 列實際打開頁面確認，其餘是搜尋摘要層級。
- C44 的英文原名是從單幀讀的，格內小字，讀錯的風險在 Z10 以外的格也存在（已用放大圖確認 Z10＝Vertical Typography）。
- 沒有任何一招做成技法卡或量過時序；兩個案例都停在 `analysed`。

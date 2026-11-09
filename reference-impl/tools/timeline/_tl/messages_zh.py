"""Traditional Chinese message templates for timeline.html, keyed by a row's message_key (PSM 3.1, 7).

Templates take str.format fields from the row's `fmt` mapping. No judgement words (TL-INV-8).
"""
from __future__ import annotations

MESSAGES = {
    # TV-1 (schema, grammar, anchors)
    "tv1.schema": "時間軸檔格式不符：{detail}",
    "tv1.missing_at": "片段 {clip} 缺少起點 at（工具不替你補）",
    "tv1.missing_dur": "片段 {clip} 缺少長度 dur（工具不替你補）",
    "tv1.missing_motion_intent": "片段 {clip} 缺少 motion_intent 欄位（可以是空陣列，但欄位要在）",
    "tv1.cycle": "錨點互相等待，形成循環：{detail}",
    "tv1.anchor_target": "錨點指向不存在的對象：{detail}",
    "tv1.film_end_fit": "fit 片長下不能引用 film.end（片長由內容決定）",
    "tv1.tl4": "{detail}（TL-4 才支援）",
    "tv1.sem3": "片段 {clip} 的 dur 涵蓋的句子不屬於它：{detail}",
    "tv1.narration_order": "旁白句沒有依片段順序分組：{detail}",
    "tv1.asset": "素材問題：{detail}",
    "tv1.film_type": "片型 {detail} 不在規則檔的片型清單裡",
    "tv1.whole_frames": "固定片長 {detail} 秒不是整數格",
    "tv1.tdur": "片段 {clip} 的轉場比片段本身長：{detail}",
    "tv1.film_id": "film_id 與資料夾名稱不同：{detail}",
    "tv1.lines_json": "voice/lines.json 問題：{detail}",
    # TV-2
    "tv2.order": "片段 {clip} 解析後的順序與檔案中的順序不同",
    "tv2.nonpositive": "片段 {clip} 解析後長度不大於 0",
    "tv2.one_frame": "片段 {clip} 的轉場短於一格",
    "tv2.tdur": "片段 {clip} 的轉場比片段本身長",
    "tv2.sem4": "片段 {clip} 的換段時刻離第一句句首 {detail} 秒，超出 ±0.15 秒",
    "tv2.sem2": "前一段在 {clip} 的轉場窗結束之後才結束：{detail}",
    "tv2.sem1": "片段 {clip} 的轉場窗在前一段的轉場窗結束前就開始：{detail}",
    "tv2.sem13": "常駐層 {clip} 與同一層的另一段重疊：{detail}",
    "tv2.declares": "片段 {clip} 宣告的區間超出片段長度：{detail}",
    "tv2.keys": "片段 {clip} 的關鍵畫面 {detail} 落在片段長度之外",
    "tv20.no_key": "片段 {clip} 沒有標關鍵畫面 K（keys 裡 role: key）；沒有要讓人看清楚的那一刻，就合併或刪掉這段（暫定）",
    "tv2.music_bar": "music-bar 與旁白不能同時當主節奏",
    # TV-3
    "tv3.not_found": "片段 {clip} 指定的元件不存在：{detail}",
    "tv3.draft": "片段 {clip} 指定的元件還不能選用（draft）：{detail}",
    "tv3.decide_first": "片段 {clip} 的元件只適用特定的 {detail}，請先決定這項整片決策",
    "tv3.incompatible": "片段 {clip} 的元件與整片決策不相容：{detail}",
    "tv3.pending": "片段 {clip} 用了覆寫，待你確認：{detail}",
    "tv3.open_transition": "片段 {clip} 的轉場還空著；核可時會當成硬切",
    # TV-4a / TV-4b
    "tv4.param": "片段 {clip} 的元件參數不合：{detail}",
    "tv4.requires": "片段 {clip} 的元件缺少相依元件：{detail}",
    "tv4.clip_dur": "片段 {clip} 的長度 {detail}",
    # TV-5
    "tv5.empty": "片段 {clip} 沒有寫動作意圖",
    "tv5.stock": "片段 {clip} 用了老梗手法，必須寫動作意圖",
    "tv5.undetermined": "規則檔沒有老梗手法清單，老梗部分無法判定",
    # TV-6, TV-9b (TL-1)
    "tv6.undetermined": "讀字時間要執行片段程式才能量（TL-1 起）",
    "tv9b.undetermined": "片段畫面文字的出處要執行片段程式才能查（TL-1 起）",
    # TV-7
    "tv7.range": "結尾停留 {detail} 秒，不在規則檔的範圍內",
    "tv7.undetermined": "規則檔沒有結尾停留範圍，無法判定",
    # TV-8
    "tv8.listed": "片段 {clip} 宣告了底色例外：{detail}",
    "tv8.no_why": "片段 {clip} 的底色例外沒有寫理由",
    # TV-9a
    "tv9a.no_claim": "{clip} 的文字含數字但沒有出處：{detail}",
    "tv9a.bad_claim": "{clip} 的出處指向沒有宣稱來源的素材：{detail}",
    "tv9a.not_in_source": "{clip} 的宣稱文字在出處檔裡找不到原句：{detail}",
    "tv9a.source_unreadable": "{clip} 的出處檔 {detail} 讀不到，無法核對原句",
    "tv9a.no_portrays":"產品片沒有任何素材宣告身分來源（portrays）",
    "tv20.no_table": "產品片沒有產品狀態表（product_state），功能鏡頭演的是哪個狀態無從核對",
    "tv20.no_shows_state": "{clip} 是功能鏡頭，但沒寫它演的是哪個產品狀態（shows_state）",
    "tv20.no_facts": "產品狀態 {clip} 沒有事實欄（facts）",
    "tv20.no_source": "產品狀態 {clip} 沒有出處（source）",
    "tv21.unknown_state": "{clip} 指到不存在的產品狀態 {detail}",
    "tv21.not_scalar": "產品狀態 {clip} 的事實 {detail} 不是單一值（字串、數字或是非）",
    "tv22.unplaced": "指定素材 {clip} 沒有被任何鏡頭用到，無法保證它會出現在畫面上",
    # TV-10
    "tv10.share": "自由（free）片段占全片 {detail}，超過門檻",
    "tv10.undetermined": "規則檔沒有 free 比例門檻，無法判定",
    # TV-14
    "tv14.cover": "片段 {clip} 的轉場蓋到前一句的尾巴：{detail}",
    # TV-15
    "tv15.outside": "片段 {clip} 的程式用了候選清單外的元件：{detail}",
    "tv15.transition_outside": "片段 {clip} 寫的轉場不在轉場候選清單內：{detail}",
    "tv15.literal": "片段 {clip} 的元件引用無法靜態判讀：{detail}",
    "tv15.conflict": "片段 {clip} 與另一段用的元件互相衝突：{detail}",
    # TV-17
    "tv17.table": "片段 {clip} 的倍速表：{detail}",
    "tv17.undetermined": "片段 {clip} 的倍速表長度無法判定：{detail}",
    # TV-19
    "tv19.overrun": "最後一段超出固定片長：{detail}",
    "tv19.line_tail": "旁白句 {clip} 延伸到片尾停留（片尾全部靜音）：{detail}",
    "tv19.overlay": "常駐層 {clip} 超出片長：{detail}",
    "tv19.extension": "{clip} 延長 {detail} 秒接上下一段",
    # A7
    "a7.empty": "片段 {clip} 這一類沒有合格元件；片段程式從零寫",
    # generic
    "undetermined.rules": "規則檔不在，無法判定",
    "undetermined.evaluator": "檢查本身出錯，無法判定：{detail}",
}


def zh(key: str, **fmt) -> str:
    t = MESSAGES.get(key)
    if t is None:
        return key
    try:
        return t.format(**{k: ("" if v is None else v) for k, v in fmt.items()})
    except (KeyError, IndexError):
        return t

"""build/timeline.html (PSM 6.11; design 5.1). Generated only, never hand-edited (TL-INV-9).

Self-contained: inline CSS, no external URL, no script needed to read it, no font download. Deterministic:
the same inputs give the same bytes (no clock, no random).
"""
from __future__ import annotations

from html import escape

from . import model as M
from .common import NOT_JUDGED_ZH

SOURCE_ZH = {"user": "你說的", "model": "模型定的", "default": "預設"}
FREEDOM_ZH = {"locked": "固定 locked", "guided": "引導 guided", "free": "自由 free"}
ROLE_ZH = {"opening": "開場", "feature": "功能段", "chapter-card": "章節卡", "end-card": "結尾卡", "interlude": "過場",
           "overlay": "常駐層"}
DECISION_ZH = {"film_type": "片型", "audience": "受眾", "energy": "能量", "rhythm_source": "節奏來源",
               "remember_one": "記住一件事", "ground": "底色", "voice": "內容語氣", "presentation": "呈現形式",
               "purpose": "目的", "shown_where": "在哪裡播", "viewer_action": "看完要做什麼"}
BUCKET_ZH = {"blocking": "擋件", "look": "要你看", "info": "資訊", "undetermined": "無法判定"}
STATE_ZH = {"DRAFT": "草稿", "VALID": "檢查通過（待核可）", "APPROVED": "已核可", "ABANDONED": "已放棄"}

CSS = """
:root{--bg:#f7f4ee;--paper:#fffdf8;--ink:#1f1d1a;--muted:#6b645a;--line:#d9d1c4;--accent:#7c2128;
--pic:#e9dfcf;--pic-b:#b9a687;--ov:#dfe7ef;--ov-b:#8aa1b8;--nar:#e6efe2;--nar-b:#86a479;--block:#f6dcdc;
--block-b:#b0484f;--look:#fbefd2;--look-b:#c49a2c;--hatch:#c9b99c;--tail:#ece6dc}
@media (prefers-color-scheme: dark){:root{--bg:#1b1a18;--paper:#24221f;--ink:#ece6dc;--muted:#a59d90;
--line:#3d3933;--accent:#e08a8f;--pic:#3a3328;--pic-b:#8f7d5f;--ov:#2b3540;--ov-b:#6d8aa6;--nar:#2c3a28;
--nar-b:#7f9f72;--block:#4a2628;--block-b:#d0777d;--look:#45391c;--look-b:#c9a248;--hatch:#6d6250;--tail:#2e2b27}}
*{box-sizing:border-box}
html,body{margin:0;background:var(--bg);color:var(--ink)}
body{font-family:"Noto Serif TC","Source Han Serif TC","PMingLiU","Songti TC",Georgia,serif;font-size:15px;line-height:1.55}
main{padding:20px 24px 40px;width:100%}
h1{font-size:24px;margin:0 0 4px}
h2{font-size:18px;margin:28px 0 10px;border-bottom:1px solid var(--line);padding-bottom:4px}
.sub{color:var(--muted);margin:0}
.band{background:var(--paper);border:1px solid var(--line);border-radius:6px;padding:12px 16px;margin-top:14px}
.legend{font-size:13px;color:var(--muted)}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px}
.card{background:var(--paper);border:1px solid var(--line);border-radius:6px;padding:10px 12px}
.card .k{font-size:13px;color:var(--muted)}
.card .v{font-size:16px;margin:2px 0 4px;word-break:break-word}
.tag{display:inline-block;font-size:12px;border-radius:3px;padding:0 6px;border:1px solid var(--line)}
.tag.user{border-color:var(--nar-b)} .tag.model{border-color:var(--look-b)} .tag.default{border-color:var(--line)}
.tag.unset{border-color:var(--block-b);color:var(--block-b)}
.rows{width:100%;border-collapse:collapse;font-size:14px}
.rows td,.rows th{border-top:1px solid var(--line);padding:5px 8px;text-align:left;vertical-align:top}
.b-blocking{background:var(--block)} .b-look{background:var(--look)}
.axis,.lane{position:relative;width:100%}
.axis{height:22px;border-bottom:1px solid var(--line);font-size:12px;color:var(--muted)}
.tick{position:absolute;top:0;transform:translateX(-50%)}
.lanes{background:var(--paper);border:1px solid var(--line);border-radius:6px;padding:10px 14px 14px}
.lanehead{font-size:13px;color:var(--muted);margin:10px 0 3px}
.lane{height:46px;background:var(--bg);border-radius:3px}
.blk{position:absolute;top:3px;bottom:3px;border:1px solid var(--pic-b);background:var(--pic);border-radius:3px;
overflow:hidden;font-size:12px;padding:2px 4px;line-height:1.25;white-space:nowrap}
.blk.ov{background:var(--ov);border-color:var(--ov-b)}
.blk.ln{background:var(--nar);border-color:var(--nar-b)}
.blk.est{border-style:dashed}
.ext{position:absolute;top:3px;bottom:3px;background:repeating-linear-gradient(45deg,transparent 0 4px,var(--hatch) 4px 6px);
border:1px dashed var(--hatch)}
.win{position:absolute;top:0;bottom:0;border-left:2px solid var(--accent);border-right:2px solid var(--accent);
background:rgba(124,33,40,.12)}
.tailh{position:absolute;top:3px;bottom:3px;background:var(--tail);border:1px dotted var(--muted);font-size:12px;padding:2px 4px}
.pre{position:absolute;top:3px;bottom:3px;background:var(--tail);font-size:12px;padding:2px 4px}
.sfx{position:absolute;top:8px;width:10px;height:10px;margin-left:-5px;border-radius:50%;background:var(--accent)}
.clips{width:100%;border-collapse:collapse;font-size:14px}
.clips th{position:sticky;top:0;background:var(--paper)}
.clips td,.clips th{border-top:1px solid var(--line);padding:6px 8px;text-align:left;vertical-align:top}
.clips td.id{font-weight:bold;white-space:nowrap}
.mi{margin:0;padding-left:18px}
.fixed{font-size:13px}
.muted{color:var(--muted)}
.wrap{overflow-x:auto}
details summary{cursor:pointer;color:var(--muted)}
@media (max-width:760px){main{padding:12px 16px}.clips,.rows{font-size:13px}}
"""


def _e(x) -> str:
    return escape("" if x is None else str(x))


def _s(x: float) -> str:
    return f"{x:.2f}"


def _pct(t: float, end: float) -> str:
    return f"{(100.0 * t / end) if end else 0:.4f}%"


def _ticks(end: float) -> str:
    step = 1 if end <= 20 else 2 if end <= 40 else 5 if end <= 100 else 10
    out, t = [], 0
    while t <= end + 1e-9:
        out.append(f'<span class="tick" style="left:{_pct(t, end)}">{t:g}</span>')
        t += step
    return "".join(out)


def render_view(film, resolved: dict, validate: dict, state: dict, timeline: dict) -> str:
    end = resolved["film_end_s"]
    t = M.tracks(timeline)
    clips = {c["id"]: c for c in t["picture"] + t["overlay"]}
    rows_static = (validate.get("static") or {}).get("rows") or []
    rows_timed = (validate.get("timed") or {}).get("rows") or []
    rows = rows_static + rows_timed
    d = state.get("draft")
    if d:
        st = f"草稿 {d['n']}：{STATE_ZH.get(d['state'], d['state'])}"
    else:
        last = max(state.get("versions") or [{"n": "?", "state": "?"}], key=lambda v: v["n"] if isinstance(v["n"], int) else -1)
        st = f"版本 {last['n']}：{STATE_ZH.get(last['state'], last['state'])}（工作資料夾與它相同）"
    h = ['<!doctype html>', '<html lang="zh-Hant" data-page-class="dashboard">', '<head><meta charset="utf-8">',
         '<meta name="viewport" content="width=device-width, initial-scale=1">',
         f'<title>時間軸 {_e(resolved["film_id"])}</title>', f'<style>{CSS}</style></head><body><main>']
    h.append(f'<h1>時間軸：{_e(resolved["film_id"])}</h1>')
    h.append(f'<p class="sub">{_e(st)} ・ 片長 {_s(end)} 秒（{resolved["n_frames"]} 格，'
             f'{resolved["format"]["fps"]} fps，{_e(resolved["format"]["size"])}，'
             f'{"內容決定長度 fit" if resolved["format"]["duration_policy"] == "fit" else "固定長度 fixed"}）'
             f' ・ <strong>{NOT_JUDGED_ZH}</strong></p>')
    h.append('<p class="legend">讀法：S1、C1、E1 這類代號是時間軸檔裡每個畫面片段的名字（下方片段表逐一說明）；'
             'L1、L2 是旁白句；TV-n 是檢查項的編號，後面一律附中文說明。秒數都是影片時間。'
             '「擋件」必須改；「要你看」由你決定；「無法判定」是工具在這個階段量不到的項目。</p>')

    # approve-time list + rows band
    pend = validate.get("pending_confirmation") or []
    pic = resolved["picture"]
    hard = [p["id"] for p in pic[1:] if p["transition"]["kind"] == "cut"]
    opn = [p["id"] for p in pic[1:] if p["transition"]["kind"] == "open"]
    und = sorted({r["check"] for r in rows if r["bucket"] == "undetermined"})
    h.append('<div class="band"><strong>核可時會列出的事</strong><ul>')
    h.append(f'<li>待你確認的覆寫：{_e("、".join(f"{p["clip"]}（{p["component"]}）" for p in pend)) or "無"}</li>')
    h.append(f'<li>硬切（明寫 cut）：{_e("、".join(hard)) or "無"}</li>')
    h.append(f'<li>轉場還空著、核可時當成硬切：{_e("、".join(opn)) or "無"}</li>')
    h.append(f'<li>這個階段還沒檢查的項目：{_e("、".join(und)) or "無"}</li></ul></div>')
    flagged = [r for r in rows if r["bucket"] in ("blocking", "look")]
    h.append('<div class="band"><strong>擋件與要你看</strong>')
    if flagged:
        h.append('<div class="wrap"><table class="rows"><tr><th>類別</th><th>片段／位置</th><th>說明</th><th>檢查項</th></tr>')
        for r in flagged:
            h.append(f'<tr class="b-{r["bucket"]}"><td>{BUCKET_ZH[r["bucket"]]}</td><td>{_e(r["where"])}</td>'
                     f'<td>{_e(r.get("message") or r.get("measured"))}</td><td>{_e(r["check"])}（{_e(r.get("basis"))}）</td></tr>')
        h.append('</table></div>')
    else:
        h.append('<p>沒有擋件，也沒有要你看的項目。</p>')
    other = [r for r in rows if r["bucket"] in ("info", "undetermined")]
    if other:
        h.append(f'<details><summary>資訊與無法判定（{len(other)} 項）</summary><div class="wrap"><table class="rows">')
        for r in other:
            why = r.get("reason") or r.get("message") or ""
            h.append(f'<tr><td>{BUCKET_ZH[r["bucket"]]}</td><td>{_e(r["where"])}</td><td>{_e(r.get("message"))}'
                     f'{"" if not r.get("reason") else "（" + _e(r["reason"]) + "）"}</td><td>{_e(r["check"])}</td></tr>')
        h.append('</table></div></details>')
    h.append('</div>')

    # decisions
    h.append('<h2>整片決策</h2><div class="cards">')
    decs = timeline.get("decisions") or {}
    for k in M.DECISION_KEYS:
        e = decs.get(k)
        req = "（核可必填）" if k in M.REQUIRED_DECISIONS else ""
        if e:
            src = e.get("source")
            h.append(f'<div class="card"><div class="k">{DECISION_ZH[k]} {k}{req}</div><div class="v">{_e(e.get("value"))}</div>'
                     f'<span class="tag {src}">{SOURCE_ZH.get(src, src)}</span>'
                     f'{"<div class=\"muted\">依據：" + _e(e["evidence"]) + "</div>" if e.get("evidence") else ""}</div>')
        else:
            h.append(f'<div class="card"><div class="k">{DECISION_ZH[k]} {k}{req}</div><div class="v muted">—</div>'
                     f'<span class="tag unset">未定</span></div>')
    h.append('</div>')

    # tracks
    h.append('<h2>軌道</h2><div class="lanes">')
    h.append(f'<div class="axis">{_ticks(end)}</div>')
    h.append('<div class="lanehead">畫面段（斜線＝為接上下一段而延長；紅框＝轉場窗）</div><div class="lane">')
    if resolved.get("ground_preroll"):
        g = resolved["ground_preroll"]
        h.append(f'<div class="pre" style="left:0;width:{_pct(g["t1"], end)}">底色</div>')
    for p in pic:
        w = p["e_author"] - p["t0"]
        title = f'{p["id"]} {ROLE_ZH.get(p["role"], p["role"])} {_s(p["t0"])}–{_s(p["e"])} 秒'
        h.append(f'<div class="blk" title="{_e(title)}" style="left:{_pct(p["t0"], end)};width:{_pct(max(w, 0), end)}">'
                 f'{_e(p["id"])} {_e(ROLE_ZH.get(p["role"], ""))}</div>')
        if p["extension_s"]:
            h.append(f'<div class="ext" title="{_e(p["id"])} 延長 {p["extension_s"]:g} 秒" '
                     f'style="left:{_pct(p["e_author"], end)};width:{_pct(p["e"] - p["e_author"], end)}"></div>')
        if p["window"]:
            h.append(f'<div class="win" title="{_e(p["id"])} 轉場窗 {_s(p["window"][0])}–{_s(p["window"][1])} 秒" '
                     f'style="left:{_pct(p["window"][0], end)};width:{_pct(p["window"][1] - p["window"][0], end)}"></div>')
    if resolved.get("tail_hold"):
        th = resolved["tail_hold"]
        h.append(f'<div class="tailh" title="片尾停留：畫面停在最後一格、聲音全部靜音" '
                 f'style="left:{_pct(th["t0"], end)};width:{_pct(th["t1"] - th["t0"], end)}">片尾停留</div>')
    h.append('</div>')
    zs = sorted({o["z"] for o in resolved["overlay"]})
    for z in zs:
        h.append(f'<div class="lanehead">常駐層 z={z}</div><div class="lane">')
        for o in resolved["overlay"]:
            if o["z"] == z:
                h.append(f'<div class="blk ov" title="{_e(o["id"])} {_s(o["t0"])}–{_s(o["e"])} 秒" '
                         f'style="left:{_pct(o["t0"], end)};width:{_pct(o["e"] - o["t0"], end)}">{_e(o["id"])}</div>')
        h.append('</div>')
    h.append('<div class="lanehead">旁白句（虛線＝估算長度，還沒有錄音）</div><div class="lane">')
    for ln in resolved["lines"]:
        cls = "blk ln est" if ln["estimated"] else "blk ln"
        lab = f'{ln["id"]}{" 估算" if ln["estimated"] else ""}'
        h.append(f'<div class="{cls}" title="{_e(ln["id"])} {_s(ln["t0"])}–{_s(ln["t1"])} 秒" '
                 f'style="left:{_pct(ln["t0"], end)};width:{_pct(ln["t1"] - ln["t0"], end)}">{_e(lab)}</div>')
    h.append('</div>')
    if resolved["sfx"]:
        h.append('<div class="lanehead">音效點</div><div class="lane">')
        for s in resolved["sfx"]:
            h.append(f'<span class="sfx" title="{_e(s["sound"])} {_s(s["t"])} 秒：{_e(s["why"])}" '
                     f'style="left:{_pct(s["t"], end)}"></span>')
        h.append('</div>')
    cap = t["captions"]
    h.append(f'<p class="muted">字幕：{"由旁白句產生（" + _e(cap["style"]) + "）" if cap else "未設定"}'
             f'；音樂：TL-4 起才有。縮圖與意圖量測：出片後才有。</p></div>')

    # clip table
    h.append('<h2>片段表</h2><div class="wrap"><table class="clips"><tr><th>片段</th><th>角色</th><th>秒數</th>'
             '<th>錨點（作者寫法）</th><th>自由度</th><th>手法</th><th>動作意圖</th><th>固定欄位</th><th>覆寫</th>'
             '<th>出處</th><th>候選</th><th>縮圖</th></tr>')
    cand_counts = validate.get("candidate_counts") or {}
    for p in pic + [dict(o, role="overlay") for o in resolved["overlay"]]:
        c = clips[p["id"]]
        secs = f'{_s(p["t0"])}–{_s(p["e"])}'
        if p.get("extension_s"):
            secs += f'<br><span class="muted">作者長度 {_s(p["d_author"])}，延長 {p["extension_s"]:g}</span>'
        fr = FREEDOM_ZH.get(p["freedom"], p["freedom"]) + ("（預設）" if p.get("freedom_defaulted") else "")
        dev = c.get("device") or {}
        device = dev.get("component") or (f'族 {dev["family"]}' + (f'，基調 {dev["tone"]}' if dev.get("tone") else "")
                                          if dev.get("family") else "不限（free）")
        if c.get("what"):
            device += f'<br><span class="muted">{_e(c["what"])}</span>'
        mi = c.get("motion_intent") or []
        mi_html = "<ul class=\"mi\">" + "".join(f"<li>{_e(x)}</li>" for x in mi) + "</ul>" if mi else '<span class="muted">（空）</span>'
        ks = c.get("keys") or []
        if ks:  # frame roles (agent-review design 3.1): K = key frame, B = breakdown; seconds in clip time
            mi_html += '<ul class="mi keys">' + "".join(
                f'<li>{"K" if k["role"] == "key" else "B"} {_e(k["id"])} @{k["at"]:g} 秒'
                + (f'，停 {k["hold"]:g} 秒' if k.get("hold") else "") + f'：{_e(k["what"])}</li>' for k in ks) + "</ul>"
        fixed = []
        if p["role"] != "overlay":
            tin = c.get("transition_in")
            fixed.append("轉場：" + ("硬切" if tin == "cut" else f'{tin["component"]} {tin["dur"]:g} 秒' if isinstance(tin, dict)
                                    else "放開（核可時當硬切）" if p["freedom"] == "guided" else "硬切（缺省）"))
        if p["freedom"] == "guided":
            fixed.append("版面：" + ("已指定：" + _e(c["layout"]) if c.get("layout") else "放開"))
            cam = c.get("camera") or {}
            for k in ("goal", "method", "move", "pace"):
                fixed.append(f"鏡頭 {k}：" + ("已指定 " + _e(cam[k]) if cam.get(k) else "放開"))
        for f in ("headline", "data", "visual"):
            if c.get(f):
                fixed.append(f'{f}：{_e(c[f])}')
        o = c.get("override")
        ov = "無" if not o else (f'{"待你確認" if o.get("source") == "user" else "模型寫的，無效"}：{_e(o.get("why"))}')
        claims = "、".join(f"{k}→{v}" for k, v in (c.get("claims") or {}).items()) or "—"
        h.append(f'<tr><td class="id">{_e(p["id"])}</td><td>{_e(ROLE_ZH.get(p["role"], p["role"]))}</td><td>{secs}</td>'
                 f'<td>at {_e(p["anchors"]["at"])}<br>dur {_e(p["anchors"]["dur"])}</td><td>{_e(fr)}</td><td>{device}</td>'
                 f'<td>{mi_html}</td><td class="fixed">{"<br>".join(fixed)}</td><td>{ov}</td><td>{_e(claims)}</td>'
                 f'<td>{_e(cand_counts.get(p["id"], "—"))}</td><td class="muted">出片後才有</td></tr>')
    h.append('</table></div>')

    # narration table
    if resolved["lines"]:
        h.append('<h2>旁白句</h2><div class="wrap"><table class="clips"><tr><th>句</th><th>屬於</th><th>秒數</th>'
                 '<th>長度來源</th><th>字幕文字</th><th>出處</th></tr>')
        by = {ln["id"]: ln for ln in t["narration"]}
        for ln in resolved["lines"]:
            src = {"est_dur": "估算（手填）", "rate": "估算（每秒 4 字）"}.get(ln["dur_source"], ln["dur_source"])
            h.append(f'<tr><td class="id">{_e(ln["id"])}</td><td>{_e(ln["section"])}</td>'
                     f'<td>{_s(ln["t0"])}–{_s(ln["t1"])}</td><td>{_e(src)}</td><td>{_e(by[ln["id"]]["text"])}</td>'
                     f'<td>{_e(by[ln["id"]].get("claim") or "—")}</td></tr>')
        h.append('</table></div>')
    assets = timeline.get("assets") or []
    if assets:
        h.append('<h2>素材</h2><div class="wrap"><table class="clips"><tr><th>素材</th><th>種類</th><th>路徑</th>'
                 '<th>身分來源</th><th>宣稱來源</th><th>授權</th></tr>')
        for a in assets:
            por = "、".join(f"{k}：{v}" for k, v in (a.get("portrays") or {}).items()) or "—"
            h.append(f'<tr><td class="id">{_e(a["id"])}</td><td>{_e(a["kind"])}</td><td>{_e(a["path"])}</td>'
                     f'<td>{_e(por)}</td><td>{_e(a.get("claims_ref") or "—")}</td><td>{_e(a.get("license") or "—")}</td></tr>')
        h.append('</table></div>')
    h.append(f'<p class="muted">本頁由 tl.py view 從 film.timeline.json、build/timeline.resolved.json、'
             f'build/validate.json、state.json 產生；手改會在下次 view 時被覆蓋。{NOT_JUDGED_ZH}。</p>')
    h.append('</main></body></html>')
    return "\n".join(h) + "\n"

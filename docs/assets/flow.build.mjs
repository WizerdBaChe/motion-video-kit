#!/usr/bin/env node
// Regeneration source for docs/assets/flow.<lang>.svg: the README "怎麼做一支片 / How a film gets made" diagram.
// Reader = a first-pass README visitor (audience-fit A1). Every node maps to a numbered step of
// reference-impl/skills/motion-video/SKILL.md "Order of work" (--mapping prints the table, copied into
// docs/DEVELOPER.md); every amber card names a shipped tool path. Layout is hand-placed on a grid, the model asserts
// on geometry (text fits its box, nodes inside the canvas, no node overlap, every edge endpoint on a node border,
// no two edges cross) and --selftest feeds known-bad models that must FAIL.
//
//   node docs/assets/flow.build.mjs [--lang en]   build + asserts (exit 1 on any FAIL)
//   node docs/assets/flow.build.mjs --selftest     known-bad controls must FAIL (exit 2 if one passes)
//   node docs/assets/flow.build.mjs --mapping      print the node -> source table
//
// The PNG comes from build_assets.py --only flow.

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const argv = process.argv.slice(2);
const li = argv.indexOf('--lang');
const LANG = li >= 0 ? argv[li + 1] : 'zh-TW';
if (!['zh-TW', 'en'].includes(LANG)) { console.error(`unknown --lang ${LANG}`); process.exit(2); }

const C = {
  ink: '#1f2328', mute: '#57606a', bg: '#ffffff', line: '#6e7781', back: '#cf222e', link: '#c58a16',
  step: ['#ddeafb', '#3b74c9'], core: ['#fde2e4', '#c4421a'], tool: ['#fcecc9', '#c58a16'], skill: ['#e6f4ea', '#2e7d4f'],
};
const W = LANG === 'en' ? 240 : 204, H = 74, GAPX = 40, X0 = 36;
const colX = (i) => X0 + i * (W + GAPX);               // five columns
const ROW = { top: 128, mid: 268, bot: 408 };           // tool band above, rows 1 and 2, tool band below
const CANVAS = { w: X0 * 2 + 5 * W + 4 * GAPX, h: 586 };

const T = {
  'zh-TW': {
    title: '怎麼做一支程式算繪的影片', legendStep: '步驟', legendCore: '核心：導演表／分鏡', legendTool: '本 repo 附的工具', legendBack: '不合格：只改一處再審',
    steps: [
      ['① 問清楚', '用途・受眾・能量'], ['② 整片先定', '一個受眾・一個基調'], ['③ 選片型', '廣告・導覽・解說'], ['④ 節奏來源', '小節線／旁白句首'],
      ['⑤ 導演表＋分鏡', '寫表，核可才動手'], ['⑥ 選手法', '每個手法一句動機'], ['⑦ 寫頁面', '每格都是時間函數'], ['⑧ 匯出＋查檔', '逐格算繪，驗過才發布'],
      ['⑨ 審片', '先看 1 fps 整片表'], ['⑩ 交付', 'A 必驗・B 體驗'],
    ],
    skill: ['規範（skills/motion-video）', 'whole-film-rules · film-types · rhythm-transitions-camera'],
    tl: ['timeline/tl.py', 'validate→resolve→approve'],
    fk: ['filmkit', 'render 匯出 · check 查檔'],
    ins: ['量測儀器 + tools/review', 'beatgrid · segments · shotstats · density … / 審片迴圈 G0–G3'],
    back: '最多 3 輪',
  },
  en: {
    title: 'How a code-rendered film gets made', legendStep: 'step', legendCore: 'core: director sheet / storyboard', legendTool: 'tool shipped in this repo', legendBack: 'fails: fix one thing, review again',
    steps: [
      ['1 Confirm', 'purpose · audience · energy'], ['2 Whole film first', 'one audience · one tone'], ['3 Film type', 'ad · tour · explainer'], ['4 Rhythm source', 'music bars / narration'],
      ['5 Director sheet', 'write it, approve it'], ['6 Devices', 'each has a motive line'], ['7 Build the page', 'every frame = f(time)'], ['8 Export + check', 'verify, then publish'],
      ['9 Review', '1 fps whole-film sheet'], ['10 Deliver', 'A must-check · B feel'],
    ],
    skill: ['Rules (skills/motion-video)', 'whole-film-rules · film-types · rhythm-transitions-camera'],
    tl: ['timeline/tl.py', 'validate→resolve→approve'],
    fk: ['filmkit', 'render exports · check verifies'],
    ins: ['Instruments + tools/review', 'beatgrid · segments · shotstats · density … / review G0-G3'],
    back: 'at most 3 rounds',
  },
}[LANG];

const MAPPING = [
  ['1 Confirm', 'SKILL.md step 0', 'whole-film-rules.md section 0'], ['2 Whole film first', 'SKILL.md step 1', 'whole-film-rules.md section 1'],
  ['3 Film type', 'SKILL.md step 2', 'film-types.md'], ['4 Rhythm source', 'SKILL.md step 3', 'rhythm-transitions-camera.md section 1'],
  ['5 Director sheet + storyboard', 'SKILL.md step 4', 'docs/timeline-layer-psm.md; tools/timeline/'], ['6 Devices', 'SKILL.md step 5', 'whole-film-rules.md section 2a'],
  ['7 Build the page', 'SKILL.md step 6', 'build-and-export.md section 1'], ['8 Export + check', 'SKILL.md step 7', 'tools/filmkit/README.md'],
  ['9 Review', 'SKILL.md step 8', 'build-and-export.md section 3; tools/review/README.md'], ['10 Deliver', 'SKILL.md step 9', 'SKILL.md "Delivery shape"'],
];

// ── model ────────────────────────────────────────────────────────────────────
function buildModel(t) {
  const nodes = [];
  t.steps.forEach(([a, b], i) => {
    const row = i < 5 ? 'mid' : 'bot';
    const col = i < 5 ? i : 9 - i;                       // second row runs right to left so step 5 -> 6 is one line down
    nodes.push({ id: `n${i + 1}`, kind: i === 4 ? 'core' : 'step', x: colX(col), y: ROW[row] - H / 2, w: W, h: H, l1: a, l2: b });
  });
  const cards = [
    { id: 'skill', kind: 'skill', x: colX(0), y: 20, w: 4 * W + 3 * GAPX, h: 62, l1: t.skill[0], l2: t.skill[1] },
    { id: 'tl', kind: 'tool', x: colX(4), y: 20, w: W, h: 62, l1: t.tl[0], l2: t.tl[1] },
    { id: 'fk', kind: 'tool', x: colX(2), y: 470, w: W, h: 62, l1: t.fk[0], l2: t.fk[1] },
    { id: 'ins', kind: 'tool', x: colX(0), y: 470, w: 2 * W + GAPX, h: 62, l1: t.ins[0], l2: t.ins[1] },
  ];
  const by = Object.fromEntries([...nodes, ...cards].map((n) => [n.id, n]));
  const cx = (n) => n.x + n.w / 2, cy = (n) => n.y + n.h / 2;
  const edges = [];
  for (let i = 1; i <= 4; i++) edges.push({ id: `e${i}`, kind: 'main', from: `n${i}`, to: `n${i + 1}`, pts: [[by[`n${i}`].x + W, cy(by[`n${i}`])], [by[`n${i + 1}`].x, cy(by[`n${i + 1}`])]] });
  edges.push({ id: 'e5', kind: 'main', from: 'n5', to: 'n6', pts: [[cx(by.n5), by.n5.y + H], [cx(by.n6), by.n6.y]] });
  for (let i = 6; i <= 9; i++) edges.push({ id: `e${i}`, kind: 'main', from: `n${i}`, to: `n${i + 1}`, pts: [[by[`n${i}`].x, cy(by[`n${i}`])], [by[`n${i + 1}`].x + W, cy(by[`n${i + 1}`])]] });
  // sent back: step 9 up into the gap between the rows, over to step 7, down onto step 7's top
  const gapY = (ROW.mid + H / 2 + ROW.bot - H / 2) / 2;
  edges.push({ id: 'back', kind: 'back', from: 'n9', to: 'n7', pts: [[cx(by.n9), by.n9.y], [cx(by.n9), gapY], [cx(by.n7), gapY], [cx(by.n7), by.n7.y]] });
  // dashed links of the tool cards to the step they serve
  edges.push({ id: 'l_tl', kind: 'link', from: 'tl', to: 'n5', pts: [[cx(by.tl), by.tl.y + by.tl.h], [cx(by.n5), by.n5.y]] });
  for (const i of [1, 2, 3, 4]) edges.push({ id: `l_sk${i}`, kind: 'link', from: 'skill', to: `n${i}`, pts: [[cx(by[`n${i}`]), by.skill.y + by.skill.h], [cx(by[`n${i}`]), by[`n${i}`].y]] });
  edges.push({ id: 'l_fk', kind: 'link', from: 'n8', to: 'fk', pts: [[cx(by.n8), by.n8.y + H], [cx(by.fk), by.fk.y]] });
  edges.push({ id: 'l_ins', kind: 'link', from: 'n9', to: 'ins', pts: [[cx(by.n9), by.n9.y + H], [cx(by.n9), by.ins.y]] });
  return { nodes: [...nodes, ...cards], edges, by };
}

const estW = (s, px) => [...s].reduce((a, ch) => a + (ch.charCodeAt(0) > 0x2e80 ? px : px * 0.58), 0);

function assertModel(m) {
  const fails = [];
  for (const n of m.nodes) {
    if (n.x < 0 || n.y < 0 || n.x + n.w > CANVAS.w || n.y + n.h > CANVAS.h) fails.push(`${n.id} outside canvas`);
    if (estW(n.l1, 16) > n.w - 16) fails.push(`${n.id} title overflows its box`);
    if (estW(n.l2, 12) > n.w - 16) fails.push(`${n.id} subtitle overflows its box`);
  }
  for (let i = 0; i < m.nodes.length; i++) for (let j = i + 1; j < m.nodes.length; j++) {
    const a = m.nodes[i], b = m.nodes[j];
    if (a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h) fails.push(`${a.id} overlaps ${b.id}`);
  }
  const onBorder = (p, n) => {
    const [x, y] = p, inX = x >= n.x - 0.5 && x <= n.x + n.w + 0.5, inY = y >= n.y - 0.5 && y <= n.y + n.h + 0.5;
    return inX && inY && (Math.abs(x - n.x) < 0.5 || Math.abs(x - n.x - n.w) < 0.5 || Math.abs(y - n.y) < 0.5 || Math.abs(y - n.y - n.h) < 0.5);
  };
  const segs = [];
  for (const e of m.edges) {
    if (!onBorder(e.pts[0], m.by[e.from])) fails.push(`${e.id} starts off ${e.from}'s border`);
    if (!onBorder(e.pts[e.pts.length - 1], m.by[e.to])) fails.push(`${e.id} ends off ${e.to}'s border`);
    for (let i = 0; i + 1 < e.pts.length; i++) {
      const s = [e.pts[i], e.pts[i + 1], e.id];
      segs.push(s);
      for (const n of m.nodes) {  // a segment interior must not run through any node other than its two ends
        if (n.id === e.from || n.id === e.to) continue;
        const [[x1, y1], [x2, y2]] = s;
        const lx = Math.min(x1, x2), hx = Math.max(x1, x2), ly = Math.min(y1, y2), hy = Math.max(y1, y2);
        if (hx > n.x + 0.5 && lx < n.x + n.w - 0.5 && hy > n.y + 0.5 && ly < n.y + n.h - 0.5) fails.push(`${e.id} runs through ${n.id}`);
      }
    }
  }
  const cross = (a, b) => {   // axis-aligned segments only
    const [[ax1, ay1], [ax2, ay2]] = a, [[bx1, by1], [bx2, by2]] = b;
    const aH = ay1 === ay2, bH = by1 === by2;
    if (aH === bH) return false;
    const [h, v] = aH ? [a, b] : [b, a];
    const hy = h[0][1], vx = v[0][0];
    const inH = vx > Math.min(h[0][0], h[1][0]) + 0.5 && vx < Math.max(h[0][0], h[1][0]) - 0.5;
    const inV = hy > Math.min(v[0][1], v[1][1]) + 0.5 && hy < Math.max(v[0][1], v[1][1]) - 0.5;
    return inH && inV;
  };
  for (let i = 0; i < segs.length; i++) for (let j = i + 1; j < segs.length; j++) {
    if (segs[i][2] !== segs[j][2] && cross(segs[i], segs[j])) fails.push(`${segs[i][2]} crosses ${segs[j][2]}`);
  }
  return fails;
}

// ── drawing ──────────────────────────────────────────────────────────────────
const esc = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;');
function svgOf(m, t) {
  const o = [];
  const font = `font-family="'Noto Sans TC','Microsoft JhengHei','Segoe UI',sans-serif"`;
  o.push(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${CANVAS.w} ${CANVAS.h}" width="${CANVAS.w}" height="${CANVAS.h}" ${font} role="img" aria-label="${esc(t.title)}">`);
  o.push(`<defs><marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill="${C.line}"/></marker>`
       + `<marker id="ahb" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill="${C.back}"/></marker></defs>`);
  o.push(`<rect width="${CANVAS.w}" height="${CANVAS.h}" fill="${C.bg}"/>`);
  for (const e of m.edges) {
    const d = e.pts.map((p, i) => `${i ? 'L' : 'M'}${p[0]} ${p[1]}`).join(' ');
    if (e.kind === 'main') o.push(`<path d="${d}" fill="none" stroke="${C.line}" stroke-width="2.2" marker-end="url(#ah)"/>`);
    else if (e.kind === 'back') o.push(`<path d="${d}" fill="none" stroke="${C.back}" stroke-width="2" stroke-dasharray="7 5" marker-end="url(#ahb)"/>`);
    else o.push(`<path d="${d}" fill="none" stroke="${C.link}" stroke-width="1.4" stroke-dasharray="3 4"/>`);
  }
  const b = m.edges.find((e) => e.id === 'back');
  o.push(`<text x="${(b.pts[1][0] + b.pts[2][0]) / 2}" y="${b.pts[1][1] - 7}" text-anchor="middle" font-size="13" fill="${C.back}">${esc(t.legendBack)}（${esc(t.back)}）</text>`);
  for (const n of m.nodes) {
    const [fill, stroke] = C[n.kind];
    o.push(`<g data-node="${n.id}"><rect x="${n.x}" y="${n.y}" width="${n.w}" height="${n.h}" rx="${n.kind === 'step' || n.kind === 'core' ? 12 : 8}" fill="${fill}" stroke="${stroke}" stroke-width="${n.kind === 'core' ? 3 : 1.6}"/>`
      + `<text x="${n.x + n.w / 2}" y="${n.y + n.h / 2 - 4}" text-anchor="middle" font-size="16" font-weight="700" fill="${C.ink}">${esc(n.l1)}</text>`
      + `<text x="${n.x + n.w / 2}" y="${n.y + n.h / 2 + 17}" text-anchor="middle" font-size="12" fill="${C.mute}">${esc(n.l2)}</text></g>`);
  }
  const ly = CANVAS.h - 14;
  let lx = X0;
  for (const [fill, stroke, label] of [[C.step[0], C.step[1], t.legendStep], [C.core[0], C.core[1], t.legendCore], [C.tool[0], C.tool[1], t.legendTool]]) {
    o.push(`<rect x="${lx}" y="${ly - 11}" width="16" height="12" rx="3" fill="${fill}" stroke="${stroke}"/><text x="${lx + 22}" y="${ly}" font-size="13" fill="${C.mute}">${esc(label)}</text>`);
    lx += 40 + estW(label, 13);
  }
  o.push(`<text x="${CANVAS.w / 2}" y="${ROW.top - 40}" text-anchor="middle" font-size="0"> </text>`);
  o.push('</svg>');
  return o.join('\n');
}

// ── controls ─────────────────────────────────────────────────────────────────
function selftest() {
  const good = buildModel(T), results = [];
  const clone = () => JSON.parse(JSON.stringify(good));
  const ok = assertModel(good);
  results.push(['known-good model', ok.length === 0, `fails=${ok.length}`]);
  const m1 = clone(); m1.nodes[0].l1 = 'x'.repeat(40); results.push(['overflowing title must FAIL', assertModel(m1).some((f) => /overflows/.test(f)), 'detected']);
  const m2 = clone(); m2.nodes[1].x = m2.nodes[0].x + 20; results.push(['overlapping nodes must FAIL', assertModel(m2).some((f) => /overlaps/.test(f)), 'detected']);
  const m3 = clone(); m3.edges.find((e) => e.id === 'e1').pts[1][0] += 30; results.push(['edge ending off its node must FAIL', assertModel(m3).some((f) => /ends off/.test(f)), 'detected']);
  const m4 = clone(); const bk = m4.edges.find((e) => e.id === 'back'); bk.pts = [bk.pts[0], [bk.pts[0][0], 150], [bk.pts[3][0], 150], bk.pts[3]];
  results.push(['edge through a row of nodes must FAIL', assertModel(m4).some((f) => /runs through|crosses/.test(f)), 'detected']);
  let bad = 0;
  for (const [name, pass, note] of results) { console.log(`${pass ? 'ok  ' : 'BAD '} ${name} (${note})`); if (!pass) bad++; }
  return bad ? 2 : 0;
}

if (argv.includes('--mapping')) {
  console.log('| node | source step | rule / tool file |\n|---|---|---|');
  for (const r of MAPPING) console.log(`| ${r.join(' | ')} |`);
  process.exit(0);
}
if (argv.includes('--selftest')) process.exit(selftest());
const model = buildModel(T), fails = assertModel(model);
if (fails.length) { for (const f of fails) console.error('FAIL ' + f); process.exit(1); }
const out = path.join(HERE, `flow.${LANG}.svg`);
fs.writeFileSync(out, svgOf(model, T), 'utf8');
console.log(`wrote ${out} (${model.nodes.length} nodes, ${model.edges.length} edges, model asserts pass)`);

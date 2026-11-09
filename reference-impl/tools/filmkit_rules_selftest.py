"""Lab-side selftest for tools/filmkit_rules.json (outside the kit, because it reads the rules file).

    python -X utf8 tools/filmkit_rules_selftest.py

FK-INV-12: no kit file contains a rule id, a sentence fragment, a basis string, or a rule's key+value pair.
FK-INV-10: no rule sentence contains a quality verdict or design advice (same word list as the kit selftest).
R-11: film_types equals the slugs of the motion-video skill's film-types.md section headings.
FK-R-16 (M2): the real rules file evaluated by the kit's generic comparator on synthetic films.
Every control runs a positive arm (the defect is present, the check must fire) and a negative arm.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
KIT = HERE / "filmkit"
RULES = HERE / "filmkit_rules.json"
FILM_TYPES_MD = Path(__file__).resolve().parents[1] / "skills" / "motion-video" / "references" / "film-types.md"
TOP_KEYS = {"schema_version", "film_types", "rules", "params", "targets"}
# PSM 4.5 (Q-10): section id of film-types.md -> slug; section 0 and 1 are not film types
SECTION_SLUGS = {"1a": "intro-ad", "1b": "hype-ad", "1c": "product-tour", "2": "data-showreel",
                 "3": "narrated-explainer", "4": "profile-reel", "5": "music-video"}
NOT_FILM_TYPES = {"0", "1"}
PLACEHOLDER = re.compile(r"\{[a-z_0-9]+\}")
TARGET_KEYS = {"lufs", "true_peak", "tolerance_lu", "source", "review_when"}   # tolerance_lu: optional, additive to PSM 4.5 (M3 reading)


def load_kit_selftest():
    """The forbidden-word scan lives in the kit selftest; import it (its temp folder is removed again)."""
    sys.path.insert(0, str(KIT))
    import selftest as kst
    shutil.rmtree(kst.TMP, ignore_errors=True)
    return kst


def rule_tokens(rules: dict) -> tuple[list[str], list[tuple[str, str]]]:
    """Strings that must not appear in the kit, and (key, value) pairs matched together."""
    toks, pairs = [], []
    for r in rules.get("rules", []):
        toks.append(r["id"])
        for k in ("sentence_zh", "missing_zh"):
            for frag in PLACEHOLDER.split(r.get(k) or ""):
                frag = frag.strip(" 。：（）()–-")
                if len(frag) >= 3:
                    toks.append(frag)
        if r.get("basis"):
            toks.append(r["basis"])
        for k, v in r.items():
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                pairs.append((k, str(v)))
            elif isinstance(v, list) and v and all(isinstance(x, (int, float)) for x in v):
                pairs.append((k, str(v[0])))
        for k, v in (r.get("select") or {}).items():
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                pairs.append((k, str(v)))
    for name, t in (rules.get("targets") or {}).items():
        toks.append(name)
        for k, v in t.items():
            if isinstance(v, (int, float)):
                pairs.append((k, str(v)))
    return toks, pairs


def kit_violations(kit: Path, rules: dict) -> list[str]:
    toks, pairs = rule_tokens(rules)
    out = []
    for p in sorted(kit.rglob("*")):
        if not p.is_file() or "__pycache__" in p.parts or p.suffix == ".pyc":
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        rel = p.relative_to(kit).as_posix()
        for t in toks:
            if t in text:
                out.append(f"{rel}: contains {t!r}")
        for k, v in pairs:
            if re.search(re.escape(k) + r"""["']?\s*[:=]\s*\[?\s*""" + re.escape(v) + r"(?![\d.])", text):
                out.append(f"{rel}: contains {k} = {v}")
    return out


def structure_problems(rules: dict) -> list[str]:
    p = []
    if set(rules) != TOP_KEYS:
        p.append(f"top-level keys {sorted(rules)} != {sorted(TOP_KEYS)}")
    ft = set(rules.get("film_types") or [])
    for r in rules.get("rules", []):
        for t in r.get("film_types") or []:
            if t not in ft:
                p.append(f"rule {r.get('id')}: film type {t} not in film_types")
        if "暫定" in (r.get("basis") or ""):
            p.append(f"rule {r.get('id')}: basis carries the provisional word itself (P-19c)")
        if "missing_ok" in r and not isinstance(r["missing_ok"], bool):
            p.append(f"rule {r.get('id')}: missing_ok is not true or false")
    tg = rules.get("targets")
    if not isinstance(tg, dict):
        return p + ["targets is not an object"]
    num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)
    for name, t in tg.items():
        if not isinstance(t, dict):
            p.append(f"target {name}: not an object")
            continue
        if set(t) - TARGET_KEYS:
            p.append(f"target {name}: unknown keys {sorted(set(t) - TARGET_KEYS)}")
        for k in ("lufs", "true_peak"):
            if not num(t.get(k)):
                p.append(f"target {name}: {k} is not a number")
        if "tolerance_lu" in t and not (num(t["tolerance_lu"]) and t["tolerance_lu"] > 0):
            p.append(f"target {name}: tolerance_lu is not a positive number")
        for k in ("source", "review_when"):
            if not isinstance(t.get(k), str) or not t[k].strip():
                p.append(f"target {name}: {k} missing or empty (an external fact needs its source and the event that invalidates it)")
        if isinstance(t.get("source"), str) and "read 20" not in t["source"]:
            p.append(f"target {name}: source carries no 'read <date>'")
    return p


def slugs_from_md(text: str) -> tuple[list[str], list[str]]:
    slugs, unknown = [], []
    for m in re.finditer(r"(?m)^## §(\w+)\b", text):
        sid = m.group(1)
        if sid in NOT_FILM_TYPES:
            continue
        if sid in SECTION_SLUGS:
            slugs.append(SECTION_SLUGS[sid])
        else:
            unknown.append(sid)
    return slugs, unknown


def check_json_of(kst, rules_path: Path, film: Path, *extra) -> tuple[int, dict]:
    """Run the kit's check.py on `film` with the rules file; return (exit code, check.json)."""
    p = subprocess.run([sys.executable, "-X", "utf8", str(KIT / "check.py"), str(film), "--rules", str(rules_path),
                        "--mounted-kit-hash", "none", *extra], capture_output=True, text=True, encoding="utf-8", errors="replace")
    doc = json.loads((film.parent / f"{film.name}.check.json").read_text(encoding="utf-8"))
    return p.returncode, doc


def r16(doc: dict) -> list[dict]:
    return [r for r in doc["rows"] if r["id"].startswith("FK-R-16")]


def rule_controls(arm, kst, rules: dict) -> None:
    """FK-R-16 on the real file: neutral numbers come from the file itself (the kit holds none of them)."""
    real = next((r for r in rules["rules"] if r.get("owner") == "filmkit" and r.get("kind") == "range"), None)
    if real is None:
        arm("FK-R-16", "negative", False, "the rules file has no owner-filmkit range rule")
        return
    rid = real["id"]
    lo, hi = real["range_s"]
    tmp = Path(tempfile.mkdtemp(prefix="filmkit_rules_fk16_"))
    try:
        def film(name, tail):
            segs = [("motion", 2)] + ([("still", tail)] if tail else [("motion", 2)])
            return kst.mk_film(tmp / name, segs)
        mid = round((lo + hi) / 2, 1)
        inside, outside, missing = film("inside.mp4", mid), film("outside.mp4", round(hi + 1.0, 1)), film("missing.mp4", 0)
        code, d1 = check_json_of(kst, RULES, inside)
        rows1 = [r for r in r16(d1) if r["id"] == f"FK-R-16#{rid}"]
        arm("FK-R-16", "negative", len(rows1) == 1 and rows1[0]["verdict"] == "PASS" and rows1[0]["text_zh"].endswith("（暫定）"),
            f"tail {mid} s inside the range: {[(r['id'], r['verdict'], r['measured']) for r in rows1]}; provisional suffix present: "
            f"{bool(rows1) and rows1[0]['text_zh'].endswith('（暫定）')}")
        code, d2 = check_json_of(kst, RULES, outside)
        rows2 = [r for r in r16(d2) if r["id"] == f"FK-R-16#{rid}"]
        arm("FK-R-16", "positive", len(rows2) == 1 and rows2[0]["verdict"] == "WARN" and rows2[0]["bucket"] == "look",
            f"tail {round(hi + 1.0, 1)} s above the range: {[(r['id'], r['verdict'], r['measured']) for r in rows2]}")
        code, d3 = check_json_of(kst, RULES, missing)
        rows3 = [r for r in r16(d3) if r["id"] == f"FK-R-16#{rid}"]
        prof = json.loads((KIT / "profiles.json").read_text(encoding="utf-8"))
        fz = prof["profiles"]["lab-round"]["thresholds"]["freeze"]
        floor = f"{min(float(fz['min_duration_s']), float(fz.get('end_min_duration_s', fz['min_duration_s']))):g}"   # end-anchored rule: the end floor (D18)
        md3 = (tmp / "missing.mp4.check.md").read_text(encoding="utf-8")
        arm("FK-R-16", "positive", len(rows3) == 1 and rows3[0]["verdict"] == "WARN" and rows3[0]["measured"] == "not detected"
            and f"長於 {floor} 秒" in rows3[0]["text_zh"] and rows3[0]["text_zh"] in md3,
            f"no still at the end: {[(r['id'], r['verdict'], r['measured']) for r in rows3]}; the missing sentence names the detection floor: "
            f"{f'長於 {floor} 秒' in (rows3[0]['text_zh'] if rows3 else '')}")
        # variants of the real file
        def variant(name, **changes):
            doc = json.loads(json.dumps(rules))
            for r in doc["rules"]:
                if r["id"] == rid:
                    r.update(changes)
            p = tmp / name
            p.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
            return p
        code, d4 = check_json_of(kst, variant("ratio.json", kind="ratio"), inside)
        rows4 = [r for r in r16(d4) if r["id"] == f"FK-R-16#{rid}"]           # the other owner-filmkit rule keeps its own row
        arm("FK-R-16", "positive", len(rows4) == 1 and rows4[0]["id"] == f"FK-R-16#{rid}" and rows4[0]["verdict"] == "UNDET"
            and rows4[0]["unfinished"] is False, f"kind ratio: {[(r['id'], r['verdict'], r['reason']) for r in rows4]}")
        code, d5 = check_json_of(kst, variant("timeline.json", owner="timeline"), inside)
        own5 = [r for r in r16(d5) if r["id"] == f"FK-R-16#{rid}"]
        arm("FK-R-16", "negative", own5 == [], f"owner timeline: rows of {rid} {[r['id'] for r in own5]} (all FK-R-16 rows {[r['id'] for r in r16(d5)]})")
        code, d6 = check_json_of(kst, variant("fixed.json", provisional=False), inside)
        rows6 = [r for r in r16(d6) if r["id"] == f"FK-R-16#{rid}"]
        arm("FK-R-16", "negative", len(rows6) == 1 and not rows6[0]["text_zh"].endswith("（暫定）") and rows6[0]["provisional"] is False,
            f"provisional false: sentence ends with {rows6[0]['text_zh'][-8:] if rows6 else None!r}")
        code, d7 = check_json_of(kst, RULES, inside, "--film-type", "not-a-listed-type")
        rows7 = r16(d7)
        arm("FK-R-16", "positive", len(rows7) == 1 and rows7[0]["id"] == "FK-R-16" and rows7[0]["verdict"] == "UNDET"
            and "film type not in vocabulary" in rows7[0]["reason"], f"film type outside the file's list: {[(r['id'], r['reason']) for r in rows7]}")
        listed = rules["film_types"][0]
        code, d8 = check_json_of(kst, RULES, inside, "--film-type", listed)
        arm("FK-R-16", "negative", any(r["id"] == f"FK-R-16#{rid}" and r["verdict"] == "PASS" for r in r16(d8)),
            f"film type {listed} (listed): {[(r['id'], r['verdict']) for r in r16(d8)]}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def head_controls(arm, kst, rules: dict) -> None:
    """FK-W32-33 (PSM 9.6): the head rule of the real file measures the first still that starts inside its window.
    Lengths and the window come from the rule's own range and selector."""
    rule = next((r for r in rules["rules"] if r.get("id") == "head_hold"), None)
    if rule is None:
        arm("head-hold", "negative", False, "the rules file has no head_hold entry")
        return
    rid = rule["id"]
    lo, hi = rule["range_s"]
    win = float(rule["select"].get("max_t0_s", 0))
    inside, outside = round(hi * 0.8, 1), round(hi + 0.6, 1)
    lead = round(win * 0.4, 1)                 # motion before a still that starts inside the window
    late = round(win + 1.0, 1)                 # motion before a still that starts outside it
    tmp = Path(tempfile.mkdtemp(prefix="filmkit_rules_head_"))
    try:
        def film(name, segs):
            return kst.mk_film(tmp / name, segs)
        f_in = film("inside.mp4", [("still", inside), ("motion", 3)])
        f_in_late = film("inside_later.mp4", [("motion", lead), ("still", inside), ("motion", 2)])
        f_e14 = film("e14_shaped.mp4", [("motion", lead), ("still", outside), ("motion", 2)])
        f_out = film("outside.mp4", [("still", outside), ("motion", 3)])
        f_none = film("none.mp4", [("motion", 4)])
        f_after = film("after_window.mp4", [("motion", late), ("still", 2.4), ("motion", 1)])
        f_short = film("short_after_window.mp4", [("motion", late + 2), ("still", inside), ("motion", 1)])

        def mine(doc):
            return [r for r in r16(doc) if r["id"] == f"FK-R-16#{rid}"]

        def fz8(doc):
            return [r for r in doc["rows"] if r["id"].startswith("FK-R-8#")]       # interval rows (the "none found" row has no #)
        _, d1 = check_json_of(kst, RULES, f_in)
        r1 = mine(d1)
        arm("head-hold", "positive", len(r1) == 1 and r1[0]["verdict"] == "PASS" and r1[0]["text_zh"].endswith("（暫定）") and not fz8(d1),
            f"{inside} s still from frame 0, then motion: {[(r['id'], r['verdict'], r['measured']) for r in r1]}; FK-R-8 rows {[r['id'] for r in fz8(d1)]}")
        _, d1b = check_json_of(kst, RULES, f_in_late)
        r1b = mine(d1b)
        arm("head-hold", "positive", len(r1b) == 1 and r1b[0]["verdict"] == "PASS" and r1b[0]["measured"] != "not detected"
            and r1b[0]["t0"] is not None and abs(r1b[0]["t0"] - lead) <= 0.3 and not fz8(d1b),
            f"{lead} s of motion, then a {inside} s still inside the window: {[(r['id'], r['verdict'], r['t0'], r['measured']) for r in r1b]}; "
            f"FK-R-8 rows {[r['id'] for r in fz8(d1b)]}")
        _, d1c = check_json_of(kst, RULES, f_e14)
        r1c = mine(d1c)
        arm("head-hold", "positive", len(r1c) == 1 and r1c[0]["verdict"] == "WARN" and r1c[0]["bucket"] == "look"
            and r1c[0]["t0"] is not None and abs(r1c[0]["t0"] - lead) <= 0.3 and not fz8(d1c),
            f"W30 E14 shape ({lead} s of motion, a {outside} s still, motion): {[(r['id'], r['verdict'], r['t0'], r['measured']) for r in r1c]}; "
            f"FK-R-8 rows {[r['id'] for r in fz8(d1c)]} (the rule row is the only one for the interval)")
        _, d2 = check_json_of(kst, RULES, f_out)
        r2 = mine(d2)
        arm("head-hold", "positive", len(r2) == 1 and r2[0]["verdict"] == "WARN" and r2[0]["bucket"] == "look"
            and not [r for r in fz8(d2) if r["bucket"] == "look"],
            f"{outside} s still from frame 0: {[(r['id'], r['verdict'], r['measured']) for r in r2]}; FK-R-8 look rows "
            f"{[r['id'] for r in fz8(d2) if r['bucket'] == 'look']} (the rule row is the only one for the interval)")
        _, d3 = check_json_of(kst, RULES, f_none)
        r3 = mine(d3)
        arm("head-hold", "negative", len(r3) == 1 and r3[0]["verdict"] == "PASS" and r3[0]["bucket"] == "confirmed"
            and r3[0]["measured"] == "not detected" and r3[0]["text_zh"].startswith("片頭 5 秒內沒有偵測到"),
            f"motion from frame 0: {[(r['id'], r['verdict'], r['bucket'], r['measured']) for r in r3]}")
        doc = json.loads(json.dumps(rules))
        for r in doc["rules"]:
            if r["id"] == rid:
                r.pop("missing_ok", None)
        nm = tmp / "no_missing_ok.json"
        nm.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
        _, d4 = check_json_of(kst, nm, f_none)
        r4 = mine(d4)
        arm("head-hold", "positive", len(r4) == 1 and r4[0]["verdict"] == "WARN" and r4[0]["bucket"] == "look",
            f"motion from frame 0, the same rule without missing_ok: {[(r['id'], r['verdict'], r['bucket']) for r in r4]}")
        _, d5 = check_json_of(kst, RULES, f_after)
        arm("head-hold", "negative", len(mine(d5)) == 1 and mine(d5)[0]["verdict"] == "PASS" and mine(d5)[0]["measured"] == "not detected"
            and [r for r in fz8(d5) if r["bucket"] == "look"],
            f"2.4 s still starting at {late} s (after the {win:g} s window): {[(r['id'], r['verdict'], r['measured']) for r in mine(d5)]}; "
            f"FK-R-8 look rows {[r['id'] for r in fz8(d5) if r['bucket'] == 'look']} (not a head still, so the general rule keeps it)")
        _, d6 = check_json_of(kst, RULES, f_short)
        arm("head-hold", "negative", len(mine(d6)) == 1 and mine(d6)[0]["measured"] == "not detected" and not fz8(d6),
            f"{inside} s still after the window (general floor): {[(r['id'], r['verdict'], r['measured']) for r in mine(d6)]}; FK-R-8 rows {[r['id'] for r in fz8(d6)]}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def check_doc(film: Path, rules_path: Path | None, *extra) -> dict:
    argv = [sys.executable, "-X", "utf8", str(KIT / "check.py"), str(film), "--mounted-kit-hash", "none", "--audio-expected", "yes", *extra]
    if rules_path is not None:
        argv += ["--rules", str(rules_path)]
    subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return json.loads((film.parent / f"{film.name}.check.json").read_text(encoding="utf-8"))


def row17(doc: dict, rid: str = "FK-R-17") -> dict | None:
    return next((r for r in doc["rows"] if r["id"] == rid), None)


def loudness_controls(arm, kst, rules: dict) -> None:
    """FK-R-17 (M3). Part 1 uses neutral numbers of a fixture rules file (design 9: about -26 LUFS against -20.5); part 2 runs
    the real targets of the rules file: normalize to each, measure the new file, then check it against the same target."""
    tmp = Path(tempfile.mkdtemp(prefix="filmkit_rules_fk17_"))
    try:
        tone = kst.mk_tone(tmp / "tone.mp4")                      # about -26 LUFS, true peak about -25 dBTP
        fx = tmp / "fixture_rules.json"
        fx.write_text(json.dumps({"schema_version": 1, "film_types": [], "rules": [], "params": {}, "targets": {
            "tgt_off": {"lufs": -20.5, "true_peak": -1.5, "tolerance_lu": 0.4, "source": "fixture", "review_when": "never"}}}), encoding="utf-8")
        d_plain = check_doc(tone, None)
        info = row17(d_plain)
        arm("FK-R-17", "negative", info is not None and info["verdict"] == "PASS" and info["severity"] == "info"
            and abs(info["values"]["integrated_lufs"] + 26.0) <= 0.3 and [r["id"] for r in d_plain["rows"] if r["id"].startswith("FK-R-17")] == ["FK-R-17"],
            f"no --rules: one info row, {info['measured'] if info else None}")
        d_fx = check_doc(tone, fx, "--target", "tgt_off")
        c = row17(d_fx, "FK-R-17#tgt_off")
        arm("FK-R-17", "positive", c is not None and c["verdict"] == "WARN" and c["bucket"] == "look" and abs(c["values"]["deviation_lu"] + 5.5) <= 0.3
            and row17(d_fx) is not None, f"measured about -26 against fixture target -20.5: {c['verdict'] if c else None}/{c['bucket'] if c else None} "
            f"({c['measured'] if c else None})")
        d_fx2 = check_doc(tone, fx)
        arm("FK-R-17", "negative", [r["id"] for r in d_fx2["rows"] if r["id"].startswith("FK-R-17")] == ["FK-R-17"],
            "rules file given but no --target named: info row only, nothing compared")
        # part 2: the file's own targets
        two = kst.mk_tone(tmp / "two.mp4", two_level=True)
        for name, t in (rules.get("targets") or {}).items():
            out = tmp / f"norm_{re.sub('[^a-z0-9]', '_', name)}.mp4"
            p = subprocess.run([sys.executable, "-X", "utf8", str(KIT / "transform.py"), "normalize", str(two), "--out", str(out),
                                "--rules", str(RULES), "--target", name], capture_output=True, text=True, encoding="utf-8", errors="replace")
            m = None
            if out.is_file():
                m = kst.loud_of(out)
            margin = float(t.get("tolerance_lu", 0.5))             # the file's tolerance, else a control margin of 0.5 LU (not a kit value)
            near = m is not None and abs(m["integrated_lufs"] - t["lufs"]) <= margin and m["true_peak_db"] <= t["true_peak"] + 0.05
            arm("FK-R-17", "negative", p.returncode == 0 and near,
                f"normalize to target {name!r}: exit {p.returncode}; new file measures {m}; file target {t['lufs']} LUFS / {t['true_peak']} dBTP, margin {margin}")
            d_ok = check_doc(out, RULES, "--target", name) if out.is_file() else {"rows": []}
            r_ok = row17(d_ok, f"FK-R-17#{name}")
            want = "PASS" if "tolerance_lu" in t else "UNDET"
            arm("FK-R-17", "negative" if want == "PASS" else "positive", r_ok is not None and r_ok["verdict"] == want,
                f"normalized file checked against {name!r}: {r_ok['verdict'] if r_ok else None} (expected {want}: "
                f"{'the target has a tolerance' if want == 'PASS' else 'the target gives no loudness tolerance, so the kit does not invent one'})")
            d_off = check_doc(two, RULES, "--target", name)
            r_off = row17(d_off, f"FK-R-17#{name}")
            want_off = "WARN" if "tolerance_lu" in t else "UNDET"
            arm("FK-R-17", "positive", r_off is not None and r_off["verdict"] == want_off and (want_off != "WARN" or r_off["bucket"] == "look"),
                f"un-normalized file (about -28 LUFS) against {name!r}: {r_off['verdict'] if r_off else None}/{r_off['bucket'] if r_off else None}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    rules = json.loads(RULES.read_text(encoding="utf-8"))
    kst = load_kit_selftest()
    results = []

    def arm(cid, name, ok, detail, skipped=None):
        results.append((cid, name, ok, detail, skipped))

    # FK-INV-12: kit scan
    v = kit_violations(KIT, rules)
    arm("FK-INV-12", "negative", not v, f"kit scanned against {len(rule_tokens(rules)[0])} tokens and {len(rule_tokens(rules)[1])} key+value pairs; violations {v or 'none'}")
    tmp = Path(tempfile.mkdtemp(prefix="filmkit_rules_selftest_"))
    try:
        cp = tmp / "filmkit"
        shutil.copytree(KIT, cp, ignore=shutil.ignore_patterns("__pycache__"))
        (cp / "_fk" / "fixture_rule.py").write_text("RULE = 'end_hold'\n", encoding="utf-8")
        v1 = kit_violations(cp, rules)
        (cp / "_fk" / "fixture_rule.py").write_text("RULE = 'head_hold'\n", encoding="utf-8")
        v1h = kit_violations(cp, rules)
        sent = next(r for r in rules["rules"] if r["id"] == "head_hold")["missing_zh"].split("{")[0].strip()
        (cp / "_fk" / "fixture_rule.py").write_text(f"TEXT = {sent!r}\n", encoding="utf-8")
        v1s = kit_violations(cp, rules)
        rng = rules["rules"][0]["range_s"]          # the real rule's range, so the fixture follows a ruling change
        (cp / "_fk" / "fixture_rule.py").write_text(f'cfg = {{"range_s": [{rng[0]:g}, {rng[1]:g}]}}\n', encoding="utf-8")
        v2 = kit_violations(cp, rules)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    arm("FK-INV-12", "positive", any("end_hold" in x for x in v1), f"fixture kit file with the rule id -> {v1}")
    arm("FK-INV-12", "positive", any("head_hold" in x for x in v1h), f"fixture kit file with the head rule id -> {v1h}")
    arm("FK-INV-12", "positive", any(sent in x for x in v1s), f"fixture kit file with the start of the head rule's missing sentence -> {v1s}")
    tok = f"range_s = {rng[0]:g}"
    arm("FK-INV-12", "positive", any(tok in x for x in v2), f"fixture kit file with {tok} -> {v2}")

    # FK-R-16 on the real rules file (M2)
    rule_controls(arm, kst, rules)
    head_controls(arm, kst, rules)

    # FK-R-17 on neutral numbers and on the real targets (M3)
    loudness_controls(arm, kst, rules)

    # structure (P-19b)
    sp = structure_problems(rules)
    arm("rules-structure", "negative", not sp, f"top-level keys, film type references and targets: {sp or 'ok'}")
    bad = dict(rules, extra={})
    arm("rules-structure", "positive", bool(structure_problems(bad)), f"fixture with an extra top-level key -> {structure_problems(bad)}")
    fx_mo = json.loads(json.dumps(rules))
    fx_mo["rules"][0]["missing_ok"] = "yes"
    arm("rules-structure", "positive", bool(structure_problems(fx_mo)), f"rule fixture with missing_ok \"yes\" -> {structure_problems(fx_mo)}")
    names = list((rules.get("targets") or {}))
    if names:
        t0 = dict(rules["targets"][names[0]])
        for label, change in (("no review_when", {"review_when": ""}), ("no source", {"source": " "}), ("tolerance zero", {"tolerance_lu": 0}),
                              ("unknown key", {"default": True}), ("lufs not a number", {"lufs": "loud"}),
                              ("source without a read date", {"source": "somewhere"})):
            fxr = json.loads(json.dumps(rules))
            fxr["targets"][names[0]] = {**t0, **change}
            sp2 = structure_problems(fxr)
            arm("rules-structure", "positive", bool(sp2), f"target fixture ({label}) -> {sp2}")

    # FK-INV-10 on rule sentences (P-19d)
    sentences = [r.get(k) or "" for r in rules.get("rules", []) for k in ("sentence_zh", "missing_zh", "basis")]
    hits = [(s, kst.forbidden_hits(s)) for s in sentences if kst.forbidden_hits(s)]
    arm("FK-INV-10-rules", "negative", not hits, f"{len(sentences)} rule sentences scanned; hits {hits or 'none'}")
    fx = "片尾停留建議 3 秒。"
    arm("FK-INV-10-rules", "positive", kst.forbidden_hits(fx) == ["建議"], f"fixture sentence -> {kst.forbidden_hits(fx)}")

    # R-11 film types vs film-types.md
    if FILM_TYPES_MD.is_file():
        slugs, unknown = slugs_from_md(FILM_TYPES_MD.read_text(encoding="utf-8"))
        arm("R-11", "negative", slugs == rules["film_types"] and not unknown,
            f"film-types.md headings -> {slugs}; unmapped sections {unknown or 'none'}")
        fx_md = FILM_TYPES_MD.read_text(encoding="utf-8") + "\n## §6 New type\n"
        s2, u2 = slugs_from_md(fx_md)
        arm("R-11", "positive", u2 == ["6"], f"fixture md with a new section §6 -> unmapped {u2}")
    else:
        arm("R-11", "negative", True, "", skipped=f"skipped ({FILM_TYPES_MD.as_posix()} not found)")
        arm("R-11", "positive", True, "", skipped=f"skipped ({FILM_TYPES_MD.as_posix()} not found)")

    n_pass = n_fail = n_skip = fired = 0
    for cid, name, ok, detail, skipped in results:
        if skipped:
            status = "SKIP"
            n_skip += 1
            detail = skipped
        elif ok:
            status = "PASS"
            n_pass += 1
            fired += name == "positive"
        else:
            status = "FAIL"
            n_fail += 1
        print(f"{status} {cid} [{name}] {detail}", flush=True)
    print(f"filmkit_rules_selftest: {n_pass} pass, {n_fail} fail, {n_skip} skipped; positive arms fired: {fired}")
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

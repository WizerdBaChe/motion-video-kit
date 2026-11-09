"""Component selection: design 6.8 tables A and B, candidate files (PSM 6.4, 4.11)."""
from __future__ import annotations

from .common import row
from .components import Index
from .messages_zh import zh
from .model import ENERGY

BASIS_A = "design 6.8 table A / TV-3"


def _ok(v, val) -> bool:
    return v == "any" or (isinstance(v, list) and val in v)


def _comp_id(ref: str) -> str:
    return ref.rsplit("@", 1)[0]


def mismatches(comp: dict, dec: dict, role: str, *, energy_values=None) -> tuple[list[str], list[str]]:
    """(incompatibilities, unset axes the component is not `any` on). dec = {energy, film_type, rhythm_source}."""
    tone, when = comp.get("tone") or {}, comp.get("when") or {}
    bad, unset = [], []
    ev = energy_values if energy_values is not None else ([dec["energy"]] if dec.get("energy") else None)
    if tone.get("energy") != "any":
        if ev is None:
            unset.append("energy")
        elif not all(e in (tone.get("energy") or []) for e in ev):
            bad.append(f"energy {'/'.join(ev)} not in {tone.get('energy')}")
    if tone.get("film_types") != "any":
        if dec.get("film_type") is None:
            unset.append("film_type")
        elif dec["film_type"] not in (tone.get("film_types") or []):
            bad.append(f"film_type {dec['film_type']} not in {tone.get('film_types')}")
    if not _ok(when.get("roles"), role):
        bad.append(f"role {role} not in {when.get('roles')}")
    rs = dec.get("rhythm_source")
    if when.get("rhythm_sources") != "any" and (rs is None or rs not in (when.get("rhythm_sources") or [])):
        bad.append(f"rhythm_source {rs or '(unset)'} not in {when.get('rhythm_sources')}")
    return bad, unset


def _conflicts(a: dict, b: dict) -> bool:
    ia, ib = _comp_id(a["ref"]), _comp_id(b["ref"])
    return ib in (a.get("conflicts") or []) or ia in (b.get("conflicts") or [])


def _locked(clip: dict, ref: str, dec: dict, index: Index, role: str, where: str, label: str, *, tone_only=False):
    """A2..A6 for one component reference of a locked (or free, tone_only) clip. Returns (rows, pending)."""
    cid = clip.get("id")
    rows, pending = [], []
    comp = index.get(ref)
    fam = ref.split(".", 1)[0]
    if comp is None:
        same = index.same_family(fam)
        rows.append(row("TV-3", where, "blocking", stage="static", measured=f"{label} {ref} not in the index",
                        expected=f"an existing component; same family: {same or 'none'}", basis=BASIS_A + " A2",
                        message_key="tv3.not_found", message=zh("tv3.not_found", clip=cid,
                                                                detail=f"{ref}；同族現有：{'、'.join(same) or '無'}")))
        return rows, pending
    if comp.get("state") not in ("candidate", "in-use", "verified"):
        rows.append(row("TV-3", where, "blocking", stage="static", measured=f"{ref} state {comp.get('state')}",
                        expected="candidate | in-use | verified", basis=BASIS_A + " A2",
                        message_key="tv3.draft", message=zh("tv3.draft", clip=cid, detail=ref)))
        return rows, pending
    bad, unset = mismatches(comp, dec, role)
    if tone_only:
        bad = [b for b in bad if b.startswith(("energy", "film_type"))]
    if unset:
        rows.append(row("TV-3", where, "blocking", stage="static", measured=f"{ref} is not `any` on unset {unset}",
                        expected=f"decide {'/'.join(unset)} first", basis=BASIS_A + " A3",
                        message_key="tv3.decide_first", message=zh("tv3.decide_first", clip=cid, detail="／".join(unset))))
        return rows, pending
    if bad:
        o = clip.get("override") or {}
        if o.get("source") == "user" and (o.get("confirmed") or "").strip():
            pending.append({"clip": cid, "component": ref, "why": o.get("why"), "confirmed": o.get("confirmed")})
            rows.append(row("TV-3", where, "info", stage="static", measured="; ".join(bad), expected="compatible",
                            basis=BASIS_A + " A4", message_key="tv3.pending",
                            message=zh("tv3.pending", clip=cid, detail=f"{ref}（{o.get('confirmed')}）")))
        else:
            rows.append(row("TV-3", where, "blocking", stage="static", measured="; ".join(bad), expected="compatible",
                            basis=BASIS_A + " A5 / TL-INV-5", message_key="tv3.incompatible",
                            message=zh("tv3.incompatible", clip=cid, detail=f"{ref}：{'；'.join(bad)}")))
    return rows, pending


def _candidates(family: str, role: str, dec: dict, index: Index, locked_components: set, energy_values=None) -> list[dict]:
    locked_entries = [index.get(r) for r in locked_components if index.get(r)]
    out = []
    for e in index.entries:
        if e.get("family") != family or e.get("state") not in ("candidate", "in-use", "verified"):
            continue
        bad, unset = mismatches(e, dec, role, energy_values=energy_values)
        if bad or unset:
            continue
        if any(_conflicts(e, le) for le in locked_entries):
            continue
        out.append({"ref": e["ref"], "family": e["family"], "label_type": bool(e.get("label_type")),
                    "claim_tier": e.get("claim_tier")})
    return sorted(out, key=lambda c: c["ref"])


def table_a(clip: dict, decisions: dict, index: Index, locked_components: set, *, freedom: str, uses=()) -> dict:
    """Device side of table A. Returns {rows, pending, candidates (guided) | None, note}."""
    cid = clip.get("id")
    role = clip.get("role") or "overlay"
    res = {"rows": [], "pending": [], "candidates": None, "note": None}
    if freedom == "free":  # A1: no filter; components a program uses must be tone-compatible
        for ref in uses:
            r, p = _locked(clip, ref, decisions, index, role, f"{cid}:{ref}", "uses", tone_only=True)
            res["rows"] += r
            res["pending"] += p
        return res
    if freedom == "locked":
        ref = (clip.get("device") or {}).get("component")
        r, p = _locked(clip, ref, decisions, index, role, cid, "device")
        res["rows"], res["pending"] = r, p
        return res
    dev = clip.get("device") or {}
    tone = dev.get("tone")
    ev = None
    if tone is not None:
        ev = tone if isinstance(tone, list) else [tone]
    elif decisions.get("energy") in ENERGY:
        ev = [decisions["energy"]]
    cands = _candidates(dev.get("family"), role, decisions, index, locked_components, energy_values=ev)
    res["candidates"] = cands
    if not cands:
        res["note"] = "no qualifying component; clip written from scratch"
        res["rows"].append(row("TV-3", f"{cid}.candidates", "info", stage="static", measured="0 candidates",
                               expected="A7", basis=BASIS_A + " A7", message_key="a7.empty",
                               message=zh("a7.empty", clip=cid)))
    return res


def transition_table_a(clip: dict, decisions: dict, index: Index, locked_components: set, *, freedom: str) -> dict:
    """Transition side (X-2): locked/free clip's transition_in.component through A2..A6 (free: tone only);
    guided: transition candidates; an absent guided transition is open (info)."""
    cid = clip.get("id")
    res = {"rows": [], "pending": [], "candidates": None, "note": None}
    t = clip.get("transition_in")
    if freedom == "guided":
        cands = _candidates("transition", "transition", decisions, index, locked_components)
        res["candidates"] = cands
        if not cands:
            res["note"] = "no qualifying transition component; write \"cut\" or leave it open"
        if t is None:
            res["rows"].append(row("TV-3", f"{cid}.transition", "info", stage="static", measured="transition_in absent",
                                   expected="listed at approve as a hard cut", basis="Z-7c / design 6.8",
                                   message_key="tv3.open_transition", message=zh("tv3.open_transition", clip=cid)))
        return res
    if isinstance(t, dict):
        r, p = _locked(clip, t["component"], decisions, index, "transition", f"{cid}.transition", "transition",
                       tone_only=(freedom == "free"))
        res["rows"], res["pending"] = r, p
    return res


def table_b(clip: dict, uses: list, candidates: list, rules, *, freedom: str, index: Index) -> list[dict]:
    """B1 (guided uses outside candidates -> TV-15 blocking) and B2 (stock family -> motion_intent, TV-5).
    B3 (free share) is TV-10 in validate --timed."""
    cid = clip.get("id")
    rows = []
    if freedom == "guided":
        allowed = {c["ref"] for c in candidates or []}
        for ref in uses:
            if ref not in allowed:
                rows.append(row("TV-15", f"{cid}:{ref}", "blocking", stage="static", measured=f"uses {ref}",
                                expected=f"one of {sorted(allowed) or 'no candidates'}", basis="SEM-6 / table B1",
                                message_key="tv15.outside", message=zh("tv15.outside", clip=cid, detail=ref)))
    return rows

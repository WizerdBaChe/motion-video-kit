"""tools/edit controls: each claim has a known-true and a known-false input (docs/edit-route-design.md).

    python -X utf8 tools/edit/selftest.py
Exit 0 only when every control holds. About 60 s (real ffmpeg renders + beatgrid reads).
"""
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
REPO = HERE.parents[1]

import assets as A  # noqa: E402
import beatcut as B  # noqa: E402
import edl as E  # noqa: E402
import render as R  # noqa: E402
from adapters import ComfyUIAdapter, MockAdapter, Request  # noqa: E402

RESULTS = []


def ok(name, cond, detail=""):
    RESULTS.append((name, bool(cond)))
    print(f"[{'ok' if cond else 'FAIL'}] {name}" + (f"  ({detail})" if detail else ""), flush=True)


def frames_of(p):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames", "-show_entries",
                        "stream=nb_read_frames", "-of", "csv=p=0", str(p)], capture_output=True, text=True)
    return int(r.stdout.strip() or 0)


def comfy_controls():
    ad = ComfyUIAdapter()
    g = ad.graph(Request(asset_id="t", prompt="a red kite", kind="image", size="512x384", seed=5))
    vals = [v for n in g.values() for v in n["inputs"].values()]
    ok("P7 comfyui graph: placeholders substituted (prompt text, int seed and size), none left",
       "a red kite" in vals and 5 in vals and 512 in vals and 384 in vals
       and not any(isinstance(v, str) and v.startswith("$") for v in vals))
    try:
        ad.graph(Request(asset_id="t", prompt="x", kind="video"))
        refused = False
    except ValueError:
        refused = True
    ok("N7 comfyui adapter refuses a video request (no video model installed)", refused)
    try:
        ad._get("/system_stats")
    except OSError:
        print("[skip] P8 live ComfyUI generation: server not reachable at 127.0.0.1:8188 (start it to run this control)")
        return
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        film = Path(td)
        (film / "assets").mkdir()
        rec = ad.generate(film, Request(asset_id="k1", prompt="a red kite in a blue sky, flat illustration",
                                        kind="image", size="512x384", seed=5))
        ok("P8 live ComfyUI image registers with workflow hash and model", not A.verify(film, "k1")
           and len(rec["params"]["workflow_sha256"]) == 64 and rec["model"].startswith("flux-2-klein"))


def main():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        td = Path(td)
        film = td / "film"
        (film / "assets").mkdir(parents=True)
        wav = td / "beat120.wav"
        subprocess.run([sys.executable, "-X", "utf8", str(REPO / "tools/make_beat_track.py"), "--bpm", "120",
                        "--bars", "8", "--offset", "0.5", "--out", str(wav)], check=True, capture_output=True)
        A.register(film, wav, "music", "footage", {"origin": "tools/make_beat_track.py --bpm 120 --bars 8 --offset 0.5",
                                                   "license": "own"})
        mock = MockAdapter()
        for k in range(1, 5):
            mock.generate(film, Request(asset_id=f"g{k}", prompt=f"test clip {k}", seconds=4, seed=k))

        # Provenance gate
        ok("P1 generated asset carries prompt, seed, adapter", not A.verify(film, "g1")
           and A.load(film, "g1")["seed"] == 1 and A.load(film, "g1")["adapter"] == "mock")
        try:
            A.register(film, film / "assets/g1.mp4", "bad", "generated", {
                "provider": "x", "model": "m", "prompt": "", "seed": None, "params": {}, "cost": None, "job_id": None,
                "adapter": "x", "adapter_version": "0", "inputs": []})
            refused = False
        except ValueError:
            refused = True
        ok("N1 generated asset with an empty prompt is refused at registration", refused)
        ok("N1b refused registration leaves no file", not (film / "assets/bad.mp4").exists())

        shutil.copyfile(film / "assets/g2.mp4", td / "g2.bak")
        with open(film / "assets/g2.mp4", "ab") as f:
            f.write(b"tamper")
        ok("N2 a file changed after registration fails verify", any("sha256" in p for p in A.verify(film, "g2")))
        shutil.copyfile(td / "g2.bak", film / "assets/g2.mp4")
        ok("P2 restored file verifies again", not A.verify(film, "g2"))

        # Plain EDL render: exact frame count, OTIO round trip
        tl = E.new("plain", 30)
        for k in (1, 2, 3):
            E.add_clip(tl, film, f"g{k}", 0, 45)
        E.save(tl, film / "edit/plain.otio")
        pl, probs = E.plan(E.read(film / "edit/plain.otio"), film)
        ok("P3 OTIO round trip keeps 3 clips and 135 frames", not probs and pl["total_frames"] == 135, str(probs))
        rec = R.render(film, film / "edit/plain.otio", film / "build/plain.mp4", size="640x360")
        n = frames_of(film / "build/plain.mp4")
        ok("P4 rendered plain EDL has exactly 135 frames", n == 135, f"{n} frames")
        ok("P4b filmkit check ran with no blocking row", rec["check"] and rec["check"]["exit"] == 0,
           json.dumps(rec["check"])[:300])

        pp = A.prov_path(film, "g3")
        pp.rename(td / "g3.prov")
        try:
            R.render(film, film / "edit/plain.otio", film / "build/never.mp4", size="640x360", check=False)
            refused = False
        except R.Refused as e:
            refused = "g3" in str(e)
        ok("N3 render refuses an EDL whose asset has no provenance, before ffmpeg", refused
           and not (film / "build/never.mp4").exists())
        (td / "g3.prov").rename(pp)

        tl = E.new("long", 30)
        E.add_clip(tl, film, "g1", 60, 90)
        E.save(tl, film / "edit/long.otio")
        try:
            R.render(film, film / "edit/long.otio", film / "build/long.mp4", size="640x360", check=False)
            refused = False
        except R.Refused:
            refused = True
        ok("N4 render refuses a clip range past the source end (4 s source, EDL needs 5 s)", refused)

        # Beat-cut: positive and half-beat-shifted negative
        info = B.beatcut(film, "music", ["g1", "g2", "g3", "g4"], film / "edit/beat.otio", beats_per_cut=2,
                         duration_s=12)
        period = info["grid"]["period_s"]
        ok("P5 music grid reads 120 BPM", abs(info["grid"]["bpm"] - 120) < 1, f"{info['grid']['bpm']:.2f}")
        R.render(film, film / "edit/beat.otio", film / "build/beat.mp4", size="640x360")
        v = B.verify(film / "build/beat.mp4", declared=info["declared_cuts_s"])
        expect = len(info["declared_cuts_s"])
        ok("P6 beat-cut film: detected cuts within 1 frame of the beat (median), recall >= 0.9",
           v["recall"] >= 0.9 and v["median_abs_ms"] is not None and v["median_abs_ms"] <= v["frame_ms"] + 1,
           f"{v['detector']} n={v['n_cuts']}/{expect} recall={v['recall']:.2f} median_abs={v['median_abs_ms']} ms")
        B.beatcut(film, "music", ["g1", "g2", "g3", "g4"], film / "edit/shift.otio", beats_per_cut=2, duration_s=12,
                  shift_s=period / 2)
        R.render(film, film / "edit/shift.otio", film / "build/shift.mp4", size="640x360")
        tl = E.new("one", 30)
        E.add_clip(tl, film, "g1", 0, 120)
        E.set_music(tl, film, "music", 0, 120)
        E.save(tl, film / "edit/one.otio")
        R.render(film, film / "edit/one.otio", film / "build/one.mp4", size="640x360", check=False)
        z = B.verify(film / "build/one.mp4", declared=[1.0, 2.0, 3.0])
        ok("N6 a film with no cuts cannot pass on declared cuts (recall stays low)", z["recall"] < 0.5,
           f"{z['detector']} recall={z['recall']:.2f}")
        w = B.verify(film / "build/shift.mp4")
        ok("N5 half-beat-shifted control reads far off the beat (>= 0.4 period)",
           w["n_cuts"] >= expect - 2 and w["median_abs_ms"] is not None and w["median_abs_ms"] >= 400 * period,
           f"n={w['n_cuts']} median_abs={w['median_abs_ms']} ms")
    comfy_controls()
    bad = [n for n, c in RESULTS if not c]
    print(f"{len(RESULTS) - len(bad)}/{len(RESULTS)} controls hold" + (f"; failing: {bad}" if bad else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

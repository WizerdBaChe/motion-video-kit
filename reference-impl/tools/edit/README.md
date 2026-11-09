# tools/edit — the edit route

Footage and generated assets -> an OpenTimelineIO edit decision list -> ffmpeg -> filmkit check. Design and the user ruling
behind it: `docs/edit-route-design.md`. Code-rendered pages still go through `tools/filmkit/render.py`; a rendered page
enters an edit as an asset with `source: motion`.

Dependency: `opentimelineio==0.18.1` (pip). ffmpeg/ffprobe on PATH (same as filmkit).

## Film folder

```
<film>/assets/<id>.<ext>               media (video, image, audio)
<film>/assets/<id>.provenance.json     sha256, source, created_at, made_by + per-source keys (assets.py BY_SOURCE)
<film>/edit/<name>.otio                EDL: V1 clips/gaps, A1 one music clip, integer frames
<film>/build/<name>.mp4                render output, plus <name>.mp4.edit.json and filmkit check.*
```

## Gates

- `register` refuses an incomplete provenance record and leaves no file behind; it never overwrites an id.
- `render` runs `edl.plan` first: every asset must verify (file present, sha256 unchanged, generation inputs unchanged),
  times must be whole frames at the timeline rate, no transitions (v1), and a video clip's range must fit its source.
  Any problem refuses before ffmpeg starts.
- `render` then runs `tools/filmkit/check.py` with the EDL's own duration, size, fps and audio expectation.

## Beat-cut

`beatcut` reads the music's grid with `tools/beatgrid.py`'s estimator and cuts every N beats; `verify-beat` measures a
rendered film's cuts against its audio grid (`beatgrid.analyse`, limits in its output). Selftest: a 120 BPM synthetic
track reads 120.01 BPM; cuts read 12/12 at median 12.9 ms (1 frame = 33.3 ms); the half-beat-shifted control reads
246 ms. The ~13 ms constant offset is unexplained (candidates: AAC priming, onset hop 11.6 ms); it is inside one frame.
scdet misses cuts between stills of one palette (ComfyUI pastel stills: 0 of 7); with `--edl` the declared cuts are
known, and below 80 % scdet recall the verifier switches to motion onsets (7 of 7, median 11.2 ms) and says so in
`detector`. `recall` (declared cuts with an event within 2 frames) keeps a blind detector from passing (control N6).

## Limits (v1)

Hard cuts only; one music clip; no overlays, titles or transitions; stills are held, not animated. The check states
facts and never judges pictures (INV-6).

## Adapters

- `mock`: deterministic colour clip with a moving bar (tests).
- `comfyui`: local ComfyUI HTTP API (checked on 0.25.1). Workflow = API-format graph in `comfy/*.api.json` with
  `$prompt $seed $width $height $prefix` placeholders; default `flux2_klein_4b_t2i.api.json` (FLUX.2 klein 4B
  distilled, 4 steps, built from the user's own Klein workflow's subgraph). Images only: no video model is installed.
  About 8 s per 1280x720 image on the RTX 5070 laptop GPU after a 27 s first load. Start the server with
  `<ComfyUI portable folder>/python_embeded/python.exe -s ComfyUI/main.py --windows-standalone-build --listen 127.0.0.1 --port 8188 --disable-auto-launch`
  (from that folder). Provenance records the graph's sha256, every loader's file, the ComfyUI version and the device.

## Controls

`python -X utf8 tools/edit/selftest.py` (17 controls, about 90 s): positive and negative for the provenance gate,
tamper detection, exact frame count, missing provenance, source-range overrun, beat alignment, cut recall, the
ComfyUI graph; P8 generates one real image and is printed `[skip]` when the server is not running.

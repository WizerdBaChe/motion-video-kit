"""Generation adapters (docs/edit-route-design.md §2.3): generate(request) -> registered asset + provenance.

An adapter only produces a media file and the provider facts; registration (hash, provenance gate) is shared here, so
no adapter can land an asset without provenance. Adapters: `mock` (deterministic synthetic clip, for tests). ComfyUI
is P3.
"""
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from assets import register, load


@dataclass
class Request:
    asset_id: str
    prompt: str
    kind: str = "video"            # video | image
    seconds: float = 2.0
    size: str = "1280x720"
    fps: int = 30
    seed: int | None = None
    negative_prompt: str = ""
    params: dict = field(default_factory=dict)
    inputs: list = field(default_factory=list)   # asset ids this generation conditions on (image-to-video etc.)


class Adapter:
    name = "base"
    version = "0"
    provider = ""

    def produce(self, req: Request, workdir: Path) -> dict:
        """Write the media into workdir; return {"path", "model", "job_id", "cost", "params"}."""
        raise NotImplementedError

    def generate(self, film, req: Request) -> dict:
        film = Path(film)
        inputs = [{"id": i, "file": load(film, i)["file"], "sha256": load(film, i)["sha256"]} for i in req.inputs]
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
            out = self.produce(req, Path(td))
            return register(film, out["path"], req.asset_id, "generated", {
                "provider": self.provider, "model": out["model"], "prompt": req.prompt,
                "negative_prompt": req.negative_prompt, "seed": req.seed, "params": out.get("params", req.params),
                "cost": out.get("cost"), "job_id": out.get("job_id"), "adapter": self.name,
                "adapter_version": self.version, "inputs": inputs}, made_by=f"tools/edit/adapters.py:{self.name}",
                move=True)


class MockAdapter(Adapter):
    """A solid colour picked from the seed with a moving bar, so cuts between two mock clips are detectable."""
    name, version, provider = "mock", "1", "local-mock"

    def produce(self, req, workdir):
        seed = 0 if req.seed is None else int(req.seed)
        hue = (seed * 67) % 360
        r, g, b = _hsv(hue, 0.7, 0.9 if seed % 2 else 0.35)   # odd/even seeds differ in luma: scdet reads luma
        color = f"0x{r:02x}{g:02x}{b:02x}"
        w, h = req.size.split("x")
        if req.kind == "image":
            out = workdir / f"{req.asset_id}.png"
            vf = f"color=c={color}:s={req.size}:d=1"
            cmd = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", vf, "-frames:v", "1", str(out)]
        else:
            out = workdir / f"{req.asset_id}.mp4"
            src = f"color=c={color}:s={req.size}:r={req.fps}:d={req.seconds}"
            vf = f"drawbox=x='mod(t*{int(w)//2},{w})':y={int(h)//3}:w={int(w)//10}:h={int(h)//3}:color=white@0.8:t=fill"
            cmd = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", src, "-vf", vf, "-c:v", "libx264",
                   "-pix_fmt", "yuv420p", str(out)]
        subprocess.run(cmd, check=True)
        return {"path": out, "model": "mock-colour-bar-v1", "job_id": f"mock-{req.asset_id}-{seed}",
                "cost": {"amount": 0, "unit": "USD"}, "params": {"hue": hue, **req.params}}


class ComfyUIAdapter(Adapter):
    """Local ComfyUI over its HTTP API (/prompt, /history/{id}, /view, /system_stats; checked on 0.25.1).

    The workflow is an API-format graph (tools/edit/comfy/*.api.json) whose string values `$prompt`, `$seed`,
    `$width`, `$height`, `$prefix` are substituted; `$seed` etc. become integers. Images only in v1 (no video model is
    installed on this machine). The graph's sha256 and every loader's model file go into provenance.
    """
    name, version, provider = "comfyui", "1", "comfyui-local"

    def __init__(self, base="http://127.0.0.1:8188", workflow=None, timeout_s=600):
        self.base = base.rstrip("/")
        self.workflow = Path(workflow or Path(__file__).parent / "comfy/flux2_klein_4b_t2i.api.json")
        self.timeout_s = timeout_s

    def _get(self, path):
        import json
        import urllib.request
        with urllib.request.urlopen(self.base + path, timeout=30) as r:
            body = r.read()
        return json.loads(body) if path.split("?")[0] not in ("/view",) else body

    def graph(self, req):
        import json
        if req.kind != "image":
            raise ValueError("comfyui adapter v1 makes images only (no video model installed)")
        w, h = (int(x) for x in req.size.split("x"))
        seed = 0 if req.seed is None else int(req.seed)
        subst = {"$prompt": req.prompt, "$seed": seed, "$width": w, "$height": h, "$prefix": f"mvl_{req.asset_id}"}
        g = json.loads(self.workflow.read_text(encoding="utf-8"))
        for node in g.values():
            for k, v in node["inputs"].items():
                if isinstance(v, str) and v in subst:
                    node["inputs"][k] = subst[v]
        return g

    def produce(self, req, workdir):
        import hashlib
        import json
        import time
        import urllib.parse
        import urllib.request
        g = self.graph(req)
        stats = self._get("/system_stats")
        body = json.dumps({"prompt": g, "client_id": "mvl-edit"}).encode("utf-8")
        t0 = time.time()
        with urllib.request.urlopen(urllib.request.Request(self.base + "/prompt", data=body,
                                                           headers={"Content-Type": "application/json"}), timeout=30) as r:
            pid = json.loads(r.read())["prompt_id"]
        while True:
            h = self._get(f"/history/{pid}")
            if pid in h:
                h = h[pid]
                break
            if time.time() - t0 > self.timeout_s:
                raise TimeoutError(f"ComfyUI job {pid} not done after {self.timeout_s} s")
            time.sleep(1)
        st = h.get("status", {})
        if st.get("status_str") not in (None, "success"):
            raise RuntimeError(f"ComfyUI job {pid}: {st.get('status_str')} {st.get('messages', [])[-1:]}")
        imgs = [im for o in h["outputs"].values() for im in o.get("images", []) if im.get("type") == "output"]
        if not imgs:
            raise RuntimeError(f"ComfyUI job {pid} produced no output image")
        im = imgs[0]
        q = urllib.parse.urlencode({"filename": im["filename"], "subfolder": im["subfolder"], "type": "output"})
        out = workdir / f"{req.asset_id}.png"
        out.write_bytes(self._get(f"/view?{q}"))
        loaders = {n["class_type"]: {k: v for k, v in n["inputs"].items() if not isinstance(v, list)}
                   for n in g.values() if n["class_type"].endswith("Loader")}
        unet = loaders.get("UNETLoader", {}).get("unet_name") or loaders.get("CheckpointLoaderSimple", {}).get("ckpt_name")
        return {"path": out, "model": unet or "unknown", "job_id": pid,
                "cost": {"amount": 0, "unit": "USD", "local_gpu_seconds": round(time.time() - t0, 1)},
                "params": {"workflow": self.workflow.name,
                           "workflow_sha256": hashlib.sha256(self.workflow.read_bytes()).hexdigest(),
                           "loaders": loaders, "size": req.size,
                           "comfyui_version": stats["system"].get("comfyui_version"),
                           "device": stats["devices"][0].get("name") if stats.get("devices") else None, **req.params}}


def _hsv(h, s, v):
    import colorsys
    r, g, b = colorsys.hsv_to_rgb(h / 360, s, v)
    return int(r * 255), int(g * 255), int(b * 255)


ADAPTERS = {"mock": MockAdapter, "comfyui": ComfyUIAdapter}

# reflib_core

The Reference Library engine as a plain Python package: **no Gradio and no WanGP imports**. The WanGP plugin is a
thin adapter around it (UI, the "WanGP is generating" check, the Reference Images hand-off). A standalone app (Qt,
FastAPI, a CLI…) reuses it the same way.

```python
import reflib_core
reflib_core.configure("/path/to/data")                 # every store under one folder (see FORMAT.md)
from reflib_core import storage, imagelib, videostore, api
from reflib_core.autotag import AutoTagService

storage.create_collection("Refs", [("a.jpg", "a.jpg")])
imagelib.add_folder("D:/Fotos/refs", recursive=True)    # read-only index
svc = AutoTagService("/path/to/data", busy=lambda: my_gpu_is_busy())
svc.save_settings({"model": "wd+qwen"})
svc.enqueue(imagelib.resolve_selection({"all": True, "f": {}}))
svc.queue.wait()
imagelib.query({"q": "pelo corto"}, 0, 50)              # synonyms + hierarchy, EN/ES
imagelib.query({"q": "ratio cintura/cadera<0.72"}, 0, 50)
```

Modules: `storage` (collections), `videostore`, `imagestore` (crops), `imagelib` (pool, watched folders, catalog,
server-side query / Recent / facets / selection, thumbnails), `api` (versioned public API used by other plugins),
`media` (ffmpeg helpers; set `media.BINARY_RESOLVER` to provide binaries), `taxonomy` (+ `taxonomy.json`),
`tagstore` (`autotags.json`), `backends` (fake, WD, Qwen2.5-VL, Jev, OpenAI-compatible, Gemini, Grok, OpenRouter),
`bodyshape` (silhouette measurement), `jobs` (background queue), `autotag` (service facade).

CLI (proves it runs without WanGP):

```
python -m reflib_core --data ./data tag ./pics --model fake      # or wd, qwen, wd+qwen, jev, …
python -m reflib_core --data ./data search "reloj de arena"
python -m reflib_core --data ./data search "90-60-90 ±5"
python -m reflib_core --data ./data show <hash>
python -m reflib_core taxonomy --lang es
```

Requirements: see `requirements.txt` (Pillow only for the library; per-backend extras for the tagger).

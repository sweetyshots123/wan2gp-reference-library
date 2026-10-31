# Similarity search API (pose + face)

Module: `reflib_core/similarity.py` (service), `reflib_core/posesim.py` (scoring),
`reflib_core/simworker.py` (model worker, separate Python env). UI: `reflib_similarity.js`.
Registered shared actions (`reflib_core/actions.py`, listed in `actions_all.py`); both UIs call them through `POST /reflib/api` (`{"action": "...", ...}`), are read-only
for the library and never send data off the machine.

## Actions
| action | request | response |
|---|---|---|
| `sim_status` | – | `{ok, sim:{running, done, total, paused, waiting, download:{file,done,total}?, index:{images, persons, faces, faces_pending, face_model}, library, face_model (in use), face_model_setting, face_fallback, face_models:[{id,label,license,mb,downloaded,images}]}}` |
| `sim_info` | – | models, licenses, paths, settings |
| `sim_index` | `{all?:bool, hashes?, force?:bool, faces_only?:bool}` | starts / extends the background job; `faces_only` = "Calcular caras" for the selected face model |
| `sim_settings` | `{settings?:{face_model:"arcface"\|"glintr100"\|"adaface"\|"sface", gpu, auto, ...}}` | switching face model keeps other models' vectors and queues faces-only re-index |
| `sim_pause` / `sim_resume` / `sim_stop` | – | job control |
| `sim_search` | `{hashes?:[..≤50], files?:[{name, data(base64)}], mode:"pose"\|"face"\|"both", weight:0..1 (pose share in both), threshold:0..1, combine:"any"\|"avg", mirror:bool}` | `{ok, sid, count}` or `{ok:false, error:"no_query"\|...}` |

## Using results
Pass the returned `sid` as filter `{sim: sid}` to `query`. Only scored items are returned; with
`sort:""` (or `"sim"`) they are ordered by score; each page item carries `sim` (0..1). Any other
sort key works on the result set.

## Storage
`data/similarity/` – `pose.npz`, `face-<model>.npz` (per-vector model id), `meta.json`, `worker.log`.
Settings: `similarity/settings.json` (`models_dir`, `python`, `workers` 0=auto decode threads (2–4), 1=sequential), env `REFLIB_SIM_PYTHON`.



## Face records (Personas / multi-face) — 1.9.6-simperf

Each indexed image may have **multiple faces** per face model. Search still takes the
best-matching face per image; Personas clustering (`reflib_core/faces.py`) uses every face.

### On-disk (`data/similarity/face-<model>.npz`)
| array | shape | notes |
|---|---|---|
| `keys` | (N,) str | item hashes |
| `owner` | (F,) int32 | index into `keys` |
| `vec` | (F, D) float16 | L2-normalised embedding (D=512 ArcFace/…, 128 SFace) |
| `model` | (F,) str | face model id (must match the file) |
| `box` | (F, 4) float32 | **optional**; xywh normalised to 0..1. Missing in older files → treat as unknown |
| `det` | (F,) float32 | **optional**; detector score. Missing → unknown |

Face index within an item is the **row order** among rows with the same `owner` (0 = first face).
A legacy single-face entry loads as `face_i=0` with `box`/`det` = null (NaN on disk).

### In-memory pack
`items[hash]["faces"][model] = {"vec": (n,D) f16, "box": (n,4) f32, "det": (n,) f32}`.
`SimIndex.face(hash)` still returns the bare `vec` matrix for search compatibility.

### Internal Python API (for `reflib_core/faces.py`)
```python
# From a SimService (or SimIndex directly):
m = service.face_matrix()            # or face_matrix("arcface")
# m["ids"] (F,) str, m["face_i"] (F,) i32, m["vec"] (F,D) f32,
# m["box"] (F,4) f32 (NaN if unknown), m["det"] (F,) f32, m["model"] str

unsub = service.on_faces(callback)   # callback([{id, face_i, model, box, det, emb}, ...])
# Fired after each successful put() that wrote faces; box is [x,y,w,h] in 0..1 or None.
unsub()
```

Index format remains forward-compatible with a run started on 1.9.6 / 1.9.1: new builds
read existing `pose.npz` + `face-*.npz` + `meta.json` and resume without reindex. After the
first save under simperf, `box`/`det` arrays appear on newly written face npz files;
rows for images indexed before the upgrade keep NaN bbox until recomputed.

## Models (see README "Similarity models" for the full table incl. glintr100 / AdaFace, 261 MB each, research-only)
| file | size | license |
|---|---|---|
| yolox_l.onnx (person detector) | 217 MB | Apache-2.0 |
| dw-ll_ucoco_384.onnx (DWPose) | 134 MB | Apache-2.0 (reused from WanGP `ckpts/pose`) |
| yunet.onnx (face detector) | 0.23 MB | MIT |
| sface.onnx (default face embedding) | 38.7 MB | Apache-2.0 |
| buffalo_l/w600k_r50.onnx (ArcFace, optional) | 174 MB | **non-commercial research only** |

## UI extension points (reference_library.js `extend({...})`)
`ctx`, `details`, `selbar` (html), `chips`, `clear`, `act`, `navLabel`.

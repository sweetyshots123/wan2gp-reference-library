# Similarity search API (pose + face) — 1.12.0-videofaces

Module: `reflib_core/similarity.py` (service), `reflib_core/posesim.py` (scoring),
`reflib_core/simworker.py` (model worker, separate Python env). UI: `reflib_similarity.js`.
Registered shared actions (`reflib_core/actions.py`, listed in `actions_all.py`); both UIs call them through `POST /reflib/api` (`{"action": "...", ...}`), are read-only
for the library and never send data off the machine.

## Actions
| action | request | response |
|---|---|---|
| `sim_status` | – | `{ok, sim:{running, done, total, paused, waiting, download:{file,done,total}?, index:{images, videos, persons, faces, faces_pending, face_model}, library, library_videos, videos_done, per_video_ms, video_frames, face_model (in use), face_model_setting, face_fallback, face_models:[{id,label,license,mb,downloaded,images}]}}` |
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
| `t` | (F,) float32 | **optional** (1.12.0); seconds into the source video. NaN for stills / legacy |

Face index within an item is the **row order** among rows with the same `owner` (0 = first face).
A legacy single-face entry loads as `face_i=0` with `box`/`det` = null (NaN on disk).

### In-memory pack
`items[hash]["faces"][model] = {"vec": (n,D) f16, "box": (n,4) f32, "det": (n,) f32, "t": (n,) f32?}`. Video items also store `kind:"video"`, fingerprint `v` (mtime+sampling params), and optional pose times `pt`.
`SimIndex.face(hash)` still returns the bare `vec` matrix for search compatibility.

### Internal Python API (for `reflib_core/faces.py`)
```python
# From a SimService (or SimIndex directly):
m = service.face_matrix()            # or face_matrix("arcface")
# m["ids"] (F,) str, m["face_i"] (F,) i32, m["vec"] (F,D) f32,
# m["box"] (F,4) f32 (NaN if unknown), m["det"] (F,) f32, m["t"] (F,) f32 (NaN if still/legacy), m["model"] str

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


## Video (1.12.0-videofaces)

`kind=video` library items are indexed when `index_videos` is true (default). Sampling and aggregation
live in `reflib_core/videosim.py` + `SimService.analyse_video`.

### Settings (`similarity/settings.json`)
| key | default | meaning |
|---|---|---|
| `index_videos` | true | include videos in `sim_index` / search corpus |
| `video_interval_s` | 2.0 | sample one frame every N seconds |
| `video_scene_detect` | true | also sample at cheap HSV-histogram scene cuts |
| `video_max_frames` | 60 | hard cap of frames per video |
| `video_merge_gap_s` | 4.0 | merge nearby match times into one segment in search / Personas |

### Pipeline
1. `cv2.VideoCapture` decodes (opencv-python-headless in the sim venv). If the codec fails, fall back to
   `ffmpeg` on PATH / WanGP; else skip with a warning.
2. Frames (JPEG) go through the existing workers / prefetch / batched `analyse` path.
3. Face (and pose) records from each frame get `t` (seconds). All faces of one video share the video's
   item hash; `face_i` runs across the whole video.
4. Incremental cache: item meta `v = {mtime, interval_s, scene, max_frames}` — unchanged fingerprint ⇒ skip.
   Job is resumable like image indexing.
5. Pose on the same sampled frames is stored with parallel `pt` on the item (cheap; same sampling). If
   pose models are disabled, video pose is simply absent — no separate video-pose path.

### Search / query page
`sim_search` scores videos as **one row per video** (max over its faces/poses). Each hit may carry:
* `kind: "video"`
* `best_t` — timestamp of the best matching frame
* `segments: [{t0, t1}, …]` — nearby match times merged by `video_merge_gap_s`

`query` with `{sim: sid}` attaches `best_t` / `segments` onto page items via `imagelib.SIMILARITY_ROW`.

### Status
`sim_status.sim` adds `library_videos`, `videos_done`, `per_video_ms`, `video_frames`; `index.videos` counts
indexed videos. Existing fields keep their meaning.

### UI
`reflib_similarity.js`: videos are valid "Find similar" sources; result details show timestamp chips that
seek the Media Library preview to that `t`. Cards show a small ⏱ chip when `best_t` is present. EN/ES + dark mode.

# Personas / face clustering API (1.12.0-videofaces)

Module: `reflib_core/faces.py` (numpy only), registered in `actions_all.py`. UIs: Media Library `reflib_faces.js`,
Galería "Personas" page (gg). Both call the same actions through `ilib` / `POST /reflib/api` (`{"action": ..., lang, ...}`).
Input = the face embeddings of `sim_index` (`data/similarity/face-<model>.npz`, see `SIMILARITY_API.md`). Nothing ever
leaves the PC; no face data is uploaded, logged remotely or exported in collection zips.

## Ids
* **face id** `"<item_hash>:<n>@<model>"`, e.g. `"3fa9…c1:0@arcface"`; `n` = row of that face inside the item's vectors
  for `model` (0-based, the worker's order). Stable as long as the item is not re-indexed with `force` for that model
  (see "Re-index" below).
* **person id** `"p_<12 hex>"` (random, never reused). The person's **tag** is `persona:<Nombre>` on every item that has
  at least one face assigned to it (existing persona tag convention, so filters / `tag_rename` keep working).
* **cluster id** `"c_<12 hex>"`; clusters are only for *unnamed, unassigned* faces of the *active* model and are a
  rebuildable cache: ids are stable across incremental runs but may change after a full `face_cluster_run {full:true}`.

## Face model switch
Assignments, rejections and covers are stored **per model**. Switching `sim_settings.face_model`:
* persons (names, tags) are global and stay; each person keeps the faces it had for each model;
* the active model's assigned faces are the person's "seeds"; if a person has none for the new model, `faces.py`
  seeds it automatically from faces of the new model on items that carry its tag and have exactly one face
  (`seeded: true` in person_list), never overriding a manual assignment;
* clusters and suggestions are recomputed for the new model (new `clusters-<model>.json`); the old model's files stay.

## Settings (`similarity/settings.json`, merged, unknown keys preserved)
`face_auto_cluster` (default true: new faces reported by simperf's `on_faces()` are grouped automatically by a
debounced incremental run ~4 s after the last batch), `face_cluster_threshold` cosine 0..1 (default per model: arcface 0.42, glintr100 0.40, adaface 0.40, sface 0.50),
`face_suggest_threshold` (default threshold − 0.05), `face_min_cluster` (default 2), `face_min_size` px (default 40;
smaller faces are skipped when bbox is known). Change via `face_settings`.
Quality gate (facequality): `face_q_min_det` 0.80, `face_q_min_blur` 25 (variance of Laplacian on the aligned crop),
`face_q_max_yaw` 0.60 (landmark yaw proxy 0..1), `face_q_skip_trunc` true (bbox > 50 % outside the image).
Strict clustering: `face_link_k` 3, `face_link_margin` 0.05. Suggestions: `face_proto_k` 4 prototypes,
`face_suggest_margin` 0.05.

### Face record fields (facequality)
Every FACE object also carries `quality:{score 0..1, ok:bool, flags:[low_det|small|blurry|profile|truncated]}` and
`aligned` (1 = legacy LMEDS partial-affine, 2 = umeyama similarity, null = unknown/indexed before facequality).
Low-quality faces (`ok:false`) are NOT clustered, NOT used for centroids/prototypes and NOT suggested, but stay
searchable, assignable by hand and visible (flagged). Faces indexed before facequality have unknown quality → ok.
The sim index `face-<model>.npz` gains an optional `q` array (n×4: blur, yaw, trunc, aligned; NaN = unknown).

## Actions
| action | request | response |
|---|---|---|
| `face_status` (fast) | – | `{ok, faces:{model, running, done, total, faces, unassigned, clusters, persons, rev, threshold}}` |
| `face_cluster_run` | `{full?:bool, threshold?:float}` | `{ok, job:true, faces:{…status}}`; incremental by default (only faces not yet seen), `full` re-clusters all unassigned faces of the active model |
| `face_clusters` (fast) | `{offset=0, limit=50, min_size?, faces_per=6}` | `{ok, total, clusters:[{id, size, cover:FACE, faces:[FACE…≤faces_per]}]}` sorted by size desc |
| `face_cluster_faces` (fast) | `{cluster, offset, limit}` | `{ok, total, faces:[FACE]}` |
| `face_for_item` (fast) | `{hash}` or `{hashes:[≤200]}` | `{ok, items:{hash:{w, h, model, faces:[FACE]}}}` |
| `face_assign` | `{person?:pid, name?:str, clusters?:[cid], faces?:[fid]}` | `{ok, person:PERSON, assigned:n, hashes:[…]}` + meta; creates the person when only `name` is given (or reuses one with the same folded name); adds `persona:<Nombre>` to items |
| `face_unassign` | `{faces:[fid]}` | `{ok, n, hashes}`; removes the tag from items left with no face of that person (manual tags on items without detected faces are kept) |
| `face_suggest` (fast) | `{person, method:"proto"\|"centroid"\|"nn"="proto", limit=40, threshold?}` | `{ok, person, faces:[FACE+{score, margin}]}` ranked by margin then score; only good-quality candidates; never rejected faces, never faces assigned to anyone |
| `face_recompute` | `{hashes?:[hash]}` (default: whole library) | `{ok, remap_items, …enqueue result}` re-indexes faces (new alignment + quality) with `force, faces_only`; person assignments/rejections are carried to the new face rows by bbox IoU ≥ 0.5 |
| `face_confirm` | `{person, faces:[fid]}` | = `face_assign` |
| `face_reject` | `{person, faces:[fid]}` | `{ok, n}`; remembered per person+model, never suggested again |
| `face_unreject` | `{person, faces?:[fid]}` | `{ok, n}`; all if `faces` omitted |
| `person_review` (1.11.1) | `{person, accept:[fid], reject:[fid]}` | batch review of suggestions = `face_confirm(accept)` + `face_reject(reject)` (reject wins); `{ok, assigned, accepted, rejected, n_rejected}`. Undo: `face_unassign(accept)` + `face_unreject(person, reject)` |
| `face_merge` | `{clusters:[cid≥2]}` or `{persons:[pid≥2], into:pid}` | `{ok, cluster:id}` / `{ok, person:PERSON}` (tags renamed via `tag_rename` logic) |
| `face_split` | `{cluster, faces:[fid]}` or `{person, faces:[fid]}` | `{ok, cluster:new_cid}`; for a person the faces become unassigned and go to a new cluster |
| `person_list` (fast) | `{offset=0, limit=200}` | `{ok, total, persons:[PERSON]}` sorted by count desc |
| `person_get` (fast) | `{person, offset, limit}` | `{ok, person:PERSON, faces:[FACE]}` |
| `person_rename` | `{person, name}` | `{ok, person}`; renames the tag everywhere (merges if the name exists → persons merged) |
| `person_delete` | `{person, keep_tag?:false}` | `{ok, undo_token}`; forgets the person and its assignments/rejections, removes the tag unless `keep_tag`. **Never deletes images.** |
| `person_undo_delete` | `{undo_token}` | 5 min |
| `person_set_cover` | `{person, face}` | `{ok, person}` |
| `face_settings` | `{settings?:{face_cluster_threshold, …}}` | `{ok, settings}` |
| `face_thumb` (fast) | `{id}` or `{hash, n, model?}` (+ `size=160` 32–1024, `margin=0.4` 0–2, `data?:bool`) | `{ok, id, url, data?:"data:image/jpeg;base64,…"}`; `face_not_found` when the id is bad or no source file is readable |

FACE = `{id, hash, n, model, box:[x,y,w,h]|null (0..1 of the image, simperf face record), bbox:[x,y,w,h]|null (= box in
pixels of the indexed image, null when w/h unknown), w, h, score?, person?:pid,
cluster?:cid, thumb:url}` — `thumb` is the shared face-thumbnail URL (see below), used by both the Media Library and the Galería. `box`/`bbox` come from simperf's face records
(SIMILARITY_API.md "Face records"); legacy rows (indexed before simperf) have `box:null` until recomputed. UIs draw
overlays from `box`.

### Data source (simperf 9b0ed21)
`faces.py` reads `SimService.face_matrix(model)` (ids, face_i, vec, box, det) — face id = `<ids[k]>:<face_i[k]>@<model>`
— cached per `SimIndex.rev`, and the per-item pack `items[h]["faces"][model] = {vec, box, det}` for one item's boxes.
It subscribes to `SimService.on_faces(cb)`: on each batch it drops assignments/rejections that point past a
re-indexed item's new face count and schedules the incremental clustering above.

### Face thumbnails (shared URL)
`GET /reflib/face_thumb/<urlencoded face id>.jpg?size=160&margin=0.4` (gallery_routes.py, same FastAPI router and
WanGP login check as `/reflib/api`), e.g. `/reflib/face_thumb/9f..e1%3A0%40arcface.jpg?size=160&margin=0.4`.
Square JPEG: `box` (0..1, scaled to the actual source file) enlarged by `margin` (0.4 = 40 % larger side), centred on the face, clamped to the image, resized to
`size`. No bbox (older index) → centred square of the whole image. 404 when there's no readable source.
Cache: `data/faces/thumbs/<hash>_<n>_<model>_<size>_<margin×100>_<source mtime>[_full].jpg`. A changed source (new mtime)
makes a new file and removes older variants for that face and size. The cache can be deleted at any time.
Built by `faces.thumb_url(fid, size, margin)`; the file comes from `faces.face_thumb_path(...)`.
PERSON = `{id, name, tag, count (faces, active model), items, cover:FACE|null, seeded?:bool}`.



## Video (1.12.0-videofaces)

Face search and Personas also cover library items with `kind=video`. Indexing samples frames
(see SIMILARITY_API.md "Video"); each detected face is stored with the same pack shape as stills
plus an optional timestamp.

### Face id / record
* Face id stays `"<video_hash>:<face_i>@<model>"`. `face_i` is unique across all sampled frames of that
  video (row order in the face npz for that hash), not reset per frame.
* FACE gains optional fields when the source is a video:
  * `kind: "video"` (stills keep `"image"` / omit for legacy)
  * `t: float` — seconds of the sampled frame where this face was detected
  * On list endpoints that dedupe per video: `best_t` (timestamp of the best-scoring face) and
    `segments: [{t0, t1}, …]` (nearby match times merged with gap `video_merge_gap_s`, default 4 s)

Image FACE records are unchanged; older clients that ignore unknown keys stay compatible.

### Deduped list endpoints
`face_suggest`, `face_clusters` (preview faces), `face_cluster_faces`, and `person_get` return **at most
one FACE per video hash**. Multiple frame hits become `best_t` + `segments`. Still images are never
merged. Assign / confirm / reject still take individual face ids (including video faces); the
`persona:<Nombre>` tag is applied to the **video item** hash, same as images.

### Face thumbnails for video faces
`face_thumb` seeks the source video to `t` (cv2, ffmpeg fallback), crops the bbox (+ margin) from that
frame, and caches under
`data/faces/thumbs/<hash>_<n>_<model>_<size>_<margin×100>_<mtime>_t<t>.jpg`. Stills keep the previous
key (no `_t…` suffix).

### UI
Media Library (`reflib_faces.js`): video faces show a 🎬 badge and timestamp chip(s); click opens the
library preview and seeks to `best_t` / the chip's `t`. EN + ES strings; chips readable in dark mode.

### Examples
```json
{"action":"face_clusters","limit":2,"faces_per":2}
{"ok":true,"total":37,"clusters":[{"id":"c_1a2b3c4d5e6f","size":58,
 "cover":{"id":"9f..e1:0@arcface","hash":"9f..e1","n":0,"model":"arcface","bbox":[412,96,180,214],"w":1024,"h":1536},
 "faces":[{"id":"9f..e1:0@arcface", "...": "..."}]}]}

{"action":"face_assign","name":"Lucía","clusters":["c_1a2b3c4d5e6f"]}
{"ok":true,"message":"58 caras asignadas a Lucía","person":{"id":"p_7c0d1e2f3a4b","name":"Lucía","tag":"persona:Lucía","count":58,"items":55,"cover":{"...":"..."}},"assigned":58,"hashes":["9f..e1","..."]}

{"action":"face_suggest","person":"p_7c0d1e2f3a4b","limit":1}
{"ok":true,"person":"p_7c0d1e2f3a4b","faces":[{"id":"a0..77:1@arcface","score":0.61,"bbox":[30,40,90,110],"...":"..."}]}

{"action":"face_reject","person":"p_7c0d1e2f3a4b","faces":["a0..77:1@arcface"]}
{"ok":true,"n":1}
```

### Errors (`{ok:false, error:<translated text>, code:<key>, ...}`, translated by faces.py `FACE_TEXT` EN/ES)
`faces_no_index` (no face vectors for the active model → run "Calcular caras"), `faces_busy` (a clustering job is running: every write — assign/confirm/unassign/reject/unreject/merge/split/
person_rename/delete/undo_delete/set_cover/face_settings — is refused instead of waiting on the lock; `face_cluster_run` too), `face_not_found` (`face`: the bad face id), `cluster_not_found`, `person_not_found`, `person_need_name`,
`faces_model_mismatch` (face id of another model than the active one), `faces_need_two` (merge), `undo_expired`.

## Storage (`data/faces/`, new files only, atomic tmp+replace, never touches existing library files)
* `persons.json` — `{version:1, persons:{pid:{name, created, cover:{model:fid}}}, assign:{model:{fid:pid}},
  reject:{model:{pid:[fid]}}}` (source of truth; a `.bak` of the previous version is kept on each write).
* `clusters-<model>.json` — `{version:1, threshold, seen:[fid], clusters:{cid:{faces:[fid]}}}` (cache; deleting it
  only loses unnamed grouping).
* `thumbs/` — face thumbnail cache (see Face thumbnails; disposable).
* Centroids are recomputed in memory (L2-normalised mean of a person's faces).

## Re-index
Face ids are row positions (`face_i`). When an item is re-indexed (`on_faces` batch), assignments/rejections whose
`face_i` is past the new face count are dropped; the others are kept by position. Faces not yet seen are clustered by
the next incremental run. `face_recompute` snapshots the bbox of every assigned/rejected face in `persons.json`
`remap:{model:{hash:{face_i:bbox}}}`; when the item comes back, old rows are matched to new rows by greedy bbox IoU ≥ 0.5
(unmatched → assignment dropped) before the stale check.
Items removed from the library drop their faces (tags go with the item).

## Algorithm
Strict (no-chaining) clustering, cosine on L2-normalised float32, good-quality faces only: a face joins the best
cluster whose centroid is ≥ threshold AND which has min(`face_link_k`, size) members ≥ threshold − `face_link_margin`;
else it starts a new cluster. Clusters then merge only by average linkage ≥ threshold (not centroid-to-centroid, so
A–bridge–B chains do not form). Cluster ids are kept from the largest previous cluster a group contains.
Incremental: only faces not in `seen`. Suggestions: `proto` = max cosine to the person's prototypes (centroid +
k-means of confirmed good faces), `nn` = max cosine to confirmed faces, `centroid` = centroid only; margin = score −
max(cosine to this person's rejected faces, to other persons' prototypes). Kept when score ≥ `face_suggest_threshold`
and margin ≥ `face_suggest_margin`.
Alignment: 5-point umeyama similarity to the ArcFace template (was cv2 estimateAffinePartial2D/LMEDS).

## 1.12.2-faces: videos in suggestions / review
* `face_suggest` / `person_get` video entries (deduped, one per video) carry `ids:[fid]` = every frame face merged
  into the entry. `person_review`, `face_assign`, `face_confirm` and `face_reject` expand a video face id server-side
  to the other still-unassigned faces of the same video with cos ≥ `face_suggest_threshold` to it (other people's
  faces are never moved). `person_review` returns `accepted_all` / `rejected_all` (expanded ids, for undo), no
  `toast` (the client shows one summary), and with `{next:true}` the refreshed `suggestions` (same ranking).
* Suggestions skip every frame of a video already having a face assigned to / rejected for that person.
* PERSON gains `photos` and `videos` (item counts by kind).

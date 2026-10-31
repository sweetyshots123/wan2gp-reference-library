# Personas / face clustering API (1.10.0, draft contract)

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
| `face_suggest` (fast) | `{person, method:"centroid"\|"nn"="nn", limit=40, threshold?}` | `{ok, person, faces:[FACE+{score}]}` best first; never rejected faces, never faces assigned to anyone |
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
the next incremental run. (Re-matching moved rows by embedding is not done; a forced re-index that reorders faces can
leave a wrong assignment, which `face_unassign` fixes.)
Items removed from the library drop their faces (tags go with the item).

## Algorithm
Leader/centroid clustering, cosine on L2-normalised float32: each new unassigned face joins the closest cluster centroid
if `cos ≥ threshold`, else starts a new cluster; after a pass, clusters whose centroids are ≥ threshold are merged.
Incremental: only faces not in `seen`. Suggestions: `nn` = max cosine to the person's faces, `centroid` = cosine to
the centroid; candidates below `face_suggest_threshold` are dropped.

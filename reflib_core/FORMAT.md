# reflib_core storage format

Everything lives under one data folder (`configure(data_dir)`; in WanGP it is the plugin folder). All JSON files are
UTF-8, written atomically (temp file + `os.replace`). Images are addressed by the SHA-256 of their bytes ("hash").
Disk files in watched folders are never written, moved or deleted.

| Path | Content | Version |
|---|---|---|
| `collections/collections.json` | collections: `{id, name, images: [{file, hash, name, added_at, meta?}]}` | unversioned since 1.0 (additive fields only) |
| `collections/<id>/<hash>.<ext>` | collection image copies | — |
| `collections/.thumbs/<hash>.jpg` | thumbnail cache (disposable) | — |
| `collections/tags.json` | manual tags `{hash: [tag, …]}` | 1.4.0 |
| `collections/.crops.json`, `.undo/` | crop dedupe keys, 15-minute undo stash | 1.3.0 / 1.4.3 |
| `pool/pool.json`, `pool/<hash>.<ext>` | unassigned images `{hash, file, name, added}` | 1.4.0 |
| `folders/folders.json` | watched folders and their index (path, recursive, files: rel → size, mtime, hash, first_seen) | 1.4.0, lazy hashes 1.4.4 |
| `videos/videos.json`, `videos/<id>.*` | video library | 1.2.0 |
| `autotags.json` | auto tags, see below | **format `reflib-autotags`, version 1** (1.5.0) |
| `autotag_settings.json` | tagger settings (model, thresholds, batch, VRAM cap, cloud opt-in, API keys) | 1.5.0 |
| `models/` | lazily downloaded model weights (HF cache layout) | — |

## autotags.json (v1)

```json
{"format": "reflib-autotags", "version": 1,
 "images": {"<sha256>": {
    "tags": {"<tag_id>": [0.87, "<source model>"]},
    "model": "wd+qwen", "at": 1760120000.0,
    "review": false,
    "accepted": ["<tag_id>"], "rejected": ["<tag_id>"],
    "height_cm": 172,
    "body": { "measurable": true, "view": "front", "full_body": true,
              "px": {"shoulder": 171, "bust": 170, "underbust": 150, "waist": 110, "high_hip": 147, "hip": 180, "thigh": 60, "gap": 10, "knee": 41},
              "norm": {"waist": 0.46, "...": 0}, "ratios": {"waist_hip": 0.61, "waist_bust": 0.65, "shoulder_hip": 0.95, "bust_hip": 0.94, "thigh_hip": 0.33, "thigh_knee": 1.46, "gap_hip": 0.06},
              "scores": {"waist_definition": 0.36, "curvature": 0.85}, "prop": {"torso": 0.32, "leg": 0.55, "arm": 0.41},
              "cm": {"waist": [66.1, 60, 73], "...": [0, 0, 0]}, "height_cm": 165, "height_source": "assumed",
              "uncertainty": 0.1, "estimated": true, "tags": {"body_hourglass": 0.9},
              "vlm": {"values": {"waist": 64}, "agree": {"waist": true}} } } } }
```

* Tag ids are `taxonomy.json` ids. Confidence is 0–1; the UI threshold (default 0.35, per group overrides) decides
  what is shown; `accepted` / `rejected` are the user's edits and survive re-runs.
* `review: true` = the model estimated the person may be under 18: then only non-body, non-nudity tags plus
  `appears_minor` / `needs_review` are stored, and no `body` block.
* `body.cm` values are **estimates** `[mid, low, high]` (cm); see bodyshape.py for the method and its limits.
* Re-runs skip hashes already tagged by the same model: a changed file has a new hash, so it is re-tagged.
* Readers must ignore unknown keys; a new incompatible layout will bump `version`.

## taxonomy.json

`{"version": 1, "notes": "…", "nodes": [{id, parent, kind: category|group|tag, en, es,
syn: {en: [], es: []}, exclusive?, sensitive?}]}`. Groups marked `exclusive` take one label; `sensitive` groups
(body, coverage, nudity) are dropped for images flagged `appears_minor`.


## user_taxonomy.json (v1, since 1.5.1)

`{"format": 1, "nodes": [...], "undo": [{"at", "what", "nodes"}]}`. Each node has the same shape as a node in taxonomy.json
(`id`, `parent`, `kind` = group|tag, `es`, `en`, `syn: {es: [], en: []}`, optional `exclusive`, `sensitive`), plus `custom: true`.
Ids start with `u_`. A tag placed straight under a category goes into an automatic `u_mine_<category>` group. The nodes are merged
after the shipped ones at load time. Shipped ids can't be overridden, and nodes whose parent no longer exists are ignored.
`undo` keeps the last 30 snapshots of `nodes`.

## autotags.json additions (1.5.1)

`age: {"est": years, "pm": ±years}`: the numeric apparent-age estimate. It is never present on entries with `review: true`.

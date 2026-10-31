# Duplicates API (1.11.0)

Module `reflib_core/dupes.py` (numpy + PIL), registered in `actions_all.py`. UIs: Galería `gallery/src/Dupes.tsx` (#/duplicados), Media Library `reflib_dupes.js`. Both only call these actions.

| action | args | returns |
|---|---|---|
| `dup_scan` | `full?` | starts the background hash worker (incremental; `full` recomputes) |
| `dup_status` (fast) | – | `dupes: {running, done, total, hashed}` |
| `dup_groups` | `threshold` (0–16, default 6), `kind` (`""`/`exact`/`near`), `offset`, `limit` | `groups[]`, `count`, `waste` |
| `dup_resolve` | `keep` hash, `drop` hashes, `paths` (same-item copies), `transfer` | `drop` hashes for the normal delete flow, `recycled` |

Group: `{id, kind, dist, same_item, keep, biggest, smallest, waste, rows[]}`; row: `{hash, name, path, dir, folder, w, h, mp, bytes, fmt, date, origin, tags, in_library, on_disk}`.
Near rule: pHash Hamming ≤ threshold and dHash ≤ threshold + 4. Cache: `<collections>/dupes.json`.
Deleting is never done here except recycling extra files of one identical item (`forget.recycle` + `imagelib.rescan`, error `dup_keep_one` if none would remain); everything else goes through `forget_plan` → `forget` / `delete_all`.

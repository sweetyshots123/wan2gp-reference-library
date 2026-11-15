
# Reference Library: stay on video after frame capture + Open Media Library (1.12.6)

- **User flow (capture):** open a video in Galería viewer or Media Library lightbox → play → D or middle-click (Vidosser) → frame is saved to the unassigned pool → stay on the same video at the same time (resume if it was playing); at most Vidosser's brief toast. Never navigate to the captured photo.
- **Shared:** `imagelib.pool_add_bytes` (existing) + `reflib_core/framecap.save_result` annotates `{stay:true, navigate:false}`; clients use `frame_capture_rules.js` / `vidosser:frame-saved`.
- **Open Media Library:** Reference Library tab top link → `/reflib/media-library/` (new tab, Media Library alone). Media Library header → Galería (`/reflib/gallery/`). Galería header → standalone Media Library + WanGP / Reference Library (`/`).
- **Privacy:** frames stay on the PC in `pool/`; no new network calls.

## 1.12.18 — Fast ML search inside WanGP, tag field fixes

- Server: `ILIB_READONLY` gains `at_suggest`, `col_peek` and `at_tax_list`. `thumbs_for` counts its budget from the start and looks up source paths in the last built catalog (`_by_hash(stale_ok)`, `_cat["prev"]` kept after `invalidate()` until the next build). A hash unknown to a stale catalog is returned as pending.
- ML transport: `sendIlib` sends `DIRECT_OK` actions (FAST_ACTIONS minus `form_busy`) to `/reflib/api` when the `directApi()` probe succeeds, and falls back to the Gradio channel (`directOff`). Opt out with `localStorage.reflib_direct_api = "0"`. A network error (no HTTP status) is retried once directly before `directOff`; `directOff` re-probes after 5 s. Test hooks: `window.__reflibDirect` and `window.__reflibSched`.
- Cancelling older keystrokes: `req.supersede = {group, sig}` (ML) and `call(…, {supersede})` (Galería) map to `scheduler.enqueue(run, prio, sup)` and `ReflibNet.supersedes`. Groups: query (sig = filter), facets, suggest (sig = text), omni-preview.
- Tags: in `tag_complete.js` v2, composition guards (`compositionstart`/`compositionend`, `isComposing`, keyCode 229, Dead/Process keys); `api.busy` / `api.open` (the ML Esc handler defers to the field while it is busy); `isPersonTag` / `plainTags` (both UIs).
- **♥ Favoritas filter in the Media Library Explorador**, shared with the Galería's ♥ Favoritas view: both send the query filter `fav: true`, which the core (`imagelib._clean_filter`, `FAV_TAG`) turns into the `favorita` tag filter (case-insensitive, ANDed with the other filters). Shared rule/constant: `filter_rules.js` (`ReflibFilters`: `FAV_TAG`, `isFav`, `favCount`, `withFav`, `favToggle`). In the ML: toggle with count in the type bar, removable chip, kept in navigation history. Tests: `python3 tests/catalog_race_check.py fav_filter`, `node --test tests/test_filter_rules.mjs`, `node tests/test_browser_favorites.mjs` (both UIs).
- Galería viewer, original first: `ReflibNet.VIEW_PRIO` / `itemPrio("current" | "view" | "neighbour")` (12 / 10 / 8). `call(…, {prio})`; `mediaUrl` and the open item's `medium.get(h)` use "current", the ±N preloads `medium.get(h, true)` use "neighbour" and wait on `MediumCache.hold(p)` (the open item's media_url + decoded original, capped by `holdMs` = 2.5 s; released when the item changes). `loadFull` sets `fetchPriority = "high"`, neighbour images "low". Test: `node tests/test_browser_viewer_prio.mjs` (`REPORT=1 DIST=<dir>` measures another build).
- Tests: `python3 tests/ilib_readonly_check.py`, `python3 tests/catalog_race_check.py thumbs_budget`, `node tests/test_browser_ml_search.mjs`.

## 1.12.18 (viewer) — Viewer rules shared by both UIs: wheel, Fit on every item, zoom to cursor

- **Shared module `viewer_rules.js` (`ReflibViewer` v1)**: imported by the Galería (`gallery/src/viewerNav.ts` → `ViewerRules`) and prepended to the Media Library by `plugin.py build_js` (tuple now also has `wheel_rules.js`, so the ML gets `ReflibWheel` too). `wheelIntent` (Ctrl/⌘ = zoom, zoomed + pannable = pan, else step; an already `defaultPrevented` wheel is left alone), `zoomAt` (translate+scale zoom to cursor, the Galería math moved here), `zoomScroll` (same invariant for a scrollable 1:1 stage, ML), `navZoom` (every navigation lands in Fit), `fitSize` (size from the ORIGINAL dimensions whatever progressive stage is loaded).
- **Wheel = previous / next in both UIs** with the same `ReflibWheel` stepper (1 notch = 1 item, fast spins step N). ML lightbox: photos and videos, as in the Galería; in 1:1 with a scrollable image the wheel pans (native scroll), Ctrl + wheel up = 1:1 at the cursor, down = Ajustar (the page zoom is prevented). Steps made while a page is loading chain from the pending target (`box._pend`), so a fast spin never repeats or skips.
- **ML "Ajustar" never small** — root cause: the fit CSS only capped (`max-width/max-height`), so the `<img>` showed at the intrinsic size of the progressive stage loaded at that moment (220 px thumbnail, then the 1024 px preview) until the full file decoded (seconds for big files / Drive folders). Now `lightboxFit()` sizes it with `fitSize` from the preview reply's `width/height` (cached per hash): aspect from the loaded pixels (EXIF-oriented), scale from the original's long side (PIL size is pre-rotation), unknown original = fill, a known small original is not upscaled beyond 1:1. Re-fit on every stage `load`, window resize / fullscreen; the size is kept across a step (the old pixels would flash at their intrinsic size) and a first, unsized image stays invisible (`reflib-ib-lbsizing`) until sized. 1:1 also means the original size (before: 1:1 of the preview).
- **Galería**: already filled the screen with its placeholder (`.phimg` 100 %) and reset the zoom per item; now through the shared rules (`VR.navZoom`, `VR.zoomAt`, `VR.wheelIntent`), and the placeholder gets the original's Fit size with `VR.fitSize` (the medium cache keeps `width/height` from the preview reply), so an original smaller than the screen no longer fills and then shrinks. Unknown size = fill, as before.
- **Fit on every item in both UIs**: the ML used to keep 1:1 across items; now, like the Galería, the next item opens in Ajustar.
- **Zoom to cursor**: ML click on the photo / Ctrl + wheel → 1:1 keeping the clicked image point under the pointer (before: 1:1 always opened at scroll 0,0); key 1 / 1:1 button zoom around the centre. Galería click / Ctrl + wheel / pinch use `VR.zoomAt` (same behaviour as before). CSS px throughout, so devicePixelRatio does not matter (tested at DPR 2). The ML has no continuous zoom or pinch (Ajustar ↔ 1:1), unchanged.
- Tests: `node tests/test_viewer_rules.mjs` (pure rules + both UIs wired to them, no local copy of the zoom math), `node tests/test_browser_mlwheel.mjs` (real standalone ML + built Galería in headless Chrome, DPR 2; ML: every painted frame checked at the 220 / 1024 px stages of a synthetic 3000×2000 "original", fails on 61c20ca; Galería: wheel steps, click / Ctrl+wheel keep the point, next item in Fit). Mock `tests/browser/server.mjs`: optional `THUMB / PREVIEW / FULL / ORIG_W / ORIG_H / PREVIEW_DELAY` env, defaults keep the other tests identical.

## 1.12.17 — Indexing races fixed, thumbnails after a long scroll, tag autocomplete

- Server: catalog edit epoch (`_cat["epoch"]` / `data_epoch`), bumped by `invalidate()`, `_patch_remove`, `_patch_tags` and `_patch_cols`. The previous catalog is served while indexing only if `data_epoch == epoch`, and an older in-flight build lands with `key=None`. The forced `_missing_recheck` waits for an in-flight background pass. Sidecar names are compared via `os.path.normcase` (`_candidates`, `origin._dir_names`).
- Clients: `ReflibNet.indexRefresh({was, running, revChanged})` returns "full", "scan" or "none". Galería poll (`wasScan` ref) → `refresh()` / `refreshScan()`; ML `pollScan` → `refreshData()` when indexing ends. Test hooks: `window.__galIndexMode` and `window.__mlIndexMode`.
- Thumbnails: `ReflibNet.rankThumbs(entries, view, margin)` and `createThumbQueue({send, batch, inflight, pos, view, margin, blocked})` (pull-based, visible first, unmounted tiles dropped), plus a `th` lane in `createLanes` (2 at a time). Galería `wantThumb(hash, el, cb)` returns `release`, and `Thumb` passes its element; test hook `window.__thumbQ`. ML `wantedThumbs()` uses `rankThumbs`.
- Tag autocomplete: `tag_complete.js` (`ReflibTagComplete.rank / completion / inline / accept / attach`), loaded in the plugin's shared JS tuple and imported by the Galería. Wired on the Galería EditPanel (`input.tagin`, key "gal-tag") and the ML footer (`.reflib-ib-tagin`, key "ml-tag").
- Tests: `python3 tests/catalog_race_check.py [case]`, `node tests/test_browser_thumbs.mjs`, `node tests/test_browser_tagcomplete.mjs`, `node tests/test_browser_indexing.mjs`; bench `python3 tests/bench_catalog_scan.py 23000 2300 .` (scan marked running).

## 1.12.16 — Fast catalog while indexing

- Server: `imagelib.catalog()` single flight (`_cat_build`) + stale-while-indexing (only when the key differs in the folders index / missing re-check and a scan runs); `_catalog_build` parses the folders index once; `forget.is_missing(i, known, gone)` uses the scan + background re-check (`_missing_recheck`, `MISSING_RECHECK_S = 60`, `missing_recheck_now()`); `SCAN_COMMIT_SECONDS = 10`; scan stores `side` (AI sidecar) from its listing, `origin.prime_sidecars`, fallback one listing per directory; `query()` passes the catalog to `_light`.
- Clients: `ReflibNet.scanRefresh` / `createLanes` / `bgPrio` (request_priority.js, both UIs). Media Library `refreshData(true)` while indexing + `renderSide()`; Galería `refreshScan()` on rev change while `scan.running`.
- Tests: `python3 tests/catalog_perf_check.py`, `node tests/test_scan_refresh_rules.mjs`, `node tests/test_browser_indexing.mjs`; bench `python3 tests/bench_catalog_scan.py 23000 2300 .`.

## 1.12.15 — Unsupported-codec notice matches the loaded video

- Galería viewer: notice + «Abrir en reproductor externo» / «Mostrar en carpeta» only while the current `<video>` really can't decode its source (`ReflibPlayback.unplayable`, playback_rules.js, shared with the Media Library); recomputed on `ReflibPlayback.UNPLAYABLE_EVENTS`, never sticky across items. Test: `node tests/test_browser_vbad.mjs`.

## 1.12.14 — Capture keeps play state; ML details video kept; tests on real code

- Shared play intent `ReflibFrameCapture.trackIntent / wantPlay` (frame_capture_rules.js v3) in Galería and Media Library.
- ML: body rebuilt around the details host (`replaceKeeping`); lightbox steps only on fresh rows.
- Galería: pin released when the open item leaves the list; App-driven moves keep fullscreen; stale bar EN/ES, closable, once per version.

### How to run the tests

- All node tests: `node --test tests/*.mjs` (the glob is needed: Node's default pattern does not match `test_*.mjs`). Each file also runs alone with `node tests/<file>.mjs`. Several suites at once on one machine (each browser test starts its own Chrome + mock server): `node --test --test-concurrency=3 tests/*.mjs`; the browser tests wait by polling with generous timeouts, but ~20 headless Chromes on 8 cores can still miss one.
- Python: `pytest -q tests/` (in an env with the plugin deps; `test_videofaces` needs `cv2`).
- Galería build: `cd gallery && npm run build`.
- Node test files (32; the browser ones use headless Chrome + the synthetic mock in `tests/browser/` and skip without google-chrome / ffmpeg / dist): `bench_viewer_priority.mjs`, `test_browser_capture.mjs`, `test_browser_favorites.mjs`, `test_browser_indexing.mjs`, `test_browser_ml_search.mjs`, `test_browser_mlwheel.mjs`, `test_browser_tagcomplete.mjs`, `test_browser_thumbs.mjs`, `test_browser_vbad.mjs`, `test_browser_viewer_prio.mjs`, `test_capture_stay_gallery.mjs`, `test_capture_stay_ml.mjs`, `test_faces_overlay.mjs`, `test_filter_rules.mjs`, `test_frame_capture_rules.mjs`, `test_fullscreen_rules.mjs`, `test_nav_paths.mjs`, `test_person_match.mjs`, `test_play_intent.mjs`, `test_playback_rules.mjs`, `test_progressive_media.mjs`, `test_request_priority.mjs`, `test_review_rules.mjs`, `test_scan_refresh_rules.mjs`, `test_selection_rules.mjs`, `test_stale_bar.mjs`, `test_standalone_rules.mjs`, `test_start_picker.mjs`, `test_tag_complete.mjs`, `test_thumb_queue.mjs`, `test_viewer_rules.mjs`, `test_wheel_rules.mjs`.

## 1.12.13 — Frame capture stays on the video (Galería fix, ML parity)

- Shared `ReflibFrameCapture.pinFollow / pinLocate / sameOpen` (frame_capture_rules.js v2).
- Galería: viewer pinned by hash across refreshes; stale-build reload bar. ML: lightbox re-indexed (not re-opened), preview `<video>` kept.
- Tests: `tests/test_capture_stay_gallery.mjs`, `tests/test_capture_stay_ml.mjs` (both fail on 1.12.12).

## 1.12.12 — All navigation paths keep fullscreen; resume offer per item

- Galería: single `navTo(j)` (keys, ‹ ›, wheel, strip) → `ReflibFullscreen.navigate`. Media Library: single `openLightbox()` wrapper → `openLightboxNow()`.
- `ReflibPlayback.offerFor` scopes the resume offer to its hash in both UIs; ML clears old offers on step.
- Tests: `node tests/test_nav_paths.mjs` (every path through the choke point + offer scoping).

## 1.12.11 — Fullscreen kept across next/prev

- Shared `fullscreen_rules.js`: fullscreen on a stable container (Galería `.stage`, ML `.reflib-ib-lightbox`); `navigate(container, step)` inside the key/click gesture first moves a native `<video>` fullscreen to the container and only then steps (removing the fullscreen `<video>` before the move completes drops it — checked in headless Chrome); `keep()` tries the move on `fullscreenchange`; `escAction` leaves Esc to the browser while fullscreen.
- Galería: same `<video>` element reused (no `key={src}`, stays mounted while the next URL loads); ⛶ button.
- Media Library / standalone: ⛶ button in the lightbox bar; arrows/buttons step inside fullscreen.
- Tests: `node tests/test_fullscreen_rules.mjs` (synthetic DOM stubs).

## 1.12.10 — Soft-assign safety, ML autocomplete parity, standalone toast once

- All-obsolete assign: no person create, no prune (`face_all_obsolete` only).
- Media Library name fields: `ReflibPersonMatch.attach` (shared with Galería keyboard/fold).
- Standalone: `bridgeFailToast` ignores `wan_bridge_unavailable` after the one-time notice.
- Atomic JSON via unique `.tmp`; Faces service singleton under `_F_LOCK`.

## 1.12.9 — Faces naming + viewer priority over thumb backlog

- **Soft assign:** `Faces.assign_faces` partitions alive vs obsolete face ids; assigns alive, prunes missing from clusters, toast `face_assigned_skip` / error `face_all_obsolete`. Same path for Galería and Media Library.
- **Name autocomplete:** `person_match.js` + `person_suggest` / `Faces.match_persons` (fold, prefix, substring). Galería NameBox keyboard; ML resolves fold-equal persons.
- **Zoom / open during scan:** `request_priority.js` priority queue + thumb gate (viewer open ⇒ thumbs wait). Progressive placeholder zoom in Galería Viewer and Media Library lightbox; full `media_url` upgrades without blocking the UI.
- **Tests:** `tests/test_faces.py` (obsolete assign, match_persons), `test_person_match.mjs`, `test_request_priority.mjs`, `test_progressive_media.mjs`.

## 1.12.8 — Standalone WanGP-action gating + resume i18n

- Standalone Media Library hides Gradio-bridge actions (add to references, control video, audio targets, generation history). Any leftover bridge call shows a **one-time** translated notice (never «bridge missing (reload)» spam). Shared `standalone_rules.js`.
- Galería resume buttons use the current UI language (`uiLang()`), not a hard-coded `"es"`.
- Docs: «Abrir Media Library» → `/reflib/media-library/`.

## 1.12.7 — Standalone Media Library & resume playback

- `/reflib/media-library/`: Media Library alone (shared explorer JS; `POST /reflib/api` fallback).
- Resume long videos (default threshold **5 minutes**, user-configurable): positions in `playback.json`; shared `playback_*` actions + `playback_rules.js` for Media Library, Galería and standalone.
- Threshold UI in Reference Library settings, Galería and standalone; install never writes `settings.json` for this.


## Tests

```sh
node tests/test_frame_capture_rules.mjs
node tests/test_playback_rules.mjs
node tests/test_standalone_rules.mjs
PYTHONPATH=. python tests/test_framecap.py
PYTHONPATH=. python tests/test_playback.py
```

## Browser retest (pending)

1. Galería: open a recent video, play, capture several frames with D; viewer must stay on the video; photos appear in Recientes / Sin colección after leaving the viewer.
2. Media Library lightbox: same.
3. Reference Library tab: top button «Abrir Media Library» opens `/reflib/media-library/` in a new tab; Media Library header «Abrir en Galería» works; Galería links to Media Library and Reference Library.

# Reference Library: starting-image picker (1.12.4)

- **User flow:** Start with Image → Choose from library / Elegir de la librería in the starting-gallery controls → existing Media Library explorer, image filter → double-click one image or select one + Add to starting images / Añadir a imágenes iniciales. Cancel/Esc restores the previous explorer filters and does not modify inputs.
- **Destination:** `image_start` on the originating generate/edit form, strictly separate from `image_refs`. Other image-routing footer actions are hidden in this picker context. Video/audio pickers retain their existing history bridge.
- **Add semantics:** plugin resolves the library image (renders virtual image crops as usual), stages it in Gradio's temporary upload folder and invokes WanGP AdvancedMediaGallery `_on_add` using CURRENT start-gallery value and its own state. Existing entries remain, insertion follows selection, and the new image is selected. Single-image state is rejected rather than replacing an entry. Nothing generates, queues or changes model/mode automatically.
- **Hook:** plugin requests `image_start_extra` alongside `image_start`. Validates the exported `[row, upload, left, right, clear, gallery, state]` layout and tags the UploadButton by component identity. JS mounts one translated button as a sibling in `.amg-controls`; it inherits row visibility, including when Start with Image is hidden. No label matching, WanGP core patch, Dragger modification or duplicate browser.
- **Bridge:** hidden `reflib_bridge_<tab>_image_start`; request `{id, target: "<tab>:image_start", to: "image_start", hash, lang}`. Only an available library image is accepted; errors return `ok:false` and skip both output components. Success returns `restored:["image_start"]`. Gallery/state are the only media outputs.
- **Privacy:** no media leaves the PC. Only the selected image is staged locally, like Add. No new persistent settings or library format. No user/library data in the commit.

## Tests

With the existing WanGP code and a Gradio environment (no model weights required):

```sh
PYTHONPATH=/path/to/Wan2GP python tests/test_start_picker.py
node tests/test_start_picker.mjs
```

Python tests use real Gradio and core AMG Add; only the model-stack dimension-label helper is stubbed. JS tests execute shipped picker functions with a small DOM/bridge harness, not a browser. Actual visual layout/theme and Gradio event round-trips require the manual retest below.

## Browser retest (pending)

1. Start the authorized box test instance with this plugin, not the PC or another agent's instance. Force reload after updating the plugin JS.
2. Select a model with Start with Image and activate that mode. Check the new button beside Add/Remove/Left/Right/Clear, both empty and populated galleries, dark/light themes and a narrow window.
3. Put two synthetic images A/B into starting images and a different C into Reference Images. Select A; open the new button. Check image-only initial filter and explicit starting-images banner/action (not Add to references).
4. Double-click library image D. Expected start gallery A/D/B, D selected; C unchanged; no generation and no queue entry. Repeat using selection + the footer action; also test a virtual image crop.
5. Open again, change browser filters, then Cancel/Esc. Inputs must be unchanged; opening the regular explorer must restore its pre-picker filters.
6. Change away from Start with Image: its controls and new button must hide together. Switch back: exactly one button, even after repeated model changes.
7. Repeat in ES and EN (live switch), and on edit form if it exposes a compatible gallery. Smoke-test ordinary Reference Images, video and audio library pickers to confirm their original destinations still work.

## 1.12.5 truncated thumbnails
Image thumbnails tolerate truncated JPEGs for the duration of one open (flag restored under a lock). Persistent decode failures are remembered by path+mtime+size and logged once.
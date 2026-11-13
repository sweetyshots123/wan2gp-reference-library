
# Reference Library: stay on video after frame capture + Open Media Library (1.12.6)

- **User flow (capture):** open a video in Galería viewer or Media Library lightbox → play → D or middle-click (Vidosser) → frame is saved to the unassigned pool → stay on the same video at the same time (resume if it was playing); at most Vidosser's brief toast. Never navigate to the captured photo.
- **Shared:** `imagelib.pool_add_bytes` (existing) + `reflib_core/framecap.save_result` annotates `{stay:true, navigate:false}`; clients use `frame_capture_rules.js` / `vidosser:frame-saved`.
- **Open Media Library:** Reference Library tab top link → `/reflib/media-library/` (new tab, Media Library alone). Media Library header → Galería (`/reflib/gallery/`). Galería header → standalone Media Library + WanGP / Reference Library (`/`).
- **Privacy:** frames stay on the PC in `pool/`; no new network calls.

## 1.12.15 — Unsupported-codec notice matches the loaded video

- Galería viewer: notice + «Abrir en reproductor externo» / «Mostrar en carpeta» only while the current `<video>` really can't decode its source (`ReflibPlayback.unplayable`, playback_rules.js, shared with the Media Library); recomputed on `ReflibPlayback.UNPLAYABLE_EVENTS`, never sticky across items. Test: `node tests/test_browser_vbad.mjs`.

## 1.12.14 — Capture keeps play state; ML details video kept; tests on real code

- Shared play intent `ReflibFrameCapture.trackIntent / wantPlay` (frame_capture_rules.js v3) in Galería and Media Library.
- ML: body rebuilt around the details host (`replaceKeeping`); lightbox steps only on fresh rows.
- Galería: pin released when the open item leaves the list; App-driven moves keep fullscreen; stale bar EN/ES, closable, once per version.

### How to run the tests

- All node tests: `node --test tests/*.mjs` (the glob is needed: Node's default pattern does not match `test_*.mjs`). Each file also runs alone with `node tests/<file>.mjs`.
- Python: `pytest -q tests/` (in an env with the plugin deps; `test_videofaces` needs `cv2`).
- Galería build: `cd gallery && npm run build`.
- Node test files (19): `bench_viewer_priority.mjs`, `test_browser_capture.mjs` (headless Chrome + `tests/browser/` synthetic mock; skips without google-chrome/ffmpeg/dist), `test_capture_stay_gallery.mjs`, `test_capture_stay_ml.mjs`, `test_faces_overlay.mjs`, `test_frame_capture_rules.mjs`, `test_fullscreen_rules.mjs`, `test_nav_paths.mjs`, `test_person_match.mjs`, `test_play_intent.mjs`, `test_playback_rules.mjs`, `test_progressive_media.mjs`, `test_request_priority.mjs`, `test_review_rules.mjs`, `test_selection_rules.mjs`, `test_stale_bar.mjs`, `test_standalone_rules.mjs`, `test_start_picker.mjs`, `test_wheel_rules.mjs`.

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

# Reference Library: stay on video after frame capture + Open Media Library (1.12.6)

- **User flow (capture):** open a video in Galería viewer or Media Library lightbox → play → D or middle-click (Vidosser) → frame is saved to the unassigned pool → stay on the same video at the same time (resume if it was playing); at most Vidosser's brief toast. Never navigate to the captured photo.
- **Shared:** `imagelib.pool_add_bytes` (existing) + `reflib_core/framecap.save_result` annotates `{stay:true, navigate:false}`; clients use `frame_capture_rules.js` / `vidosser:frame-saved`.
- **Open Media Library:** Reference Library tab top link → `/reflib/media-library/` (new tab, Media Library alone). Media Library header → Galería (`/reflib/gallery/`). Galería header → standalone Media Library + WanGP / Reference Library (`/`).
- **Privacy:** frames stay on the PC in `pool/`; no new network calls.

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
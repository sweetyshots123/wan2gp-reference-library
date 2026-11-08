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

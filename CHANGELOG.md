# Changelog

## 1.6.3 — 2026-10-17

- **Python API v5** (`wan2gp_reference_library_api`, `API_VERSION = 5`, v1–v4 unchanged): read-only access to the generation history for other plugins. `get_history_entry(eid)`, `find_history_by_output(path)`, `latest_history_entry()`, `history_settings_file(eid=None, video=None)`, `media_fields()`, and a hook `on_history_entry(callback) -> token` / `off_history_entry(token)` called after every saved generation (`updated: True` for a sliding-window continuation). Callbacks get their own copy, each runs in its own try/except, and an exception never breaks the capture. Entries are plain dicts with absolute paths. See the README.
- Every entry from the API includes **`video_source`** as an absolute path (in "L" / *Continue last video* mode, the previous output WanGP resolved, so a continuation can be chained to its parent shot), plus `image_prompt_type`, `keep_frames_video_source` and `sliding_window_overlap` in `settings`. History capture now records these even when WanGP's metadata cleaning drops them. Older entries give `None`.
- **Fix: "Reutilizar todos los ajustes" could pick the wrong upload box.** WanGP's *Custom Guide* file input (and possibly others) uses the same `wangp-settings-upload` class as the real *Load Settings From Media File / Json / Zip* loader, and comes first in the page. The loader is now chosen by its surroundings: it sits next to the settings buttons (default / export / include media / reset) and its label reads *Load Settings*. Blocks labelled *Custom Guide* or restricted to specific file types are ruled out, and if no block qualifies nothing is loaded, rather than a guess. Checked against WanGP 18.18.
- The settings are still restored through WanGP's JSON loader with the media sent by Reference Library. A queue ZIP (queue.json + media) was evaluated and not adopted: its format is internal to WanGP and changes between versions, WanGP loads it without validating the settings, and large control videos would be uploaded twice.

## 1.6.2 — 2026-10-16

- **Video resize ("Redimensionar")** to **480p / 720p / 1080p** (short side). Aspect ratio kept; the long side is rounded to a multiple of 16 (WanGP-friendly), the short side is the preset exactly. A video already at that size is left alone. **No upscaling** without an explicit confirmation.
- Encoded with ffmpeg: **NVENC** (h264_nvenc, preset p7, CQ 19) when it really works on the machine (checked with a test encode), otherwise **libx264 CRF 18**. Audio is kept (copied; re-encoded to AAC only when the container needs it). Live progress with Cancel. One resize at a time.
- **Control Video bar**: "⤡ Redimensionar" resizes the current Control Video, **replaces the input** with the result and saves it to the Video Library.
- **Media browser**: right-click, Detalles panel and the viewer offer "Redimensionar" for videos; the result goes to the Video Library.
- The source file is never touched. Results are named `<name> (720p)` (no stacking: `x (720p)` → `x (480p)`). Cropping stays in the Cropper plugin.

## 1.6.1 — 2026-10-14

- **"Recortar" (Crop) from the media browser**: right-click menu, Detalles panel and the full-screen viewer, for images and videos (not audio). Opens the Cropper plugin's editor on the library file itself, with nothing going through WanGP's inputs. Needs **Cropper 1.5.0+** (file API `window.cropper.cropFile`); with an older Cropper the button is disabled with a tooltip.
- Image crops are copied into the automatic **"Recortes"** collection; the browser switches to it and selects the new crop. Video crops are copied into the **Video Library**. Cropper's temporary result is copied right away (its temp folder is cleaned after 24 h); the original file is never changed.
- If a crop is already open, a second "Recortar" just shows a soft "Ya hay un recorte abierto" notice. Cancelling the editor saves nothing.

## 1.6.0 — 2026-10-11

- **Image browser → media browser ("Explorador de medios").** Watched folders and Import now also index **video** (mp4, mov, webm, mkv, avi) and **audio** (wav, mp3, flac, ogg, m4a, aac, opus). Files are still read in place, never copied or modified.
- **Type filter** in the header (**Todo / Fotos / Vídeos / Audios**, with counts for the current filter) and as a removable chip. The folder tree counts per type, too (tooltip).
- **Audio cards**: waveform thumbnail (ffmpeg, server-side, cached in `collections/.thumbs`), duration, ▶ to play/pause in place. **Video cards**: poster frame, duration, muted hover preview after a short delay.
- **Viewer** (double-click) plays video and audio; the **Details** panel has an inline player with duration, size, fps, codec, sample rate and file size. "Show in Explorer" / "Locate folder" are unchanged.
- **"Añadir a" per type**, only for inputs the current model shows: images → Reference Images; one video → Control video, or the Video Library; one audio → each audio input the model exposes (Audio 1/2/3). Mismatched or missing inputs are refused with a message.
- Collections hold any type; tags, search and autocomplete work for every type. History also records and restores audio inputs.
- **Auto-tagging stays images-only**: videos and audio in a selection are skipped with a notice.
- Fast at 12k+ files: large media (≥ 48 MB) use a sampled content hash (size + 3 × 4 MB), durations are probed by one throttled background ffprobe thread (on-screen items first) and cached in `collections/mediainfo.json`. Playback serves exactly the requested file through Gradio, never whole folders.

## 1.5.9 — 2026-10-12

- **A single click only selects.** The right details panel no longer opens on its own, so the grid keeps its size.
- **View selector** in the image browser header: thumbnails **very large / medium / small**, plus a **Detalles** (Details) toggle for the right panel. Details is off by default; when on, the panel shows the selected image (with "Abrir en el Explorador", "Localizar carpeta", etc.) and its × turns it off. Both choices are remembered in the plugin settings (`browser_thumb`, `browser_details`). No list view.
- **Double-click opens a full-screen image viewer** over the whole window (not the details): ←/→ (or ‹ ›) for previous/next within the current filtered results, with a position counter; **Ajustar** (fit, key 0) and **1:1** (actual size, scrollable, key 1), clicking the image toggles them; Esc closes. The selection follows the viewer.
- Right-click menu keeps "Abrir en el Explorador", "Localizar carpeta" and "Vista grande", and adds "Ver detalles" when the panel is off.

## 1.5.8 — 2026-10-12

- **Export taxonomy** in "Mis etiquetas": full (built-in + yours, merged, bilingual, with synonyms and the ES/EN path of every node) or only yours, as JSON (re-importable) or CSV (`path, es, en, synonyms`, UTF-8 with BOM for Excel). Downloaded through the browser as `reflib-taxonomy-<full|mine>-<date>.<json|csv>`.
- **Import** a taxonomy JSON (an export from this plugin, full or mine, or a `user_taxonomy.json`): **merge** (adds new nodes, updates yours with the same id) or **replace yours**. Each node is validated with the same rules and blocklist as the editor (no genital/sexual-anatomy tags, nothing about minors, no explicit acts, nothing under apparent age). Built-in nodes in a full export are skipped. A confirm dialog shows the counts first and lists the rejected nodes with the reason. One click **undo**.
- Fix: closing the auto-tag settings panel (⚙) could leave the image grid blank until you scrolled; it now redraws right away.
- Your custom taxonomy lives in `user_taxonomy.json` in the plugin's own folder (next to `plugin.py`), not in `reflib_core`.

## 1.5.7 — 2026-10-11

- **Reuse from WanGP's output player**: a compact bar right under the output video player/gallery with **"Reutilizar ajustes"** (all settings) and **"Solo referencias"**. They act on the video currently shown/selected in the player, with the 1.5.5 logic: its history entry when there is one (settings through WanGP's own loader, then refs / control video / masks), otherwise WanGP's loader with the video file itself (embedded metadata). "Solo referencias" without a history entry uses the reference images WanGP embedded in the file, if any.
- The bar sits below the player block, never over the video; no keyboard shortcuts, and its key events don't reach the player, so Vidosser's overlays and shortcuts are untouched (Vidosser is not modified). Only files inside WanGP's output folder or Gradio's cache are accepted.
- **"Abrir siempre a pantalla completa"** now lives only in the Reference Library plugin settings (the checkbox at the bottom of the browser's left column is gone) and is applied every time the browser opens. The ⛶ button still toggles for the current session.

## 1.5.6 — 2026-10-11

- **Delete in Historial and "Usadas como referencia"**: multi-select entries (click, Ctrl+click, Shift+click, like the browser) and "Borrar seleccionadas"; a **"Borrar…"** menu with última hora, últimas 24 h, últimos 7 días, todo and a custom date range.
- Every delete asks for confirmation with the exact count and offers **Deshacer** (one undo per operation, any size; the last 10 operations stay undoable).
- Deleting removes only history records and the copies the history made itself, and a copy is removed only when no other entry (or undoable delete) still uses it. Outputs and original files are never touched. In "Usadas como referencia" only the usage records go; the images stay in the library.
- Bilingual EN/ES, dark-safe menu and confirm dialog (Esc cancels the dialog without closing the view).

## 1.5.5 — 2026-10-11

- **Generation history ("Historial")**: every WanGP generation is recorded with its inputs (reference images, start/end images, control video, video/image masks, guide/source video), the prompt, ALL settings and the output path. Captured from WanGP's `before_metadata_save` plugin data hook (no core change, read-only, never alters the metadata).
- Open it from the browser header (🕘 Historial) or the 🕘 button next to the browser buttons (manager and generator bars). Newest first, output poster + input thumbnails, prompt search.
- **"Reutilizar todos los ajustes"** hands the stored settings to WanGP's own "Load Settings From Media File / Json" loader (model, prompt, seed, resolution, steps…), then restores refs (replaced), control video, masks and start/end images. Works for history entries and for generated videos in WanGP's output folder without a history entry (the file itself goes to WanGP's loader, which reads its embedded metadata).
- **"Reutilizar solo referencias"** (append by default, "Reemplazar" option) and **"Guardar refs como colección"**.
- Efficient storage: media deduped by SHA-256; in-memory images and temporary uploads are copied, files in stable places are only referenced. Size cap setting (default 2048 MB, oldest entries dropped first), delete with undo.
- **"Usadas como referencia"** view in the image browser: every image that lands in WanGP's Reference Images (Dragger, upload, "Añadir a referencias", collections, history reuse) is logged by hash with last-use date and use count; newest first, grouped by day like Recientes; normal selection / "Añadir a referencias"; "Quitar seleccionadas del historial" and "Vaciar historial". Images not yet in the library are added to the pool so they can be shown.
- **Full-screen image browser**: ⛶ button next to the X maximizes/restores (edge to edge, no margins; the grid gets more columns); "Abrir siempre a pantalla completa" option (localStorage + plugin settings `browser_fullscreen`). Esc still closes.
- **Folder search**: the browser search also matches watched-folder and subfolder names/paths (e.g. a subfolder name); the autocomplete suggests matching folders (📁); picking one acts like clicking it in the tree and adds a "Carpeta: x" chip. One folded string per tree node, matched once per query (~15 ms at 11k images).

## 1.5.4 — 2026-10-11

- **Per-image auto-tag status**: each card shows a badge for the current or last job — en cola, procesando (animated), hecha, falló, local (fallback / kept local by the cloud rules). Live through the job polling: a status revision counter makes the browser refetch only the visible server-side pages.
- **"Estado del etiquetado" facet** with counts over the current filter (en cola, procesando, hechas, fallidas, local, nunca etiquetadas); click filters the grid (with a removable chip). The job bar shows N en cola / N procesando / N hechas / N fallidas, each clickable to filter.
- The last status per image is persisted in `job_status.json`; **"Reintentar fallidas"** re-queues the failed images (job bar and facet).
- Cloud batch mode: confirmed OFF by default; the toggle now says so.
- Model names and licences in the auto-tag dropdown and dialogs are translated to Spanish (e.g. "Gemini 3.8 Flash (nube, de pago · recomendado)").

## 1.5.3 — 2026-10-11

- **Paid cloud vision backends** for the auto-tagger, each off by default with its own enable toggle: Gemini 3.8 Flash (`gemini-3.8-flash`, recommended; JSON schema, safety BLOCK_NONE, context cache, optional Batch API), GPT-6.1 Sol (`gpt-6.1-sol`; strict json_schema, prompt caching, optional Batch API), Claude Opus 5.5 (`claude-opus-5-5`) and Claude Sonnet 5.5 (`claude-sonnet-5-5`), both clothed-only. Model ids verified against the providers' docs and editable.
- **Never-cloud rule**: images flagged explicit content, appears_minor or in review are always tagged locally; untagged images get the local fast tagger first. Claude gate: coverage = clothed and no semi-nude/nude/topless/lingerie/swimwear tag. Gated images and refusals fall back to local per image, with notes and counts in the job report.
- **Cost estimate dialog** before a cloud job (image tokens for the downscaled size, taxonomy prompt with/without cache, ~500 output tokens, batch discount; editable price table, Oct 2026 list prices) and a **report** with the real cost from the usage fields. Gemini warns that its price doubles on 1 Jan 2027.
- **Localizar carpeta / Show folder in tree** in the preview (next to "Abrir en el Explorador") and the card's right-click menu: expands the folder tree to the image's sub-folder, filters the grid to it (sub-folders off), scrolls to the image and keeps it selected and highlighted. The preview shows the folder path as a clickable breadcrumb. Collection / pool images highlight their collection chip(s) instead.
- **Selection**: a plain click on an image that is already part of a multi-selection keeps the selection (shows its preview and makes it the anchor), like Windows Explorer; a plain click on an unselected image still replaces the selection, Ctrl+click still toggles.
- Uploads are downscaled to 1024 px and re-encoded without EXIF/GPS/ICC. Keys from env vars or masked settings, never logged. Per-provider data-retention and nudity-policy notes with links in settings and README.

## 1.5.2 — 2026-10-11

- **File-manager clicks** in the browser: a click selects one image (replacing the selection) and shows its preview; Ctrl/Cmd+click toggles, Shift+click selects a range, the checkbox toggles without clearing the rest, a click on empty grid space clears the selection, double-click opens a large preview (←/→ step, Esc closes). Marquee drag is unchanged.
- **Show in folder / Abrir en el Explorador** in the preview and in a right-click menu on a card: Explorer with the file selected on Windows (`explorer.exe /select,`), `open -R` on macOS, `xdg-open` on the parent folder on Linux. Argument list, no shell, only for files the library knows. Only for browsers on the WanGP PC (localhost); otherwise disabled with a tooltip.
- **Taxonomy editor as a tree**: new top-level categories, sub-categories at any depth inside new and built-in categories, tags at any level; tree picker with "+ Nueva categoría" and "+ Subcategoría"; rename, move (drag or ⇄) and delete user nodes with undo. Unlimited depth in `user_taxonomy.json`, facets, chips, autocomplete paths and search (a parent finds all descendants). Cycles are refused; the safety blocklist applies to every node.
- **Explicit-content review flag** "Revisión › contenido explícito" / "Review › explicit content": set when a model reports explicit sexual activity (a yes/no only, never described). Such images get no fine body-shape or measurement tags and are marked for review, so they can be found and removed. No sexual-act tags or categories exist, and the editor refuses them.
- Fix (since 1.5.1): the linked-prompt chips under the Reference bar did not appear after applying a collection, because the new filter-chip bar reused the same function name. Renamed; both work again.
- Autocomplete ranks a label match above a synonym match ("sen" → "sentada" before "senior").
- The auto-tag settings panel always starts closed when the browser opens, so the ⚙ button never needs two clicks.
- **Dark-mode fix for every form control**: one themed style (theme input variables, `color-scheme: dark`, placeholder colours, option lists) for the bar, manager, videos, browser, preview, facets, editor, settings and folder picker. The "Rangos corporales" inputs are narrower and their labels wrap. An E2E audit checks every visible control in both themes (contrast ≥ 4.5, placeholder ≥ 3).

## 1.5.1 — 2026-10-10

- **Active filter chips** under the search row: one chip per collection, folder, manual tag, auto tag, range and search text. × removes one, "Quitar todos" clears all. Clicking an auto-tag chip opens its category in the tree, scrolls to it and highlights it. Each auto-tag chip toggles between include (=) and exclude (≠). Chips in the same taxonomy group combine with OR, different groups with AND (shown as small "o"/"y" joiners). Collapsed tree categories show a badge with their number of active filters. Facet counts inside a group ignore that group's own selection, so OR siblings stay visible.
- **Tag autocomplete** in the search box: taxonomy tags (labels and synonyms, ES/EN, accent-insensitive, prefix and in-word) plus manual tags, each with its category path and image count; counted ones first. ↑/↓ move, Enter or Tab adds the suggestion as a chip, Esc closes the list (and no longer closes the modal). Plain text without a pick still searches by name.
- **Apparent age (estimated)**: bands 18–24, 25–34, 35–44, 45–54, 55–64 and 65+, plus a numeric estimate with ± (searchable range `edad 30-40`, range slider, chips, autocomplete, preview). The minor gate is unchanged and also binds manual edits: an image flagged `appears_minor` stores no age band, numeric age, body or nudity tags, and is only flagged for review. There is no under-18 band. Old 1.5.0 band ids are read through an alias map (approximate for the wide old bands; re-run Autoetiquetar for the new ones).
- **Taxonomy editor ("Mis etiquetas", in the auto-tag settings)**: create custom groups (exclusive or multi-label) or tags under any category or group, with ES/EN labels and synonyms; rename, move, delete, undo (30 steps). Stored in `user_taxonomy.json` in the data folder, merged over the shipped taxonomy, so it survives updates. Custom tags work for manual tagging (new "Añadir etiqueta a esta imagen…" box in the preview), facets, chips, autocomplete and search. The same safety rules apply: tags for genitals or sexual anatomy, tags that target minors, and anything under the apparent-age group are refused with a translated message. Custom tags under body/nudity categories are marked sensitive, so the minor gate drops them too. `training_examples_binary()` exposes the accepted/removed examples per multi-label tag (custom tags included) for the SigLIP2 heads that ship with 1.6.0.
- Fix: a query that had returned 0 results is refetched when the taxonomy changes, instead of staying empty.

## 1.5.0 — 2026-10-10

- **Auto-tagger.** *Auto-tag* on the selection (or all matching images), background queue with progress, pause,
  cancel and *Free GPU*; waits while WanGP generates (reads `wgp.gen_in_progress` / the queue, never imports wgp) and
  unloads the models; idle unload after 2 min; lazy model downloads with a size prompt; offline mode.
- **Taxonomy** `reflib_core/taxonomy.json`: 9 categories, 52 groups, 335 tags, 744 synonyms, EN/ES, exclusive and
  multi-label groups, sensitive groups; `appears_minor` safety gate (no body / nudity tags, no measurements, review).
- **Backends:** fake (tests), WD-EVA02, Qwen2.5-VL-7B (JSON constrained to the taxonomy), WD+Qwen (default), Jev
  (jevimage 0.1.20: choice / score / noul / trained heads, in process or via `jevimage serve`), Jev+Qwen; optional
  cloud (off by default): OpenAI-compatible, Gemini, Grok, OpenRouter Jev Router and the local-description →
  Jev 1.13 Decisions cascade; refusals fall back to the local model; cost estimate first, real cost from `usage.cost`.
- **Body shape** (adults only): silhouette + keypoints (BiRefNet + ViTPose) → widths, ratios, waist definition,
  curvature, build, thigh shape and gap, proportions, shape tags with confidences; estimated circumference bands
  (assumed or user-entered height, per image or collection), optional VLM cross-check; "not measurable" outside
  front standing poses.
- **Search:** synonyms + hierarchy in both languages, numeric body ranges and ratios, `field:value` terms; facet
  panel by taxonomy category with counts and body range filters; preview with accept / remove / restore and the
  *Body shape* panel.
- **Architecture:** the engine moved to `reflib_core/` (no Gradio / WanGP imports, CLI, `FORMAT.md`, own
  requirements); the old module names are aliases; the plugin is the adapter.

## 1.4.4 — 2026-10-10

- **Performance at scale** (11k-image watched folders). Measured on a synthetic 12,000-image tree with 40 4K JPEG/PNG originals: modal shell 45–60 ms; first page of cards 0.65–1.26 s → 0.26–0.27 s; first thumbnail 0.8–2.1 s → 0.34–0.44 s; biggest request 4.6 MB → 99 KB; data on open ~10 MB → ~1 MB; 300 cards / ~2,500 modal nodes → 42 cards / ~430 nodes (max 60 cards while scrolling the whole grid).
- Server-side pages: the browser gets counts + folder tree + 120 light items per request (`open`, `query`); filters, search, tags, Recent (with day groups) run on the server over a cached, compact catalog (~1.5 KB/image, rebuilt only when an index file changes, prewarmed at startup). All browser reads go through the unqueued channel, never behind WanGP's generation queue.
- Windowed grid with recycled cards; DOM order follows list order.
- Selection model "all N matching" (Ctrl+A, *Select shown*) with exceptions; Shift ranges and rubber-band selections resolve unloaded positions on the server; footer summary (deletable, collections, on-disk, tags) from the server.
- Thumbnails: visible cards only, 6 per request, one in flight, cancelled when scrolled away; per-request generation budget, the rest in a bounded low-priority worker; JPEG draft decoding, size/pixel guards; client cache capped.
- Folders: throttled background re-check on open (every 10 min at most), `os.scandir` stats, unchanged files never re-hashed and the index isn't rewritten when nothing changed; partial commits at most once a second. **Pause indexing** setting (settings tab and progress strip).
- Fixes: stale counts when a quick scan finished before the first poll, or replies arriving out of order (meta revisions); clicking the grid now leaves the search field so Ctrl+A selects images.

## 1.4.3 — 2026-10-10

- **Selection:** rubber-band (marquee) drag in the grid (from empty space or a card, not its checkbox), Ctrl/Cmd+drag adds, auto-scroll near the edges; Shift+click range from the anchor (also on checkboxes); Ctrl/Cmd+click toggles; Ctrl+A selects everything shown (not inside text fields); Esc clears the selection, a second Esc closes. Grid text can no longer be selected while dragging (`user-select: none`).
- **Delete any selection:** with one collection filter, **Remove from <collection>** (that collection only, Undo). **Delete from library** removes from every collection and the pool (two clicks, the confirm says how many images and collections, Undo for 15 min via `collections/.undo/`). Watched-folder files are never deleted from disk; folder-only images are skipped and the disabled button explains why. The footer wraps without cutting anything off in narrow windows; the preview becomes an overlay below 1000 px.
- **Blank thumbnails fixed.** Root cause: thumbnails went through the same queued Gradio bridge as everything else, one shared hidden textbox. With a large watched folder, index polls/list refreshes and thumb batches overlapped: later requests overwrote earlier ones in the shared box and replies were matched to the wrong request or dropped, so cards stayed empty for good (no retry), and thumb batches waited behind long list payloads. A zero-byte cached thumb (interrupted write) was also accepted as valid. Paths/`file=` routes were not involved (thumbs are inline data URIs). Fix: a separate unqueued **fast channel** for read-only actions (thumbs, scan status, browse, preview), client-side serialization per channel with request ids, visible cards first, retries with backoff and a placeholder only when no readable source exists, falling back to the original if the cache is missing or empty.

## 1.4.2 — 2026-10-10

- **Recent / Recientes** view at the top of the browser sidebar (the sidebar is now always shown): every image newest first, deduplicated by hash with its newest date, day headers (*Hoy*, *Ayer*, *Esta semana*, then dates), time on hover and in the preview. Last 30 days / 500 images per step (at least 24), *Ver más* for older. Combines with search, tags and collections.
- Dates: new collection entries store `added_at`; pool entries use their `added`; older entries fall back to the file mtime. Watched-folder files record when they were first indexed (`first`) and use max(mtime, first). Existing data is not migrated.
- API: `list_images()` entries also carry `added` (epoch seconds).
- **Examinar… / Browse…** folder picker in the *Add folder* panel, served by the WanGP server: drives (Windows) or `/`, shortcuts (home, Pictures, WanGP outputs), click-through navigation with breadcrumb and ↑, subfolders and the image count of the current folder, **Select this folder** fills the path and adds it (include-subfolders kept). Read-only `os.scandir`, hidden/system folders skipped, permission errors and slow drives (4 s timeout) reported in EN/ES. The typed path stays as a fallback.

## 1.4.1 — 2026-10-10

- **Add folder** button in the browser header (next to Import / Re-scan) opens a path field; *Include subfolders* is on by default. Windows paths work: backslashes, drive letters (`D:` → `D:\`), spaces, quotes, `file:///` URLs.
- Indexing starts immediately in a **background thread** with a progress strip and a count toast; partial results are committed every 200 files so the grid fills in; unchanged files are never re-hashed. Thumbnails are **lazy-loaded** (only cards scrolled into view, in batches). Pages of 300 cards.
- **Folder tree** sidebar: each watched root, expandable into subfolders mirroring the disk, with image counts (subtree or direct); click to filter, *Include subfolders* toggle, **breadcrumb** with ↑. Works together with the collection and tag filters. Per-root ⟳ re-scan and × remove (two clicks). The old collapsed "Watched folders" row is gone.
- **Add to references**: a primary action in the selection footer appends ONLY the selected images to Reference Images (same AdvancedMediaGallery path as a collection apply; duplicates skipped, never replaces). Folder images go in from their path without being copied into a collection. Optional *Close after adding*. Error toast if Reference Images is hidden for the current model.
- Everything on disk stays read-only.

## 1.4.0 — 2026-10-10

- **Image browser**: a grid icon in the bar and the manager opens a modal with every image (all collections, deduplicated by sha256, with a ×N collections badge). Filters by collections (multi, All, Unassigned), folders, tags and name; larger preview with collections/files/tags; multi-select; **Add to collection…** (default: the collection loaded in the bar, or a new one; never the same content twice); Esc / × close and refresh the bars. EN/ES with live switching, dark theme, toasts bottom-right.
- **Tags** per image (by hash), with autocomplete, stored in `collections/tags.json`.
- **Unassigned pool** (`pool/`): *Import images* (button or drag-and-drop), deduplicated; images removed from their last collection are kept there; two-click delete with Undo and trash.
- **Watched folders** (`folders/index.json`): folders on the WanGP machine indexed in place (never copied or modified), optional subfolders, rescan on open and with *Re-scan*, server-side path validation, missing/moved files handled; adding to a collection copies. Thumbnails cached in `collections/.thumbs/`.
- **API v4**: read-only `list_images(tag, collection_id, unassigned)`, `list_tags()`, `image_tags(sha256)`; v1–v3 unchanged.
- Cropper fixes: `add_image` now stores the **full `meta`** (crop, target, source_file, dedupe_key…) with the image entry (previously only the dedupe key), and also returns `name` and `meta` (old keys unchanged). The image-crop toasts now name the image: *Recorte “X” guardado en la colección “Recortes”* / *Crop “X” saved to the collection “Crops”* (and the duplicate one).
- Existing data and `settings.json` are not touched or migrated.

## 1.3.0 — 2026-10-10

- **Rename in place with a pencil**, with the same look and behaviour as Prompt Library 1.2.1: a small pencil inside the select (round hover background), the name turns into a text field with an amber frame, **Enter** or clicking away saves, **Esc** cancels, double-click also starts it, and an empty name on Enter shows the error and stays in edit mode.
  - Collections: the bar's selected collection and the manager's collection select.
  - Videos: the video bar and the selected video's name in the Videos section (pencil shown on hover, like Prompt Library's tag chips).
  - Same validation, name dedupe (videos: “X 2”) and translated messages as the Rename button; the ids don't change. All bars, the manager and the Videos section refresh, and `reflib:changed` fires (`rename` / `video-renamed`).
  - The manager's **Rename** buttons stay, as Prompt Library keeps its manager Rename.
- **Image crops from Cropper 1.2**: public API **`API_VERSION` 3** adds `add_image(path, name=None, source="cropper", meta=None, collection_id=None)` and `image_crop_policy()`. v1/v2 are unchanged.
  - Destination: the given collection, otherwise an automatic **“Crops” / “Recortes”** collection (created on first use, UI language, id remembered in `collections/.crops.json`). The user's other collections are never changed implicitly.
  - Never raises; same dedupe as videos (sha256 or `meta.dedupe_key`, per collection) and restore-aware: undoing the delete of the crops collection merges the one created meanwhile back into it.
  - New setting **Image crops made with Cropper** (*auto* / *ask* / *off*, default auto), separate from videos (now labelled *Crops made with Cropper (videos)*). Toasts and the *Save to the collection* button appear when the crop lands in Start/End, Reference or Control image inputs; the collection bars refresh.
- Image entries may now carry `source` and `key` (dedupe key); older indexes load unchanged.

## 1.2.1 — 2026-10-09

- Toasts moved to the **bottom-right corner** (newest at the bottom, at most 5 stacked, never dropping one that still has a button) with z-index 10090. The top-centre spot is shared by Dragger, Cropper and Prompt Library toasts (and bottom-centre by Vidosser), which could cover the *Ask each time* **Save to the library** button. It now stays visible and clickable for its whole 20 s, also above Cropper's dialog.
- Fix: **Undo** of a deleted video no longer creates a duplicate. If the same video was saved again while the deleted one was in the trash (same content, or same `meta.dedupe_key`, e.g. the same crop made again with Cropper), Undo keeps the entry that is already there, drops the trash copy and says so: *“X” was not restored: the same video is already in the library as “Y”* / *No se ha restaurado «X»: el mismo vídeo ya está en la librería como «Y»*.
- A restored video whose name was taken meanwhile by a different video gets a unique name (“X 2”), as when saving.

## 1.2.0 — 2026-10-09

- **Video library** for Control Videos, managed like the image collections but stored on its own (`videos/`, next to `collections/`; existing collections are not touched or migrated).
  - Compact bar **under Control Video** (only while WanGP shows it): pick a video (name · duration · resolution) to load it, **Load**, **Save as…** (inline name; empty = file name), **Manage**. A small poster with fps, frames, size and origin shows the selected video.
  - **Videos** section in the Reference Library tab: thumbnail grid with captions, preview player, rename, **Load into Control Video**, reorder (Left/Right), delete with the two-click confirm and a 5-minute **Undo** (files go to `videos/.trash/`, purged after 15 min), **Download**, **Export all** (zip) and **Import** (videos or a library zip).
  - Videos are copied into the plugin folder (sha256 dedupe: the same video is never stored twice) with a poster and their facts (resolution, fps, frames, duration).
  - Loading puts a copy named after the entry into Control Video, so the stored file is never modified; WanGP's own Control Video handlers (label, trims) keep working.
- **Cropper integration**: crops applied with [Cropper](https://github.com/sweetyshots123/wan2gp-cropper) can be stored in the video library with the crop already applied. New setting **Crops made with Cropper**: *Save automatically* (default) / *Ask each time* (toast with a Save button) / *Don't save*. The same crop is never stored twice.
- Public Python API `wan2gp_reference_library_api` → **`API_VERSION` 2** (v1 functions unchanged): `list_videos()`, `get_video(vid)`, `video_path(vid)`, `add_video(path, name=None, source="cropper", meta=None)`.
- JS events: listens for `reflib:video-add {path, name?, source?, meta?}` and `reflib:video-apply {id}`; emits `reflib:video-applied {id, name, tab}`; `reflib:changed` now also reports `video-added` / `video-renamed` / `video-deleted` / `video-restored` with `kind: "video"`.
- New settings: **Show the video bar under Control Video** (on) and **Crops made with Cropper** (auto). Existing `settings.json` files get the new keys from the defaults.
- Fix: the collection **Export** file was not shown after exporting.
- Fix: **Save settings** switched the tab to English in a Spanish browser with Language = Auto (the browser language was not sent).
- English and Spanish for everything new.
- Note: Prompt Library 1.1.0 only accepted `API_VERSION == 1` and hides its Reference Library links with 1.2.0; Prompt Library 1.2+ accepts any version ≥ 1.

## 1.1.1 — 2026-10-09

- Fix: duplicating a collection in the Spanish UI named it “X (copy)”. Copies are now named in the UI language, “X (copia)” / “X (copy)”, and numbered when that name is taken (“X (copia 2)”, “X (copia 3)”…). Duplicating a copy doesn't pile up suffixes.
- Other server-side fallbacks are translated too: the default name of a new empty collection (“Colección” / “Collection”, numbered if taken), the name of an imported zip without a name (“Colección importada” / “Imported collection”), and the export file name fallback.
- Error messages from storage (image no longer in the collection, missing image or zip, invalid zip, expired undo…) are shown translated instead of raw English text.

## 1.1.0 — 2026-10-08

- Two-way links with [Prompt Library](https://github.com/sweetyshots123/wan2gp-prompt-library) 1.1+ (optional; each plugin still works alone). Prompt Library is the single source of truth for the links (`collections` on each prompt). Reference Library stores no link data.
- Manager tab: a **Linked prompts** / **Prompts asociados** multi-select per collection, with **Save links** / **Guardar vínculos**. It refreshes when Prompt Library changes the links (`promptlib:changed`).
- Bar: loading a collection with linked prompts shows a small **Prompts: …** chip row. Clicking a chip asks Prompt Library to insert that prompt (`promptlib:apply`). The chips only show for collections loaded in the current page.
- New setting **Linked prompts when a collection is loaded**: *Offer* (default, the prompt box is never changed until you click), *Apply the first automatically*, *Do nothing*.
- Public Python API `sys.modules["wan2gp_reference_library_api"]` (`API_VERSION` 1): `list_collections()`, `get_collection(cid)`, `image_paths(cid)`. Collections in the undo trash count as not found.
- JS events: listens for `reflib:apply` `{id, mode?}` (loads the collection into Reference Images and selects it in the bar); emits `reflib:applied` `{id, name, count, tab}` and `reflib:changed` `{reason, id}`.
- All the Prompt Library UI is hidden when Prompt Library is not installed or has no compatible API. It is looked up lazily, so plugin load order doesn't matter.
- English and Spanish for everything new.

## 1.0.2 — 2026-10-08

- Redesigned bar under Reference Images: small header (icon + “Reference Library” + muted status on the same line) and one main row — the dropdown (no big label) grows, buttons have the same height as the dropdown, full text, never truncated. If the column is too narrow the buttons wrap together to a full-width second line (2×2 grid when very narrow), never one orphan.
- Short labels with line icons in WanGP's own style and tooltips: Apply, Save as…, Update, Manage (Aplicar, Guardar como…, Actualizar, Gestionar).
- “Save as…” opens an inline row [name][Save][Cancel] only when needed: Enter saves, Esc cancels, it hides again after saving.
- Status text is small and muted, hidden when empty.
- Panels use WanGP's theme variables, so they match both the dark and the light theme.
- Manager tab: same treatment (aligned toolbar rows, icons, compact thumbnail grid, Delete in red text that turns solid red only when armed and resets after 5 s).
- Fix: reloading the page (or switching language) no longer re-applies the last collection to Reference Images; only a real selection in the dropdown applies.
- CSS moved to `reference_library.css`.

## 1.0.1 — 2026-10-08

- Live language switching (English / Spanish), like Dragger 1.1.0: on page load the browser language relabels the bar and the whole Reference Library tab; saving Language / Idioma applies immediately (no restart).
- Friendlier delete: first click arms the button as “Confirm delete” / “Confirmar borrado” for 5 seconds; second click soft-deletes with an Undo toast.
- Compact bar (single row, shorter “Save as…” / “Guardar como…” label) and denser manager gallery (thumbnails without large preview).
- Fixed UploadButton i18n (`label` instead of `value`) so localize no longer crashed with a 500.

## 1.0.0 — 2026-10-08

- First release: named collections of WanGP **Reference Images**.
- Compact bar under the Reference Images gallery (generate form, optional Edit tab): select, Apply, Save current as…, Update, Manage.
- Settings: replace vs append, auto-apply on select, show bar in Edit tab, confirmation toasts, Language / Idioma (auto / en / es).
- Reference Library tab: create, rename, duplicate, delete, add/remove/reorder images, set cover, export/import zip.
- Collections stored in `collections/` inside the plugin folder (copied files + `collections.json`); never shipped in the zip; survive updates.
- Loads into the gallery through WanGP's own Add/Clear handlers so Remove / Left / Right / Clear keep working.
- English and Spanish UI.

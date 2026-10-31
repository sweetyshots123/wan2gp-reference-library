# Changelog

## 1.7.3 — 2026-10-30

- **Fix: "Borrar de la librería" was disabled for videos in "🎬 Librería de vídeos"** (webcam recordings, crops, resizes, saved inputs). Cause: since 1.6.8 those videos appear in the explorer as read-only items (no watched folder, no collection), so neither the managed-copy delete nor the 1.7.1 "remove from the library" applied to them. They can now be deleted from the explorer:
  - the confirmation lists the Video Library videos, their masks and virtual copies, and says where the file goes (EN/ES);
  - the Video Library entry is soft-deleted; **Undo** (15 min) restores the entry at its old position, with its masks and virtual copies;
  - when the undo window ends the video file goes to the **Recycle Bin** / Trash, never a permanent delete. If it can't be recycled, it stays in `videos/.trash/` and is retried later. This also applies to videos deleted in the Video Library itself (they used to be removed permanently after 15 min);
  - a video that is both in a watched folder and in the Video Library: the folder file stays on disk (as in 1.7.1) and the Video Library copy is deleted.
- **Toasts moved to the top-right** (they were bottom-right, over the explorer's action bar), newest on top, above every Reference Library layer (explorer, dialogs, full-screen viewer). Undo toasts included.
- **New: hover preview in the collection dropdown** above the inputs. Hovering a collection (`name (N)`) shows, after ~150 ms, a small floating card next to the list with up to 8 thumbnails (then `+N`), the name and the count; an empty collection says *Vacía / Empty*. Thumbnails come from the existing thumbnail cache (no originals are sent) and are kept in memory. It never takes the mouse or keyboard (clicks and arrow keys work as before) and hides when the list closes. Dark mode supported.
- Unchanged: the 1.6.5 seed rule, Vidosser, the 1.6.2 Resize button, Media Editor and Cropper (not modified). Plugin only, no WanGP core changes.

## 1.7.2 — 2026-10-26

- **Fix: "Reutilizar ajustes" / "Solo referencias" under the output player sometimes said "Este vídeo no tiene entrada en el historial ni imágenes de referencia incrustadas"** for a video that does have a history entry. Cause: the player plays **Gradio's cached copy** of the output (`…/gradio/<hash>/<name>`), and Gradio cleans up that name (only letters, digits and `._-, ` are kept, so `[Shot 1]` becomes `Shot 1`). The lookup compared the exact path and the file name, so outputs whose name contains such characters were not found. It only happened for some videos, depending on their names.
  - The video is now matched by: exact path → file name → Gradio's cleaned-up name, confirmed by a content signature (size + first/last 64 KB) → size and date (±10 min) plus that signature. A cached copy is mapped back to the original file in the output folder.
  - If there is still no entry, the settings and reference images embedded in the file are used (as before). The entry is then **added to the history** from that metadata ("backfill": the original output path, the file date, its reference images and a poster), so the next time it is found directly. Only from the player bar and only when the history is enabled; if WanGP's own capture arrives later, it replaces the rebuilt entry, with no duplicates.
  - The player bar now reads the big preview, not the first thumbnail of the strip, and tries the selected thumbnail too.
  - Sliding window: a later window is merged into the previous entry only when the seeds don't differ (separate generations with the same prompt are no longer merged).
- Unchanged: the 1.6.5 seed rule (reuse always sets seed -1), Vidosser, the 1.6.2 Resize button, Media Editor (not modified). Plugin only, no WanGP core changes.

## 1.7.1 — 2026-10-22

- **Fix: "Borrar de la librería" was disabled for files from watched folders** (the "carpeta" badge), for videos and audios linked from disk, and for entries whose file no longer exists. It now works for all of them. **It removes only the library entry**: name and metadata, manual and auto tags, thumbnails and cached data, the collection copies of that file, its masks and its virtual copies. **The file on disk is not deleted or moved.** The confirmation lists everything that goes, says so in bold (EN/ES), and offers **Undo**.
  - **"También borrar el archivo del disco / Also delete file from disk"**: an opt-in checkbox in that confirmation. It's **unchecked by default** and only shown when the selected files exist. It lists the files and how many there are. When ticked, the files go to the **Recycle Bin** through the Windows shell (never a permanent delete; on Linux, the desktop Trash). Only files in your own watched folders qualify, never the library's own copies or the plugin's saved-audio folder. Network shares and removable drives have no Recycle Bin, so their files are refused and kept. If a file can't be recycled, it is kept and the toast names it. Undo brings the entry back; restore recycled files from the Recycle Bin.
  - **Each folder remembers the files removed from it**, so a rescan doesn't bring them back. The folder's row in the tree shows **⊘n**, which opens **Mostrar excluidos** with **Restaurar** / **Restaurar todos** (flags: "no está en el disco", "en la Papelera").
  - **Missing files:**
    - entries whose file is gone (deleted outside WanGP, or the drive is disconnected) get an **⚠ archivo no encontrado** badge on the card and a notice with the path in the details;
    - a new **⚠ archivo no encontrado (n)** filter in the type bar;
    - with the filter on, **Quitar todas las que faltan** removes them all, with a confirmation that also names unavailable folders.
  - **Managed copies** (files the library owns: collections, imported images) keep the previous two-click delete, unchanged. In a mixed selection they're deleted in the same step, under the same Undo. Video Library entries are still deleted in the Video Library; the confirmation says when a removed file is also kept there (1.7.3: they can be deleted here too).
- Data: per-folder `exclude` list in `folders/index.json`. Undo records live in `collections/.undo/` for 15 min.
- Unchanged: Vidosser, Media Editor (not modified), the 1.6.2 Resize button, the 1.6.5 seed rule, the 1.6.9 restore and the 1.7.0 masks. Plugin only, no WanGP core changes.

## 1.7.0 — 2026-10-20

- **Mask library per video.** The masks you make in WanGP's **Video Mask** (mask creator / Matanyone, or an upload) are kept in the library, **linked to the Control Video they were made for**. The link is the video's content: the same file loaded from a folder, the Video Library or a staged copy is the same video. A **virtual copy** with a trim or crop has its own masks.
  - **Saved automatically** when Video Mask gets a new value (setting "Keep the masks I make in Video Mask…", on by default). If the Control Video isn't in the library yet, it's added to the Video Library first. Generations that used a Control Video + Video Mask keep their mask too, when the video is already in the library. **🎭 Guardar máscara**, next to 📚 in the Video Mask toolbar, saves it by hand. The same mask is never stored twice for one video. Each save shows a toast with **Deshacer**.
  - **Explorer:**
    - a new type **🎭 Máscaras** and a **🎭 con máscara** filter (only videos that have masks). Masks kept only in the mask library aren't listed under "Vídeos"; a library video assigned as a mask stays in "Vídeos" and also appears under "Máscaras";
    - video cards show a **🎭n** badge, mask cards a **máscara** tag ("Máscara de «vídeo»"), and there's a **🎭 Máscaras** pseudo folder;
    - hovering a mask previews it.
  - **Details of a video** list its masks, newest first:
    - each with a thumbnail, inline ▶ preview, date, size, length, source and an editable name;
    - **Usar con máscara**, and 🗑 with Undo;
    - a ⚠ warning when the mask's **length or size** doesn't match the video. A virtual copy is checked against its trimmed / cropped size, with a tolerance of max(0.25 s, 3 %) and 2 px.
    - Deleting a mask (here or in the browser) **never deletes its video**.
  - **Details of a mask:** «Máscara de «vídeo»», **Usar con su vídeo**, **Mostrar vídeo**, **Asignar como máscara de…** and **Borrar**.
  - **Usar con máscara / Usar con su vídeo** puts the video into **Control Video** and the mask into **Video Mask** in one action, with the 1.6.9 logic: wait for WanGP to settle, send both, check they stayed, and send again if WanGP emptied them. A notice appears if the current model hides Video Mask.
  - **Asignar como máscara de…** (right-click a video or mask, or the mask's details) keeps any library video as a mask of another video. Pick it by double-clicking or with **Asignar a este vídeo**; Esc cancels. Files are never moved.
  - The **Video Mask** library button (1.6.8) now opens on **Máscaras**; plain videos can still be picked.
- **API v6** (v1–v5 unchanged): read-only `list_masks(video_path)`, `get_mask(mask_id)`, `mask_path(mask_id)`.
- Data: `masks/masks.json` + `masks/<id>/<file>` (gitignored, never in the zip). Deleted masks stay in `masks/.trash/` for 15 min (Undo).
- Unchanged: Vidosser, Media Editor (not modified), the 1.6.2 Resize button, 📚 Guardar en librería, the 1.6.8 library buttons, the 1.6.5 seed rule and the 1.6.9 restore. Plugin only, no WanGP core changes.

## 1.6.9 — 2026-10-20

- **Fix: "Reutilizar ajustes" lost the start image, the reference images and the voice on a busy PC.** The settings came back (prompt, model, "Use Reference Images" / start-image / audio options, seed −1), but "Images as starting points", "Reference Images" and the reference audio stayed empty.
  - **Cause:** WanGP loads settings in a chain: settings file → prompt check → form save → `load_settings_from_file` → (model switch) → `refresh_form_trigger` → `fill_inputs`, and `fill_inputs` rewrites **every** input of the form, the media included. Up to 1.6.8 the media of the history entry were sent after a **fixed 3.5 s**. While WanGP is generating (busy CPU / GPU, busy queue), that chain ends later, so `fill_inputs` emptied the media again right after the "Restaurado" toast. The history entries had stored them correctly, and the field names (`image_start`, `image_refs`, `audio_guide`…) were right.
  - **Fix:** the media are sent only once WanGP's load has **really finished**. RL waits for WanGP's settings box to hand the file back, then asks the server whether any step of that chain is still queued or running for this browser tab (a read-only look at Gradio's queue; your running generation doesn't count), then waits for the media inputs to stay still. After sending, RL **checks the media stayed**. Anything WanGP empties again is sent again (up to 4 rounds, with a "volviendo a poner…" notice; if WanGP keeps emptying an input, a message names it).
  - Applies to both ways in: **↺ Reutilizar ajustes** under WanGP's output player, and **Reutilizar todo** in the history panel. **Solo referencias** (player and panel) was checked too: it doesn't reload settings, so it was never affected, and it still adds the refs without touching the start image or the voice.
  - The 1.6.5 seed rule is kept: the seed stays random (−1). If the restore ends late, the seed guard is re-armed unless you've touched the Seed field.
- **Media Editor 1.8.0 checked** with the real build (trim mode, fileApi 3): video virtual copies (new and edit, in/out and crop round-trip, crop limited to the frame, back to full length), audio copies, browser WebM without a duration, cancel and busy, and rendered lengths and sizes. Nothing needed changing.
- Unchanged: Vidosser, Media Editor (not modified), the 1.6.2 Resize button, 📚 Guardar en librería, the 1.6.8 library button. Plugin only, no WanGP core changes.

## 1.6.8 — 2026-10-20

- **Library button on WanGP's video and audio inputs.** Control Video 1/2/3, Video to Continue (Source Video), Video Mask, Voice to follow 1/2/3, Soundtrack and the Voice Samples get the same grid icon as the Reference Images bar. When the input is empty it sits in the top-right corner. When the input has a value it sits in Gradio's toolbar, just before **📚 Guardar en librería**.
  - It opens the media browser in **pick mode** over the whole library, filtered to **Vídeos** (or **Audios** for audio inputs). A banner reads «Elige un vídeo para «Control Video 2»» with **Cancelar**.
  - **Double-click** a video, or select it and press **Cargar en «input»**, and it loads into **that** input. A toast confirms it and the browser closes. Esc or Cancelar leaves without changes, and the browser's previous filters, search and selection come back.
  - Virtual copies load their **render** (with the in/out and crop applied), never the original. The stored file is never handed to WanGP: a staged copy is.
- **Video Library in the media browser.** A read-only **🎬 Librería de vídeos** folder lists the Video Library's own videos (saved with 📚, Media Editor crops, imports). Videos with the same bytes as a watched-folder file are listed once, with both locations. Video-Library-only cards show a **lib. vídeos** badge. They are renamed and deleted in the Video Library, as before.
- The history bridge now reaches every input that has the button (adds Control Video 2/3, Soundtrack and the Voice Samples).
- Unchanged: 📚 Guardar en librería, the 1.6.2 Resize button, Media Editor (not modified; 1.7.0 / fileApi 2 works as before, trim mode with fileApi 3), Vidosser, the 1.6.5 "Reutilizar ajustes" seed rule. Plugin only, no WanGP core changes.

## 1.6.7 — 2026-10-19

- **Fix: the in/out trimmer of a virtual copy was dead on browser / webcam recordings.** Files recorded with a browser's MediaRecorder (Chrome "webcam capture" WebM, also live-written Matroska and audio WebM) store **no duration** in the container: ffprobe reports `N/A` and the browser `Infinity`. 1.6.6 measured 0 s, so the timeline showed a single handle, Entrada / Salida stayed empty, and dragging or Marcar entrada / salida did nothing. Now:
  - The server measures such files by **reading their packet timestamps** with ffprobe (no decoding; about 0.3 s for a 3.5 min / 65 MB clip). This applies to the editor, the cards' duration, Video Library / resize facts and audio.
  - Copies saved by 1.6.6 with a 0 s duration **heal themselves** the next time they're opened or previewed. Durations cached as 0 are measured again once.
  - In the browser, when no duration is known, the trimmer seeks far ahead to make the browser read the real length, then returns to the start.
  - If the duration really can't be found, the trimmer **is never left dead**. A clear message explains it, and the in/out seconds can be typed or set with Marcar entrada / salida while playing.
  - Renders use `-fflags +genpts` for these recordings. An audio-only `.webm` listed as a video renders its sound instead of failing.
- **Media Editor trim mode (fileApi 3).** With a Media Editor that offers `cropFile({mode:"trim", initialTrim, initialRect, allowRect})`, video copies pick in/out **and** the frame crop there, and audio copies pick in/out (no rect). Our own timeline is not shown, editing hands the stored in/out and rect back, and keeping the full length stores no in/out. Older Media Editor (1.7.0 = fileApi 2), none, or an error from it: the built-in trimmer above (error toast first). Image copies keep the 1.6.6 rect mode.
- Unchanged: the 1.6.5 "Reutilizar ajustes" fix (seed always random), Vidosser, the 1.6.2 Resize button. Plugin only, no WanGP core or Media Editor changes.

## 1.6.6 — 2026-10-19

- **Virtual copies (Lightroom-style).** A virtual copy stores only **parameters pointing at the original**: an image **rect**; for video a **rect and/or in/out**; for audio **in/out**. Nothing is duplicated, and the original is never modified. It is rendered **on demand** into a cache (`<plugin>/virtuals/.cache/`) when something needs the pixels: preview, viewer, "Añadir a referencias", Video Library, resize. Changing the params replaces the old render.
- Create one with **"Nueva copia virtual"** (right-click, Detalles panel, viewer). Edit it with **"Editar recorte"**. Copies are named `<name> (copia virtual)` (EN `(virtual copy)`), then `(copia virtual 2)`… A copy of a copy points at the same original.
- **In the browser:** copies show a **"virtual"** badge with a two-squares icon. They live under the pseudo folder **"Copias virtuales"** and work with tags, selection and refs (collections skip them). Their Detalles panel shows **"Original: …"**, the params and **"Mostrar original"**. An original shows a copy count on its card and lists **"Copias virtuales (n)"** in Detalles, one click each.
- **Deleting a copy never touches the original** (Deshacer for 15 min). If the original is gone, the copy is marked **"⚠ rota"** with the missing path; it recovers by itself when the file comes back. Moved files are found again by content hash.
- **Editor:** for video and audio, an **in/out timeline**: handles, number inputs, "Marcar entrada/salida" at the playhead, play selection, keys I / O / Space / Enter / Esc. Audio shows its waveform. Video also has an optional frame rect ("Recortar el encuadre", aspect free / original / 1:1 / 4:3 / 3:4 / 16:9 / 9:16, live readout in px).
- **Media Editor 1.7.0 rect mode (fileApi 2).** Image copies open straight in Media Editor with `cropFile({path, url, kind, name, source:"reference-library", mode:"rect", initialRect})`. It returns only `{ok, rect:{x,y,w,h}, sourceWidth, sourceHeight, …}`: no file is rendered and the original is untouched. Video copies keep the in/out editor; its **"✂ Recortar en Media Editor"** button picks the frame rect in Media Editor (even values) and returns to the editor. "Editar recorte" reopens Media Editor on the stored rect. Rects are in **upright source pixels**: EXIF orientation is applied (`exif_transpose`) before cropping, in the renderer, thumbnails and the reported size, so a rotated phone photo is cut exactly where it was marked. **Fallback:** with Media Editor older than 1.7.0, without it, or if it refuses the file (error toast), the built-in rect tool (8 handles, same aspect presets) is used. Cancel creates nothing.
- **"📚 Guardar en librería" offers "Copia virtual de «original»"** after a Gradio trim, when the pre-trim file is identified as a library file by content hash. Only Gradio's own upload folder is hashed. It then stores just the in/out, with the trim span scaled to the original's duration. Otherwise it saves the trimmed file as in 1.6.4.
- Fix: an unfinished video render while hovering a card no longer shows "Error: unknown"; the browser badge uses a proper SVG icon instead of a font glyph.
- Data: `virtuals/virtuals.json` + `virtuals/.cache/` (git-ignored, safe to delete the cache). Plugin only, no WanGP core changes; Media Editor itself is not modified. Vidosser, the 1.6.2 Resize button and the 1.6.5 "Reutilizar ajustes" fix (seed always random) are unaffected.
## 1.6.5 — 2026-10-19

- **Hotfix: "↺ Reutilizar ajustes" (under WanGP's output player) and "Reutilizar todos los ajustes" (history) loaded the settings into the wrong form.** WanGP 18.18 builds a second, complete generation form in its hidden **Edit** tab (the queue task editor, `#edit-tab-content`), with its own "Load Settings From Media File / Json / Zip" loader identical to the real one. Since 1.6.3 both scored the same and the later one, the Edit tab's, won. WanGP loaded the file into the invisible Edit form. Gradio then printed `UserWarning: A function (fill_inputs) returned too many output values (needed: 332, returned: 333)` with a long dump of components and values, and the Generate form, model included, never changed.
- The loader is now picked from the **Generate** form only. Anything inside the Edit tab is excluded, and the loader on screen in the same tab as the output player wins; a tie goes to the first one. If only the Edit loader can be found, nothing is loaded and you get a clear message instead of a wrong load.
- **Reusing settings never copies the seed (new).** Every reuse path (output-player bar, history "Reutilizar todos los ajustes", the outputs list, the API's `history_settings_file()`) leaves the seed **random (-1)**. The seed is reset in the settings handed to WanGP's loader. The Generate form's generation Seed (Advanced › General) is then held at -1 for a few seconds, because a generated video handed over as a file carries its seed in its metadata and WanGP may re-render the form on a model switch. Touching the Seed field yourself stops it. Stored history is unchanged: entries, and `get_history_entry()`, still record the seed that was used. "Solo referencias" never touched the seed.
- Verified end to end on WanGP 18.18 with a real MiniMax-H3 finetune entry: the model switches, and prompt, resolution, frames, steps and the sliding window come back in the Generate form, plus Refs and Audio 1, while the seed stays -1. Gradio logs no warning. Same-model reloads, generated videos without a history entry and the history panel's button all work.
- Virtual copies move to 1.6.6.

## 1.6.4 — 2026-10-18

- **"📚 Guardar en librería" (Save to library) on WanGP's own audio and video inputs.** It sits in each input's toolbar, after Media Editor's Crop/Resize buttons and before Gradio's own (undo / ✂ trim / ✕). It shows only while the input holds a file. Generate tab: Control Video 1/2/3 (`video_guide*`), Source Video (`video_source`), Video Mask, Audio 1/2/3 (`audio_guide*`), Source Audio and the voice-replacement samples.
- It saves **what the input holds right now**, so after Gradio's built-in trim it saves the trimmed clip. The file is copied **immediately**, because Gradio's temporary uploads get cleaned. The original file is never touched.
- **Video** goes to the **Video Library** (`add_video`, source `wangp-input`). **Audio** goes to the new managed folder **"Audios guardados" / "Saved audio"** (`<plugin>/saved_audio/`). It is created on first use and auto-indexed as a watched folder of the media browser, so saved audio shows up there right away with waveform, duration, tags and "Añadir a".
- A trimmed file is named **`<name> (recorte)`** (EN: `<name> (trim)`), an untouched one keeps its name. Suffixes never stack; a clash becomes `name 2`. Identical content is not saved twice ("Ya está en la librería").
- A toast confirms it with name and duration, with **Deshacer** (Undo): the video goes to the Video Library trash, the saved audio file is removed.
- **How Gradio 5.29 trims (WanGP 18.18):** video trim runs ffmpeg.wasm in the browser (downloaded from unpkg.com on first use) and uploads the result as a new `video.mp4`. Audio trim cuts the wavesurfer region with WebAudio and uploads `audio.wav`. Either way the input's value becomes the new file. If ffmpeg.wasm isn't loaded yet (first use, offline) or the handles weren't moved, Gradio silently keeps the full video. Reference Library detects that from the duration, saves it under its normal name and warns "Gradio no llegó a recortar este vídeo".
- Fix: the "Reutilizar todos los ajustes" loader selector (1.6.3) no longer counts the page itself, or a container of several upload boxes, as "next to WanGP's settings buttons".
- Plugin only, no WanGP core changes. Vidosser, Media Editor and the 1.6.2 Resize button are unaffected.

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

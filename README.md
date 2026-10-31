# Reference Library for Wan2GP

Save WanGP **Reference Images** as named collections and **Control Videos** in a video library, and load them back with one click.

**Version:** 1.7.2 ([changelog](CHANGELOG.md)) · **Author:** [sweetyshots123](https://github.com/sweetyshots123) · **License:** MIT · **Requires:** [Wan2GP](https://github.com/deepbeepmeep/Wan2GP) (Gradio plugin)

[Español → README.es.md](README.es.md)

## What it does

- A compact **bar under the Reference Images gallery**: pick a collection, then Apply, Save as…, Update or Manage. “Save as…” opens a small inline name field (Enter saves, Esc cancels). It follows WanGP's dark and light themes.
- **Rename in place with the pencil**, as in Prompt Library: the pencil inside the bar's collection select (and the video bar, the manager's collection select and the selected video's name in the Videos section) turns the name into a text field. Enter or clicking away saves, Esc cancels; double-click works too. Same validation and messages as the Rename button, which stays in the manager (Prompt Library also keeps its manager Rename).
- A **Reference Library** tab to create, rename, duplicate, delete, add/remove/reorder images, set a cover, and export/import a collection as zip.
- Choosing a collection loads its images into Reference Images through WanGP's own gallery handlers (same as the Add button), so Remove / Left / Right / Clear keep working.
- Collections live in the plugin folder (`collections/`) as copied image files plus an index — they survive WanGP updates and are never overwritten by a plugin update.
- Safe delete: the first click turns **Delete** into a red **Confirm delete** for 5 s; deleting shows an **Undo** toast (Undo works for 5 minutes; deleted files are purged from `collections/.trash/` after 15 minutes).
- A **video library** for Control Videos with its own bar under Control Video and a Videos section in the tab; crops made with Cropper can be saved there automatically. See [Video library](#video-library).
- Optional **[Prompt Library](https://github.com/sweetyshots123/wan2gp-prompt-library) link** (1.1+): each collection can have linked prompts, offered as chips under the bar when you load it. See below.
- English and Spanish (follows the browser language, or force it in settings).

## Video library

Control Videos get their own library, managed the same way as the image collections.

- **Bar under Control Video** (only while WanGP shows Control Video): pick a video (shown as *name · duration · resolution*) to load it, or use **Load**, **Save as…** (inline name; Enter saves, Esc cancels, empty = file name) and **Manage**. A small poster with fps, frames, size and origin shows the selected video.
- **Videos section** in the Reference Library tab: thumbnail grid with captions, a preview player, **Rename**, **Load into Control Video**, **Left / Right** to reorder, **Delete** (two clicks, 5-minute **Undo**), **Download**, **Export all** (zip) and **Import** (video files or a library zip).
- Undoing a delete never creates a duplicate: if the same video (or the same crop) was saved again meanwhile, the existing entry is kept and a message says so.
- Messages appear in the **bottom-right corner**, away from the top-centre toasts of Dragger, Cropper and Prompt Library, so buttons such as *Save to the library* stay clickable.
- Videos are **copied** into `videos/` with a poster and their facts (resolution, fps, frames, duration). The same video (same bytes) is never stored twice; saving it again says which entry already has it.
- Loading places a copy named after the entry into Control Video, so the stored file is never changed. WanGP keeps handling the input as usual (label, *Frames to keep*, trims). *Frames to keep in Control Video* is not part of the entry.
- **Crops from [Cropper](https://github.com/sweetyshots123/wan2gp-cropper)** are stored with the crop already applied, depending on the setting *Crops made with Cropper* (see [Integration](#integration-cropper-and-other-plugins)).

**Why a separate library and not videos inside collections?** Collections are image sets that fill the Reference Images gallery; Control Video is a single input with its own size, fps and length. Keeping videos in their own store (`videos/`, next to `collections/`) means one click loads one video, nothing in the existing collections changes (no migration), and each side has the controls that fit it. The UI is shared: same bar style, same tab, same delete/undo behaviour.

## Image browser (1.4)

The grid icon in the Reference Library bar (and next to the manager's collection select) opens a modal with **every image** the library knows, once per content (sha256):

- **Sources:** all collections, the **unassigned pool** and **watched folders**. A badge shows how many collections use each image (×2), or *unassigned* / *folder*.
- **Filters:** collections (multi-select, *All*, *Unassigned*), folders, tags (all selected tags must match) and a name search.
- **Tags** belong to the image (its hash), so they apply wherever it's used and survive renames, moves and rescans. Select one or more images, type a tag (autocomplete from existing tags; Enter or *Add tag*), remove one with the × on its chip. Stored in `collections/tags.json`.
- **Add to collection…** copies the selection into a collection (default: the one loaded in the bar) or a new one. The same content is never added twice to a collection.
- **Import images** (button or drag-and-drop onto the modal) puts files into the **unassigned pool** (`pool/`), deduplicated against everything in the library. Images removed from their last collection (removed, replaced by Update, or the collection deleted) also stay in the pool. Pool images can be tagged and added to collections; **Delete** (two clicks, *Undo* for 5 min, purged from `pool/.trash/` after 15 min) removes unassigned pool images. Since 1.4.3 any selection can be deleted, see below.
- **Watched folders:** click **Add folder** in the header, type a folder path on the WanGP machine (e.g. `D:\Fotos\refs`; there's no native folder picker in Gradio, so the server validates the path) *Include subfolders* is on by default. Windows paths work as typed or pasted: backslashes, drive letters (`D:` alone means `D:\`), spaces and surrounding quotes. Indexing runs **in the background** right away, with a progress strip and a count toast at the end; the grid fills in as it goes, and thumbnails load lazily as you scroll, so folders with thousands of images don't freeze the page.
- **Recent** (1.4.2): the first entry in the sidebar, above *All images*. It's a view, not a copy: every image newest first, under day headers (*Today*, *Yesterday*, *This week*, then dates), with the exact time on hover and in the preview. Collection and pool images use the date they were added to the library (older entries without it: the file's modification time). Watched-folder images use the later of the file's modification time and when it was first indexed. An image used in several places shows once, with its newest date. It shows the last 30 days (up to 500 images, and at least a screenful); *Show older* extends it. Search, tag and collection filters work inside it.
- **Browse…** (1.4.2) in the *Add folder* panel opens a folder picker served by the WanGP server (it runs on your PC, so it can list your disk): drive letters (or `/`), plus Home, Pictures and the WanGP outputs folder as shortcuts. Click through folders, with a breadcrumb and ↑, and see the subfolders and the number of images in the current folder. **Select this folder** fills the path and adds it (your *Include subfolders* choice is kept). It only reads the disk (`os.scandir`). Folders you can't read and slow or disconnected drives (4 s timeout) show a message instead of hanging. Typing the path still works.
- **Removing and deleting (1.4.3)** work on any selection. With one collection filter active, **Remove from <collection>** takes the images out of that collection only (*Undo*; an image leaving its last collection stays in the pool). **Delete from library** (two clicks; the confirm says how many images and collections) removes them from every collection and from the pool, with *Undo* for 15 min. Watched-folder files are never deleted from disk: folder-only images are skipped, and the button's tooltip says why when nothing else is selected.
- **Selecting (1.4.3):** drag a rectangle over the grid (from empty space or a card, not its checkbox; Ctrl/Cmd+drag adds; auto-scrolls at the edges), Shift+click for a range from the last clicked card, Ctrl/Cmd+click to toggle, Ctrl+A for everything shown, Esc clears the selection and a second Esc closes.
- **Large libraries (1.4.4):** the browser opens instantly whatever the library size. It loads counts, the folder tree and one page of 120 images; filters, search, Recent and sorting run on the server, and the grid is windowed (only the cards near the viewport exist). Thumbnails are requested only for visible cards (6 per request, cancelled when scrolled away), served from the disk cache or made on demand by a low-priority worker (4K JPEGs decoded at reduced size; very large sources get a placeholder). Ctrl+A and *Select shown* mean **all N matching**, without loading them. Opening re-checks folders in the background at most every 10 minutes (*Re-scan* forces it), unchanged files are never re-hashed, and indexing can be paused from the progress strip or the settings.
- **Folder tree** (left sidebar, 1.4.1): every watched root, expandable into its subfolders as on disk, with image counts. Click a folder to filter the grid; *Include subfolders* switches between the whole subtree and that folder only. A breadcrumb above the grid shows the path; click a segment or ↑ to go up. The folder filter combines with the collection and tag filters. Each root has ⟳ (re-scan) and × (remove, two clicks) on hover. Images are **read in place**: never copied, moved, modified or deleted (unless you tick *Also delete file from disk*, 1.7.1: Recycle Bin), so they use no extra space. They're re-scanned whenever the modal opens and with **Re-scan** (unchanged files are not re-hashed). Moved or deleted files just drop out or reappear at their new path; a missing folder is flagged. Adding a folder image to a collection **copies** it, so collections stay self-contained. *Remove* (two clicks) only removes the folder from the index. Index: `folders/index.json`; thumbnails cached in `collections/.thumbs/`.
- **Add to references** (selection footer) appends only the selected images to WanGP's Reference Images through the same gallery path as a collection apply. Images already in the gallery are skipped and nothing is replaced. Folder images are read from where they are; they aren't copied into a collection. *Close after adding* closes the modal afterwards (remembered). If the current model has no Reference Images, you get an error.
- Click an image for a larger preview, its collections, files and tags. **Esc** or **×** closes; the bars and manager refresh.

## Remove from the library, missing files (1.7.1)

- **Borrar de la librería** works for every entry. For files from watched folders, videos/audios linked from disk and entries whose file is gone, it removes only the library entry: metadata, tags, thumbnails/cache, collection copies, masks and virtual copies. **The file on disk is not deleted or moved.** The confirmation lists what goes and offers Undo. The folder remembers the removed files, so rescans skip them: **⊘n** on the folder in the tree → **Mostrar excluidos** → **Restaurar** / **Restaurar todos**.
- **Video Library videos (1.7.3)** (the **🎬 Librería de vídeos** folder: webcam recordings, crops, resizes, saved inputs) can be deleted here too. Their Video Library entry goes, with its masks and virtual copies (listed in the confirmation); **Undo** brings everything back for 15 min. After that the video file goes to the **Recycle Bin** (never a permanent delete; if it can't be recycled it is kept).
- **Collection preview (1.7.3):** in the collection dropdown above the inputs, hover a collection to see up to 8 of its thumbnails (+N), its name and count; empty collections say *Empty*. Clicks and keyboard work as usual.
- **Sorting (1.7.4):** the sort menu in the explorer header orders any folder, collection, filter or search by date modified (newest first by default, or oldest first) or by file name (A–Z / Z–A). It is remembered for the session; set the default in the plugin settings (**Default sort order in the media browser**).
- **Navigation history (1.7.4):** ◀ / ▶ in the explorer header (or Alt+←/Alt+→, or the mouse back/forward buttons) step back and forward through the places you visited (folder, collection, filters, search, sort, scroll). 🕘 lists the last 50 states; click one to jump. Kept for the browser session.
- Toasts (including the Undo toasts) appear **top-right**, above the explorer, its dialogs and the full-screen viewer, so they no longer cover the action bar.
- **Also delete file from disk** (opt-in in that confirmation, unchecked by default, only when the files exist): the listed files go to the **Recycle Bin** (Windows shell; never a permanent delete). Network and removable drives are refused (no Recycle Bin there). A file that can't be recycled is kept and named in the toast.
- **⚠ archivo no encontrado:** a badge on cards whose file no longer exists, a filter in the type bar, and **Quitar todas las que faltan** (with confirmation).
- Managed copies (collections, imported images) keep the two-click delete.

## Mask library per video (1.7.0)

Masks you make in WanGP's **Video Mask** (mask creator / Matanyone, or an upload) are kept in the library **with the Control Video they were made for**. They are linked by the video's content (the same file loaded from anywhere is the same video). A virtual copy with a trim or crop has **its own** masks.

- **Saving:** with **Keep the masks I make in Video Mask in the mask library** on (Settings, default on), a new Video Mask value is kept as a mask of the current Control Video. If that video isn't in the library yet, it is added to the Video Library. Generations that used a Control Video and a Video Mask also keep their mask, when the video is already in the library. Next to 📚 in the Video Mask toolbar, **🎭 Guardar máscara** saves it by hand. The same mask is never stored twice for one video.
- **Explorer:** the type bar has **🎭 Máscaras** and a **🎭 con máscara** filter (only videos with masks). Masks kept only in the mask library aren't listed under Vídeos; a library video assigned as a mask is listed in both. Video cards show **🎭n**, and mask cards a **máscara** tag. Masks also have a **🎭 Máscaras** folder.
- **Details of a video:** **Máscaras (n)**, newest first, each with a thumbnail and ▶ preview, its date, size, length and source, an editable name (Enter saves), **Usar con máscara** and 🗑 (with Undo). A ⚠ warning appears when the mask's **length or size differs** from the video's (a virtual copy is checked against its trimmed / cropped size). Deleting a mask **never deletes the video**.
- **Details of a mask:** «Máscara de «vídeo»», **Usar con su vídeo**, **Mostrar vídeo**, **Asignar como máscara de…** and **Borrar**.
- **Usar con máscara** puts the video into **Control Video** and the mask into **Video Mask** in one action. It uses the 1.6.9 settle → send → check → resend logic, so it works while WanGP is busy. If the current model hides Video Mask, a notice tells you to pick a Control Video option that uses a mask.
- **Asignar como máscara de…** (right-click a video or mask, or the mask's details): pick the video it belongs to (double-click, or **Asignar a este vídeo**; Esc cancels). The file stays where it is.
- The Video Mask library button opens on **Máscaras** (plain videos can still be picked).

## Virtual copies (1.6.6)

A virtual copy is a crop and/or in/out **pointing at a library file**, like a Lightroom virtual copy: no pixels are duplicated and the original is never changed. Images: a rect. Video: a rect and/or in/out. Audio: in/out. Make one with **Nueva copia virtual** (right-click, Detalles, viewer) and change it later with **Editar recorte**. It renders on demand into `virtuals/.cache/` whenever something needs the actual file (preview, refs, Video Library, resize).

Copies carry a **virtual** badge and are listed under **Copias virtuales**. Detalles shows **Original: …** with **Mostrar original**, and the original lists its copies. Deleting a copy never deletes the original. If the original disappears, the copy is shown as **rota** (broken) until the file is back. With **Media Editor 1.7.0+** (`fileApi >= 2`), image rects are picked in Media Editor's rect-only mode (`cropFile({mode:"rect", initialRect})`, nothing rendered), and video copies get a **✂ Recortar en Media Editor** button for the frame rect. Rects are in upright pixels (EXIF orientation applied first). With an older Media Editor, none, or if it refuses the file, a built-in rect tool is used. **1.6.7:** with Media Editor `fileApi >= 3`, video and audio copies are trimmed in its **trim mode** (in/out, plus the frame crop for video) instead of the built-in timeline. Browser / webcam recordings (MediaRecorder WebM) have no duration in the file; it is measured from the packets, and if it still can't be read, the in/out seconds can be typed. After a Gradio trim on an input, **Guardar en librería** offers **Copia virtual de «original»** when the untrimmed file is in the library.

## Load library media into inputs (1.6.8)

Every WanGP video and audio input (Control Video 1/2/3, Video to Continue, Video Mask, Voice to follow 1/2/3, Soundtrack, Voice Samples) has the library's grid icon. It sits top-right when the input is empty, or in its toolbar next to 📚 when the input has a value. The icon opens the media browser filtered to **Videos** (or **Audios**), including the **Video Library** folder and virtual copies. **Double-click** an item, or select it and press **Load into «input»**, to put it into that input. A virtual copy loads its render. Esc / Cancel restores the browser as it was.

## Save inputs to the library (1.6.4)

Every WanGP audio and video input (Control Video 1/2/3, Source Video, Video Mask, Audio 1/2/3, Source Audio, voice samples) gets a **📚 Guardar en librería / Save to library** button in its toolbar while it holds a file. It saves the input's **current** value, so trim it first with Gradio's ✂ (video) or the waveform region (audio) and the trimmed clip is what gets saved. The file is copied at once; the original is never touched.

- **Video** → Video Library. **Audio** → the managed folder **Saved audio / Audios guardados** (`saved_audio/` in the plugin folder), auto-indexed in the media browser.
- Trimmed files are named `name (recorte)` (EN: `name (trim)`); duplicates are recognised. The toast has **Undo**.
- Gradio trims video with ffmpeg.wasm in the browser (loaded from unpkg.com the first time). If it isn't ready, Gradio keeps the full video without saying so; the button notices and saves it under its normal name with a warning. Wait a moment and trim again.

## Resize videos (1.6.2)

**⤡ Resize** to 480p / 720p / 1080p (short side; aspect kept, long side a multiple of 16) from the Control Video bar (replaces the input and saves the result to the Video Library) or from the media browser (right-click, Details, viewer; saved to the Video Library). Never upscales without asking, keeps the audio, never changes the original. Uses NVENC when available, else libx264 CRF 18. Results are named `<name> (720p)`.

## Crop from the browser (1.6.1)

**Recortar / Crop** (right-click, Details panel, viewer) opens [Cropper](https://github.com/sweetyshots123/wan2gp-cropper) 1.5.0+ on the selected image or video. Image crops go to the "Recortes" collection and are selected; video crops go to the Video Library. Without Cropper 1.5.0 the button is disabled.

## Media browser: photos, videos and audio (1.6.0)

Watched folders and Import index images, **videos** (mp4, mov, webm, mkv, avi) and **audio** (wav, mp3, flac, ogg, m4a, aac, opus). The header's **All / Photos / Videos / Audio** buttons (with counts) filter by type. Audio cards show a waveform and duration with ▶ to listen; video cards show a poster, duration and a hover preview. Double-click plays the file in the full-screen viewer; Details has an inline player and codec info. **Add to** offers only what the current model accepts: images → Reference Images, a video → Control video or the Video Library, an audio → the model's audio inputs. Auto-tagging only processes images. Requires ffmpeg/ffprobe (bundled with WanGP) for waveforms and durations.

## Browsing: view selector and viewer (1.5.9)

A click selects (Ctrl/Shift as usual) without opening anything. The header's view selector sets the thumbnail size (very large / medium / small) and toggles **Details**, the right panel with the selected image's info and actions; both are remembered. **Double-click** opens a full-screen viewer: ←/→ step through the current results, **Fit** / **1:1** (keys 0 / 1), Esc closes. Right-click a thumbnail for "Show in Explorer", "Show folder in tree", "Large preview" and "Show details".

## Generation history (1.5.5)

Every generation WanGP makes is recorded: reference images, start/end images, control video, masks, prompt, all settings and the output path (captured through WanGP's `before_metadata_save` plugin hook; nothing in WanGP is modified). Open **🕘 Historial** from the image browser header or the 🕘 button next to the browser button.

- **Reutilizar todos los ajustes / Reuse all settings**: uses WanGP's own "Load Settings From Media File / Json" loader for model, prompt, resolution, steps…, **never the seed** (it stays random, -1; 1.6.5), then puts back refs, control video, masks and start/end images. Also works for videos in WanGP's output folder that have no history entry (WanGP reads the metadata embedded in the file).
- **Reuse references only** (append; tick "Replace" to replace) and **Save refs as collection**.
- Storage: deduped by hash; only in-memory images and temporary uploads are copied (`history/blobs`), stable files are referenced. Size cap (default 2048 MB) and delete with undo.
- **Deleting (1.5.6)**: select entries (click / Ctrl / Shift) and "Delete selected", or use **Delete…** (last hour, last 24 h, last 7 days, everything, custom range). Always confirmed with a count and undoable. Only history records and history-made copies that nothing else uses are removed; outputs and originals are never deleted. The same menu exists in "Used as reference" (images stay in the library).
- Limitations: entries are recorded from 1.5.5 on; if a referenced original file is later moved, that input cannot be restored; start/end images and masks are restored only when WanGP shows them as simple image/video inputs; with a model switch the media restore runs ~3.5 s after WanGP's own load.

The **Used as reference** view (left column, under Recientes) lists every image that ever landed in Reference Images, from any source, deduped by hash, with last-use date and use count, grouped by day. Images that were not in the library (uploads, Dragger) are added to the pool ("Sin colección"). Entries can be removed (selected or all) without touching the images.

The ⛶ button next to the browser's X switches to full screen (more columns); to make it the default, turn on "Always open the image browser full screen" in the Reference Library settings.

Under WanGP's output player there is a small bar with **Reuse settings** and **References only** for the video shown in the player (history entry if any, otherwise the metadata embedded in the file). **1.7.2:** the player shows Gradio's cached copy of the output, whose name Gradio cleans up (for example `[` and `]` are dropped); the video is matched to its history entry by path, name, Gradio's cleaned-up name and a content signature, or by size and date plus that signature. If no entry exists but the file has WanGP metadata, the entry is rebuilt from it (with its embedded reference images) and saved in the history. It sits below the player and has no shortcuts, so it does not interfere with Vidosser.

When settings come from a history entry, its start image, reference images, voice and control media are put back once WanGP has finished loading the settings and refreshing the form, even while it is generating. They are then checked and sent again if WanGP emptied them (1.6.9). The seed is never copied: it stays random (-1).

**The seed is never reused (1.6.5).** Every way of reusing settings (output-player bar, history, outputs list, `history_settings_file()` in the API) leaves the seed random (`-1`). The seed is reset in the settings handed to WanGP's loader, and the Generate form's Seed field is kept at -1 for a few seconds after the load (a generated video handed over as a file still carries its seed in its metadata). Touching the Seed field yourself stops this. The history still records the seed that was used.

The browser search also matches folder names and paths of watched folders and subfolders; the autocomplete lists matching folders (📁) and picking one selects it in the tree.

## Paid cloud models (1.5.3)

Optional, **off by default**: pick the model in the auto-tag ⚙ settings *and* tick its own "Enable" box. Keys come from
`GEMINI_API_KEY` / `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` or the masked settings fields (never logged). Model ids are editable.

| Backend | Model id (verified 2026-10-11) | Default price, USD / 1M tokens (in · out · cache read) | Notes |
| --- | --- | --- | --- |
| Gemini 3.8 Flash (recommended) | `gemini-3.8-flash` | 0.75 · 3.75 · 0.075 | JSON schema, safety BLOCK_NONE, context cache, optional Batch API (−50 %). **Google doubles the price on 1 Jan 2027.** |
| GPT-6.1 Sol | `gpt-6.1-sol` | 2 · 10 · 0.10 | strict `json_schema`, prompt caching, optional Batch API (−50 %). |
| Claude Opus 5.5 | `claude-opus-5-5` | 4 · 20 · 0.20 | **clothed photos only**; tool-use JSON + prompt caching. |
| Claude Sonnet 5.5 | `claude-sonnet-5-5` | 2 · 10 · 0.10 | **clothed photos only**; same as Opus. |

Rules for every cloud model: photos flagged "Review › explicit content" or "appears under 18" (or in review) are **never
uploaded**, always tagged locally; untagged photos get the local fast tagger first. Claude only receives photos whose
coverage is *clothed* with no semi-nude, nude, topless, lingerie or swimwear tag; the rest fall back to local with a note.
Refusals / safety blocks fall back to local per image and are counted. Uploads are downscaled to 1024 px and re-encoded
without EXIF/GPS. Before a job a dialog shows the token accounting (image, taxonomy prompt with/without cache, ~500 output
tokens, batch discount) and the estimated cost; after it, the real cost from the providers' usage fields.

Provider policies (read them before sending nude photos):
- **Google Gemini API** — paid tier: not used for training, kept ~55 days for abuse monitoring; the sexual-content filter can be lowered, sexual content involving minors is always blocked. [Terms](https://ai.google.dev/gemini-api/terms) · [Use policy](https://policies.google.com/terms/generative-ai/use-policy)
- **OpenAI API** — not used for training by default, kept up to 30 days for abuse monitoring; adult sexual content may be refused; mass explicit uploads risk suspension. [Enterprise privacy](https://openai.com/enterprise-privacy/) · [Usage policies](https://openai.com/policies/usage-policies/)
- **Anthropic API** — not used for training, deleted within 30 days (longer if flagged); the usage policy forbids sexual content, hence clothed-only. [Privacy](https://privacy.anthropic.com/) · [Usage policy](https://www.anthropic.com/legal/aup)

## Browser clicks, Show in folder, nested tags (1.5.2)

- **Tagging status** (1.5.4): per-card badges (queued / processing / done / failed / local), a "Tagging status" facet and clickable counts in the job bar; "Retry failed" re-queues failures (persisted in `job_status.json`).

- **Show folder in tree** (1.5.3): preview button / right-click → the folder tree opens at the image's sub-folder, the grid filters to it and scrolls to the image; the preview shows a clickable folder breadcrumb. Collection images highlight their collection chip.
- A plain click on an already-selected image keeps a multi-selection (1.5.3).

- Click selects one image and shows it; Ctrl+click toggles, Shift+click selects a range, double-click opens a large preview, and a click on empty space clears the selection.
- Right-click a card (or use the preview button) for **Show in folder**. It only works when the browser runs on the WanGP PC.
- **My tags** is a tree: create your own top-level categories, sub-categories at any depth (also inside built-in ones) and tags at any level. Drag to move nodes, and every change can be undone.
- Images where a model reports explicit sexual activity get a single **Review › explicit content** flag and no body-shape measurements, so you can find and remove them.

## Export / import your taxonomy (1.5.8)

In **Auto-tag settings › My tags**: **Export taxonomy** downloads the full taxonomy (built-in + yours, bilingual, with synonyms) or only yours, as JSON or CSV (`path, es, en, synonyms`). **Import…** takes a JSON export (or a `user_taxonomy.json`) and either merges it or replaces your own nodes. Every node passes the same checks and blocklist as the editor; rejected ones are listed with the reason. You confirm the counts first, and you can undo. Your tags are stored in `user_taxonomy.json` in the plugin folder (`plugins/wan2gp-reference-library/`).

## Filters, autocomplete and your own tags (1.5.1)

- **Active filter chips** under the search box show every filter at a glance. × removes one and "Clear all" removes everything. Clicking an auto-tag chip finds it in the tree, and = / ≠ switches between include and exclude. Tags in the same group match any of them (or), and different groups must all match (and).
- **Autocomplete**: type "sen" to get "Pose › sentada" with its image count. ↑/↓ and Enter/Tab add it as a chip, and Esc closes the list.
- **Apparent age (estimated)**: 18–24 … 65+ bands and a ± estimate, adults only; search for it with `edad 30-40`.
- **My tags**: auto-tag settings (⚙) → "My tags" creates your own groups and tags with synonyms. They're stored in `user_taxonomy.json` and kept across updates. Add them to an image from the preview, and they work in facets, chips, search and autocomplete. Anatomy and minor-related tags are refused.

## Auto-tagger (1.5.0)

Select images in the browser and click **Auto-tag** (Ctrl+A = all matching images). A background job tags them with
a local model (default: WD-EVA02 tagger + Qwen2.5-VL-7B, plus a body-shape pass); it waits while WanGP is generating,
gives the GPU back, can be paused / cancelled, and unloads the models when idle or with **Free GPU**. Then:

- search by any tag, its synonyms and its parent / child terms in English or Spanish ("arena", "pelo corto",
  "curvy"); numeric body searches like `cintura<65`, `90-60-90 ±5`, `ratio cintura/cadera<0.72`, `cadera:media`;
- the **Auto tags** sidebar panel lists the taxonomy categories with counts (click to filter) and range filters for
  the estimated body values;
- the preview shows each auto tag with its confidence and source (✓ accept, × remove, ↺ restore; your edits survive
  re-runs) and a **Body shape** panel: estimated bust / waist / hip / thigh bands in cm, ratios, waist definition,
  curvature, proportions and silhouette widths, all labelled *estimated*, plus a height field (per image or for the
  collection) that rescales them;
- only new or changed images are tagged again; auto tags are stored apart from your manual tags (`autotags.json`).

Adults only: an image the model thinks may show someone under 18 keeps no body or nudity tags and is marked for
review. Cloud classifiers (OpenAI-compatible, Gemini, Grok, OpenRouter Jev) exist but are off by default.
Details — taxonomy, model comparison, body-shape method and its limits, cloud, install: **[AUTOTAG.md](AUTOTAG.md)**.

## Install

1. In WanGP → **Plugins** → paste this repo URL and install, **or** unzip a release into `Wan2GP/plugins/wan2gp-reference-library/`.
2. Enable **Reference Library**, click **Restart**, reload the page.
3. Auto-tagger (optional): `pip install kornia` in WanGP's environment; models download on first use (≈ 18.7 GB, asked first). See [AUTOTAG.md](AUTOTAG.md#install-on-the-pc-wangps-own-venv).
4. Open a model that shows **Reference Images** (e.g. Inject Frames / Appearance Reference). The bar appears under that gallery. The video bar appears under **Control Video** when a Control Video mode is selected.

## Language

English and Spanish. **Auto** follows the browser language and relabels the bar and the tab as soon as the page loads (and again when you save Language / Idioma). No WanGP restart needed.

## Settings (Reference Library tab)

| Setting | Default | Meaning |
|---|---|---|
| When loading a collection | Replace | Replace current references, or append |
| Apply automatically when selecting | On | Selecting a collection or a video in the bars loads it immediately |
| Also show the bars in the Edit tab | On | Queue Edit form |
| Show the video bar under Control Video | On | The video library bar |
| Image crops made with Cropper | Save automatically | *Save to the “Crops” collection automatically* / *Ask each time* / *Don't save*. Start/end, reference and control images; never twice in a collection. |
| Crops made with Cropper (videos) | Save automatically | *Save to the video library automatically* / *Ask each time* (toast with a Save button) / *Don't save*. The same crop is never stored twice. |
| Confirmation messages | On | Toasts on load/save (errors always show) |
| Language / Idioma | Auto | Auto / English / Español |
| Linked prompts when a collection is loaded | Offer | *Offer them* (chips under the bar) / *Apply the first linked prompt automatically* / *Do nothing*. Only shown when Prompt Library 1.1+ is installed. |

## Integration with Prompt Library

With [Prompt Library](https://github.com/sweetyshots123/wan2gp-prompt-library) **1.1 or newer** installed and enabled, collections and prompts can be linked in both directions. Each plugin keeps working on its own. Without Prompt Library (or with an older version), none of this UI is shown.

- **Manager tab:** a **Linked prompts** multi-select under the collection lists Prompt Library's prompts by title. Pick the ones that go with the collection and press **Save links**. Prompt Library shows the same link from its side (its *Collections* selector), and editing it there refreshes this selector.
- **Bar:** when you load a collection that has linked prompts, a small row **Prompts: …** appears under the bar. Click a chip to put that prompt in WanGP's prompt box (Prompt Library inserts it, and asks for template variables if it has any).
- **Your prompt is never overwritten silently.** With the default *Offer*, the prompt box only changes when you click a chip. *Apply the first linked prompt automatically* is opt-in.
- **Where the links live:** only in Prompt Library's `library.json` (`collections: [collection ids]` on each prompt). Reference Library stores no link data. Deleting a collection doesn't touch Prompt Library; undoing the delete brings the links back.

## Integration: Cropper and other plugins

Reference Library never imports other plugins and they never need to import it. Everything goes through a module registered in `sys.modules` (looked up lazily at call time, because plugin load order isn't guaranteed) or through `window` events. If Reference Library is missing or disabled, the lookup returns `None` and the other plugin just skips the call.

**Cropper → video library.** When Cropper applies a crop to a video input, it can hand the result over:

```python
import hashlib, sys

def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

def _offer_to_reference_library(out, src, spec, name):
    api = sys.modules.get("wan2gp_reference_library_api")      # lazy: never at import time
    if api is None or getattr(api, "API_VERSION", 0) < 2:
        return None                                            # not installed / too old: nothing to do
    try:
        return api.add_video(out, name=name, source="cropper", meta={
            "crop": [spec["x"], spec["y"], spec["w"], spec["h"]],
            "out": [spec["out_w"], spec["out_h"]],
            "source_file": src,
            "dedupe_key": f"{_sha256(src)}|{spec['x']},{spec['y']},{spec['w']},{spec['h']}|{spec['out_w']}x{spec['out_h']}",
        })
    except Exception:
        return None                                            # never let the library break a crop
```

- Call it right after the crop file is written and before returning the updates to Gradio. Only for video outputs. Not for the cropped mask (`video_mask`) and not on Undo.
- `add_video` copies the file into `videos/` (Cropper may clean its own temp files later) and **never raises**. It returns the new or existing video id, or `None` (setting *Don't save*, *Ask each time*, or an unreadable file).
- Reference Library applies the user's **Crops made with Cropper** setting (*Save automatically* / *Ask each time* / *Don't save*), shows the toast in the UI language when the crop lands in the input, selects it in the video bar and skips duplicates (same bytes, or same `meta["dedupe_key"]`). Cropper doesn't need any JS for this.
- Without a Python hook, the JS path does the same: `window.dispatchEvent(new CustomEvent("reflib:video-add", {detail: {path, name, source: "cropper", meta}}))`.

**Cropper → image crops (API v3, Reference Library 1.3).** Cropper 1.2 also crops Start/End images, Reference Images and the Control Image. Hand each result over the same way:

```python
def _offer_image_to_reference_library(out, src, spec, name, target):
    api = sys.modules.get("wan2gp_reference_library_api")      # lazy: never at import time
    if api is None or getattr(api, "API_VERSION", 0) < 3:
        return None                                            # not installed / older than 1.3: nothing to do
    try:
        return api.add_image(out, name=name, source="cropper", meta={
            "crop": [spec["x"], spec["y"], spec["w"], spec["h"]],
            "target": target,                                  # "image_start" / "image_end" / "image_refs" / "image_guide"
            "source_file": src,
            "dedupe_key": f"{_sha256(src)}|{spec['x']},{spec['y']},{spec['w']},{spec['h']}|{spec['out_w']}x{spec['out_h']}",
        })                                                     # collection_id=None -> the "Crops" collection
    except Exception:
        return None
```

- **Where images go.** `collection_id` when it names a live collection; otherwise an automatic **“Crops” / “Recortes”** collection, created on first use and named in the UI language (“Recortes 2” if you already have a “Recortes”). Its id is remembered, so renaming it is fine. *Why not the collection loaded in the bar?* That collection is curated by the user and may have been loaded for something else; adding crops to it silently would change it behind their back, and two clicks of Apply would then load the crops too. One predictable place is easier to find and clean up. Cropper (or a future option) can still target a collection explicitly.
- `add_image` copies the file and **never raises**. It returns `{collection_id, collection_name, file, path, created}` (`created=False` when that collection already had it) or `None` (*Don't save*, *Ask each time*, or not an image).
- It follows its **own** setting **Image crops made with Cropper** (*Save to the “Crops” collection automatically* / *Ask each time* / *Don't save*), separate from the video one. The toast (with the **Save to the collection** button in *Ask* mode) appears when the cropped image lands in one of the image inputs. The Control Image is a PIL image without a file name, so there the newest crop notice (< 20 s) is used.
- **Duplicates:** never twice in the same collection: same bytes (sha256) or same `meta["dedupe_key"]`. Collections in the undo trash don't count. **Restore-aware:** if you delete the “Crops” collection, crop again (a new one is created) and then **Undo** the delete, the newer collection is merged back into the restored one (duplicates skipped) and removed, and a message says how many crops were moved.

**Python API** (`sys.modules["wan2gp_reference_library_api"]`, **`API_VERSION` 6**; check `>= 1` for collections only, `>= 2` for videos, `>= 3` for `add_image`, `>= 4` for `list_images` / tags, `>= 5` for the generation history, `>= 6` for masks, below):

| Function | Returns |
|---|---|
| `API_VERSION` | `6` (v1–v5 functions unchanged) |
| `list_collections()` | `[{id, name, count, cover_path or None, updated}]`, sorted by name |
| `get_collection(cid)` | `{id, name, count, cover_path, updated, created, images: [absolute paths]}` or `None` |
| `image_paths(cid)` | absolute image paths in collection order, `[]` if not found |
| `list_videos()` | `[{id, name, path, poster_path, width, height, fps, frames, duration, size, source, meta, created, updated}]` in library order |
| `get_video(vid)` | the same dict, or `None` (unknown or in the undo trash) |
| `video_path(vid)` | absolute path of the stored file (read-only), or `None` |
| `add_image(path, name=None, source="cropper", meta=None, collection_id=None)` | `{collection_id, collection_name, file, path, created, name, meta}` (`name`, `meta` since 1.4) or `None`; never raises. The full `meta` is stored with the image. Target collection or the automatic “Crops” collection; follows the image-crop setting for `source="cropper"`; deduped per collection by sha256 and `meta["dedupe_key"]`. |
| `list_images(tag=None, collection_id=None, unassigned=False)` | (v4) `[{hash, name, names, path, collections: [{id, name}], tags, unassigned, folders: [{id, path}]}]`, one per content; filters by tag (case/accent-insensitive), collection or unassigned pool. `path` is read-only (it can be a file in a watched folder). Never raises. |
| `list_tags()` / `image_tags(sha256)` | (v4) `[{tag, count}]` / `["tag", …]` |
| `image_crop_policy()` / `crop_policy()` | `"auto"`, `"ask"` or `"off"` (images / videos) |
| `add_video(path, name=None, source="cropper", meta=None)` | video id or `None`; never raises. `source="cropper"` follows the crop setting; any other source always saves. `name` defaults to the file name. `meta` is a small JSON-able dict (≤ 4 KB) stored with the entry. |

**Mask API (API v6, Reference Library 1.7.0).** Read-only, never raises, returns copies.

| Function | Returns |
|---|---|
| `list_masks(video_path) -> list[dict]` | the masks kept for that video (any copy of the same file), newest first: `[{id, label, path, video, video_name, w, h, dur, created, source}]`; `[]` when unknown |
| `get_mask(mask_id) -> dict \| None` | one mask (same shape), or `None` |
| `mask_path(mask_id) -> str \| None` | absolute path of the mask file (read-only), or `None` |

**Generation history API (API v5, Reference Library 1.6.3).** Read-only access to the generation history plus a hook called after every saved generation. All functions **never raise** (errors are printed, the result is `None` / `False` / `[]`) and return **copies**: changing them changes nothing in the library. All paths are **absolute**; a path is `None` when that file is gone.

| Function | Returns |
|---|---|
| `get_history_entry(eid: str) -> dict \| None` | the entry (shape below), or `None` |
| `find_history_by_output(path) -> dict \| None` | the entry that produced this output file (exact path, else same file name), or `None` |
| `latest_history_entry() -> dict \| None` | the newest entry, or `None` when the history is empty |
| `history_settings_file(eid=None, video=None) -> str \| None` | a JSON settings file for WanGP's *Load Settings From Media File / Json*, from entry `eid` or for output `video` (its entry, else the metadata embedded in the file). Written to the temp folder. The seed in it is always `-1` (1.6.5). |
| `on_history_entry(callback) -> str \| None` | token (`None` if `callback` isn't callable). `callback(entry)` runs right after an entry is saved, with `"updated": True` when a sliding-window continuation updated the previous entry (same `id`) instead of adding one. Each callback gets its own copy and runs in its own `try/except`: an exception is printed and never breaks the capture or the other callbacks. Synchronous on WanGP's saving thread, so hand heavy work to a thread. |
| `off_history_entry(token) -> bool` | `True` if that listener was removed |
| `media_fields() -> list[str]` | the input fields recorded in `media`: `image_refs, image_start, image_end, video_guide, video_mask, image_mask, image_guide, video_source, audio_guide, audio_guide2, audio_guide3` |

Entry shape (`updated` only in `on_history_entry` payloads):

```json
{
  "id": "6604566dfb8e41a88f2a66baa6afa273",
  "ts": 1792271461.097842,
  "output": ["/path/to/Wan2GP/outputs/2026-10-17-23h11m01s_seed424242_a woman walking.mp4"],
  "model_type": "vace_14B",
  "prompt": "a woman walking in the city",
  "settings": {"prompt": "a woman walking in the city", "seed": 424242, "num_inference_steps": 12, "resolution": "832x480",
               "image_prompt_type": "L", "keep_frames_video_source": "", "sliding_window_overlap": 5, "...": "..."},
  "media": {
    "image_refs": [{"h": "73042f6e…", "kind": "image",
                    "path": "/path/to/plugins/wan2gp-reference-library/history/blobs/73042f6e….png",
                    "thumb_path": "/path/to/plugins/wan2gp-reference-library/history/thumbs/73042f6e….jpg"}],
    "video_guide": [{"h": "85062480…", "kind": "video", "path": "/path/to/…/history/blobs/85062480….mp4",
                     "thumb_path": "/path/to/…/history/thumbs/85062480….jpg"}]
  },
  "poster_path": "/path/to/…/history/thumbs/out_6604566dfb8e41a88f2a66baa6afa273.jpg",
  "video_source": "/path/to/Wan2GP/outputs/2026-10-17-23h05m40s_seed111_first shot.mp4",
  "video_source_original": "/path/to/Wan2GP/outputs/2026-10-17-23h05m40s_seed111_first shot.mp4",
  "updated": false
}
```

- `settings` are WanGP's settings as saved in the output's metadata, and always contain **`image_prompt_type`**, **`keep_frames_video_source`** and **`sliding_window_overlap`**. WanGP's metadata cleaning can drop them (for example `keep_frames_video_source` when the source video isn't used), so they are also taken from WanGP's own generation values. The metadata value wins when both exist. `None` when unknown, e.g. entries recorded before 1.6.3.
- **`video_source`** is the source video WanGP really used, as an absolute path. In **"L" mode** (*Continue last video*) WanGP resolves it to the previous output before generating, and that resolved path is what's recorded, so `find_history_by_output(entry["video_source"])` gives the parent shot. It points to the original file when it still exists, else to the history's own stored copy, else `None`. `video_source_original` is the recorded path even when the file is gone (`None` for older entries).
- `media` paths point to the history's stored copies (`history/blobs`), or to the original file for large inputs that are only referenced.

```python
import sys, threading

def _rl():
    api = sys.modules.get("wan2gp_reference_library_api")      # lazy: never at import time
    return api if api is not None and getattr(api, "API_VERSION", 0) >= 5 else None

def _on_entry(entry):                                          # runs on WanGP's saving thread: keep it fast
    threading.Thread(target=index_scene, args=(entry,), daemon=True).start()

api = _rl()
token = api.on_history_entry(_on_entry) if api else None
# later: api.off_history_entry(token)

# chain a continuation back to its parent shot
e = api.latest_history_entry()
parent = api.find_history_by_output(e["video_source"]) if e and e["video_source"] else None
```

Ids are `uuid4().hex` and survive renames. Reference Library consumes `sys.modules["wan2gp_prompt_library_api"]` the same way (`list_prompts()`, `prompts_for_collection(cid)`, `set_collection_prompts(cid, prompt_ids)`). Prompt Library 1.1.0 only accepted `API_VERSION == 1` and hides its links with Reference Library 1.2.0; use Prompt Library 1.2 or newer.

**JS events** (on `window`):

| Event | Direction | Detail |
|---|---|---|
| `reflib:apply` | listened | `{id, mode?: "replace" \| "append"}`: selects the collection in the generator bar and loads it into Reference Images, with a toast. |
| `reflib:applied` | emitted | `{id, name, count, tab}` after a collection is loaded. |
| `reflib:video-add` | listened | `{path, name?, source?, meta?}`: adds a video file (same rules as `add_video`). |
| `reflib:video-apply` | listened | `{id}`: loads that video into Control Video and selects it in the video bar. |
| `reflib:video-applied` | emitted | `{id, name, tab}` after a video is loaded. |
| `reflib:changed` | emitted | `{reason, id}` after any change. Collections: `create`, `rename`, `delete`, `images`, `restore`, `duplicate`. Videos (with `kind: "video"`): `video-added`, `video-renamed`, `video-deleted`, `video-restored`. |
| `promptlib:apply` | dispatched | `{id, source: "reference-library", collection_id, tab, auto}` when a prompt chip is clicked. |
| `promptlib:changed` | listened | Refreshes the *Linked prompts* selector and the chips. |

`window.referenceLibrary.version` gives the plugin version.

## Data layout

```
plugins/wan2gp-reference-library/
  plugin.py, promptlink.py, reference_library.js, reference_library.css   # the WanGP adapter (UI, busy check, gallery hand-off)
  storage.py, videostore.py, imagestore.py, imagelib.py, media.py, api.py # aliases of reflib_core.* (old imports keep working)
  reflib_core/           # the engine: no Gradio / WanGP imports, CLI, FORMAT.md, requirements.txt (1.5.0)
  settings.json          # your preferences (not in the zip)
  autotags.json          # auto tags + body estimates (1.5.0, versioned format "reflib-autotags" v1)
  autotag_settings.json  # tagger settings incl. API keys (1.5.0)
  user_taxonomy.json     # your own groups/tags, merged over the shipped taxonomy (1.5.1)
  models/                # downloaded tagger models (1.5.0)
  collections/
    collections.json     # index
    tags.json            # image tags by sha256 (1.4)
    .thumbs/             # cached thumbnails (1.4)
    .crops.json          # id of the automatic "Crops" collection (1.3)
    <id>/
      <sha256>.png       # copied images
  pool/                  # unassigned images (1.4): pool.json + <sha256>.<ext>, .trash/
  folders/
    index.json           # watched folders + file index (files stay where they are) (1.4)
  saved_audio/           # "Saved audio" (1.6.4): audio saved from WanGP inputs, managed + auto-indexed watched folder
  virtuals/              # virtual copies (1.6.6): virtuals.json (params) + .cache/ (renders, safe to delete)
  masks/                 # mask library (1.7.0): masks.json (mask -> video key, label, facts) + <id>/<file>, .trash/
  videos/
    videos.json          # index (order, names, facts, source, meta)
    <id>/
      video.mp4          # copied video (original extension)
      poster.jpg
    .trash/              # deleted videos, restorable for 5 min, purged after 15 min
```

`settings.json`, `autotags.json`, `autotag_settings.json`, `models/`, `collections/`, `videos/`, `saved_audio/`, `virtuals/`, `masks/`, `pool/` and `folders/` are gitignored and excluded from release zips. New settings are added from the defaults; existing data is never migrated.

## Standalone use (reflib_core)

Everything that is not WanGP UI lives in `reflib_core/` (collections, pool, watched folders, index, thumbnails,
videos, manual and auto tags, Recent, search, the public API, the tagger, the job queue). It has no Gradio or WanGP
imports, its own `requirements.txt`, a documented and versioned storage format (`reflib_core/FORMAT.md`) and a CLI:
`python -m reflib_core --data DIR tag <folder>` / `search "<query>"`. A standalone app calls
`reflib_core.configure(data_dir)` and uses the same modules; see `reflib_core/README.md`. The plugin keeps its
data in its own folder, so a standalone app can point at that folder and see the same library.

## Coexistence

Works alongside [Dragger](https://github.com/sweetyshots123/wan2gp-dragger), [Vidosser](https://github.com/sweetyshots123/wan2gp-vidosser), [Prompt Library](https://github.com/sweetyshots123/wan2gp-prompt-library) (1.2+) and [Cropper](https://github.com/sweetyshots123/wan2gp-cropper). Separate CSS/JS namespaces (`reflib-*` / `window.referenceLibrary`). Dragger's drop/paste and per-thumbnail X still work on images loaded from a collection.

## Hard rule

Plugin only — never modifies Wan2GP core files.

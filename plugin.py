"""Reference Library - named collections of WanGP Reference Images.

Saves the images currently in the Reference Images gallery (`image_refs`) as a
named collection on disk (copied into the plugin folder), and loads a collection
back into that gallery through WanGP's own AdvancedMediaGallery handlers
(`_on_clear` / `_on_add`), so form state stays consistent with Add / Remove /
Left / Right / Clear.

UI
  * Compact bar injected under the Reference Images gallery (generate form, and
    optionally the queue Edit tab): pick a collection, Apply / Save as / Update.
  * "Reference Library" tab: settings + full manager (create, rename, duplicate,
    delete, add/remove/reorder images, set cover, export/import zip).

Video library (1.2): a second compact bar under the Control Video input saves the current control video under a name
and loads it back with one click; the tab has a Videos section (rename, reorder, delete with undo, import/export).
Crops made with Cropper are saved into it through the public API (`add_video`, API_VERSION 2), following the
"Crops made with Cropper" setting. Videos live in `videos/`, next to `collections/`.

Bilingual English / Spanish (auto by browser language, or forced in settings).
"""
from __future__ import annotations

import copy
import html
import json
import zipfile
import math
import re
import os
import shutil
import sys
import threading
import time
import traceback
import uuid

import gradio as gr

from shared.utils.plugins import WAN2GPPlugin

from . import storage
from . import videostore
from . import media
from . import imagestore
from . import imagelib
try:   # the core is host-agnostic; give it WanGP's ffmpeg/ffprobe resolver
    from shared.utils.video_decode import resolve_media_binary as _rmb
    media.BINARY_RESOLVER = _rmb
except Exception:
    pass
from . import api as _public_api
from .reflib_core.autotag import AutoTagService
from .reflib_core import taxonomy as _taxonomy


def _wgp_busy() -> bool:
    """WanGP is generating (or has queued tasks): the auto-tagger waits and gives the GPU back. Read-only peek at
    wgp's module globals; never imports wgp."""
    import sys as _s
    mod = _s.modules.get("wgp") or _s.modules.get("__main__")
    try:
        return bool(getattr(mod, "gen_in_progress", False)) or bool(getattr(mod, "global_queue_ref", None))
    except Exception:
        return False


_AUTOTAG = None


def autotag_service() -> AutoTagService:
    global _AUTOTAG
    if _AUTOTAG is None:
        _AUTOTAG = AutoTagService(os.path.dirname(storage.COLLECTIONS_DIR), busy=_wgp_busy)
    return _AUTOTAG
from . import promptlink

# Public read-only API for other plugins (Prompt Library). Registered at load; callers look it up lazily.
_public_api.register()

PLUGIN_VERSION = "1.6.5"
_PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
SETTINGS_PATH = os.path.join(_PLUGIN_DIR, "settings.json")
TAB_IDS = ("generate", "edit")
LANGS = ("en", "es")

# ---------------------------------------------------------------------------- i18n
TEXT = {
    "en": {
        "intro": "Save the images in **Reference Images** as named collections and load them back with one click. "
                 "Collections are stored in the plugin folder (`collections/`) and survive WanGP updates. "
                 "A compact bar appears under the Reference Images gallery. "
                 "The **video library** keeps control videos the same way (bar under Control Video, Videos section below; "
                 "stored in `videos/`), including crops made with Cropper.",
        "language": "Language / Idioma",
        "language_info": "Auto = the browser language (Spanish if it is Spanish, English otherwise). Applies immediately.",
        "lang_auto": "Auto (browser language)",
        "sec_apply": "### Applying collections",
        "sec_bar": "### Bars",
        "sec_messages": "### Messages",
        "replace_mode": "When loading a collection",
        "mode_replace": "Replace current references",
        "mode_append": "Append to current references",
        "auto_apply": "Apply automatically when selecting a collection or a video in the bars",
        "show_edit": "Also show the bars in the queue Edit tab",
        "toasts": "Confirmation messages",
        "toasts_info": "Errors are always shown.",
        "toast_s": "Duration (seconds)",
        "sec_prompts": "### Prompt Library",
        "on_apply_prompts": "Linked prompts when a collection is loaded",
        "on_apply_prompts_info": "Offer = show them as chips under the bar (the prompt box is never changed until you click one).",
        "oap_offer": "Offer them (chips under the bar)",
        "oap_apply_first": "Apply the first linked prompt automatically",
        "oap_off": "Do nothing",
        "mgr_prompts": "Linked prompts",
        "mgr_prompts_info": "Prompts from Prompt Library associated with this collection (also editable from Prompt Library).",
        "mgr_prompts_save": "Save links",
        "mgr_prompts_title": "Prompts (Prompt Library)",
        "prompts_saved": "Linked prompts saved for \"{name}\" ({n})",
        "prompts_failed": "Could not save the links in Prompt Library: {error}",
        "prompts_unavailable": "Prompt Library is not available",
        "chips_label": "Prompts:",
        "chip_tip": "Use this prompt (replaces the prompt box)",
        "save": "Save settings",
        "saved": "✅ Settings saved and applied ({time}).",
        "save_failed": "❌ Could not save `settings.json`: {error}",
        "sec_manager": "### Collections",
        "mgr_pick": "Collection",
        "mgr_name": "Name",
        "mgr_name_ph": "Collection name",
        "mgr_refresh": "Refresh",
        "mgr_new_empty": "New empty",
        "mgr_rename": "Rename",
        "mgr_duplicate": "Duplicate",
        "mgr_delete": "Delete",
        "mgr_confirm_delete_btn": "Confirm delete",
        "mgr_apply": "Apply to Reference Images",
        "mgr_add": "Add images",
        "mgr_remove": "Remove selected",
        "mgr_left": "Left",
        "mgr_right": "Right",
        "mgr_cover": "Set as cover",
        "mgr_export": "Export zip",
        "mgr_import": "Import zip",
        "mgr_gallery": "Images in this collection",
        "settings_acc": "Settings",
        "bar_label": "Reference Library",
        "delete_armed": "Click again to confirm deletion",
        "deleted_undo_toast": "Collection \"{name}\" deleted",
        "undo": "Undo",
        "restored_col": "Collection \"{name}\" restored",
        "undo_expired": "Can't undo any more",
        "bar_pick": "Collection",
        "bar_apply": "Apply",
        "bar_save_as": "Save as…",
        "bar_name_ok": "Save",
        "bar_name_cancel": "Cancel",
        "bar_update": "Update",
        "bar_manage": "Manage",
        "bar_name": "New collection name",
        "bar_name_ph": "New collection name…",
        "none": "(none)",
        "loaded": "Collection \"{name}\" loaded ({n} images)",
        "loaded_append": "Collection \"{name}\" appended ({n} images, total {total})",
        "saved_col": "Collection \"{name}\" saved ({n} images)",
        "hist_no_settings": "No settings found for this generation", "hist_deleted": "History entry deleted", "hist_restored": "History entry restored",
        "hist_no_refs": "This generation has no reference images", "hist_deleted_n": "{n} history entries deleted", "pv_no_video": "No generated video selected in the player", "pv_no_refs": "This video has no history entry and no embedded reference images", "hist_restored_n": "{n} history entries restored",
        "used_deleted_n": "{n} removed from the reference history", "used_restored_n": "{n} restored to the reference history", "hist_col_name": "Generation {date}",
        "updated_col": "Collection \"{name}\" updated ({n} images)",
        "deleted_col": "Collection \"{name}\" deleted",
        "renamed_col": "Renamed to \"{name}\"",
        "duplicated_col": "Duplicated as \"{name}\"",
        "empty_gallery": "Reference Images is empty — add images first",
        "no_collection": "No collection selected",
        "need_name": "Enter a name for the collection",
        "created_empty": "Empty collection \"{name}\" created",
        "added_imgs": "Added {n} image(s) (total {total})",
        "removed_img": "Image removed ({total} left)",
        "cover_set": "Cover updated",
        "exported": "Exported to {path}",
        "imported": "Imported as \"{name}\" ({n} images)",
        "bad_request": "invalid request",
        "at_no_images": "Auto-tagging works on images only: select at least one image.",
        "at_not_image": "{n} video/audio file(s) skipped (auto-tagging is images-only).",
        "at_queued": "Auto-tagging {n} image(s) in the background ({k} already tagged, skipped).",
        "at_height_bad": "Height must be between 120 and 220 cm.",
        "unknown_action": "unknown action",
        "not_found": "collection not found",
        "gallery_missing": "Reference Images gallery not available",
        "default_name": "Collection",
        "copy_suffix": "copy",
        "imported_name": "Imported collection",
        "err_image_index": "That image is no longer in the collection — refresh and try again",
        "err_image_missing": "Image file not found",
        "err_target_missing": "That WanGP input isn't available for the current model.",
        "vlib_added": "{n} video(s) added to the Video Library ({k} already there).",
        "err_not_image": "Not an image file",
        "err_zip_missing": "Zip file not found",
        "err_bad_zip": "Not a valid zip file",
        "err_unsafe": "Unsafe file path rejected",
        "err_exists": "A collection with that id already exists",
        "err_generic": "Something went wrong: {e}",
        "sec_videos": "### Video library",
        "video_bar": "Show the video bar under Control Video",
        "crop_save": "Crops made with Cropper (videos)",
        "crop_save_info": "Save every crop into the video library automatically, ask with a Save button, or don't save. The same crop is never stored twice.",
        "cs_auto": "Save to the video library automatically",
        "cs_ask": "Ask each time (Save button)",
        "cs_off": "Don't save",
        "vbar_label": "Reference Library · Videos",
        "vbar_pick": "Video",
        "vbar_load": "Load",
        "vbar_save_as": "Save as…",
        "vbar_manage": "Manage",
        "vbar_name": "Name for the video",
        "vbar_name_ph": "Name for the video (empty = file name)…",
        "vnone": "(none)",
        "vsec": "### Videos",
        "vmgr_title": "Video library ({n})",
        "vmgr_title_tip": "Control videos stored in the plugin folder (videos/). Click a thumbnail to select it.",
        "vmgr_name": "Video name",
        "vmgr_name_ph": "Select a video, then type a new name",
        "vmgr_rename": "Rename",
        "vmgr_load": "Load into Control Video",
        "vmgr_delete": "Delete",
        "vmgr_import": "Import",
        "vmgr_left": "Left",
        "vmgr_right": "Right",
        "vmgr_download": "Download",
        "vmgr_export": "Export all",
        "vmgr_empty": "No videos yet. Save one with the bar under Control Video, import files here, or crop one with Cropper.",
        "vmgr_none_selected": "Click a thumbnail to select a video.",
        "src_manual": "saved from Control Video",
        "src_cropper": "Cropper crop",
        "src_import": "imported",
        "vloaded": "Video \"{name}\" loaded into Control Video",
        "vsaved": "Video \"{name}\" saved to the library",
        "rs_same": "The video is already {w}×{h}",
        "rs_started": "Resizing to {preset}…",
        "rs_no_video": "Load a control video first",
        "vdup": "Already in the video library as \"{name}\"",
        "vcrop_saved": "Crop saved to the video library as \"{name}\"",
        "vcrop_offer": "Save this crop to the video library?",
        "vcrop_offer_btn": "Save to library",
        "vrenamed": "Video renamed to \"{name}\"",
        "vdeleted_undo": "Video \"{name}\" deleted",
        "vrestored": "Video \"{name}\" restored",
        "ilib_tagged": "Tags updated on {n} image(s)",
        "ilib_tag_nochange": "Nothing changed",
        "ilib_added": "{added} image(s) added to \"{name}\"",
        "ilib_added_skip": "{added} image(s) added to \"{name}\" ({skipped} already there)",
        "ilib_added_none": "All selected images are already in \"{name}\"",
        "ilib_new_col": "Collection \"{name}\" created with {n} image(s)",
        "ilib_imported": "{n} image(s) imported into the unassigned pool",
        "ilib_imported_skip": "{n} image(s) imported into the unassigned pool ({skipped} already in the library)",
        "ilib_imported_none": "Those images are already in the library",
        "ilib_deleted": "{n} image(s) deleted",
        "ilib_delete_kept": "Images still used in a collection are not deleted",
        "ilib_restored": "{n} image(s) restored",
        "ilib_restore_dup": "Already back in the library, not restored twice",
        "folder_added": "Folder added: {path} ({n} images)",
        "ilib_removed_from": "{n} image(s) removed from \"{name}\"",
        "ilib_deleted_all": "{n} image(s) deleted from the library ({c} collection(s) affected)",
        "ilib_folder_kept": "{k} from watched folders stay on disk",
        "ilib_folder_only": "Watched-folder images are never deleted from disk ({k} skipped)",
        "err_undo_expired": "Undo is no longer available",
        "refs_used": "{n} image(s) loaded into Reference Images",
        "refs_appended": "{n} image(s) added to Reference Images ({total} in total)",
        "refs_appended_skip": "{n} image(s) added to Reference Images ({skipped} already there)",
        "refs_none": "Those images are already in Reference Images",
        "folder_added_bg": "Folder added: {path}. Indexing…",
        "folder_indexing": "Indexing {path}: {done} / {total}",
        "rescanning": "Re-scanning the watched folders…",
        "folder_removed": "Folder removed from the index (the files on disk are untouched)",
        "folder_updated": "Folder updated: {n} images",
        "rescanned": "Re-scan: {files} images in folders ({added} new, {removed} gone)",
        "rescanned_missing": "Re-scan: {files} images; {m} folder(s) not found",
        "err_browse_denied": "No permission to read that folder",
        "err_browse_slow": "That drive is not responding (asleep or disconnected?). Try again or type the path",
        "err_folder_missing": "That folder doesn't exist on the WanGP machine",
        "err_not_folder": "That path is a file, not a folder",
        "err_folder_dup": "That folder is already watched",
        "err_folder_forbidden": "That folder can't be watched (plugin data folder)",
        "err_no_images": "Select at least one image",
        "err_no_tags": "Type a tag",
        "sec_img_crops": "### Image crops",
        "browser_fullscreen": "Always open the media browser full screen",
        "browser_fullscreen_info": "The media browser opens filling the whole screen (the ⛶ button in its header still switches for the current session).",
        "index_paused": "Pause folder indexing",
        "index_paused_info": "Watched folders stop being indexed in the background until you turn this off (also from the media browser).",
        "indexing_paused": "Indexing paused",
        "crop_save_images": "Image crops made with Cropper",
        "crop_save_images_info": "Start/end, reference and control images cropped with Cropper go to the automatic \"Crops\" collection (or the collection Cropper names). Save automatically, ask with a Save button, or don't save. The same crop is never stored twice in a collection.",
        "cs_img_auto": "Save to the \"Crops\" collection automatically",
        "crops_name": "Crops",
        "icrop_saved": "Crop \"{name}\" saved to the collection \"{collection}\"",
        "icrop_dup": "This crop (\"{name}\") is already in \"{collection}\"",
        "icrop_offer": "Save this crop to the collection \"{collection}\"?",
        "icrop_offer_btn": "Save to the collection",
        "restored_merged": "Collection \"{name}\" restored; {added} crop(s) made meanwhile in \"{merged}\" were moved into it",
        "rename_col_tip": "Rename the collection (or double-click)",
        "rename_video_tip": "Rename the video (or double-click)",
        "renamed_video_same": "Nothing to rename",
        "vrestore_dup": "\"{name}\" was not restored: the same video is already in the library as \"{existing}\"",
        "vimported": "Imported {n} video(s)",
        "vimported_skip": "Imported {n} video(s); {skipped} already in the library",
        "vexported": "Exported {n} video(s) to {path}",
        "vdownload": "Ready to download: {path}",
        "no_video": "No video selected",
        "no_control_video": "Control Video is empty — add a video first",
        "control_missing": "Control Video is not available in this form",
        "video_not_found": "video not found",
        "video_default_name": "Video",
        "err_video_missing": "Video file not found",
        "err_not_video": "Not a video file",
        "err_exists_video": "A video with that id already exists",
        "offer_expired": "That crop is no longer available",
        "frames_n": "{n} frames",
        "need_vname": "Enter a name for the video",
        "reveal_remote": "Only available when the browser runs on the same PC as WanGP",
        "reveal_missing": "The file is not on disk",
    },
    "es": {
        "intro": "Guarda las imágenes de **Referencias** como colecciones con nombre y cárgalas de nuevo con un clic. "
                 "Las colecciones viven en la carpeta del plugin (`collections/`) y sobreviven a las actualizaciones de WanGP. "
                 "Una barra compacta aparece bajo la galería de Referencias. "
                 "La **librería de vídeos** guarda los vídeos de control igual (barra bajo Vídeo de control, sección Vídeos más abajo; "
                 "se guardan en `videos/`), también los recortes hechos con Cropper.",
        "language": "Language / Idioma",
        "language_info": "Auto = el idioma del navegador (español si está en español; si no, inglés). Se aplica al momento.",
        "lang_auto": "Auto (idioma del navegador)",
        "sec_apply": "### Al aplicar colecciones",
        "sec_bar": "### Barras",
        "sec_messages": "### Avisos",
        "replace_mode": "Al cargar una colección",
        "mode_replace": "Sustituir las referencias actuales",
        "mode_append": "Añadir a las referencias actuales",
        "auto_apply": "Aplicar automáticamente al elegir una colección o un vídeo en las barras",
        "show_edit": "Mostrar también las barras en la pestaña Edit de la cola",
        "toasts": "Mensajes de confirmación",
        "toasts_info": "Los errores se muestran siempre.",
        "toast_s": "Duración (segundos)",
        "sec_prompts": "### Prompt Library",
        "on_apply_prompts": "Prompts asociados al cargar una colección",
        "on_apply_prompts_info": "Ofrecer = mostrarlos como chips bajo la barra (el cuadro de prompt no cambia hasta que pulses uno).",
        "oap_offer": "Ofrecerlos (chips bajo la barra)",
        "oap_apply_first": "Aplicar automáticamente el primer prompt asociado",
        "oap_off": "No hacer nada",
        "mgr_prompts": "Prompts asociados",
        "mgr_prompts_info": "Prompts de Prompt Library asociados a esta colección (también se editan desde Prompt Library).",
        "mgr_prompts_save": "Guardar vínculos",
        "mgr_prompts_title": "Prompts asociados (Prompt Library)",
        "prompts_saved": "Prompts asociados guardados para \"{name}\" ({n})",
        "prompts_failed": "No se pudieron guardar los vínculos en Prompt Library: {error}",
        "prompts_unavailable": "Prompt Library no está disponible",
        "chips_label": "Prompts:",
        "chip_tip": "Usar este prompt (sustituye el cuadro de prompt)",
        "save": "Guardar ajustes",
        "saved": "✅ Ajustes guardados y aplicados ({time}).",
        "save_failed": "❌ No se pudo guardar `settings.json`: {error}",
        "sec_manager": "### Colecciones",
        "mgr_pick": "Colección",
        "mgr_name": "Nombre",
        "mgr_name_ph": "Nombre de la colección",
        "mgr_refresh": "Actualizar",
        "mgr_new_empty": "Nueva vacía",
        "mgr_rename": "Renombrar",
        "mgr_duplicate": "Duplicar",
        "mgr_delete": "Borrar",
        "mgr_confirm_delete_btn": "Confirmar borrado",
        "mgr_apply": "Aplicar a Referencias",
        "mgr_add": "Añadir imágenes",
        "mgr_remove": "Quitar seleccionada",
        "mgr_left": "Izquierda",
        "mgr_right": "Derecha",
        "mgr_cover": "Usar como portada",
        "mgr_export": "Exportar zip",
        "mgr_import": "Importar zip",
        "mgr_gallery": "Imágenes de esta colección",
        "settings_acc": "Ajustes",
        "bar_label": "Reference Library",
        "delete_armed": "Pulsa otra vez para confirmar el borrado",
        "deleted_undo_toast": "Colección \"{name}\" borrada",
        "undo": "Deshacer",
        "restored_col": "Colección \"{name}\" restaurada",
        "undo_expired": "Ya no se puede deshacer",
        "bar_pick": "Colección",
        "bar_apply": "Aplicar",
        "bar_save_as": "Guardar como…",
        "bar_name_ok": "Guardar",
        "bar_name_cancel": "Cancelar",
        "bar_update": "Actualizar",
        "bar_manage": "Gestionar",
        "bar_name": "Nombre de la colección nueva",
        "bar_name_ph": "Nombre de la colección nueva…",
        "none": "(ninguna)",
        "loaded": "Colección \"{name}\" cargada ({n} imágenes)",
        "loaded_append": "Colección \"{name}\" añadida ({n} imágenes, total {total})",
        "hist_no_settings": "No hay ajustes para esta generación", "hist_deleted": "Entrada del historial borrada", "hist_restored": "Entrada del historial restaurada",
        "hist_no_refs": "Esta generación no tiene imágenes de referencia", "hist_deleted_n": "{n} entradas del historial borradas", "pv_no_video": "No hay ningún vídeo generado seleccionado en el reproductor", "pv_no_refs": "Este vídeo no tiene entrada en el historial ni imágenes de referencia incrustadas", "hist_restored_n": "{n} entradas del historial restauradas",
        "used_deleted_n": "{n} quitadas del historial de referencias", "used_restored_n": "{n} restauradas en el historial de referencias", "hist_col_name": "Generación {date}",
        "saved_col": "Colección \"{name}\" guardada ({n} imágenes)",
        "updated_col": "Colección \"{name}\" actualizada ({n} imágenes)",
        "deleted_col": "Colección \"{name}\" borrada",
        "renamed_col": "Renombrada a \"{name}\"",
        "duplicated_col": "Duplicada como \"{name}\"",
        "empty_gallery": "Referencias está vacía — añade imágenes primero",
        "no_collection": "No hay ninguna colección seleccionada",
        "need_name": "Escribe un nombre para la colección",
        "created_empty": "Colección vacía \"{name}\" creada",
        "added_imgs": "Añadidas {n} imagen(es) (total {total})",
        "removed_img": "Imagen quitada (quedan {total})",
        "cover_set": "Portada actualizada",
        "exported": "Exportada a {path}",
        "imported": "Importada como \"{name}\" ({n} imágenes)",
        "bad_request": "petición no válida",
        "at_no_images": "El autoetiquetado solo funciona con imágenes: selecciona al menos una.",
        "at_not_image": "{n} vídeo(s)/audio(s) omitidos (el autoetiquetado es solo para imágenes).",
        "at_queued": "Autoetiquetando {n} imagen(es) en segundo plano ({k} ya etiquetadas, omitidas).",
        "at_height_bad": "La altura debe estar entre 120 y 220 cm.",
        "unknown_action": "acción desconocida",
        "not_found": "colección no encontrada",
        "gallery_missing": "la galería de Referencias no está disponible",
        "default_name": "Colección",
        "copy_suffix": "copia",
        "imported_name": "Colección importada",
        "err_image_index": "Esa imagen ya no está en la colección — actualiza y vuelve a intentarlo",
        "err_image_missing": "No se encuentra el archivo de la imagen",
        "err_target_missing": "Esa entrada de WanGP no está disponible con el modelo actual.",
        "vlib_added": "{n} vídeo(s) añadidos a la Librería de vídeos ({k} ya estaban).",
        "err_not_image": "No es un archivo de imagen",
        "err_zip_missing": "No se encuentra el archivo zip",
        "err_bad_zip": "El archivo no es un zip válido",
        "err_unsafe": "Ruta de archivo no segura; rechazada",
        "err_exists": "Ya existe una colección con ese id",
        "err_generic": "Algo ha fallado: {e}",
        "sec_videos": "### Librería de vídeos",
        "video_bar": "Mostrar la barra de vídeos bajo Vídeo de control",
        "crop_save": "Recortes hechos con Cropper (vídeos)",
        "crop_save_info": "Guardar cada recorte en la librería de vídeos automáticamente, preguntar con un botón Guardar, o no guardarlos. El mismo recorte nunca se guarda dos veces.",
        "cs_auto": "Guardar en la librería de vídeos automáticamente",
        "cs_ask": "Preguntar cada vez (botón Guardar)",
        "cs_off": "No guardar",
        "vbar_label": "Reference Library · Vídeos",
        "vbar_pick": "Vídeo",
        "vbar_load": "Cargar",
        "vbar_save_as": "Guardar como…",
        "vbar_manage": "Gestionar",
        "vbar_name": "Nombre del vídeo",
        "vbar_name_ph": "Nombre del vídeo (vacío = nombre del archivo)…",
        "vnone": "(ninguno)",
        "vsec": "### Vídeos",
        "vmgr_title": "Librería de vídeos ({n})",
        "vmgr_title_tip": "Vídeos de control guardados en la carpeta del plugin (videos/). Pulsa una miniatura para elegirlo.",
        "vmgr_name": "Nombre del vídeo",
        "vmgr_name_ph": "Elige un vídeo y escribe el nombre nuevo",
        "vmgr_rename": "Renombrar",
        "vmgr_load": "Cargar en Vídeo de control",
        "vmgr_delete": "Borrar",
        "vmgr_import": "Importar",
        "vmgr_left": "Izquierda",
        "vmgr_right": "Derecha",
        "vmgr_download": "Descargar",
        "vmgr_export": "Exportar todo",
        "vmgr_empty": "Todavía no hay vídeos. Guarda uno con la barra bajo Vídeo de control, importa archivos aquí o recorta uno con Cropper.",
        "vmgr_none_selected": "Pulsa una miniatura para elegir un vídeo.",
        "src_manual": "guardado desde Vídeo de control",
        "src_cropper": "recorte de Cropper",
        "src_import": "importado",
        "vloaded": "Vídeo \"{name}\" cargado en Vídeo de control",
        "vsaved": "Vídeo \"{name}\" guardado en la librería",
        "rs_same": "El vídeo ya mide {w}×{h}",
        "rs_started": "Redimensionando a {preset}…",
        "rs_no_video": "Carga antes un vídeo de control",
        "vdup": "Ya está en la librería de vídeos como \"{name}\"",
        "vcrop_saved": "Recorte guardado en la librería de vídeos como \"{name}\"",
        "vcrop_offer": "¿Guardar este recorte en la librería de vídeos?",
        "vcrop_offer_btn": "Guardar en la librería",
        "vrenamed": "Vídeo renombrado a \"{name}\"",
        "vdeleted_undo": "Vídeo \"{name}\" borrado",
        "vrestored": "Vídeo \"{name}\" restaurado",
        "ilib_tagged": "Etiquetas actualizadas en {n} imagen(es)",
        "ilib_tag_nochange": "No ha cambiado nada",
        "ilib_added": "{added} imagen(es) añadidas a \"{name}\"",
        "ilib_added_skip": "{added} imagen(es) añadidas a \"{name}\" ({skipped} ya estaban)",
        "ilib_added_none": "Todas las imágenes elegidas ya están en \"{name}\"",
        "ilib_new_col": "Colección \"{name}\" creada con {n} imagen(es)",
        "ilib_imported": "{n} imagen(es) importadas a la bolsa sin colección",
        "ilib_imported_skip": "{n} imagen(es) importadas a la bolsa sin colección ({skipped} ya estaban en la librería)",
        "ilib_imported_none": "Esas imágenes ya están en la librería",
        "ilib_deleted": "{n} imagen(es) borradas",
        "ilib_delete_kept": "Las imágenes que siguen en alguna colección no se borran",
        "ilib_restored": "{n} imagen(es) restauradas",
        "ilib_restore_dup": "Ya están otra vez en la librería; no se restauran dos veces",
        "folder_added": "Carpeta añadida: {path} ({n} imágenes)",
        "ilib_removed_from": "{n} imagen(es) quitadas de \"{name}\"",
        "ilib_deleted_all": "{n} imagen(es) borradas de la librería ({c} colección(es) afectadas)",
        "ilib_folder_kept": "{k} de carpetas vigiladas se quedan en el disco",
        "ilib_folder_only": "Las imágenes de carpetas vigiladas nunca se borran del disco ({k} omitidas)",
        "err_undo_expired": "Ya no se puede deshacer",
        "refs_used": "{n} imagen(es) cargadas en Reference Images",
        "refs_appended": "{n} imagen(es) añadidas a Reference Images ({total} en total)",
        "refs_appended_skip": "{n} imagen(es) añadidas a Reference Images ({skipped} ya estaban)",
        "refs_none": "Esas imágenes ya están en Reference Images",
        "folder_added_bg": "Carpeta añadida: {path}. Indexando…",
        "folder_indexing": "Indexando {path}: {done} / {total}",
        "rescanning": "Reescaneando las carpetas vigiladas…",
        "folder_removed": "Carpeta quitada del índice (los archivos del disco no se tocan)",
        "folder_updated": "Carpeta actualizada: {n} imágenes",
        "rescanned": "Reescaneo: {files} imágenes en carpetas ({added} nuevas, {removed} ya no están)",
        "rescanned_missing": "Reescaneo: {files} imágenes; {m} carpeta(s) no encontradas",
        "err_browse_denied": "No hay permiso para leer esa carpeta",
        "err_browse_slow": "Esa unidad no responde (¿dormida o desconectada?). Vuelve a intentarlo o escribe la ruta",
        "err_folder_missing": "Esa carpeta no existe en el equipo de WanGP",
        "err_not_folder": "Esa ruta es un archivo, no una carpeta",
        "err_folder_dup": "Esa carpeta ya está vigilada",
        "err_folder_forbidden": "Esa carpeta no se puede vigilar (carpeta de datos del plugin)",
        "err_no_images": "Elige al menos una imagen",
        "err_no_tags": "Escribe una etiqueta",
        "sec_img_crops": "### Recortes de imágenes",
        "browser_fullscreen": "Abrir siempre a pantalla completa",
        "browser_fullscreen_info": "El explorador de medios se abre ocupando toda la pantalla (el botón ⛶ de su cabecera sigue cambiándolo solo para esa vez).",
        "index_paused": "Pausar la indexación de carpetas",
        "index_paused_info": "Las carpetas vigiladas dejan de indexarse en segundo plano hasta que lo desactives (también desde el explorador de medios).",
        "indexing_paused": "Indexación en pausa",
        "crop_save_images": "Recortes de imágenes hechos con Cropper",
        "crop_save_images_info": "Las imágenes de inicio/fin, de referencia y de control recortadas con Cropper van a la colección automática «Recortes» (o a la colección que indique Cropper). Guardar automáticamente, preguntar con un botón Guardar, o no guardarlos. El mismo recorte nunca se guarda dos veces en una colección.",
        "cs_img_auto": "Guardar en la colección «Recortes» automáticamente",
        "crops_name": "Recortes",
        "icrop_saved": "Recorte \"{name}\" guardado en la colección \"{collection}\"",
        "icrop_dup": "Este recorte (\"{name}\") ya está en \"{collection}\"",
        "icrop_offer": "¿Guardar este recorte en la colección \"{collection}\"?",
        "icrop_offer_btn": "Guardar en la colección",
        "restored_merged": "Colección \"{name}\" restaurada; se le han pasado {added} recorte(s) hechos mientras tanto en \"{merged}\"",
        "rename_col_tip": "Renombrar la colección (o doble clic)",
        "rename_video_tip": "Renombrar el vídeo (o doble clic)",
        "renamed_video_same": "Nada que renombrar",
        "vrestore_dup": "No se ha restaurado \"{name}\": el mismo vídeo ya está en la librería como \"{existing}\"",
        "vimported": "{n} vídeo(s) importado(s)",
        "vimported_skip": "{n} vídeo(s) importado(s); {skipped} ya estaba(n) en la librería",
        "vexported": "{n} vídeo(s) exportado(s) a {path}",
        "vdownload": "Listo para descargar: {path}",
        "no_video": "No hay ningún vídeo seleccionado",
        "no_control_video": "Vídeo de control está vacío — añade un vídeo primero",
        "control_missing": "Vídeo de control no está disponible en este formulario",
        "video_not_found": "vídeo no encontrado",
        "video_default_name": "Vídeo",
        "err_video_missing": "No se encuentra el archivo del vídeo",
        "err_not_video": "El archivo no es un vídeo",
        "err_exists_video": "Ya existe un vídeo con ese id",
        "offer_expired": "Ese recorte ya no está disponible",
        "frames_n": "{n} fotogramas",
        "need_vname": "Escribe un nombre para el vídeo",
        "reveal_remote": "Solo disponible cuando el navegador está en el mismo PC que WanGP",
        "reveal_missing": "El archivo no está en el disco",
    },
}


def resolve_lang(setting, browser_lang=None):
    if setting in LANGS:
        return setting
    return "es" if str(browser_lang or "").strip().lower().startswith("es") else "en"


def tr(lang, key, **params):
    text = TEXT.get(lang if lang in LANGS else "en", TEXT["en"]).get(key)
    if text is None:
        text = TEXT["en"].get(key, key)
    return text.format(**params) if params else text


# StorageError messages are English internals: never show them raw, map them to translated text.
_STORAGE_ERRORS = {
    "collection not found": "not_found",
    "invalid collection id": "not_found",
    "invalid image index": "err_image_index",
    "invalid image order": "err_image_index",
    "invalid image file": "err_image_missing",
    "image file not found": "err_image_missing",
    "source image not found": "err_image_missing",
    "zip not found": "err_zip_missing",
    "path safety check failed": "err_unsafe",
    "undo expired": "undo_expired",
    "collection already exists": "err_exists",
    "video not found": "video_not_found",
    "invalid video order": "video_not_found",
    "video file not found": "err_video_missing",
    "source video not found": "err_video_missing",
    "not a video file": "err_not_video",
    "video already exists": "err_exists_video",
    "offer expired": "offer_expired",
    "folder not found": "err_folder_missing",
    "not a folder": "err_not_folder",
    "folder already added": "err_folder_dup",
    "folder not allowed": "err_folder_forbidden",
    "permission denied": "err_browse_denied",
    "folder too slow": "err_browse_slow",
    "no images selected": "err_no_images",
    "no tags given": "err_no_tags",
    "not an image file": "err_not_image",
}


def storage_error_text(lang, e) -> str:
    msg = str(e or "").strip()
    key = _STORAGE_ERRORS.get(msg)
    if key:
        return tr(lang, key)
    if isinstance(e, zipfile.BadZipFile):
        return tr(lang, "err_bad_zip")
    return tr(lang, "err_generic", e=msg or e.__class__.__name__)


def language_choices(lang):
    return [(tr(lang, "lang_auto"), "auto"), ("English", "en"), ("Español", "es")]


def prompt_mode_choices(lang):
    return [(tr(lang, "oap_offer"), "offer"), (tr(lang, "oap_apply_first"), "apply_first"), (tr(lang, "oap_off"), "off")]


def crop_save_choices(lang):
    return [(tr(lang, "cs_auto"), "auto"), (tr(lang, "cs_ask"), "ask"), (tr(lang, "cs_off"), "off")]


def crop_save_images_choices(lang):
    return [(tr(lang, "cs_img_auto"), "auto"), (tr(lang, "cs_ask"), "ask"), (tr(lang, "cs_off"), "off")]


def replace_choices(lang):
    return [(tr(lang, "mode_replace"), "replace"), (tr(lang, "mode_append"), "append")]


DEFAULT_SETTINGS = {
    "replace_mode": "replace",   # "replace" | "append"
    "auto_apply": True,          # selecting in the bar applies immediately
    "show_edit_bar": True,       # also inject the bar in the queue Edit tab
    "language": "auto",
    "toasts": True,
    "toast_ms": 3500,
    "on_apply_prompts": "offer",  # "offer" | "apply_first" | "off" (only used when Prompt Library is installed)
    "video_bar": True,            # bar under Control Video (1.2)
    "crop_save": "auto",          # crops from Cropper: "auto" | "ask" | "off"
    "crop_save_images": "auto",   # image crops from Cropper (1.3): "auto" | "ask" | "off"
    "index_paused": False,        # 1.4.4: pause background indexing of watched folders
    "browser_fullscreen": False,  # 1.5.5: always open the image browser full screen (also kept in localStorage)
    "browser_details": False,     # 1.5.9: right details panel in the image browser (off: a click only selects)
    "browser_thumb": "m",         # 1.5.9: thumbnail size l / m / s
}
_CHOICES = {"browser_thumb": ("l", "m", "s"), "replace_mode": ("replace", "append"), "language": ("auto",) + LANGS,
            "on_apply_prompts": ("offer", "apply_first", "off"), "crop_save": ("auto", "ask", "off"),
            "crop_save_images": ("auto", "ask", "off")}
_CHANGE_REASONS = {"saved_col": "create", "created_empty": "create", "imported": "create", "renamed_col": "rename",
                   "duplicated_col": "duplicate", "deleted_undo_toast": "delete", "restored_col": "restore",
                   "updated_col": "images", "added_imgs": "images", "removed_img": "images", "cover_set": "images",
                   # video library (detail.kind = "video")
                   "vsaved": "video-added", "vcrop_saved": "video-added", "vimported": "video-added",
                   "vimported_skip": "video-added", "vrenamed": "video-renamed", "vdeleted_undo": "video-deleted",
                   "vrestored": "video-restored", "icrop_saved": "images", "restored_merged": "restore",
                   # image browser (1.4)
                   "ilib_added": "images", "ilib_added_skip": "images", "ilib_new_col": "create", "ilib_tagged": "tags",
                   "ilib_imported": "pool", "ilib_imported_skip": "pool", "ilib_deleted": "images", "ilib_restored": "images", "ilib_removed_from": "images"}
_RANGES = {"toast_ms": (1000, 30000)}


def _coerce(key, default, value):
    if isinstance(default, bool):
        return value if isinstance(value, bool) else default
    if key in _CHOICES:
        value = str(value).strip().lower()
        return value if value in _CHOICES[key] else default
    if isinstance(default, int):
        ok = isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
        if not ok:
            return default
        lo, hi = _RANGES.get(key, (1, 10**9))
        return int(max(lo, min(hi, round(value))))
    return default


def load_settings(path=None):
    settings = copy.deepcopy(DEFAULT_SETTINGS)
    try:
        with open(path or SETTINGS_PATH, "r", encoding="utf-8") as reader:
            user = json.load(reader)
    except FileNotFoundError:
        return settings
    except Exception as e:
        print(f"[Reference Library] Ignoring invalid settings.json: {e}")
        return settings
    if not isinstance(user, dict):
        return settings
    for key, default in DEFAULT_SETTINGS.items():
        if key in user:
            settings[key] = _coerce(key, default, user[key])
    return settings


# Cropper (and other plugins) call api.add_video lazily; the crop policy and the default name follow the settings.
_public_api._policy_provider = lambda: load_settings()["crop_save"]
_public_api._image_policy_provider = lambda: load_settings()["crop_save_images"]
try:
    imagelib.set_paused(bool(load_settings().get("index_paused")))   # 1.4.4
except Exception:
    pass


_SERVED = set()
AUDIO_TARGETS = ("audio_guide", "audio_guide2", "audio_guide3")   # 1.6.0 WanGP audio inputs (shown per model)


def _serve_url(path):
    """1.6.0: let Gradio stream exactly this one library file (video/audio playback in the media browser). Only files the
    browser asks to play are added (never whole folders), so nothing else in a watched folder becomes reachable."""
    from pathlib import Path
    from urllib.parse import quote
    from gradio.data_classes import _StaticFiles
    rp = Path(path).resolve()
    if rp not in _SERVED:
        _StaticFiles.all_paths.append(rp)
        _SERVED.add(rp)
    return "/gradio_api/file=" + quote(str(rp).replace("\\", "/"), safe="/:")


imagelib.SERVE_URL = _serve_url


def _prewarm_catalog():
    try:
        imagelib.catalog()   # 1.4.4: build the browser catalog once in the background, so the first open is instant
    except Exception as e:
        print(f"[Reference Library] catalog prewarm failed: {e}")


_t = threading.Timer(3.0, _prewarm_catalog)
_t.daemon = True
_t.start()
storage._orphan_hook = imagelib.keep_orphans   # images leaving their last collection stay in the unassigned pool (1.4)
_LAST_BROWSER = {"lang": ""}   # last browser language seen (names the automatic crops collection in "auto" language)
_public_api._crops_name = lambda: tr(resolve_lang(load_settings()["language"], _LAST_BROWSER["lang"]), "crops_name")
_public_api._fallback_name = lambda: tr(resolve_lang(load_settings()["language"]), "video_default_name")


def save_settings(settings, path=None):
    path = path or SETTINGS_PATH
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as writer:
        json.dump(settings, writer, indent=2, ensure_ascii=False)
        writer.write("\n")
    os.replace(tmp, path)


def load_css():
    try:
        with open(os.path.join(_PLUGIN_DIR, "reference_library.css"), "r", encoding="utf-8") as reader:
            return reader.read()
    except OSError:
        return ".reflib-hidden{display:none !important;}"


def build_js(settings=None):
    settings = settings or load_settings()
    with open(os.path.join(_PLUGIN_DIR, "reference_library.js"), "r", encoding="utf-8") as reader:
        script = reader.read()
    return (script
            .replace("__REFLIB_SETTINGS__", json.dumps(settings))
            .replace("__REFLIB_CSS__", json.dumps(load_css()))
            .replace("__REFLIB_VERSION__", PLUGIN_VERSION))


def _upload_folder():
    try:
        from gradio import utils as gr_utils
        return os.path.realpath(gr_utils.get_upload_folder())
    except Exception:
        import tempfile
        return os.path.realpath(os.environ.get("GRADIO_TEMP_DIR") or os.path.join(tempfile.gettempdir(), "gradio"))


def _gallery_paths(gallery, state=None):
    from shared.gradio.gallery import get_gradio_file_path, get_list, get_state
    items = get_list(gallery)
    if state is not None:
        st_items = get_list(get_state(state).get("items"))
        # Prefer gallery value when both present; fall back to state.
        if not items and st_items:
            items = st_items
    paths = []
    for it in items:
        p = get_gradio_file_path(it)
        if p and os.path.isfile(p):
            paths.append(p)
    return paths


def _stage_for_gallery(paths):
    """Copy collection files into Gradio's upload folder so WanGP can use them like Add would."""
    out_dir = os.path.join(_upload_folder(), "reference_library", uuid.uuid4().hex)
    os.makedirs(out_dir, exist_ok=True)
    staged = []
    for src in paths:
        name = os.path.basename(src)
        dest = os.path.join(out_dir, name)
        # avoid collisions within the same stage folder
        if os.path.exists(dest):
            stem, ext = os.path.splitext(name)
            dest = os.path.join(out_dir, f"{stem}_{uuid.uuid4().hex[:8]}{ext}")
        shutil.copy2(src, dest)
        staged.append(dest)
    return staged


# ---------------------------------------------------------------------------- video library helpers
WATCH_VIDEOS = ("video_guide", "video_guide2", "video_guide3", "video_source")  # inputs Cropper may put a crop into
WATCH_IMAGES = ("image_start", "image_end", "image_refs", "image_guide")          # image inputs Cropper 1.2 crops
# 1.6.4 "📚 Guardar en librería": every WanGP video / audio input (WanGP 18.18 names; missing ones are skipped)
SAVE_VIDEO_INPUTS = ("video_guide", "video_guide2", "video_guide3", "video_source", "video_mask")
SAVE_AUDIO_INPUTS = ("audio_guide", "audio_guide2", "audio_guide3", "audio_source", "replace_voice_sample", "replace_voice_sample2")


def _stage_video(path, name):
    """Copy a library video into Gradio's upload folder (named after the library entry) before giving it to WanGP, so
    nothing WanGP or another plugin does to its input can touch the stored file."""
    out_dir = os.path.join(_upload_folder(), "reference_library", uuid.uuid4().hex)
    os.makedirs(out_dir, exist_ok=True)
    stem = storage._safe_name(name, "video").replace(" ", "_")
    dest = os.path.join(out_dir, stem + os.path.splitext(path)[1].lower())
    shutil.copyfile(path, dest)
    return dest


def _video_label(v):
    parts = [v["name"], media.fmt_duration(v.get("duration"))]
    if v.get("width") and v.get("height"):
        parts.append(f'{v["width"]}×{v["height"]}')
    return " · ".join(parts)


def _video_dd_choices(lang, selected_id=None):
    choices = [(tr(lang, "vnone"), "")]
    for v in videostore.list_videos():
        choices.append((_video_label(v), v["id"]))
    value = selected_id if selected_id and any(c[1] == selected_id for c in choices) else ""
    return choices, value


_POSTER_CACHE = {}


def _poster_data_uri(v):
    """Small poster as a data URI (no file serving needed for the bar)."""
    path = videostore.poster_file(v)
    if not path:
        return ""
    try:
        key = (path, os.path.getmtime(path))
        if key not in _POSTER_CACHE:
            import base64
            with open(path, "rb") as reader:
                _POSTER_CACHE[key] = "data:image/jpeg;base64," + base64.b64encode(reader.read()).decode("ascii")
            if len(_POSTER_CACHE) > 200:
                _POSTER_CACHE.pop(next(iter(_POSTER_CACHE)))
        return _POSTER_CACHE[key]
    except OSError:
        return ""


def _video_facts(lang, v, with_source=False):
    parts = [media.fmt_duration(v.get("duration"))]
    if v.get("width") and v.get("height"):
        parts.append(f'{v["width"]}×{v["height"]}')
    if media.fmt_fps(v.get("fps")):
        parts.append(media.fmt_fps(v.get("fps")))
    if v.get("frames"):
        parts.append(tr(lang, "frames_n", n=v["frames"]))
    if v.get("size"):
        parts.append(media.fmt_size(v.get("size")))
    if with_source:
        src = str(v.get("source") or "manual")
        parts.append(tr(lang, "src_" + src) if ("src_" + src) in TEXT["en"] else src)
    return " · ".join(parts)


def _video_info_html(lang, vid):
    """Poster + facts of the selected video under the bar; empty string (hidden) when nothing is selected."""
    if not vid:
        return ""
    try:
        v = videostore.get_video(vid)
    except storage.StorageError:
        return ""
    uri = _poster_data_uri(v)
    img = f'<img class="reflib-vinfo-poster" src="{uri}" alt="">' if uri else '<span class="reflib-vinfo-poster reflib-vinfo-noposter"></span>'
    return (f'<div class="reflib-vinfo" data-vid="{_esc(v["id"])}">{img}<div class="reflib-vinfo-text">'
            f'<span class="reflib-vinfo-name">{_esc(v["name"])}</span>'
            f'<span class="reflib-vinfo-facts">{_esc(_video_facts(lang, v, with_source=True))}</span></div></div>')


def _vmgr_gallery_value(videos):
    items = []
    for v in videos:
        thumb = videostore.poster_file(v)
        if not thumb:
            try:
                thumb = videostore.video_file(v)
            except storage.StorageError:
                continue
        items.append((thumb, _video_label(v)))
    return items


def _vmeta_html(lang, v, empty=False):
    if v is None:
        text = tr(lang, "vmgr_empty") if empty else tr(lang, "vmgr_none_selected")
        return f'<div class="reflib-vmeta reflib-vmeta-hint">{_esc(text)}</div>'
    created = time.strftime("%Y-%m-%d %H:%M", time.localtime(v.get("created") or 0))
    return (f'<div class="reflib-vmeta" data-vid="{_esc(v["id"])}"><span class="reflib-vmeta-head"><span class="reflib-vinfo-name">{_esc(v["name"])}</span></span>'
            f'<span class="reflib-vinfo-facts">{_esc(_video_facts(lang, v, with_source=True))} · {_esc(created)}</span></div>')


def _esc(text):
    return html.escape(str(text or ""), quote=True)


def _bar_title_html(label, icon="library"):
    return (f'<div class="reflib-bar-title"><span class="reflib-bar-ico reflib-bar-ico-{icon}" aria-hidden="true"></span>'
            f'{_esc(label)}</div>')


def _panel_title_html(label, tip=""):
    title = f' title="{_esc(tip)}"' if tip else ""
    return f'<div class="reflib-panel-title"{title}>{_esc(label)}</div>'


def _status_html(out):
    """Small muted status line for the bar header; empty string hides it."""
    if not out:
        return ""
    ok = out.get("ok", True)
    text = out.get("message") if ok else out.get("error")
    if not text:
        return ""
    kind = "ok" if ok else "error"
    return f'<div class="reflib-bar-status-text" data-kind="{kind}" title="{_esc(text)}">{_esc(text)}</div>'


def _dropdown_choices(lang, selected_id=None):
    none = tr(lang, "none")
    choices = [(none, "")]
    for col in storage.list_collections():
        label = f'{col["name"]} ({len(col["images"])})'
        choices.append((label, col["id"]))
    value = selected_id if selected_id and any(c[1] == selected_id for c in choices) else ""
    return choices, value


def _manager_gallery_value(collection_id):
    if not collection_id:
        return []
    try:
        return storage.absolute_image_paths(collection_id)
    except storage.StorageError:
        return []



# ---------------------------------------------------------------- 1.5.5 history helpers
def _hist_cfg_path():
    return os.path.join(storage.PLUGIN_DIR, "history", "config.json")


def history_config():
    cfg = {"enabled": True, "cap_mb": 2048.0}
    try:
        cfg.update(json.load(open(_hist_cfg_path(), encoding="utf-8")))
    except Exception:
        pass
    return cfg


def save_history_config(cfg):
    os.makedirs(os.path.dirname(_hist_cfg_path()), exist_ok=True)
    json.dump(cfg, open(_hist_cfg_path(), "w", encoding="utf-8"))


def _thumb_data(path):
    if not path:
        return ""
    import base64
    try:
        return "data:image/jpeg;base64," + base64.b64encode(open(path, "rb").read()).decode()
    except OSError:
        return ""


def _wgp_save_path():
    m = sys.modules.get("__main__")
    p = getattr(m, "save_path", None) or getattr(sys.modules.get("wgp"), "save_path", None)
    if not p:
        try:
            p = json.load(open("wgp_config.json", encoding="utf-8")).get("save_path")
        except Exception:
            p = None
    return os.path.abspath(p or "outputs")


def _h_outputs(_h, limit=40):
    d = _wgp_save_path()
    try:
        names = [n for n in os.listdir(d) if n.lower().endswith((".mp4", ".mkv", ".mov", ".png", ".jpg", ".webp"))]
    except OSError:
        return []
    files = sorted((os.path.join(d, n) for n in names), key=lambda p: -os.path.getmtime(p))
    out = []
    for p in files[:limit]:
        e = _h.find_by_output(p)
        out.append({"path": p, "name": os.path.basename(p), "mtime": os.path.getmtime(p), "eid": e["id"] if e else None,
                    "url": "/gradio_api/file=" + p.replace("\\", "/")})
    return out


def _del_scope(req):
    """1.5.6: (ids, since, until) from {ids} / {range: "1h"|"24h"|"7d"|"all"|"custom", from, to} (epoch seconds)."""
    ids = [str(x) for x in (req.get("ids") or []) if isinstance(x, str)]
    rg = str(req.get("range") or "")
    now = time.time()
    since = until = None
    if rg in ("1h", "24h", "7d"):
        since = now - {"1h": 3600, "24h": 86400, "7d": 7 * 86400}[rg]
    elif rg == "all":
        since = 0.0
    elif rg == "custom":
        try:
            since = float(req.get("from") or 0)
            until = float(req["to"]) if req.get("to") not in (None, "") else None
        except (TypeError, ValueError):
            since = None
    return ids, since, until


def _video_from_url(v):
    """1.5.7: an output-player src (".../gradio_api/file=PATH" or a plain path) -> a local file path, only inside WanGP's
    output folder or Gradio's upload/cache folder (never an arbitrary file)."""
    from urllib.parse import unquote, urlparse
    v = (v or "").strip()
    if not v:
        return ""
    if "file=" in v:
        v = unquote(v.split("file=", 1)[1].split("?", 1)[0].split("#", 1)[0])
    elif v.startswith(("http://", "https://")):
        v = unquote(urlparse(v).path)
    p = os.path.realpath(v)
    roots = [os.path.realpath(_wgp_save_path()), _upload_folder()]
    import tempfile
    roots.append(os.path.realpath(os.path.join(tempfile.gettempdir(), "gradio")))
    if not os.path.isfile(p) or not any(p == r or p.startswith(r + os.sep) for r in roots):
        return ""
    return p


def _embedded_refs(path):
    """Reference images WanGP embedded in a generated video (setting "embed source images"), staged as files."""
    if not path:
        return []
    try:
        from shared.utils.video_metadata import extract_source_images
        got = extract_source_images(path) or {}
    except Exception:
        return []
    imgs = got.get("image_refs")
    imgs = imgs if isinstance(imgs, list) else ([imgs] if imgs is not None else [])
    out_dir = os.path.join(_upload_folder(), "reference_library", uuid.uuid4().hex)
    os.makedirs(out_dir, exist_ok=True)
    out = []
    for k, im in enumerate(imgs):
        try:
            if isinstance(im, str) and os.path.isfile(im):
                out.append(im)
            else:
                dest = os.path.join(out_dir, f"embedded_ref_{k + 1}.png"); im.save(dest); out.append(dest)
        except Exception:
            pass
    return out

class ReferenceLibraryPlugin(WAN2GPPlugin):
    def __init__(self):
        self._hist_comps = {}
        self._extra_comps = {}
        super().__init__()
        self.name = "Reference Library"
        self.version = PLUGIN_VERSION
        self.description = "Named collections of Reference Images: save, load, manage."
        self.targets = {}   # "generate:image_refs" -> {tab, gallery, state, row}
        self._amg = None
        self._lock = threading.Lock()
        self._last_applied = {}  # tab -> collection_id (session memory)
        self._bars = {}          # tab -> dict of bar components (for refresh)
        self._bar_localize_order = []  # [(tab, BAR_KEYS key), ...] wired into localize outputs
        self._delete_undo = {}    # token -> {id, name, time, kind}
        self._seen_tabs = []      # form order seen in post_ui_setup ("generate", then "edit")
        self.vtargets = {}        # tab -> {"video": video_guide, "watch": {name: gr.Video}}
        self.save_targets = {}    # 1.6.4: tab -> {field: gr.Video | gr.Audio} for "Guardar en librería"
        self._vbars = {}          # tab -> dict of video bar components
        self._vbar_localize_order = []
        self._last_video = {}     # tab -> video id (session memory)

    # ------------------------------------------------------------ plugin API
    def setup_ui(self):
        self.request_component("image_refs")
        self.request_component("image_refs_extra")
        self.request_component("image_refs_row")
        self.request_component("tab_id")
        for name in ("video_mask", "image_mask") + AUDIO_TARGETS:
            self.request_component(name)
        try:   # 1.5.5 generation history: WanGP calls this right before writing a generation's metadata
            self.register_data_hook("before_metadata_save", self._history_hook)
        except Exception:
            traceback.print_exc()
        for name in WATCH_VIDEOS + WATCH_IMAGES:
            self.request_component(name)
        for name in SAVE_VIDEO_INPUTS + SAVE_AUDIO_INPUTS:
            if name not in WATCH_VIDEOS + AUDIO_TARGETS + ("video_mask",):
                self.request_component(name)
        self.add_custom_js(build_js())
        self.add_tab(tab_id="reference_library", label="Reference Library", component_constructor=self.create_ui)

    def post_ui_setup(self, components):
        tab = components.get("tab_id")
        tab = tab if tab in TAB_IDS else ("generate" if "generate" not in self._seen_tabs else "edit")
        if tab not in self._seen_tabs:
            self._seen_tabs.append(tab)
        try:
            self._setup_video_target(tab, components)
        except Exception:
            traceback.print_exc()
        try:
            self._setup_save_targets(tab, components)
        except Exception:
            traceback.print_exc()
        gallery, extra = components.get("image_refs"), components.get("image_refs_extra")
        row = components.get("image_refs_row")
        if gallery is None or not isinstance(extra, (list, tuple)) or len(extra) < 2:
            print(f"[Reference Library] {tab}:image_refs not found, skipped")
            return {}
        state = extra[-1]
        if extra[-2] is not gallery or not isinstance(state, gr.State):
            print(f"[Reference Library] {tab}:image_refs unexpected layout, skipped")
            return {}
        key = f"{tab}:image_refs"
        self.targets[key] = {"tab": tab, "gallery": gallery, "state": state, "row": row}
        try:   # 1.5.5 "Usadas como referencia": whatever puts an image into Reference Images (any source)
            gallery.change(fn=self._refs_watch_fn(tab), inputs=[gallery], outputs=None, show_progress="hidden",
                           trigger_mode="always_last", queue=False)
        except Exception:
            traceback.print_exc()
        settings = load_settings()
        if tab == "edit" and not settings.get("show_edit_bar", True):
            return {}
        if row is not None:
            # Capture tab/gallery/state in the closure for the insert_after constructor.
            self.insert_after("image_refs_row", lambda t=tab, g=gallery, s=state: self.create_bar(t, g, s))
        return {}

    def _setup_video_target(self, tab, components):
        video = components.get("video_guide")
        if not isinstance(video, gr.Video):
            print(f"[Reference Library] {tab}:video_guide not found, video bar skipped")
            return
        # Tag the block for reference_library.js (several WanGP video inputs share elem_id "video_input").
        classes = video.elem_classes if isinstance(video.elem_classes, list) else ([video.elem_classes] if video.elem_classes else [])
        video.elem_classes = classes + ["reflib-vtarget", f"reflib-vt-{tab}"]
        watch = {}
        for name in WATCH_VIDEOS:
            comp = components.get(name)
            if isinstance(comp, gr.Video):
                watch[name] = comp
        self._extra_comps[tab] = {n: components.get(n) for n in ("video_mask", "image_mask") + AUDIO_TARGETS}
        for n in AUDIO_TARGETS:   # 1.6.0: tag WanGP's audio inputs so the media browser knows which ones the model shows
            c = components.get(n)
            if isinstance(c, gr.Audio):
                cl = c.elem_classes if isinstance(c.elem_classes, list) else ([c.elem_classes] if c.elem_classes else [])
                c.elem_classes = cl + ["reflib-atarget", f"reflib-at-{n}-{tab}"]
        watch_images = {name: components[name] for name in WATCH_IMAGES if isinstance(components.get(name), gr.components.Component)}
        self.vtargets[tab] = {"video": video, "watch": watch, "watch_images": watch_images}
        settings = load_settings()
        show = bool(settings.get("video_bar", True)) and (tab != "edit" or bool(settings.get("show_edit_bar", True)))
        # Always inserted (hidden when disabled) so the crop notices still reach the page.
        self.insert_after("video_guide", lambda t=tab, v=show: self.create_vbar(t, v))

    # ------------------------------------------------------------ 1.6.4 "Guardar en librería"
    def _setup_save_targets(self, tab, components):
        """Tag every WanGP video / audio input for reference_library.js (it adds the button in the input's toolbar)."""
        found = {}
        for name in SAVE_VIDEO_INPUTS + SAVE_AUDIO_INPUTS:
            comp = components.get(name)
            want = gr.Video if name in SAVE_VIDEO_INPUTS else gr.Audio
            if not isinstance(comp, want):
                continue
            cl = comp.elem_classes if isinstance(comp.elem_classes, list) else ([comp.elem_classes] if comp.elem_classes else [])
            comp.elem_classes = cl + ["reflib-savein", f"reflib-si-{name}-{tab}"]
            found[name] = comp
        self.save_targets[tab] = found

    def save_input(self, tab, field, raw, value):
        """Bridge for one input: {action: "save_input", name, trimmed} saves the CURRENT value (after a Gradio trim it is
        the trimmed upload); {action: "save_input_undo", kind, ref} removes the copy that save created."""
        from .reflib_core import savein
        try:
            req = json.loads(raw or "{}")
            if not isinstance(req, dict):
                raise ValueError
        except Exception:
            return json.dumps({"ok": False, "error": tr("en", "bad_request")})
        lang = req.get("lang") if req.get("lang") in LANGS else resolve_lang(load_settings()["language"])
        out = {"id": req.get("id"), "quiet": True}
        try:
            if req.get("action") == "save_input":
                r = savein.save(field, value, name=str(req.get("name") or "")[:200] or None, trimmed=bool(req.get("trimmed")), lang=lang)
                vid = r.pop("id", None)   # "id" is the bridge request id: the video id travels as "video_id"
                out.update(r, video_id=vid)
                out["changed"] = {"reason": "video-added", "id": vid, "kind": "video"} if r["kind"] == "video" else {"reason": "audio-saved", "id": r["hash"]}
            elif req.get("action") == "save_input_undo":
                if req.get("kind") == "video":
                    out.update(savein.undo_video(str(req.get("ref") or "")))
                    out["changed"] = {"reason": "video-deleted", "id": req.get("ref"), "kind": "video"}
                else:
                    out.update(savein.undo_audio(str(req.get("ref") or "")))
                    out["changed"] = {"reason": "audio-removed", "id": None}
            else:
                out.update(self._err(lang, "bad_request"))
        except Exception as e:
            print(f"[Reference Library] save {tab}:{field} failed: {e}")
            out.update({"ok": False, "error": str(e)})
        return json.dumps(out)

    # ------------------------------------------------------------ 1.5.5 generation history
    def _history_hook(self, configs=None, plugin_data=None, model_type=None, **kw):
        """before_metadata_save: grab the generation's raw inputs from WanGP's generate_media frame (read-only), then
        record in a thread once WanGP has finished filling the same configs dict (prompt / creation date are set right
        after this hook). Never raises, never changes configs."""
        try:
            if not isinstance(configs, dict) or not history_config().get("enabled", True):
                return configs
            import inspect
            fr, loc = inspect.currentframe(), None
            for _ in range(8):
                fr = fr.f_back if fr is not None else None
                if fr is None:
                    break
                if fr.f_code.co_name == "generate_media" and "video_path" in fr.f_locals:
                    loc = fr.f_locals
                    break
            if loc is None:
                return configs
            from .reflib_core import history as _h
            raw = {f: loc.get(f) for f in _h.FIELDS}   # video_source: already resolved by WanGP in "L" mode
            extra = {k: loc.get(k) for k in getattr(_h, "EXTRA_SETTINGS", ())}
            out = loc.get("video_path")
            cfg_ref = configs
            def work():
                for _ in range(50):
                    if "creation_date" in cfg_ref:
                        break
                    time.sleep(0.1)
                time.sleep(0.2)
                try:
                    _h.capture(raw, dict(cfg_ref), out, model_type or "", cap_mb=history_config().get("cap_mb"), extra=extra)
                except Exception:
                    traceback.print_exc()
            threading.Thread(target=work, daemon=True, name="reflib-history").start()
        except Exception:
            traceback.print_exc()
        return configs

    def _refs_watch_fn(self, tab):
        def fn(value):
            try:
                self._refs_seen(tab, value)
            except Exception:
                traceback.print_exc()
        fn.__name__ = f"reflib_refs_used_{tab}"
        return fn

    def _refs_seen(self, tab, value):
        """Hash the gallery's files (cached by path/size/mtime); images new to this gallery are logged as used and,
        when not in the library yet (uploads, Dragger…), added to the pool so the browser can show them."""
        from shared.gradio.gallery import get_gradio_file_path, get_list
        from .reflib_core import refusage
        cache = self.__dict__.setdefault("_hcache", {})
        cur = []
        for it in get_list(value) or []:
            pth = get_gradio_file_path(it)
            if not pth or not os.path.isfile(pth):
                continue
            st = os.stat(pth)
            k = (pth, st.st_size, st.st_mtime_ns)
            if k not in cache:
                if len(cache) > 5000:
                    cache.clear()
                cache[k] = storage._file_hash(pth)
            cur.append((cache[k], pth))
        prev = self.__dict__.setdefault("_refs_prev", {}).get(tab, set())
        new = [(h, p) for h, p in cur if h not in prev]
        self._refs_prev[tab] = {h for h, _ in cur}
        if not new:
            return
        known = imagelib.catalog()["by_hash"]
        for h, pth in new:
            if h not in known:
                try:
                    imagelib.pool_add(pth, name=os.path.basename(pth), source="refs")
                except Exception:
                    pass
        refusage.record([h for h, _ in new])
        imagelib.invalidate()

    def _history(self, action, req, lang):
        from .reflib_core import history as _h
        if action == "hist_list":
            r = _h.entries(str(req.get("q") or ""), int(req.get("offset") or 0), min(60, int(req.get("limit") or 30)))
            for it in r["items"]:
                it["thumbs"] = {}
                for f, xs in it["media"].items():
                    for x in xs:
                        it["thumbs"][x["h"]] = _thumb_data(_h.thumb_path(x["h"]))
                it["poster_src"] = _thumb_data(_h.thumb_path(it["poster"])) if it.get("poster") else ""
            return {"ok": True, "hist": r, "config": history_config()}
        if action == "hist_outputs":   # generated videos without a history entry (bonus: reuse from WanGP's output folder)
            return {"ok": True, "outputs": _h_outputs(_h, int(req.get("limit") or 40))}
        if action == "hist_get":
            e = _h.get(str(req.get("eid") or ""))
            return {"ok": bool(e), "entry": _h._public(e) if e else None}
        if action == "hist_find":
            path = _video_from_url(str(req.get("path") or req.get("url") or ""))
            if req.get("url") and not path:
                return {"ok": False, "error": tr(lang, "pv_no_video")}
            e = _h.find_by_output(path) if path else None
            if e:
                return {"ok": True, "eid": e["id"], "path": path, "has_refs": bool((e.get("media") or {}).get("image_refs"))}
            md = _h.read_embedded(path) if path and os.path.isfile(path) else None
            return {"ok": True, "eid": None, "path": path, "embedded": bool(md), "prompt": (md or {}).get("prompt", "")}
        if action == "hist_settings":   # JSON for WanGP's native settings loader
            if req.get("eid"):
                s = (_h.get(str(req["eid"])) or {}).get("settings")
            else:
                path = str(req.get("path") or "")
                e = _h.find_by_output(path)
                s = e.get("settings") if e else _h.read_embedded(path)
            if not s:
                return {"ok": False, "error": tr(lang, "hist_no_settings")}
            # 1.6.5: reusing settings never copies the seed (random, -1); the stored entry is untouched
            return {"ok": True, "json": json.dumps(_h.for_restore(s), ensure_ascii=False), "name": "reflib_settings.json"}
        if action in ("hist_del", "hist_undo_batch"):   # 1.5.6 multi / range delete with confirm count + undo
            if action == "hist_undo_batch":
                n = _h.undo_batch(str(req.get("batch") or ""))
                return {"ok": n > 0, "n": n, "message": tr(lang, "hist_restored_n", n=n)}
            ids, since, until = _del_scope(req)
            sel = _h.select(ids, since, until)
            if req.get("dry"):
                return {"ok": True, "n": len(sel)}
            r = _h.delete_many(sel)
            return {"ok": True, "n": r["n"], "batch": r["batch"], "message": tr(lang, "hist_deleted_n", n=r["n"])}
        if action == "hist_delete":
            ok = _h.delete(str(req.get("eid") or ""))
            return {"ok": ok, "message": tr(lang, "hist_deleted"), "undo": ok}
        if action == "hist_undo":
            return {"ok": bool(_h.undo(str(req.get("eid") or ""))), "message": tr(lang, "hist_restored")}
        if action == "hist_savecol":
            paths = _h.paths(str(req.get("eid") or ""), "image_refs")
            if not paths:
                return self._err(lang, "hist_no_refs")
            name = (str(req.get("name") or "")).strip() or tr(lang, "hist_col_name", date=time.strftime("%Y-%m-%d %H:%M"))
            col = storage.create_collection(name, [(p, os.path.basename(p)) for p in paths], fallback=tr(lang, "default_name"))
            return {**self._ok(lang, "saved_col", name=col["name"], n=len(col["images"]), _cid=col["id"]), "cid": col["id"]}
        if action == "hist_config":
            cfg = history_config()
            if isinstance(req.get("set"), dict):
                st = req["set"]
                if "enabled" in st:
                    cfg["enabled"] = bool(st["enabled"])
                if "cap_mb" in st:
                    try:
                        cfg["cap_mb"] = max(0, min(10**6, float(st["cap_mb"])))
                    except (TypeError, ValueError):
                        pass
                save_history_config(cfg)
                _h.enforce_cap(cfg["cap_mb"])
            return {"ok": True, "config": cfg, "size_mb": round(_h.size_bytes() / 2**20, 1)}
        return self._err(lang, "bad_request")

    def _hist_targets(self, tab):
        vt = self.vtargets[tab]
        hcomps = [("video_guide", vt["video"])] + [(n, c) for n, c in vt["watch"].items() if n == "video_source"]
        for n in ("video_mask", "image_mask") + AUDIO_TARGETS:
            c = self._extra_comps.get(tab, {}).get(n)
            if isinstance(c, (gr.Video, gr.Image, gr.ImageEditor, gr.Gallery, gr.Audio)):
                hcomps.append((n, c))
        for n in ("image_start", "image_end", "image_guide"):
            c = vt.get("watch_images", {}).get(n)
            if isinstance(c, (gr.Image, gr.Gallery)):
                hcomps.append((n, c))
        self._hist_comps[tab] = hcomps
        return hcomps

    def history_media(self, tab, raw):
        """Bridge for the generator form: control video / masks / start-end images of a history entry."""
        from .reflib_core import history as _h
        vt = self.vtargets.get(tab) or {}
        comps = self._hist_comps.get(tab) or []
        try:
            req = json.loads(raw or "{}")
        except Exception:
            req = {}
        eid = str(req.get("eid") or "")
        e = _h.get(eid) or {}
        ups, done = [], []
        direct = {}
        if req.get("hash") and req.get("to"):   # 1.6.0 media browser: one library video/audio -> one WanGP input
            to, src = str(req["to"]), imagelib.media_path(str(req["hash"]))
            ent = imagelib.entry_for(str(req["hash"])) or {}
            want = "audio" if to in AUDIO_TARGETS else "video"
            if src and ent.get("kind") == want and any(n == to for n, _ in comps):
                direct[to] = [src]
            else:
                return (json.dumps({"ok": False, "id": req.get("id"), "error": tr(req.get("lang", "en"), "err_target_missing"), "target": f"{tab}:history"}),
                        *[gr.skip() for _ in comps])
        for name, comp in comps:
            ps = direct.get(name, []) if direct else (_h.paths(eid, name) if e else [])
            if not ps:
                ups.append(gr.skip()); continue
            try:
                if isinstance(comp, (gr.Video, gr.Audio)):
                    val = _stage_video(ps[0], (os.path.splitext(os.path.basename(ps[0]))[0] if direct else f"history_{name}"))
                elif isinstance(comp, gr.Gallery):
                    val = _stage_for_gallery(ps)
                else:
                    val = _stage_for_gallery(ps[:1])[0]
                ups.append(gr.update(value=val)); done.append(name)
            except Exception:
                traceback.print_exc(); ups.append(gr.skip())
        out = {"ok": True, "id": req.get("id"), "restored": done, "target": f"{tab}:history"}
        return (json.dumps(out), *ups)

    def amg(self):
        if self._amg is None:
            from shared.gradio.gallery import AdvancedMediaGallery
            self._amg = AdvancedMediaGallery(media_mode="image")
        return self._amg

    # ---------------------------------------------------------------- helpers
    def _lang(self, browser_lang=None):
        if browser_lang:
            _LAST_BROWSER["lang"] = str(browser_lang)[:16]
        return resolve_lang(load_settings()["language"], browser_lang)

    def _status(self, lang, key, **params):
        return tr(lang, key, **params)

    def _ok(self, lang, key, **params):
        cid = params.pop("_cid", None)
        out = {"ok": True, "message": tr(lang, key, **params), "toast": tr(lang, key, **params)}
        if key in _CHANGE_REASONS:
            reason = _CHANGE_REASONS[key]
            out["changed"] = {"reason": reason, "id": cid}
            if reason.startswith("video-"):
                out["changed"]["kind"] = "video"
        return out

    def _err(self, lang, key, **params):
        return {"ok": False, "error": tr(lang, key, **params)}

    # ------------------------------------------------ apply / save / update
    def apply_collection(self, tab, collection_id, gallery, state, mode=None, lang="en"):
        if not collection_id:
            return self._err(lang, "no_collection"), gr.skip(), gr.skip()
        settings = load_settings()
        mode = mode if mode in ("replace", "append") else settings["replace_mode"]
        try:
            paths = storage.absolute_image_paths(collection_id)
            col = storage.get_collection(collection_id)
        except storage.StorageError:
            return self._err(lang, "not_found"), gr.skip(), gr.skip()
        if not paths:
            # empty collection: still clear if replace
            if mode == "replace":
                gallery_update, st = self.amg()._on_clear(state)
                self._last_applied[tab] = collection_id
                return ({**self._ok(lang, "loaded", name=col["name"], n=0), "total": 0, "id": collection_id,
                         **self._applied_extras(tab, col, 0)}, gallery_update, st)
            return self._err(lang, "empty_gallery"), gr.skip(), gr.skip()
        staged = _stage_for_gallery(paths)
        st = state
        if mode == "replace":
            gallery_update, st = self.amg()._on_clear(st)
            # _on_clear returns updates; apply them as current value for _on_add
            from shared.gradio.gallery import get_state
            st = get_state(st)
            st["items"] = []
            st["selected"] = None
            gallery_value = []
        else:
            from shared.gradio.gallery import get_list, get_state
            st = get_state(st)
            gallery_value = get_list(gallery)
            st["selected"] = len(gallery_value) - 1 if gallery_value else 0
        gallery_update, st = self.amg()._on_add(staged, st, gallery_value if mode == "append" else [])
        self._last_applied[tab] = collection_id
        n = len(staged)
        total = len(st.get("items") or [])
        key = "loaded_append" if mode == "append" else "loaded"
        return {**self._ok(lang, key, name=col["name"], n=n, total=total), "total": total, "id": collection_id,
                "resync": {"selected": st.get("selected"), "count": total},
                **self._applied_extras(tab, col, n)}, gallery_update, st

    def apply_images(self, tab, hashes, gallery, state, mode="replace", lang="en", paths_override=None):
        """Image browser (1.4.1): load ONLY the selected images into Reference Images, through the same
        AdvancedMediaGallery path as a collection apply, always appending. Folder images are read from where they are (staged in Gradio's
        upload folder like any Add), never copied into a collection. append skips images already in the gallery."""
        if paths_override is None:
            mode = "append"   # 1.4.1: only "Add to references" — append, skip duplicates, never replace
        else:   # 1.5.5 history reuse: append (default) or replace
            mode = "replace" if mode == "replace" else "append"
        want = [h for h in (hashes or []) if isinstance(h, str)] if paths_override is None else []
        if not want and not paths_override:
            return self._err(lang, "err_no_images"), gr.skip(), gr.skip()
        by_hash = imagelib.catalog()["by_hash"] if paths_override is None else {}
        paths, seen = ([p for p in paths_override if os.path.isfile(p)] if paths_override else []), set()
        for h in want:
            img = by_hash.get(h)
            if not img or h in seen or img.get("kind", "image") != "image":   # 1.6.0: only images go to Reference Images
                continue
            cands = [img["path"]] + list(img.get("files") or [])
            path = next((c for c in cands if c and os.path.isfile(c)), None)
            if path:
                paths.append(path)
                seen.add(h)
        if not paths:
            return self._err(lang, "err_image_missing"), gr.skip(), gr.skip()
        from shared.gradio.gallery import get_list, get_state
        skipped = 0
        if mode == "append":
            current = _gallery_paths(gallery, state)
            have = set()
            for c in current:
                try:
                    have.add(storage._file_hash(c))
                except OSError:
                    pass
            keep = []
            for pth in paths:
                try:
                    dup = storage._file_hash(pth) in have
                except OSError:
                    dup = False
                if dup:
                    skipped += 1
                else:
                    keep.append(pth)
            paths = keep
            if not paths:
                msg = tr(lang, "refs_none")
                return {"ok": True, "kind": "info", "message": msg, "toast": msg, "sent": 0, "skipped": skipped}, gr.skip(), gr.skip()
            st = get_state(state)
            gallery_value = get_list(gallery)
            st["selected"] = len(gallery_value) - 1 if gallery_value else 0
        else:
            _, st = self.amg()._on_clear(state)
            st = get_state(st)
            st["items"] = []
            st["selected"] = None
            gallery_value = []
        staged = _stage_for_gallery(paths)
        gallery_update, st = self.amg()._on_add(staged, st, gallery_value)
        total = len(st.get("items") or [])
        if mode == "append":
            msg = tr(lang, "refs_appended_skip" if skipped else "refs_appended", n=len(staged), skipped=skipped, total=total)
        else:
            msg = tr(lang, "refs_used", n=len(staged))
        return {"ok": True, "message": msg, "toast": msg, "sent": len(staged), "skipped": skipped, "total": total,
                "resync": {"selected": st.get("selected"), "count": total}}, gallery_update, st

    def _applied_extras(self, tab, col, count):
        """Extra fields for the JS: reflib:applied payload + Prompt Library prompts to offer (never applied silently)."""
        extras = {"tab": tab, "applied": {"id": col["id"], "name": col["name"], "count": count}}
        if promptlink.available():
            mode = load_settings().get("on_apply_prompts", "offer")
            extras["prompt_mode"] = mode
            extras["prompts"] = [] if mode == "off" else promptlink.prompts_for_collection(col["id"])
        return extras

    def save_from_gallery(self, tab, name, gallery, state, lang="en"):
        name = (name or "").strip()
        if not name:
            return self._err(lang, "need_name"), None
        paths = _gallery_paths(gallery, state)
        if not paths:
            return self._err(lang, "empty_gallery"), None
        sources = [(p, os.path.basename(p)) for p in paths]
        col = storage.create_collection(name, sources, fallback=tr(lang, "default_name"))
        self._last_applied[tab] = col["id"]
        return {**self._ok(lang, "saved_col", name=col["name"], n=len(col["images"]), _cid=col["id"]), "id": col["id"]}, col

    def update_from_gallery(self, tab, collection_id, gallery, state, lang="en"):
        if not collection_id:
            return self._err(lang, "no_collection"), None
        paths = _gallery_paths(gallery, state)
        if not paths:
            return self._err(lang, "empty_gallery"), None
        sources = [(p, os.path.basename(p)) for p in paths]
        try:
            col = storage.replace_images(collection_id, sources)
        except storage.StorageError:
            return self._err(lang, "not_found"), None
        self._last_applied[tab] = col["id"]
        return {**self._ok(lang, "updated_col", name=col["name"], n=len(col["images"]), _cid=col["id"]), "id": col["id"]}, col

    # ------------------------------------------------------------ video library: load / save / notes
    def resize_start(self, src, preset, name, upscale_ok, lang="en"):
        """1.6.2 video resize -> Video Library. Returns a JSON-able response: {ok, job} | {ok:false, need_confirm, src, dst}."""
        from .reflib_core import resize as _rs
        if preset not in _rs.PRESETS:
            return self._err(lang, "bad_request")
        if not src or not os.path.isfile(src) or not media.is_video_path(src):
            return self._err(lang, "rs_no_video")
        try:
            p = _rs.plan(src, preset)
        except Exception as e:
            return {"ok": False, "error": str(e)}
        if not p["dst"][0]:
            return self._err(lang, "err_generic", e="ffprobe")
        if p["same"]:
            return {"ok": True, "same": True, "kind": "info", "toast": tr(lang, "rs_same", w=p["src"][0], h=p["src"][1])}
        if p["upscale"] and not upscale_ok:
            return {"ok": True, "quiet": True, "need_confirm": True, "src": p["src"], "dst": p["dst"], "preset": preset}
        rname = _rs.result_name(name or os.path.basename(src), preset)

        def store(out, job):
            entry, created = videostore.add_video(out, name=rname, source="resize",
                                                  meta={"resize": preset, "source_file": os.path.basename(src), "size": job.get("dst_size")},
                                                  fallback=rname)
            imagelib.invalidate()
            return {"video_id": entry["id"], "name": entry["name"], "created": bool(created)}
        jid = _rs.start(src, preset, rname, on_done=store)
        return {"ok": True, "quiet": True, "job": jid, "src": p["src"], "dst": p["dst"], "name": rname, "upscale": p["upscale"],
                "message": tr(lang, "rs_started", preset=preset)}

    def load_video(self, tab, vid, lang="en"):
        """Stage a copy of the stored video and return (out, gr.update for the Control Video)."""
        if not vid:
            return self._err(lang, "no_video"), gr.skip()
        try:
            v = videostore.get_video(vid)
            path = videostore.video_file(v)
        except storage.StorageError as e:
            return {"ok": False, "error": storage_error_text(lang, e)}, gr.skip()
        staged = _stage_video(path, v["name"])
        self._last_video[tab] = v["id"]
        out = {**self._ok(lang, "vloaded", name=v["name"]), "vid": v["id"],
               "vapplied": {"id": v["id"], "name": v["name"], "tab": tab}}
        return out, gr.update(value=staged)

    def save_video_from_input(self, tab, name, value, lang="en"):
        path = _public_api._clean_src(value)
        if not path or not os.path.isfile(path):
            return self._err(lang, "no_control_video"), None
        if not media.is_video_path(path):
            return self._err(lang, "err_not_video"), None
        try:
            entry, created = videostore.add_video(path, name=(name or "").strip() or None, source="manual",
                                                  fallback=tr(lang, "video_default_name"))
        except storage.StorageError as e:
            return {"ok": False, "error": storage_error_text(lang, e)}, None
        self._last_video[tab] = entry["id"]
        if created:
            out = self._ok(lang, "vsaved", name=entry["name"], _cid=entry["id"])
        else:
            out = {"ok": True, "message": tr(lang, "vdup", name=entry["name"]), "toast": tr(lang, "vdup", name=entry["name"]),
                   "kind": "info"}
        out["vid"] = entry["id"]
        return out, entry

    def note_toast(self, lang, note):
        """Toast payload for what api.add_video / api.add_image did with a file (saved / duplicate / ask)."""
        kind = note.get("kind")
        if note.get("what") == "image":
            col = note.get("collection") or tr(lang, "crops_name")
            if kind == "saved":
                out = self._ok(lang, "icrop_saved", collection=col, name=note.get("name") or "", _cid=note.get("collection_id"))
                out["reload"] = True   # refresh the collection bars / manager (new image or new "Crops" collection)
                return out
            if kind == "duplicate":
                return {"ok": True, "message": tr(lang, "icrop_dup", collection=col, name=note.get("name") or ""), "toast": tr(lang, "icrop_dup", collection=col, name=note.get("name") or ""),
                        "kind": "info"}
            if kind == "offer":
                return {"ok": True, "message": tr(lang, "icrop_offer", collection=col), "toast": tr(lang, "icrop_offer", collection=col),
                        "kind": "info", "offer_token": note.get("token"), "offer_kind": "image",
                        "offer_label": tr(lang, "icrop_offer_btn"), "sticky_ms": 20000}
            return {"ok": True, "quiet": True}
        if kind == "saved":
            key = "vcrop_saved" if note.get("source") == "cropper" else "vsaved"
            return {**self._ok(lang, key, name=note.get("name"), _cid=note.get("id")), "vid": note.get("id")}
        if kind == "duplicate":
            # Same crop already stored: no toast, just the muted status line.
            return {"ok": True, "message": tr(lang, "vdup", name=note.get("name")), "quiet": True, "vid": note.get("id")}
        if kind == "offer":
            return {"ok": True, "message": tr(lang, "vcrop_offer"), "toast": tr(lang, "vcrop_offer"), "kind": "info",
                    "offer_token": note.get("token"), "offer_label": tr(lang, "vcrop_offer_btn"), "sticky_ms": 20000}
        return {"ok": True, "quiet": True}

    # ---------------------------------------------------------------- video bar UI
    VBAR_KEYS = ("title", "dd", "load", "save", "manage", "name_tb", "name_ok", "name_cancel", "status", "info")

    def vbar_texts(self, lang, selected_id=None):
        choices, value = _video_dd_choices(lang, selected_id)
        t = lambda key: tr(lang, key)
        return {
            "title": {"value": _bar_title_html(t("vbar_label"), "video")},
            "dd": {"label": t("vbar_pick"), "choices": choices, "value": value},
            "load": {"value": t("vbar_load")},
            "save": {"value": t("vbar_save_as")},
            "manage": {"value": t("vbar_manage")},
            "name_tb": {"label": t("vbar_name"), "placeholder": t("vbar_name_ph")},
            "name_ok": {"value": t("bar_name_ok")},
            "name_cancel": {"value": t("bar_name_cancel")},
            "status": {"value": ""},
            "info": {"value": _video_info_html(lang, value)},
        }

    def _vdd_update(self, tab, lang, selected=None):
        ch, val = _video_dd_choices(lang, selected if selected is not None else self._last_video.get(tab))
        return gr.update(choices=ch, value=val, label=tr(lang, "vbar_pick"))

    def create_vbar(self, tab, show=True):
        lang = self._lang()
        tx = self.vbar_texts(lang, self._last_video.get(tab))
        video = self.vtargets[tab]["video"]
        with gr.Column(visible=show, elem_classes=["reflib-panel", "reflib-bar", "reflib-vbar"], elem_id=f"reflib_vbar_{tab}") as bar:
            with gr.Row(elem_classes=["reflib-bar-head"]):
                title = gr.HTML(tx["title"]["value"], elem_id=f"reflib_vbar_title_{tab}",
                                elem_classes=["reflib-bar-titlebox"], padding=False)
                status = gr.HTML("", elem_id=f"reflib_vbar_status_{tab}", elem_classes=["reflib-bar-status"], padding=False)
            with gr.Row(elem_classes=["reflib-row", "reflib-bar-row"]):
                dd = gr.Dropdown(elem_id=f"reflib_vbar_dd_{tab}", allow_custom_value=False, show_label=False,
                                 container=False, scale=1, min_width=180, elem_classes=["reflib-ctl", "reflib-bar-dd"],
                                 **{k: tx["dd"][k] for k in ("label", "choices", "value")})
                with gr.Row(elem_classes=["reflib-btns"]):
                    load_btn = gr.Button(tx["load"]["value"], variant="primary", size="lg", scale=0, min_width=0,
                                         elem_id=f"reflib_vbar_load_{tab}", elem_classes=["reflib-btn", "reflib-ico-load"])
                    save_btn = gr.Button(tx["save"]["value"], size="lg", scale=0, min_width=0,
                                         elem_id=f"reflib_vbar_save_{tab}", elem_classes=["reflib-btn", "reflib-ico-save"])
                    manage_btn = gr.Button(tx["manage"]["value"], size="lg", scale=0, min_width=0,
                                           elem_id=f"reflib_vbar_manage_{tab}", elem_classes=["reflib-btn", "reflib-ico-manage"])
            with gr.Row(elem_id=f"reflib_vbar_name_row_{tab}", elem_classes=["reflib-row", "reflib-bar-name"]):
                name_tb = gr.Textbox(elem_id=f"reflib_vbar_name_{tab}", show_label=False, container=False,
                                     lines=1, max_lines=1, scale=1, min_width=160, elem_classes=["reflib-ctl", "reflib-bar-name-tb"],
                                     **tx["name_tb"])
                with gr.Row(elem_classes=["reflib-btns"]):
                    name_ok = gr.Button(tx["name_ok"]["value"], variant="primary", size="lg", scale=0, min_width=0,
                                        elem_id=f"reflib_vbar_name_ok_{tab}", elem_classes=["reflib-btn", "reflib-ico-save"])
                    name_cancel = gr.Button(tx["name_cancel"]["value"], size="lg", scale=0, min_width=0,
                                            elem_id=f"reflib_vbar_name_cancel_{tab}", elem_classes=["reflib-btn", "reflib-ico-cancel"])
            info = gr.HTML(tx["info"]["value"], elem_id=f"reflib_vbar_info_{tab}", elem_classes=["reflib-vbar-info"], padding=False)
            toast_box = gr.Textbox(value="", visible=False, elem_id=f"reflib_vbar_toast_{tab}")
            hook_box = gr.Textbox(value="", visible=False, elem_id=f"reflib_vbar_hook_{tab}")
            ihook_box = gr.Textbox(value="", visible=False, elem_id=f"reflib_ihook_{tab}")
            bar_lang = gr.Textbox(value="", visible=False, elem_id=f"reflib_vbar_lang_{tab}")

        self._vbars[tab] = {"title": title, "dd": dd, "load": load_btn, "save": save_btn, "manage": manage_btn,
                            "name_tb": name_tb, "name_ok": name_ok, "name_cancel": name_cancel, "status": status,
                            "info": info, "toast": toast_box, "bar": bar}

        def do_load(vid, browser_lang=""):
            lang2 = self._lang(browser_lang)
            out, video_u = self.load_video(tab, vid, lang2)
            sel = out.get("vid") or vid
            return (_status_html(out), json.dumps(out, ensure_ascii=False), self._vdd_update(tab, lang2, sel), video_u,
                    _video_info_html(lang2, sel))

        def do_select(vid, browser_lang=""):
            lang2 = self._lang(browser_lang)
            if not vid:
                return "", "", gr.update(), gr.skip(), ""
            if not load_settings().get("auto_apply", True):
                return gr.update(), "", gr.update(), gr.skip(), _video_info_html(lang2, vid)
            return do_load(vid, browser_lang)

        def do_save(name, value, browser_lang=""):
            lang2 = self._lang(browser_lang)
            out, entry = self.save_video_from_input(tab, name, value, lang2)
            vid = (entry or {}).get("id")
            return (_status_html(out), json.dumps(out, ensure_ascii=False), self._vdd_update(tab, lang2, vid),
                    gr.update(value="" if out.get("ok") else name), _video_info_html(lang2, vid or self._last_video.get(tab)))

        toast_js = "(t) => { if (window.referenceLibrary) window.referenceLibrary.handleToast(t); }"
        saved_js = ("(t) => { if (window.referenceLibrary) { window.referenceLibrary.handleToast(t); "
                    f"window.referenceLibrary.afterSave('{tab}', t, 'vbar'); }} }}")
        lang1_js = "(a, l) => [a, navigator.language || '']"


        load_btn.click(fn=do_load, inputs=[dd, bar_lang], outputs=[status, toast_box, dd, video, info],
                       show_progress="hidden", js=lang1_js).then(fn=None, inputs=[toast_box], outputs=None, js=toast_js)
        dd.input(fn=do_select, inputs=[dd, bar_lang], outputs=[status, toast_box, dd, video, info],
                 show_progress="hidden", js=lang1_js).then(fn=None, inputs=[toast_box], outputs=None, js=toast_js)
        save_btn.click(fn=None, inputs=None, outputs=None, show_progress="hidden",
                       js=f"() => {{ if (window.referenceLibrary) window.referenceLibrary.toggleNameRow('{tab}', 'vbar'); }}")
        name_cancel.click(fn=None, inputs=None, outputs=[name_tb], show_progress="hidden",
                          js=f"() => {{ if (window.referenceLibrary) window.referenceLibrary.closeNameRow('{tab}', 'vbar'); return ''; }}")
        for trigger in (name_ok.click, name_tb.submit):
            trigger(fn=do_save, inputs=[name_tb, video, bar_lang], outputs=[status, toast_box, dd, name_tb, info],
                    show_progress="hidden", js="(n, v, l) => [n, v, navigator.language || '']").then(
                fn=None, inputs=[toast_box], outputs=None, js=saved_js)
        manage_btn.click(fn=None, inputs=None, outputs=None, show_progress="hidden",
                         js="() => { if (window.referenceLibrary) window.referenceLibrary.openTab('videos'); }")

        # Crops put into a video input by Cropper: show what add_video did (saved / ask / already there).
        for name, comp in self.vtargets[tab]["watch"].items():
            comp.change(fn=self._watch_fn(tab, name), inputs=[comp, bar_lang], outputs=[hook_box, dd, info, status],
                        show_progress="hidden", trigger_mode="always_last",
                        js="(v, l) => [v, navigator.language || '']").then(
                fn=None, inputs=[hook_box], outputs=None, js=toast_js)
        # Image crops (Cropper 1.2 -> api.add_image): same toasts when the cropped image lands in an image input.
        for name, comp in self.vtargets[tab].get("watch_images", {}).items():
            comp.change(fn=self._iwatch_fn(tab, name), inputs=[comp, bar_lang], outputs=[ihook_box],
                        show_progress="hidden", trigger_mode="always_last",
                        js="(v, l) => [v, navigator.language || '']").then(
                fn=None, inputs=[ihook_box], outputs=None, js=toast_js)
        return bar

    def _iwatch_fn(self, tab, name):
        def fn(value, browser_lang=""):
            if not _public_api.has_notes() or value is None:
                return ""
            if hasattr(value, "size") and hasattr(value, "mode"):   # gr.Image(type="pil"): no file name to match
                note = _public_api.take_recent_image_note()
            else:
                note = _public_api.take_note(value)
            if not note or note.get("what") != "image":
                return ""
            lang2 = self._lang(browser_lang)
            return json.dumps({**self.note_toast(lang2, note), "tab": tab}, ensure_ascii=False)
        fn.__name__ = f"reflib_iwatch_{tab}_{name}"
        return fn

    def _watch_fn(self, tab, name):
        def fn(value, browser_lang=""):
            if not _public_api.has_notes():
                return "", gr.skip(), gr.skip(), gr.skip()
            note = _public_api.take_note(value)
            if not note:
                return "", gr.skip(), gr.skip(), gr.skip()
            lang2 = self._lang(browser_lang)
            out = {**self.note_toast(lang2, note), "tab": tab}
            sel = self._last_video.get(tab)
            if name == "video_guide" and note.get("kind") in ("saved", "duplicate") and note.get("id"):
                sel = self._last_video[tab] = note["id"]   # the new control video is that library entry
            return (json.dumps(out, ensure_ascii=False), self._vdd_update(tab, lang2, sel), _video_info_html(lang2, sel),
                    _status_html(out) if out.get("message") and not out.get("offer_token") else gr.skip())
        fn.__name__ = f"reflib_watch_{tab}_{name}"
        return fn

    # ---------------------------------------------------------------- bar UI
    BAR_KEYS = ("title", "dd", "apply", "save", "update", "manage", "name_tb", "name_ok", "name_cancel", "status")

    def bar_texts(self, lang, selected_id=None):
        choices, value = _dropdown_choices(lang, selected_id)
        t = lambda key: tr(lang, key)
        return {
            "title": {"value": _bar_title_html(t("bar_label"))},
            "dd": {"label": t("bar_pick"), "choices": choices, "value": value},
            "apply": {"value": t("bar_apply")},
            "save": {"value": t("bar_save_as")},
            "update": {"value": t("bar_update")},
            "manage": {"value": t("bar_manage")},
            "name_tb": {"label": t("bar_name"), "placeholder": t("bar_name_ph")},
            "name_ok": {"value": t("bar_name_ok")},
            "name_cancel": {"value": t("bar_name_cancel")},
            "status": {"value": ""},
        }

    def bar_updates(self, tab, lang):
        bar = self._bars.get(tab) or {}
        if not bar:
            return []
        texts = self.bar_texts(lang, self._last_applied.get(tab))
        # Keep the dropdown's current selection when only relabelling: prefer last_applied, else "".
        return [gr.update(**texts[key]) for key in self.BAR_KEYS]

    def all_bar_updates(self, lang):
        out = []
        for tab in TAB_IDS:
            out.extend(self.bar_updates(tab, lang))
        return out

    def create_bar(self, tab, gallery, state):
        lang = self._lang()
        tx = self.bar_texts(lang, self._last_applied.get(tab))
        with gr.Column(elem_classes=["reflib-panel", "reflib-bar"], elem_id=f"reflib_bar_{tab}") as bar:
            with gr.Row(elem_classes=["reflib-bar-head"]):
                title = gr.HTML(tx["title"]["value"], elem_id=f"reflib_bar_title_{tab}",
                                elem_classes=["reflib-bar-titlebox"], padding=False)
                status = gr.HTML("", elem_id=f"reflib_bar_status_{tab}", elem_classes=["reflib-bar-status"],
                                 padding=False)
            with gr.Row(elem_classes=["reflib-row", "reflib-bar-row"]):
                dd = gr.Dropdown(elem_id=f"reflib_bar_dd_{tab}", allow_custom_value=False, show_label=False,
                                 container=False, scale=1, min_width=180, elem_classes=["reflib-ctl", "reflib-bar-dd"],
                                 **{k: tx["dd"][k] for k in ("label", "choices", "value")})
                with gr.Row(elem_classes=["reflib-btns"]):
                    apply_btn = gr.Button(tx["apply"]["value"], variant="primary", size="lg", scale=0, min_width=0,
                                          elem_id=f"reflib_bar_apply_{tab}", elem_classes=["reflib-btn", "reflib-ico-apply"])
                    save_btn = gr.Button(tx["save"]["value"], size="lg", scale=0, min_width=0,
                                         elem_id=f"reflib_bar_save_{tab}", elem_classes=["reflib-btn", "reflib-ico-save"])
                    update_btn = gr.Button(tx["update"]["value"], size="lg", scale=0, min_width=0,
                                           elem_id=f"reflib_bar_update_{tab}", elem_classes=["reflib-btn", "reflib-ico-refresh"])
                    manage_btn = gr.Button(tx["manage"]["value"], size="lg", scale=0, min_width=0,
                                           elem_id=f"reflib_bar_manage_{tab}", elem_classes=["reflib-btn", "reflib-ico-manage"])
            # Shown only while "Save as…" is open (data-open on the row, toggled by reference_library.js).
            with gr.Row(elem_id=f"reflib_bar_name_row_{tab}", elem_classes=["reflib-row", "reflib-bar-name"]) as name_row:
                name_tb = gr.Textbox(elem_id=f"reflib_bar_name_{tab}", show_label=False, container=False,
                                     lines=1, max_lines=1, scale=1, min_width=160, elem_classes=["reflib-ctl", "reflib-bar-name-tb"],
                                     **tx["name_tb"])
                with gr.Row(elem_classes=["reflib-btns"]):
                    name_ok = gr.Button(tx["name_ok"]["value"], variant="primary", size="lg", scale=0, min_width=0,
                                        elem_id=f"reflib_bar_name_ok_{tab}", elem_classes=["reflib-btn", "reflib-ico-save"])
                    name_cancel = gr.Button(tx["name_cancel"]["value"], size="lg", scale=0, min_width=0,
                                            elem_id=f"reflib_bar_name_cancel_{tab}", elem_classes=["reflib-btn", "reflib-ico-cancel"])
            # Linked prompts (Prompt Library) offered as chips; filled by reference_library.js, hidden when empty.
            gr.HTML("", elem_id=f"reflib_bar_chips_{tab}", elem_classes=["reflib-bar-chips"], padding=False)
            toast_box = gr.Textbox(value="", visible=False, elem_id=f"reflib_bar_toast_{tab}")
            bar_lang = gr.Textbox(value="", visible=False, elem_id=f"reflib_bar_lang_{tab}")

        self._bars[tab] = {"title": title, "dd": dd, "apply": apply_btn, "save": save_btn, "update": update_btn,
                           "manage": manage_btn, "name_row": name_row, "name_tb": name_tb,
                           "name_ok": name_ok, "name_cancel": name_cancel, "status": status, "toast": toast_box}

        def refresh_dd(selected=None, browser_lang=""):
            lang2 = self._lang(browser_lang)
            ch, val = _dropdown_choices(lang2, selected if selected is not None else self._last_applied.get(tab))
            return gr.update(choices=ch, value=val, label=tr(lang2, "bar_pick"))

        def do_apply(cid, gal, st, browser_lang=""):
            lang2 = self._lang(browser_lang)
            out, gal_u, st_u = self.apply_collection(tab, cid, gal, st, lang=lang2)
            toast = json.dumps(out, ensure_ascii=False)
            return (_status_html(out), toast, refresh_dd(out.get("id") or cid, browser_lang), gal_u, st_u)

        def do_select(cid, gal, st, browser_lang=""):
            if not load_settings().get("auto_apply", True) or not cid:
                return gr.update(), gr.update(), gr.update(), gr.skip(), gr.skip()
            return do_apply(cid, gal, st, browser_lang)

        def do_save(name, gal, st, browser_lang=""):
            lang2 = self._lang(browser_lang)
            out, col = self.save_from_gallery(tab, name, gal, st, lang=lang2)
            toast = json.dumps(out, ensure_ascii=False)
            cid = (col or {}).get("id") if out.get("ok") else None
            return (_status_html(out), toast, refresh_dd(cid, browser_lang),
                    gr.update(value="" if out.get("ok") else name))

        def do_update(cid, gal, st, browser_lang=""):
            lang2 = self._lang(browser_lang)
            out, col = self.update_from_gallery(tab, cid, gal, st, lang=lang2)
            toast = json.dumps(out, ensure_ascii=False)
            return _status_html(out), toast, refresh_dd((col or {}).get("id") or cid, browser_lang)

        toast_js = "(t) => { if (window.referenceLibrary) window.referenceLibrary.handleToast(t); }"
        saved_js = ("(t) => { if (window.referenceLibrary) { window.referenceLibrary.handleToast(t); "
                    f"window.referenceLibrary.afterSave('{tab}', t); }} }}")
        lang_js = "(a,g,s,l) => [a, g, s, navigator.language || '']"

        apply_btn.click(fn=do_apply, inputs=[dd, gallery, state, bar_lang],
                        outputs=[status, toast_box, dd, gallery, state], show_progress="hidden",
                        js=lang_js).then(fn=None, inputs=[toast_box], outputs=None, js=toast_js)

        dd.input(fn=do_select, inputs=[dd, gallery, state, bar_lang],
                  outputs=[status, toast_box, dd, gallery, state], show_progress="hidden",
                  js=lang_js).then(fn=None, inputs=[toast_box], outputs=None, js=toast_js)

        save_btn.click(fn=None, inputs=None, outputs=None, show_progress="hidden",
                       js=f"() => {{ if (window.referenceLibrary) window.referenceLibrary.toggleNameRow('{tab}'); }}")
        name_cancel.click(fn=None, inputs=None, outputs=[name_tb], show_progress="hidden",
                          js=f"() => {{ if (window.referenceLibrary) window.referenceLibrary.closeNameRow('{tab}'); return ''; }}")
        for trigger in (name_ok.click, name_tb.submit):
            trigger(fn=do_save, inputs=[name_tb, gallery, state, bar_lang],
                    outputs=[status, toast_box, dd, name_tb], show_progress="hidden",
                    js=lang_js).then(fn=None, inputs=[toast_box], outputs=None, js=saved_js)

        update_btn.click(fn=do_update, inputs=[dd, gallery, state, bar_lang],
                         outputs=[status, toast_box, dd], show_progress="hidden",
                         js=lang_js).then(fn=None, inputs=[toast_box], outputs=None, js=toast_js)

        manage_btn.click(fn=None, inputs=None, outputs=None, show_progress="hidden",
                         js="() => { if (window.referenceLibrary) window.referenceLibrary.openTab(); }")

        return bar

    # -------------------------------------------------------- settings + manager tab
    TAB_KEYS = (
        "intro", "settings_acc", "language", "sec_apply", "replace_mode", "auto_apply", "sec_bar", "show_edit",
        "sec_messages", "toasts", "toast_s", "sec_prompts", "on_apply_prompts", "save", "sec_manager",
        "mgr_dd", "mgr_refresh", "mgr_name", "mgr_new", "mgr_rename", "mgr_dup", "mgr_delete", "mgr_apply",
        "mgr_prompts_title", "mgr_prompts_save", "mgr_gallery", "mgr_gallery_title", "mgr_add", "mgr_remove", "mgr_left", "mgr_right", "mgr_cover", "mgr_export", "mgr_import",
        "video_bar", "sec_videos", "crop_save", "sec_img_crops", "crop_save_images", "index_paused", "browser_fullscreen", "vsec", "vmgr_title", "vmgr_name", "vmgr_rename", "vmgr_load", "vmgr_delete",
        "vmgr_import", "vmgr_left", "vmgr_right", "vmgr_download", "vmgr_export",
    )

    def tab_texts(self, lang):
        t = lambda key: tr(lang, key)
        ch, _ = _dropdown_choices(lang)
        return {
            "intro": {"value": f"## Reference Library {PLUGIN_VERSION}\n" + t("intro")},
            "settings_acc": {"label": t("settings_acc")},
            "language": {"label": t("language"), "info": t("language_info"), "choices": language_choices(lang)},
            "sec_apply": {"value": t("sec_apply")},
            "replace_mode": {"label": t("replace_mode"), "choices": replace_choices(lang)},
            "auto_apply": {"label": t("auto_apply")},
            "sec_bar": {"value": t("sec_bar")},
            "show_edit": {"label": t("show_edit")},
            "sec_messages": {"value": t("sec_messages")},
            "toasts": {"label": t("toasts"), "info": t("toasts_info")},
            "toast_s": {"label": t("toast_s")},
            "sec_prompts": {"value": t("sec_prompts")},
            "on_apply_prompts": {"label": t("on_apply_prompts"), "info": t("on_apply_prompts_info"),
                                 "choices": prompt_mode_choices(lang)},
            "mgr_prompts_title": {"value": _panel_title_html(t("mgr_prompts_title"), t("mgr_prompts_info"))},
            "mgr_prompts_save": {"value": t("mgr_prompts_save")},
            "save": {"value": t("save")},
            "sec_manager": {"value": t("sec_manager")},
            "mgr_dd": {"label": t("mgr_pick"), "choices": ch},
            "mgr_refresh": {"value": t("mgr_refresh")},
            "mgr_name": {"label": t("mgr_name"), "placeholder": t("mgr_name_ph")},
            "mgr_new": {"value": t("mgr_new_empty")},
            "mgr_rename": {"value": t("mgr_rename")},
            "mgr_dup": {"value": t("mgr_duplicate")},
            "mgr_delete": {"value": t("mgr_delete")},
            "mgr_apply": {"value": t("mgr_apply")},
            "mgr_gallery": {"label": t("mgr_gallery")},
            "mgr_gallery_title": {"value": _panel_title_html(t("mgr_gallery"))},
            "mgr_add": {"label": t("mgr_add")},
            "mgr_remove": {"value": t("mgr_remove")},
            "mgr_left": {"value": t("mgr_left")},
            "mgr_right": {"value": t("mgr_right")},
            "mgr_cover": {"value": t("mgr_cover")},
            "mgr_export": {"value": t("mgr_export")},
            "mgr_import": {"label": t("mgr_import")},
            "video_bar": {"label": t("video_bar")},
            "sec_videos": {"value": t("sec_videos")},
            "crop_save": {"label": t("crop_save"), "info": t("crop_save_info"), "choices": crop_save_choices(lang)},
            "sec_img_crops": {"value": t("sec_img_crops")},
            "crop_save_images": {"label": t("crop_save_images"), "info": t("crop_save_images_info"),
                                 "choices": crop_save_images_choices(lang)},
            "index_paused": {"label": t("index_paused"), "info": t("index_paused_info")},
            "browser_fullscreen": {"label": t("browser_fullscreen"), "info": t("browser_fullscreen_info")},
            "vsec": {"value": t("vsec")},
            "vmgr_title": {"value": _panel_title_html(tr(lang, "vmgr_title", n=len(videostore.list_videos())), t("vmgr_title_tip"))},
            "vmgr_name": {"label": t("vmgr_name"), "placeholder": t("vmgr_name_ph")},
            "vmgr_rename": {"value": t("vmgr_rename")},
            "vmgr_load": {"value": t("vmgr_load")},
            "vmgr_delete": {"value": t("vmgr_delete")},
            "vmgr_import": {"label": t("vmgr_import")},
            "vmgr_left": {"value": t("vmgr_left")},
            "vmgr_right": {"value": t("vmgr_right")},
            "vmgr_download": {"value": t("vmgr_download")},
            "vmgr_export": {"value": t("vmgr_export")},
        }

    def tab_updates(self, lang):
        texts = self.tab_texts(lang)
        return [gr.update(**texts[key]) for key in self.TAB_KEYS]

    def create_ui(self):
        current = lambda key: (lambda: load_settings()[key])
        lang = resolve_lang(load_settings()["language"])
        tx = self.tab_texts(lang)
        ui = {}
        gr.HTML(f"<style>{load_css()}</style>", elem_classes=["reflib-hidden"], padding=False)
        ui["intro"] = gr.Markdown(tx["intro"]["value"], elem_id="reflib_intro")
        with gr.Accordion(tx["settings_acc"]["label"], open=False, elem_id="reflib_settings_acc") as settings_acc:
            ui["settings_acc"] = settings_acc
            with gr.Row():
                ui["language"] = gr.Dropdown(value=current("language"), elem_id="reflib_language", **tx["language"])
            with gr.Group():
                ui["sec_apply"] = gr.Markdown(tx["sec_apply"]["value"])
                with gr.Row():
                    ui["replace_mode"] = gr.Dropdown(value=current("replace_mode"), elem_id="reflib_replace_mode", **tx["replace_mode"])
                    ui["auto_apply"] = gr.Checkbox(value=current("auto_apply"), elem_id="reflib_auto_apply", **tx["auto_apply"])
            with gr.Group():
                ui["sec_bar"] = gr.Markdown(tx["sec_bar"]["value"])
                with gr.Row():
                    ui["show_edit"] = gr.Checkbox(value=current("show_edit_bar"), elem_id="reflib_show_edit", **tx["show_edit"])
                    ui["video_bar"] = gr.Checkbox(value=current("video_bar"), elem_id="reflib_video_bar", **tx["video_bar"])
            with gr.Group():
                ui["sec_videos"] = gr.Markdown(tx["sec_videos"]["value"])
                ui["crop_save"] = gr.Dropdown(value=current("crop_save"), elem_id="reflib_crop_save", **tx["crop_save"])
            with gr.Group():
                ui["sec_img_crops"] = gr.Markdown(tx["sec_img_crops"]["value"])
                ui["crop_save_images"] = gr.Dropdown(value=current("crop_save_images"), elem_id="reflib_crop_save_images",
                                                     **tx["crop_save_images"])
                ui["index_paused"] = gr.Checkbox(value=current("index_paused"), elem_id="reflib_index_paused", **tx["index_paused"])
                ui["browser_fullscreen"] = gr.Checkbox(value=current("browser_fullscreen"), elem_id="reflib_browser_fullscreen", **tx["browser_fullscreen"])
            with gr.Group():
                ui["sec_messages"] = gr.Markdown(tx["sec_messages"]["value"])
                with gr.Row():
                    ui["toasts"] = gr.Checkbox(value=current("toasts"), elem_id="reflib_toasts", **tx["toasts"])
                    ui["toast_s"] = gr.Number(value=lambda: load_settings()["toast_ms"] / 1000, minimum=1, maximum=30, step=0.5,
                                              elem_id="reflib_toast_s", **tx["toast_s"])
            with gr.Group(visible=False, elem_id="reflib_prompts_settings") as prompts_settings_group:
                ui["sec_prompts"] = gr.Markdown(tx["sec_prompts"]["value"])
                ui["on_apply_prompts"] = gr.Dropdown(value=current("on_apply_prompts"), elem_id="reflib_on_apply_prompts",
                                                     **tx["on_apply_prompts"])
            ui["save"] = gr.Button(tx["save"]["value"], variant="primary", elem_id="reflib_save_settings")
            status = gr.Markdown("", elem_id="reflib_status")

        ui["sec_manager"] = gr.Markdown(tx["sec_manager"]["value"], elem_id="reflib_sec_manager",
                                        elem_classes=["reflib-section-title"])
        B = lambda key, ico, **kw: gr.Button(tx[key]["value"], size="lg", scale=0, min_width=0, elem_id=f"reflib_{key}",
                                             elem_classes=["reflib-btn", f"reflib-ico-{ico}"] + kw.pop("classes", []), **kw)
        with gr.Column(elem_classes=["reflib-panel", "reflib-mgr"], elem_id="reflib_mgr_panel"):
            with gr.Row(elem_classes=["reflib-row"]):
                ui["mgr_dd"] = gr.Dropdown(value="", elem_id="reflib_mgr_dd", show_label=False, container=False, scale=1,
                                           min_width=200, elem_classes=["reflib-ctl"],
                                           **{k: tx["mgr_dd"][k] for k in ("label", "choices")})
                with gr.Row(elem_classes=["reflib-btns"]):
                    ui["mgr_refresh"] = B("mgr_refresh", "refresh")
                    ui["mgr_apply"] = B("mgr_apply", "apply", variant="primary")
                    ui["mgr_delete"] = B("mgr_delete", "delete", classes=["reflib-danger"])
            with gr.Row(elem_classes=["reflib-row"]):
                ui["mgr_name"] = gr.Textbox(elem_id="reflib_mgr_name", show_label=False, container=False, lines=1,
                                            max_lines=1, scale=1, min_width=200, elem_classes=["reflib-ctl"],
                                            label=tx["mgr_name"]["label"], placeholder=tx["mgr_name"]["placeholder"])
                with gr.Row(elem_classes=["reflib-btns"]):
                    ui["mgr_rename"] = B("mgr_rename", "rename")
                    ui["mgr_dup"] = B("mgr_dup", "duplicate")
                    ui["mgr_new"] = B("mgr_new", "new")
        with gr.Column(visible=False, elem_classes=["reflib-panel", "reflib-mgr"], elem_id="reflib_prompts_panel") as prompts_panel:
            ui["mgr_prompts_title"] = gr.HTML(tx["mgr_prompts_title"]["value"], padding=False,
                                              elem_id="reflib_mgr_prompts_title", elem_classes=["reflib-panel-head"])
            with gr.Row(elem_classes=["reflib-row"]):
                mgr_prompts = gr.Dropdown(choices=[], value=[], multiselect=True, show_label=False, container=False,
                                          scale=1, min_width=200, elem_id="reflib_mgr_prompts",
                                          elem_classes=["reflib-ctl", "reflib-ctl-multi"], label=tr(lang, "mgr_prompts"))
                with gr.Row(elem_classes=["reflib-btns"]):
                    ui["mgr_prompts_save"] = B("mgr_prompts_save", "save", variant="primary")
        with gr.Column(elem_classes=["reflib-panel", "reflib-mgr"], elem_id="reflib_mgr_images_panel"):
            ui["mgr_gallery_title"] = gr.HTML(_panel_title_html(tx["mgr_gallery"]["label"]), padding=False,
                                              elem_id="reflib_mgr_gallery_title", elem_classes=["reflib-panel-head"])
            ui["mgr_gallery"] = gr.Gallery(columns=8, height=170, preview=False, allow_preview=False, show_label=False,
                                           object_fit="cover", container=False, elem_id="reflib_mgr_gallery",
                                           elem_classes=["reflib-mgr-gallery"], label=tx["mgr_gallery"]["label"])
            mgr_selected = gr.Number(value=-1, visible=False, elem_id="reflib_mgr_selected")
            delete_armed = gr.Textbox(value="{}", visible=False, elem_id="reflib_delete_armed")
            with gr.Row(elem_classes=["reflib-row", "reflib-tools"]):
                with gr.Row(elem_classes=["reflib-btns"]):
                    ui["mgr_add"] = gr.UploadButton(label=tx["mgr_add"]["label"], file_types=["image"], file_count="multiple",
                                                    size="lg", scale=0, min_width=0, elem_id="reflib_mgr_add",
                                                    elem_classes=["reflib-btn", "reflib-ico-new"])
                    ui["mgr_remove"] = B("mgr_remove", "remove")
                    ui["mgr_left"] = B("mgr_left", "left")
                    ui["mgr_right"] = B("mgr_right", "right")
                    ui["mgr_cover"] = B("mgr_cover", "cover")
                with gr.Row(elem_classes=["reflib-btns", "reflib-btns-end"]):
                    ui["mgr_export"] = B("mgr_export", "export")
                    ui["mgr_import"] = gr.UploadButton(label=tx["mgr_import"]["label"], file_types=[".zip"], file_count="single",
                                                       size="lg", scale=0, min_width=0, elem_id="reflib_mgr_import",
                                                       elem_classes=["reflib-btn", "reflib-ico-import"])
            mgr_export_file = gr.File(label="", visible=False, elem_id="reflib_mgr_export_file")
        mgr_status = gr.Markdown("", elem_id="reflib_mgr_status", elem_classes=["reflib-mgr-status"])
        mgr_toast = gr.Textbox(value="", visible=False, elem_id="reflib_mgr_toast")
        # ---- video library section (1.2) ----
        ui["vsec"] = gr.Markdown(tx["vsec"]["value"], elem_id="reflib_vsec", elem_classes=["reflib-section-title"])
        with gr.Column(elem_classes=["reflib-panel", "reflib-mgr"], elem_id="reflib_vmgr_panel"):
            ui["vmgr_title"] = gr.HTML(tx["vmgr_title"]["value"], padding=False, elem_id="reflib_vmgr_title",
                                       elem_classes=["reflib-panel-head"])
            vmgr_gallery = gr.Gallery(columns=6, height=330, preview=False, allow_preview=False, show_label=False,
                                      object_fit="cover", container=False, elem_id="reflib_vmgr_gallery",
                                      elem_classes=["reflib-mgr-gallery", "reflib-vmgr-gallery"], label="Videos",
                                      value=lambda: _vmgr_gallery_value(videostore.list_videos()))
            with gr.Row(elem_classes=["reflib-row"]):
                ui["vmgr_name"] = gr.Textbox(elem_id="reflib_vmgr_name", show_label=False, container=False, lines=1,
                                             max_lines=1, scale=1, min_width=200, elem_classes=["reflib-ctl"],
                                             label=tx["vmgr_name"]["label"], placeholder=tx["vmgr_name"]["placeholder"])
                with gr.Row(elem_classes=["reflib-btns"]):
                    ui["vmgr_rename"] = B("vmgr_rename", "rename")
                    ui["vmgr_load"] = B("vmgr_load", "load", variant="primary")
                    ui["vmgr_delete"] = B("vmgr_delete", "delete", classes=["reflib-danger"])
            with gr.Row(elem_classes=["reflib-row", "reflib-tools"]):
                with gr.Row(elem_classes=["reflib-btns"]):
                    ui["vmgr_import"] = gr.UploadButton(label=tx["vmgr_import"]["label"], file_types=["video", ".zip"],
                                                        file_count="multiple", size="lg", scale=0, min_width=0,
                                                        elem_id="reflib_vmgr_import", elem_classes=["reflib-btn", "reflib-ico-import"])
                    ui["vmgr_left"] = B("vmgr_left", "left")
                    ui["vmgr_right"] = B("vmgr_right", "right")
                with gr.Row(elem_classes=["reflib-btns", "reflib-btns-end"]):
                    ui["vmgr_download"] = B("vmgr_download", "export")
                    ui["vmgr_export"] = B("vmgr_export", "archive")
            with gr.Row(elem_classes=["reflib-row", "reflib-vmgr-detail"]):
                vmgr_preview = gr.Video(value=None, interactive=False, show_label=False, height=240, scale=1, min_width=240,
                                        elem_id="reflib_vmgr_preview", elem_classes=["reflib-vmgr-preview"], label="Preview")
                vmgr_meta = gr.HTML(lambda: _vmeta_html(self._lang(), None, empty=not videostore.list_videos()),
                                    elem_id="reflib_vmgr_meta", elem_classes=["reflib-vmgr-meta"], padding=False)
            vmgr_file = gr.File(label="", visible=False, elem_id="reflib_vmgr_file")
        vmgr_status = gr.Markdown("", elem_id="reflib_vmgr_status", elem_classes=["reflib-mgr-status"])
        vmgr_toast = gr.Textbox(value="", visible=False, elem_id="reflib_vmgr_toast")
        vmgr_sel = gr.Textbox(value="", visible=False, elem_id="reflib_vmgr_sel")
        vdelete_armed = gr.Textbox(value="{}", visible=False, elem_id="reflib_vdelete_armed")
        # aliases used by existing handlers below
        mgr_dd, mgr_refresh, mgr_name = ui["mgr_dd"], ui["mgr_refresh"], ui["mgr_name"]
        mgr_new, mgr_rename, mgr_dup = ui["mgr_new"], ui["mgr_rename"], ui["mgr_dup"]
        mgr_delete, mgr_apply = ui["mgr_delete"], ui["mgr_apply"]
        mgr_gallery = ui["mgr_gallery"]
        mgr_add, mgr_remove = ui["mgr_add"], ui["mgr_remove"]
        mgr_left, mgr_right, mgr_cover = ui["mgr_left"], ui["mgr_right"], ui["mgr_cover"]
        mgr_export, mgr_import = ui["mgr_export"], ui["mgr_import"]

        tab_outputs = [ui[key] for key in self.TAB_KEYS]

        with gr.Group(elem_classes="reflib-hidden"):
            settings_json = gr.Textbox(value=lambda: json.dumps(load_settings()), elem_id="reflib_settings_json", show_label=False)
            browser_lang = gr.Textbox(value="", elem_id="reflib_browser_lang", show_label=False)
            localize_btn = gr.Button("localize", elem_id="reflib_localize")
            prompts_refresh_btn = gr.Button("prompts", elem_id="reflib_prompts_refresh")
            prompts_refresh_out = gr.Textbox(value="", elem_id="reflib_prompts_refresh_out", show_label=False)
            # Bridge buttons to apply from the manager tab into each form's image_refs
            bridge_req = gr.Textbox(value="", elem_id="reflib_bridge_req", show_label=False)
            bridge_resp = gr.Textbox(value="", elem_id="reflib_bridge_resp", show_label=False)
            for key, target in list(self.targets.items()):
                btn = gr.Button("bridge", elem_id="reflib_bridge_" + key.replace(":", "_"))
                bar = self._bars.get(target["tab"]) or {}
                extra_outs = [bar["dd"], bar["status"]] if bar else []
                btn.click(fn=self._bridge_fn(key, with_bar=bool(bar)), inputs=[bridge_req, target["gallery"], target["state"]],
                          outputs=[bridge_resp, target["gallery"], target["state"]] + extra_outs, show_progress="hidden",
                          trigger_mode="multiple", queue=True).then(
                    fn=None, inputs=[bridge_resp], outputs=None, show_progress="hidden",
                    js="(r) => { if (window.referenceLibrary) window.referenceLibrary.bridgeResponse(r); }")
            # Video bridges (target "<tab>:video_guide"): manager Load, reflib:video-apply / reflib:video-add, Save offers.
            for tab, vt in list(self.vtargets.items()):
                vbar = self._vbars.get(tab) or {}
                extra_outs = [vbar["dd"], vbar["status"], vbar["info"]] if vbar else []
                btn = gr.Button("vbridge", elem_id=f"reflib_bridge_{tab}_video_guide")
                btn.click(fn=self._vbridge_fn(tab, with_bar=bool(vbar)), inputs=[bridge_req, vt["video"]],
                          outputs=[bridge_resp, vt["video"]] + extra_outs, show_progress="hidden",
                          trigger_mode="multiple", queue=True).then(
                    fn=None, inputs=[bridge_resp], outputs=None, show_progress="hidden",
                    js="(r) => { if (window.referenceLibrary) window.referenceLibrary.bridgeResponse(r); }")
            # 1.5.5 history -> generator form media (control video, masks, start/end images): target "<tab>:history"
            for tab in list(self.vtargets):
                hcomps = self._hist_targets(tab)
                hbtn = gr.Button("hbridge", elem_id=f"reflib_bridge_{tab}_history")
                hbtn.click(fn=lambda raw, t=tab: self.history_media(t, raw), inputs=[bridge_req],
                           outputs=[bridge_resp] + [c for _, c in hcomps], show_progress="hidden", queue=True).then(
                    fn=None, inputs=[bridge_resp], outputs=None, show_progress="hidden",
                    js="(r) => { if (window.referenceLibrary) window.referenceLibrary.bridgeResponse(r); }")
            # 1.6.4 "Guardar en librería": one bridge per WanGP video / audio input, reading its CURRENT value
            for tab, comps in list(self.save_targets.items()):
                for field, comp in comps.items():
                    sbtn = gr.Button("sbridge", elem_id=f"reflib_bridge_{tab}_save_{field}")
                    sbtn.click(fn=lambda raw, value, t=tab, f=field: self.save_input(t, f, raw, value), inputs=[bridge_req, comp],
                               outputs=[bridge_resp], show_progress="hidden", trigger_mode="multiple", queue=True).then(
                        fn=None, inputs=[bridge_resp], outputs=None, show_progress="hidden",
                        js="(r) => { if (window.referenceLibrary) window.referenceLibrary.bridgeResponse(r); }")
            vreload_btn = gr.Button("vreload", elem_id="reflib_vreload")
            # Inline rename (pencil, 1.3.0) and a refresh of every collection/video list after changes made elsewhere.
            rename_req = gr.Textbox(value="", elem_id="reflib_rename_req", show_label=False)
            rename_out = gr.Textbox(value="", elem_id="reflib_rename_out", show_label=False)
            rename_btn = gr.Button("rename", elem_id="reflib_rename_btn")
            reload_btn = gr.Button("reload", elem_id="reflib_reload")
            # Image browser (1.4.0): one JSON bridge + a hidden multi-file upload for "Import images".
            ilib_req = gr.Textbox(value="", elem_id="reflib_ilib_req", show_label=False)
            ilib_resp = gr.Textbox(value="", elem_id="reflib_ilib_resp", show_label=False)
            ilib_btn = gr.Button("ilib", elem_id="reflib_ilib_btn")
            ilib_upload = gr.File(file_count="multiple", file_types=["image", "video", "audio"], elem_id="reflib_ilib_upload", show_label=False)
            # 1.4.3: a second, unqueued channel for small fast calls (thumbnails, scan progress, folder picker), so they
            # never wait behind a big list refresh or an import in the Gradio queue.
            ilib_fast_req = gr.Textbox(value="", elem_id="reflib_ilib_fast_req", show_label=False)
            ilib_fast_resp = gr.Textbox(value="", elem_id="reflib_ilib_fast_resp", show_label=False)
            ilib_fast_btn = gr.Button("ilib-fast", elem_id="reflib_ilib_fast_btn")
            ilib_upload_meta = gr.Textbox(value="", elem_id="reflib_ilib_upload_meta", show_label=False)

        # Bar components are created before this tab (insert_after during form build).
        bar_outputs = []
        self._bar_localize_order = []
        for tab in TAB_IDS:
            bar = self._bars.get(tab)
            if not bar:
                continue
            for key in self.BAR_KEYS:
                bar_outputs.append(bar[key])
                self._bar_localize_order.append((tab, key))
        self._vbar_localize_order = []
        for tab in TAB_IDS:
            vbar = self._vbars.get(tab)
            if not vbar:
                continue
            for key in self.VBAR_KEYS:
                bar_outputs.append(vbar[key])
                self._vbar_localize_order.append((tab, key))

        prompt_outputs = [prompts_settings_group, prompts_panel, mgr_prompts]

        # ---- localize / settings ----
        localize_btn.click(
            fn=self._localize, inputs=[browser_lang], outputs=[settings_json] + tab_outputs + bar_outputs + prompt_outputs,
            show_progress="hidden", queue=False,
            js="(x) => JSON.stringify({ browser: navigator.language || '', lang: (window.referenceLibrary && window.referenceLibrary.tabRequest) || null })",
        ).then(fn=None, inputs=[settings_json], outputs=None,
               js="(s) => { if (window.referenceLibrary) window.referenceLibrary.applySettings(s, true); }")

        ui["save"].click(
            fn=self._save_from_ui,
            inputs=[ui["replace_mode"], ui["auto_apply"], ui["show_edit"], ui["toasts"], ui["toast_s"], ui["language"],
                    ui["on_apply_prompts"], ui["video_bar"], ui["crop_save"], ui["crop_save_images"], ui["index_paused"], browser_lang, ui["browser_fullscreen"]],
            outputs=[status, settings_json] + tab_outputs + bar_outputs + prompt_outputs, show_progress="hidden",
            js="(a0,a1,a2,a3,a4,a5,a6,a7,a8,a9,a10,l,fs) => [a0,a1,a2,a3,a4,a5,a6,a7,a8,a9,a10, navigator.language || '', fs]",
        ).then(fn=None, inputs=[settings_json], outputs=None,
               js="(s) => { if (window.referenceLibrary) window.referenceLibrary.applySettings(s, 'saved'); }")

        # ---- manager handlers ----
        def refresh_mgr(cid="", browser_lang=""):
            lang2 = self._lang(browser_lang)
            ch, val = _dropdown_choices(lang2, cid or None)
            if cid and val != cid:
                val = ""
            name = ""
            if val:
                try:
                    name = storage.get_collection(val)["name"]
                except storage.StorageError:
                    val = ""
            return (gr.update(choices=ch, value=val, label=tr(lang2, "mgr_pick")),
                    gr.update(value=name, label=tr(lang2, "mgr_name")),
                    _manager_gallery_value(val),
                    gr.update(value=-1))

        def on_pick(cid, browser_lang=""):
            return refresh_mgr(cid, browser_lang)

        def on_new(name, browser_lang=""):
            lang2 = self._lang(browser_lang)
            name = (name or "").strip() or storage.unique_name(tr(lang2, "default_name"))
            col = storage.create_collection(name, [], fallback=storage.unique_name(tr(lang2, "default_name")))
            out = self._ok(lang2, "created_empty", name=col["name"], _cid=col["id"])
            a, b, c, d = refresh_mgr(col["id"], browser_lang)
            return a, b, c, d, out["message"], json.dumps(out, ensure_ascii=False)

        def on_rename(cid, name, browser_lang=""):
            lang2 = self._lang(browser_lang)
            name = (name or "").strip()
            if not cid:
                out = self._err(lang2, "no_collection")
                a, b, c, d = refresh_mgr(cid, browser_lang)
                return a, b, c, d, out["error"], json.dumps(out, ensure_ascii=False)
            if not name:
                out = self._err(lang2, "need_name")
                a, b, c, d = refresh_mgr(cid, browser_lang)
                return a, b, c, d, out["error"], json.dumps(out, ensure_ascii=False)
            try:
                col = storage.rename_collection(cid, name, fallback=tr(lang2, "default_name"))
                out = self._ok(lang2, "renamed_col", name=col["name"], _cid=col["id"])
            except storage.StorageError:
                out = self._err(lang2, "not_found")
                col = None
            a, b, c, d = refresh_mgr((col or {}).get("id") or cid, browser_lang)
            return a, b, c, d, out.get("message") or out.get("error"), json.dumps(out, ensure_ascii=False)

        def on_dup(cid, browser_lang=""):
            lang2 = self._lang(browser_lang)
            if not cid:
                out = self._err(lang2, "no_collection")
                a, b, c, d = refresh_mgr("", browser_lang)
                return a, b, c, d, out["error"], json.dumps(out, ensure_ascii=False)
            try:
                col = storage.duplicate_collection(cid, copy_suffix=tr(lang2, "copy_suffix"))
                out = self._ok(lang2, "duplicated_col", name=col["name"], _cid=col["id"])
            except storage.StorageError:
                out = self._err(lang2, "not_found")
                col = None
            a, b, c, d = refresh_mgr((col or {}).get("id"), browser_lang)
            return a, b, c, d, out.get("message") or out.get("error"), json.dumps(out, ensure_ascii=False)

        def on_delete(cid, armed_raw, browser_lang=""):
            """Two-step delete: first click arms the button for 5 s; second confirms. Soft-delete + undo toast."""
            lang2 = self._lang(browser_lang)
            try:
                armed = json.loads(armed_raw) if isinstance(armed_raw, str) and armed_raw.strip().startswith("{") else (armed_raw if isinstance(armed_raw, dict) else {})
            except Exception:
                armed = {}
            if not isinstance(armed, dict):
                armed = {"cid": None, "until": 0}
            now = time.time()
            storage.purge_trash()
            if not cid:
                out = self._err(lang2, "no_collection")
                a, b, c, d = refresh_mgr("", browser_lang)
                return (a, b, c, d, out["error"], json.dumps(out, ensure_ascii=False),
                        gr.update(value=tr(lang2, "mgr_delete"), variant="secondary"), json.dumps({"cid": None, "until": 0}))
            if armed.get("cid") == cid and now < float(armed.get("until") or 0):
                try:
                    col = storage.soft_delete(cid)
                    token = uuid.uuid4().hex
                    self._delete_undo[token] = {"id": col["id"], "name": col["name"], "time": now}
                    out = {
                        **self._ok(lang2, "deleted_undo_toast", name=col["name"], _cid=col["id"]),
                        "undo_token": token,
                        "undo_label": tr(lang2, "undo"),
                    }
                except storage.StorageError:
                    out = self._err(lang2, "not_found")
                a, b, c, d = refresh_mgr("", browser_lang)
                return (a, b, c, d, out.get("message") or out.get("error"), json.dumps(out, ensure_ascii=False),
                        gr.update(value=tr(lang2, "mgr_delete"), variant="secondary"), json.dumps({"cid": None, "until": 0}))
            # Arm
            out = {"ok": True, "message": tr(lang2, "delete_armed"), "toast": tr(lang2, "delete_armed"), "kind": "info",
                   "armed": True}
            a, b, c, d = refresh_mgr(cid, browser_lang)
            return (a, b, c, d, out["message"], json.dumps(out, ensure_ascii=False),
                    gr.update(value=tr(lang2, "mgr_confirm_delete_btn"), variant="stop"), json.dumps({"cid": cid, "until": now + 5}))

        def on_disarm(armed_raw, browser_lang=""):
            """Called by JS ~5 s after arming: put the Delete button back to normal if the window expired."""
            lang2 = self._lang(browser_lang)
            try:
                armed = json.loads(armed_raw or "{}")
            except (TypeError, ValueError):
                armed = {}
            if isinstance(armed, dict) and armed.get("cid") and time.time() < float(armed.get("until") or 0):
                return gr.skip(), gr.skip()
            return gr.update(value=tr(lang2, "mgr_delete"), variant="secondary"), json.dumps({"cid": None, "until": 0})

        def on_undo_delete(raw, browser_lang=""):
            lang2 = self._lang(browser_lang)
            try:
                req = json.loads(raw or "{}")
            except Exception:
                req = {}
            token = req.get("undo_token") if isinstance(req, dict) else None
            info = self._delete_undo.pop(token, None) if token else None
            if not info or info.get("kind") == "video" or time.time() - info["time"] > 5 * 60:
                out = self._err(lang2, "undo_expired")
                a, b, c, d = refresh_mgr("", browser_lang)
                return a, b, c, d, out["error"], json.dumps(out, ensure_ascii=False)
            try:
                col = storage.restore_soft_deleted(info["id"])
                merged = imagestore.merge_after_restore(col["id"])
                if merged:
                    col = storage.get_collection(col["id"])
                    out = self._ok(lang2, "restored_merged", name=col["name"], added=merged["added"], merged=merged["merged_name"],
                                   _cid=col["id"])
                else:
                    out = self._ok(lang2, "restored_col", name=col["name"], _cid=col["id"])
                a, b, c, d = refresh_mgr(col["id"], browser_lang)
            except storage.StorageError:
                out = self._err(lang2, "undo_expired")
                a, b, c, d = refresh_mgr("", browser_lang)
            return a, b, c, d, out.get("message") or out.get("error"), json.dumps(out, ensure_ascii=False)

        def on_add(cid, files, browser_lang=""):
            lang2 = self._lang(browser_lang)
            if not cid:
                out = self._err(lang2, "no_collection")
                a, b, c, d = refresh_mgr(cid, browser_lang)
                return a, b, c, d, out["error"], json.dumps(out, ensure_ascii=False)
            paths = []
            if files is None:
                files = []
            if not isinstance(files, list):
                files = [files]
            for f in files:
                p = f if isinstance(f, str) else getattr(f, "name", None) or getattr(f, "path", None)
                if p and os.path.isfile(p):
                    paths.append((p, os.path.basename(p)))
            try:
                col = storage.add_images(cid, paths)
                out = self._ok(lang2, "added_imgs", n=col.get("_added", 0), total=len(col["images"]), _cid=cid)
            except storage.StorageError:
                out = self._err(lang2, "not_found")
            a, b, c, d = refresh_mgr(cid, browser_lang)
            return a, b, c, d, out.get("message") or out.get("error"), json.dumps(out, ensure_ascii=False)

        def _sel_index(evt_or_num):
            if isinstance(evt_or_num, (int, float)):
                return int(evt_or_num)
            # Gallery select event
            try:
                return int(evt_or_num.index) if evt_or_num is not None else -1
            except Exception:
                return -1

        def on_gallery_select(evt: gr.SelectData):
            return _sel_index(evt)

        def on_remove(cid, sel, browser_lang=""):
            lang2 = self._lang(browser_lang)
            sel = _sel_index(sel)
            if not cid:
                out = self._err(lang2, "no_collection")
            else:
                try:
                    col = storage.remove_image(cid, sel)
                    out = self._ok(lang2, "removed_img", total=len(col["images"]), _cid=cid)
                except storage.StorageError as e:
                    out = {"ok": False, "error": storage_error_text(lang2, e)}
            a, b, c, d = refresh_mgr(cid, browser_lang)
            return a, b, c, d, out.get("message") or out.get("error"), json.dumps(out, ensure_ascii=False)

        def on_move(cid, sel, delta, browser_lang=""):
            lang2 = self._lang(browser_lang)
            sel = _sel_index(sel)
            if not cid:
                out = self._err(lang2, "no_collection")
            else:
                try:
                    col = storage.move_image(cid, sel, delta)
                    out = {"ok": True, "message": "", "changed": {"reason": "images", "id": cid}}
                    # keep selection on moved item
                    new_sel = sel + delta if 0 <= sel + delta < len(col["images"]) else sel
                except storage.StorageError as e:
                    out = {"ok": False, "error": storage_error_text(lang2, e)}
                    new_sel = sel
            a, b, c, d = refresh_mgr(cid, browser_lang)
            return a, b, c, gr.update(value=new_sel if out.get("ok") else -1), out.get("message") or out.get("error") or "", json.dumps(out, ensure_ascii=False)

        def on_cover(cid, sel, browser_lang=""):
            lang2 = self._lang(browser_lang)
            sel = _sel_index(sel)
            if not cid:
                out = self._err(lang2, "no_collection")
            else:
                try:
                    storage.set_cover(cid, sel)
                    out = self._ok(lang2, "cover_set", _cid=cid)
                except storage.StorageError as e:
                    out = {"ok": False, "error": storage_error_text(lang2, e)}
            a, b, c, d = refresh_mgr(cid, browser_lang)
            return a, b, c, d, out.get("message") or out.get("error"), json.dumps(out, ensure_ascii=False)

        def on_export(cid, browser_lang=""):
            lang2 = self._lang(browser_lang)
            if not cid:
                out = self._err(lang2, "no_collection")
                return None, out["error"], json.dumps(out, ensure_ascii=False)
            try:
                col = storage.get_collection(cid)
                out_dir = os.path.join(_upload_folder(), "reference_library", "export")
                os.makedirs(out_dir, exist_ok=True)
                safe = storage._safe_name(col["name"], tr(lang2, "default_name")).replace(" ", "_")
                dest = os.path.join(out_dir, f"{safe}-{cid[:8]}.zip")
                storage.export_collection_zip(cid, dest)
                out = self._ok(lang2, "exported", path=os.path.basename(dest))
                return gr.update(value=dest, visible=True), out["message"], json.dumps(out, ensure_ascii=False)
            except storage.StorageError:
                out = self._err(lang2, "not_found")
                return None, out["error"], json.dumps(out, ensure_ascii=False)

        def on_import(file_obj, browser_lang=""):
            lang2 = self._lang(browser_lang)
            path = file_obj if isinstance(file_obj, str) else getattr(file_obj, "name", None)
            if not path:
                out = self._err(lang2, "bad_request")
                a, b, c, d = refresh_mgr("", browser_lang)
                return a, b, c, d, out["error"], json.dumps(out, ensure_ascii=False)
            try:
                col = storage.import_collection_zip(path, default_name=tr(lang2, "imported_name"))
                out = self._ok(lang2, "imported", name=col["name"], n=len(col["images"]), _cid=col["id"])
            except Exception as e:
                out = {"ok": False, "error": storage_error_text(lang2, e)}
                col = None
            a, b, c, d = refresh_mgr((col or {}).get("id"), browser_lang)
            return a, b, c, d, out.get("message") or out.get("error"), json.dumps(out, ensure_ascii=False)

        def on_mgr_apply(cid, browser_lang=""):
            """Apply from manager: write request for the generate bridge (JS clicks it)."""
            lang2 = self._lang(browser_lang)
            if not cid:
                out = self._err(lang2, "no_collection")
                return json.dumps(out, ensure_ascii=False), out["error"]
            if "generate:image_refs" not in self.targets:
                out = self._err(lang2, "gallery_missing")
                return json.dumps(out, ensure_ascii=False), out["error"]
            req = {"id": uuid.uuid4().hex, "action": "apply", "collection_id": cid, "target": "generate:image_refs", "lang": lang2}
            return json.dumps(req, ensure_ascii=False), tr(lang2, "loaded", name="…", n="…")

        # wire manager
        bl_hidden = gr.Textbox(value="", visible=False)
        mgr_outs = [mgr_dd, mgr_name, mgr_gallery, mgr_selected]
        toast_js = "(t) => { if (window.referenceLibrary) window.referenceLibrary.handleToast(t); }"

        mgr_dd.change(fn=on_pick, inputs=[mgr_dd, bl_hidden], outputs=mgr_outs, show_progress="hidden",
                      js="(c,l) => [c, navigator.language || '']")

        # ---- Prompt Library links (Prompt Library owns the data; we only read/write through its API) ----
        def links_update(cid):
            if not promptlink.available():
                return gr.update(choices=[], value=[]), gr.update(visible=False)
            choices = [(p["title"], p["id"]) for p in promptlink.list_prompts()]
            linked = [p["id"] for p in promptlink.prompts_for_collection(cid)] if cid else []
            valid = {c[1] for c in choices}
            return (gr.update(choices=choices, value=[i for i in linked if i in valid],
                              interactive=bool(cid) and promptlink.can_write()), gr.update(visible=True))

        def on_save_links(cid, ids, browser_lang=""):
            lang2 = self._lang(browser_lang)
            if not cid:
                out = self._err(lang2, "no_collection")
            elif not promptlink.can_write():
                out = self._err(lang2, "prompts_unavailable")
            else:
                ok, error = promptlink.set_collection_prompts(cid, list(ids or []))
                if ok:
                    try:
                        name = storage.get_collection(cid)["name"]
                    except storage.StorageError:
                        name = cid
                    out = {**self._ok(lang2, "prompts_saved", name=name, n=len(ids or [])), "prompts_changed": True}
                else:
                    out = self._err(lang2, "prompts_failed", error=error)
            dd_u, _panel = links_update(cid)
            return dd_u, out.get("message") or out.get("error"), json.dumps(out, ensure_ascii=False)

        def on_refresh_prompts(cid, applied_json):
            """Hidden button clicked by JS on promptlib:changed (and after saving links). `applied_json` is the page's own
            {tab: collection_id} (what THIS page applied), so chips never come from another browser session."""
            dd_u, panel_u = links_update(cid)
            on = promptlink.available()
            mode = load_settings().get("on_apply_prompts", "offer")
            try:
                page_applied = json.loads(applied_json or "{}")
            except (TypeError, ValueError):
                page_applied = {}
            bars = {}
            if on and isinstance(page_applied, dict):
                for t in TAB_IDS:
                    acid = page_applied.get(t)
                    if isinstance(acid, str) and acid and _public_api.get_collection(acid) is not None:
                        bars[t] = {"id": acid, "prompt_mode": mode,
                                   "prompts": [] if mode == "off" else promptlink.prompts_for_collection(acid)}
            return dd_u, panel_u, gr.update(visible=on), json.dumps({"available": on, "bars": bars}, ensure_ascii=False)

        mgr_dd.change(fn=lambda c: links_update(c), inputs=[mgr_dd], outputs=[mgr_prompts, prompts_panel],
                      show_progress="hidden")
        ui["mgr_prompts_save"].click(fn=on_save_links, inputs=[mgr_dd, mgr_prompts, bl_hidden],
                                     outputs=[mgr_prompts, mgr_status, mgr_toast], show_progress="hidden",
                                     js="(c,p,l) => [c, p, navigator.language || '']").then(
            fn=None, inputs=[mgr_toast], outputs=None, js=toast_js)
        prompts_refresh_btn.click(fn=on_refresh_prompts, inputs=[mgr_dd, prompts_refresh_out],
                                  outputs=[mgr_prompts, prompts_panel, prompts_settings_group, prompts_refresh_out],
                                  show_progress="hidden", trigger_mode="always_last",
                                  js="(c, r) => [c, JSON.stringify(window.referenceLibrary ? window.referenceLibrary.appliedIds() : {})]").then(
            fn=None, inputs=[prompts_refresh_out], outputs=None,
            js="(r) => { if (window.referenceLibrary) window.referenceLibrary.promptsRefreshed(r); }")
        mgr_refresh.click(fn=lambda c, l: refresh_mgr(c, l), inputs=[mgr_dd, bl_hidden], outputs=mgr_outs,
                          show_progress="hidden", js="(c,l) => [c, navigator.language || '']")
        mgr_new.click(fn=on_new, inputs=[mgr_name, bl_hidden], outputs=mgr_outs + [mgr_status, mgr_toast],
                      show_progress="hidden", js="(n,l) => [n, navigator.language || '']").then(
            fn=None, inputs=[mgr_toast], outputs=None, js=toast_js)
        mgr_rename.click(fn=on_rename, inputs=[mgr_dd, mgr_name, bl_hidden], outputs=mgr_outs + [mgr_status, mgr_toast],
                         show_progress="hidden", js="(c,n,l) => [c, n, navigator.language || '']").then(
            fn=None, inputs=[mgr_toast], outputs=None, js=toast_js)
        mgr_dup.click(fn=on_dup, inputs=[mgr_dd, bl_hidden], outputs=mgr_outs + [mgr_status, mgr_toast],
                      show_progress="hidden", js="(c,l) => [c, navigator.language || '']").then(
            fn=None, inputs=[mgr_toast], outputs=None, js=toast_js)
        mgr_delete.click(fn=on_delete, inputs=[mgr_dd, delete_armed, bl_hidden],
                         outputs=mgr_outs + [mgr_status, mgr_toast, mgr_delete, delete_armed], show_progress="hidden",
                         js="""(c,a,l) => {
                           const root = document.getElementById('reflib_delete_armed');
                           const ta = root && (root.tagName === 'TEXTAREA' ? root : root.querySelector('textarea'));
                           return [c, ta ? ta.value : (a || '{}'), navigator.language || ''];
                         }""").then(
            fn=None, inputs=[mgr_toast], outputs=None,
            js="""(t) => { if (!window.referenceLibrary) return; window.referenceLibrary.handleToast(t);
                   let d = {}; try { d = JSON.parse(t || '{}'); } catch (e) {}
                   if (d && d.armed) { clearTimeout(window.__reflibDisarm);
                     window.__reflibDisarm = setTimeout(() => { const b = document.getElementById('reflib_delete_disarm'); if (b) b.click(); }, 5300); } }""")
        disarm_btn = gr.Button("disarm", elem_id="reflib_delete_disarm", elem_classes=["reflib-hidden"])
        disarm_btn.click(fn=on_disarm, inputs=[delete_armed, bl_hidden], outputs=[mgr_delete, delete_armed],
                         show_progress="hidden", queue=False,
                         js="""(a,l) => { const root = document.getElementById('reflib_delete_armed');
                           const ta = root && (root.tagName === 'TEXTAREA' ? root : root.querySelector('textarea'));
                           return [ta ? ta.value : (a || '{}'), navigator.language || '']; }""")
        # Hidden undo trigger: JS clicks after the user presses Undo on the toast
        undo_btn = gr.Button("undo", elem_id="reflib_undo_delete", visible=False)
        undo_req = gr.Textbox(value="", visible=False, elem_id="reflib_undo_req")
        undo_btn.click(fn=on_undo_delete, inputs=[undo_req, bl_hidden],
                       outputs=mgr_outs + [mgr_status, mgr_toast], show_progress="hidden",
                       js="(r,l) => [r, navigator.language || '']").then(
            fn=None, inputs=[mgr_toast], outputs=None, js=toast_js)
        mgr_add.upload(fn=on_add, inputs=[mgr_dd, mgr_add, bl_hidden], outputs=mgr_outs + [mgr_status, mgr_toast],
                       show_progress="hidden", js="(c,f,l) => [c, f, navigator.language || '']").then(
            fn=None, inputs=[mgr_toast], outputs=None, js=toast_js)
        mgr_gallery.select(fn=on_gallery_select, inputs=None, outputs=[mgr_selected], show_progress="hidden")
        mgr_remove.click(fn=on_remove, inputs=[mgr_dd, mgr_selected, bl_hidden], outputs=mgr_outs + [mgr_status, mgr_toast],
                         show_progress="hidden", js="(c,s,l) => [c, s, navigator.language || '']").then(
            fn=None, inputs=[mgr_toast], outputs=None, js=toast_js)
        mgr_left.click(fn=lambda c, s, l: on_move(c, s, -1, l), inputs=[mgr_dd, mgr_selected, bl_hidden],
                       outputs=mgr_outs + [mgr_status, mgr_toast], show_progress="hidden",
                       js="(c,s,l) => [c, s, navigator.language || '']").then(
            fn=None, inputs=[mgr_toast], outputs=None, js=toast_js)
        mgr_right.click(fn=lambda c, s, l: on_move(c, s, +1, l), inputs=[mgr_dd, mgr_selected, bl_hidden],
                        outputs=mgr_outs + [mgr_status, mgr_toast], show_progress="hidden",
                        js="(c,s,l) => [c, s, navigator.language || '']").then(
            fn=None, inputs=[mgr_toast], outputs=None, js=toast_js)
        mgr_cover.click(fn=on_cover, inputs=[mgr_dd, mgr_selected, bl_hidden], outputs=mgr_outs + [mgr_status, mgr_toast],
                        show_progress="hidden", js="(c,s,l) => [c, s, navigator.language || '']").then(
            fn=None, inputs=[mgr_toast], outputs=None, js=toast_js)
        mgr_export.click(fn=on_export, inputs=[mgr_dd, bl_hidden], outputs=[mgr_export_file, mgr_status, mgr_toast],
                         show_progress="hidden", js="(c,l) => [c, navigator.language || '']").then(
            fn=None, inputs=[mgr_toast], outputs=None, js=toast_js)
        mgr_import.upload(fn=on_import, inputs=[mgr_import, bl_hidden], outputs=mgr_outs + [mgr_status, mgr_toast],
                          show_progress="hidden", js="(f,l) => [f, navigator.language || '']").then(
            fn=None, inputs=[mgr_toast], outputs=None, js=toast_js)
        mgr_apply.click(fn=on_mgr_apply, inputs=[mgr_dd, bl_hidden], outputs=[bridge_req, mgr_status],
                        show_progress="hidden", js="(c,l) => [c, navigator.language || '']").then(
            fn=None, inputs=[bridge_req], outputs=None,
            js="""(r) => {
              if (!window.referenceLibrary) return;
              try {
                const req = JSON.parse(r || '{}');
                if (!req.action) { window.referenceLibrary.handleToast(r); return; }
                window.referenceLibrary.sendBridge(req);
              } catch (e) { console.warn('[Reference Library]', e); }
            }""")
        # ---- video library manager handlers ----
        vmgr_outs = [vmgr_gallery, vmgr_sel, ui["vmgr_name"], vmgr_preview, vmgr_meta, ui["vmgr_title"]]

        def refresh_vmgr(vid="", browser_lang="", preview=True):
            lang2 = self._lang(browser_lang)
            videos = videostore.list_videos()
            ids = [v["id"] for v in videos]
            vid = vid if vid in ids else ""
            v = videos[ids.index(vid)] if vid else None
            prev = gr.skip()
            if preview:
                try:
                    prev = videostore.video_file(v) if v else None
                except storage.StorageError:
                    prev = None
            return (gr.update(value=_vmgr_gallery_value(videos), selected_index=ids.index(vid) if vid else None),
                    vid,
                    gr.update(value=v["name"] if v else "", label=tr(lang2, "vmgr_name"), placeholder=tr(lang2, "vmgr_name_ph")),
                    prev,
                    _vmeta_html(lang2, v, empty=not videos),
                    _panel_title_html(tr(lang2, "vmgr_title", n=len(videos)), tr(lang2, "vmgr_title_tip")))

        def vresult(out, vid, browser_lang, preview=True):
            return (*refresh_vmgr(vid, browser_lang, preview), out.get("message") or out.get("error") or "",
                    json.dumps(out, ensure_ascii=False))

        def on_vselect(browser_lang, evt: gr.SelectData):
            videos = videostore.list_videos()
            try:
                idx = int(evt.index if not isinstance(evt.index, (list, tuple)) else evt.index[0])
            except Exception:
                idx = -1
            vid = videos[idx]["id"] if 0 <= idx < len(videos) else ""
            return refresh_vmgr(vid, browser_lang)

        def on_vrename(vid, name, browser_lang=""):
            lang2 = self._lang(browser_lang)
            name = (name or "").strip()
            if not vid:
                return vresult(self._err(lang2, "no_video"), "", browser_lang, False)
            if not name:
                return vresult(self._err(lang2, "need_vname"), vid, browser_lang, False)
            try:
                v = videostore.rename_video(vid, name, fallback=tr(lang2, "video_default_name"))
                out = self._ok(lang2, "vrenamed", name=v["name"], _cid=v["id"])
            except storage.StorageError as e:
                out = {"ok": False, "error": storage_error_text(lang2, e)}
            return vresult(out, vid, browser_lang, False)

        def on_vmove(vid, delta, browser_lang=""):
            lang2 = self._lang(browser_lang)
            if not vid:
                return vresult(self._err(lang2, "no_video"), "", browser_lang, False)
            try:
                videostore.move_video(vid, delta)
                out = {"ok": True, "message": "", "changed": {"reason": "video-reordered", "id": vid, "kind": "video"}}
            except storage.StorageError as e:
                out = {"ok": False, "error": storage_error_text(lang2, e)}
            return vresult(out, vid, browser_lang, False)

        def on_vdelete(vid, armed_raw, browser_lang=""):
            """Same two-step delete as collections: arm for 5 s, then soft-delete with a 5-minute Undo."""
            lang2 = self._lang(browser_lang)
            try:
                armed = json.loads(armed_raw) if isinstance(armed_raw, str) and armed_raw.strip().startswith("{") else {}
            except Exception:
                armed = {}
            now = time.time()
            videostore.purge_trash()
            reset = (gr.update(value=tr(lang2, "vmgr_delete"), variant="secondary"), json.dumps({"vid": None, "until": 0}))
            if not vid:
                return (*vresult(self._err(lang2, "no_video"), "", browser_lang), *reset)
            if isinstance(armed, dict) and armed.get("vid") == vid and now < float(armed.get("until") or 0):
                try:
                    v = videostore.soft_delete(vid)
                    token = uuid.uuid4().hex
                    self._delete_undo[token] = {"id": v["id"], "name": v["name"], "time": now, "kind": "video"}
                    for t in list(self._last_video):
                        if self._last_video[t] == vid:
                            self._last_video.pop(t, None)
                    out = {**self._ok(lang2, "vdeleted_undo", name=v["name"], _cid=v["id"]), "undo_token": token,
                           "undo_label": tr(lang2, "undo"), "undo_button": "reflib_undo_vdelete"}
                except storage.StorageError as e:
                    out = {"ok": False, "error": storage_error_text(lang2, e)}
                return (*vresult(out, "", browser_lang), *reset)
            out = {"ok": True, "message": tr(lang2, "delete_armed"), "toast": tr(lang2, "delete_armed"), "kind": "info",
                   "armed": True, "disarm_button": "reflib_vdelete_disarm"}
            return (*vresult(out, vid, browser_lang, False),
                    gr.update(value=tr(lang2, "mgr_confirm_delete_btn"), variant="stop"), json.dumps({"vid": vid, "until": now + 5}))

        def on_vdisarm(armed_raw, browser_lang=""):
            lang2 = self._lang(browser_lang)
            try:
                armed = json.loads(armed_raw or "{}")
            except (TypeError, ValueError):
                armed = {}
            if isinstance(armed, dict) and armed.get("vid") and time.time() < float(armed.get("until") or 0):
                return gr.skip(), gr.skip()
            return gr.update(value=tr(lang2, "vmgr_delete"), variant="secondary"), json.dumps({"vid": None, "until": 0})

        def on_vundo(raw, browser_lang=""):
            lang2 = self._lang(browser_lang)
            try:
                req = json.loads(raw or "{}")
            except Exception:
                req = {}
            token = req.get("undo_token") if isinstance(req, dict) else None
            info = self._delete_undo.get(token) if token else None
            if not info or info.get("kind") != "video" or time.time() - info["time"] > 5 * 60:
                self._delete_undo.pop(token, None)
                return vresult(self._err(lang2, "undo_expired"), "", browser_lang)
            self._delete_undo.pop(token, None)
            try:
                v = videostore.restore_soft_deleted(info["id"])
                merged = v.pop("_merged_from", None)
                if merged:
                    # An equivalent video was saved meanwhile: no second copy; select the one that is there.
                    out = {"ok": True, "kind": "info", "message": tr(lang2, "vrestore_dup", name=merged["name"], existing=v["name"]),
                           "toast": tr(lang2, "vrestore_dup", name=merged["name"], existing=v["name"])}
                    return vresult(out, v["id"], browser_lang)
                return vresult(self._ok(lang2, "vrestored", name=v["name"], _cid=v["id"]), v["id"], browser_lang)
            except storage.StorageError:
                return vresult(self._err(lang2, "undo_expired"), "", browser_lang)

        def on_vimport(files, browser_lang=""):
            lang2 = self._lang(browser_lang)
            files = files if isinstance(files, list) else ([files] if files else [])
            added, skipped, errors = [], 0, []
            for f in files:
                path = f if isinstance(f, str) else getattr(f, "name", None) or getattr(f, "path", None)
                if not path or not os.path.isfile(path):
                    continue
                try:
                    if path.lower().endswith(".zip"):
                        got, skip = videostore.import_zip(path, fallback=tr(lang2, "video_default_name"))
                        added.extend(got)
                        skipped += skip
                    else:
                        entry, created = videostore.add_video(path, source="import", fallback=tr(lang2, "video_default_name"))
                        if created:
                            added.append(entry)
                        else:
                            skipped += 1
                except Exception as e:
                    errors.append(storage_error_text(lang2, e))
            if not added and not skipped and errors:
                out = {"ok": False, "error": errors[0]}
            else:
                key = "vimported_skip" if skipped else "vimported"
                out = self._ok(lang2, key, n=len(added), skipped=skipped, _cid=added[0]["id"] if added else None)
            return vresult(out, added[0]["id"] if added else "", browser_lang)

        def export_dir():
            path = os.path.join(_upload_folder(), "reference_library", "export", uuid.uuid4().hex[:8])
            os.makedirs(path, exist_ok=True)
            return path

        def on_vdownload(vid, browser_lang=""):
            lang2 = self._lang(browser_lang)
            if not vid:
                out = self._err(lang2, "no_video")
                return gr.skip(), out["error"], json.dumps(out, ensure_ascii=False)
            try:
                dest = videostore.export_file(vid, export_dir(), fallback=tr(lang2, "video_default_name"))
                out = self._ok(lang2, "vdownload", path=os.path.basename(dest))
                return gr.update(value=dest, visible=True), out["message"], json.dumps(out, ensure_ascii=False)
            except Exception as e:
                out = {"ok": False, "error": storage_error_text(lang2, e)}
                return gr.skip(), out["error"], json.dumps(out, ensure_ascii=False)

        def on_vexport(browser_lang=""):
            lang2 = self._lang(browser_lang)
            try:
                dest, n = videostore.export_all_zip(os.path.join(export_dir(), time.strftime("reference-library-videos-%Y%m%d-%H%M.zip")))
                out = self._ok(lang2, "vexported", n=n, path=os.path.basename(dest))
                return gr.update(value=dest, visible=True), out["message"], json.dumps(out, ensure_ascii=False)
            except Exception as e:
                out = {"ok": False, "error": storage_error_text(lang2, e)}
                return gr.skip(), out["error"], json.dumps(out, ensure_ascii=False)

        def on_vmgr_load(vid, browser_lang=""):
            lang2 = self._lang(browser_lang)
            if not vid:
                out = self._err(lang2, "no_video")
                return json.dumps(out, ensure_ascii=False), out["error"]
            if "generate" not in self.vtargets:
                out = self._err(lang2, "control_missing")
                return json.dumps(out, ensure_ascii=False), out["error"]
            req = {"id": uuid.uuid4().hex, "action": "video_load", "video_id": vid, "target": "generate:video_guide", "lang": lang2}
            return json.dumps(req, ensure_ascii=False), ""

        def on_vreload(vid, browser_lang=""):
            lang2 = self._lang(browser_lang)
            bars = []
            for tab in TAB_IDS:
                if tab in self._vbars:
                    sel = self._last_video.get(tab)
                    bars += [self._vdd_update(tab, lang2, sel), _video_info_html(lang2, sel)]
            return (*refresh_vmgr(vid, browser_lang, preview=False), *bars)

        vtoast_js = "(t) => { if (window.referenceLibrary) window.referenceLibrary.handleToast(t); }"
        vlang = "navigator.language || ''"
        vouts = vmgr_outs + [vmgr_status, vmgr_toast]
        vmgr_gallery.select(fn=on_vselect, inputs=[bl_hidden], outputs=vmgr_outs, show_progress="hidden",
                            js=f"(l) => [{vlang}]")
        ui["vmgr_rename"].click(fn=on_vrename, inputs=[vmgr_sel, ui["vmgr_name"], bl_hidden], outputs=vouts,
                                show_progress="hidden", js=f"(c, n, l) => [c, n, {vlang}]").then(
            fn=None, inputs=[vmgr_toast], outputs=None, js=vtoast_js)
        ui["vmgr_name"].submit(fn=on_vrename, inputs=[vmgr_sel, ui["vmgr_name"], bl_hidden], outputs=vouts,
                               show_progress="hidden", js=f"(c, n, l) => [c, n, {vlang}]").then(
            fn=None, inputs=[vmgr_toast], outputs=None, js=vtoast_js)
        ui["vmgr_left"].click(fn=lambda c, l: on_vmove(c, -1, l), inputs=[vmgr_sel, bl_hidden], outputs=vouts,
                              show_progress="hidden", js=f"(c, l) => [c, {vlang}]").then(
            fn=None, inputs=[vmgr_toast], outputs=None, js=vtoast_js)
        ui["vmgr_right"].click(fn=lambda c, l: on_vmove(c, +1, l), inputs=[vmgr_sel, bl_hidden], outputs=vouts,
                               show_progress="hidden", js=f"(c, l) => [c, {vlang}]").then(
            fn=None, inputs=[vmgr_toast], outputs=None, js=vtoast_js)
        ui["vmgr_delete"].click(fn=on_vdelete, inputs=[vmgr_sel, vdelete_armed, bl_hidden],
                                outputs=vouts + [ui["vmgr_delete"], vdelete_armed], show_progress="hidden",
                                js=f"""(c, a, l) => {{ const root = document.getElementById('reflib_vdelete_armed');
                                  const ta = root && (root.tagName === 'TEXTAREA' ? root : root.querySelector('textarea'));
                                  return [c, ta ? ta.value : (a || '{{}}'), {vlang}]; }}""").then(
            fn=None, inputs=[vmgr_toast], outputs=None, js=vtoast_js)
        vdisarm_btn = gr.Button("vdisarm", elem_id="reflib_vdelete_disarm", elem_classes=["reflib-hidden"])
        vdisarm_btn.click(fn=on_vdisarm, inputs=[vdelete_armed, bl_hidden], outputs=[ui["vmgr_delete"], vdelete_armed],
                          show_progress="hidden", queue=False,
                          js=f"""(a, l) => {{ const root = document.getElementById('reflib_vdelete_armed');
                            const ta = root && (root.tagName === 'TEXTAREA' ? root : root.querySelector('textarea'));
                            return [ta ? ta.value : (a || '{{}}'), {vlang}]; }}""")
        vundo_btn = gr.Button("vundo", elem_id="reflib_undo_vdelete", visible=False)
        vundo_btn.click(fn=on_vundo, inputs=[undo_req, bl_hidden], outputs=vouts, show_progress="hidden",
                        js=f"(r, l) => [r, {vlang}]").then(fn=None, inputs=[vmgr_toast], outputs=None, js=vtoast_js)
        ui["vmgr_import"].upload(fn=on_vimport, inputs=[ui["vmgr_import"], bl_hidden], outputs=vouts, show_progress="full",
                                 js=f"(f, l) => [f, {vlang}]").then(fn=None, inputs=[vmgr_toast], outputs=None, js=vtoast_js)
        ui["vmgr_download"].click(fn=on_vdownload, inputs=[vmgr_sel, bl_hidden], outputs=[vmgr_file, vmgr_status, vmgr_toast],
                                  show_progress="hidden", js=f"(c, l) => [c, {vlang}]").then(
            fn=None, inputs=[vmgr_toast], outputs=None, js=vtoast_js)
        ui["vmgr_export"].click(fn=on_vexport, inputs=[bl_hidden], outputs=[vmgr_file, vmgr_status, vmgr_toast],
                                show_progress="hidden", js=f"(l) => [{vlang}]").then(
            fn=None, inputs=[vmgr_toast], outputs=None, js=vtoast_js)
        ui["vmgr_load"].click(fn=on_vmgr_load, inputs=[vmgr_sel, bl_hidden], outputs=[bridge_req, vmgr_status],
                              show_progress="hidden", js=f"(c, l) => [c, {vlang}]").then(
            fn=None, inputs=[bridge_req], outputs=None,
            js="""(r) => {
              if (!window.referenceLibrary) return;
              try {
                const req = JSON.parse(r || '{}');
                if (!req.action) { window.referenceLibrary.handleToast(r); return; }
                window.referenceLibrary.loadVideoRequest(req);
              } catch (e) { console.warn('[Reference Library]', e); }
            }""")
        vbar_reload_outs = []
        for tab in TAB_IDS:
            if tab in self._vbars:
                vbar_reload_outs += [self._vbars[tab]["dd"], self._vbars[tab]["info"]]
        vreload_btn.click(fn=on_vreload, inputs=[vmgr_sel, bl_hidden], outputs=vmgr_outs + vbar_reload_outs,
                          show_progress="hidden", trigger_mode="always_last", js=f"(c, l) => [c, {vlang}]")

        # ---- inline rename (pencil) + full list refresh ----
        img_tabs = [tab for tab in TAB_IDS if tab in self._bars]
        vid_tabs = [tab for tab in TAB_IDS if tab in self._vbars]
        list_inputs = [mgr_dd, vmgr_sel] + [self._bars[t]["dd"] for t in img_tabs] + [self._vbars[t]["dd"] for t in vid_tabs]
        list_outputs = (mgr_outs + vmgr_outs + [self._bars[t]["dd"] for t in img_tabs]
                        + [x for t in vid_tabs for x in (self._vbars[t]["dd"], self._vbars[t]["info"])])

        def lists_refresh(lang2, browser_lang, mgr_cid, vsel, bar_vals, vbar_vals):
            out = list(refresh_mgr(mgr_cid or "", browser_lang)) + list(refresh_vmgr(vsel or "", browser_lang, preview=False))
            for t, cid in zip(img_tabs, bar_vals):
                ch, val = _dropdown_choices(lang2, cid or None)
                out.append(gr.update(choices=ch, value=val))
            for t, vid in zip(vid_tabs, vbar_vals):
                vid = vid or None
                out += [self._vdd_update(t, lang2, vid), _video_info_html(lang2, vid)]
            return out

        def split(rest):
            bar_vals = list(rest[:len(img_tabs)])
            vbar_vals = list(rest[len(img_tabs):len(img_tabs) + len(vid_tabs)])
            return bar_vals, vbar_vals, (rest[-1] if rest else "")

        def on_inline_rename(raw, mgr_cid, vsel, *rest):
            bar_vals, vbar_vals, browser_lang = split(rest)
            lang2 = self._lang(browser_lang)
            try:
                req = json.loads(raw or "{}")
                req = req if isinstance(req, dict) else {}
            except Exception:
                req = {}
            scope, tab = req.get("scope"), req.get("tab") or "generate"
            name = re.sub(r"\s+", " ", str(req.get("name") or "")).strip()
            out = self._err(lang2, "bad_request")
            try:
                if scope in ("bar", "mgr"):
                    cid = mgr_cid if scope == "mgr" else (bar_vals[img_tabs.index(tab)] if tab in img_tabs else "")
                    if not cid:
                        out = self._err(lang2, "no_collection")
                    elif not name:
                        out = self._err(lang2, "need_name")
                    elif name == storage.get_collection(cid)["name"]:
                        out = {"ok": True, "quiet": True}
                    else:
                        col = storage.rename_collection(cid, name, fallback=tr(lang2, "default_name"))
                        out = self._ok(lang2, "renamed_col", name=col["name"], _cid=col["id"])
                elif scope in ("vbar", "vmgr"):
                    vid = (req.get("vid") or vsel) if scope == "vmgr" else (vbar_vals[vid_tabs.index(tab)] if tab in vid_tabs else "")
                    if not vid:
                        out = self._err(lang2, "no_video")
                    elif not name:
                        out = self._err(lang2, "need_vname")
                    elif name == videostore.get_video(vid)["name"]:
                        out = {"ok": True, "quiet": True}
                    else:
                        v = videostore.rename_video(vid, name, fallback=tr(lang2, "video_default_name"))
                        out = self._ok(lang2, "vrenamed", name=v["name"], _cid=v["id"])
            except storage.StorageError as e:
                out = {"ok": False, "error": storage_error_text(lang2, e)}
            out["rid"] = req.get("rid")
            return (json.dumps(out, ensure_ascii=False),
                    *lists_refresh(lang2, browser_lang, mgr_cid, vsel, bar_vals, vbar_vals))

        def on_reload(mgr_cid, vsel, *rest):
            bar_vals, vbar_vals, browser_lang = split(rest)
            return tuple(lists_refresh(self._lang(browser_lang), browser_lang, mgr_cid, vsel, bar_vals, vbar_vals))

        ilib_btn.click(fn=self.ilib, inputs=[ilib_req], outputs=[ilib_resp], show_progress="hidden",
                       trigger_mode="multiple", queue=True).then(
            fn=None, inputs=[ilib_resp], outputs=None, show_progress="hidden",
            js="(r) => { if (window.referenceLibrary) window.referenceLibrary.bridgeResponse(r); }")
        ilib_fast_btn.click(fn=self.ilib_fast, inputs=[ilib_fast_req], outputs=[ilib_fast_resp], show_progress="hidden",
                            trigger_mode="multiple", queue=False).then(
            fn=None, inputs=[ilib_fast_resp], outputs=None, show_progress="hidden", queue=False,
            js="(r) => { if (window.referenceLibrary) window.referenceLibrary.bridgeResponse(r); }")
        ilib_upload.upload(fn=self.ilib_upload, inputs=[ilib_upload, ilib_upload_meta], outputs=[ilib_resp, ilib_upload],
                           show_progress="hidden").then(
            fn=None, inputs=[ilib_resp], outputs=None, show_progress="hidden",
            js="(r) => { if (window.referenceLibrary) window.referenceLibrary.bridgeResponse(r); }")

        n_in = len(list_inputs)
        rename_btn.click(fn=on_inline_rename, inputs=[rename_req] + list_inputs + [bl_hidden],
                         outputs=[rename_out] + list_outputs, show_progress="hidden", trigger_mode="multiple",
                         js=f"(...a) => {{ a = a.slice(0, {n_in + 2}); a[{n_in + 1}] = navigator.language || ''; return a; }}").then(
            fn=None, inputs=[rename_out], outputs=None, show_progress="hidden",
            js="(r) => { if (window.referenceLibrary) window.referenceLibrary.renameResponse(r); }")
        reload_btn.click(fn=on_reload, inputs=list_inputs + [bl_hidden], outputs=list_outputs, show_progress="hidden",
                         trigger_mode="always_last",
                         js=f"(...a) => {{ a = a.slice(0, {n_in + 1}); a[{n_in}] = navigator.language || ''; return a; }}")

    # ------------------------------------------------------------ settings IO
    def _ordered_bar_updates(self, lang):
        """Match the order of components registered in create_ui as bar_outputs (image bars, then video bars)."""
        out = []
        texts_by_tab = {}
        for tab, key in self._bar_localize_order:
            if tab not in texts_by_tab:
                texts_by_tab[tab] = self.bar_texts(lang, self._last_applied.get(tab))
            out.append(gr.update(**texts_by_tab[tab][key]))
        vtexts_by_tab = {}
        for tab, key in self._vbar_localize_order:
            if tab not in vtexts_by_tab:
                vtexts_by_tab[tab] = self.vbar_texts(lang, self._last_video.get(tab))
            out.append(gr.update(**vtexts_by_tab[tab][key]))
        return out

    def _localize(self, raw):
        try:
            req = json.loads(raw) if str(raw or "").lstrip().startswith("{") else {"browser": raw}
        except Exception:
            req = {}
        settings = load_settings()
        if req.get("browser"):
            _LAST_BROWSER["lang"] = str(req["browser"])[:16]
        lang = req.get("lang") if req.get("lang") in LANGS else resolve_lang(settings["language"], req.get("browser"))
        return (json.dumps(settings), *self.tab_updates(lang), *self._ordered_bar_updates(lang), *self._prompt_ui_updates(lang))

    def _prompt_ui_updates(self, lang):
        """Visibility of the Prompt Library UI + prompt choices (value untouched). Evaluated lazily at page load."""
        on = promptlink.available()
        choices = [(p["title"], p["id"]) for p in promptlink.list_prompts()] if on else []
        return (gr.update(visible=on), gr.update(visible=on),
                gr.update(choices=choices, label=tr(lang, "mgr_prompts"), interactive=promptlink.can_write()))

    def _save_from_ui(self, replace_mode, auto_apply, show_edit, toasts, toast_s, language="auto", on_apply_prompts="offer",
                      video_bar=True, crop_save="auto", crop_save_images="auto", index_paused=False, browser_lang="", browser_fullscreen=None):
        settings = copy.deepcopy(DEFAULT_SETTINGS)
        settings.update({
            "replace_mode": _coerce("replace_mode", "replace", replace_mode),
            "auto_apply": bool(auto_apply),
            "show_edit_bar": bool(show_edit),
            "toasts": bool(toasts),
            "toast_ms": _coerce("toast_ms", 3500, (toast_s or 0) * 1000 if isinstance(toast_s, (int, float)) else None),
            "language": _coerce("language", "auto", language),
            "on_apply_prompts": _coerce("on_apply_prompts", "offer", on_apply_prompts),
            "video_bar": bool(video_bar),
            "crop_save": _coerce("crop_save", "auto", crop_save),
            "crop_save_images": _coerce("crop_save_images", "auto", crop_save_images),
            "index_paused": bool(index_paused),
            "browser_fullscreen": bool(load_settings().get("browser_fullscreen", False)) if browser_fullscreen is None else bool(browser_fullscreen),
        })
        _cur = load_settings()
        settings.update({k: _cur.get(k, DEFAULT_SETTINGS[k]) for k in ("browser_details", "browser_thumb")})   # 1.5.9: set from the browser header
        imagelib.set_paused(settings["index_paused"])
        lang = resolve_lang(settings["language"], browser_lang)
        try:
            save_settings(settings)
        except Exception as e:
            return (tr(lang, "save_failed", error=e), gr.skip(), *self.tab_updates(lang), *self._ordered_bar_updates(lang),
                    *self._prompt_ui_updates(lang))
        return (tr(lang, "saved", time=time.strftime("%H:%M:%S")), json.dumps(settings), *self.tab_updates(lang),
                *self._ordered_bar_updates(lang), *self._prompt_ui_updates(lang))

    # ------------------------------------------------------------ JS bridge
    def _bridge_fn(self, key, with_bar=False):
        def fn(raw, gallery, state):
            resp, gal, st = self.bridge(key, raw, gallery, state)
            if not with_bar:
                return resp, gal, st
            try:
                data = json.loads(resp)
            except Exception:
                data = {}
            if data.get("applied"):
                # Reflect the loaded collection in the generator-form bar (reflib:apply / manager "Apply").
                ch, val = _dropdown_choices(data.get("lang") or self._lang(), data["applied"]["id"])
                return resp, gal, st, gr.update(choices=ch, value=val), _status_html(data)
            return resp, gal, st, gr.skip(), gr.skip()
        fn.__name__ = f"reflib_{key.replace(':', '_')}"
        return fn

    def bridge(self, key, raw, gallery, state):
        try:
            req = json.loads(raw or "{}")
            if not isinstance(req, dict):
                raise ValueError
        except Exception:
            return json.dumps({"ok": False, "error": tr("en", "bad_request")}), gr.skip(), gr.skip()
        lang = req.get("lang") if req.get("lang") in LANGS else resolve_lang(load_settings()["language"])
        out_gallery, out_state = gr.skip(), gr.skip()
        try:
            if req.get("target") not in (None, key):
                out = self._err(lang, "bad_request")
            elif req.get("action") == "apply_images":
                out, out_gallery, out_state = self.apply_images(key.split(":", 1)[0], imagelib.resolve_selection(req["selection"]) if isinstance(req.get("selection"), dict) else req.get("hashes"), gallery, state,
                                                                mode=req.get("mode"), lang=lang)
            elif req.get("action") == "apply_history":   # 1.5.5: refs of a history entry
                from .reflib_core import history as _h
                out, out_gallery, out_state = self.apply_images(key.split(":", 1)[0], None, gallery, state, mode=req.get("mode"), lang=lang,
                                                                paths_override=_h.paths(str(req.get("eid") or ""), "image_refs") or ["\0none"])
            elif req.get("action") == "apply_video_refs":   # 1.5.7: refs embedded in a generated video (no history entry)
                pths = _embedded_refs(_video_from_url(str(req.get("path") or "")))
                if not pths:
                    out = self._err(lang, "pv_no_refs")
                else:
                    out, out_gallery, out_state = self.apply_images(key.split(":", 1)[0], None, gallery, state, mode=req.get("mode"), lang=lang, paths_override=pths)
            elif req.get("action") == "apply":
                tab = key.split(":", 1)[0]
                out, out_gallery, out_state = self.apply_collection(
                    tab, req.get("collection_id"), gallery, state,
                    mode=req.get("mode"), lang=lang)
            elif req.get("action") == "inspect":
                from shared.gradio.gallery import get_gradio_file_path, get_list, get_state
                st = get_state(state)
                names = [os.path.basename(get_gradio_file_path(it) or "") for it in get_list(gallery)]
                out = {"ok": True, "gallery": names, "selected": st.get("selected"),
                       "count": len(names), "last_applied": self._last_applied.get(tab := key.split(':', 1)[0])}
            elif req.get("action") == "list":
                out = {"ok": True, "collections": [storage.public_summary(c) for c in storage.list_collections()]}
            else:
                out = self._err(lang, "unknown_action")
        except Exception as e:
            traceback.print_exc()
            out = {"ok": False, "error": storage_error_text(lang, e)}
        out["id"] = req.get("id")
        out["target"] = key
        out["lang"] = lang
        return json.dumps(out, ensure_ascii=False), out_gallery, out_state

    # ------------------------------------------------------------ image browser (1.4.0)
    def _ilib_payload(self, lang, rescan=False):
        """1.4.4: counts, collections, tags, folders and the folder tree only, never the image list (pages come from
        the "query" action). Kept small whatever the library size."""
        scan = imagelib.start_scan() if rescan else imagelib.scan_status()
        out = {"ok": True, "meta": imagelib.meta(), "scan": scan, "default_collection": self._last_applied.get("generate") or "",
               "paused": imagelib.is_paused()}
        return out

    def _outputs_dir(self):
        """WanGP's outputs folder (shortcut in the folder picker), best effort."""
        try:
            import sys as _sys
            mod = _sys.modules.get("wgp") or _sys.modules.get("__main__")   # never import wgp (it is the app itself)
            cfg = getattr(mod, "server_config", None) or {}
            p = cfg.get("save_path") or cfg.get("image_save_path")
            if p:
                return p
        except Exception:
            pass
        return os.path.join(os.getcwd(), "outputs")

    def _scan_message(self, lang, st):
        if st.get("running"):
            return tr(lang, "folder_indexing", path=st.get("path") or "", done=st.get("done", 0), total=st.get("total", 0))
        if st.get("missing"):
            return tr(lang, "rescanned_missing", files=st.get("files", 0), m=len(st["missing"]))
        return tr(lang, "rescanned", files=st.get("files", 0), added=st.get("added", 0), removed=st.get("removed", 0))

    def ilib(self, raw, request: gr.Request = None):
        try:
            req = json.loads(raw or "{}")
            req = req if isinstance(req, dict) else {}
        except Exception:
            req = {}
        lang = req.get("lang") if req.get("lang") in LANGS else self._lang(req.get("browser"))
        action = req.get("action")
        if action == "reveal":   # 1.5.2 "Show in folder": same-PC requests only, library-known files only
            from .reflib_core import reveal as _rv
            host = getattr(getattr(request, "client", None), "host", None) if request is not None else None
            if not _rv.is_local(host):
                return json.dumps({"ok": False, "id": req.get("id"), "error": TEXT[lang]["reveal_remote"]})
            p = _rv.known_path(str(req.get("hash") or ""))
            if not p:
                return json.dumps({"ok": False, "id": req.get("id"), "error": TEXT[lang]["reveal_missing"]})
            try:
                _rv.reveal(p)
                return json.dumps({"ok": True, "id": req.get("id"), "path": p})
            except Exception as e:
                return json.dumps({"ok": False, "id": req.get("id"), "error": str(e)[:200]})
        hashes = req.get("hashes") if isinstance(req.get("hashes"), list) else []
        try:
            if isinstance(req.get("selection"), dict):   # 1.4.4: "all N matching" without sending N hashes
                hashes = imagelib.resolve_selection(req["selection"])
            if action == "open":
                imagelib.maybe_scan()
                out = self._ilib_payload(lang)
                out["page"] = imagelib.query(req.get("f"), 0, int(req.get("limit") or 120), int(req.get("tz") or 0))
            elif action == "query":
                out = {"ok": True, "page": imagelib.query(req.get("f"), int(req.get("offset") or 0), int(req.get("limit") or 120),
                                                         int(req.get("tz") or 0))}
                if req.get("meta"):
                    out.update({k: v for k, v in self._ilib_payload(lang).items() if k != "ok"})
            elif action == "ui_pref":   # 1.5.5 browser UI preferences
                st = load_settings()
                for k in ("browser_fullscreen", "browser_details", "browser_thumb"):   # 1.5.9: only the keys sent
                    if k in req:
                        st[k] = _coerce(k, DEFAULT_SETTINGS[k], req[k])
                save_settings(st)
                out = {"ok": True, **{k: st[k] for k in ("browser_fullscreen", "browser_details", "browser_thumb")}}
            elif action in ("used_del", "used_undo"):   # 1.5.6
                from .reflib_core import refusage
                if action == "used_undo":
                    n = refusage.undo(str(req.get("batch") or ""))
                    out = {"ok": n > 0, "n": n, "message": tr(lang, "used_restored_n", n=n)}
                else:
                    _ids, since, until = _del_scope(req)
                    sel = refusage.select(hashes if (req.get("hashes") or req.get("selection")) else None, since, until)
                    if req.get("dry"):
                        out = {"ok": True, "n": len(sel)}
                    else:
                        r = refusage.clear_batch(sel)
                        out = {"ok": True, "n": r["n"], "batch": r["batch"], "message": tr(lang, "used_deleted_n", n=r["n"])}
            elif action == "used_clear":   # 1.5.5: remove entries from the "used as reference" history (images stay)
                from .reflib_core import refusage
                out = {"ok": True, "n": refusage.clear(None if req.get("all") else hashes)}
            elif str(action or "").startswith("hist_"):
                out = self._history(action, req, lang)
            elif action == "index_of":
                out = {"ok": True, "index": imagelib.index_of(req.get("f"), str(req.get("hash") or ""))}
            elif action == "locate":
                loc = imagelib.locate(str(req.get("hash") or ""))
                out = dict(loc, ok=True) if loc else {"ok": False, "error": "not found"}
            elif action == "range":
                out = {"ok": True, "hashes": imagelib.range_hashes(req.get("f"), int(req.get("start") or 0), int(req.get("end") or 0))}
            elif action == "sel_info":
                out = {"ok": True, "info": imagelib.selection_info(hashes, str(req.get("one_col") or "") or None), "sig": req.get("sig")}
            elif action == "pause_index":
                st = load_settings()
                st["index_paused"] = bool(req.get("paused"))
                save_settings(st)
                imagelib.set_paused(st["index_paused"])
                out = {"ok": True, "scan": imagelib.scan_status(), "paused": st["index_paused"]}
            elif action == "list":
                out = self._ilib_payload(lang, rescan=bool(req.get("rescan")))
            elif action == "thumbs":
                pend = []
                out = {"ok": True, "thumbs": imagelib.thumbs_for((req.get("hashes") or [])[:24], budget=0.25, pending=pend), "pending": pend}
            elif action == "resize_start":   # 1.6.2: a library video -> resized copy in the Video Library
                h = str(req.get("hash") or "")
                ent = imagelib.entry_for(h) or {}
                src = imagelib.media_path(h) if ent.get("kind") == "video" else None
                out = self.resize_start(src, str(req.get("preset") or ""), os.path.splitext(ent.get("name") or "")[0], bool(req.get("upscale")), lang)
            elif action == "resize_status":
                from .reflib_core import resize as _rs
                st = _rs.status(req.get("job"))
                out = {"ok": bool(st), "job": st}
            elif action == "resize_cancel":
                from .reflib_core import resize as _rs
                out = {"ok": _rs.cancel(req.get("job"))}
            elif action == "media_src":   # 1.6.1 "Recortar": the library file handed to Cropper's file API
                h = str(req.get("hash") or "")
                ent, src = imagelib.entry_for(h) or {}, imagelib.media_path(h)
                if not src or not os.path.isfile(src):
                    out = {"ok": False, "error": "file not found"}
                else:
                    out = {"ok": True, "path": os.path.abspath(src), "url": _serve_url(src), "kind": ent.get("kind") or imagelib.kind_of(src),
                           "name": os.path.splitext(ent.get("name") or os.path.basename(src))[0]}
            elif action == "crop_save":   # 1.6.1: Cropper's result -> "Recortes" (images) / Video Library (videos)
                from .reflib_core import api as _rapi, storage as _st
                path, kind, srch = str(req.get("path") or ""), str(req.get("kind") or ""), str(req.get("src") or "")
                ent = imagelib.entry_for(srch) or {}
                base = os.path.splitext(ent.get("name") or "crop")[0][:80]
                if not path or not os.path.isfile(path) or imagelib.kind_of(path) != kind or kind not in ("image", "video"):
                    out = {"ok": False, "error": "bad crop result"}
                elif kind == "image":
                    r = _rapi.add_image(path, name=f"{base} (crop){os.path.splitext(path)[1].lower()}", source="media-browser",
                                        meta={"source_hash": srch, "dedupe_key": "crop:" + _st._file_hash(path)})
                    if not r:
                        out = {"ok": False, "error": "not saved"}
                    else:
                        imagelib.invalidate()
                        out = {"ok": True, "kind": "image", "collection_id": r.get("collection_id"), "collection_name": r.get("collection_name"),
                               "hash": _st._file_hash(r["path"]) if r.get("path") and os.path.isfile(r["path"]) else _st._file_hash(path)}
                else:
                    vid = _rapi.add_video(path, name=f"{base} (crop)", source="media-browser", meta={"source_hash": srch})
                    out = {"ok": bool(vid), "kind": "video", "video_id": vid} if vid else {"ok": False, "error": "not saved"}
            elif action == "media_url":   # 1.6.0: stream one video/audio in the browser (hover, viewer, details)
                u = imagelib.media_url(str(req.get("hash") or ""))
                out = {"ok": bool(u), "url": u}
            elif action == "media_dur":   # 1.6.0: durations probed so far (background, throttled)
                from .reflib_core import mediainfo
                dd = {}
                for h in [str(x) for x in (req.get("hashes") or [])][:400]:
                    mi = mediainfo.get(h)
                    if mi and mi.get("duration"):
                        dd[h] = mi["duration"]
                out = {"ok": True, "dur": dd}
            elif action == "to_vlib":   # 1.6.0: selected videos -> Video Library
                n_add = n_dup = 0
                for h in hashes:
                    ent = imagelib.entry_for(h) or {}
                    src = imagelib.media_path(h) if ent.get("kind") == "video" else None
                    if not src:
                        continue
                    try:
                        _v, created = videostore.add_video(src, name=os.path.splitext(ent.get("name") or os.path.basename(src))[0], source="browser")
                        n_add += 1 if created else 0
                        n_dup += 0 if created else 1
                    except Exception as e:
                        print(f"[Reference Library] to video library failed: {e}")
                out = {"ok": bool(n_add or n_dup), "added": n_add, "dup": n_dup, "message": tr(lang, "vlib_added", n=n_add, k=n_dup)}
            elif action == "preview":
                p = imagelib.preview(str(req.get("hash") or ""))
                out = {"ok": bool(p), "image": p} if p else self._err(lang, "err_image_missing")
            elif action == "tag":
                res = imagelib.set_tags(hashes, req.get("add") or [], req.get("remove") or [])
                out = self._ok(lang, "ilib_tagged", n=res["changed"]) if res["changed"] else \
                    {"ok": True, "message": tr(lang, "ilib_tag_nochange"), "toast": tr(lang, "ilib_tag_nochange"), "kind": "info"}
                out.update(self._ilib_payload(lang))
            elif action == "add":
                if req.get("new_name") is not None:
                    res = imagelib.new_collection_with(hashes, str(req.get("new_name") or "").strip() or tr(lang, "default_name"),
                                                       fallback=tr(lang, "default_name"))
                    out = self._ok(lang, "ilib_new_col", name=res["collection"]["name"], n=res["added"], _cid=res["collection"]["id"])
                else:
                    res = imagelib.add_to_collection(hashes, str(req.get("collection_id") or ""))
                    name = res["collection"]["name"]
                    if not res["added"]:
                        out = {"ok": True, "kind": "info", "message": tr(lang, "ilib_added_none", name=name),
                               "toast": tr(lang, "ilib_added_none", name=name)}
                    else:
                        key = "ilib_added_skip" if res["skipped"] else "ilib_added"
                        out = self._ok(lang, key, added=res["added"], skipped=res["skipped"], name=name, _cid=res["collection"]["id"])
                out["added"], out["skipped"], out["collection_id"] = res["added"], res["skipped"], res["collection"]["id"]
                out["reload"] = True
                out.update({k: v for k, v in self._ilib_payload(lang).items() if k not in ("ok",)})
            elif action == "delete":
                res = imagelib.pool_delete(hashes)
                if res["deleted"]:
                    out = self._ok(lang, "ilib_deleted", n=len(res["deleted"]))
                    out["undo_hashes"] = res["deleted"]
                    if res["kept"]:
                        out["toast"] += " · " + tr(lang, "ilib_delete_kept")
                else:
                    out = self._err(lang, "ilib_delete_kept")
                out.update({k: v for k, v in self._ilib_payload(lang).items() if k not in ("ok",)})
            elif action == "remove_from":
                res = imagelib.remove_from_collection(hashes, str(req.get("collection_id") or ""))
                name = res["collection"]["name"]
                out = self._ok(lang, "ilib_removed_from", n=res["removed"], name=name, _cid=res["collection"]["id"])
                out["undo_remove"] = res["token"]
                out["reload"] = True
                out.update({k: v for k, v in self._ilib_payload(lang).items() if k not in ("ok",)})
            elif action == "delete_all":
                res = imagelib.delete_everywhere(hashes)
                if res["deleted"]:
                    msg = tr(lang, "ilib_deleted_all", n=res["deleted"], c=res["collections"])
                    if res["on_disk"]:
                        msg += " · " + tr(lang, "ilib_folder_kept", k=res["on_disk"])
                    out = {**self._ok(lang, "ilib_deleted"), "message": msg, "toast": msg, "undo_remove": res["token"], "reload": True}
                else:
                    msg = tr(lang, "ilib_folder_only", k=res["folder_only"])
                    out = {"ok": True, "kind": "info", "message": msg, "toast": msg}
                out.update({k: v for k, v in self._ilib_payload(lang).items() if k not in ("ok",)})
            elif action == "undo_remove":
                res = imagelib.undo_remove(str(req.get("token") or ""))
                out = self._ok(lang, "ilib_restored", n=res["restored"])
                out["reload"] = True
                out.update({k: v for k, v in self._ilib_payload(lang).items() if k not in ("ok",)})
            elif action == "restore":
                res = imagelib.pool_restore(hashes)
                out = self._ok(lang, "ilib_restored", n=res["restored"]) if res["restored"] else \
                    {"ok": True, "kind": "info", "message": tr(lang, "ilib_restore_dup"), "toast": tr(lang, "ilib_restore_dup")}
                out.update({k: v for k, v in self._ilib_payload(lang).items() if k not in ("ok",)})
            elif action == "folder_add":
                f = imagelib.add_folder(str(req.get("path") or ""), bool(req.get("recursive", True)), background=True)
                msg = tr(lang, "folder_added_bg", path=f["path"])
                out = {"ok": True, "message": msg, "toast": msg, "kind": "info", "folder_id": f["id"]}
                out.update({k: v for k, v in self._ilib_payload(lang).items() if k not in ("ok",)})
            elif action == "folder_remove":
                imagelib.remove_folder(str(req.get("folder_id") or ""))
                out = {"ok": True, "message": tr(lang, "folder_removed"), "toast": tr(lang, "folder_removed")}
                out.update({k: v for k, v in self._ilib_payload(lang).items() if k not in ("ok",)})
            elif action == "folder_recursive":
                imagelib.set_folder_recursive(str(req.get("folder_id") or ""), bool(req.get("recursive")), background=True)
                out = {"ok": True}
                out.update({k: v for k, v in self._ilib_payload(lang).items() if k not in ("ok",)})
            elif action in ("rescan", "folder_rescan"):
                fid = str(req.get("folder_id") or "")
                imagelib.start_scan([fid] if action == "folder_rescan" and fid else None)
                out = self._ilib_payload(lang)
                msg = tr(lang, "rescanning")
                out.update({"message": msg, "toast": msg, "kind": "info"})
            elif action == "browse":
                path = str(req.get("path") or "")
                if not path:
                    out = {"ok": True, "browse": imagelib.browse_roots(self._outputs_dir())}
                else:
                    out = {"ok": True, "browse": imagelib.browse_dir(path)}
            elif action.startswith("at_") if isinstance(action, str) else False:
                out = self._autotag(action, req, hashes, lang)
            elif action == "scan_status":
                st = imagelib.scan_status()
                out = {"ok": True, "scan": st, "scan_message": self._scan_message(lang, st)}
            else:
                out = self._err(lang, "bad_request")
        except Exception as e:
            if not isinstance(e, (storage.StorageError, ValueError)):
                traceback.print_exc()
            out = {"ok": False, "error": storage_error_text(lang, e)}
        if action not in self.ILIB_READONLY:
            imagelib.invalidate()
        out["id"] = req.get("id")
        out["ilib"] = True
        return json.dumps(out, ensure_ascii=False)

    ILIB_READONLY = ("open", "query", "range", "sel_info", "index_of", "locate", "pause_index", "list", "thumbs", "preview", "browse", "scan_status",
                     "at_status", "at_facets", "at_image", "at_settings", "at_estimate", "at_pause", "at_cancel", "at_unload", "at_enqueue", "at_jobfacets", "at_retry",
                     "hist_list", "hist_outputs", "hist_find", "hist_settings", "hist_delete", "hist_undo", "hist_config", "ui_pref", "hist_del", "hist_undo_batch", "hist_get", "at_tax_export", "media_url", "media_dur", "media_src", "resize_status")

    def _autotag(self, action, req, hashes, lang):
        svc = autotag_service()
        if action == "at_status":
            return {"ok": True, "at": svc.queue.status()}
        if action == "at_tax_export":   # 1.5.8
            from .reflib_core import usertax
            fmt = "csv" if req.get("fmt") == "csv" else "json"
            out = usertax.export("mine" if req.get("scope") == "mine" else "full", fmt)
            return {"ok": True, "fmt": fmt, "data": out}
        if action in ("at_tax_add", "at_tax_update", "at_tax_delete", "at_tax_undo", "at_tax_list", "at_tax_import"):
            from .reflib_core import usertax
            try:
                if action == "at_tax_add":
                    r = usertax.add(req.get("kind", "tag"), req.get("parent"), req.get("es", ""), req.get("en", ""),
                                    req.get("syn_es"), req.get("syn_en"), bool(req.get("exclusive")))
                elif action == "at_tax_update":
                    r = usertax.update(str(req.get("tid") or ""), es=req.get("es"), en=req.get("en"), syn_es=req.get("syn_es"),
                                       syn_en=req.get("syn_en"), parent=req.get("parent"), **({"exclusive": req["exclusive"]} if "exclusive" in req else {}))
                elif action == "at_tax_delete":
                    r = usertax.delete(str(req.get("tid") or ""))
                elif action == "at_tax_undo":
                    r = usertax.undo()
                elif action == "at_tax_import":   # 1.5.8
                    r = usertax.import_(req.get("data") or {}, req.get("mode", "merge"), bool(req.get("dry_run")))
                    if r.get("rejected"):
                        for x in r["rejected"]:
                            x["reason"] = usertax.MSG.get(x["code"], {}).get(lang[:2], x["code"])
                else:
                    r = None
            except usertax.UserTaxError as e:
                return {"ok": False, "error": e.msg(lang), "code": e.code}
            imagelib.invalidate()
            return {"ok": True, "r": r, "user": usertax.listing(), "tax": _taxonomy.compact()}
        if action == "at_suggest":
            return {"ok": True, "sug": imagelib.suggest(req.get("text", ""), req.get("f"), lang)}
        if action == "at_facets":
            out = {"ok": True, "facets": imagelib.facets(req.get("f")), "body": imagelib.body_stats(req.get("f")),
                   "jobs": svc.job_facets(req.get("f")), "jrev": svc.queue.jrev}
            if req.get("tax"):
                out["tax"] = _taxonomy.compact()
            return out
        if action == "at_image":
            return {"ok": True, "img": svc.image_tags(str(req.get("hash") or ""), lang)}
        if action == "at_edit":
            svc.edit(str(req.get("hash") or ""), str(req.get("tag") or ""), str(req.get("op") or ""))
            return {"ok": True, "img": svc.image_tags(str(req.get("hash") or ""), lang)}
        if action == "at_height":
            cm = req.get("cm")
            cm = float(cm) if cm not in (None, "", 0) else None
            if cm is not None and not 120 <= cm <= 220:
                raise ValueError(tr(lang, "at_height_bad"))
            if req.get("collection_id"):
                n = svc.set_collection_height(str(req["collection_id"]), cm)
            else:
                n = svc.set_height(hashes or [str(req.get("hash") or "")], cm)
            return {"ok": True, "n": n, "img": svc.image_tags(str(req.get("hash") or ""), lang) if req.get("hash") else None}
        if action == "at_settings":
            if isinstance(req.get("set"), dict):
                svc.save_settings(req["set"])
            from .reflib_core import backends as _b
            from .reflib_core import cloud as _c
            return {"ok": True, "settings": svc.settings(), "models": {k: {kk: v[kk] for kk in ("label", "size_gb", "licence") if kk in v} | {"cloud": bool(v.get("cloud")), "paid": bool(v.get("paid"))} for k, v in _b.MODELS.items()},
                    "cloud": {k: {"provider": v["provider"], "model_id": v["model_id"], "batch": v["batch"], "clothed_only": bool(v.get("clothed_only")),
                                  "key_field": v["key_field"], "key_env": v["key_env"][0], "env_set": any(os.environ.get(e) for e in v["key_env"]),
                                  "price": _c.DEFAULT_PRICES[k], "warning": _c.PRICE_WARNINGS.get(k, "")} for k, v in _c.CLOUD.items()},
                    "policies": _c.POLICIES}
        if action in ("at_estimate", "at_enqueue"):   # 1.6.0: only images are auto-tagged
            n_all = len(hashes)
            hashes = svc.only_images(hashes)
            if not hashes and n_all:
                return {"ok": False, "error": tr(lang, "at_no_images")}
        if action == "at_estimate":
            return {"ok": True, "estimate": svc.estimate(len(hashes))}
        if action == "at_enqueue":
            est = svc.estimate(len(hashes))
            if (est.get("cloud") or est.get("download_gb")) and not req.get("confirm"):
                return {"ok": True, "confirm": est}   # the UI shows size / cost and asks once
            r = svc.enqueue(hashes, force=bool(req.get("force")))
            r["not_image"] = n_all - len(hashes)
            msg = tr(lang, "at_queued", n=r["queued"], k=r["skipped"]) + (" " + tr(lang, "at_not_image", n=r["not_image"]) if r["not_image"] else "")
            return {"ok": True, "queued": r, "at": svc.queue.status(), "message": msg}
        if action == "at_jobfacets":
            return {"ok": True, "counts": svc.job_facets(req.get("f")), "jrev": svc.queue.jrev}
        if action == "at_retry":
            r = svc.retry_failed()
            return {"ok": True, "queued": r, "at": svc.queue.status(), "message": tr(lang, "at_queued", n=r["queued"], k=r["skipped"])}
        if action == "at_pause":
            svc.queue.pause(bool(req.get("paused")))
            return {"ok": True, "at": svc.queue.status()}
        if action == "at_cancel":
            svc.queue.cancel()
            return {"ok": True, "at": svc.queue.status()}
        if action == "at_unload":
            svc.queue.unload()
            return {"ok": True, "at": svc.queue.status()}
        return self._err(lang, "bad_request")

    def ilib_fast(self, raw):
        """Only read-only, quick actions go through the unqueued channel."""
        try:
            req = json.loads(raw or "{}")
        except Exception:
            req = {}
        if not isinstance(req, dict) or req.get("action") not in ("thumbs", "scan_status", "browse", "preview", "open", "query", "range", "sel_info", "pause_index", "at_status", "at_facets", "at_image", "at_suggest", "index_of", "locate", "at_jobfacets", "hist_list", "hist_outputs", "hist_find", "hist_settings", "hist_get", "media_url", "media_dur", "media_src", "resize_status", "resize_cancel"):
            return json.dumps({"ok": False, "id": (req or {}).get("id") if isinstance(req, dict) else None, "error": "bad request"})
        return self.ilib(raw)

    def ilib_upload(self, files, raw_meta):
        try:
            meta = json.loads(raw_meta or "{}")
        except Exception:
            meta = {}
        lang = meta.get("lang") if meta.get("lang") in LANGS else self._lang(meta.get("browser"))
        created = skipped = 0
        for f in files or []:
            path = f if isinstance(f, str) else getattr(f, "name", None) or (f.get("path") if isinstance(f, dict) else None)
            name = os.path.basename(getattr(f, "orig_name", None) or path or "")
            try:
                res = imagelib.pool_add(path, name=name, source="import")
                created += 1 if res["created"] else 0
                skipped += 0 if res["created"] else 1
            except storage.StorageError:
                skipped += 1
        if created:
            key = "ilib_imported_skip" if skipped else "ilib_imported"
            out = self._ok(lang, key, n=created, skipped=skipped)
        else:
            out = {"ok": True, "kind": "info", "message": tr(lang, "ilib_imported_none"), "toast": tr(lang, "ilib_imported_none")}
        out.update({k: v for k, v in self._ilib_payload(lang).items() if k not in ("ok",)})
        out["id"] = meta.get("id")
        out["ilib"] = True
        out["imported"] = created
        return json.dumps(out, ensure_ascii=False), None

    # ------------------------------------------------------------ video JS bridge
    def _vbridge_fn(self, tab, with_bar=False):
        def fn(raw, value):
            resp, video_u, sel = self.vbridge(tab, raw, value)
            if not with_bar:
                return resp, video_u
            if sel is None:
                return resp, video_u, gr.skip(), gr.skip(), gr.skip()
            try:
                data = json.loads(resp)
            except Exception:
                data = {}
            lang = data.get("lang") or self._lang()
            status = _status_html(data) if data.get("message") and not data.get("offer_token") else gr.skip()
            return resp, video_u, self._vdd_update(tab, lang, sel or None), status, _video_info_html(lang, sel or self._last_video.get(tab))
        fn.__name__ = f"reflib_{tab}_video_guide"
        return fn

    def vbridge(self, tab, raw, value):
        """Returns (json response, Control Video update, bar selection or None = leave the bar alone)."""
        try:
            req = json.loads(raw or "{}")
            if not isinstance(req, dict):
                raise ValueError
        except Exception:
            return json.dumps({"ok": False, "error": tr("en", "bad_request")}), gr.skip(), None
        lang = req.get("lang") if req.get("lang") in LANGS else resolve_lang(load_settings()["language"])
        key = f"{tab}:video_guide"
        video_u, sel = gr.skip(), None
        try:
            action = req.get("action")
            if req.get("target") not in (None, key):
                out = self._err(lang, "bad_request")
            elif action == "video_load":
                out, video_u = self.load_video(tab, req.get("video_id"), lang)
                if out.get("ok"):
                    sel = out["vid"]
            elif action == "video_add":
                path = _public_api._clean_src(req.get("path"))
                source = str(req.get("source") or "manual")
                meta = req.get("meta") if isinstance(req.get("meta"), dict) else None
                vid = _public_api.add_video(path, name=req.get("name") or None, source=source, meta=meta)
                note = _public_api.take_note(path) if path else None
                if note:
                    out = self.note_toast(lang, note)
                    sel = self._last_video.get(tab) or ""
                elif source == "cropper" and _public_api.crop_policy() == "off":
                    out = {"ok": True, "quiet": True, "saved": False}
                elif not path or not os.path.isfile(path):
                    out = self._err(lang, "err_video_missing")
                elif not media.is_video_path(path):
                    out = self._err(lang, "err_not_video")
                else:
                    out = self._err(lang, "err_generic", e="add_video")
                out["vid"] = out.get("vid") or vid
            elif action == "video_offer_accept":
                entry, created = _public_api.accept_offer(req.get("token"))
                if created:
                    out = {**self._ok(lang, "vcrop_saved", name=entry["name"], _cid=entry["id"])}
                else:
                    out = {"ok": True, "message": tr(lang, "vdup", name=entry["name"]), "toast": tr(lang, "vdup", name=entry["name"]),
                           "kind": "info"}
                out["vid"] = entry["id"]
                current = _public_api._clean_src(value)
                if current and os.path.isfile(current) and videostore.file_hash(current) == entry.get("hash"):
                    self._last_video[tab] = entry["id"]   # the crop is the current Control Video
                sel = self._last_video.get(tab) or ""
            elif action == "image_offer_accept":
                res = _public_api.accept_image_offer(req.get("token"))
                key2 = "icrop_saved" if res["created"] else "icrop_dup"
                out = self._ok(lang, key2, collection=res["collection_name"], name=res["name"], _cid=res["collection_id"]) if res["created"] else \
                    {"ok": True, "message": tr(lang, key2, collection=res["collection_name"], name=res["name"]),
                     "toast": tr(lang, key2, collection=res["collection_name"], name=res["name"]), "kind": "info"}
                out["reload"] = True
            elif action == "resize_start":   # 1.6.2: resize the current Control Video
                path = _public_api._clean_src(value)
                nm = None
                lv = self._last_video.get(tab)
                if lv and path and os.path.isfile(path):
                    try:
                        e2 = videostore.get_video(lv)
                        if e2 and e2.get("hash") == videostore.file_hash(path):
                            nm = e2.get("name")
                    except Exception:
                        pass
                out = self.resize_start(path, str(req.get("preset") or ""), nm or os.path.splitext(os.path.basename(path or ""))[0], bool(req.get("upscale")), lang)
            elif action == "resize_apply":   # 1.6.2: the finished resize replaces the Control Video
                from .reflib_core import resize as _rs
                st = _rs.status(req.get("job"))
                if not st or st["state"] != "done" or not (st.get("result") or {}).get("video_id"):
                    out = self._err(lang, "err_generic", e="resize")
                else:
                    out, video_u = self.load_video(tab, st["result"]["video_id"], lang)
                    if out.get("ok"):
                        sel = out["vid"]
                        out["quiet"] = True   # the browser shows its own "replaced + saved" toast
            elif action == "video_inspect":
                path = _public_api._clean_src(value)
                ok = bool(path and os.path.isfile(path))
                out = {"ok": True, "file": os.path.basename(path) if ok else None, "size": os.path.getsize(path) if ok else 0,
                       "hash": videostore.file_hash(path) if ok and req.get("hash") else None,
                       "selected": self._last_video.get(tab)}
            elif action == "video_list":
                out = {"ok": True, "videos": [videostore.public_summary(v) for v in videostore.list_videos()]}
            else:
                out = self._err(lang, "unknown_action")
        except Exception as e:
            if not isinstance(e, storage.StorageError):
                traceback.print_exc()
            out = {"ok": False, "error": storage_error_text(lang, e)}
        out["id"] = req.get("id")
        out["target"] = key
        out["tab"] = tab
        out["lang"] = lang
        return json.dumps(out, ensure_ascii=False), video_u, sel

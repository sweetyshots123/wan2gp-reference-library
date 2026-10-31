# 1.9.0 — Find similar (pose / face)

## EN
- **Find similar by pose and/or face**: right-click, details panel, multi-select bar, or drop photos (not saved). Pose / Face / Both, pose weight, minimum similarity, "like any / like all", ignore mirroring. Results are an explorer result set: sortable ("Most similar first", name, date…) and part of the navigation history.
- Background, incremental index in `data/similarity/` (separate Python env, onnxruntime, GPU when available), with progress, pause, and waiting while WanGP generates.
- **Selectable face model**: ArcFace w600k_r50 (default), ArcFace glintr100 (antelopev2, larger), AdaFace IR-101, SFace (automatic fallback). One face index per model; switching keeps the others and only recomputes faces. Lazy download with progress.
- **Licences:** ArcFace w600k_r50 / glintr100 (InsightFace) and AdaFace weights: **non-commercial research use only**. SFace Apache-2.0, YOLOX/DWPose Apache-2.0, YuNet MIT. Everything runs locally; no face or image leaves the PC.
- For the Galería: `sim_*` shared actions (see `SIMILARITY_API.md`), then `query` with filter `{sim: sid}`.
- Restart WanGP.

## ES
- **Buscar similares por pose y/o cara**: menú contextual, panel de detalles, barra de selección o soltando fotos (no se guardan). Pose / Cara / Ambas, peso, similitud mínima, «parecidas a cualquiera / a todas», ignorar espejo. El resultado es un conjunto del explorador: ordenable y en el historial.
- Índice incremental en segundo plano en `data/similarity/` (entorno Python aparte, GPU si hay), con progreso, pausa y espera mientras WanGP genera.
- **Modelo de caras a elegir**: ArcFace w600k_r50 (por defecto), ArcFace glintr100 (antelopev2), AdaFace IR-101, SFace (respaldo automático). Un índice de caras por modelo; cambiar conserva los demás y solo recalcula caras. Descarga al primer uso con progreso.
- **Licencias:** ArcFace w600k_r50 / glintr100 (InsightFace) y AdaFace: **solo uso de investigación no comercial**. SFace, YOLOX/DWPose Apache-2.0; YuNet MIT. Todo en local.
- Galería: acciones compartidas `sim_*` (ver `SIMILARITY_API.md`) y `query` con filtro `{sim: sid}`.
- Requiere reiniciar WanGP.

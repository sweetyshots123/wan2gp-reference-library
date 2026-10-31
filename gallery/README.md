# Galería (Media Library)

Segunda interfaz, muy visual, sobre **los mismos datos** de la Media Library (plugin Reference Library de WanGP).

- **URL:** `http://localhost:7860/reflib/gallery/` (la sirve WanGP; reinicia WanGP tras instalar o actualizar el plugin).
- **Sin sincronización:** la Galería llama al mismo manejador que el explorador de la Media Library (`POST /reflib/api` → acciones `ilib` del plugin). Lo que cambias en una lo ve la otra; la Galería además se recarga sola cuando cambia la revisión de la librería (sondeo cada 5 s).
- **Favoritas** = etiqueta `favorita`. **Modelos/personas** = etiqueta `modelo:<Nombre>`. Son etiquetas normales: la Media Library las muestra y edita.

## Desarrollo

```
cd gallery
npm install
npm run dev        # http://localhost:5174/reflib/gallery/  (proxy a WanGP en 7860)
WANGP=http://127.0.0.1:7882 npm run dev   # otro puerto
npm run build      # genera gallery/dist, que es lo que sirve WanGP
```

## Estructura

- `src/api.ts` cliente del puente (`call(action, body)`), miniaturas agrupadas (24 por llamada) y subida.
- `src/App.tsx` rutas (`#/`, `#/modelos`, `#/modelo/<n>`, `#/etiquetas`, `#/tag/<t>`, `#/colecciones`, `#/coleccion/<id>`, `#/favoritas`, `#/videos`, `#/sin-coleccion`), rejilla, selección en bloque. Una vista nueva = un caso en `parseRoute` + `routeFilter`.
- `src/Viewer.tsx` visor: clic en la foto = zoom hacia ese punto / otro clic = ajustar (arrastrar no cuenta como clic); rueda sin zoom = anterior/siguiente (una muesca = una foto, con umbral para trackpads); con zoom, rueda = desplazar; Ctrl+rueda = zoom (sin zoom de página); pellizco, + − 0, ← →, F (favorita), E (panel), Espacio (vídeo), editor de copia virtual (recorte y entrada/salida).
- `src/EditPanel.tsx` favorita, modelos, etiquetas, colecciones, acciones (copia virtual, Video Library, quitar, eliminar con deshacer). Sirve para 1 o N elementos.
- `src/actions.ts` ejecuta una acción, muestra el aviso y ofrece *Deshacer* si el servidor da token.
- `../gallery_routes.py` rutas FastAPI dentro de WanGP: `/reflib/api`, `/reflib/upload`, `/reflib/gallery/*`.

## Novedades 1.8.2
- **Personas** (antes "Modelos"): etiquetas `persona:Nombre`; `modelo:` sigue reconociéndose. Rutas `#/personas`, `#/persona/…` (alias `#/modelos`).
- **Búsqueda universal**: sugerencias agrupadas (Personas, Colecciones, Etiquetas, Archivos) con miniatura y conteo, vista previa en vivo, teclado (↑↓ Enter Esc ⌫), chips combinados con Y, sin distinguir acentos ni mayúsculas; página `#/buscar`.
- **Índice lateral (scrubber)**: según el orden — fecha (años/meses) o nombre (A–Z, #); cabeceras de sección, rejilla virtualizada, respeta los filtros. La fecha es la de importación o, si falta, la de modificación del archivo (no EXIF).
- **Tipos**: botones foto / vídeo / audio (multiselección, con conteos; audio desactivado "Sin audio" si no hay).
- **Vidosser**: los vídeos usan el reproductor Vidosser instalado (`/vidosser/vidosser.js`, cargado en tiempo de ejecución); si no está, `<video>` nativo.
- **Favoritos/etiquetas instantáneos**: actualización optimista y parche incremental del catálogo en el servidor.

## 1.8.3 · Carpetas
`#/carpetas` y `#/carpeta/<fid>/<rel>`: árbol de las carpetas vigiladas (mismo `meta.folders`/`meta.tree` que la Media Library), filtro `{node:{fid,rel}, sub:true}`.
Acciones del puente: `folder_add`, `browse`, `folder_rescan`, `rescan`, `folder_recursive`, `folder_excluded`, `folder_restore`, `folder_remove`, `pause_index`, `scan_status`.
Colecciones: casilla optimista + parche incremental del catálogo (sin reconstruir).

# Reference Library para Wan2GP

Guarda las **Referencias** de WanGP como colecciones con nombre y los **vídeos de control** en una librería de vídeos, y cárgalos de nuevo con un clic.

**Versión:** 1.7.1 ([cambios](CHANGELOG.md)) · **Autor:** [sweetyshots123](https://github.com/sweetyshots123) · **Licencia:** MIT · **Requiere:** [Wan2GP](https://github.com/deepbeepmeep/Wan2GP)

[English → README.md](README.md)

## Qué hace

- Una **barra compacta bajo la galería de Referencias**: elige una colección y pulsa Aplicar, Guardar como…, Actualizar o Gestionar. «Guardar como…» abre un pequeño campo de nombre en línea (Intro guarda, Esc cancela). Se adapta al tema oscuro y al claro de WanGP.
- **Renombrar en el sitio con el lápiz**, como en Prompt Library: el lápiz dentro del selector de colección de la barra (y en la barra de vídeos, en el selector de colección del gestor y en el nombre del vídeo elegido en la sección Vídeos) convierte el nombre en un campo de texto. Intro o hacer clic fuera guarda, Esc cancela; también vale doble clic. Misma validación y mensajes que el botón Renombrar, que se mantiene en el gestor (Prompt Library también mantiene el suyo).
- La pestaña **Reference Library** (Biblioteca de referencias en los textos de la UI) para crear, renombrar, duplicar, borrar, añadir/quitar/reordenar imágenes, elegir portada y exportar/importar zip.
- Al elegir una colección se cargan sus imágenes en Referencias con los mismos manejadores de WanGP que el botón Add, así que Quitar / Izquierda / Derecha / Clear siguen funcionando.
- Las colecciones viven en la carpeta del plugin (`collections/`) como archivos copiados más un índice: sobreviven a las actualizaciones de WanGP y no se pisan al actualizar el plugin.
- Borrado seguro: el primer clic convierte **Borrar** en un **Confirmar borrado** rojo durante 5 s; tras borrar aparece un aviso con **Deshacer** (Deshacer funciona durante 5 minutos; los archivos borrados se eliminan de `collections/.trash/` a los 15 minutos).
- Una **librería de vídeos** para Vídeo de control, con su propia barra bajo Vídeo de control y una sección Vídeos en la pestaña; los recortes hechos con Cropper se pueden guardar ahí automáticamente. Ver [Librería de vídeos](#librería-de-vídeos).
- **Vínculo opcional con [Prompt Library](https://github.com/sweetyshots123/wan2gp-prompt-library)** (1.1 o posterior): cada colección puede tener prompts asociados, que se ofrecen como chips bajo la barra al cargarla. Ver más abajo.
- Inglés y español (sigue el idioma del navegador, o lo fuerzas en ajustes).

## Librería de vídeos

Los vídeos de control tienen su propia librería, que se gestiona igual que las colecciones de imágenes.

- **Barra bajo Vídeo de control** (solo mientras WanGP muestra Vídeo de control): elige un vídeo (aparece como *nombre · duración · resolución*) para cargarlo, o usa **Cargar**, **Guardar como…** (nombre en línea; Intro guarda, Esc cancela, vacío = nombre del archivo) y **Gestionar**. Un póster pequeño con fps, fotogramas, tamaño y origen muestra el vídeo elegido.
- **Sección Vídeos** en la pestaña Reference Library: cuadrícula de miniaturas con su nombre, reproductor de vista previa, **Renombrar**, **Cargar en Vídeo de control**, **Izquierda / Derecha** para ordenar, **Borrar** (dos clics, **Deshacer** durante 5 minutos), **Descargar**, **Exportar todo** (zip) e **Importar** (vídeos o un zip de la librería).
- Deshacer un borrado nunca crea un duplicado: si el mismo vídeo (o el mismo recorte) se guardó otra vez mientras tanto, se queda la entrada que ya existe y un aviso lo explica.
- Los avisos salen en la **esquina inferior derecha**, lejos de los avisos arriba al centro de Dragger, Cropper y Prompt Library, así que botones como *Guardar en la librería* siempre se pueden pulsar.
- Los vídeos se **copian** en `videos/` con un póster y sus datos (resolución, fps, fotogramas, duración). El mismo vídeo (mismos bytes) nunca se guarda dos veces; si lo guardas otra vez te dice en qué entrada está.
- Al cargar se pone en Vídeo de control una copia con el nombre de la entrada, así que el archivo guardado nunca cambia. WanGP sigue tratando la entrada como siempre (etiqueta, *Frames to keep*, recortes de duración). *Frames to keep in Control Video* no se guarda con la entrada.
- **Los recortes de [Cropper](https://github.com/sweetyshots123/wan2gp-cropper)** se guardan ya recortados, según el ajuste *Recortes hechos con Cropper* (ver [Integración](#integración-cropper-y-otros-plugins)).

**¿Por qué una librería aparte y no vídeos dentro de las colecciones?** Las colecciones son conjuntos de imágenes que llenan la galería de Referencias; Vídeo de control es una sola entrada con su tamaño, fps y duración. Guardar los vídeos aparte (`videos/`, junto a `collections/`) hace que un clic cargue un vídeo, que las colecciones existentes no cambien (sin migración) y que cada lado tenga los controles que le corresponden. La interfaz es común: mismo estilo de barra, misma pestaña, mismo borrar/deshacer.

## Explorador de imágenes (1.4)

El icono de cuadrícula de la barra de Reference Library (y junto al selector de colección del gestor) abre un modal con **todas las imágenes** que conoce la librería, una vez por contenido (sha256):

- **Orígenes:** todas las colecciones, la **bolsa sin colección** y las **carpetas vigiladas**. Una insignia indica en cuántas colecciones está cada imagen (×2), o *sin colección* / *carpeta*.
- **Filtros:** colecciones (selección múltiple, *Todas*, *Sin colección*), carpetas, etiquetas (deben cumplirse todas las elegidas) y búsqueda por nombre.
- Las **etiquetas** son de la imagen (su hash): valen en cualquier sitio donde se use y sobreviven a renombrados, movimientos y reescaneos. Elige una o varias imágenes, escribe una etiqueta (autocompleta con las existentes; Enter o *Añadir etiqueta*) y quítala con la × de su chip. Se guardan en `collections/tags.json`.
- **Añadir a colección…** copia la selección a una colección (por defecto, la cargada en la barra) o a una nueva. El mismo contenido nunca se añade dos veces a una colección.
- **Importar imágenes** (botón o arrastrar y soltar sobre el modal) las guarda en la **bolsa sin colección** (`pool/`), sin duplicar nada de la librería. Las imágenes que salen de su última colección (quitadas, sustituidas con Actualizar o por borrar la colección) también se quedan en la bolsa. Se pueden etiquetar y añadir a colecciones; **Borrar** (dos clics, *Deshacer* durante 5 min, purgadas de `pool/.trash/` a los 15 min) borra imágenes de la bolsa sin colección. Desde 1.4.3 se puede borrar cualquier selección (ver abajo).
- **Carpetas vigiladas:** pulsa **Añadir carpeta** en la cabecera, escribe la ruta de una carpeta del equipo de WanGP (p. ej. `D:\Fotos\refs`; Gradio no tiene selector de carpetas, así que el servidor valida la ruta) *Incluir subcarpetas* está activado por defecto. Las rutas de Windows funcionan tal cual se escriben o pegan: barras invertidas, letras de unidad (`D:` sola equivale a `D:\`), espacios y comillas alrededor. La indexación empieza **en segundo plano** al momento, con una barra de progreso y un aviso con el recuento al terminar; la cuadrícula se va llenando y las miniaturas se cargan al hacer scroll, así que carpetas con miles de imágenes no congelan la página.
- **Recientes** (1.4.2): la primera entrada de la barra lateral, encima de *Todas las imágenes*. Es una vista, no una copia: todas las imágenes de la más nueva a la más antigua, agrupadas por día (*Hoy*, *Ayer*, *Esta semana* y luego fechas), con la hora exacta al pasar el ratón y en la vista previa. Las de colecciones y de la bolsa usan la fecha en que se añadieron a la librería (las antiguas sin fecha: la de modificación del archivo). Las de carpetas vigiladas usan la más reciente entre la modificación del archivo y la primera vez que se indexó. Una imagen usada en varios sitios sale una vez, con su fecha más nueva. Muestra los últimos 30 días (hasta 500 imágenes, y al menos una pantalla); *Ver más* amplía el periodo. Los filtros de búsqueda, etiquetas y colecciones funcionan dentro.
- **Examinar…** (1.4.2), en el panel *Añadir carpeta*, abre un selector de carpetas servido por el servidor de WanGP (corre en tu PC, así que puede listar tu disco): letras de unidad (o `/`), y como atajos Inicio, Imágenes y la carpeta de salidas de WanGP. Navega haciendo clic en las carpetas, con ruta de navegación y ↑, y ve las subcarpetas y cuántas imágenes tiene la carpeta actual. **Seleccionar esta carpeta** rellena la ruta y la añade (se respeta tu opción de *Incluir subcarpetas*). Solo lee el disco (`os.scandir`). Las carpetas sin permiso y las unidades lentas o desconectadas (4 s de espera máxima) muestran un aviso en vez de bloquearse. Escribir la ruta sigue funcionando.
- **Quitar y borrar (1.4.3)** funcionan con cualquier selección. Con un filtro de una colección activo, **Quitar de <colección>** saca las imágenes solo de esa colección (*Deshacer*; si una imagen sale de su última colección se queda en la bolsa). **Borrar de la librería** (dos clics; la confirmación dice cuántas imágenes y colecciones) las quita de todas las colecciones y de la bolsa, con *Deshacer* durante 15 min. Los archivos de carpetas vigiladas nunca se borran del disco: las imágenes solo de carpetas se omiten, y el tooltip del botón lo explica cuando no hay nada más seleccionado.
- **Selección (1.4.3):** arrastra un rectángulo sobre la cuadrícula (desde un hueco o una tarjeta, no su casilla; Ctrl/Cmd+arrastrar añade; se desplaza solo en los bordes), Mayús+clic para un rango desde la última tarjeta pulsada, Ctrl/Cmd+clic alterna una, Ctrl+A selecciona todo lo mostrado, Esc vacía la selección y un segundo Esc cierra.
- **Librerías grandes (1.4.4):** el explorador se abre al instante sea cual sea el tamaño. Carga los recuentos, el árbol y una página de 120 imágenes; filtros, búsqueda, Recientes y orden se resuelven en el servidor, y la cuadrícula es ventaneada (solo existen las tarjetas cerca de la vista). Las miniaturas se piden solo para tarjetas visibles (6 por petición, canceladas al desplazarse), salen de la caché en disco o las crea bajo demanda un proceso de baja prioridad (los JPEG 4K se decodifican reducidos; los originales enormes muestran un marcador). Ctrl+A y *Seleccionar las mostradas* significan **todas las N que coinciden**, sin cargarlas. Al abrir se revisan las carpetas en segundo plano como mucho cada 10 minutos (*Reescanear* lo fuerza), los archivos sin cambios nunca se vuelven a hashear, y la indexación se puede pausar desde la barra de progreso o los ajustes.
- **Árbol de carpetas** (barra lateral izquierda, 1.4.1): cada raíz vigilada, desplegable en sus subcarpetas como en el disco, con recuentos. Haz clic en una carpeta para filtrar; *Incluir subcarpetas* alterna entre todo el subárbol y solo esa carpeta. Una ruta de navegación encima de la cuadrícula muestra dónde estás; haz clic en un tramo o en ↑ para subir. El filtro de carpeta se combina con los de colección y etiquetas. Cada raíz tiene ⟳ (reescanear) y × (quitar, dos clics) al pasar el ratón. Las imágenes se **leen en su sitio**: nunca se copian, mueven, modifican ni borran (salvo si marcas *También borrar el archivo del disco*, 1.7.1: Papelera de reciclaje), así que no ocupan espacio extra. Se reescanean al abrir el modal y con **Reescanear** (los archivos sin cambios no se vuelven a hashear). Si un archivo se mueve o se borra, desaparece o reaparece en su nueva ruta; una carpeta que falta se marca. Al añadir una imagen de carpeta a una colección se **copia**, para que las colecciones sigan siendo autónomas. *Quitar* (dos clics) solo la quita del índice. Índice: `folders/index.json`; miniaturas en caché en `collections/.thumbs/`.
- **Añadir a referencias** (pie de la selección) añade solo las imágenes elegidas a Reference Images de WanGP, por el mismo camino que al aplicar una colección. Las que ya estén en la galería se saltan y nunca se sustituye nada. Las imágenes de carpetas se leen en su sitio; no se copian a ninguna colección. *Cerrar al añadir* cierra el modal después (se recuerda). Si el modelo actual no tiene Reference Images, sale un error.
- Haz clic en una imagen para verla en grande con sus colecciones, archivos y etiquetas. **Esc** o **×** cierran; las barras y el gestor se refrescan.

## Borrar de la librería, archivos que faltan (1.7.1)

- **Borrar de la librería** funciona con todas las entradas. Con archivos de carpetas vigiladas, vídeos/audios enlazados del disco y entradas cuyo archivo ya no existe, quita solo la entrada de la librería: metadatos, etiquetas, miniaturas/caché, copias en colecciones, máscaras y copias virtuales. **El archivo del disco no se borra ni se mueve.** La confirmación enumera lo que se quita y permite Deshacer. La carpeta recuerda los archivos quitados y los escaneos los saltan: **⊘n** en la carpeta del árbol → **Mostrar excluidos** → **Restaurar** / **Restaurar todos**.
- **También borrar el archivo del disco** (opcional en esa confirmación, desmarcado por defecto, solo si los archivos existen): los archivos de la lista van a la **Papelera de reciclaje** (shell de Windows; nunca un borrado definitivo). Las unidades de red y extraíbles se rechazan (no tienen Papelera). Si un archivo no se puede enviar a la Papelera, se conserva y el aviso lo nombra.
- **⚠ archivo no encontrado:** una marca en las tarjetas cuyo archivo ya no existe, un filtro en la barra de tipos y **Quitar todas las que faltan** (con confirmación).
- Las copias propias de la librería (colecciones, imágenes importadas) mantienen el borrado de dos clics.

## Librería de máscaras por vídeo (1.7.0)

Las máscaras que creas en **Video Mask** de WanGP (creador de máscaras / Matanyone, o subidas) se guardan en la librería **junto al Control Video para el que se hicieron**. Se enlazan por el contenido del vídeo (el mismo archivo cargado desde cualquier sitio es el mismo vídeo). Una copia virtual con recorte o entrada/salida tiene **sus propias** máscaras.

- **Guardar:** con **Guardar en la librería de máscaras las máscaras que creo en Video Mask** activado (Ajustes, activado por defecto), cada valor nuevo de Video Mask se guarda como máscara del Control Video actual. Si ese vídeo aún no está en la librería, se añade a la Librería de vídeos. Las generaciones que usaron Control Video y Video Mask también guardan su máscara, si el vídeo ya está en la librería. Junto a 📚 en la barra de Video Mask, **🎭 Guardar máscara** la guarda a mano. La misma máscara nunca se guarda dos veces para un vídeo.
- **Explorador:** la barra de tipos tiene **🎭 Máscaras** y un filtro **🎭 con máscara** (solo vídeos con máscaras). Las máscaras que solo están en la librería de máscaras no salen en Vídeos; un vídeo de la librería asignado como máscara sale en las dos. Las tarjetas de vídeo muestran **🎭n** y las de máscara una etiqueta **máscara**. Las máscaras tienen también una carpeta **🎭 Máscaras**.
- **Detalles de un vídeo:** **Máscaras (n)**, de la más nueva a la más antigua. Cada una tiene miniatura y vista previa ▶, fecha, tamaño, duración y origen, un nombre editable (Intro guarda), **Usar con máscara** y 🗑 (con Deshacer). Aparece un aviso ⚠ cuando la **duración o el tamaño** de la máscara no coinciden con los del vídeo (una copia virtual se compara con su tamaño recortado). Borrar una máscara **nunca borra el vídeo**.
- **Detalles de una máscara:** «Máscara de «vídeo»», **Usar con su vídeo**, **Mostrar vídeo**, **Asignar como máscara de…** y **Borrar**.
- **Usar con máscara** pone el vídeo en **Control Video** y la máscara en **Video Mask** en una sola acción. Usa la lógica de 1.6.9 (esperar → enviar → comprobar → reenviar), así que funciona aunque WanGP esté ocupado. Si el modelo actual oculta Video Mask, un aviso te pide elegir en Control Video una opción que use máscara.
- **Asignar como máscara de…** (clic derecho en un vídeo o una máscara, o desde los detalles de la máscara): elige el vídeo al que pertenece (doble clic, o **Asignar a este vídeo**; Esc cancela). El archivo se queda donde está.
- El botón de librería de Video Mask se abre en **Máscaras** (también se pueden elegir vídeos normales).

## Copias virtuales (1.6.6)

Una copia virtual es un recorte y/o una entrada/salida **que apunta a un archivo de la librería**, como las copias virtuales de Lightroom: no se duplica nada y el original nunca se modifica. Imágenes: un rectángulo. Vídeo: rectángulo y/o entrada/salida. Audio: entrada/salida. Se crea con **Nueva copia virtual** (clic derecho, Detalles, visor) y se cambia luego con **Editar recorte**. Se renderiza bajo demanda en `virtuals/.cache/` cuando algo necesita el archivo real (vista previa, referencias, librería de vídeos, redimensionar).

Las copias llevan la insignia **virtual** y aparecen en **Copias virtuales**. Detalles muestra **Original: …** con **Mostrar original**, y el original lista sus copias. Borrar una copia nunca borra el original. Si el original desaparece, la copia se marca como **rota** hasta que el archivo vuelva. Con **Media Editor 1.7.0+** (`fileApi >= 2`), el rectángulo de las imágenes se elige en el modo solo-rectángulo de Media Editor (`cropFile({mode:"rect", initialRect})`, sin generar archivos), y las copias de vídeo tienen un botón **✂ Recortar en Media Editor** para el encuadre. Los rectángulos van en píxeles con la orientación EXIF ya aplicada. Con un Media Editor anterior, sin él o si rechaza el archivo, se usa una herramienta de recorte propia. **1.6.7:** con Media Editor `fileApi >= 3`, las copias de vídeo y audio se recortan en su **modo trim** (entrada/salida y, en vídeo, el encuadre) en lugar de la línea de tiempo propia. Las grabaciones del navegador o la webcam (WebM de MediaRecorder) no guardan la duración en el archivo: se mide a partir de los paquetes y, si aun así no se puede leer, la entrada y la salida se pueden escribir en segundos. Tras recortar una entrada con Gradio, **Guardar en librería** ofrece **Copia virtual de «original»** cuando el archivo sin recortar está en la librería.

## Cargar medios de la librería en las entradas (1.6.8)

Cada entrada de vídeo y audio de WanGP (Control Video 1/2/3, Video to Continue, Video Mask, Voice to follow 1/2/3, Soundtrack, Voice Samples) tiene el icono de cuadrícula de la librería. Está arriba a la derecha si la entrada está vacía, o en su barra junto a 📚 si tiene un valor. El icono abre el explorador de medios filtrado a **Vídeos** (o **Audios**), con la carpeta **Librería de vídeos** y las copias virtuales. **Doble clic** sobre un elemento, o seleccionarlo y pulsar **Cargar en «entrada»**, lo carga en esa entrada. Una copia virtual carga su versión generada. Esc / Cancelar deja el explorador como estaba.

## Guardar entradas en la librería (1.6.4)

Cada entrada de audio y vídeo de WanGP (Control Video 1/2/3, Source Video, Video Mask, Audio 1/2/3, Source Audio, muestras de voz) tiene un botón **📚 Guardar en librería** en su barra mientras contiene un archivo. Guarda el valor **actual** de la entrada: recórtala antes con el ✂ de Gradio (vídeo) o la región de la onda (audio) y se guarda el recorte. El archivo se copia en el acto; el original no se toca nunca.

- **Vídeo** → Librería de vídeos. **Audio** → la carpeta gestionada **Audios guardados** (`saved_audio/` dentro del plugin), indexada sola en el explorador de medios.
- Los recortes se llaman `nombre (recorte)`; los duplicados se reconocen. El aviso tiene **Deshacer**.
- Gradio recorta el vídeo con ffmpeg.wasm en el navegador (se descarga de unpkg.com la primera vez). Si aún no está listo, Gradio deja el vídeo entero sin avisar; el botón lo detecta, lo guarda con su nombre normal y avisa. Espera un momento y vuelve a recortar.

## Redimensionar vídeos (1.6.2)

**⤡ Redimensionar** a 480p / 720p / 1080p (lado corto; se mantiene la proporción y el lado largo es múltiplo de 16) desde la barra del vídeo de control (sustituye la entrada y guarda el resultado en la Librería de vídeos) o desde el explorador de medios (clic derecho, Detalles, visor; se guarda en la Librería de vídeos). Nunca amplía sin preguntar, conserva el audio y no modifica el original. Usa NVENC si está disponible; si no, libx264 CRF 18. Los resultados se llaman `<nombre> (720p)`.

## Recortar desde el explorador (1.6.1)

**Recortar** (clic derecho, panel Detalles, visor) abre [Cropper](https://github.com/sweetyshots123/wan2gp-cropper) 1.5.0+ con la imagen o el vídeo seleccionado. Los recortes de imagen van a la colección «Recortes» y quedan seleccionados; los de vídeo, a la Librería de vídeos. Sin Cropper 1.5.0 el botón aparece desactivado.

## Explorador de medios: fotos, vídeos y audios (1.6.0)

Las carpetas vigiladas e Importar indexan imágenes, **vídeos** (mp4, mov, webm, mkv, avi) y **audios** (wav, mp3, flac, ogg, m4a, aac, opus). Los botones **Todo / Fotos / Vídeos / Audios** de la cabecera (con recuentos) filtran por tipo. Las tarjetas de audio muestran la forma de onda y la duración con ▶ para escuchar; las de vídeo, un fotograma, la duración y una vista previa al pasar el ratón. Doble clic reproduce el archivo en el visor a pantalla completa; Detalles incluye un reproductor y los datos del códec. **Añadir a** solo ofrece lo que acepta el modelo actual: imágenes → Imágenes de referencia, un vídeo → Vídeo de control o la Librería de vídeos, un audio → las entradas de audio del modelo. El autoetiquetado solo procesa imágenes. Usa ffmpeg/ffprobe (incluidos con WanGP) para las ondas y duraciones.

## Navegar: selector de vista y visor (1.5.9)

Un clic selecciona (Ctrl/Mayús como siempre) sin abrir nada. El selector de vista de la cabecera cambia el tamaño de las miniaturas (muy grandes / medianas / pequeñas) y activa **Detalles**, el panel derecho con la información y las acciones de la imagen seleccionada; ambos se recuerdan. **Doble clic** abre un visor a pantalla completa: ←/→ recorren los resultados actuales, **Ajustar** / **1:1** (teclas 0 / 1), Esc cierra. Con clic derecho en una miniatura tienes «Abrir en el Explorador», «Localizar carpeta», «Vista grande» y «Ver detalles».

## Historial de generaciones (1.5.5)

Cada generación de WanGP queda registrada: imágenes de referencia, imágenes de inicio/final, vídeo de control, máscaras, prompt, todos los ajustes y la ruta del vídeo (capturado con el hook `before_metadata_save` de plugins; no se modifica nada de WanGP). Ábrelo con **🕘 Historial** en la cabecera del explorador o con el botón 🕘 junto al botón del explorador.

- **Reutilizar todos los ajustes**: usa el cargador propio de WanGP ("Load Settings From Media File / Json") para modelo, prompt, resolución, pasos…, **nunca la semilla** (queda aleatoria, -1; 1.6.5), y luego repone refs, vídeo de control, máscaras e imágenes de inicio/final. También sirve para vídeos de la carpeta de salida de WanGP sin entrada en el historial (WanGP lee los metadatos incrustados en el archivo).
- **Reutilizar solo referencias** (añade; marca "Reemplazar" para sustituir) y **Guardar refs como colección**.
- Almacenamiento: deduplicado por hash; solo se copian las imágenes en memoria y las subidas temporales (`history/blobs`), los archivos estables se referencian. Tamaño máximo (2048 MB por defecto) y borrar con deshacer.
- **Borrar (1.5.6)**: selecciona entradas (clic / Ctrl / Mayús) y "Borrar seleccionadas", o usa **Borrar…** (última hora, últimas 24 h, últimos 7 días, todo, rango de fechas). Siempre con confirmación y recuento, y con deshacer. Solo se eliminan registros y copias hechas por el historial que nadie más usa; nunca los vídeos generados ni los originales. El mismo menú está en "Usadas como referencia" (las imágenes siguen en la librería).
- Limitaciones: se registran las generaciones desde la 1.5.5; si mueves un original referenciado, esa entrada no se puede reponer; inicio/final y máscaras se reponen solo si WanGP los muestra como entradas simples de imagen/vídeo; si cambia el modelo, la reposición de medios se hace ~3,5 s después de la carga de WanGP.

La vista **Usadas como referencia** (columna izquierda, bajo Recientes) lista todas las imágenes que han entrado alguna vez en Reference Images, de cualquier origen, sin duplicados (por hash), con fecha de último uso y número de usos, agrupadas por día. Las que no estaban en la librería (subidas, Dragger) se añaden al pool ("Sin colección"). Puedes quitar entradas (seleccionadas o todas) sin tocar las imágenes.

El botón ⛶ junto a la X del explorador pasa a pantalla completa (más columnas); para que sea lo predeterminado, activa "Abrir siempre a pantalla completa" en los ajustes de Reference Library.

Bajo el reproductor de vídeos generados de WanGP hay una pequeña barra con **Reutilizar ajustes** y **Solo referencias** para el vídeo mostrado (entrada del historial si existe; si no, los metadatos incrustados en el archivo). Va debajo del reproductor y no tiene atajos, así que no interfiere con Vidosser.

Cuando los ajustes vienen de una entrada del historial, su imagen de inicio, imágenes de referencia, voz y medios de control se vuelven a poner cuando WanGP termina de cargar los ajustes y refrescar el formulario, incluso mientras genera. Después se comprueban y se reenvían si WanGP los vació (1.6.9). La semilla nunca se copia: queda aleatoria (-1).

**La semilla nunca se reutiliza (1.6.5).** Todas las formas de reutilizar ajustes (barra del reproductor, historial, lista de salidas, `history_settings_file()` de la API) dejan la semilla aleatoria (`-1`). La semilla se pone a -1 en los ajustes que se pasan al cargador de WanGP, y el campo Seed del formulario de generación se mantiene en -1 unos segundos tras la carga (un vídeo generado que se pasa como archivo lleva su semilla en los metadatos). Si tocas tú el campo Seed, se deja de forzar. El historial sigue guardando la semilla que se usó.

La búsqueda del explorador también encuentra nombres y rutas de carpetas vigiladas y subcarpetas; el autocompletado sugiere carpetas (📁) y al elegir una se selecciona en el árbol.

## Modelos de pago en la nube (1.5.3)

Opcionales y **apagados por defecto**: elige el modelo en el ⚙ del autoetiquetado *y* marca su casilla "Activar". Las claves
salen de `GEMINI_API_KEY` / `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` o de los campos ocultos de ajustes (nunca se registran). Los ids son editables.

| Modelo | Id (verificado 11-10-2026) | Precio por defecto, USD / 1M tokens (entrada · salida · caché) | Notas |
| --- | --- | --- | --- |
| Gemini 3.8 Flash (recomendado) | `gemini-3.8-flash` | 0,75 · 3,75 · 0,075 | Esquema JSON, filtros en BLOCK_NONE, caché de contexto, modo lote opcional (−50 %). **Google duplica el precio el 1-1-2027.** |
| GPT-6.1 Sol | `gpt-6.1-sol` | 2 · 10 · 0,10 | `json_schema` estricto, caché del prompt, modo lote opcional (−50 %). |
| Claude Opus 5.5 | `claude-opus-5-5` | 4 · 20 · 0,20 | **solo fotos vestidas**; JSON por herramienta + caché. |
| Claude Sonnet 5.5 | `claude-sonnet-5-5` | 2 · 10 · 0,10 | **solo fotos vestidas**; igual que Opus. |

Reglas para todos: las fotos marcadas «Revisión › contenido explícito» o «parece menor de edad» (o en revisión) **nunca se
suben** y se etiquetan en local; las fotos sin etiquetas pasan antes por el etiquetador rápido local. A Claude solo van fotos
con cobertura *vestida* sin etiquetas de semidesnudo, desnudo, topless, lencería o bañador; el resto va a local con una nota.
Los rechazos van a local por imagen y se cuentan. Se envían a 1024 px y sin EXIF/GPS. Antes de empezar, un diálogo muestra
los tokens (imagen, prompt con y sin caché, ~500 de salida, descuento por lote) y el coste estimado; al terminar, el coste real.

Políticas (léelas antes de enviar desnudos):
- **Google Gemini API** — plan de pago: no entrena, guarda ~55 días por abusos; el filtro sexual se puede bajar, lo sexual con menores siempre se bloquea. [Términos](https://ai.google.dev/gemini-api/terms) · [Uso](https://policies.google.com/terms/generative-ai/use-policy)
- **OpenAI API** — no entrena por defecto, guarda hasta 30 días; puede rechazar contenido sexual adulto; subir desnudos en masa puede suspender la cuenta. [Privacidad](https://openai.com/enterprise-privacy/) · [Uso](https://openai.com/policies/usage-policies/)
- **Anthropic API** — no entrena, borra en 30 días (más si se marca); prohíbe el contenido sexual, por eso solo vestidas. [Privacidad](https://privacy.anthropic.com/) · [Uso](https://www.anthropic.com/legal/aup)

## Clics en el navegador, Abrir en el Explorador, etiquetas anidadas (1.5.2)

- **Estado del etiquetado** (1.5.4): insignia por tarjeta (en cola / procesando / hecha / falló / local), faceta «Estado del etiquetado» y contadores clicables en la barra del trabajo; «Reintentar fallidas» vuelve a poner en cola las fallidas (se guardan en `job_status.json`).

- **Localizar carpeta** (1.5.3): botón en la vista previa y clic derecho → el árbol se abre en la subcarpeta de la imagen, la cuadrícula se filtra y se desplaza hasta ella; la vista previa muestra la ruta como migas clicables. Las imágenes de colección resaltan su colección.
- Un clic normal en una imagen ya seleccionada mantiene la selección múltiple (1.5.3).

- Un clic selecciona una imagen y la muestra; Ctrl+clic alterna, Mayús+clic selecciona un rango, doble clic abre la vista grande y un clic en un hueco vacío quita la selección.
- Clic derecho en una tarjeta (o el botón de la vista previa) para **Abrir en el Explorador**. Solo funciona si el navegador está en el PC de WanGP.
- **Mis etiquetas** es un árbol: crea categorías propias de primer nivel, subcategorías a cualquier profundidad (también dentro de las de serie) y etiquetas en cualquier nivel. Arrastra para mover y todo se puede deshacer.
- Las imágenes en las que un modelo detecta actividad sexual explícita reciben solo la marca **Revisión › contenido explícito** y ninguna medida corporal, para que puedas encontrarlas y quitarlas.

## Exportar / importar tu taxonomía (1.5.8)

En **Ajustes del autoetiquetado › Mis etiquetas**: **Exportar taxonomía** descarga la taxonomía completa (de serie + tuya, bilingüe, con sinónimos) o solo la tuya, en JSON o CSV (`path, es, en, synonyms`). **Importar…** acepta un JSON exportado (o un `user_taxonomy.json`) y lo combina o reemplaza tus nodos. Cada nodo pasa las mismas comprobaciones y lista de bloqueo que el editor; los rechazados se listan con el motivo. Primero confirmas los recuentos y puedes deshacer. Tus etiquetas se guardan en `user_taxonomy.json`, en la carpeta del plugin (`plugins/wan2gp-reference-library/`).

## Filtros, autocompletado y etiquetas propias (1.5.1)

- **Chips de filtros activos** bajo el buscador: todos los filtros de un vistazo. × quita uno y "Quitar todos" los quita todos. Al pulsar un chip de etiqueta automática, se localiza en el árbol, y = / ≠ alterna entre incluir y excluir. Las etiquetas de un mismo grupo se combinan con "o", y las de grupos distintos con "y".
- **Autocompletado**: escribe "sen" y sale "Pose › sentada" con su número de imágenes. ↑/↓ y Enter/Tab la añaden como chip, y Esc cierra la lista.
- **Edad aparente (estimada)**: franjas de 18–24 a 65+ y una estimación con ±, solo para adultos; se busca con `edad 30-40`.
- **Mis etiquetas**: en los ajustes del autoetiquetado (⚙), "Mis etiquetas" crea grupos y etiquetas propios con sinónimos. Se guardan en `user_taxonomy.json` y se conservan al actualizar. Se añaden a una imagen desde la vista previa y funcionan en las facetas, los chips, la búsqueda y el autocompletado. Se rechazan las etiquetas de anatomía sexual o referidas a menores.

## Autoetiquetado (1.5.0)

Selecciona imágenes en el explorador y pulsa **Autoetiquetar** (Ctrl+A = todas las que coinciden). Un trabajo en
segundo plano las etiqueta con un modelo local (por defecto: tagger WD-EVA02 + Qwen2.5-VL-7B, más un análisis de la
forma del cuerpo); espera mientras WanGP genera, libera la GPU, se puede pausar o cancelar y descarga los modelos en
reposo o con **Liberar GPU**. Después:

- busca por cualquier etiqueta, sus sinónimos y sus términos padre / hijo en español o inglés ("arena", "pelo
  corto", "curvilínea"); búsquedas numéricas como `cintura<65`, `90-60-90 ±5`, `ratio cintura/cadera<0.72`,
  `cadera:media`;
- el panel **Etiquetas automáticas** de la barra lateral muestra las categorías con recuentos (clic para filtrar) y
  filtros por rango de los valores corporales estimados;
- la vista previa muestra cada etiqueta con su confianza y origen (✓ aceptar, × quitar, ↺ restaurar; tus cambios se
  conservan al repetir) y un panel **Forma del cuerpo**: bandas estimadas de pecho / cintura / cadera / muslo en cm,
  proporciones, definición de cintura, curvatura y anchuras de la silueta, todo marcado como *estimado*, más un campo
  de altura (por imagen o para la colección) que las reescala;
- solo se vuelven a etiquetar las imágenes nuevas o cambiadas; las etiquetas automáticas se guardan aparte de las
  manuales (`autotags.json`).

Solo adultos: si el modelo cree que la persona podría ser menor de 18, la imagen no guarda etiquetas corporales ni
de desnudez y queda marcada para revisar. Hay clasificadores en la nube (compatibles con OpenAI, Gemini, Grok,
OpenRouter Jev) pero están desactivados por defecto. Detalles (taxonomía, comparación de modelos, método y límites de
las medidas, nube, instalación): **[AUTOTAG.md](AUTOTAG.md)** (en inglés).

## Instalar

1. En WanGP → **Plugins** → pega la URL del repo e instala, **o** descomprime un release en `Wan2GP/plugins/wan2gp-reference-library/`.
2. Activa **Reference Library**, pulsa **Restart** y recarga la página.
3. Abre un modelo que muestre **Referencias**. La barra aparece debajo de esa galería. La barra de vídeos aparece bajo **Vídeo de control** (Control Video) al elegir un modo con vídeo de control.

## Idioma

Inglés y español. **Auto** sigue el idioma del navegador y traduce la barra y la pestaña en cuanto carga la página (y otra vez al guardar Language / Idioma). No hace falta reiniciar WanGP.

## Ajustes

| Ajuste | Por defecto | Significado |
|---|---|---|
| Al cargar una colección | Sustituir | Sustituir las referencias actuales, o añadir |
| Aplicar automáticamente al elegir | Sí | Al elegir una colección o un vídeo en las barras se carga al momento |
| Mostrar también las barras en Edit | Sí | Formulario Edit de la cola |
| Mostrar la barra de vídeos bajo Vídeo de control | Sí | La barra de la librería de vídeos |
| Recortes de imágenes hechos con Cropper | Guardar automáticamente | *Guardar en la colección «Recortes» automáticamente* / *Preguntar cada vez* / *No guardar*. Imágenes de inicio/fin, referencias y control; nunca dos veces en una colección. |
| Recortes hechos con Cropper (vídeos) | Guardar automáticamente | *Guardar en la librería de vídeos automáticamente* / *Preguntar cada vez* (aviso con botón Guardar) / *No guardar*. El mismo recorte nunca se guarda dos veces. |
| Mensajes de confirmación | Sí | Avisos al cargar/guardar (los errores siempre) |
| Language / Idioma | Auto | Auto / English / Español |
| Prompts asociados al cargar una colección | Ofrecerlos | *Ofrecerlos* (chips bajo la barra) / *Aplicar automáticamente el primer prompt asociado* / *No hacer nada*. Solo aparece con Prompt Library 1.1+ instalado. |

## Integración con Prompt Library

Con [Prompt Library](https://github.com/sweetyshots123/wan2gp-prompt-library) **1.1 o posterior** instalado y activado, las colecciones y los prompts se pueden asociar en los dos sentidos. Cada plugin sigue funcionando por separado. Sin Prompt Library (o con una versión anterior) no se muestra nada de esto.

- **Pestaña de gestión:** bajo la colección aparece **Prompts asociados (Prompt Library)**, un selector múltiple con los títulos de los prompts de Prompt Library. Marca los que van con la colección y pulsa **Guardar vínculos**. Prompt Library muestra el mismo vínculo desde su lado (su selector *Colecciones*); si lo cambias allí, este selector se actualiza solo.
- **Barra:** al cargar una colección con prompts asociados aparece una fila pequeña **Prompts: …** bajo la barra. Pulsa un chip para poner ese prompt en el cuadro de prompt de WanGP (lo inserta Prompt Library, que pide las variables de la plantilla si las tiene).
- **Tu prompt nunca se sustituye sin avisar.** Con *Ofrecerlos* (por defecto), el cuadro de prompt solo cambia cuando pulsas un chip. *Aplicar automáticamente el primer prompt asociado* hay que activarlo a propósito.
- **Dónde se guardan los vínculos:** solo en el `library.json` de Prompt Library (`collections: [ids de colección]` en cada prompt). Reference Library no guarda ningún vínculo. Borrar una colección no toca Prompt Library; si deshaces el borrado, los vínculos vuelven.

## Integración: Cropper y otros plugins

Reference Library no importa otros plugins y ellos no necesitan importarlo. Todo pasa por un módulo registrado en `sys.modules` (se busca en el momento de usarlo, porque el orden de carga de los plugins no está garantizado) o por eventos en `window`. Si Reference Library no está instalado o activado, la búsqueda devuelve `None` y el otro plugin simplemente no hace la llamada.

**Cropper → librería de vídeos.** Cuando Cropper aplica un recorte a una entrada de vídeo, puede entregar el resultado:

```python
import hashlib, sys

def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

def _offer_to_reference_library(out, src, spec, name):
    api = sys.modules.get("wan2gp_reference_library_api")      # en el momento, nunca al importar
    if api is None or getattr(api, "API_VERSION", 0) < 2:
        return None                                            # no instalado / versión antigua: nada que hacer
    try:
        return api.add_video(out, name=name, source="cropper", meta={
            "crop": [spec["x"], spec["y"], spec["w"], spec["h"]],
            "out": [spec["out_w"], spec["out_h"]],
            "source_file": src,
            "dedupe_key": f"{_sha256(src)}|{spec['x']},{spec['y']},{spec['w']},{spec['h']}|{spec['out_w']}x{spec['out_h']}",
        })
    except Exception:
        return None                                            # la librería nunca debe romper un recorte
```

- Llámalo justo después de escribir el archivo recortado y antes de devolver las actualizaciones a Gradio. Solo para salidas de vídeo. No para la máscara recortada (`video_mask`) ni al deshacer.
- `add_video` copia el archivo a `videos/` (Cropper puede limpiar sus temporales después) y **nunca lanza excepciones**. Devuelve el id del vídeo nuevo o existente, o `None` (ajuste *No guardar*, *Preguntar cada vez*, o archivo ilegible).
- Reference Library aplica el ajuste del usuario **Recortes hechos con Cropper** (*Guardar automáticamente* / *Preguntar cada vez* / *No guardar*), muestra el aviso en el idioma de la interfaz cuando el recorte llega a la entrada, lo selecciona en la barra de vídeos y evita duplicados (mismos bytes, o mismo `meta["dedupe_key"]`). Cropper no necesita JS para esto.
- Sin el gancho en Python, el camino JS hace lo mismo: `window.dispatchEvent(new CustomEvent("reflib:video-add", {detail: {path, name, source: "cropper", meta}}))`.

**Cropper → recortes de imágenes (API v3, Reference Library 1.3).** Cropper 1.2 también recorta las imágenes de inicio/fin, las Referencias y la imagen de control. Entrega cada resultado igual:

```python
def _offer_image_to_reference_library(out, src, spec, name, target):
    api = sys.modules.get("wan2gp_reference_library_api")      # en el momento, nunca al importar
    if api is None or getattr(api, "API_VERSION", 0) < 3:
        return None                                            # no instalado / anterior a 1.3: nada que hacer
    try:
        return api.add_image(out, name=name, source="cropper", meta={
            "crop": [spec["x"], spec["y"], spec["w"], spec["h"]],
            "target": target,                                  # "image_start" / "image_end" / "image_refs" / "image_guide"
            "source_file": src,
            "dedupe_key": f"{_sha256(src)}|{spec['x']},{spec['y']},{spec['w']},{spec['h']}|{spec['out_w']}x{spec['out_h']}",
        })                                                     # collection_id=None -> la colección «Recortes»
    except Exception:
        return None
```

- **Dónde van las imágenes.** A `collection_id` si es una colección existente; si no, a una colección automática **«Recortes» / «Crops»**, que se crea al primer uso con el nombre en el idioma de la interfaz («Recortes 2» si ya tienes una «Recortes»). Se recuerda su id, así que puedes renombrarla. *¿Por qué no la colección cargada en la barra?* Esa colección la cuida el usuario y puede estar cargada para otra cosa; meterle recortes sin avisar la cambiaría a sus espaldas, y al volver a aplicarla se cargarían también los recortes. Un sitio fijo es más fácil de encontrar y de limpiar. Cropper (o una opción futura) puede indicar una colección explícitamente.
- `add_image` copia el archivo y **nunca lanza excepciones**. Devuelve `{collection_id, collection_name, file, path, created}` (`created=False` si esa colección ya la tenía) o `None` (*No guardar*, *Preguntar cada vez*, o no es una imagen).
- Sigue su **propio** ajuste **Recortes de imágenes hechos con Cropper** (*Guardar en la colección «Recortes» automáticamente* / *Preguntar cada vez* / *No guardar*), aparte del de vídeos. El aviso (con el botón **Guardar en la colección** en modo *Preguntar*) sale cuando la imagen recortada llega a una de las entradas de imagen. La imagen de control es una imagen PIL sin nombre de archivo; ahí se usa el aviso de recorte más reciente (< 20 s).
- **Duplicados:** nunca dos veces en la misma colección: mismos bytes (sha256) o mismo `meta["dedupe_key"]`. Las colecciones en la papelera de deshacer no cuentan. **Tiene en cuenta Deshacer:** si borras la colección «Recortes», recortas otra vez (se crea una nueva) y luego **Deshaces** el borrado, la nueva se vuelca en la restaurada (sin duplicados) y se elimina, y un aviso dice cuántos recortes se han pasado.

**API de Python** (`sys.modules["wan2gp_reference_library_api"]`, **`API_VERSION` 6**; comprueba `>= 1` si solo usas colecciones, `>= 2` para vídeos, `>= 3` para `add_image`, `>= 4` para `list_images` / etiquetas, `>= 5` para el historial de generaciones y `>= 6` para las máscaras, más abajo):

| Función | Devuelve |
|---|---|
| `API_VERSION` | `6` (las funciones de la v1 a la v5 no cambian) |
| `list_collections()` | `[{id, name, count, cover_path o None, updated}]`, ordenadas por nombre |
| `get_collection(cid)` | `{id, name, count, cover_path, updated, created, images: [rutas absolutas]}` o `None` |
| `image_paths(cid)` | rutas absolutas de las imágenes en el orden de la colección; `[]` si no existe |
| `list_videos()` | `[{id, name, path, poster_path, width, height, fps, frames, duration, size, source, meta, created, updated}]` en el orden de la librería |
| `get_video(vid)` | el mismo diccionario, o `None` (desconocido o en la papelera de deshacer) |
| `video_path(vid)` | ruta absoluta del archivo guardado (solo lectura), o `None` |
| `add_image(path, name=None, source="cropper", meta=None, collection_id=None)` | `{collection_id, collection_name, file, path, created}` o `None`; nunca lanza excepciones. Colección indicada o la colección automática «Recortes»; con `source="cropper"` sigue el ajuste de recortes de imágenes; sin duplicados por colección (sha256 y `meta["dedupe_key"]`). |
| `list_images(tag=None, collection_id=None, unassigned=False)` | (v4) `[{hash, name, names, path, collections: [{id, name}], tags, unassigned, folders: [{id, path}]}]`, one per content; filters by tag (case/accent-insensitive), collection or unassigned pool. `path` is read-only (it can be a file in a watched folder). Never raises. |
| `list_tags()` / `image_tags(sha256)` | (v4) `[{tag, count}]` / `["tag", …]` |
| `image_crop_policy()` / `crop_policy()` | `"auto"`, `"ask"` o `"off"` (imágenes / vídeos) |
| `add_video(path, name=None, source="cropper", meta=None)` | id del vídeo o `None`; nunca lanza excepciones. `source="cropper"` sigue el ajuste de recortes; cualquier otro origen siempre guarda. `name` por defecto es el nombre del archivo. `meta` es un diccionario pequeño serializable a JSON (≤ 4 KB) que se guarda con la entrada. |

**API de máscaras (API v6, Reference Library 1.7.0).** Solo lectura, nunca lanza excepciones y devuelve copias.

| Función | Devuelve |
|---|---|
| `list_masks(video_path) -> list[dict]` | las máscaras guardadas para ese vídeo (cualquier copia del mismo archivo), de la más nueva a la más antigua: `[{id, label, path, video, video_name, w, h, dur, created, source}]`; `[]` si no se conoce |
| `get_mask(mask_id) -> dict \| None` | una máscara (misma forma), o `None` |
| `mask_path(mask_id) -> str \| None` | ruta absoluta del archivo de la máscara (solo lectura), o `None` |

**API del historial de generaciones (API v5, Reference Library 1.6.3).** Acceso de solo lectura al historial de generaciones y un aviso tras cada generación guardada. Ninguna función **lanza excepciones** (los errores se imprimen y el resultado es `None` / `False` / `[]`) y todas devuelven **copias**: cambiarlas no cambia nada en la librería. Todas las rutas son **absolutas**; una ruta es `None` si ese archivo ya no existe.

| Función | Devuelve |
|---|---|
| `get_history_entry(eid: str) -> dict \| None` | la entrada (forma abajo), o `None` |
| `find_history_by_output(path) -> dict \| None` | la entrada que generó ese archivo de salida (ruta exacta, si no mismo nombre de archivo), o `None` |
| `latest_history_entry() -> dict \| None` | la entrada más reciente, o `None` si el historial está vacío |
| `history_settings_file(eid=None, video=None) -> str \| None` | un JSON de ajustes para *Load Settings From Media File / Json* de WanGP, de la entrada `eid` o del vídeo de salida `video` (su entrada, si no los metadatos incrustados en el archivo). Se escribe en la carpeta temporal. La semilla en él es siempre `-1` (1.6.5). |
| `on_history_entry(callback) -> str \| None` | token (`None` si `callback` no es invocable). `callback(entry)` se llama justo después de guardar una entrada, con `"updated": True` cuando una continuación de ventana deslizante actualizó la entrada anterior (mismo `id`) en vez de añadir una. Cada callback recibe su propia copia y va en su propio `try/except`: una excepción se imprime y nunca rompe la captura ni a los demás callbacks. Se llama de forma síncrona en el hilo de guardado de WanGP; pasa el trabajo pesado a otro hilo. |
| `off_history_entry(token) -> bool` | `True` si se quitó ese listener |
| `media_fields() -> list[str]` | los campos de entrada que se guardan en `media`: `image_refs, image_start, image_end, video_guide, video_mask, image_mask, image_guide, video_source, audio_guide, audio_guide2, audio_guide3` |

Forma de una entrada (`updated` solo en lo que recibe `on_history_entry`):

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

- `settings` son los ajustes de WanGP tal como se guardaron en los metadatos de la salida, y siempre incluyen **`image_prompt_type`**, **`keep_frames_video_source`** y **`sliding_window_overlap`**. La limpieza de metadatos de WanGP puede quitarlos (por ejemplo `keep_frames_video_source` si no se usa vídeo de origen), así que también se toman de los valores de la propia generación de WanGP. Si existen ambos, gana el de los metadatos. Valen `None` si no se conocen, p. ej. en entradas guardadas antes de la 1.6.3.
- **`video_source`** es el vídeo de origen que WanGP usó realmente, como ruta absoluta. En el **modo "L"** (*Continuar el último vídeo*) WanGP lo resuelve a la salida anterior antes de generar, y es esa ruta resuelta la que se guarda, así que `find_history_by_output(entry["video_source"])` da la toma anterior. Apunta al archivo original si sigue existiendo; si no, a la copia guardada en el historial; si tampoco, `None`. `video_source_original` es la ruta guardada aunque el archivo ya no exista (`None` en entradas antiguas).
- Las rutas de `media` apuntan a las copias guardadas en el historial (`history/blobs`) o, para entradas grandes que solo se referencian, al archivo original.

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

Los ids son `uuid4().hex` y no cambian al renombrar. Reference Library usa `sys.modules["wan2gp_prompt_library_api"]` del mismo modo (`list_prompts()`, `prompts_for_collection(cid)`, `set_collection_prompts(cid, prompt_ids)`). Prompt Library 1.1.0 solo aceptaba `API_VERSION == 1` y oculta sus vínculos con Reference Library 1.2.0; usa Prompt Library 1.2 o posterior.

**Eventos JS** (en `window`):

| Evento | Sentido | Detalle |
|---|---|---|
| `reflib:apply` | escucha | `{id, mode?: "replace" \| "append"}`: selecciona la colección en la barra del generador y la carga en Referencias, con aviso. |
| `reflib:applied` | emite | `{id, name, count, tab}` después de cargar una colección. |
| `reflib:video-add` | escucha | `{path, name?, source?, meta?}`: añade un archivo de vídeo (mismas reglas que `add_video`). |
| `reflib:video-apply` | escucha | `{id}`: carga ese vídeo en Vídeo de control y lo selecciona en la barra de vídeos. |
| `reflib:video-applied` | emite | `{id, name, tab}` después de cargar un vídeo. |
| `reflib:changed` | emite | `{reason, id}` tras cualquier cambio. Colecciones: `create`, `rename`, `delete`, `images`, `restore`, `duplicate`. Vídeos (con `kind: "video"`): `video-added`, `video-renamed`, `video-deleted`, `video-restored`. |
| `promptlib:apply` | lanza | `{id, source: "reference-library", collection_id, tab, auto}` al pulsar un chip de prompt. |
| `promptlib:changed` | escucha | Actualiza el selector *Prompts asociados* y los chips. |

`window.referenceLibrary.version` da la versión del plugin.

## Datos

```
plugins/wan2gp-reference-library/
  plugin.py, storage.py, videostore.py, imagestore.py, media.py, api.py, promptlink.py, reference_library.js, reference_library.css
  settings.json          # tus preferencias (no va en el zip)
  collections/
    collections.json
    tags.json            # image tags by sha256 (1.4)
    .thumbs/             # cached thumbnails (1.4)
    .crops.json          # id de la colección automática «Recortes» (1.3)
    <id>/
      <sha256>.png
  pool/                  # unassigned images (1.4): pool.json + <sha256>.<ext>, .trash/
  folders/
    index.json           # watched folders + file index (files stay where they are) (1.4)
  saved_audio/           # «Audios guardados» (1.6.4): audios guardados desde las entradas de WanGP, carpeta vigilada gestionada
  virtuals/              # copias virtuales (1.6.6): virtuals.json (parámetros) + .cache/ (renders, se puede borrar)
  masks/                 # librería de máscaras (1.7.0): masks.json (máscara -> clave del vídeo, nombre, datos) + <id>/<archivo>, .trash/
  videos/
    videos.json          # índice (orden, nombres, datos, origen, meta)
    <id>/
      video.mp4          # vídeo copiado (extensión original)
      poster.jpg
    .trash/              # vídeos borrados: se pueden recuperar 5 min, se eliminan a los 15 min
```

`settings.json`, `collections/`, `videos/`, `saved_audio/`, `virtuals/` y `masks/` están en .gitignore y no van en los zips. Los ajustes nuevos se añaden desde los valores por defecto; los datos existentes nunca se migran.

## Uso independiente (reflib_core)

Todo lo que no es interfaz de WanGP está en `reflib_core/` (colecciones, bolsa, carpetas vigiladas, índice,
miniaturas, vídeos, etiquetas manuales y automáticas, Recientes, búsqueda, la API, el etiquetador y la cola). No
importa Gradio ni WanGP, tiene su `requirements.txt`, un formato de datos documentado y versionado
(`reflib_core/FORMAT.md`) y una CLI: `python -m reflib_core --data DIR tag <carpeta>` / `search "<consulta>"`. Una app
independiente llama a `reflib_core.configure(carpeta_de_datos)` y usa los mismos módulos.

## Convivencia

Funciona junto a [Dragger](https://github.com/sweetyshots123/wan2gp-dragger), [Vidosser](https://github.com/sweetyshots123/wan2gp-vidosser), [Prompt Library](https://github.com/sweetyshots123/wan2gp-prompt-library) (1.2+) y [Cropper](https://github.com/sweetyshots123/wan2gp-cropper). Namespaces aparte. El arrastrar/pegar y la X de Dragger siguen funcionando sobre las imágenes cargadas desde una colección.

## Regla

Solo plugin: no modifica archivos del núcleo de Wan2GP.

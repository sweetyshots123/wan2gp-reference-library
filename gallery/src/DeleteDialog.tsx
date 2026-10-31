// 1.8.6: la misma confirmación de borrado que la Media Library (reference_library.js fgOpen): el plan lo calcula el
// servidor (forget_plan -> reflib_core.forget.plan) y se ejecuta con las mismas acciones (forget / delete_all) y
// las mismas opciones (delete_files = a la Papelera). Textos copiados de la tabla FGT.es del explorador.
import { useEffect, useState } from "react";
import { call } from "./api";
import { act } from "./actions";

const T = {
  title: "Borrar de la librería",
  lead: "Se quitarán {n} elemento(s) de la Reference Library. Se elimina:",
  l_entry: "la entrada de la librería: nombre, metadatos, miniaturas y caché", l_tags: "las etiquetas de {k} elemento(s)",
  l_cols: "{k} copia(s) en colecciones ({c} colección(es))", l_masks: "{k} máscara(s)", l_virt: "{k} copia(s) virtual(es)",
  l_missing: "{k} entrada(s) cuyo archivo ya no existe", l_owned: "{k} copia(s) propias de la librería (se borran como siempre)",
  l_vlib: "{k} vídeo(s) de la Video Library (“Librería de vídeos”): se borran también allí",
  vlib_bin: "Los archivos de la Video Library van a la Papelera de reciclaje cuando acaba el plazo para deshacer (15 min). Hasta entonces, Deshacer los recupera.",
  l_folders: "De: {list}", l_offline: "⚠ Carpeta no disponible (¿disco desconectado?): {list}. Sus entradas cuentan como que faltan.",
  safe: "Los archivos del disco NO se borran ni se mueven.", safe2: "Se quedan donde están y un nuevo escaneo no los volverá a añadir (“Mostrar excluidos” en la carpeta los restaura). Se puede deshacer.",
  disk: "También borrar el archivo del disco", disk_n: "Si lo marcas, estos {k} archivo(s) irán a la Papelera de reciclaje (nunca un borrado definitivo):",
  disk_more: "… y {k} más", disk_fail: "Si un archivo no se puede enviar a la Papelera, se conserva y se te avisa.",
  disk_on: "Los {k} archivo(s) de la lista irán a la Papelera de reciclaje. Deshacer recupera las entradas, no los archivos (esos se recuperan desde la Papelera).",
  cancel: "Cancelar", go: "Borrar de la librería", go_disk: "Borrar y enviar {k} archivo(s) a la Papelera", loading: "Cargando…",
} as const;
const t = (k: keyof typeof T, p: Record<string, any> = {}) => T[k].replace(/\{(\w+)\}/g, (_, n) => String(p[n] ?? ""));

// Igual que el botón "del" del explorador: con entradas "olvidables" (carpetas vigiladas, Video Library, faltan)
// abre el diálogo; si todo son copias propias de la librería, delete_all directo con Deshacer.
export async function startDelete(hashes: string[], open: (plan: any) => void, after: () => void) {
  const r = await call("forget_plan", { hashes });
  const p = r?.plan;
  if (p && p.n > 0) open(p);
  else await act("delete_all", { hashes }, after);
}

export default function DeleteDialog({ plan: p, hashes, close, after }: { plan: any; hashes: string[]; close: () => void; after: () => void }) {
  const [disk, setDisk] = useState(false);
  useEffect(() => { const k = (e: KeyboardEvent) => { if (e.key === "Escape") close(); }; window.addEventListener("keydown", k); return () => window.removeEventListener("keydown", k); }, [close]);
  const files: string[] = p.disk_files || [];
  const go = () => { close(); act("forget", { hashes, delete_files: disk }, after); };
  return (
    <div className="dlgbg" onClick={close}>
      <div className={`dlg ${disk ? "disk" : ""}`} role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
        <h3>{t("title")}</h3>
        <div>{t("lead", { n: p.n })}</div>
        <ul>
          <li>{t("l_entry")}</li>
          {p.tagged > 0 && <li>{t("l_tags", { k: p.tagged })}</li>}
          {p.copies_in_cols > 0 && <li>{t("l_cols", { k: p.copies_in_cols, c: p.cols })}</li>}
          {p.masks > 0 && <li>{t("l_masks", { k: p.masks })}</li>}
          {p.virtuals > 0 && <li>{t("l_virt", { k: p.virtuals })}</li>}
          {p.missing > 0 && <li>{t("l_missing", { k: p.missing })}</li>}
          {p.owned_only > 0 && <li>{t("l_owned", { k: p.owned_only })}</li>}
          {p.vlib > 0 && <li>{t("l_vlib", { k: p.vlib })}</li>}
        </ul>
        {(p.folders || []).length > 0 && <div className="muted">{t("l_folders", { list: p.folders.join(", ") })}</div>}
        {(p.offline_folders || []).length > 0 && <div className="warn">{t("l_offline", { list: p.offline_folders.join(", ") })}</div>}
        {p.vlib > 0 && <div>{t("vlib_bin")}</div>}
        {!(p.vlib_only && p.vlib_only === p.n) && (disk ? <p><b>⚠ {t("disk_on", { k: p.on_disk })}</b></p> : <p><b>{t("safe")}</b> {t("safe2")}</p>)}
        {p.on_disk > 0 && (
          <div className="diskbox">
            <label><input type="checkbox" checked={disk} onChange={(e) => setDisk(e.target.checked)} /> <b>{t("disk")}</b></label>
            <div>{t("disk_n", { k: p.on_disk })}</div>
            <ul className="files">{files.slice(0, 12).map((f) => <li key={f} title={f}>{f}</li>)}{p.on_disk > 12 && <li className="muted">{t("disk_more", { k: p.on_disk - 12 })}</li>}</ul>
            <div className="muted">{t("disk_fail")}</div>
          </div>
        )}
        <div className="btns"><button onClick={close}>{t("cancel")}</button><button className="danger" autoFocus onClick={go}>{disk ? t("go_disk", { k: p.on_disk }) : t("go")}</button></div>
      </div>
    </div>
  );
}

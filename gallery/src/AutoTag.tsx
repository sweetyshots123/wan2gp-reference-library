// 1.8.7: AutoTag en la Galería. Usa exactamente las acciones ilib de la Media Library (at_enqueue / at_status /
// at_pause / at_cancel -> reflib_core.autotag.AutoTagService): misma cola, mismos modelos y el mismo aviso de
// descarga / coste en la nube (at_enqueue devuelve "confirm" y se reenvía con confirm:true). Nada se reimplementa.
import { useEffect, useRef, useState } from "react";
import { call } from "./api";
import { toast } from "./ui";

const KICK = "reflib:at-kick";
export const AT_DONE = "reflib:at-done";   // 1.9.2: la cola terminó (o cambió una imagen): recargar etiquetas automáticas

// 1.9.2: taxonomía (nombres ES de las etiquetas automáticas), la misma que usa la Media Library (at_facets tax:true)
let TAX: Map<string, any> | null = null;
let taxP: Promise<void> | null = null;
export function setTax(list: any[] | undefined) { if (list && list.length) TAX = new Map(list.map((n) => [n.id, n])); }
export function loadTax(): Promise<void> {
  if (TAX) return Promise.resolve();
  if (!taxP) taxP = call("at_facets", { f: {}, tax: true }).then((r) => setTax(r.tax)).catch(() => { taxP = null; });
  return taxP;
}
export const autoLabel = (id: string) => { const n = TAX?.get(id); return n ? n.es || n.en || id : id; };
export const isLeafTag = (id: string) => { const n = TAX?.get(id); return !!n && n.k === "t" && id !== "appears_minor" && id !== "needs_review"; };

export async function startAutotag(hashes: string[], force = false) {
  let r = await call("at_enqueue", { hashes, force });
  if (r.ok && r.confirm) {
    const e = r.confirm;
    const parts = [`${e.images} imagen(es) con el modelo ${e.model}.`];
    if (e.download_gb) parts.push(`Primero se descargará el modelo (~${e.download_gb} GB).`);
    if (e.cloud) parts.push(`Modelo en la nube: las imágenes se envían a su servicio${e.usd != null ? ` (coste estimado ${e.usd} USD)` : ""}.`);
    if (e.warning) parts.push(e.warning);
    if (!window.confirm(parts.join("\n") + "\n\n¿Continuar?")) return;
    r = await call("at_enqueue", { hashes, force, confirm: true });
  }
  if (!r.ok) { toast(r.error || r.message || "Error", "err"); return; }
  toast(r.message || "Autoetiquetado en cola");
  window.dispatchEvent(new Event(KICK));
}

/** Barra de progreso de la cola de autoetiquetado (la misma cola que ve la Media Library). */
export function AutoTagBar({ onDone }: { onDone: () => void }) {
  const [at, setAt] = useState<any>(null);
  const was = useRef(false);
  const done = useRef(onDone); done.current = onDone;
  useEffect(() => {
    let timer: any, alive = true;
    const poll = async () => {
      clearTimeout(timer);
      try {
        const r = await call("at_status");
        if (!alive) return;
        const s = r.at; setAt(s);
        const busy = !!s && (s.running || s.queued > 0);
        if (was.current && !busy) {
          done.current(); window.dispatchEvent(new Event(AT_DONE));
          if (s.error) toast(`Autoetiquetado detenido: ${s.error}`, "err");
          else if (s.failed) toast(`Autoetiquetado terminado: ${s.done} hecha(s), ${s.failed} fallida(s)`, "err");
          else if (s.done) toast(`Autoetiquetado terminado: ${s.done} imagen(es). Las etiquetas están en «Etiquetas automáticas».`);
          else if (s.skipped) toast("Ya estaban etiquetadas (usa ↻ Reetiquetar para repetir)");
        }
        was.current = busy;
        timer = setTimeout(poll, busy ? 1500 : 15000);
      } catch { timer = setTimeout(poll, 5000); }
    };
    const kick = () => { was.current = true; poll(); };
    window.addEventListener(KICK, kick); poll();
    return () => { alive = false; clearTimeout(timer); window.removeEventListener(KICK, kick); };
  }, []);
  if (!at || !(at.running || at.queued > 0)) return null;
  const total = Math.max(at.total || 0, (at.done || 0) + (at.queued || 0));
  const pct = total ? Math.round((100 * at.done) / total) : 0;
  return (
    <div className="atbar" role="status">
      <span>🏷 Autoetiquetando {at.done}/{total}{at.failed ? ` · ${at.failed} fallidas` : ""}{at.paused ? " · en pausa" : at.waiting && at.waiting !== "paused" ? ` · ${at.waiting}` : ""}</span>
      <div className="atprog"><div style={{ width: pct + "%" }} /></div>
      <button onClick={async () => setAt((await call("at_pause", { paused: !at.paused })).at)}>{at.paused ? "▶ Seguir" : "⏸ Pausa"}</button>
      <button onClick={async () => setAt((await call("at_cancel")).at)}>✕ Cancelar</button>
      {!at.loaded && !at.done && <span className="muted">{at.waiting ? "" : "cargando / descargando el modelo… (la primera vez puede tardar)"}</span>}
      {at.error && <span className="aterr">{at.error}</span>}
    </div>
  );
}

/** 1.9.2: «Etiquetas automáticas» de una imagen, como en la Media Library: at_image (lectura) y at_edit
 *  (accept = ✓ confirmar, remove = × quitar, restore = ↺ recuperar). Se guardan aparte de las etiquetas manuales. */
export function AutoTags({ hash, onSearch }: { hash: string; onSearch?: (id: string, label: string) => void }) {
  const [img, setImg] = useState<any>(null);
  const [st, setSt] = useState<any>(null);
  const [more, setMore] = useState(false);
  const load = () => call("at_image", { hash }).then((r) => r.ok && setImg(r.img)).catch(() => {});
  useEffect(() => {
    setImg(null); setMore(false); load();
    const h = () => load();
    const k = () => setSt({ queued: true });
    window.addEventListener(AT_DONE, h); window.addEventListener(KICK, k);
    return () => { window.removeEventListener(AT_DONE, h); window.removeEventListener(KICK, k); };
  }, [hash]);
  const edit = async (tag: string, op: string) => {
    const r = await call("at_edit", { hash, tag, op });
    if (r.ok) { setImg(r.img); window.dispatchEvent(new Event(AT_DONE)); } else toast(r.error || "Error", "err");
  };
  if (!img) return null;
  const tags: any[] = img.tags || [];
  const shown = tags.filter((t) => t.shown && !t.rejected);
  const hidden = tags.filter((t) => !t.shown || t.rejected);
  const chip = (t: any) => (
    <span key={t.id} className={`chip auto ${t.shown && !t.rejected ? "" : "off"} ${t.accepted ? "acc" : ""}`} title={`Confianza ${Math.round(t.conf * 100)} % · ${t.src}${t.accepted ? " · confirmada" : ""}`}>
      <span className="clk" onClick={() => onSearch?.(t.id, t.label)} title="Clic: ver todas las imágenes con esta etiqueta">{t.label}</span><small> {Math.round(t.conf * 100)}</small>
      {t.rejected ? <button title="Recuperar" onClick={() => edit(t.id, "restore")}>↺</button>
        : <>{!t.accepted && <button title="Confirmar (la etiqueta se queda y entrena el modelo)" onClick={() => edit(t.id, "accept")}>✓</button>}
          <button title="Quitar esta etiqueta automática" onClick={() => edit(t.id, "remove")}>×</button></>}
    </span>);
  return (
    <section>
      <h4>Etiquetas automáticas {img.model && <small className="muted">{img.model}</small>}</h4>
      {img.review && <p className="aterr">⚠ Marcada para revisión: sin etiquetas automáticas visibles.</p>}
      <div className="chips">
        {shown.map(chip)}
        {!tags.length && <span className="muted">{st?.queued ? "En cola… aparecerán aquí al terminar." : img.model ? "El modelo no encontró etiquetas." : "Aún sin autoetiquetar."}</span>}
      </div>
      {hidden.length > 0 && <p><button className="link" onClick={() => setMore(!more)}>{more ? "Ocultar" : `+ ${hidden.length} con poca confianza o quitadas`}</button></p>}
      {more && <div className="chips">{hidden.map(chip)}</div>}
    </section>
  );
}

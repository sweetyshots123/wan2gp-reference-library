// 1.8.7: AutoTag en la Galería. Usa exactamente las acciones ilib de la Media Library (at_enqueue / at_status /
// at_pause / at_cancel -> reflib_core.autotag.AutoTagService): misma cola, mismos modelos y el mismo aviso de
// descarga / coste en la nube (at_enqueue devuelve "confirm" y se reenvía con confirm:true). Nada se reimplementa.
import { useEffect, useRef, useState } from "react";
import { call } from "./api";
import { toast } from "./ui";

const KICK = "reflib:at-kick";

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
        if (was.current && !busy) done.current();
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
      {at.error && <span className="aterr">{at.error}</span>}
    </div>
  );
}

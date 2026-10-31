// 1.9.3: similitud por pose / cara en la Galería. Solo llama a las acciones compartidas sim_* de 1.9.0
// (reflib_core/similarity.py, ver SIMILARITY_API.md): sim_search -> sid; el resultado es el filtro {sim: sid} de query
// ordenado por similitud (sort ""); sim_index / sim_status / sim_pause / sim_cancel = «Calcular poses y caras».
// Mismos textos y mensajes que el diálogo «Buscar similares» de la Media Library. Nada se reimplementa.
import { useEffect, useRef, useState } from "react";
import { call } from "./api";
import { toast } from "./ui";

export type SimMode = "pose" | "face";
export interface SimRef { sid: string; hash: string; name: string; mode: SimMode; n: number }
export const SIM_EVENT = "reflib:sim";
const KICK = "reflib:sim-kick";
const MODE_ES: Record<SimMode, string> = { pose: "Pose", face: "Cara" };

export const SIM_ENV_MSG = "El entorno de similitud no está configurado (Python con onnxruntime; ver README «Similarity models»).";
/** 1.9.4: same wording for sim_search and the progress bar; the classification (env_missing) comes from the backend. */
export const simErr = (err: string, envMissing?: boolean) => (envMissing ? `${SIM_ENV_MSG} ${err}` : err);

export async function findSimilar(hash: string, name: string, mode: SimMode) {
  try {
    const info = await call("sim_info", { hash });
    if (info.ok && info.info && !info.info.indexed)
      toast("Aún no calculada: la primera búsqueda calcula la imagen de consulta (puede tardar unos segundos)…");
    const t0 = Date.now();
    const r = await call("sim_search", { hashes: [hash], mode, slow: true });
    if (!r.ok) {
      if (r.error === "no_query") toast(mode === "face" ? "No se encontró ninguna cara en esta imagen." : "No se detectó ninguna persona (pose) en esta imagen.", "err");
      else if (r.error === "engine") {
        const d = String(r.detail || "");
        toast(r.env_missing
          ? `${SIM_ENV_MSG} ${d}`
          : `Error del motor de similitud: ${d || "?"}`, "err");
      } else toast(`Error del motor de similitud: ${r.error || "?"}`, "err");
      return;
    }
    window.dispatchEvent(new CustomEvent(SIM_EVENT, { detail: { sid: r.sid, hash, name, mode, n: r.n } as SimRef }));
    toast(`${r.n} imágenes similares (${Date.now() - t0} ms)`);
  } catch (e: any) { toast(`Error del motor de similitud: ${e?.message || e}`, "err"); }
}

/** «Similares: Pose · Cara» (visor y panel de edición de un elemento). */
export function SimilarButtons({ hash, name }: { hash: string; name: string }) {
  const [busy, setBusy] = useState<SimMode | null>(null);
  const go = async (m: SimMode) => { setBusy(m); await findSimilar(hash, name, m); setBusy(null); };
  return (
    <div className="simbtns" title="Busca imágenes con una pose o una cara parecida (las mismas acciones que «Buscar similares» de la Media Library)">
      <span>⧉ Similares</span>
      {(["pose", "face"] as SimMode[]).map((m) => <button key={m} disabled={!!busy} onClick={() => go(m)}>{busy === m ? "…" : MODE_ES[m]}</button>)}
    </div>
  );
}

export async function startSimIndex(hashes: string[] | null) {
  const r = await call("sim_index", hashes ? { hashes } : { all: true });
  if (!r.ok) { toast(r.error || "Error", "err"); return; }
  toast(r.queued ? `Calculando poses y caras de ${r.queued} imagen(es)…` : "Ya estaban calculadas.");
  window.dispatchEvent(new Event(KICK));
}

/** Barra de progreso de «Calcular poses y caras» (sim_status), como el estado del diálogo de la Media Library. */
export function SimBar() {
  const [s, setS] = useState<any>(null);
  const was = useRef(false);
  useEffect(() => {
    let timer: any, alive = true;
    const poll = async () => {
      clearTimeout(timer);
      try {
        const r = await call("sim_status"); if (!alive) return;
        const x = r.sim; setS(x);
        const busy = !!x && x.running;
        if (was.current && !busy) {
          if (x.error) toast(x.env_missing ? simErr(x.error, true) : `Cálculo de poses y caras detenido: ${x.error}`, "err");
          else toast(`Poses y caras calculadas: ${x.index?.images || 0} de ${x.library || 0} imágenes · ${x.index?.persons || 0} personas · ${x.index?.faces || 0} caras${x.failed ? ` · ${x.failed} fallidas` : ""}`);
        }
        was.current = busy;
        timer = setTimeout(poll, busy ? 1500 : 20000);
      } catch { timer = setTimeout(poll, 8000); }
    };
    const kick = () => { was.current = true; poll(); };
    window.addEventListener(KICK, kick); poll();
    return () => { alive = false; clearTimeout(timer); window.removeEventListener(KICK, kick); };
  }, []);
  if (!s || !s.running) return null;
  const pct = s.total ? Math.round((100 * s.done) / s.total) : 0;
  const w = String(s.waiting || "");
  const wait = s.paused ? "en pausa" : w === "busy" ? "en espera: WanGP está generando" : w.startsWith("download:") ? `descargando el modelo ${w.slice(9)}…` : "";
  const dl = s.download;
  return (
    <div className="atbar simbar" role="status">
      <span>⧉ Calculando poses y caras {s.done}/{s.total}{s.per_image_ms ? ` · ${s.per_image_ms} ms por imagen` : ""}{wait ? ` · ${wait}` : ""}
        {dl ? ` · descargando ${dl.file}: ${Math.round(dl.done / 1e6)} / ${Math.round(dl.total / 1e6)} MB` : ""}</span>
      <div className="atprog"><div style={{ width: pct + "%" }} /></div>
      <button onClick={async () => setS((await call("sim_pause", { paused: !s.paused })).sim)}>{s.paused ? "▶ Reanudar" : "⏸ Pausar"}</button>
      <button onClick={async () => setS((await call("sim_cancel")).sim)}>✕ Detener</button>
      {s.error && <span className="aterr">{simErr(s.error, s.env_missing)}</span>}
    </div>
  );
}

/** Cabecera de un resultado de similitud: miniatura de la referencia, Pose/Cara y quitar. */
export function SimHeader({ r, clear, Thumb }: { r: SimRef; clear: () => void; Thumb: any }) {
  return (
    <div className="simhead">
      <Thumb hash={r.hash} className="simref" />
      <span>Similares a <b>{r.name}</b> · {r.n}</span>
      <span className="seg">{(["pose", "face"] as SimMode[]).map((m) =>
        <button key={m} className={r.mode === m ? "on" : ""} onClick={() => r.mode !== m && findSimilar(r.hash, r.name, m)}>{MODE_ES[m]}</button>)}</span>
      <button onClick={clear} title="Quitar el filtro de similitud">× Quitar</button>
    </div>
  );
}

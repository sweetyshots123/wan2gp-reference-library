// 1.11.0 Duplicados: grupos de fotos iguales o casi iguales, con la resolución y los datos de cada copia.
// Toda la lógica está en el servidor (reflib_core/dupes.py: dup_scan / dup_status / dup_groups / dup_resolve), la misma
// que usa la Media Library. Borrar usa el flujo de siempre (forget_plan → DeleteDialog / delete_all, 1.9.7).
import { useEffect, useState } from "react";
import { call } from "./api";
import { act } from "./actions";
import DeleteDialog, { startDelete } from "./DeleteDialog";
import { toast, Thumb } from "./ui";

export interface DupRow { hash: string; name: string; path: string; dir: string; folder: string | null; w: number; h: number; mp: number; bytes: number; fmt: string; date: number; origin: string; tags: number; in_library: boolean; on_disk: boolean; video?: boolean; dur?: number | null; codec?: string; fps?: number | null }
export interface DupGroup { id: string; kind: "exact" | "near"; dist: number; rows: DupRow[]; keep: number; biggest: number; smallest: number; waste: number; same_item: boolean }

const fmtB = (b: number) => b >= 1 << 20 ? `${(b / (1 << 20)).toFixed(1)} MB` : `${Math.max(1, Math.round(b / 1024))} KB`;
const fmtD = (t: number) => t ? new Date(t * 1000).toLocaleString("es-ES", { dateStyle: "short", timeStyle: "short" }) : "";

/** Plan for a group keeping row k: hashes for the delete flow + extra same-content files for the Papelera. */
function planOf(g: DupGroup, k: number) {
  const keep = g.rows[k];
  if (g.same_item) return { keep: keep.hash, drop: [] as string[], copies: g.rows.filter((_, i) => i !== k).map((r) => r.path) };
  return { keep: keep.hash, drop: [...new Set(g.rows.filter((r) => r.hash !== keep.hash).map((r) => r.hash))], copies: [] as string[] };
}

export function DupesPage({ after }: { after: () => void }) {
  const [st, setSt] = useState<any>(null);
  const [thr, setThr] = useState<number>(() => Number(localStorage.getItem("gal.dupthr") || 6));
  const [kind, setKind] = useState<"" | "exact" | "near">("");
  const [data, setData] = useState<any>(null);
  const [limit, setLimit] = useState(30);
  const [tick, setTick] = useState(0);
  const [transfer, setTransfer] = useState(true);
  const [keepSel, setKeepSel] = useState<Record<string, number>>({});
  const [del, setDel] = useState<{ plan: any; hashes: string[]; ok?: () => void } | null>(null);
  const refresh = () => { setTick((t) => t + 1); after(); };
  useEffect(() => {
    let dead = false, t: any;
    const poll = async () => {
      const r = await call("dup_status").catch(() => null); if (dead || !r) return;
      setSt(r.dupes); if (r.dupes?.running) t = setTimeout(poll, 1000); else if (st?.running) setTick((x) => x + 1);
    };
    poll(); return () => { dead = true; clearTimeout(t); };
  }, [tick, st?.running]);
  useEffect(() => { call("dup_groups", { threshold: thr, kind, limit }).then((r) => r.ok && setData(r)).catch(() => {}); localStorage.setItem("gal.dupthr", String(thr)); }, [thr, kind, limit, tick]);
  const groups: DupGroup[] = data?.groups || [];

  const apply = async (gs: DupGroup[], pick: (g: DupGroup) => number) => {
    const drop: string[] = [];
    const moves: { keep: string; tags: string[] }[] = [];   // 1.11.0: solo tras borrar con éxito
    let recycled = 0;
    for (const g of gs) {
      const p = planOf(g, pick(g));
      const r = await call("dup_resolve", { ...p, transfer }).catch(() => null);
      if (!r || !r.ok) { toast(r?.error || "Error", "err"); continue; }
      drop.push(...(r.drop || [])); recycled += r.recycled || 0; if (r.tags?.length) moves.push({ keep: r.keep, tags: r.tags });
    }
    if (recycled) toast(`${recycled} copia(s) idénticas enviadas a la Papelera`, "ok");
    const ok = async () => { for (const m of moves) await call("dup_transfer", m).catch(() => null); refresh(); };
    if (drop.length) await startDelete(drop, (plan) => setDel({ plan, hashes: drop, ok }), refresh, ok);
    else refresh();
  };
  const keepAll = () => {
    if (!groups.length) return;
    const n = groups.reduce((a, g) => a + g.rows.length - 1, 0);
    if (!window.confirm(`¿Conservar la copia más grande en ${groups.length} grupo(s) y quitar las otras ${n}?\n\nLas copias idénticas del mismo archivo irán a la Papelera; para el resto se abre el diálogo de borrado de siempre (puedes elegir enviar a la Papelera o solo quitar de la librería).${transfer ? "\nLas etiquetas, favoritos y personas pasan a la copia que se conserva." : ""}`)) return;
    apply(groups, (g) => g.keep);
  };

  return (
    <div className="dupes">
      <div className="fstat muted">
        {st ? <>{st.hashed} fotos analizadas{st.running ? ` · analizando ${st.done}/${st.total}…` : ""}{data ? ` · ${data.count} grupo(s) · ${fmtB(data.waste || 0)} recuperables` : ""}</> : "…"}
        <button disabled={!!st?.running} onClick={() => act("dup_scan", {}, refresh, { quiet: true })} title="Analiza las fotos nuevas (incremental)">↻ Buscar duplicados</button>
        <label title="Diferencia permitida entre fotos (bits de pHash): 0 = solo idénticas, más alto = también recortes / recompresiones">Parecido
          <input type="range" min={0} max={16} value={thr} onChange={(e) => setThr(+e.target.value)} /> {thr}</label>
        <span className="seg">{([["", "Todos"], ["exact", "Idénticos"], ["near", "Casi iguales"]] as const).map(([k, l]) =>
          <button key={k} className={kind === k ? "on" : ""} onClick={() => setKind(k)}>{l}</button>)}</span>
        <label title="Mueve etiquetas, favoritos y personas a la copia que se conserva"><input type="checkbox" checked={transfer} onChange={(e) => setTransfer(e.target.checked)} /> Pasar etiquetas</label>
        <button className="danger" disabled={!groups.length} onClick={keepAll}>Conservar la más grande en todos</button>
      </div>
      {!groups.length && <p className="muted">{st?.hashed ? "No hay duplicados con este parecido." : "Pulsa «Buscar duplicados» para analizar las fotos."}</p>}
      {groups.map((g) => { const k = keepSel[g.id] ?? g.keep; return (
        <div key={g.id} className="dgroup">
          <div className="dhead"><b>{g.kind === "exact" ? "Idénticos" : `Casi iguales (diferencia ${g.dist})`}</b> · {g.rows.length} copias · {fmtB(g.waste)} recuperables
            <button onClick={() => { if (window.confirm(`¿Conservar la copia marcada y quitar las otras ${g.rows.length - 1}?${transfer ? "\nLas etiquetas, favoritos y personas pasan a la copia que se conserva (solo si el borrado se completa)." : ""}`)) apply([g], () => k); }}>Conservar la marcada</button></div>
          <div className="drows">
            {g.rows.map((r, i) => (
              <div key={r.hash + r.path} className={`drow ${i === k ? "keep" : "lose"}`} onClick={() => setKeepSel({ ...keepSel, [g.id]: i })}>
                <div className="dimg"><Thumb hash={r.hash} />
                  <span className="dbadges">{i === g.biggest && <span className="badge big">Más grande</span>}{i === g.smallest && g.rows.length > 1 && <span className="badge small">Más pequeña</span>}
                    {r.origin === "ai" && <span className="badge ia">IA</span>}{r.video && <span className="badge video">▶ Vídeo</span>}</span></div>
                <div className="dinfo">
                  <b>{r.w} × {r.h}</b> <span>{r.mp} MP</span><br />
                  <span>{fmtB(r.bytes)} · {r.fmt}</span><br />
                  {r.video && <><span>{[r.dur != null ? r.dur + " s" : "", r.codec, r.fps ? r.fps + " fps" : ""].filter(Boolean).join(" · ")}</span><br /></>}
                  <span className="muted">{fmtD(r.date)}</span><br />
                  <span className="muted dpath" title={r.path}>{r.dir}</span><br />
                  <span className="muted">{r.name}{r.tags ? ` · ${r.tags} etiqueta(s)` : ""}{r.in_library ? " · en colección" : ""}</span>
                  <div className="dkeep">{i === k ? "✓ Conservar" : "Quitar"}</div>
                </div>
              </div>))}
          </div>
        </div>); })}
      {data && groups.length < data.count && <button className="more" onClick={() => setLimit(limit + 30)}>Ver más grupos</button>}
      {del && <DeleteDialog plan={del.plan} hashes={del.hashes} close={() => setDel(null)} after={refresh} ok={del.ok} />}
    </div>
  );
}

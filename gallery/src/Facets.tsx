// 1.9.5: panel de facetas de la Media Library en la Galería: etiquetas automáticas del filtro actual (incluir / excluir:
// f.atags / f.xtags), estado del autoetiquetado (f.jst) y rangos corporales (f.ranges). Todo sale de la acción
// compartida at_facets (facets, body, jobs) con el mismo filtro que la consulta.
import { useEffect, useState } from "react";
import { Filter, call } from "./api";
import { AT_DONE, BODY_RANGE_FIELDS, autoLabel, bodyName, isLeafTag, setTax } from "./AutoTag";

export interface AFilt { atags: string[]; xtags: string[]; ranges: Record<string, [number, number]>; jst: string }
export const AF0: AFilt = { atags: [], xtags: [], ranges: {}, jst: "" };
export const afActive = (a: AFilt) => a.atags.length + a.xtags.length + Object.keys(a.ranges).length + (a.jst ? 1 : 0);
export function afToFilter(a: AFilt): Partial<Filter> & Record<string, any> {
  const o: Record<string, any> = {};
  if (a.atags.length) o.atags = a.atags;
  if (a.xtags.length) o.xtags = a.xtags;
  const r = Object.entries(a.ranges); if (r.length) o.ranges = r.map(([k, v]) => [k, v[0], v[1]]);
  if (a.jst) o.jst = a.jst;
  return o;
}
const JST: Record<string, string> = { queued: "En cola", processing: "Procesando", done: "Autoetiquetadas", failed: "Con error", local: "Etiquetadas localmente", never: "Sin autoetiquetar" };

export function FacetPanel({ f, af, setAf, rev }: { f: Filter; af: AFilt; setAf: (a: AFilt) => void; rev: number }) {
  const [r, setR] = useState<any>(null);
  const [tax, setTx] = useState<any[] | null>(null);
  const [open, setOpen] = useState<Set<string>>(new Set());
  const [atRev, setAtRev] = useState(0);
  useEffect(() => { const h = () => setAtRev((x) => x + 1); window.addEventListener(AT_DONE, h); return () => window.removeEventListener(AT_DONE, h); }, []);
  const fk = JSON.stringify(f);
  useEffect(() => {
    call("at_facets", { f, tax: !tax }).then((x) => { if (!x.ok) return; if (x.tax) { setTax(x.tax); setTx(x.tax); } setR(x); }).catch(() => {});
  }, [fk, rev, atRev]);
  if (!r) return <aside className="facetp"><p className="muted">Cargando…</p></aside>;
  const fc: Record<string, number> = r.facets || {};
  const byId = new Map((tax || []).map((n: any) => [n.id, n]));
  const catOf = (id: string) => { let n: any = byId.get(id), c = id; while (n && n.p) { c = n.p; n = byId.get(n.p); } return c; };
  const ids = [...new Set([...Object.keys(fc).filter((id) => isLeafTag(id)), ...af.atags, ...af.xtags])];
  const cats = new Map<string, string[]>();
  for (const id of ids) { const c = catOf(id); cats.set(c, [...(cats.get(c) || []), id]); }
  const click = (id: string, ex: boolean) => {
    const inA = af.atags.includes(id), inX = af.xtags.includes(id);
    const atags = af.atags.filter((x) => x !== id), xtags = af.xtags.filter((x) => x !== id);
    if (ex) { if (!inX) xtags.push(id); } else if (!inA) atags.push(id);
    setAf({ ...af, atags, xtags });
  };
  const setRange = (k: string, i: number, v: string) => {
    const cur: [number, number] = [...(af.ranges[k] || [-1e9, 1e9])] as any;
    cur[i] = v === "" ? (i ? 1e9 : -1e9) : Number(v);
    const ranges = { ...af.ranges }; if (cur[0] <= -1e9 && cur[1] >= 1e9) delete ranges[k]; else ranges[k] = cur;
    setAf({ ...af, ranges });
  };
  const jc: Record<string, number> = r.jobs || {};
  const bs: Record<string, any> = r.body || {};
  const avail = BODY_RANGE_FIELDS.filter((k) => bs[k]?.n || af.ranges[k]);
  return (
    <aside className="facetp">
      <div className="fph"><b>Facetas</b>{afActive(af) > 0 && <button className="link" onClick={() => setAf(AF0)}>Limpiar</button>}</div>
      <p className="muted small">Clic: incluir · Ctrl/⌘+clic o clic derecho: excluir</p>
      {Object.keys(jc).some((k) => jc[k]) && <div className="fcat"><div className="fct open">Autoetiquetado</div>
        {Object.entries(jc).filter(([k, n]) => n || af.jst === k).map(([k, n]) => <div key={k} className={`fnode ${af.jst === k ? "on" : ""}`} onClick={() => setAf({ ...af, jst: af.jst === k ? "" : k })}><span>{JST[k] || k}</span><i>{n}</i></div>)}</div>}
      {!ids.length && <p className="muted">Sin etiquetas automáticas en esta vista.</p>}
      {[...cats.entries()].map(([c, list]) => {
        const op = open.has(c) || list.some((id) => af.atags.includes(id) || af.xtags.includes(id));
        return <div key={c} className="fcat">
          <div className={`fct ${op ? "open" : ""}`} onClick={() => setOpen((s) => { const n = new Set(s); n.has(c) ? n.delete(c) : n.add(c); return n; })}>{op ? "▾" : "▸"} {autoLabel(c)} <small>{list.length}</small></div>
          {op && list.sort((a, b) => (fc[b] || 0) - (fc[a] || 0)).map((id) => <div key={id} className={`fnode ${af.atags.includes(id) ? "on" : ""} ${af.xtags.includes(id) ? "not" : ""}`}
            onClick={(e) => click(id, e.ctrlKey || e.metaKey)} onContextMenu={(e) => { e.preventDefault(); click(id, true); }}><span>{autoLabel(id)}</span><i>{fc[id] || 0}</i></div>)}
        </div>;
      })}
      {avail.length > 0 && <div className="fcat"><div className="fct open">Rangos corporales <small className="muted">estimado</small></div>
        {avail.map((k) => { const st = bs[k] || { min: 0, max: 1 }, cur = af.ranges[k] || [], ratio = st.max <= 2, step = ratio ? 0.01 : 1;
          return <div key={k} className="frange" title="Filtrar por rango estimado"><span>{bodyName(k)}</span>
            <input type="number" step={step} placeholder={ratio ? Number(st.min).toFixed(2) : String(Math.floor(st.min))} defaultValue={cur[0] != null && cur[0] > -1e8 ? cur[0] : ""} onChange={(e) => setRange(k, 0, e.target.value)} />–
            <input type="number" step={step} placeholder={ratio ? Number(st.max).toFixed(2) : String(Math.ceil(st.max))} defaultValue={cur[1] != null && cur[1] < 1e8 ? cur[1] : ""} onChange={(e) => setRange(k, 1, e.target.value)} /></div>; })}
      </div>}
    </aside>
  );
}

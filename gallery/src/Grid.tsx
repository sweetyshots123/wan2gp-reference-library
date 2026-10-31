import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import type { Item } from "./api";

// Rejilla virtualizada (filas de altura fija, solo se pintan las visibles: fluida con 15k elementos) con cabeceras de
// sección y un índice a la derecha que sigue el orden activo: fecha = años / meses, nombre = letras A–Z (# = dígitos
// y símbolos). Las secciones vienen del servidor (query sections=true) y son proporcionales al número de elementos.
const MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"];
const MES3 = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];
export type Section = [string, number];
const isDate = (k: string) => /^\d{4}-\d{2}$/.test(k);
export const sectionTitle = (k: string) => (k === "0000-00" ? "Sin fecha" : isDate(k) ? `${MESES[+k.slice(5) - 1]} de ${k.slice(0, 4)}` : k === "#" ? "# · números y símbolos" : k);
const shortLabel = (k: string) => (k === "0000-00" ? "?" : isDate(k) ? `${MES3[+k.slice(5) - 1]} ${k.slice(0, 4)}` : k);
const HEAD = 46, GAP = 4;

interface Props {
  total: number; sections: Section[] | null; size: number; version: number;
  getItem: (i: number) => Item | undefined; ensure: (from: number, to: number) => void;
  renderTile: (it: Item | undefined, i: number) => React.ReactNode;
}

export default function Grid({ total, sections, size, version, getItem, ensure, renderTile }: Props) {
  const wrap = useRef<HTMLDivElement>(null);
  const [W, setW] = useState(1200);
  const [scroll, setScroll] = useState({ y: 0, top: 0, vh: innerHeight });
  useLayoutEffect(() => {
    const el = wrap.current; if (!el) return;
    const ro = new ResizeObserver(() => setW(el.clientWidth)); ro.observe(el); setW(el.clientWidth);
    return () => ro.disconnect();
  }, []);
  useEffect(() => {
    let raf = 0;
    const on = () => { cancelAnimationFrame(raf); raf = requestAnimationFrame(() => { const el = wrap.current; if (el) setScroll({ y: scrollY, top: el.getBoundingClientRect().top + scrollY, vh: innerHeight }); }); };
    on(); addEventListener("scroll", on, { passive: true }); addEventListener("resize", on);
    return () => { removeEventListener("scroll", on); removeEventListener("resize", on); cancelAnimationFrame(raf); };
  }, []);
  useEffect(() => { document.documentElement.classList.add("noscrollbar"); return () => document.documentElement.classList.remove("noscrollbar"); }, []);

  const cols = Math.max(2, Math.floor((W + GAP) / (size + GAP)));
  const tile = (W - GAP * (cols - 1)) / cols;
  const rowH = tile + GAP;
  // secciones -> filas: [tipo, top, sección, primer índice]
  const lay = useMemo(() => {
    const secs: Section[] = sections && sections.length && sections.reduce((a, s) => a + s[1], 0) === total ? sections : [["", total]];
    const rows: { top: number; head?: string; first: number; n: number }[] = [];
    const starts: { key: string; top: number; h: number; first: number }[] = [];
    let y = 0, idx = 0;
    for (const [key, n] of secs) {
      const st = { key, top: y, h: 0, first: idx };
      if (key) { rows.push({ top: y, head: key, first: idx, n }); y += HEAD; }
      for (let r = 0; r < Math.ceil(n / cols); r++) { rows.push({ top: y, first: idx + r * cols, n: Math.min(cols, n - r * cols) }); y += rowH; }
      st.h = y - st.top; starts.push(st); idx += n;
    }
    return { rows, starts, height: y, plain: secs.length === 1 && !secs[0][0] };
  }, [sections, total, cols, rowH]);

  const rel = scroll.y - scroll.top;
  const from = rel - scroll.vh * 0.8, to = rel + scroll.vh * 1.8;
  let lo = 0, hi = lay.rows.length;
  while (lo < hi) { const m = (lo + hi) >> 1; if (lay.rows[m].top + rowH < from) lo = m + 1; else hi = m; }
  const vis: typeof lay.rows = [];
  for (let k = lo; k < lay.rows.length && lay.rows[k].top < to; k++) vis.push(lay.rows[k]);
  useEffect(() => {
    const t = vis.filter((r) => !r.head);
    if (t.length) ensure(t[0].first, t[t.length - 1].first + t[t.length - 1].n);
  }, [vis.length && vis[0].first, vis.length && vis[vis.length - 1].first, version, total]);

  return (
    <>
      <div ref={wrap} className="vgrid" style={{ height: lay.height }}>
        {vis.map((r) => r.head
          ? <h2 key={"h" + r.head + r.first} className="sechead" style={{ top: r.top }}>{sectionTitle(r.head)} <small>{r.n}</small></h2>
          : <div key={"r" + r.first} className="vrow" style={{ top: r.top, height: tile, gridTemplateColumns: `repeat(${cols}, ${tile}px)` }}>
              {Array.from({ length: r.n }, (_, j) => <div key={r.first + j} className="vcell">{renderTile(getItem(r.first + j), r.first + j)}</div>)}
            </div>)}
      </div>
      {!lay.plain && lay.height > scroll.vh && <Scrubber lay={lay} rel={rel} vh={scroll.vh} top={scroll.top} />}
    </>
  );
}

function Scrubber({ lay, rel, vh, top }: { lay: { starts: { key: string; top: number; h: number; first: number }[]; height: number }; rel: number; vh: number; top: number }) {
  const bar = useRef<HTMLDivElement>(null);
  const [hover, setHover] = useState<{ y: number; key: string } | null>(null);
  const [H, setH] = useState(400);
  useLayoutEffect(() => { const el = bar.current; if (!el) return; const ro = new ResizeObserver(() => setH(el.clientHeight)); ro.observe(el); setH(el.clientHeight); return () => ro.disconnect(); }, []);
  const frac = (k: number) => (k / lay.height) * H;
  const secAt = (py: number) => { const c = (py / H) * lay.height; let s = lay.starts[0]; for (const x of lay.starts) { if (x.top <= c) s = x; else break; } return s; };
  const jump = (py: number) => { const c = Math.max(0, Math.min(1, py / H)) * lay.height; window.scrollTo({ top: top + c - 70 }); };
  const yOf = (e: { clientY: number }) => e.clientY - bar.current!.getBoundingClientRect().top;
  const cur = secAt(frac(Math.max(0, rel + 80)));
  // etiquetas: fecha = año (al empezar cada año) y meses si cabe; nombre = letras. Sin solaparse (>= 13 px).
  const labels = useMemo(() => {
    const out: { y: number; text: string; key: string; year?: boolean }[] = [];
    let lastY = -99, lastYear = "";
    for (const s of lay.starts) {
      const y = frac(s.top), date = /^\d{4}-\d{2}$/.test(s.key);
      const year = date ? s.key.slice(0, 4) : "";
      if (date && year !== lastYear) { if (y - lastY >= 13 || !out.length) { out.push({ y, text: year, key: s.key, year: true }); lastY = y; } lastYear = year; continue; }
      if (y - lastY >= 13) { out.push({ y, text: date ? MES3[+s.key.slice(5) - 1] : s.key, key: s.key }); lastY = y; }
    }
    return out;
  }, [lay, H]);
  return (
    <div className="scrub" ref={bar}
      onPointerDown={(e) => { (e.target as HTMLElement).setPointerCapture(e.pointerId); jump(yOf(e)); }}
      onPointerMove={(e) => { const y = yOf(e); setHover({ y, key: secAt(y).key }); if (e.buttons & 1) jump(y); }}
      onPointerLeave={() => setHover(null)}>
      {labels.map((l) => <span key={l.key} className={`sl ${l.year ? "yr" : ""} ${cur.key === l.key || (l.year && cur.key.slice(0, 4) === l.text) ? "on" : ""}`} style={{ top: l.y }}>{l.text}</span>)}
      <i className="spos" style={{ top: frac(Math.max(0, rel)), height: Math.max(4, frac(vh)) }} />
      {hover && <b className="stip" style={{ top: hover.y }}>{shortLabel(hover.key)}</b>}
    </div>
  );
}

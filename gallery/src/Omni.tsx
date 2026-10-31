import { useEffect, useMemo, useRef, useState } from "react";
import { FAV, Filter, Item, Meta, call, fold, isPerson, personName } from "./api";
import { Thumb } from "./ui";

// Búsqueda universal: un solo cuadro para personas, colecciones, etiquetas y archivos (nombre o carpeta).
// Sugerencias agrupadas + vista previa en vivo mientras escribes; cada sugerencia elegida pasa a ser un filtro (chip)
// y todos los filtros se combinan con Y. Sin acentos ni mayúsculas.
export type ChipKind = "persona" | "tag" | "col" | "text" | "auto";   // 1.9.2: "auto" = etiqueta automática (f.atags, como la Media Library)
export interface Chip { k: ChipKind; v: string; label: string }
export const chipsFilter = (chips: Chip[], extraText = ""): Filter => {
  const f: Filter = {};
  const tags = chips.filter((c) => c.k === "persona" || c.k === "tag").map((c) => c.v);
  const cols = chips.filter((c) => c.k === "col").map((c) => c.v);
  const qall = [...chips.filter((c) => c.k === "text").map((c) => c.v), ...extraText.split(/\s+/).filter(Boolean)];
  const atags = chips.filter((c) => c.k === "auto").map((c) => c.v);
  if (atags.length) f.atags = atags;
  if (tags.length) f.tags = tags; if (cols.length) f.cols = cols; if (qall.length) f.qall = qall;
  return f;
};
const words = (s: string) => fold(s).split(/\s+/).filter(Boolean);
const score = (label: string, ws: string[]) => { const l = fold(label); if (!ws.every((w) => l.includes(w))) return -1; return l.startsWith(ws[0]) ? 2 : 1; };

interface Sug { k: ChipKind | "file"; v: string; label: string; count?: number; f?: Filter; item?: Item }
const coverCache = new Map<string, Promise<string | null>>();
function Cover({ f }: { f: Filter }) {
  const key = JSON.stringify(f);
  const [h, setH] = useState<string | null>(null);
  useEffect(() => {
    let on = true;
    if (!coverCache.has(key)) coverCache.set(key, call("query", { f, limit: 1 }).then((r) => r.page.items[0]?.hash || null).catch(() => null));
    coverCache.get(key)!.then((x) => on && setH(x));
    return () => { on = false; };
  }, [key]);
  return h ? <Thumb hash={h} className="sthumb" /> : <span className="sthumb ph" />;
}

interface Props {
  meta: Meta | null; chips: Chip[]; setChips: (c: Chip[]) => void; text: string; setText: (s: string) => void;
  onSearch: () => void; onOpenItem: (it: Item, list: Item[]) => void;
}
export default function Omni({ meta, chips, setChips, text, setText, onSearch, onOpenItem }: Props) {
  const [open, setOpen] = useState(false);
  const [hi, setHi] = useState(0);
  const [prev, setPrev] = useState<{ total: number; items: Item[] } | null>(null);
  const inp = useRef<HTMLInputElement>(null);
  const box = useRef<HTMLDivElement>(null);
  const ws = useMemo(() => words(text), [text]);

  const groups = useMemo(() => {
    if (!meta || !ws.length) return { personas: [] as Sug[], cols: [] as Sug[], tags: [] as Sug[] };
    const taken = new Set(chips.map((c) => c.k + "\u0000" + c.v));
    const pick = (xs: Sug[]) => xs.map((x) => [x, score(x.label, ws)] as const).filter(([x, s]) => s > 0 && !taken.has(x.k + "\u0000" + x.v))
      .sort((a, b) => b[1] - a[1] || (b[0].count || 0) - (a[0].count || 0)).slice(0, 6).map(([x]) => x);
    return {
      personas: pick(meta.tags.filter((t) => isPerson(t.tag)).map((t) => ({ k: "persona", v: t.tag, label: personName(t.tag), count: t.count, f: { tags: [t.tag] } }))),
      cols: pick(meta.collections.map((c) => ({ k: "col", v: c.id, label: c.name, count: c.count, f: { cols: [c.id] } }))),
      tags: pick(meta.tags.filter((t) => !isPerson(t.tag)).map((t) => ({ k: "tag", v: t.tag, label: t.tag.toLowerCase() === FAV ? "♥ favorita" : t.tag, count: t.count, f: { tags: [t.tag] } }))),
    };
  }, [meta, ws, chips]);

  // vista previa en vivo (con retardo corto; la última respuesta gana)
  const seq = useRef(0);
  useEffect(() => {
    if (!open || (!ws.length && !chips.length)) { setPrev(null); return; }
    const my = ++seq.current;
    const t = window.setTimeout(() => {
      call("query", { f: { ...chipsFilter(chips, text), sort: "date_desc" }, limit: 18 })
        .then((r) => { if (my === seq.current) setPrev({ total: r.page.total, items: r.page.items }); }).catch(() => {});
    }, 160);
    return () => window.clearTimeout(t);
  }, [text, chips, open]);

  // 1.9.2: etiquetas automáticas: la misma acción de sugerencias que la Media Library (at_suggest, con sinónimos ES/EN)
  const [autoS, setAutoS] = useState<Sug[]>([]);
  useEffect(() => {
    if (!open || text.trim().length < 2) { setAutoS([]); return; }
    let on = true;
    const t = window.setTimeout(() => {
      call("at_suggest", { text, f: chipsFilter(chips) }).then((r) => {
        if (!on || !r.ok) return;
        const taken = new Set(chips.filter((c) => c.k === "auto").map((c) => c.v));
        setAutoS((r.sug || []).filter((x: any) => x.kind === "at" && x.n > 0 && !taken.has(x.id)).slice(0, 6)
          .map((x: any) => ({ k: "auto", v: x.id, label: x.label, count: x.n, f: { atags: [x.id] } })));
      }).catch(() => {});
    }, 160);
    return () => { on = false; window.clearTimeout(t); };
  }, [text, chips, open]);

  const files: Sug[] = ws.length ? (prev?.items || []).filter((i) => score(i.name, ws) > 0).slice(0, 5).map((i) => ({ k: "file", v: i.hash, label: i.name, item: i })) : [];
  const flat = [...groups.personas, ...groups.cols, ...groups.tags, ...autoS, ...files];
  useEffect(() => setHi(0), [text]);
  useEffect(() => { const d = (e: MouseEvent) => { if (!box.current?.contains(e.target as Node)) setOpen(false); }; addEventListener("mousedown", d); return () => removeEventListener("mousedown", d); }, []);

  const choose = (s: Sug) => {
    if (s.k === "file") { onOpenItem(s.item!, prev?.items || [s.item!]); setOpen(false); return; }
    setChips([...chips, { k: s.k, v: s.v, label: s.label }]); setText(""); onSearch(); inp.current?.focus();
  };
  const commit = () => {
    const t = text.trim();
    setChips(t ? [...chips, { k: "text", v: t, label: `“${t}”` }] : chips); setText(""); setOpen(false); onSearch();
  };
  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setOpen(true); setHi((h) => Math.min(flat.length, h + 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setHi((h) => Math.max(0, h - 1)); }
    else if (e.key === "Enter") { e.preventDefault(); if (hi > 0 && flat[hi - 1]) choose(flat[hi - 1]); else commit(); }
    else if (e.key === "Escape") { setOpen(false); inp.current?.blur(); }
    else if (e.key === "Backspace" && !text && chips.length) setChips(chips.slice(0, -1));
  };
  let n = 0;
  const row = (s: Sug) => { const k = ++n; return (
    <li key={s.k + s.v} className={hi === k ? "hi" : ""} onMouseEnter={() => setHi(k)} onMouseDown={(e) => { e.preventDefault(); choose(s); }}>
      {s.item ? <Thumb hash={s.item.hash} className="sthumb" /> : s.f ? <Cover f={s.f} /> : null}
      <span className="sl">{s.k === "tag" ? "#" : s.k === "auto" ? "🏷 " : ""}{s.label}</span>{s.count != null && <small>{s.count}</small>}
    </li>); };
  const group = (title: string, xs: Sug[]) => xs.length ? <div className="og"><h5>{title}</h5><ul>{xs.map(row)}</ul></div> : null;
  const show = open && (ws.length > 0 || chips.length > 0);
  return (
    <div className="omni" ref={box}>
      <div className="obox" onClick={() => inp.current?.focus()}>
        {chips.map((c, i) => <span key={c.k + c.v} className={`chip on ${c.k}`}>{c.k === "tag" ? "#" : c.k === "col" ? "▣ " : c.k === "persona" ? "👤 " : c.k === "auto" ? "🏷 " : ""}{c.label}
          <button onClick={(e) => { e.stopPropagation(); setChips(chips.filter((_, j) => j !== i)); }} title="Quitar">×</button></span>)}
        <input id="q" ref={inp} value={text} placeholder={chips.length ? "Añadir más…" : "Buscar personas, colecciones, etiquetas, archivos…  ( / )"}
          onChange={(e) => { setText(e.target.value); setOpen(true); }} onFocus={() => setOpen(true)} onKeyDown={onKey} autoComplete="off" />
      </div>
      {show && (
        <div className="odrop">
          <div className="ocols">
            {group("Personas", groups.personas)}{group("Colecciones", groups.cols)}{group("Etiquetas", groups.tags)}{group("Etiquetas automáticas", autoS)}{group("Archivos", files)}
            {ws.length > 0 && !flat.length && <p className="muted">Ningún nombre coincide; Enter busca «{text}» en archivos y carpetas.</p>}
          </div>
          <div className="oprev">
            <div className="ophead"><b>{prev ? `${prev.total} resultado${prev.total === 1 ? "" : "s"}` : "Buscando…"}</b>
              <button className={hi === 0 ? "on" : ""} onMouseDown={(e) => { e.preventDefault(); commit(); }}>Ver todos ↵</button></div>
            <div className="ogrid">{prev?.items.map((i) => <button key={i.hash} onMouseDown={(e) => { e.preventDefault(); onOpenItem(i, prev.items); setOpen(false); }} title={i.name}><Thumb hash={i.hash} /></button>)}</div>
          </div>
        </div>
      )}
    </div>
  );
}

import { OPEN_EVENT, fmtT } from "./videoT";
import { useSelection } from "./Selection";
import { AutoTagBar } from "./AutoTag";
import Folders, { folderLabel, nodeHref } from "./Folders";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { FAV, Filter, Item, Meta, PERSON, call, fold, isPerson, metaOf, personName, personTag, upload } from "./api";
import { ManageList } from "./Manage";
import { PersonasPage, PersonHeader } from "./Faces";
import { DupesPage } from "./Dupes";
import { VideoManager } from "./Videos";
import { AF0, AFilt, FacetPanel, afActive, afToFilter } from "./Facets";
import { act } from "./actions";
import EditPanel from "./EditPanel";
import DeleteDialog, { startDelete } from "./DeleteDialog";
import { SIM_EVENT, SimBar, SimHeader, SimRef, startSimIndex } from "./Similar";
import { AT_DONE, autoLabel, isLeafTag, loadTax, setTax } from "./AutoTag";
import Viewer from "./Viewer";
import { setRemover } from "./optimistic";
import Grid, { Section } from "./Grid";
import Omni, { Chip, chipsFilter } from "./Omni";
import { Thumb, Toasts, fmtDur, toast } from "./ui";

// ---------------- rutas (hash): fáciles de ampliar añadiendo un caso en parseRoute + una vista
type Route =
  | { v: "explorar" } | { v: "favoritas" } | { v: "videos" } | { v: "sin" } | { v: "buscar" }
  | { v: "personas" } | { v: "persona"; name: string } | { v: "duplicados" }
  | { v: "tags" } | { v: "tag"; tag: string } | { v: "auto"; id: string } | { v: "similares" }
  | { v: "colecciones" } | { v: "coleccion"; id: string }
  | { v: "carpetas" } | { v: "carpeta"; fid: string; rel: string };

function parseRoute(): Route {
  const [a, b, c] = location.hash.replace(/^#\/?/, "").split("/").map((x) => decodeURIComponent(x || ""));
  switch (a) {
    case "favoritas": return { v: "favoritas" };
    case "videos": return { v: "videos" };
    case "sin-coleccion": return { v: "sin" };
    case "buscar": return { v: "buscar" };
    case "personas": case "modelos": return { v: "personas" };          // #/modelos = enlace antiguo
    case "persona": case "modelo": return b ? { v: "persona", name: b } : { v: "personas" };
    case "duplicados": return { v: "duplicados" };   // 1.11.0
    case "etiquetas": return { v: "tags" };
    case "tag": return b ? { v: "tag", tag: b } : { v: "tags" };
    case "similares": return { v: "similares" };   // 1.9.3
    case "auto": return b ? { v: "auto", id: b } : { v: "tags" };   // 1.9.2: etiqueta automática
    case "colecciones": return { v: "colecciones" };
    case "coleccion": return b ? { v: "coleccion", id: b } : { v: "colecciones" };
    case "carpetas": return { v: "carpetas" };
    case "carpeta": return b ? { v: "carpeta", fid: b, rel: c || "" } : { v: "carpetas" };
    default: return { v: "explorar" };
  }
}

const PAGE = 120;
const SORTS: [string, string][] = [["date_desc", "Fecha · recientes"], ["date_asc", "Fecha · antiguas"], ["name_asc", "Nombre A–Z"], ["name_desc", "Nombre Z–A"]];

export default function App() {
  const [route, setRoute] = useState<Route>(parseRoute);
  const [fopen, setFopen] = useState(() => localStorage.getItem("gal.fside") !== "0");
  useEffect(() => { localStorage.setItem("gal.fside", fopen ? "1" : "0"); }, [fopen]);
  const fside = fopen && (route.v === "carpetas" || route.v === "carpeta");
  const [meta, setMeta] = useState<Meta | null>(null);
  const [total, setTotal] = useState(0);
  const [sections, setSections] = useState<Section[] | null>(null);
  const [ver, setVer] = useState(0);                       // sube cuando llegan páginas nuevas
  const [text, setText] = useState("");                    // lo que se está escribiendo en la búsqueda
  const [chips, setChips] = useState<Chip[]>([]);          // filtros de la búsqueda (Y)
  const [kinds, setKinds] = useState<string[]>(() => { try { const k = JSON.parse(localStorage.getItem("gal.kinds") || "[]"); return Array.isArray(k) ? k : []; } catch { return []; } });   // [] = todo
  const [kc, setKc] = useState<Record<string, number>>({});
  const [sort, setSort] = useState(() => localStorage.getItem("gal.sort") || "date_desc");
  const [extraTags, setExtraTags] = useState<string[]>([]);
  const [af, setAf] = useState<AFilt>(AF0);   // 1.9.5: facetas de la Media Library (atags / xtags / jst / rangos)
  const [fpanel, setFpanel] = useState(() => localStorage.getItem("gal.facets") === "1");
  useEffect(() => { localStorage.setItem("gal.facets", fpanel ? "1" : "0"); }, [fpanel]);
  const [, setTaxOk] = useState(false);
  const [simRef, setSimRef] = useState<SimRef | null>(() => { try { return JSON.parse(sessionStorage.getItem("gal.sim") || "null"); } catch { return null; } });   // 1.9.3: búsqueda de similares activa (sim_search)
  useEffect(() => { const h = (e: any) => { setSimRef(e.detail); try { sessionStorage.setItem("gal.sim", JSON.stringify(e.detail)); } catch {} setViewer(null); setSolo(null); setSel(new Set()); if (location.hash !== "#/similares") location.hash = "#/similares"; else refresh(); }; window.addEventListener(SIM_EVENT, h); return () => window.removeEventListener(SIM_EVENT, h); });
  useEffect(() => { const h = (e: any) => { setChips([e.detail]); setText(""); location.hash = "#/buscar"; }; window.addEventListener("reflib:search-chip", h); return () => window.removeEventListener("reflib:search-chip", h); }, []);
  useEffect(() => { loadTax().then(() => setTaxOk(true)); }, []);   // 1.9.2: nombres de las etiquetas automáticas
  const [viewer, setViewer] = useState<number | null>(null);
  const [solo, setSolo] = useState<{ list: Item[]; i: number } | null>(null);   // visor abierto desde la búsqueda
  useEffect(() => { const h = (e: any) => setSolo({ list: [e.detail], i: 0 }); window.addEventListener(OPEN_EVENT, h); return () => window.removeEventListener(OPEN_EVENT, h); }, []);   // 1.12.0 caras de vídeo -> visor en best_t
  const [selMode, setSelMode] = useState(false);
  const [sel, setSel] = useState<Set<string>>(new Set());
  const [editOpen, setEditOpen] = useState(false);   // 1.11.0: el panel de edición solo se abre a petición
  const [delPlan, setDelPlan] = useState<any>(null);
  useEffect(() => { if (sel.size === 0) setEditOpen(false); }, [sel.size]);
  const [size, setSize] = useState(() => +(localStorage.getItem("gal.size") || 220));
  const [drag, setDrag] = useState(false);
  const rev = useRef(0);
  const fileIn = useRef<HTMLInputElement>(null);
  // elementos dispersos: índice -> Item, por páginas (solo se pide lo que se ve)
  const store = useRef(new Map<number, Item>());
  const pages = useRef(new Map<number, number>());         // página -> generación cargada / pidiéndose
  const gen = useRef(0);

  useEffect(() => { const h = () => { setRoute(parseRoute()); setViewer(null); setExtraTags([]); setSel(new Set()); window.scrollTo(0, 0); }; window.addEventListener("hashchange", h); return () => window.removeEventListener("hashchange", h); }, []);
  const [manage, setManage] = useState(false);
  useEffect(() => { localStorage.setItem("gal.size", String(size)); }, [size]);
  useEffect(() => { localStorage.setItem("gal.sort", sort); }, [sort]);
  useEffect(() => { localStorage.setItem("gal.kinds", JSON.stringify(kinds)); }, [kinds]);
  const [origins, setOrigins] = useState<string[]>(() => { try { const k = JSON.parse(localStorage.getItem("gal.origins") || "[]"); return Array.isArray(k) ? k : []; } catch { return []; } });   // 1.10.0 IA / Real
  useEffect(() => { localStorage.setItem("gal.origins", JSON.stringify(origins)); }, [origins]);

  const routeFilter = (r: Route): Filter | null => {
    switch (r.v) {
      case "explorar": return {};
      case "favoritas": return { tags: [FAV] };
      case "videos": return { kind: "video" };
      case "sin": return { none: true };
      case "buscar": return chipsFilter(chips);
      case "persona": return { tags: [personTag(r.name, meta?.tags || [])] };
      case "tag": return { tags: [r.tag] };
      case "auto": return { atags: [r.id] };
      case "similares": return simRef ? { sim: simRef.sid } : {};
      case "coleccion": return { cols: [r.id] };
      case "carpetas": return {};
      case "carpeta": return { node: { fid: r.fid, rel: r.rel }, sub: true };
      default: return null;   // vistas de índice (personas, etiquetas, colecciones)
    }
  };
  const base = routeFilter(route);
  const baseKey = JSON.stringify(base);
  const filter = useMemo<Filter | null>(() => {
    if (!base) return null;
    const out: Filter = { ...base, sort: base.sim ? "" : sort };   // 1.9.3: resultado de similitud = mejor primero
    if (kinds.length && kinds.length < 3 && !base.kind) out.kinds = kinds;
    if (origins.length === 1) out.origins = origins;
    if (extraTags.length) out.tags = [...(base.tags || []), ...extraTags];
    const ax = afToFilter(af);
    if (ax.atags) ax.atags = [...(base.atags || []), ...ax.atags];
    return { ...out, ...ax };
  }, [baseKey, kinds, origins, sort, extraTags, JSON.stringify(af)]);
  const fkey = JSON.stringify(filter);

  const applyMeta = (r: any) => { const m = metaOf(r); if (m) { setMeta(m); rev.current = m.rev; } };
  const tz = -new Date().getTimezoneOffset();

  const fetchPage = useCallback(async (p: number, g: number, withSections = false) => {
    if (!filter) return;
    pages.current.set(p, g);
    try {
      const r = await call("query", { f: filter, offset: p * PAGE, limit: PAGE, meta: withSections, sections: withSections, tz_min: tz });
      if (g !== gen.current) return;
      if (withSections) { applyMeta(r); setSections(r.page.sections || null); if (r.page.kinds) setKc(r.page.kinds); }
      setTotal(r.page.total);
      r.page.items.forEach((it: Item, j: number) => store.current.set(p * PAGE + j, it));
      setVer((v) => v + 1);
    } catch { if (g === gen.current) pages.current.delete(p); }
  }, [fkey]);

  // filtro nuevo: se vacía y se pide la primera página (con las secciones del índice lateral)
  useEffect(() => {
    if (!filter) { call("list").then(applyMeta); return; }
    const g = ++gen.current; store.current = new Map(); pages.current = new Map(); setTotal(0); setSections(null); setVer((v) => v + 1);
    fetchPage(0, g, true);
  }, [fkey]);

  const closeViewer = useCallback(() => setViewer(null), []);   // 1.9.7: props estables -> el visor (memo) no se re-renderiza por el resto de la app
  const ensure = useCallback((from: number, to: number) => {
    for (let p = Math.floor(Math.max(0, from) / PAGE); p <= Math.floor(Math.max(0, to - 1) / PAGE); p++)
      if (pages.current.get(p) !== gen.current) fetchPage(p, gen.current);
  }, [fetchPage]);

  // recarga en el sitio (tras editar o si cambió algo en la Media Library): mismas páginas, sin vaciar
  const refresh = useCallback(() => {
    if (!filter) { call("list").then(applyMeta); return; }
    const g = ++gen.current, loaded = [...pages.current.keys()];
    pages.current = new Map();
    fetchPage(0, g, true).then(() => loaded.filter((p) => p > 0).forEach((p) => fetchPage(p, g)));
  }, [fetchPage]);

  // sincronía: si la Media Library cambia algo (otra pestaña / otra UI) se recarga sola
  useEffect(() => {
    const t = window.setInterval(async () => {
      if (document.hidden) return;
      try { const r = await call("list"); const m = metaOf(r); if (m && m.rev !== rev.current) { applyMeta(r); refresh(); } } catch {}
    }, 5000);
    return () => window.clearInterval(t);
  }, [refresh]);

  // 1.9.7: borrado optimista (optimistic.ts): se quitan de la lista cargada al instante y el visor pasa a la siguiente
  const totalNow = useRef(0); totalNow.current = total;
  const viewerNow = useRef<number | null>(null); viewerNow.current = viewer;
  useEffect(() => {
    setRemover((hs) => {
      const snap = { store: store.current, total: totalNow.current, viewer: viewerNow.current };
      const next = new Map<number, Item>(), gone: number[] = [];
      [...store.current.entries()].sort((a, b) => a[0] - b[0]).forEach(([i, it]) => { if (hs.has(it.hash)) gone.push(i); else next.set(i - gone.length, it); });
      if (!gone.length) return () => {};
      const nt = Math.max(0, snap.total - gone.length);
      store.current = next; setTotal(nt); setVer((v) => v + 1);
      setSel((s) => { if (![...hs].some((h) => s.has(h))) return s; const n = new Set(s); hs.forEach((h) => n.delete(h)); return n; });
      if (snap.viewer != null) { const before = gone.filter((i) => i < snap.viewer!).length; setViewer(nt ? Math.min(snap.viewer - before, nt - 1) : null); }
      return () => { store.current = snap.store; setTotal(snap.total); setVer((v) => v + 1); if (snap.viewer != null) setViewer(snap.viewer); };
    });
    return () => setRemover(null);
  }, []);

  const items = useMemo(() => { const a: Item[] = new Array(total); store.current.forEach((it, i) => { if (i < total) a[i] = it; }); return a; }, [ver, total]);
  const loaded = useMemo(() => [...store.current.values()], [ver]);

  const doUpload = async (files: File[]) => {
    if (!files.length) return;
    toast(`Subiendo ${files.length} archivo(s)…`, "info");
    const r = await upload(files);
    toast(r.toast || r.message || (r.ok ? "Importado" : "Error"), r.ok ? "ok" : "err");
    refresh();
  };

  const toggleSel = (h: string) => setSel((s) => { const n = new Set(s); n.has(h) ? n.delete(h) : n.add(h); return n; });
  const selection = useSelection(sel, setSel, filter, total, (i) => store.current.get(i)?.hash);
  const selApi = useRef(selection); selApi.current = selection;
  const selRef = useRef(sel); selRef.current = sel;
  const selItems = loaded.filter((i) => sel.has(i.hash));
  const open = viewer !== null || solo !== null;
  useEffect(() => {
    const k = (e: KeyboardEvent) => {
      if (open || (e.target as HTMLElement).closest("input,textarea,select")) return;
      if (e.key === "s") setSelMode((m) => !m);
      else if (selApi.current.key(e)) { e.preventDefault(); if (e.key === "Escape") setSelMode(false); }
      else if (e.key === "Escape") setSelMode(false);
      else if (e.key === "/") { e.preventDefault(); document.getElementById("q")?.focus(); }
    };
    window.addEventListener("keydown", k); return () => window.removeEventListener("keydown", k);
  }, [open]);

  const title = (() => {
    switch (route.v) {
      case "explorar": return "Explorar";
      case "favoritas": return "Favoritas";
      case "videos": return "Vídeos";
      case "sin": return "Sin colección";
      case "buscar": return "Búsqueda";
      case "personas": return "Personas";
      case "duplicados": return "Duplicados";
      case "persona": return route.name;
      case "tags": return "Etiquetas";
      case "tag": return `#${route.tag}`;
      case "auto": return `🏷 ${autoLabel(route.id)}`;
      case "similares": return "Similares";
      case "colecciones": return "Colecciones";
      case "carpetas": return "Carpetas";
      case "carpeta": { const f = meta?.folders.find((x: any) => x.id === route.fid); return route.rel ? route.rel.split("/").pop() || "" : folderLabel(f); }
      case "coleccion": return meta?.collections.find((c) => c.id === route.id)?.name || "Colección";
    }
  })();
  const nav = (h: string, label: string, on: boolean) => <a href={h} className={on ? "on" : ""}>{label}</a>;
  const v = route.v;
  const goSearch = () => { if (location.hash !== "#/buscar") location.hash = "#/buscar"; };
  const tq = fold(text.trim());

  // etiquetas que aparecen en lo cargado (para afinar la vista)
  const facet = useMemo(() => {
    const m = new Map<string, number>();
    loaded.forEach((i) => i.tags.forEach((t) => m.set(t, (m.get(t) || 0) + 1)));
    const b = new Set((filter?.tags || []).map((t) => t.toLowerCase()));
    return [...m.entries()].filter(([t]) => !b.has(t.toLowerCase())).sort((a, b) => b[1] - a[1]).slice(0, 14);
  }, [loaded, filter]);

  // página de resultados: personas / colecciones / etiquetas cuyo nombre coincide con los textos buscados
  const matches = useMemo(() => {
    const ts = chips.filter((c) => c.k === "text").map((c) => fold(c.v));
    if (!meta || v !== "buscar" || !ts.length) return [] as Chip[];
    const ok = (s: string) => ts.some((t) => fold(s).includes(t));
    const have = new Set(chips.map((c) => c.v));
    return [
      ...meta.tags.filter((t) => isPerson(t.tag) && ok(personName(t.tag))).map((t) => ({ k: "persona" as const, v: t.tag, label: personName(t.tag), n: t.count })),
      ...meta.collections.filter((c) => ok(c.name)).map((c) => ({ k: "col" as const, v: c.id, label: c.name, n: c.count })),
      ...meta.tags.filter((t) => !isPerson(t.tag) && ok(t.tag)).map((t) => ({ k: "tag" as const, v: t.tag, label: t.tag, n: t.count })),
    ].filter((c) => !have.has(c.v)).slice(0, 24);
  }, [meta, chips, v]);

  const dateNote = sort.startsWith("date") ? "Fecha: la de importación a la Media Library (o la de modificación del archivo si no hay)." : "";

  return (
    <div className={`app ${drag ? "dragging" : ""}`}
      onDragOver={(e) => { if (e.dataTransfer.types.includes("Files")) { e.preventDefault(); setDrag(true); } }}
      onDragLeave={(e) => { if (e.currentTarget === e.target) setDrag(false); }}
      onDrop={(e) => { e.preventDefault(); setDrag(false); doUpload([...e.dataTransfer.files]); }}>
      <header className="top">
        <a className="logo" href="#/">Galería<small>Media Library</small></a>
        <nav>
          {nav("#/", "Explorar", v === "explorar")}
          {nav("#/personas", "Personas", v === "personas" || v === "persona")}
          {nav("#/etiquetas", "Etiquetas", v === "tags" || v === "tag" || v === "auto")}
          {nav("#/colecciones", "Colecciones", v === "colecciones" || v === "coleccion")}
          {nav("#/carpetas", "Carpetas", v === "carpetas" || v === "carpeta")}
          {nav("#/favoritas", "♥ Favoritas", v === "favoritas")}
          {nav("#/videos", "Vídeos", v === "videos")}
          {nav("#/duplicados", "Duplicados", v === "duplicados")}
        </nav>
        <Omni meta={meta} chips={chips} setChips={(c) => { setChips(c); goSearch(); }} text={text} setText={setText} onSearch={goSearch}
          onOpenItem={(it, list) => setSolo({ list, i: Math.max(0, list.findIndex((x) => x.hash === it.hash)) })} />
        <button onClick={() => fileIn.current?.click()} title="O arrastra archivos a la ventana">⤒ Subir</button>
        <input ref={fileIn} type="file" multiple hidden accept="image/*,video/*,audio/*" onChange={(e) => { doUpload([...(e.target.files || [])]); e.target.value = ""; }} />
        <a className="ml" href="/" title="Abrir WanGP / Media Library">WanGP ↗</a>
      </header>

      {filter ? (
        <div className={`${fside ? "withside" : ""} ${fpanel ? "withfacets" : ""}`}>
        {fside && meta && <Folders meta={meta} node={route.v === "carpeta" ? { fid: route.fid, rel: route.rel } : null} onChanged={refresh} />}
        <main>
          <div className="bar">
            <h1>{(v === "carpetas" || v === "carpeta") && <button className="sidetg" onClick={() => setFopen(!fopen)} title="Mostrar/ocultar el árbol de carpetas">{fopen ? "◧" : "☰"}</button>}{title} <small>{total}</small>{v === "videos" && <button className="ml" onClick={() => setManage(!manage)} title="Video Library: renombrar, ordenar, borrar, importar y exportar">{manage ? "Ver vídeos" : "Gestionar Video Library"}</button>}</h1>
            {v === "videos" && manage && <VideoManager after={refresh} />}
            {v === "carpeta" && <p className="muted crumbs">{crumbsOf(meta, route)}</p>}
            {v === "persona" && <p className="muted">Etiqueta: <code>{filter.tags?.[0] || PERSON + route.name}</code></p>}
            {v === "persona" && <PersonHeader name={route.name} rev={meta?.rev || 0} after={refresh} />}
            {v === "similares" && (simRef ? <SimHeader r={simRef} Thumb={Thumb} clear={() => { setSimRef(null); location.hash = "#/explorar"; }} />
              : <p className="muted">Abre una imagen y pulsa «⧉ Similares: Pose / Cara».</p>)}
            {v === "buscar" && !chips.length && <p className="muted">Escribe arriba: personas, colecciones, etiquetas o nombres de archivo. Varios filtros se combinan (Y).</p>}
            <div className="tools">
              {!base?.kind && <KindToggles kinds={kinds} setKinds={setKinds} counts={kc} libAudio={meta?.kinds?.audio ?? kc.audio ?? 0} />}
              <OriginToggles origins={origins} setOrigins={setOrigins} counts={kc} />
              <select value={sort} onChange={(e) => setSort(e.target.value)} title={dateNote || "Orden (el índice de la derecha lo sigue)"}>
                {SORTS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
              </select>
              <input type="range" min={120} max={420} value={size} onChange={(e) => setSize(+e.target.value)} title="Tamaño de miniaturas" />
              <button className={selMode ? "on" : ""} onClick={() => { setSelMode(!selMode); setSel(new Set()); }} title="Seleccionar (S)">☑ Seleccionar</button>
              <button className={fpanel ? "on" : ""} onClick={() => setFpanel(!fpanel)} title="Facetas: etiquetas automáticas, estado del autoetiquetado y rangos corporales (como en la Media Library)">🏷 Facetas{afActive(af) ? ` (${afActive(af)})` : ""}</button>
              <button onClick={() => startSimIndex(null)} title="Calcula pose y cara de toda la biblioteca para «Similares» (solo lo que falta; en segundo plano, como en la Media Library)">⧉ Calcular poses y caras</button>
            </div>
          </div>
          {v === "buscar" && chips.length > 0 && (
            <div className="facets">
              {chips.map((c, i) => <button key={c.k + c.v} className="chip on" onClick={() => setChips(chips.filter((_, j) => j !== i))}>{c.k === "tag" ? "#" : c.k === "col" ? "▣ " : c.k === "persona" ? "👤 " : c.k === "auto" ? "🏷 " : ""}{c.label} ×</button>)}
              {matches.length > 0 && <span className="muted">· también coinciden:</span>}
              {matches.map((m: any) => <button key={m.k + m.v} className={`chip ${m.k === "persona" ? "model" : ""}`} onClick={() => setChips([...chips, { k: m.k, v: m.v, label: m.label }])}>{m.k === "tag" ? "#" : m.k === "col" ? "▣ " : "👤 "}{m.label} <small>{m.n}</small></button>)}
            </div>
          )}
          {(facet.length > 0 || extraTags.length > 0) && (
            <div className="facets">
              {extraTags.map((t) => <button key={t} className="chip on" onClick={() => setExtraTags(extraTags.filter((x) => x !== t))}>{isPerson(t) ? personName(t) : t} ×</button>)}
              {facet.map(([t, n]) => <button key={t} className={`chip ${isPerson(t) ? "model" : ""}`} onClick={() => setExtraTags([...extraTags, t])}>{isPerson(t) ? personName(t) : t} <small>{n}</small></button>)}
            </div>
          )}
          {dateNote && <p className="muted datenote">{dateNote}</p>}
          {total > 0 && (
            <Grid total={total} sections={sections} size={size} version={ver} getItem={(i) => store.current.get(i)} ensure={ensure}
              renderTile={(it, i) => it ? (
                <Tile it={it} sel={sel.has(it.hash)} selMode={selMode || sel.size > 0}
                  onOpen={(e) => { if (selection.click(it.hash, i, e, false)) return; if (selMode && sel.size === 0) toggleSel(it.hash); else setViewer(i); }}
                  onSel={(e) => { setSelMode(true); selection.click(it.hash, i, e, true); }}
                  onFav={() => act("tag", { hashes: [it.hash], ...(it.tags.some((t) => t.toLowerCase() === FAV) ? { remove: [FAV] } : { add: [FAV] }) }, refresh, { quiet: true })} />
              ) : <div className="tile"><div className="ph" /></div>} />
          )}
          {!total && ver > 1 && <p className="empty">{v === "buscar" ? "Sin resultados." : "Nada por aquí todavía. Arrastra imágenes o vídeos a la ventana para importarlos."}</p>}
        </main>
        {fpanel && filter && <FacetPanel f={filter} af={af} setAf={setAf} rev={meta?.rev || 0} />}
        </div>
      ) : (
        <main>
          <div className="bar"><h1>{title}</h1>{tq && <p className="muted">filtrando por «{text}»</p>}
            {(v === "tags" || v === "personas" || v === "colecciones") && <button className="ml" onClick={() => setManage(!manage)}>{manage ? "Ver tarjetas" : "Gestionar"}</button>}</div>
          {meta && manage && v === "tags" && <ManageList kind="tag" rows={meta.tags.filter((t) => !isPerson(t.tag) && t.tag.toLowerCase() !== FAV).filter((t) => !tq || fold(t.tag).includes(tq)).map((t) => ({ key: t.tag, label: t.tag, count: t.count }))} after={refresh} />}
          {meta && manage && v === "personas" && <ManageList kind="persona" rows={meta.tags.filter((t) => isPerson(t.tag)).filter((t) => !tq || fold(personName(t.tag)).includes(tq)).map((t) => ({ key: t.tag, label: personName(t.tag), count: t.count }))} after={refresh} />}
          {meta && manage && v === "colecciones" && <ManageList kind="col" rows={meta.collections.filter((c) => !tq || fold(c.name).includes(tq)).map((c) => ({ key: c.id, label: c.name, count: c.count }))} after={refresh} />}
          {meta && v === "duplicados" && <DupesPage after={refresh} />}
          {meta && !manage && v === "personas" && <PersonasPage tq={tq} rev={meta.rev} after={refresh} />}
          {meta && !manage && v === "personas" && <h2>Etiquetas «persona:»</h2>}
          {meta && !manage && v === "personas" && <IndexCards entries={meta.tags.filter((t) => isPerson(t.tag)).filter((t) => !tq || fold(personName(t.tag)).includes(tq)).map((t) => ({ key: t.tag, label: personName(t.tag), count: t.count, href: `#/persona/${encodeURIComponent(personName(t.tag))}`, f: { tags: [t.tag] } }))} empty="Aún no hay personas. Añade una desde el panel de edición (o etiqueta con «persona:Nombre» en la Media Library)." />}
          {meta && !manage && v === "tags" && <IndexCards entries={meta.tags.filter((t) => !isPerson(t.tag) && t.tag.toLowerCase() !== FAV).filter((t) => !tq || fold(t.tag).includes(tq)).map((t) => ({ key: t.tag, label: `#${t.tag}`, count: t.count, href: `#/tag/${encodeURIComponent(t.tag)}`, f: { tags: [t.tag] } }))} empty="Aún no hay etiquetas." />}
          {meta && !manage && v === "tags" && <AutoIndex tq={tq} rev={meta.rev} />}
          {meta && !manage && v === "colecciones" && <IndexCards entries={[{ key: "__none", label: "Sin colección", count: (meta as any).n_unassigned ?? 0, href: "#/sin-coleccion", f: { none: true } as Filter }, ...meta.collections.filter((c) => !tq || fold(c.name).includes(tq)).map((c) => ({ key: c.id, label: c.name, count: c.count, href: `#/coleccion/${c.id}`, f: { cols: [c.id] } }))]} empty="" />}
        </main>
      )}

      {/* 1.11.0: seleccionar NO abre el panel: barra compacta abajo; el panel solo con «Editar selección» */}
      {sel.size > 0 && meta && !open && (
        <div className="selbar">
          <b>{sel.size} seleccionados</b>
          <button onClick={() => selection.selectAll()} title="Ctrl+A">Todas ({total})</button>
          <button onClick={() => setSel(new Set())}>Ninguno</button>
          <button onClick={() => act("tag", { hashes: [...sel], add: [FAV] }, refresh)} title="Marcar como favoritas">♥ Favorita</button>
          <button onClick={() => setEditOpen(true)}>Etiquetar</button>
          {route.v === "coleccion" && <button onClick={() => act("remove_from", { hashes: [...sel], collection_id: (route as any).id }, () => { setSel(new Set()); refresh(); })}>Quitar de esta colección</button>}
          <button className="danger" onClick={() => startDelete([...sel], setDelPlan, () => { setSel(new Set()); refresh(); })}>Borrar</button>
          <button className="primary" onClick={() => setEditOpen((o) => !o)}>{editOpen ? "Cerrar panel" : "Editar selección"}</button>
        </div>
      )}
      {sel.size > 0 && meta && !open && editOpen && (
        <div className="bulk">
          <EditPanel items={selItems} meta={meta} onChanged={refresh} onClose={() => setEditOpen(false)} />
        </div>
      )}
      {delPlan && <DeleteDialog plan={delPlan} hashes={[...sel]} close={() => setDelPlan(null)} after={() => { setSel(new Set()); refresh(); }} />}

      {viewer !== null && meta && !solo && (
        <Viewer items={items} index={viewer} total={total} meta={meta} setIndex={setViewer} close={closeViewer} onChanged={refresh} ensure={ensure} />
      )}
      {solo && meta && (
        <Viewer items={solo.list} index={solo.i} total={solo.list.length} meta={meta} setIndex={(i) => setSolo({ ...solo, i })} close={() => setSolo(null)} onChanged={refresh} ensure={() => {}} />
      )}
      {drag && <div className="dropzone">Suelta para importar a la Media Library</div>}
      <AutoTagBar onDone={refresh} />
      <SimBar />
      <Toasts />
    </div>
  );
}

type ClickMods = { shiftKey: boolean; ctrlKey: boolean; metaKey: boolean };
function Tile({ it, sel, selMode, onOpen, onSel, onFav }: { it: Item; sel: boolean; selMode: boolean; onOpen: (e: ClickMods) => void; onSel: (e: ClickMods) => void; onFav: () => void }) {
  const fav = it.tags.some((t) => t.toLowerCase() === FAV);
  const people = it.tags.filter(isPerson).map(personName);
  return (
    <figure className={`tile ${sel ? "sel" : ""} ${selMode ? "selmode" : ""}`} onClick={(e) => { if (e.shiftKey) e.preventDefault(); onOpen(e); }} onMouseDown={(e) => { if (e.shiftKey) e.preventDefault(); }}>
      <Thumb hash={it.hash} alt={it.name} />
      {it.kind && it.kind !== "image" && <span className="badge">▶ {fmtDur(it.dur)}</span>}
      {it.best_t != null && <span className="badge tbest" title="Mejor coincidencia en el vídeo (el visor abre ahí)">⏱ {fmtT(it.best_t)}</span>}
      {it.virtual && <span className="badge v" title="Copia virtual">✂</span>}
      {it.missing && <span className="badge warn">archivo no encontrado</span>}
      {it.origin === "ai" && <span className="badge ia" title="Generada con IA">IA</span>}
      <button className={`hfav ${fav ? "on" : ""}`} onClick={(e) => { e.stopPropagation(); onFav(); }} title="Favorita">{fav ? "♥" : "♡"}</button>
      <button className="cb" onClick={(e) => { e.stopPropagation(); onSel(e); }} title="Seleccionar (Mayús = rango)">{sel ? "✓" : ""}</button>
      <figcaption>{people.length ? <b>{people.join(", ")}</b> : null}<span>{it.name}</span></figcaption>
    </figure>
  );
}

// 1.9.2: etiquetas automáticas (las del autoetiquetado, guardadas aparte de las manuales): mismos recuentos que el
// panel de facetas de la Media Library (at_facets). Clic = filtrar por esa etiqueta (f.atags).
function AutoIndex({ tq, rev }: { tq: string; rev: number }) {
  const [rows, setRows] = useState<Entry[] | null>(null);
  const [all, setAll] = useState(false);
  const [atRev, setAtRev] = useState(0);
  useEffect(() => { const h = () => setAtRev((x) => x + 1); window.addEventListener(AT_DONE, h); return () => window.removeEventListener(AT_DONE, h); }, []);
  useEffect(() => {
    call("at_facets", { f: {}, tax: true }).then((r) => {
      if (!r.ok) return;
      setTax(r.tax);
      setRows(Object.entries(r.facets || {}).filter(([id]) => isLeafTag(id)).sort((a: any, b: any) => b[1] - a[1])
        .map(([id, n]: any) => ({ key: "auto:" + id, label: autoLabel(id), count: n, href: `#/auto/${encodeURIComponent(id)}`, f: { atags: [id] } })));
    }).catch(() => setRows([]));
  }, [rev, atRev]);
  if (!rows || !rows.length) return null;
  const vis = rows.filter((e) => !tq || fold(e.label).includes(tq));
  return (<>
    <div className="bar"><h2>🏷 Etiquetas automáticas <small className="muted">{rows.length}</small></h2></div>
    <IndexCards entries={all || tq ? vis : vis.slice(0, 48)} empty="Ninguna coincide." />
    {!all && !tq && vis.length > 48 && <p><button onClick={() => setAll(true)}>Ver las {vis.length}</button></p>}
  </>);
}

interface Entry { key: string; label: string; count: number; href: string; f: Filter }
function IndexCards({ entries, empty }: { entries: Entry[]; empty: string }) {
  if (!entries.length) return <p className="empty">{empty}</p>;
  return <div className="cards">{entries.map((e) => <Card key={e.key} e={e} />)}</div>;
}
function Card({ e }: { e: Entry }) {
  const [hs, setHs] = useState<string[]>([]);
  useEffect(() => { call("query", { f: e.f, limit: 4 }).then((r) => setHs(r.page.items.map((i: Item) => i.hash))).catch(() => {}); }, [e.key, e.count]);
  return (
    <a className="card" href={e.href}>
      <div className={`cover n${Math.min(hs.length, 4)}`}>{hs.map((h) => <Thumb key={h} hash={h} />)}</div>
      <div className="cmeta"><b>{e.label}</b><small>{e.count}</small></div>
    </a>
  );
}

// tipo de medio: tres interruptores (varios a la vez; todos encendidos = todo). Sin audio en la biblioteca: icono apagado.
const ICONS: Record<string, JSX.Element> = {
  image: <svg viewBox="0 0 24 24"><rect x="3" y="5" width="18" height="14" rx="2" /><circle cx="9" cy="10" r="1.8" /><path d="M4 18l5-5 4 4 3-3 4 4" /></svg>,
  video: <svg viewBox="0 0 24 24"><rect x="3" y="6" width="13" height="12" rx="2" /><path d="M16 10l5-3v10l-5-3z" /></svg>,
  audio: <svg viewBox="0 0 24 24"><path d="M9 18V6l11-2v12" /><circle cx="6.5" cy="18" r="2.5" /><circle cx="17.5" cy="16" r="2.5" /></svg>,
};
const KLABEL: Record<string, string> = { image: "Fotos", video: "Vídeos", audio: "Audio" };
function KindToggles({ kinds, setKinds, counts, libAudio }: { kinds: string[]; setKinds: (k: string[]) => void; counts: Record<string, number>; libAudio: number }) {
  const all = ["image", "video", "audio"];
  const active = (k: string) => kinds.includes(k);             // sin filtro (todos) = ninguno pulsado
  const SOLO: Record<string, string> = { image: "solo fotos", video: "solo vídeos", audio: "solo audio" };
  const press = (k: string, combine: boolean) => {
    let next: string[];
    if (combine) next = kinds.includes(k) ? kinds.filter((x) => x !== k) : [...kinds, k];   // Ctrl/Cmd: combinar
    else next = kinds.length === 1 && kinds[0] === k ? [] : [k];                            // clic: solo ese; otra vez: todos
    setKinds(!next.length || next.length === all.length ? [] : all.filter((x) => next.includes(x)));
  };
  return (
    <span className="kinds" role="group" aria-label="Tipo de medio">
      {all.map((k) => {
        const n = k === "video" ? (counts.video || 0) + (counts.mask || 0) : counts[k] || 0;
        const off = k === "audio" && !libAudio;
        const solo = kinds.length === 1 && kinds[0] === k;
        return <button key={k} className={`kt ${active(k) && !off ? "on" : ""}`} disabled={off} aria-pressed={active(k)}
          onClick={(e) => press(k, e.ctrlKey || e.metaKey)}
          title={off ? "Sin audio" : `${KLABEL[k]} · ${n} — Clic: ${solo ? "volver a todos" : SOLO[k]} · Ctrl+clic: combinar`}>{ICONS[k]}<small>{off ? "" : n}</small></button>;
      })}
    </span>
  );
}

// 1.10.0: IA / Real, same semantics as the type toggles (clic = solo ese, otra vez = todos; Ctrl+clic = combinar)
function OriginToggles({ origins, setOrigins, counts }: { origins: string[]; setOrigins: (k: string[]) => void; counts: Record<string, number> }) {
  const all = ["ai", "real"], L: Record<string, string> = { ai: "IA", real: "Real" };
  const press = (k: string, combine: boolean) => {
    let next: string[];
    if (combine) next = origins.includes(k) ? origins.filter((x) => x !== k) : [...origins, k];
    else next = origins.length === 1 && origins[0] === k ? [] : [k];
    setOrigins(!next.length || next.length === all.length ? [] : all.filter((x) => next.includes(x)));
  };
  return (
    <span className="kinds origins" role="group" aria-label="Origen">
      {all.map((k) => {
        const solo = origins.length === 1 && origins[0] === k, n = counts[k] || 0;
        return <button key={k} className={`kt ${origins.includes(k) ? "on" : ""}`} aria-pressed={origins.includes(k)} onClick={(e) => press(k, e.ctrlKey || e.metaKey)}
          title={`${L[k]} · ${n} — Clic: ${solo ? "volver a todos" : k === "ai" ? "solo IA" : "solo reales"} · Ctrl+clic: combinar · también origin:ia / origin:real en la búsqueda`}><b>{L[k]}</b><small>{n}</small></button>;
      })}
    </span>
  );
}

function crumbsOf(meta: any, r: any) {
  const f = meta?.folders.find((x: any) => x.id === r.fid);
  const parts = r.rel ? r.rel.split("/") : [];
  return <>{[<a key="" href={nodeHref({ fid: r.fid, rel: "" })}>{f?.path || folderLabel(f)}</a>, ...parts.map((p: string, i: number) => <span key={i}> / <a href={nodeHref({ fid: r.fid, rel: parts.slice(0, i + 1).join("/") })}>{p}</a></span>)]}</>;
}

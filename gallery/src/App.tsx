import Folders, { folderLabel, nodeHref } from "./Folders";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { FAV, Filter, Item, Meta, PERSON, call, fold, isPerson, metaOf, personName, personTag, upload } from "./api";
import { ManageList } from "./Manage";
import { act } from "./actions";
import EditPanel from "./EditPanel";
import Viewer from "./Viewer";
import Grid, { Section } from "./Grid";
import Omni, { Chip, chipsFilter } from "./Omni";
import { Thumb, Toasts, fmtDur, toast } from "./ui";

// ---------------- rutas (hash): fáciles de ampliar añadiendo un caso en parseRoute + una vista
type Route =
  | { v: "explorar" } | { v: "favoritas" } | { v: "videos" } | { v: "sin" } | { v: "buscar" }
  | { v: "personas" } | { v: "persona"; name: string }
  | { v: "tags" } | { v: "tag"; tag: string }
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
    case "etiquetas": return { v: "tags" };
    case "tag": return b ? { v: "tag", tag: b } : { v: "tags" };
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
  const [viewer, setViewer] = useState<number | null>(null);
  const [solo, setSolo] = useState<{ list: Item[]; i: number } | null>(null);   // visor abierto desde la búsqueda
  const [selMode, setSelMode] = useState(false);
  const [sel, setSel] = useState<Set<string>>(new Set());
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

  const routeFilter = (r: Route): Filter | null => {
    switch (r.v) {
      case "explorar": return {};
      case "favoritas": return { tags: [FAV] };
      case "videos": return { kind: "video" };
      case "sin": return { none: true };
      case "buscar": return chipsFilter(chips);
      case "persona": return { tags: [personTag(r.name, meta?.tags || [])] };
      case "tag": return { tags: [r.tag] };
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
    const out: Filter = { ...base, sort };
    if (kinds.length && kinds.length < 3 && !base.kind) out.kinds = kinds;
    if (extraTags.length) out.tags = [...(base.tags || []), ...extraTags];
    return out;
  }, [baseKey, kinds, sort, extraTags]);
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
  const selItems = loaded.filter((i) => sel.has(i.hash));
  const open = viewer !== null || solo !== null;
  useEffect(() => {
    const k = (e: KeyboardEvent) => {
      if (open || (e.target as HTMLElement).closest("input,textarea,select")) return;
      if (e.key === "s") setSelMode((m) => !m);
      else if (e.key === "Escape") { setSel(new Set()); setSelMode(false); }
      else if (e.key === "a" && (e.ctrlKey || e.metaKey) && selMode) { e.preventDefault(); setSel(new Set(loaded.map((i) => i.hash))); }
      else if (e.key === "/") { e.preventDefault(); document.getElementById("q")?.focus(); }
    };
    window.addEventListener("keydown", k); return () => window.removeEventListener("keydown", k);
  }, [open, selMode, loaded]);

  const title = (() => {
    switch (route.v) {
      case "explorar": return "Explorar";
      case "favoritas": return "Favoritas";
      case "videos": return "Vídeos";
      case "sin": return "Sin colección";
      case "buscar": return "Búsqueda";
      case "personas": return "Personas";
      case "persona": return route.name;
      case "tags": return "Etiquetas";
      case "tag": return `#${route.tag}`;
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
          {nav("#/etiquetas", "Etiquetas", v === "tags" || v === "tag")}
          {nav("#/colecciones", "Colecciones", v === "colecciones" || v === "coleccion")}
          {nav("#/carpetas", "Carpetas", v === "carpetas" || v === "carpeta")}
          {nav("#/favoritas", "♥ Favoritas", v === "favoritas")}
          {nav("#/videos", "Vídeos", v === "videos")}
        </nav>
        <Omni meta={meta} chips={chips} setChips={(c) => { setChips(c); goSearch(); }} text={text} setText={setText} onSearch={goSearch}
          onOpenItem={(it, list) => setSolo({ list, i: Math.max(0, list.findIndex((x) => x.hash === it.hash)) })} />
        <button onClick={() => fileIn.current?.click()} title="O arrastra archivos a la ventana">⤒ Subir</button>
        <input ref={fileIn} type="file" multiple hidden accept="image/*,video/*,audio/*" onChange={(e) => { doUpload([...(e.target.files || [])]); e.target.value = ""; }} />
        <a className="ml" href="/" title="Abrir WanGP / Media Library">WanGP ↗</a>
      </header>

      {filter ? (
        <div className={fside ? "withside" : ""}>
        {fside && meta && <Folders meta={meta} node={route.v === "carpeta" ? { fid: route.fid, rel: route.rel } : null} onChanged={refresh} />}
        <main>
          <div className="bar">
            <h1>{(v === "carpetas" || v === "carpeta") && <button className="sidetg" onClick={() => setFopen(!fopen)} title="Mostrar/ocultar el árbol de carpetas">{fopen ? "◧" : "☰"}</button>}{title} <small>{total}</small></h1>
            {v === "carpeta" && <p className="muted crumbs">{crumbsOf(meta, route)}</p>}
            {v === "persona" && <p className="muted">Etiqueta: <code>{filter.tags?.[0] || PERSON + route.name}</code></p>}
            {v === "buscar" && !chips.length && <p className="muted">Escribe arriba: personas, colecciones, etiquetas o nombres de archivo. Varios filtros se combinan (Y).</p>}
            <div className="tools">
              {!base?.kind && <KindToggles kinds={kinds} setKinds={setKinds} counts={kc} libAudio={meta?.kinds?.audio ?? kc.audio ?? 0} />}
              <select value={sort} onChange={(e) => setSort(e.target.value)} title={dateNote || "Orden (el índice de la derecha lo sigue)"}>
                {SORTS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
              </select>
              <input type="range" min={120} max={420} value={size} onChange={(e) => setSize(+e.target.value)} title="Tamaño de miniaturas" />
              <button className={selMode ? "on" : ""} onClick={() => { setSelMode(!selMode); setSel(new Set()); }} title="Seleccionar (S)">☑ Seleccionar</button>
            </div>
          </div>
          {v === "buscar" && chips.length > 0 && (
            <div className="facets">
              {chips.map((c, i) => <button key={c.k + c.v} className="chip on" onClick={() => setChips(chips.filter((_, j) => j !== i))}>{c.k === "tag" ? "#" : c.k === "col" ? "▣ " : c.k === "persona" ? "👤 " : ""}{c.label} ×</button>)}
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
                <Tile it={it} sel={sel.has(it.hash)} selMode={selMode}
                  onOpen={() => (selMode ? toggleSel(it.hash) : setViewer(i))} onSel={() => { setSelMode(true); toggleSel(it.hash); }}
                  onFav={() => act("tag", { hashes: [it.hash], ...(it.tags.some((t) => t.toLowerCase() === FAV) ? { remove: [FAV] } : { add: [FAV] }) }, refresh, { quiet: true })} />
              ) : <div className="tile"><div className="ph" /></div>} />
          )}
          {!total && ver > 1 && <p className="empty">{v === "buscar" ? "Sin resultados." : "Nada por aquí todavía. Arrastra imágenes o vídeos a la ventana para importarlos."}</p>}
        </main>
        </div>
      ) : (
        <main>
          <div className="bar"><h1>{title}</h1>{tq && <p className="muted">filtrando por «{text}»</p>}
            {(v === "tags" || v === "personas" || v === "colecciones") && <button className="ml" onClick={() => setManage(!manage)}>{manage ? "Ver tarjetas" : "Gestionar"}</button>}</div>
          {meta && manage && v === "tags" && <ManageList kind="tag" rows={meta.tags.filter((t) => !isPerson(t.tag) && t.tag.toLowerCase() !== FAV).filter((t) => !tq || fold(t.tag).includes(tq)).map((t) => ({ key: t.tag, label: t.tag, count: t.count }))} after={refresh} />}
          {meta && manage && v === "personas" && <ManageList kind="persona" rows={meta.tags.filter((t) => isPerson(t.tag)).filter((t) => !tq || fold(personName(t.tag)).includes(tq)).map((t) => ({ key: t.tag, label: personName(t.tag), count: t.count }))} after={refresh} />}
          {meta && manage && v === "colecciones" && <ManageList kind="col" rows={meta.collections.filter((c) => !tq || fold(c.name).includes(tq)).map((c) => ({ key: c.id, label: c.name, count: c.count }))} after={refresh} />}
          {meta && !manage && v === "personas" && <IndexCards entries={meta.tags.filter((t) => isPerson(t.tag)).filter((t) => !tq || fold(personName(t.tag)).includes(tq)).map((t) => ({ key: t.tag, label: personName(t.tag), count: t.count, href: `#/persona/${encodeURIComponent(personName(t.tag))}`, f: { tags: [t.tag] } }))} empty="Aún no hay personas. Añade una desde el panel de edición (o etiqueta con «persona:Nombre» en la Media Library)." />}
          {meta && !manage && v === "tags" && <IndexCards entries={meta.tags.filter((t) => !isPerson(t.tag) && t.tag.toLowerCase() !== FAV).filter((t) => !tq || fold(t.tag).includes(tq)).map((t) => ({ key: t.tag, label: `#${t.tag}`, count: t.count, href: `#/tag/${encodeURIComponent(t.tag)}`, f: { tags: [t.tag] } }))} empty="Aún no hay etiquetas." />}
          {meta && !manage && v === "colecciones" && <IndexCards entries={[{ key: "__none", label: "Sin colección", count: (meta as any).n_unassigned ?? 0, href: "#/sin-coleccion", f: { none: true } as Filter }, ...meta.collections.filter((c) => !tq || fold(c.name).includes(tq)).map((c) => ({ key: c.id, label: c.name, count: c.count, href: `#/coleccion/${c.id}`, f: { cols: [c.id] } }))]} empty="" />}
        </main>
      )}

      {selMode && sel.size > 0 && meta && !open && (
        <div className="bulk">
          <div className="bulkbar">
            <b>{sel.size} seleccionados</b>
            <button onClick={() => setSel(new Set(loaded.map((i) => i.hash)))}>Todos los cargados</button>
            <button onClick={() => setSel(new Set())}>Ninguno</button>
            {route.v === "coleccion" && <button onClick={() => act("remove_from", { hashes: [...sel], collection_id: (route as any).id }, () => { setSel(new Set()); refresh(); })}>Quitar de esta colección</button>}
          </div>
          <EditPanel items={selItems} meta={meta} onChanged={refresh} onClose={() => setSel(new Set())} />
        </div>
      )}

      {viewer !== null && meta && !solo && (
        <Viewer items={items} index={viewer} total={total} meta={meta} setIndex={setViewer} close={() => setViewer(null)} onChanged={refresh} ensure={ensure} />
      )}
      {solo && meta && (
        <Viewer items={solo.list} index={solo.i} total={solo.list.length} meta={meta} setIndex={(i) => setSolo({ ...solo, i })} close={() => setSolo(null)} onChanged={refresh} ensure={() => {}} />
      )}
      {drag && <div className="dropzone">Suelta para importar a la Media Library</div>}
      <Toasts />
    </div>
  );
}

function Tile({ it, sel, selMode, onOpen, onSel, onFav }: { it: Item; sel: boolean; selMode: boolean; onOpen: () => void; onSel: () => void; onFav: () => void }) {
  const fav = it.tags.some((t) => t.toLowerCase() === FAV);
  const people = it.tags.filter(isPerson).map(personName);
  return (
    <figure className={`tile ${sel ? "sel" : ""} ${selMode ? "selmode" : ""}`} onClick={onOpen}>
      <Thumb hash={it.hash} alt={it.name} />
      {it.kind && it.kind !== "image" && <span className="badge">▶ {fmtDur(it.dur)}</span>}
      {it.virtual && <span className="badge v" title="Copia virtual">✂</span>}
      {it.missing && <span className="badge warn">archivo no encontrado</span>}
      <button className={`hfav ${fav ? "on" : ""}`} onClick={(e) => { e.stopPropagation(); onFav(); }} title="Favorita">{fav ? "♥" : "♡"}</button>
      <button className="cb" onClick={(e) => { e.stopPropagation(); onSel(); }} title="Seleccionar">{sel ? "✓" : ""}</button>
      <figcaption>{people.length ? <b>{people.join(", ")}</b> : null}<span>{it.name}</span></figcaption>
    </figure>
  );
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

function crumbsOf(meta: any, r: any) {
  const f = meta?.folders.find((x: any) => x.id === r.fid);
  const parts = r.rel ? r.rel.split("/") : [];
  return <>{[<a key="" href={nodeHref({ fid: r.fid, rel: "" })}>{f?.path || folderLabel(f)}</a>, ...parts.map((p: string, i: number) => <span key={i}> / <a href={nodeHref({ fid: r.fid, rel: parts.slice(0, i + 1).join("/") })}>{p}</a></span>)]}</>;
}

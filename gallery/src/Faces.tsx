// 1.10.0: Personas estilo «Fotos» del iPhone. Solo llama a las acciones compartidas face_* / person_* (reflib_core/faces.py,
// FACES_API.md), las mismas que usa la Media Library (reflib_faces.js). Aquí no hay lógica de caras propia: solo vista.
import { useCallback, useEffect, useRef, useState } from "react";
import { call, fold } from "./api";
import { act } from "./actions";
import { toast, Thumb } from "./ui";

export interface Face { id: string; hash: string; n: number; model: string; box?: number[] | null; bbox: number[] | null; det?: number | null; w: number; h: number; score?: number; person?: string; cluster?: string; thumb?: string }
export interface Person { id: string; name: string; tag: string; count: number; items: number; cover: Face | null; seeded?: boolean }

// ---------------------------------------------------------------- recorte de cara
// Miniatura compartida del servidor (FACE.thumb = GET /reflib/face_thumb/<id>.jpg), la misma que usa la Media Library.
const sized = (u: string, size: number) => u.replace(/([?&])size=\d+/, `$1size=${size}`) + (/[?&]size=/.test(u) ? "" : (u.includes("?") ? "&" : "?") + `size=${size}`);
export function FaceImg({ f, size = 160, className }: { f: Face | null; size?: number; className?: string }) {
  const [bad, setBad] = useState(false);
  if (!f) return <div className={`face none ${className || ""}`}>👤</div>;
  if (!f.thumb || bad) return <Thumb hash={f.hash} className={`face ${className || ""}`} />;
  return <img className={`face ${className || ""}`} src={sized(f.thumb, size)} alt="" loading="lazy" decoding="async" onError={() => setBad(true)} />;
}

// ---------------------------------------------------------------- datos compartidos
export function usePersons(rev: number) {
  const [persons, setPersons] = useState<Person[]>([]);
  const load = useCallback(() => call("person_list", { limit: 1000 }).then((r) => r.ok && setPersons(r.persons || [])).catch(() => {}), []);
  useEffect(() => { load(); }, [rev, load]);
  return { persons, reload: load };
}
const errMsg = (r: any) => r?.code === "faces_busy" ? "Agrupando caras: espera unos segundos y vuelve a intentarlo." : r?.code === "faces_no_index" ? "Aún no hay caras calculadas: lanza «Calcular caras» en ⧉ Similitud." : (r?.error || "Error");

// ---------------------------------------------------------------- página Personas
export function PersonasPage({ tq, rev, after }: { tq: string; rev: number; after: () => void }) {
  const [st, setSt] = useState<any>(null);
  const [clusters, setClusters] = useState<any[]>([]);
  const [ctotal, setCtotal] = useState(0);
  const [limit, setLimit] = useState(30);
  const [sel, setSel] = useState<Set<string>>(new Set());
  const [err, setErr] = useState("");
  const [tick, setTick] = useState(0);
  const { persons, reload } = usePersons(rev + tick);
  const refresh = () => { setTick((t) => t + 1); after(); };
  useEffect(() => {
    let dead = false, t: any;
    const poll = async () => {
      const r = await call("face_status").catch(() => null);
      if (dead || !r) return; setSt(r.faces);
      if (r.faces?.running) t = setTimeout(poll, 1000); else if (st?.running) setTick((x) => x + 1);
    };
    poll(); return () => { dead = true; clearTimeout(t); };
  }, [tick, st?.running]);
  useEffect(() => {
    call("face_clusters", { limit, faces_per: 6 }).then((r) => { if (r.ok) { setClusters(r.clusters || []); setCtotal(r.total || 0); setErr(""); } else setErr(errMsg(r)); }).catch(() => {});
  }, [limit, tick, rev]);
  const names = persons.map((p) => p.name);
  const assign = async (cids: string[], name: string) => {
    name = name.trim(); if (!name) return;
    const p = persons.find((x) => fold(x.name) === fold(name));
    setClusters((cs) => cs.filter((c) => !cids.includes(c.id)));   // optimista
    const r = await act("face_assign", p ? { person: p.id, clusters: cids } : { name, clusters: cids }, refresh);
    if (!r || !r.ok) setTick((t) => t + 1);
    setSel(new Set());
  };
  const shown = persons.filter((p) => !tq || fold(p.name).includes(tq));
  return (
    <div className="personas">
      <div className="fstat muted">
        {st ? <>{st.faces ?? 0} caras · {st.persons ?? 0} personas · {st.unassigned ?? 0} sin nombre en {st.clusters ?? 0} grupos{st.running ? ` · agrupando ${st.done}/${st.total}…` : ""}</> : "…"}
        <button disabled={!!st?.running} onClick={() => act("face_cluster_run", {}, refresh, { quiet: true })} title="Agrupa las caras nuevas (incremental)">↻ Agrupar caras</button>
        <FaceSettings />
        <button disabled={!!st?.running} onClick={() => window.confirm("¿Reagrupar todas las caras sin nombre? (los grupos sin nombre pueden cambiar)") && act("face_cluster_run", { full: true }, refresh, { quiet: true })}>Reagrupar todo</button>
      </div>
      <div className="pgrid">
        {shown.map((p) => (
          <a key={p.id} className="pcard" href={`#/persona/${encodeURIComponent(p.name)}`}>
            <FaceImg f={p.cover} size={200} className="round" />
            <b>{p.name}</b><small>{p.items} {p.seeded ? "· auto" : ""}</small>
          </a>))}
        {!shown.length && <p className="muted">Aún no hay personas con caras. Pon nombre a un grupo de «Caras sin nombre».</p>}
      </div>
      <h2>Caras sin nombre <small>{ctotal}</small>
        {sel.size >= 2 && <button onClick={async () => { await act("face_merge", { clusters: [...sel] }, refresh); setSel(new Set()); }}>⇄ Unir {sel.size} grupos</button>}
        {sel.size >= 1 && <NameBox names={names} placeholder={`Nombre para ${sel.size} grupo(s)…`} onName={(n) => assign([...sel], n)} />}
      </h2>
      {err && <p className="muted">{err}</p>}
      <datalist id="pnames">{names.map((n) => <option key={n} value={n} />)}</datalist>
      <div className="cgrid">
        {clusters.map((c) => (
          <div key={c.id} className={`ccard ${sel.has(c.id) ? "on" : ""}`}>
            <div className="cfaces" onClick={() => setSel((s) => { const n = new Set(s); n.has(c.id) ? n.delete(c.id) : n.add(c.id); return n; })} title="Clic: seleccionar (para unir o nombrar varios)">
              <FaceImg f={c.cover} size={160} className="big round" />
              <div className="mini">{(c.faces || []).filter((f: Face) => f.id !== c.cover?.id).slice(0, 5).map((f: Face) => <FaceImg key={f.id} f={f} size={64} className="round" />)}</div>
            </div>
            <small>{c.size} caras</small>
            <NameBox names={names} placeholder="¿Quién es?" onName={(n) => assign([c.id], n)} />
          </div>))}
      </div>
      {clusters.length < ctotal && <button className="more" onClick={() => setLimit(limit + 30)}>Ver más grupos</button>}
    </div>
  );
}

function NameBox({ names, placeholder, onName }: { names: string[]; placeholder: string; onName: (n: string) => void }) {
  const [v, setV] = useState("");
  return <input className="namebox" list="pnames" value={v} placeholder={placeholder} onChange={(e) => setV(e.target.value)}
    onKeyDown={(e) => { if (e.key === "Enter" && v.trim()) { onName(v); setV(""); } }}
    onBlur={() => { if (v.trim() && names.some((n) => fold(n) === fold(v))) { onName(v); setV(""); } }} />;
}

// ---------------------------------------------------------------- cabecera de una persona
export function PersonHeader({ name, rev, after }: { name: string; rev: number; after: () => void }) {
  const [tick, setTick] = useState(0);
  const { persons } = usePersons(rev + tick);
  const p = persons.find((x) => fold(x.name) === fold(name));
  const [sug, setSug] = useState<Face[]>([]);
  const [showFaces, setShowFaces] = useState(false);
  const [faces, setFaces] = useState<Face[]>([]);
  const [fsel, setFsel] = useState<Set<string>>(new Set());
  const refresh = () => { setTick((t) => t + 1); after(); };
  const pid = p?.id;
  useEffect(() => { if (pid) call("face_suggest", { person: pid, limit: 20 }).then((r) => setSug(r.ok ? r.faces || [] : [])).catch(() => {}); else setSug([]); }, [pid, tick]);
  useEffect(() => { if (pid && showFaces) call("person_get", { person: pid, limit: 500 }).then((r) => r.ok && setFaces(r.faces || [])); }, [pid, showFaces, tick]);
  const cur = sug[0];
  const answer = useCallback(async (yes: boolean) => {
    if (!cur || !pid) return;
    setSug((s) => s.slice(1));   // optimista: la siguiente sugerencia al instante
    const r = await call(yes ? "face_confirm" : "face_reject", { person: pid, faces: [cur.id] }).catch(() => null);
    if (!r || !r.ok) { toast(errMsg(r), "err"); setSug((s) => [cur, ...s]); return; }
    if (yes) after();
    if (sug.length <= 1) setTick((t) => t + 1);
  }, [cur, pid, sug.length]);
  const keys = useRef(answer); keys.current = answer;
  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement)?.closest("input,textarea,select") || e.ctrlKey || e.metaKey || e.altKey) return;
      if (document.querySelector(".viewer")) return;
      const k = e.key.toLowerCase();
      if (k === "y" || k === "s") { e.preventDefault(); keys.current(true); }
      else if (k === "n") { e.preventDefault(); keys.current(false); }
    };
    window.addEventListener("keydown", h); return () => window.removeEventListener("keydown", h);
  }, []);
  if (!p) return null;
  const others = persons.filter((x) => x.id !== p.id);
  const fs = [...fsel];
  return (
    <div className="phead">
      <div className="prow">
        <FaceImg f={p.cover} size={200} className="round big" />
        <div className="pact">
          <button onClick={() => { const n = window.prompt("Nuevo nombre", p.name); if (n && n.trim() && n.trim() !== p.name) act("person_rename", { person: p.id, name: n.trim() }, () => { location.hash = `#/persona/${encodeURIComponent(n.trim())}`; refresh(); }); }}>✎ Renombrar</button>
          {others.length > 0 && <select value="" onChange={(e) => { const o = others.find((x) => x.id === e.target.value); if (o && window.confirm(`¿Unir «${o.name}» en «${p.name}»?`)) act("face_merge", { persons: [p.id, o.id], into: p.id }, refresh); }}>
            <option value="">⇄ Unir con…</option>{others.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}</select>}
          <button onClick={() => window.confirm(`¿Olvidar a «${p.name}»? Las fotos no se borran (se puede deshacer 5 min).`) && act("person_delete", { person: p.id }, () => { location.hash = "#/personas"; after(); })}>🗑 Olvidar persona</button>
          <button className={showFaces ? "on" : ""} onClick={() => setShowFaces(!showFaces)}>☺ Caras ({p.count})</button>
        </div>
        {cur && (
          <div className="suggest">
            <FaceImg f={cur} size={160} className="round big" />
            <div><b>¿Es esta también {p.name}?</b>
              <div className="yn"><button className="yes" onClick={() => answer(true)}>Sí <kbd>Y</kbd></button><button onClick={() => answer(false)}>No <kbd>N</kbd></button></div>
              <small className="muted">{sug.length} sugerencia(s){cur.score != null ? ` · parecido ${(cur.score * 100).toFixed(0)}%` : ""}</small></div>
          </div>)}
      </div>
      {showFaces && (
        <div className="pfaces">
          <div className="tools">{fs.length > 0 && <>
            <button onClick={async () => { await act("face_split", { person: p.id, faces: fs }, refresh); setFsel(new Set()); }} title="Las caras pasan a un grupo nuevo sin nombre">✂ Separar {fs.length}</button>
            <button onClick={async () => { await act("face_unassign", { faces: fs }, refresh); setFsel(new Set()); }}>× Quitar {fs.length}</button>
            {fs.length === 1 && <button onClick={() => act("person_set_cover", { person: p.id, face: fs[0] }, refresh)}>★ Portada</button>}</>}</div>
          <div className="fgrid">{faces.map((f) => (
            <div key={f.id} className={`fcell ${fsel.has(f.id) ? "on" : ""}`} onClick={() => setFsel((s) => { const n = new Set(s); n.has(f.id) ? n.delete(f.id) : n.add(f.id); return n; })}>
              <FaceImg f={f} size={96} className="round" /></div>))}</div>
        </div>)}
    </div>
  );
}

// ---------------------------------------------------------------- caras de un elemento (panel de edición)
export function ItemFaces({ hash, onChanged }: { hash: string; onChanged: () => void }) {
  const [faces, setFaces] = useState<Face[] | null>(null);
  const [hot, setHot] = useState("");
  const [tick, setTick] = useState(0);
  const { persons } = usePersons(tick);
  useEffect(() => { let live = true; call("face_for_item", { hash }).then((r) => live && setFaces(r.ok ? r.items?.[hash]?.faces || [] : [])).catch(() => live && setFaces([])); return () => { live = false; }; }, [hash, tick]);
  if (!faces || !faces.length) return null;
  const done = () => { setTick((t) => t + 1); onChanged(); };
  const byId = new Map(persons.map((p) => [p.id, p]));
  return (
    <div className="ifaces"><h4>Caras</h4>
      <FaceBoxes hash={hash} faces={faces} hot={hot} />
      <datalist id="pnames-i">{persons.map((p) => <option key={p.id} value={p.name} />)}</datalist>
      {faces.map((f) => { const who = f.person ? byId.get(f.person) : null; return (
        <div key={f.id} className="iface" onMouseEnter={() => setHot(f.id)} onMouseLeave={() => setHot("")}>
          <FaceImg f={f} size={64} className="round" />
          {who ? <><a href={`#/persona/${encodeURIComponent(who.name)}`}>{who.name}</a><button title="Quitar esta cara de la persona" onClick={() => act("face_unassign", { faces: [f.id] }, done, { quiet: true })}>×</button></>
            : <input className="namebox" list="pnames-i" placeholder="¿Quién es?" onKeyDown={(e) => {
                const v = (e.target as HTMLInputElement).value.trim(); if (e.key !== "Enter" || !v) return;
                const p = persons.find((x) => fold(x.name) === fold(v));
                act("face_assign", p ? { person: p.id, faces: [f.id] } : { name: v, faces: [f.id] }, done, { quiet: true });
              }} />}
        </div>); })}
    </div>
  );
}

// ---------------------------------------------------------------- ajustes (face_auto_cluster / face_min_size, compartidos con la Media Library)
function FaceSettings() {
  const [s, setS] = useState<any>(null);
  useEffect(() => { call("face_settings").then((r) => r.ok && setS(r.settings)).catch(() => {}); }, []);
  if (!s) return null;
  const save = (patch: any) => { setS({ ...s, ...patch }); act("face_settings", { settings: patch }, () => {}, { quiet: true }).then((r: any) => r?.settings && setS(r.settings)); };
  return (
    <span className="fset">
      <label title="Agrupa automáticamente las caras nuevas al indexar"><input type="checkbox" checked={s.face_auto_cluster !== false} onChange={(e) => save({ face_auto_cluster: e.target.checked })} /> Auto</label>
      <label title="Ignora caras más pequeñas (px)">mín <input type="number" min={0} max={1024} step={8} defaultValue={s.face_min_size ?? 40}
        onBlur={(e) => { const v = Math.max(0, Math.min(1024, parseInt(e.target.value) || 0)); if (v !== s.face_min_size) save({ face_min_size: v }); }} /> px</label>
    </span>
  );
}

// Recuadros de las caras sobre la imagen (box = fracción 0..1 del registro simperf; null = sin posición)
function FaceBoxes({ hash, faces, hot }: { hash: string; faces: Face[]; hot: string }) {
  const boxed = faces.filter((f) => f.box && f.box.length === 4);
  if (!boxed.length) return null;
  return (
    <div className="fboxes"><Thumb hash={hash} className="fbimg" />
      {boxed.map((f) => { const [x, y, w, h] = f.box!; return <div key={f.id} className={`fbox ${hot === f.id ? "hot" : ""}`}
        style={{ left: `${x * 100}%`, top: `${y * 100}%`, width: `${w * 100}%`, height: `${h * 100}%` }} />; })}
    </div>
  );
}

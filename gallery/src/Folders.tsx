import { useEffect, useMemo, useRef, useState } from "react";
import { Meta, call } from "./api";
import { act } from "./actions";
import { toast } from "./ui";

// Carpetas vigiladas: exactamente las mismas que la Media Library (meta.folders + meta.tree) y las mismas acciones
// del puente (folder_add, folder_rescan, rescan, folder_remove, folder_recursive, folder_excluded/restore, pause_index, browse).
export interface Node { fid: string; rel: string }
const PSEUDO: Record<string, string> = { video_library: "🎬 Librería de vídeos", virtual: "⧉ Copias virtuales", masks: "🎭 Máscaras" };
export const folderLabel = (f: any) => (f?.pseudo ? PSEUDO[f.name] || f.name : f?.name || f?.path || "?");
export const nodeHref = (n: Node) => `#/carpeta/${encodeURIComponent(n.fid)}/${encodeURIComponent(n.rel)}`;

export default function Folders({ meta, node, onChanged }: { meta: Meta; node: Node | null; onChanged: () => void }) {
  const tree: Record<string, Record<string, number[]>> = (meta as any).tree || {};
  const [open, setOpen] = useState<Set<string>>(() => new Set(JSON.parse(localStorage.getItem("gal.fopen") || "[]")));
  const [adding, setAdding] = useState(false);
  const [scan, setScan] = useState<any>(null);
  const [excl, setExcl] = useState<any | null>(null);
  const poll = useRef<number>(0);
  useEffect(() => { localStorage.setItem("gal.fopen", JSON.stringify([...open])); }, [open]);
  // la rama del nodo activo siempre abierta
  useEffect(() => {
    if (!node) return;
    const parts = node.rel ? node.rel.split("/") : [];
    setOpen((o) => { const x = new Set(o); for (let k = 0; k < parts.length; k++) x.add(node.fid + "|" + parts.slice(0, k).join("/")); return x; });
  }, [node?.fid, node?.rel]);

  const watchScan = () => {
    clearTimeout(poll.current);
    const tick = async () => {
      try {
        const r: any = await call("scan_status");
        const s = r.scan || r; setScan(s);
        if (s.running || s.queued) { poll.current = window.setTimeout(tick, 1000); } else { onChanged(); }
      } catch { /* se reintenta en la próxima acción */ }
    };
    poll.current = window.setTimeout(tick, 400);
  };
  useEffect(() => { call("scan_status").then((r: any) => { const s = r.scan || r; setScan(s); if (s.running) watchScan(); }).catch(() => {}); return () => clearTimeout(poll.current); }, []);

  // hijos directos de un nodo, calculados al desplegar (los árboles profundos solo se pintan donde se abren)
  const kids = useMemo(() => {
    const m = new Map<string, string[]>();
    for (const [fid, rels] of Object.entries(tree)) for (const rel of Object.keys(rels)) {
      if (!rel) continue;
      const i = rel.lastIndexOf("/"); const par = fid + "|" + (i < 0 ? "" : rel.slice(0, i));
      (m.get(par) || m.set(par, []).get(par)!).push(rel);
    }
    m.forEach((v) => v.sort((a, b) => a.localeCompare(b, "es", { numeric: true, sensitivity: "base" })));
    return m;
  }, [tree]);

  const toggle = (k: string) => setOpen((o) => { const x = new Set(o); x.has(k) ? x.delete(k) : x.add(k); return x; });
  const row = (f: any, rel: string, depth: number): JSX.Element => {
    const k = f.id + "|" + rel, ch = kids.get(k) || [], c = tree[f.id]?.[rel] || [0, f.count || 0];
    const on = node && node.fid === f.id && node.rel === rel;
    const name = rel ? rel.split("/").pop() : folderLabel(f);
    return (
      <li key={k}>
        <div className={`frow ${on ? "on" : ""} ${!rel && f.missing ? "missing" : ""}`} style={{ paddingLeft: 6 + depth * 14 }}>
          <button className="caret" disabled={!ch.length} onClick={() => toggle(k)} aria-label="desplegar">{ch.length ? (open.has(k) ? "▾" : "▸") : ""}</button>
          <a href={nodeHref({ fid: f.id, rel })} title={rel ? f.path + "/" + rel : f.path || name}>{name}</a>
          {!rel && f.missing && <span className="warn" title="Carpeta no encontrada">⚠</span>}
          <small>{c[1]}</small>
          {!f.pseudo && <OriginMark f={f} rel={rel} marks={meta.origin_folders || {}} onChanged={onChanged} />}
          {!rel && !f.pseudo && <FolderActions f={f} onChanged={onChanged} watchScan={watchScan} onExcl={() => setExcl(f)} />}
        </div>
        {ch.length > 0 && open.has(k) && <ul>{ch.map((r) => row(f, r, depth + 1))}</ul>}
      </li>
    );
  };
  const real = meta.folders.filter((f: any) => !f.pseudo), pseudo = meta.folders.filter((f: any) => f.pseudo);
  const running = !!(scan && (scan.running || scan.queued > 0));

  return (
    <aside className="folders">
      <header>
        <h3>Carpetas</h3>
        <button onClick={() => setAdding(!adding)} title="Añadir carpeta vigilada">＋</button>
        <button onClick={async () => { await act("rescan", {}, () => {}, { quiet: true }); watchScan(); }} title="Volver a escanear todas">⟳</button>
      </header>
      {running && (
        <div className="fscan">
          <span>{scan.paused ? "En pausa" : "Indexando"} {scan.path ? scan.path.split(/[\\/]/).pop() : ""} {scan.total ? `${scan.done}/${scan.total}` : ""}{scan.queued ? ` · ${scan.queued} en cola` : ""}</span>
          <button onClick={async () => { const r: any = await call("pause_index", { paused: !scan.pause_set }); if (r.scan) setScan(r.scan); }}>{scan.pause_set ? "▶ Seguir" : "⏸ Pausa"}</button>
        </div>
      )}
      {adding && <AddFolder onDone={(ok) => { setAdding(false); if (ok) { onChanged(); watchScan(); } }} />}
      <ul className="ftree">
        <li><div className={`frow ${!node ? "on" : ""}`} style={{ paddingLeft: 6 }}><span className="caret" /><a href="#/carpetas">Todas</a><small>{meta.total}</small></div></li>
        {real.map((f: any) => row(f, "", 0))}
        {pseudo.length > 0 && <li className="fsep" />}
        {pseudo.map((f: any) => row(f, "", 0))}
      </ul>
      {!real.length && <p className="muted">Sin carpetas vigiladas. Pulsa ＋ para añadir una (las mismas que en la Media Library).</p>}
      {excl && <Excluded f={excl} onClose={() => setExcl(null)} onChanged={onChanged} />}
    </aside>
  );
}

function FolderActions({ f, onChanged, watchScan, onExcl }: { f: any; onChanged: () => void; watchScan: () => void; onExcl: () => void }) {
  const [armed, setArmed] = useState(false);
  useEffect(() => { if (!armed) return; const t = setTimeout(() => setArmed(false), 5000); return () => clearTimeout(t); }, [armed]);
  return (
    <span className="facts">
      {f.excluded > 0 && <button onClick={onExcl} title={`${f.excluded} elemento(s) quitados de esta carpeta: ver / restaurar`}>⊘{f.excluded}</button>}
      <button className={f.recursive ? "on" : ""} title={f.recursive ? "Incluye subcarpetas (clic: solo esta carpeta)" : "Solo esta carpeta (clic: incluir subcarpetas)"}
        onClick={async () => { await act("folder_recursive", { folder_id: f.id, recursive: !f.recursive }, onChanged, { quiet: true }); watchScan(); }}>⊞</button>
      <button title="Volver a escanear" onClick={async () => { await act("folder_rescan", { folder_id: f.id }, () => {}, { quiet: true }); watchScan(); }}>⟳</button>
      <button className={`rm ${armed ? "armed" : ""}`} title={armed ? "Pulsa otra vez para quitarla (los archivos no se borran)" : "Dejar de vigilar"}
        onClick={() => (armed ? act("folder_remove", { folder_id: f.id }, onChanged) : setArmed(true))}>{armed ? "¿Quitar?" : "×"}</button>
    </span>
  );
}

function AddFolder({ onDone }: { onDone: (ok: boolean) => void }) {
  const [path, setPath] = useState("");
  const [rec, setRec] = useState(true);
  const [br, setBr] = useState<any | null>(null);
  const [busy, setBusy] = useState(false);
  const browse = async (p: string) => {
    try { const r: any = await call("browse", { path: p }); if (!r.ok) { toast(r.error || "Error", "err"); return; } setBr(r.browse); if (r.browse.path) setPath(r.browse.path); }
    catch (e: any) { toast(String(e?.message || e), "err"); }
  };
  const add = async () => {
    if (!path.trim()) return;
    setBusy(true); const r = await act("folder_add", { path: path.trim(), recursive: rec }, () => {}); setBusy(false);
    if (r && r.ok) onDone(true);
  };
  return (
    <div className="fadd">
      <input value={path} onChange={(e) => setPath(e.target.value)} placeholder="Carpeta del equipo de WanGP, p. ej. D:\Fotos\refs"
        onKeyDown={(e) => { if (e.key === "Enter") add(); if (e.key === "Escape") onDone(false); }} autoFocus />
      <label><input type="checkbox" checked={rec} onChange={(e) => setRec(e.target.checked)} /> Incluir subcarpetas</label>
      <div className="row">
        <button onClick={() => browse(br ? br.path || "" : path.trim())}>Explorar…</button>
        <button className="primary" disabled={busy || !path.trim()} onClick={add}>Añadir</button>
        <button onClick={() => onDone(false)}>Cancelar</button>
      </div>
      {br && (
        <div className="fbrowse">
          {!br.path ? (
            <>{(br.shortcuts || []).map((s: any) => <button key={s.path} onClick={() => browse(s.path)}>★ {s.name}</button>)}
              {(br.drives || []).map((d: any) => <button key={d.path || d} onClick={() => browse(d.path || d)}>🖴 {d.name || d.path || d}</button>)}</>
          ) : (
            <>
              <div className="crumbs"><button onClick={() => browse("")}>Equipo</button>{(br.crumbs || []).map((c: any) => <button key={c.path} onClick={() => browse(c.path)}>{c.name}</button>)}</div>
              <small className="muted">{br.images}{br.images_more ? "+" : ""} archivo(s) multimedia aquí</small>
              {br.parent && <button onClick={() => browse(br.parent)}>↑ ..</button>}
              {(br.dirs || []).map((d: any) => <button key={d.path} onClick={() => browse(d.path)}>📁 {d.name}</button>)}
              {br.dirs_more && <small className="muted">… hay más carpetas</small>}
            </>
          )}
        </div>
      )}
    </div>
  );
}

function Excluded({ f, onClose, onChanged }: { f: any; onClose: () => void; onChanged: () => void }) {
  const [items, setItems] = useState<any[] | null>(null);
  const load = () => call("folder_excluded", { fid: f.id }).then((r: any) => setItems(r.items || [])).catch(() => setItems([]));
  useEffect(() => { load(); }, [f.id]);
  const restore = async (body: any) => { const r = await act("folder_restore", { fid: f.id, ...body }, onChanged); if (r?.ok) body.all ? onClose() : load(); };
  return (
    <div className="dlgbg" onClick={onClose}>
      <div className="dlg" onClick={(e) => e.stopPropagation()}>
        <h3>Quitados de «{folderLabel(f)}»</h3>
        {!items ? <p className="muted">Cargando…</p> : !items.length ? <p className="muted">Nada quitado.</p> : (
          <ul className="exlist">{items.slice(0, 500).map((x) => (
            <li key={x.hash}><span title={x.path}>{x.rel ? x.rel + "/" + x.name : x.name}</span>{x.recycled ? <em>papelera</em> : !x.on_disk ? <em>ya no está</em> : null}
              <button onClick={() => restore({ hashes: [x.hash] })}>Restaurar</button></li>))}</ul>
        )}
        <div className="row"><button onClick={onClose}>Cerrar</button>{items && items.length > 0 && <button className="primary" onClick={() => restore({ all: true })}>Restaurar todo ({items.length})</button>}</div>
      </div>
    </div>
  );
}

// 1.10.0 «Marcar carpeta como IA»: heredado por subcarpetas y archivos nuevos (origin_folder, compartido con la Media Library)
function OriginMark({ f, rel, marks, onChanged }: { f: any; rel: string; marks: Record<string, string>; onChanged: () => void }) {
  const own = marks[f.id + "|" + rel];
  let inh: string | undefined;
  const parts = rel ? rel.split("/") : [];
  for (let k = parts.length - 1; k >= 0 && !inh; k--) inh = marks[f.id + "|" + parts.slice(0, k).join("/")];
  const ai = own ? own === "ai" : inh === "ai";
  const next = own === "ai" ? (inh === "ai" ? "real" : "auto") : own === "real" ? "auto" : ai ? "real" : "ai";
  const title = own === "ai" ? "Marcada como IA (clic: quitar marca)" : own === "real" ? "Marcada como real dentro de una carpeta IA (clic: heredar)"
    : inh === "ai" ? "IA por la carpeta superior (clic: marcar esta como real)" : "Marcar carpeta como IA (incluye subcarpetas y archivos nuevos)";
  return <button className={`omark ${ai ? "on" : ""} ${own ? "own" : ""}`} title={title}
    onClick={(e) => { e.preventDefault(); act("origin_folder", { fid: f.id, rel, value: next }, onChanged); }}>IA</button>;
}

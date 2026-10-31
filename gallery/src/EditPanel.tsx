import { useEffect, useMemo, useState } from "react";
import { FAV, Item, Meta, isPerson, personName, personTag } from "./api";
import { renameOne } from "./Manage";
import DeleteDialog, { startDelete } from "./DeleteDialog";
import { act } from "./actions";
import { AutoTags, startAutotag } from "./AutoTag";
import { SimilarButtons, startSimIndex } from "./Similar";

interface Props {
  items: Item[];                 // los elementos a editar (1 = ficha, N = edición en bloque)
  meta: Meta;
  onChanged: () => void;
  onVirtual?: () => void;        // abrir el editor de copia virtual (solo con 1 elemento)
  onClose?: () => void;
  compact?: boolean;
}

export default function EditPanel({ items, meta, onChanged, onVirtual, onClose }: Props) {
  const hashes = items.map((i) => i.hash);
  const n = items.length;
  const [tagIn, setTagIn] = useState("");
  const [plan, setPlan] = useState<any>(null);
  const [modelIn, setModelIn] = useState("");
  const [newCol, setNewCol] = useState("");
  const [busy, setBusy] = useState(false);
  // 1.8.3: casillas de colección optimistas (cambian al instante; se deshacen si el servidor falla)
  const [colOpt, setColOpt] = useState<Record<string, boolean>>({});
  const hkey = hashes.join(",");
  useEffect(() => setColOpt({}), [hkey, items]);
  const toggleCol = async (cid: string, on: boolean) => {
    setColOpt((o) => ({ ...o, [cid]: on }));
    const r = await act(on ? "add" : "remove_from", { hashes, collection_id: cid }, onChanged, { quiet: true });
    if (!r || !r.ok) setColOpt((o) => { const x = { ...o }; delete x[cid]; return x; });
  };

  const tagCount = useMemo(() => {
    const m = new Map<string, number>();
    items.forEach((i) => i.tags.forEach((t) => m.set(t, (m.get(t) || 0) + 1)));
    return m;
  }, [items]);
  const colCount = useMemo(() => {
    const m = new Map<string, number>();
    items.forEach((i) => i.cols.forEach((c) => m.set(c, (m.get(c) || 0) + 1)));
    return m;
  }, [items]);
  const allTags = meta.tags.map((t) => t.tag);
  const models = [...tagCount.keys()].filter(isPerson);
  const plain = [...tagCount.keys()].filter((t) => !isPerson(t) && t.toLowerCase() !== FAV);
  const favN = items.filter((i) => i.tags.some((t) => t.toLowerCase() === FAV)).length;
  const videos = items.filter((i) => i.kind === "video");
  const one = n === 1 ? items[0] : null;

  const run = async (action: string, body: Record<string, any>, quiet = false) => {
    setBusy(true);
    await act(action, { hashes, ...body }, onChanged, { quiet });
    setBusy(false);
  };
  const addTags = (tags: string[]) => tags.length && run("tag", { add: tags });
  const splitTags = (s: string) => s.split(",").map((x) => x.trim()).filter(Boolean);

  return (
    <aside className="edit">
      <header>
        <h3>{one ? one.name : `${n} elementos seleccionados`}</h3>
        {onClose && <button className="x" onClick={onClose} title="Cerrar (E)">×</button>}
      </header>
      {one && (
        <p className="sub">
          {one.kind === "video" ? "Vídeo" : one.kind === "audio" ? "Audio" : "Imagen"}
          {one.virtual ? " · copia virtual" : ""}
          {one.vcopies ? ` · ${one.vcopies} copia(s) virtual(es)` : ""}
          {one.pool ? " · bolsa" : ""} · {new Date(one.added * 1000).toLocaleDateString("es-ES")}
        </p>
      )}

      <section>
        <button disabled={busy} className={`fav ${favN === n ? "on" : ""}`}
          onClick={() => run("tag", favN === n ? { remove: [FAV] } : { add: [FAV] }, true)}>
          {favN === n ? "♥ Favorita" : favN ? `♡ Marcar favoritas (${favN}/${n})` : "♡ Añadir a favoritas"}
        </button>
      </section>

      <section>
        <h4>Personas</h4>
        <div className="chips">
          {models.map((t) => (
            <span key={t} className="chip model">
              <span className="clk" title="Clic: renombrar en toda la librería" onClick={() => renameOne("persona", t, personName(t), onChanged)}>{personName(t)}</span>{n > 1 && <small> {tagCount.get(t)}/{n}</small>}
              <button title="Quitar" onClick={() => run("tag", { remove: [t] })}>×</button>
            </span>
          ))}
          {!models.length && <span className="muted">Sin persona</span>}
        </div>
        <form onSubmit={(e) => { e.preventDefault(); const v = modelIn.trim(); if (v) { addTags([personTag(v, allTags)]); setModelIn(""); } }}>
          <input list="dl-personas" value={modelIn} onChange={(e) => setModelIn(e.target.value)} placeholder="Añadir persona…" />
          <datalist id="dl-personas">{allTags.filter(isPerson).map((t) => <option key={t} value={personName(t)} />)}</datalist>
        </form>
      </section>

      <section>
        <h4>Etiquetas</h4>
        <div className="chips">
          {plain.map((t) => (
            <span key={t} className="chip">
              <span className="clk" title="Clic: renombrar en toda la librería" onClick={() => renameOne("tag", t, t, onChanged)}>{t}</span>{n > 1 && <small> {tagCount.get(t)}/{n}</small>}
              <button title="Quitar" onClick={() => run("tag", { remove: [t] })}>×</button>
            </span>
          ))}
          {!plain.length && <span className="muted">Sin etiquetas</span>}
        </div>
        <form onSubmit={(e) => { e.preventDefault(); addTags(splitTags(tagIn)); setTagIn(""); }}>
          <input list="dl-tags" value={tagIn} onChange={(e) => setTagIn(e.target.value)} placeholder="Añadir etiquetas (separadas por comas)…" />
          <datalist id="dl-tags">{allTags.filter((t) => !isPerson(t)).map((t) => <option key={t} value={t} />)}</datalist>
        </form>
      </section>

      {one && (one.kind || "image") === "image" && <AutoTags hash={one.hash} onSearch={(id, label) => {
        window.dispatchEvent(new CustomEvent("reflib:search-chip", { detail: { k: "auto", v: id, label } }));
      }} />}

      <section>
        <h4>Colecciones</h4>
        <ul className="cols">
          {meta.collections.map((c) => {
            const real = colCount.get(c.id) || 0;
            const k = c.id in colOpt ? (colOpt[c.id] ? n : 0) : real;
            const cnt = c.count + (c.id in colOpt ? (colOpt[c.id] ? n - real : -real) : 0);
            return (
              <li key={c.id}>
                <label>
                  <input type="checkbox" checked={k === n} ref={(el) => { if (el) el.indeterminate = k > 0 && k < n; }} 
                    onChange={() => toggleCol(c.id, k !== n)} />
                  {c.name} <small>{cnt}</small>
                </label>
              </li>
            );
          })}
        </ul>
        <form onSubmit={(e) => { e.preventDefault(); if (newCol.trim()) { run("add", { new_name: newCol.trim() }); setNewCol(""); } }}>
          <input value={newCol} onChange={(e) => setNewCol(e.target.value)} placeholder="Nueva colección con esto…" />
        </form>
      </section>

      <section className="actions">
        <h4>Acciones</h4>
        {one && onVirtual && one.kind !== "mask" && (
          <button disabled={busy} onClick={onVirtual}>
            {one.virtual ? "✂ Editar copia virtual" : one.kind === "video" || one.kind === "audio" ? "✂ Recortar clip / encuadre (copia virtual)" : "✂ Recortar (copia virtual)"}
          </button>
        )}
        {videos.length > 0 && !videos.every((v) => v.vl) && (
          <button disabled={busy} onClick={() => act("to_vlib", { hashes: videos.map((v) => v.hash) }, onChanged)}>🎞 Enviar a Video Library</button>
        )}
        {items.some((i) => (i.kind || "image") === "image") && (<>
          <button disabled={busy} title="La misma cola de autoetiquetado que la Media Library (solo imágenes; omite las ya etiquetadas)"
            onClick={() => startAutotag(hashes)}>🏷 Autoetiquetar{n > 1 ? ` (${n})` : ""}</button>
          <button disabled={busy} title="Volver a etiquetar aunque ya tengan etiquetas automáticas" onClick={() => startAutotag(hashes, true)}>↻ Reetiquetar</button>
        </>)}
        {one && (one.kind || "image") === "image" && <SimilarButtons hash={one.hash} name={one.name} />}
        {items.some((i) => (i.kind || "image") === "image") && (
          <button disabled={busy} title="Calcula pose y cara de lo seleccionado para «Similares» (las mismas acciones que la Media Library)"
            onClick={() => startSimIndex(hashes)}>⧉ Calcular poses y caras{n > 1 ? ` (${n})` : ""}</button>)}
        <button disabled={busy} className="danger" title="La misma confirmación que la Media Library: quitar de la librería o, si lo marcas, enviar los archivos a la Papelera"
          onClick={() => startDelete(hashes, setPlan, onChanged)}>
          🗑 Borrar…
        </button>
        {plan && <DeleteDialog plan={plan} hashes={hashes} close={() => setPlan(null)} after={onChanged} />}
      </section>
    </aside>
  );
}

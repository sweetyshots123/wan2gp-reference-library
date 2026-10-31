// 1.9.5: gestor de la Video Library (renombrar, ordenar, borrar con deshacer, importar, descargar, exportar todo).
// Sin lógica propia: son las acciones compartidas v_* que usa también la Media Library de Gradio.
import { useEffect, useState } from "react";
import { call, download, pickFiles, upload } from "./api";
import { act } from "./actions";
import { Thumb, fmtDur, toast } from "./ui";

interface V { id: string; name: string; hash: string; width?: number; height?: number; duration?: number; size?: number }

export function VideoManager({ after }: { after: () => void }) {
  const [vs, setVs] = useState<V[] | null>(null);
  const load = () => call("v_list").then((r) => setVs(r.videos || [])).catch(() => setVs([]));
  useEffect(() => { load(); }, []);
  const done = () => { load(); after(); };
  const rename = (v: V) => { const n = window.prompt(`Nuevo nombre para «${v.name}»:`, v.name); if (n && n.trim() && n.trim() !== v.name) act("v_rename", { vid: v.id, name: n.trim() }, done); };
  const del = (v: V) => { if (window.confirm(`¿Borrar «${v.name}» de la Video Library? (se puede deshacer durante 5 min)`)) act("v_delete", { vid: v.id }, done); };
  const imp = async () => {
    const files = await pickFiles("video/*,.zip"); if (!files.length) return;
    toast("Importando…", "info");
    const r = await upload(files, { action: "v_import" });
    toast(r.toast || r.message || r.error || "?", r.ok ? "ok" : "err"); done();
  };
  const exp = async (body: any) => { const r = await act("v_export", body, () => {}); if (r) download(r); };
  if (!vs) return <p className="muted">Cargando…</p>;
  return (
    <div className="manage vman">
      <div className="mbar">
        <button onClick={imp}>⬆ Importar vídeos o .zip</button>
        <button disabled={!vs.length} onClick={() => exp({ all: true })}>⬇ Exportar todos (.zip)</button>
      </div>
      {!vs.length && <p className="muted">La Video Library está vacía.</p>}
      <table><tbody>
        {vs.map((v, i) => (
          <tr key={v.id}>
            <td className="vth">{v.hash ? <Thumb hash={v.hash} /> : null}</td>
            <td className="mname">{v.name}</td>
            <td className="muted">{v.width && v.height ? `${v.width}×${v.height}` : ""} {v.duration ? fmtDur(v.duration) : ""}</td>
            <td>
              <button title="Mover a la izquierda" disabled={i === 0} onClick={() => act("v_move", { vid: v.id, delta: -1 }, done, { quiet: true })}>◀</button>
              <button title="Mover a la derecha" disabled={i === vs.length - 1} onClick={() => act("v_move", { vid: v.id, delta: 1 }, done, { quiet: true })}>▶</button>
              <button title="Renombrar" onClick={() => rename(v)}>✎</button>
              <button title="Descargar" onClick={() => exp({ vid: v.id })}>⬇</button>
              <button title="Borrar" onClick={() => del(v)}>🗑</button>
            </td>
          </tr>
        ))}
      </tbody></table>
    </div>
  );
}

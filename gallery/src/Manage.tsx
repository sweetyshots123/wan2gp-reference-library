// 1.8.6: gestión global de etiquetas, personas y colecciones. Sin lógica propia: todo son acciones compartidas de la
// Media Library (tag_rename / tag_merge / tag_delete / tag_undo_delete, col_rename / col_delete / col_undo_delete).
import { useState } from "react";
import { PERSON, personName } from "./api";
import { act } from "./actions";

export type Kind = "tag" | "persona" | "col";
export interface Row { key: string; label: string; count: number }

const full = (kind: Kind, name: string) => (kind === "persona" ? PERSON + name.trim() : name.trim());
const what = (kind: Kind) => (kind === "col" ? "la colección" : kind === "persona" ? "la persona" : "la etiqueta");

export async function renameOne(kind: Kind, key: string, label: string, after: () => void, optimistic?: (to: string | null) => void) {
  const to = window.prompt(`Nuevo nombre para ${what(kind)} «${label}»${kind !== "col" ? " (si ya existe se fusionan)" : ""}:`, label);
  if (!to || !to.trim() || to.trim() === label) return;
  optimistic?.(to.trim());
  const r = kind === "col" ? await act("col_rename", { collection_id: key, name: to.trim() }, after)
                           : await act("tag_rename", { tag: key, to: full(kind, to) }, after);
  if (!r?.ok) optimistic?.(null);
}

export async function deleteOne(kind: Kind, key: string, label: string, count: number, after: () => void, optimistic?: (gone: boolean) => void) {
  const msg = kind === "col" ? `¿Borrar la colección «${label}» (${count} elementos)? Los archivos no se pierden si están en otras colecciones o carpetas.`
                             : `¿Quitar ${what(kind)} «${label}» de ${count} elementos?`;
  if (!window.confirm(msg)) return;
  optimistic?.(true);
  const r = kind === "col" ? await act("col_delete", { collection_id: key }, after) : await act("tag_delete", { tag: key }, after);
  if (!r?.ok) optimistic?.(false);
}

export function ManageList({ kind, rows, after }: { kind: Kind; rows: Row[]; after: () => void }) {
  const [sel, setSel] = useState<Set<string>>(new Set());
  const [gone, setGone] = useState<Set<string>>(new Set());
  const [names, setNames] = useState<Record<string, string>>({});
  const vis = rows.filter((r) => !gone.has(r.key));
  const flip = (k: string) => setSel((s) => { const n = new Set(s); n.has(k) ? n.delete(k) : n.add(k); return n; });
  const merge = async () => {
    const keys = [...sel]; if (keys.length < 2) return;
    const first = rows.find((r) => r.key === keys[0])!;
    const to = window.prompt(`Fusionar ${keys.length} en (nombre final):`, first.label);
    if (!to || !to.trim()) return;
    const n = rows.filter((r) => sel.has(r.key)).reduce((a, r) => a + r.count, 0);
    if (!window.confirm(`¿Fusionar ${keys.length} ${kind === "persona" ? "personas" : "etiquetas"} (${n} usos) en «${to.trim()}»?`)) return;
    setGone((g) => new Set([...g, ...keys.slice(1)])); setNames((m) => ({ ...m, [keys[0]]: to.trim() }));
    const r = await act("tag_merge", { tags: keys, to: full(kind, to) }, after);
    if (!r?.ok) { setGone(new Set()); setNames({}); }
    setSel(new Set());
  };
  return (
    <div className="manage">
      {kind !== "col" && <div className="mbar"><button disabled={sel.size < 2} onClick={merge}>Fusionar seleccionadas ({sel.size})</button></div>}
      <table><tbody>
        {vis.map((r) => (
          <tr key={r.key}>
            {kind !== "col" && <td><input type="checkbox" checked={sel.has(r.key)} onChange={() => flip(r.key)} /></td>}
            <td className="mname">{names[r.key] ?? r.label}</td>
            <td className="muted">{r.count}</td>
            <td>
              <button title="Renombrar" onClick={() => renameOne(kind, r.key, r.label, after, (to) => setNames((m) => { const n = { ...m }; if (to) n[r.key] = to; else delete n[r.key]; return n; }))}>✎</button>
              <button title="Borrar" onClick={() => deleteOne(kind, r.key, r.label, r.count, after, (g) => setGone((s) => { const n = new Set(s); g ? n.add(r.key) : n.delete(r.key); return n; }))}>🗑</button>
            </td>
          </tr>
        ))}
      </tbody></table>
    </div>
  );
}
export { personName };

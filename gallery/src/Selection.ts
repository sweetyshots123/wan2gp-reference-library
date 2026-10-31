// 1.9.6: selección compartida por TODAS las rejillas de la Galería (explorar, carpetas, colecciones, similares…),
// con la misma semántica que la Media Library (reference_library.js):
//  · círculo ✓: alterna sin abrir el visor; con Mayús selecciona el rango desde el ancla (aditivo)
//  · Ctrl/Cmd+clic: alterna y fija el ancla · Mayús+clic: rango desde el ancla (Ctrl+Mayús = añade)
//  · Ctrl+A: todas las que coinciden con el filtro (acción compartida "range", no solo las cargadas)
//  · Esc: la 1.ª vez limpia la selección
import { useRef } from "react";
import { call } from "./api";

export type SelApi = {
  click: (hash: string, idx: number, e: { shiftKey: boolean; ctrlKey: boolean; metaKey: boolean }, viaBox: boolean) => boolean;
  selectAll: () => Promise<void>;
  clear: () => void;
};

export function useSelection(sel: Set<string>, setSel: (s: Set<string>) => void, filter: unknown, total: number,
                             hashAt: (i: number) => string | undefined): SelApi {
  const anchor = useRef(-1);
  const cur = useRef(sel); cur.current = sel;
  const range = async (a: number, b: number, additive: boolean) => {
    const lo = Math.min(a, b), hi = Math.max(a, b), got: string[] = [];
    let missing = false;
    for (let k = lo; k <= hi; k++) { const h = hashAt(k); if (h) got.push(h); else { missing = true; break; } }
    let hs = got;
    if (missing) { const r = await call("range", { f: filter, start: lo, end: hi }); hs = r.ok ? r.hashes : got; }
    const n = additive ? new Set(cur.current) : new Set<string>();
    hs.forEach((h) => n.add(h)); setSel(n);
  };
  const toggle = (h: string) => { const n = new Set(cur.current); n.has(h) ? n.delete(h) : n.add(h); setSel(n); };
  // devuelve true si el clic se consumió como selección (si no, el llamador abre el visor)
  const click: SelApi["click"] = (h, idx, e, viaBox) => {
    const ctrl = e.ctrlKey || e.metaKey;
    if (e.shiftKey && anchor.current >= 0 && anchor.current !== idx) { range(anchor.current, idx, viaBox || ctrl); return true; }
    if (viaBox || ctrl) { toggle(h); anchor.current = idx; return true; }
    anchor.current = idx;
    if (cur.current.size > 0) { toggle(h); return true; }   // con selección activa, un clic alterna (como el modo selección)
    return false;
  };
  const selectAll = async () => {
    if (!total) return;
    const r = await call("range", { f: filter, start: 0, end: total - 1 });
    if (r.ok) setSel(new Set(r.hashes));
  };
  return { click, selectAll, clear: () => { anchor.current = -1; setSel(new Set()); } };
}

// 1.9.6: selección compartida por TODAS las rejillas de la Galería. Las reglas (clic, Ctrl, Mayús+ancla, círculo,
// Esc, Ctrl+A) son el MISMO archivo que usa la Media Library: ../../selection_rules.js (aquí solo se aplican).
import { useRef } from "react";
import "../../selection_rules.js";
import { call } from "./api";

type Op = { op: string; from?: number; to?: number; additive?: boolean; anchor?: number; preview?: boolean };
type RSApi = {
  cardClick: (anchor: number, idx: number, isSelected: boolean, ev: { shift: boolean; ctrl: boolean }) => Op;
  boxClick: (anchor: number, idx: number, ev: { shift: boolean }) => Op;
  rangeBounds: (a: number, b: number, max?: number) => [number, number];
  key: (ev: { ctrl?: boolean; key: string }, has: boolean) => Op | null;
};
export const RS: RSApi = (globalThis as any).ReflibSelection;

type Mods = { shiftKey: boolean; ctrlKey: boolean; metaKey: boolean };
export type SelApi = {
  click: (hash: string, idx: number, e: Mods, viaBox: boolean) => boolean;
  key: (e: KeyboardEvent) => boolean;
  selectAll: () => Promise<void>;
  clear: () => void;
};

export function useSelection(sel: Set<string>, setSel: (s: Set<string>) => void, filter: unknown, total: number,
                             hashAt: (i: number) => string | undefined): SelApi {
  const anchor = useRef(-1);
  const cur = useRef(sel); cur.current = sel;
  const range = async (from: number, to: number, additive: boolean) => {
    const [lo, hi] = RS.rangeBounds(from, to);
    let hs: string[] = [];
    for (let k = lo; k <= hi; k++) { const h = hashAt(k); if (!h) { hs = []; break; } hs.push(h); }
    if (!hs.length) { const r = await call("range", { f: filter, start: lo, end: hi }); if (!r.ok) return; hs = r.hashes; }
    const n = additive ? new Set(cur.current) : new Set<string>();
    hs.forEach((h) => n.add(h)); setSel(n);
  };
  const run = (r: Op, h: string) => {
    if (r.anchor !== undefined) anchor.current = r.anchor;
    if (r.op === "range") { range(r.from!, r.to!, !!r.additive); return true; }
    if (r.op === "toggle") { const n = new Set(cur.current); n.has(h) ? n.delete(h) : n.add(h); setSel(n); return true; }
    return false;
  };
  // true = consumido como selección; false = el llamador abre el visor (la "vista previa" de la Media Library)
  const click: SelApi["click"] = (h, idx, e, viaBox) => {
    const ctrl = e.ctrlKey || e.metaKey;
    if (viaBox) return run(RS.boxClick(anchor.current, idx, { shift: e.shiftKey }), h) || true;
    const r = RS.cardClick(anchor.current, idx, cur.current.has(h), { shift: e.shiftKey, ctrl });
    if (run(r, h)) return true;
    if (r.op === "single" && cur.current.size > 0) { setSel(new Set([h])); return true; }   // como en la ML: reemplaza la selección
    return false;   // sin selección, o clic en una ya seleccionada ("keep"): vista previa = visor
  };
  const selectAll = async () => {
    if (!total) return;
    const r = await call("range", { f: filter, start: 0, end: total - 1 });
    if (r.ok) setSel(new Set(r.hashes));
  };
  const clear = () => { anchor.current = -1; setSel(new Set()); };
  const key = (e: KeyboardEvent) => {
    const r = RS.key({ ctrl: e.ctrlKey || e.metaKey, key: e.key }, cur.current.size > 0);
    if (!r) return false;
    if (r.op === "all") selectAll(); else if (r.op === "clear") clear();
    return true;
  };
  return { click, key, selectAll, clear };
}

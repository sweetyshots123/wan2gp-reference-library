// 1.12.0 vídeos en caras/similares: abrir el visor en un instante (best_t) y chips de segmentos.
import type { Item } from "./api";
export interface Seg { t0: number; t1: number }
export const fmtT = (t: number) => { t = Math.max(0, Math.round(t || 0)); return `${Math.floor(t / 60)}:${String(t % 60).padStart(2, "0")}`; };
const pending = new Map<string, number>();
/** El próximo visor que cargue `hash` salta a `t` segundos. */
export const seekNext = (hash: string, t: number | null | undefined) => { if (t != null && isFinite(+t)) pending.set(hash, +t); };
export const takeSeek = (hash: string) => { const t = pending.get(hash); pending.delete(hash); return t; };
export const OPEN_EVENT = "gal:open-at";
/** Abre el visor suelto (como desde el buscador) en `t`. */
export function openAt(item: Partial<Item> & { hash: string }, t?: number | null) {
  seekNext(item.hash, t ?? 0);
  const it: Item = { name: "", cols: [], pool: false, folders: [], tags: [], added: 0, kind: "video", ...item } as Item;
  window.dispatchEvent(new CustomEvent(OPEN_EVENT, { detail: it }));
}
/** Chips de tiempo (segmentos o best_t); clic = saltar. */
export function segChips(x: { best_t?: number | null; segments?: Seg[] | null }): { t: number; label: string }[] {
  if (x.segments && x.segments.length) return x.segments.map((s) => ({ t: s.t0, label: Math.round(s.t0) === Math.round(s.t1) ? fmtT(s.t0) : `${fmtT(s.t0)}–${fmtT(s.t1)}` }));
  return x.best_t != null ? [{ t: x.best_t, label: fmtT(x.best_t) }] : [];
}

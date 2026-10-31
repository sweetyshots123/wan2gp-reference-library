// 1.9.7: navegación rápida del visor con la rueda + caché de imágenes decodificadas.
// · WheelStepper: acumula deltas normalizados (deltaMode píxel / línea / página; rueda con muescas o trackpad)
//   y devuelve cuántas fotos avanzar; nunca descarta eventos (sin bloqueo fijo ni debounce).
// · MediumCache: LRU de imágenes medianas (acción compartida "preview", la misma que usa la Media Library
//   en su vista previa) ya decodificadas; precarga ±N vecinos en la dirección del giro y cancela lo que sobra.
import { call } from "./api";

export const STEP_PX = 100;        // una muesca típica de rueda = 100 px (Chrome/Edge, deltaMode 0) = 1 foto
const IDLE_RESET_MS = 220;         // sin eventos durante este tiempo, el resto acumulado se olvida

export function normDelta(e: { deltaY: number; deltaMode: number }): number {
  return e.deltaMode === 1 ? e.deltaY * 40 : e.deltaMode === 2 ? e.deltaY * 800 : e.deltaY;
}

export class WheelStepper {
  private acc = 0; private last = 0;
  /** delta normalizado en px -> número de fotos a avanzar (con signo) */
  push(dy: number, now = performance.now()): number {
    if (now - this.last > IDLE_RESET_MS || (this.acc && Math.sign(dy) !== Math.sign(this.acc))) this.acc = 0;
    this.last = now;
    this.acc += dy;
    const n = Math.trunc(this.acc / STEP_PX);
    this.acc -= n * STEP_PX;
    return n;
  }
  reset() { this.acc = 0; }
}

type Entry = { src: string; img: HTMLImageElement };
export class MediumCache {
  private lru = new Map<string, Entry>();
  private inflight = new Map<string, { img: HTMLImageElement; p: Promise<string | null>; dead: boolean }>();
  constructor(private max = 30) {}
  peek(h: string): string | null { const e = this.lru.get(h); if (!e) return null; this.lru.delete(h); this.lru.set(h, e); return e.src; }
  get(h: string): Promise<string | null> {
    const c = this.peek(h); if (c) return Promise.resolve(c);
    const f = this.inflight.get(h); if (f) return f.p;
    const img = new Image();
    const job = { img, dead: false, p: null as any as Promise<string | null> };
    job.p = (async () => {
      const r = await call("preview", { hash: h }).catch(() => null);
      const src = r && r.ok && r.image && r.image.src;
      if (!src || job.dead) return null;
      img.decoding = "async"; img.src = src;
      try { await img.decode(); } catch { if (job.dead) return null; }
      if (job.dead) return null;
      this.lru.set(h, { src, img });
      while (this.lru.size > this.max) this.lru.delete(this.lru.keys().next().value as string);
      return src;
    })().finally(() => this.inflight.delete(h));
    this.inflight.set(h, job);
    return job.p;
  }
  /** deja solo las cargas de `keep`; el resto se cancela (src vacío = el navegador aborta la descarga) */
  prune(keep: Set<string>) {
    this.inflight.forEach((j, h) => { if (!keep.has(h)) { j.dead = true; j.img.src = ""; this.inflight.delete(h); } });
  }
  forget(h: string) { this.lru.delete(h); }
}
export const medium = new MediumCache();

/** Carga una imagen a resolución completa ya decodificada; abort() la cancela. */
export function loadFull(src: string): { p: Promise<boolean>; abort: () => void } {
  const img = new Image(); let dead = false;
  img.decoding = "async"; img.src = src;
  const p = (img.decode ? img.decode() : Promise.resolve()).then(() => !dead, () => !dead && img.complete);
  return { p, abort: () => { dead = true; img.src = ""; } };
}

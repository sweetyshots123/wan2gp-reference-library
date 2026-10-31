// 1.9.7: navegación rápida del visor con la rueda + caché de imágenes decodificadas.
// · WheelStepper: envoltorio de ../../wheel_rules.js (1.11.0, compartido con la Media Library): 1 muesca = 1 foto.
// · MediumCache: LRU de imágenes medianas (acción compartida "preview", la misma que usa la Media Library
//   en su vista previa) ya decodificadas; precarga ±N vecinos en la dirección del giro y cancela lo que sobra.
import { call } from "./api";

import "../../wheel_rules.js";

/** píxeles aproximados (solo para zoom con Ctrl y para desplazar con zoom; NO para pasar de foto) */
export function normDelta(e: { deltaY: number; deltaMode: number }): number {
  return e.deltaMode === 1 ? e.deltaY * 40 : e.deltaMode === 2 ? e.deltaY * 800 : e.deltaY;
}

// 1.11.0: anterior/siguiente con la rueda = ../../wheel_rules.js (compartido): 1 muesca = 1 foto exacta.
type WR = { push: (dy: number, mode: number, now: number) => number; reset: () => void };
export class WheelStepper {
  private w: WR = (globalThis as any).ReflibWheel.create();
  /** evento de rueda -> número de fotos a avanzar (con signo); nunca descarta muescas */
  push(e: { deltaY: number; deltaMode: number }, now = performance.now()): number { return this.w.push(e.deltaY, e.deltaMode, now); }
  reset() { this.w.reset(); }
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

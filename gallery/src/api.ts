// Cliente del puente de la Media Library: cada llamada es exactamente una acción de plugin.ilib(...)
import "../../request_priority.js";
import "../../tag_complete.js";   // 1.12.17: shared tag autocomplete (ReflibTagComplete)
const Net: any = (globalThis as any).ReflibNet;
const viewSched = Net?.createScheduler?.() || null;
const lanes = Net?.createLanes?.() || null;   // 1.12.16: preview / media in their own lane, never behind a slow query
const thumbGate = Net?.createThumbGate?.() || { enterViewer() {}, leaveViewer() {}, blocked: false, whenFree() { return Promise.resolve(); } };
export const viewerNet = { enter: () => thumbGate.enterViewer(), leave: () => thumbGate.leaveViewer(), blocked: () => !!thumbGate.blocked };
export type Kind = "image" | "video" | "audio" | "mask";
export interface Item {
  hash: string; name: string; names?: string[]; cols: string[]; pool: boolean; folders: string[];
  tags: string[]; added: number; kind?: Kind; virtual?: { orig: string; broken: boolean }; missing?: boolean;
  dur?: number; vl?: boolean; vcopies?: number; origin?: "ai";
  best_t?: number | null; segments?: { t0: number; t1: number }[];   // 1.12.0: vídeo en resultados de similares
}
export interface Collection { id: string; name: string; count: number }
export interface TagCount { tag: string; count: number }
export interface Meta { rev: number; total: number; collections: Collection[]; tags: TagCount[]; folders: any[]; tree?: Record<string, Record<string, number[]>>; n_unassigned?: number; kinds: Record<string, number>; origins?: Record<string, number>; origin_folders?: Record<string, string> }
export interface Filter {
  kinds?: string[]; origins?: string[];
  cols?: string[]; tags?: string[]; atags?: string[]; sim?: string; q?: string; qall?: string[]; kind?: string; sort?: string; none?: boolean; recent?: boolean;
  node?: { fid: string; rel: string }; sub?: boolean;
}
export interface Resp { ok: boolean; message?: string; toast?: string; kind?: string; error?: string; [k: string]: any }

export const FAV = "favorita";
// Personas: etiqueta manual «persona:<Nombre>». Las antiguas «modelo:<Nombre>» se siguen reconociendo como personas
// (no se reescribe nada); al añadir una persona que ya existe con «modelo:» se reutiliza esa etiqueta, así no hay duplicados.
export const PERSON = "persona:";
const PERSON_PREFIXES = ["persona:", "modelo:"];
export const isPerson = (t: string) => PERSON_PREFIXES.some((p) => t.toLowerCase().startsWith(p));
export const personName = (t: string) => { const p = PERSON_PREFIXES.find((x) => t.toLowerCase().startsWith(x)); return p ? t.slice(p.length).trim() : t; };
export const fold = (s: string) => s.normalize("NFKD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
/** Etiqueta de la persona «name»: la que ya exista en la librería (persona: o modelo:) o una nueva «persona:name». */
export function personTag(name: string, tags: { tag: string }[] | string[] = []): string {
  const n = fold(name.trim());
  const all = (tags as any[]).map((t) => (typeof t === "string" ? t : t.tag)).filter((t) => isPerson(t) && fold(personName(t)) === n);
  return all.find((t) => t.toLowerCase().startsWith(PERSON)) || all[0] || PERSON + name.trim();
}

async function rawCall<T = Resp>(action: string, body: Record<string, any> = {}): Promise<T & Resp> {
  const r = await fetch("/reflib/api", {
    method: "POST", headers: { "Content-Type": "application/json" }, credentials: "same-origin",
    body: JSON.stringify({ action, lang: "es", tz: -new Date().getTimezoneOffset(), ...body }),
  });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

/** 1.12.9: viewer actions (preview/media_url/…) jump the queue; thumbs wait while the viewer is open. */
export async function call<T = Resp>(action: string, body: Record<string, any> = {}, opts: { bg?: boolean } = {}): Promise<T & Resp> {
  const ch = Net?.channel?.(action) || (action === "thumbs" ? "thumb" : "normal");
  // 1.12.16: bg = refresh while indexing: behind anything the user asked for
  const prio = opts.bg ? (Net?.bgPrio ?? 1) : ch === "view" ? 10 : ch === "thumb" ? 0 : 5;
  // Gate wait is outside the scheduler so parked thumbs never block preview/media_url.
  if (ch === "thumb") await thumbGate.whenFree();
  const run = () => rawCall<T>(action, body);
  if (lanes) return lanes.enqueue(action, run, prio);
  if (viewSched) return viewSched.enqueue(run, prio);
  return run();
}

/** 1.9.5: descarga un archivo escrito por col_export / v_export (servido por GET /reflib/export/<rel>). */
export function download(r: Resp) {
  if (!r?.ok || !r.rel) return;
  const a = document.createElement("a");
  a.href = "/reflib/export/" + String(r.rel).split("/").map(encodeURIComponent).join("/"); a.download = r.name || "";
  document.body.appendChild(a); a.click(); a.remove();
}

/** 1.9.5: elige archivos con un <input type=file> temporal. */
export function pickFiles(accept: string, multiple = true): Promise<File[]> {
  return new Promise((res) => {
    const i = document.createElement("input"); i.type = "file"; i.accept = accept; i.multiple = multiple;
    i.onchange = () => res([...(i.files || [])]); i.click();
  });
}

export function metaOf(r: any): Meta | null {
  if (r?.meta) return r.meta;
  if (r && "rev" in r && "collections" in r) return r as Meta;
  return null;
}

// Miniaturas: el servidor acepta hasta 24 hashes por llamada; se agrupan y se cachean.
// 1.12.17: shared pull-based queue (ReflibNet.createThumbQueue): each batch is picked when a slot frees, visible tiles
// first (positions *now*), tiles scrolled past and unmounted are dropped before they are sent; 2 batches in flight in
// their own lane. Before, a FIFO kept every tile ever mounted, so after a long scroll the screen waited for all of it.
const thumbCache = new Map<string, string>();
const thumbSend = async (hashes: string[]) => call<{ thumbs: Record<string, string>; pending: string[] }>("thumbs", { hashes });
export const thumbQ = Net?.createThumbQueue?.({
  send: thumbSend, batch: 24, inflight: 2,
  pos: (el: Element) => (el.isConnected ? el.getBoundingClientRect() : null),
  view: () => ({ top: 0, bottom: innerHeight }),
  margin: () => innerHeight * 0.6,
  blocked: () => !!thumbGate.blocked,
}) || null;
if (thumbQ && typeof window !== "undefined") {
  let t = 0;   // positions changed: re-rank before the next batch
  addEventListener("scroll", () => { if (!t) t = window.setTimeout(() => { t = 0; thumbQ.poke(); }, 60); }, { passive: true });
  (window as any).__thumbQ = thumbQ;   // tests
}

/** Thumbnail for a tile: cb(url) once loaded; returns release() (call on unmount). */
export function wantThumb(hash: string, el: Element | null, cb: (u: string) => void): () => void {
  const c = thumbCache.get(hash);
  if (c) { cb(c); return () => {}; }
  if (thumbQ) return thumbQ.want(hash, el, (u: string) => { thumbCache.set(hash, u); cb(u); });
  let on = true; thumbSend([hash]).then((r) => { const u = r.thumbs?.[hash]; if (u) { thumbCache.set(hash, u); if (on) cb(u); } }).catch(() => {});
  return () => { on = false; };
}

export function thumb(hash: string): Promise<string> {
  const c = thumbCache.get(hash);
  if (c) return Promise.resolve(c);
  return new Promise((res) => { wantThumb(hash, null, res); });
}
export const forgetThumb = (h: string) => thumbCache.delete(h);
export const thumbNow = (h: string) => thumbCache.get(h) || null;   // 1.9.7: miniatura ya en caché (síncrona)

export async function mediaUrl(hash: string): Promise<{ url: string | null; rendering?: boolean }> {
  const r = await call("media_url", { hash });
  return { url: r.url || null, rendering: !!r.rendering };
}

export async function upload(files: File[], extra: Record<string, any> = {}): Promise<Resp> {
  const fd = new FormData();
  files.forEach((f) => fd.append("files", f, f.name));
  fd.append("meta", JSON.stringify({ lang: "es", ...extra }));   // 1.9.5: {action:"col_import"|"v_import"} -> acción compartida
  const r = await fetch("/reflib/upload", { method: "POST", body: fd, credentials: "same-origin" });
  return r.json();
}

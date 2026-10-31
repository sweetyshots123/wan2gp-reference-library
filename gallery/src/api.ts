// Cliente del puente de la Media Library: cada llamada es exactamente una acción de plugin.ilib(...)
export type Kind = "image" | "video" | "audio" | "mask";
export interface Item {
  hash: string; name: string; names?: string[]; cols: string[]; pool: boolean; folders: string[];
  tags: string[]; added: number; kind?: Kind; virtual?: { orig: string; broken: boolean }; missing?: boolean;
  dur?: number; vl?: boolean; vcopies?: number;
}
export interface Collection { id: string; name: string; count: number }
export interface TagCount { tag: string; count: number }
export interface Meta { rev: number; total: number; collections: Collection[]; tags: TagCount[]; folders: any[]; tree?: Record<string, Record<string, number[]>>; n_unassigned?: number; kinds: Record<string, number> }
export interface Filter {
  kinds?: string[];
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

export async function call<T = Resp>(action: string, body: Record<string, any> = {}): Promise<T & Resp> {
  const r = await fetch("/reflib/api", {
    method: "POST", headers: { "Content-Type": "application/json" }, credentials: "same-origin",
    body: JSON.stringify({ action, lang: "es", tz: -new Date().getTimezoneOffset(), ...body }),
  });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

export function metaOf(r: any): Meta | null {
  if (r?.meta) return r.meta;
  if (r && "rev" in r && "collections" in r) return r as Meta;
  return null;
}

// Miniaturas: el servidor acepta hasta 24 hashes por llamada; se agrupan y se cachean.
const thumbCache = new Map<string, string>();
const waiting = new Map<string, ((u: string) => void)[]>();
let queue: string[] = [];
let timer: number | undefined;

export function thumb(hash: string): Promise<string> {
  const c = thumbCache.get(hash);
  if (c) return Promise.resolve(c);
  return new Promise((res) => {
    const w = waiting.get(hash);
    if (w) { w.push(res); return; }
    waiting.set(hash, [res]);
    queue.push(hash);
    if (timer === undefined) timer = window.setTimeout(flush, 30);
  });
}

async function flush() {
  timer = undefined;
  const batch = queue.splice(0, 24);
  if (queue.length) timer = window.setTimeout(flush, 0);
  if (!batch.length) return;
  try {
    const r = await call<{ thumbs: Record<string, string>; pending: string[] }>("thumbs", { hashes: batch });
    const retry: string[] = [];
    for (const h of batch) {
      const u = r.thumbs?.[h];
      if (u) {
        thumbCache.set(h, u);
        (waiting.get(h) || []).forEach((f) => f(u));
        waiting.delete(h);
      } else retry.push(h);
    }
    if (retry.length) window.setTimeout(() => { queue.push(...retry); if (timer === undefined) timer = window.setTimeout(flush, 0); }, 1200);
  } catch {
    window.setTimeout(() => { queue.push(...batch); if (timer === undefined) timer = window.setTimeout(flush, 0); }, 2000);
  }
}
export const forgetThumb = (h: string) => thumbCache.delete(h);

export async function mediaUrl(hash: string): Promise<{ url: string | null; rendering?: boolean }> {
  const r = await call("media_url", { hash });
  return { url: r.url || null, rendering: !!r.rendering };
}

export async function upload(files: File[]): Promise<Resp> {
  const fd = new FormData();
  files.forEach((f) => fd.append("files", f, f.name));
  fd.append("meta", JSON.stringify({ lang: "es" }));
  const r = await fetch("/reflib/upload", { method: "POST", body: fd, credentials: "same-origin" });
  return r.json();
}

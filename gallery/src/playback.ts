// 1.12.7: resume playback — same rules as Media Library (../../playback_rules.js → ReflibPlayback).
import "../../playback_rules.js";
import { call } from "./api";

type PB = {
  version: number;
  DEFAULT_MIN_S: number;
  shouldTrack: (duration: number, t: number, minSeconds?: number) => boolean;
  fmt: (t: number) => string;
  offerLabels: (t: number, lang?: string) => { continue: string; restart: string; tip: string };
  minS: (v: any) => number;
};
export const Playback: PB = (globalThis as any).ReflibPlayback;

let cachedMin = Playback?.DEFAULT_MIN_S ?? 300;
let loaded = false;

export async function resumeMinS(): Promise<number> {
  if (loaded) return cachedMin;
  try {
    const r = await call("playback_settings");
    if (r?.ok && r.min_s != null) cachedMin = Number(r.min_s);
  } catch {}
  loaded = true;
  return cachedMin;
}

export async function setResumeMinM(minM: number): Promise<number> {
  const r = await call("playback_settings", { min_m: minM });
  if (r?.ok && r.min_s != null) {
    cachedMin = Number(r.min_s);
    loaded = true;
  }
  return cachedMin;
}

export async function getPos(hash: string) {
  const r = await call("playback_get", { hash });
  if (r?.min_s != null) { cachedMin = Number(r.min_s); loaded = true; }
  return r?.ok ? r.pos as { t: number; dur: number } | null : null;
}

export async function savePos(hash: string, t: number, duration: number) {
  const thr = await resumeMinS();
  if (!Playback?.shouldTrack(duration, t, thr)) {
    await call("playback_set", { hash, clear: 1 }).catch(() => {});
    return;
  }
  await call("playback_set", { hash, t, duration }).catch(() => {});
}

export async function clearPos(hash: string) {
  await call("playback_set", { hash, clear: 1 }).catch(() => {});
}

/** Current UI language for resume labels (Galería / document lang). */
export function uiLang(): string {
  try {
    const d = typeof document !== "undefined" ? document.documentElement?.lang : "";
    if (d) return d;
  } catch {}
  try {
    if (typeof navigator !== "undefined" && navigator.language) return navigator.language;
  } catch {}
  return "es";
}

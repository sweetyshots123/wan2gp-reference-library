import { useEffect, useRef, useState } from "react";
import { thumbNow, wantThumb } from "./api";

export interface Toast { id: number; text: string; kind?: string; action?: { label: string; run: () => void } }
let push: (t: Omit<Toast, "id">) => void = () => {};
let seq = 0;
export const toast = (text: string, kind = "ok", action?: Toast["action"]) => push({ text, kind, action });

export function Toasts() {
  const [list, setList] = useState<Toast[]>([]);
  useEffect(() => {
    push = (t) => {
      const id = ++seq;
      setList((l) => [...l.slice(-3), { ...t, id }]);
      window.setTimeout(() => setList((l) => l.filter((x) => x.id !== id)), t.action ? 15000 : 4500);
    };
  }, []);
  return (
    <div className="toasts">
      {list.map((t) => (
        <div key={t.id} className={`toast ${t.kind || ""}`}>
          <span>{t.text}</span>
          {t.action && (
            <button onClick={() => { t.action!.run(); setList((l) => l.filter((x) => x.id !== t.id)); }}>{t.action.label}</button>
          )}
        </div>
      ))}
    </div>
  );
}

// 1.12.17: the tile's own element is passed so the queue can rank by on-screen position; unmount releases the request
export function Thumb({ hash, className, alt }: { hash: string; className?: string; alt?: string }) {
  const [src, setSrc] = useState<string>(() => thumbNow(hash) || "");
  const ph = useRef<HTMLDivElement>(null);
  useEffect(() => {
    let on = true; const c = thumbNow(hash); setSrc(c || "");
    if (c) return;
    const release = wantThumb(hash, ph.current, (u) => { if (on) setSrc(u); });
    return () => { on = false; release(); };
  }, [hash]);
  return src ? <img className={className} src={src} alt={alt || ""} draggable={false} /> : <div ref={ph} className={`ph ${className || ""}`} />;
}

export const fmtDur = (s?: number) => {
  if (!s && s !== 0) return "";
  const m = Math.floor(s / 60), r = Math.floor(s % 60);
  return `${m}:${String(r).padStart(2, "0")}`;
};

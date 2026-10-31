import { useEffect, useState } from "react";
import { thumb } from "./api";

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

export function Thumb({ hash, className, alt }: { hash: string; className?: string; alt?: string }) {
  const [src, setSrc] = useState<string>("");
  useEffect(() => { let on = true; setSrc(""); thumb(hash).then((u) => on && setSrc(u)); return () => { on = false; }; }, [hash]);
  return src ? <img className={className} src={src} alt={alt || ""} draggable={false} /> : <div className={`ph ${className || ""}`} />;
}

export const fmtDur = (s?: number) => {
  if (!s && s !== 0) return "";
  const m = Math.floor(s / 60), r = Math.floor(s % 60);
  return `${m}:${String(r).padStart(2, "0")}`;
};

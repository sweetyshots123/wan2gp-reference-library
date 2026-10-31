import { useCallback, useEffect, useRef, useState } from "react";
import { FAV, Item, Meta, call, mediaUrl, personName, isPerson } from "./api";
import { act } from "./actions";
import EditPanel from "./EditPanel";
import { SimilarButtons } from "./Similar";
import { Thumb, toast, fmtDur } from "./ui";

interface Props {
  items: Item[]; index: number; meta: Meta; total: number;
  setIndex: (i: number) => void; close: () => void; onChanged: () => void; ensure: (from: number, to: number) => void;
}
type Rect = [number, number, number, number];
interface VEdit { url: string; kind: string; params: { rect?: Rect; start?: number; end?: number }; isVirtual: boolean; name: string; duration?: number }

const clamp = (v: number, a: number, b: number) => Math.max(a, Math.min(b, v));

export default function Viewer({ items, index, meta, total, setIndex, close, onChanged, ensure }: Props) {
  const it = items[index];
  const [url, setUrl] = useState<string | null>(null);
  const [rendering, setRendering] = useState(false);
  const [z, setZ] = useState({ s: 1, x: 0, y: 0 });
  const [panel, setPanel] = useState(() => localStorage.getItem("gal.panel") === "1");
  const [ve, setVe] = useState<VEdit | null>(null);
  const [draft, setDraft] = useState<Rect | null>(null);
  const stage = useRef<HTMLDivElement>(null);
  const media = useRef<HTMLImageElement & HTMLVideoElement>(null);
  const pts = useRef(new Map<number, { x: number; y: number }>());
  const last = useRef<{ x: number; y: number; d: number } | null>(null);
  const clickStart = useRef<{ x: number; y: number; moved: boolean } | null>(null);

  useEffect(() => { localStorage.setItem("gal.panel", panel ? "1" : "0"); }, [panel]);
  useEffect(() => { ensure(Math.max(0, index - 13), Math.min(total, index + 14)); }, [index, total, !!it]);
  const vid = useVidosser();
  // favorita al instante (optimista): el corazón cambia ya y se revierte si el servidor falla
  const [favOpt, setFavOpt] = useState<{ h: string; v: boolean } | null>(null);

  // medio a resolución completa (imagen original, vídeo o copia virtual renderizada)
  useEffect(() => {
    if (!it) return;
    let on = true, tries = 0;
    setUrl(null); setZ({ s: 1, x: 0, y: 0 }); setVe(null); setDraft(null);
    const load = () => mediaUrl(it.hash).then((r) => {
      if (!on) return;
      setRendering(!!r.rendering);
      if (r.url) setUrl(r.url);
      else if (r.rendering && tries++ < 60) window.setTimeout(load, 1000);
    });
    load();
    return () => { on = false; };
  }, [it?.hash]);

  const go = useCallback((d: number) => { const j = index + d; if (j >= 0 && j < total) setIndex(j); }, [index, total]);
  const isFav = favOpt && favOpt.h === it?.hash ? favOpt.v : !!it?.tags.some((t) => t.toLowerCase() === FAV);
  const toggleFav = () => {
    if (!it) return;
    const h = it.hash, was = isFav;
    setFavOpt({ h, v: !was });
    act("tag", { hashes: [h], ...(was ? { remove: [FAV] } : { add: [FAV] }) }, onChanged, { quiet: true })
      .then((r: any) => { if (r?.ok === false) { setFavOpt({ h, v: was }); toast("No se pudo guardar la favorita", "err"); } else toast(was ? "Quitada de favoritas" : "Añadida a favoritas ♥"); })
      .catch(() => { setFavOpt({ h, v: was }); toast("No se pudo guardar la favorita", "err"); });
  };
  useEffect(() => { if (favOpt && it && favOpt.h === it.hash && it.tags.some((t) => t.toLowerCase() === FAV) === favOpt.v) setFavOpt(null); }, [it]);

  const zoomAt = (factor: number, cx: number, cy: number) => setZ((o) => {
    const r = stage.current!.getBoundingClientRect();
    const px = cx - r.left - r.width / 2, py = cy - r.top - r.height / 2;
    const s = clamp(o.s * factor, 1, 12);
    if (s === 1) return { s: 1, x: 0, y: 0 };
    const k = s / o.s;
    return { s, x: px - (px - o.x) * k, y: py - (py - o.y) * k };
  });
  const zoomCenter = (f: number) => { const r = stage.current!.getBoundingClientRect(); zoomAt(f, r.left + r.width / 2, r.top + r.height / 2); };

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement).closest("input,textarea,select")) { if (e.key === "Escape") (e.target as HTMLElement).blur(); return; }
      const k = e.key;
      if (e.defaultPrevented) return;
      // con Vidosser en un vídeo, sus teclas mandan (l = bucle, e = vídeo anterior…): aquí solo flechas, F, Esc, h
      if (vid && media.current?.tagName === "VIDEO" && k.length === 1 && vidKeys().has(k.toLowerCase()) && k.toLowerCase() !== "f") return;
      if (k === "Escape") { ve ? setVe(null) : close(); }
      else if (k === "ArrowRight" || k === "l") go(1);
      else if (k === "ArrowLeft" || k === "h") go(-1);
      else if (k === "f" || k === "F") toggleFav();
      else if (k === "e" || k === "E") setPanel((p) => !p);
      else if (k === "+" || k === "=") zoomCenter(1.4);
      else if (k === "-") zoomCenter(1 / 1.4);
      else if (k === "0") setZ({ s: 1, x: 0, y: 0 });
      else if (k === " " && media.current?.tagName === "VIDEO") { e.preventDefault(); const v = media.current; v.paused ? v.play() : v.pause(); }
      else return;
      e.preventDefault();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [go, ve, isFav, it?.hash, vid]);

  // rueda: sin zoom = anterior/siguiente (una muesca = una foto); con zoom = desplazar; Ctrl+rueda = zoom
  const zRef = useRef(z); zRef.current = z;
  const goRef = useRef(go); goRef.current = go;
  const wheelAcc = useRef(0), wheelLock = useRef(0);
  useEffect(() => {
    const el = stage.current; if (!el) return;
    const w = (e: WheelEvent) => {
      if (ve) return;
      e.preventDefault();   // también evita el zoom de página del navegador con Ctrl
      const dy = e.deltaMode === 1 ? e.deltaY * 40 : e.deltaMode === 2 ? e.deltaY * 800 : e.deltaY;
      const dx = e.deltaMode === 1 ? e.deltaX * 40 : e.deltaX;
      if (e.ctrlKey || e.metaKey) { zoomAt(Math.exp(-dy * 0.0025), e.clientX, e.clientY); return; }
      if (zRef.current.s > 1) { setZ((o) => ({ ...o, x: o.x - dx, y: o.y - dy })); return; }
      const now = performance.now();
      if (now < wheelLock.current) { wheelLock.current = Math.max(wheelLock.current, now + 120); return; }   // inercia del trackpad
      wheelAcc.current += dy;
      if (Math.abs(wheelAcc.current) >= 50) {
        goRef.current(wheelAcc.current > 0 ? 1 : -1);
        wheelAcc.current = 0; wheelLock.current = now + 280;
      }
    };
    el.addEventListener("wheel", w, { passive: false });
    return () => el.removeEventListener("wheel", w);
  }, [ve]);

  const onDown = (e: React.PointerEvent) => {
    if (ve) return;
    (e.target as HTMLElement).setPointerCapture?.(e.pointerId);
    pts.current.set(e.pointerId, { x: e.clientX, y: e.clientY });
    last.current = null;
    if (pts.current.size === 1) clickStart.current = { x: e.clientX, y: e.clientY, moved: false };
    else if (clickStart.current) clickStart.current.moved = true;   // pellizco: no es clic
  };
  const onMove = (e: React.PointerEvent) => {
    if (!pts.current.has(e.pointerId)) return;
    pts.current.set(e.pointerId, { x: e.clientX, y: e.clientY });
    const c = clickStart.current;
    if (c && Math.hypot(e.clientX - c.x, e.clientY - c.y) > 6) c.moved = true;
    const p = [...pts.current.values()];
    if (p.length === 2) {   // pellizco
      const cx = (p[0].x + p[1].x) / 2, cy = (p[0].y + p[1].y) / 2, d = Math.hypot(p[0].x - p[1].x, p[0].y - p[1].y);
      if (last.current?.d) zoomAt(d / last.current.d, cx, cy);
      last.current = { x: cx, y: cy, d };
    } else if (p.length === 1 && z.s > 1) {   // arrastrar
      if (last.current) { const dx = e.clientX - last.current.x, dy = e.clientY - last.current.y; setZ((o) => ({ ...o, x: o.x + dx, y: o.y + dy })); }
      last.current = { x: e.clientX, y: e.clientY, d: 0 };
    }
  };
  // clic en la foto = zoom hacia ese punto; otro clic = ajustar. Arrastrar no cuenta como clic.
  const onUp = (e: React.PointerEvent) => {
    pts.current.delete(e.pointerId); last.current = null;
    const c = clickStart.current;
    if (pts.current.size === 0) clickStart.current = null;
    if (ve || !c || c.moved || e.button !== 0 || e.type === "pointercancel") return;
    if (e.target !== media.current || media.current?.tagName !== "IMG") return;
    if (z.s > 1) setZ({ s: 1, x: 0, y: 0 }); else zoomAt(2.5, e.clientX, e.clientY);
  };

  // ---------- copia virtual: recorte (imagen / vídeo) y entrada-salida (vídeo / audio)
  const openVirtual = async () => {
    const r = await call("virt_src", { hash: it.hash });
    if (!r.ok) { toast(r.error || "No disponible", "err"); return; }
    setPanel(true); setZ({ s: 1, x: 0, y: 0 });
    setVe({ url: r.url, kind: r.kind || "image", params: { ...(r.params || {}) }, isVirtual: !!r.virtual, name: r.name || it.name, duration: r.duration });
    setDraft(r.params?.rect || null);
  };
  const natSize = () => {
    const m = media.current; if (!m) return null;
    const nw = (m as any).naturalWidth || (m as any).videoWidth, nh = (m as any).naturalHeight || (m as any).videoHeight;
    return nw ? { nw, nh, r: m.getBoundingClientRect() } : null;
  };
  const cropDown = (e: React.PointerEvent) => {
    if (!ve || ve.kind === "audio") return;
    const s = natSize(); if (!s) return;
    if (ve.kind !== "image" && e.clientY > s.r.bottom - 56) return;   // deja usar los controles del vídeo
    e.preventDefault();
    const toNat = (cx: number, cy: number) => [clamp((cx - s.r.left) / s.r.width, 0, 1) * s.nw, clamp((cy - s.r.top) / s.r.height, 0, 1) * s.nh];
    const [x0, y0] = toNat(e.clientX, e.clientY);
    const mv = (ev: PointerEvent) => {
      const [x1, y1] = toNat(ev.clientX, ev.clientY);
      setDraft([Math.round(Math.min(x0, x1)), Math.round(Math.min(y0, y1)), Math.round(Math.abs(x1 - x0)), Math.round(Math.abs(y1 - y0))]);
    };
    const up = () => { window.removeEventListener("pointermove", mv); window.removeEventListener("pointerup", up); };
    window.addEventListener("pointermove", mv); window.addEventListener("pointerup", up);
  };
  const setIO = (k: "start" | "end") => { const v = media.current as HTMLVideoElement; if (v && ve) setVe({ ...ve, params: { ...ve.params, [k]: Math.round(v.currentTime * 100) / 100 } }); };
  const saveVirtual = async () => {
    if (!ve) return;
    const params: any = {};
    if (draft && draft[2] > 8 && draft[3] > 8 && ve.kind !== "audio") params.rect = draft;
    if (ve.kind !== "image") { if (ve.params.start != null) params.start = ve.params.start; if (ve.params.end != null) params.end = ve.params.end; }
    if (!Object.keys(params).length) { toast("Marca un recorte o un tramo de entrada/salida", "info"); return; }
    const r = await act(ve.isVirtual ? "virt_update" : "virt_create", { hash: it.hash, params, name: ve.name }, onChanged);
    if (r?.ok) setVe(null);
  };
  // en un vídeo con tramo, reproducir en bucle dentro del tramo
  useEffect(() => {
    const v = media.current as HTMLVideoElement | null;
    if (!v || !ve || ve.kind === "image") return;
    const t = () => { const { start, end } = ve.params; if (end != null && v.currentTime > end) v.currentTime = start || 0; };
    v.addEventListener("timeupdate", t);
    return () => v.removeEventListener("timeupdate", t);
  }, [ve]);

  if (!it) return (
    <div className="viewer"><div className="vtop"><span className="count">{index + 1} / {total}</span><span className="vbtns"><button onClick={close}>✕</button></span></div>
      <div className="vbody"><div className="stage"><div className="loading">Cargando…</div></div></div></div>);
  const src = ve ? ve.url : url;
  const kind = ve ? ve.kind : it.kind || "image";
  const rectStyle = (() => {
    const s = draft && natSize(); if (!s || !draft || !stage.current) return null;
    const st = stage.current.getBoundingClientRect();
    const k = s.r.width / s.nw;
    return { left: s.r.left - st.left + draft[0] * k, top: s.r.top - st.top + draft[1] * k, width: draft[2] * k, height: draft[3] * k };
  })();
  const tags = it.tags.filter((t) => !isPerson(t) && t.toLowerCase() !== FAV);
  const models = it.tags.filter(isPerson);

  return (
    <div className="viewer">
      <div className="vtop">
        <span className="count">{index + 1} / {total}</span>
        <span className="vname">{it.name}{it.virtual ? " · copia virtual" : ""}</span>
        <span className="vtags">
          {models.map((t) => <a key={t} href={`#/persona/${encodeURIComponent(personName(t))}`} onClick={close} className="chip model">{personName(t)}</a>)}
          {tags.slice(0, 6).map((t) => <a key={t} href={`#/tag/${encodeURIComponent(t)}`} onClick={close} className="chip">{t}</a>)}
        </span>
        <span className="vbtns">
          <button className={isFav ? "fav on" : "fav"} onClick={toggleFav} title="Favorita (F)">{isFav ? "♥" : "♡"}</button>
          <button onClick={() => zoomCenter(1 / 1.4)} title="Alejar (-)">−</button>
          <span className="zl">{Math.round(z.s * 100)}%</span>
          <button onClick={() => zoomCenter(1.4)} title="Acercar (+)">+</button>
          <button onClick={() => setZ({ s: 1, x: 0, y: 0 })} title="Ajustar (0)">⤢</button>
          {(it.kind || "image") === "image" && <SimilarButtons hash={it.hash} name={it.name} />}
          <button onClick={() => setPanel(!panel)} className={panel ? "on" : ""} title="Editar (E)">✎ Editar</button>
          <button onClick={close} title="Cerrar (Esc)">✕</button>
        </span>
      </div>
      <div className="vbody">
        <div className={`stage ${z.s > 1 ? "zoomed" : ""} ${ve ? "cropping" : ""}`} ref={stage}
          onPointerDown={ve ? cropDown : onDown} onPointerMove={onMove} onPointerUp={onUp} onPointerCancel={onUp}>
          {!src && <div className="loading">{rendering ? "Renderizando copia virtual…" : "Cargando…"}<Thumb hash={it.hash} className="blur" /></div>}
          {src && kind === "image" && (
            <img ref={media} src={src} alt={it.name} draggable={false} onLoad={() => setDraft((d) => d && [...d] as Rect)}
              style={{ transform: `translate(${z.x}px, ${z.y}px) scale(${z.s})` }} />
          )}
          {src && (kind === "video" || kind === "mask") && (
            <div className="vidhost" key={src} style={{ transform: `translate(${z.x}px, ${z.y}px) scale(${z.s})` }}>
              <video ref={media} src={src} controls autoPlay loop playsInline onLoadedMetadata={() => setDraft((d) => d && [...d] as Rect)} />
            </div>
          )}
          {src && kind === "audio" && <audio ref={media as any} src={src} controls autoPlay />}
          {ve && rectStyle && <div className="croprect" style={rectStyle} />}
          {vid && kind !== "image" && kind !== "audio" && <span className="vidbadge" title="Reproductor Vidosser (cargado desde el plugin instalado)">Vidosser {vid}</span>}
          {!ve && kind === "image" && <div className="vhint">{z.s > 1 ? "Clic: ajustar · Arrastrar o rueda: mover · Ctrl+rueda: zoom" : "Clic: zoom · Rueda: anterior / siguiente · Ctrl+rueda: zoom"}</div>}
          {!ve && index > 0 && <button className="nav prev" onClick={() => go(-1)} title="Anterior (← o rueda arriba)">‹</button>}
          {!ve && index < total - 1 && <button className="nav next" onClick={() => go(1)} title="Siguiente (→ o rueda abajo)">›</button>}
        </div>
        {panel && (
          <div className="vside">
            {ve ? (
              <div className="vedit">
                <h3>{ve.isVirtual ? "Editar copia virtual" : "Nueva copia virtual"}</h3>
                <p className="muted">El original no se toca: la copia guarda solo el recorte y el tramo, igual que en la Media Library.</p>
                <label>Nombre<input value={ve.name} onChange={(e) => setVe({ ...ve, name: e.target.value })} /></label>
                {ve.kind !== "audio" && (
                  <div>
                    <h4>Encuadre</h4>
                    <p className="muted">Arrastra sobre la imagen para marcar el recorte.</p>
                    {draft ? <p>{draft[2]}×{draft[3]} px desde ({draft[0]}, {draft[1]}) <button onClick={() => setDraft(null)}>Quitar</button></p> : <p className="muted">Sin recorte</p>}
                  </div>
                )}
                {ve.kind !== "image" && (
                  <div>
                    <h4>Tramo (clip)</h4>
                    <div className="io">
                      <button onClick={() => setIO("start")}>[ Entrada aquí</button>
                      <input type="number" step="0.1" min={0} value={ve.params.start ?? ""} placeholder="0"
                        onChange={(e) => setVe({ ...ve, params: { ...ve.params, start: e.target.value === "" ? undefined : +e.target.value } })} />
                    </div>
                    <div className="io">
                      <button onClick={() => setIO("end")}>Salida aquí ]</button>
                      <input type="number" step="0.1" min={0} value={ve.params.end ?? ""} placeholder={ve.duration ? String(ve.duration) : "fin"}
                        onChange={(e) => setVe({ ...ve, params: { ...ve.params, end: e.target.value === "" ? undefined : +e.target.value } })} />
                    </div>
                    <p className="muted">Duración del clip: {fmtDur((ve.params.end ?? ve.duration ?? 0) - (ve.params.start ?? 0))}</p>
                  </div>
                )}
                <div className="row">
                  <button className="primary" onClick={saveVirtual}>{ve.isVirtual ? "Guardar cambios" : "Crear copia virtual"}</button>
                  <button onClick={() => setVe(null)}>Cancelar</button>
                </div>
              </div>
            ) : (
              <EditPanel items={[it]} meta={meta} onChanged={onChanged} onVirtual={openVirtual} onClose={() => setPanel(false)} />
            )}
          </div>
        )}
      </div>
      <div className="filmstrip">
        {Array.from({ length: Math.min(total, index + 13) - Math.max(0, index - 12) }, (_, k) => {
          const j = Math.max(0, index - 12) + k, x = items[j];
          if (!x) return <button key={"p" + j} onClick={() => setIndex(j)}><span className="ph" /></button>;
          return <button key={x.hash} className={j === index ? "cur" : ""} onClick={() => setIndex(j)}><Thumb hash={x.hash} /></button>;
        })}
      </div>
    </div>
  );
}

// Vidosser: se carga UNA vez el reproductor del plugin instalado (/vidosser/vidosser.js, servido en vivo por Vidosser:
// lo que cambie en su código o ajustes llega aquí al recargar). Si Vidosser no está, queda el <video> normal.
let vidState: Promise<string | null> | null = null;
function loadVidosser(): Promise<string | null> {
  if (!vidState) vidState = new Promise((res) => {
    const w = window as any;
    if (w.vidosser) { res(w.vidosser.version || "?"); return; }
    const s = document.createElement("script");
    s.src = "/vidosser/vidosser.js"; s.async = true;
    const done = () => res(w.vidosser ? String(w.vidosser.version || "?") : null);
    window.addEventListener("vidosser:ready", done, { once: true });
    s.onload = () => window.setTimeout(done, 50);
    s.onerror = () => res(null);
    document.head.appendChild(s);
  });
  return vidState;
}
function useVidosser() {
  const [v, setV] = useState<string | null>(null);
  useEffect(() => { let on = true; loadVidosser().then((x) => on && setV(x)); return () => { on = false; }; }, []);
  return v;
}
function vidKeys(): Set<string> {
  const k = (window as any).vidosser?.settings?.keys || {};
  return new Set(Object.values(k).filter((x) => typeof x === "string").map((x: any) => x.toLowerCase()));
}

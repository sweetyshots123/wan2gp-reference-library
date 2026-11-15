// Compact chip row = the Media Library's Colecciones / Etiquetas rows, same shared rules (../../chip_rules.js,
// ReflibChips): one line by default with a "+N" toggle and a filter field; open = ~3 lines with inner scroll; active
// chips first (always visible); most used first; people (persona: / modelo:) grouped without the prefix; the open
// state is remembered in localStorage with the same key as the Media Library.
import { useLayoutEffect, useRef, useState } from "react";
import "../../chip_rules.js";

export type ChipItem = { id: string; label: string; count?: number; active?: boolean; fixed?: boolean; group?: string };
type CR = {
  arrange: (i: ChipItem[]) => ChipItem[]; match: (i: ChipItem, q: string) => boolean; hiddenCount: (tops: number[]) => number;
  tagItems: (t: { tag: string; count: number }[], on: (t: string) => boolean) => ChipItem[];
  isOpen: (s: Storage | null, row: string) => boolean; setOpen: (s: Storage | null, row: string, on: boolean) => void;
};
export const Chips: CR = (globalThis as any).ReflibChips;

export function ChipRow({ row, items, onPick }: { row: string; items: ChipItem[]; onPick: (it: ChipItem) => void }) {
  const [open, setOpenSt] = useState(() => Chips.isOpen(null, row));
  const [q, setQ] = useState("");
  const [hid, setHid] = useState(0);
  const box = useRef<HTMLDivElement>(null);
  const list = Chips.arrange(items);
  const sig = list.map((x) => x.id + (x.active ? "*" : "")).join("|") + "§" + q;
  useLayoutEffect(() => {
    const el = box.current; if (!el) return;
    const m = () => setHid(Chips.hiddenCount([...el.querySelectorAll<HTMLElement>("button.chip:not([hidden])")].map((c) => c.offsetTop)));
    m();
    const ro = new ResizeObserver(m); ro.observe(el);
    return () => ro.disconnect();
  }, [sig, open]);
  let grp = false;
  return (
    <div className={`facets chiprow ${open ? "open" : ""}`} data-row={row}>
      <input type="search" className="chipq" value={q} placeholder="Filtrar…" aria-label="Filtrar etiquetas" onChange={(e) => setQ(e.target.value)} />
      {(open || hid > 0) && <button className="chipmore" aria-expanded={open} title={open ? "Mostrar una sola línea" : `Mostrar ${hid} más (se recuerda)`}
        onClick={() => { Chips.setOpen(null, row, !open); setOpenSt(!open); }}>{open ? "−" : `+${hid}`}</button>}
      <div className="chipbox" ref={box}>
        {list.map((x) => {
          const g = !grp && !x.active && !x.fixed && x.group === "people" ? (grp = true) : false;
          return [g && <span key="§grp" className="chipgrp" title="Personas (persona: / modelo:)">👤</span>,
            <button key={x.id} hidden={!Chips.match(x, q)} title={x.id} className={`chip ${x.active ? "on" : ""} ${x.group === "people" ? "model" : ""}`} onClick={() => onPick(x)}>
              {x.label}{x.active ? " ×" : x.count != null ? <small>{x.count}</small> : null}</button>];
        })}
      </div>
    </div>
  );
}

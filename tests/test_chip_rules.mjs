// node tests/test_chip_rules.mjs — compact chip rows (chip_rules.js), shared by the Media Library and the Galería.
// Pure / synthetic only, plus static checks that both UIs and plugin.py use the shared module.
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
const root = path.join(path.dirname(fileURLToPath(import.meta.url)), "..");
await import(path.join(root, "chip_rules.js"));
const C = globalThis.ReflibChips;
// people prefix → group, shown without it
assert.deepEqual(C.split("persona:Ana"), { group: "people", name: "Ana" });
assert.deepEqual(C.split("Modelo: Bea"), { group: "people", name: "Bea" });
assert.deepEqual(C.split("playa"), { group: "", name: "playa" });
// arrange: fixed first (given order), then active (by count), then plain tags by count, then people by count; ties by label
const tags = [{ tag: "playa", count: 3 }, { tag: "persona:Ana", count: 50 }, { tag: "noche", count: 9 }, { tag: "modelo:Bea", count: 7 }, { tag: "Árbol", count: 9 }, { tag: "rojo", count: 1 }];
const items = C.tagItems(tags, (t) => t === "rojo" || t === "persona:Ana");
const ids = C.arrange([{ id: "all", label: "Todas", fixed: true }, ...items]).map((x) => x.id);
assert.deepEqual(ids, ["all", "persona:Ana", "rojo", "Árbol", "noche", "playa", "modelo:Bea"]);
assert.equal(items.find((x) => x.id === "persona:Ana").label, "Ana");
// match: accents / case folded, on the label or the full tag; active and fixed always shown
const by = (id) => items.find((x) => x.id === id);
assert.equal(C.match(by("Árbol"), "arb"), true);
assert.equal(C.match(by("modelo:Bea"), "MODELO"), true);
assert.equal(C.match(by("playa"), "noc"), false);
assert.equal(C.match(by("rojo"), "zzz"), true, "an active chip never disappears");
assert.equal(C.match({ id: "all", label: "Todas", fixed: true }, "zzz"), true);
assert.equal(C.match(by("playa"), ""), true);
// hidden count = chips below the first line
assert.equal(C.hiddenCount([0, 0, 0, 29, 29, 58]), 3);
assert.equal(C.hiddenCount([5, 5, 5]), 0);
assert.equal(C.hiddenCount([]), 0);
// open state per row, one key for both UIs
const mem = new Map(), st = { getItem: (k) => mem.get(k) ?? null, setItem: (k, v) => mem.set(k, String(v)) };
assert.equal(C.isOpen(st, "tags"), false);
C.setOpen(st, "tags", true); assert.equal(C.isOpen(st, "tags"), true); assert.equal(mem.get("reflib_chips_open_tags"), "1");
C.setOpen(st, "tags", false); assert.equal(C.isOpen(st, "tags"), false);
assert.equal(C.isOpen({ getItem() { throw new Error("blocked"); } }, "tags"), false, "storage errors = collapsed");
// wiring: plugin.py shared tuple, ML rows and the Galería ChipRow use the module
const pl = fs.readFileSync(path.join(root, "plugin.py"), "utf8");
assert.match(/for _shared in \(([^)]*)\)/.exec(pl)[1], /"chip_rules\.js"/);
const js = fs.readFileSync(path.join(root, "reference_library.js"), "utf8");
assert.match(js, /chipRowHTML\("cols"/); assert.match(js, /chipRowHTML\("tags"/); assert.match(js, /C\.arrange\(items\)/); assert.match(js, /C\.hiddenCount\(tops\)/); assert.match(js, /ReflibChips\.setOpen\(null, el\.dataset\.row, on\)/);
const cr = fs.readFileSync(path.join(root, "gallery/src/ChipRow.tsx"), "utf8"), app = fs.readFileSync(path.join(root, "gallery/src/App.tsx"), "utf8");
assert.match(cr, /import "\.\.\/\.\.\/chip_rules\.js"/); assert.match(cr, /Chips\.arrange\(items\)/); assert.match(cr, /Chips\.hiddenCount\(/); assert.match(cr, /Chips\.setOpen\(null, row/);
assert.match(app, /<ChipRow row="gtags"/);
console.log("test_chip_rules: ok");

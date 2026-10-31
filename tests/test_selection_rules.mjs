// node tests/test_selection_rules.mjs  — unit test of selection_rules.js + parity check (both UIs use it)
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
const root = path.join(path.dirname(fileURLToPath(import.meta.url)), "..");
await import(path.join(root, "selection_rules.js"));
const RS = globalThis.ReflibSelection;
const E = { shift: false, ctrl: false };
assert.deepEqual(RS.cardClick(-1, 3, false, E), { op: "single", anchor: 3, preview: true });
assert.equal(RS.cardClick(2, 3, true, E).op, "keep");
assert.deepEqual(RS.cardClick(1, 4, false, { ...E, ctrl: true }), { op: "toggle", anchor: 4 });
assert.deepEqual(RS.cardClick(1, 4, false, { shift: true, ctrl: false }), { op: "range", from: 1, to: 4, additive: false, anchor: 1 });
assert.equal(RS.cardClick(1, 4, false, { shift: true, ctrl: true }).additive, true);
assert.equal(RS.cardClick(-1, 4, false, { shift: true, ctrl: false }).op, "single");   // no anchor yet
assert.deepEqual(RS.boxClick(-1, 2, { shift: false }), { op: "toggle", anchor: 2 });
assert.deepEqual(RS.boxClick(5, 2, { shift: true }), { op: "range", from: 5, to: 2, additive: true, anchor: 2 });
assert.equal(RS.boxClick(2, 2, { shift: true }).op, "toggle");
assert.deepEqual(RS.rangeBounds(7, 3), [3, 7]);
assert.deepEqual(RS.rangeBounds(0, 99, 10), [0, 9]);
assert.deepEqual(RS.key({ ctrl: true, key: "a" }, false), { op: "all" });
assert.deepEqual(RS.key({ key: "Escape" }, true), { op: "clear" });
assert.equal(RS.key({ key: "Escape" }, false), null);
const s = new Set(["x"]);
RS.apply(s, { op: "range", from: 0, to: 2, additive: true }, null, (a, b) => ["a", "b", "c"].slice(a, b + 1));
assert.deepEqual([...s], ["x", "a", "b", "c"]);
// parity: both UIs consume the same file, and neither reimplements the rules
const ml = fs.readFileSync(path.join(root, "reference_library.js"), "utf8");
const gal = fs.readFileSync(path.join(root, "gallery/src/Selection.ts"), "utf8");
const py = fs.readFileSync(path.join(root, "plugin.py"), "utf8");
assert.match(py, /"selection_rules\.js"/);
assert.match(ml, /window\.ReflibSelection/);
for (const f of ["cardClick", "boxClick", "rangeBounds", "key("]) { assert.ok(ml.includes("RS." + f), "ML uses RS." + f); assert.ok(gal.includes("RS." + f), "Galería uses RS." + f); }
assert.match(gal, /import "\.\.\/\.\.\/selection_rules\.js"/);
const dist = fs.readdirSync(path.join(root, "gallery/dist/assets")).filter((f) => f.endsWith(".js")).map((f) => fs.readFileSync(path.join(root, "gallery/dist/assets", f), "utf8")).join("");
assert.ok(dist.includes("ReflibSelection"), "built Galería bundles selection_rules.js");
console.log("selection_rules: all tests passed");

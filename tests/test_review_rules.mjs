// node tests/test_review_rules.mjs
import assert from "node:assert";
await import("../selection_rules.js"); await import("../review_rules.js");
const R = globalThis.ReflibReview;
const faces = [0.9, 0.8, 0.7, 0.6, 0.5].map((s, i) => ({ id: "f" + i, score: s })), ids = faces.map(f => f.id);
const st = { discard: new Set(), anchor: -1 };
R.click(st, ids, 1, {}); assert.deepEqual([...st.discard], ["f1"]);
R.click(st, ids, 1, {}); assert.equal(st.discard.size, 0);              // toggles back
R.click(st, ids, 1, {}); R.click(st, ids, 3, { shift: true });            // range 1..3
assert.deepEqual([...st.discard].sort(), ["f1", "f2", "f3"]);
assert.deepEqual(R.plan(faces, st.discard), { accept: ["f0", "f4"], reject: ["f1", "f2", "f3"] });
assert.deepEqual(R.plan(faces, new Set(), 65), { accept: ["f0", "f1", "f2"], reject: ["f3", "f4"] });
assert.deepEqual(R.key("ArrowDown", 0, 5, 3), { op: "move", to: 3 }); assert.equal(R.key("Delete").op, "discard"); assert.equal(R.key("Enter").op, "confirm");
console.log("review rules ok");

// node --test tests/test_filter_rules.mjs — 1.12.18: shared favourites rule (filter_rules.js, both UIs).
import test from "node:test"; import assert from "node:assert/strict";
import "../filter_rules.js";
const RF = globalThis.ReflibFilters;
test("favourite tag is case-insensitive and shared", () => {
  assert.equal(RF.FAV_TAG, "favorita");
  assert.equal(RF.isFav(["x", "Favorita"]), true); assert.equal(RF.isFav(["favoritas"]), false); assert.equal(RF.isFav(null), false);
});
test("withFav copies and toggles only fav", () => {
  const f = { tags: ["a"] };
  assert.deepEqual(RF.withFav(f, true), { tags: ["a"], fav: true }); assert.deepEqual(f, { tags: ["a"] });
  assert.deepEqual(RF.withFav({ fav: true, q: "x" }, false), { q: "x" });
});
test("favCount and favToggle", () => {
  assert.equal(RF.favCount([{ tag: "a", n: 3 }, { tag: "Favorita", count: 4 }]), 4); assert.equal(RF.favCount([]), 0);
  assert.deepEqual(RF.favToggle(["favorita"]), { remove: ["favorita"] }); assert.deepEqual(RF.favToggle([]), { add: ["favorita"] });
});

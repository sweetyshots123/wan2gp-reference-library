// node --test tests/test_view_state_rules.mjs
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.join(path.dirname(fileURLToPath(import.meta.url)), "..");
await import(path.join(root, "view_state_rules.js"));
const VS = globalThis.ReflibViewState;

function memStorage(initial = {}) {
  const map = new Map(Object.entries(initial).map(([k, v]) => [k, String(v)]));
  return {
    getItem(k) { return map.has(k) ? map.get(k) : null; },
    setItem(k, v) { map.set(k, String(v)); },
    removeItem(k) { map.delete(k); },
    _dump() { return Object.fromEntries(map.entries()); },
  };
}

test("shouldRemember defaults ON and obeys server/localStorage flag", () => {
  const ls = memStorage();
  assert.equal(VS.shouldRemember(null, ls), true);
  assert.equal(VS.shouldRemember(false, ls), false);
  assert.equal(VS.shouldRemember({ browser_remember_state: false }, ls), false);
  assert.equal(VS.shouldRemember(true, ls), true);

  VS.syncRememberFlag(ls, false);
  assert.equal(ls.getItem(VS.KEYS.remember), "0");
  assert.equal(VS.shouldRemember(null, ls), false);
  assert.equal(VS.shouldRemember(true, ls), true);

  VS.syncRememberFlag(ls, true);
  assert.equal(ls.getItem(VS.KEYS.remember), "1");
  assert.equal(VS.shouldRemember(null, ls), true);
});

test("Media Library normalize drops ephemeral sim and saves/loads round-trip", () => {
  const ls = memStorage();
  const state = {
    f: {
      q: "retrato",
      cols: ["col1"],
      tags: ["persona:Ana", "luz"],
      node: { fid: "f1", rel: "sub/a" },
      sub: false,
      kind: "image",
      fav: true,
      origins: ["real"],
      sim: "ephemeral-sid-99",
      atags: ["at1"],
      xtags: ["at2"],
      ranges: { height: [160, 180] },
      jst: "done",
    },
    sort: "name_asc",
    recentPages: 3,
    expanded: ["f1"],
    chipQ: { cols: "col", tags: "ana" },
    atOpen: ["body"],
    scroll: 420,
    treeScroll: 85,
  };
  VS.saveML(ls, state, "date_desc");
  const loaded = VS.loadML(ls, "date_desc");
  assert.equal(loaded.f.q, "retrato");
  assert.deepEqual(loaded.f.cols, ["col1"]);
  assert.deepEqual(loaded.f.tags, ["persona:ana", "luz"]);
  assert.deepEqual(loaded.f.node, { fid: "f1", rel: "sub/a" });
  assert.equal(loaded.f.sub, false);
  assert.equal(loaded.f.kind, "image");
  assert.equal(loaded.f.fav, true);
  assert.deepEqual(loaded.f.origins, ["real"]);
  assert.equal(loaded.sort, "name_asc");
  assert.equal(loaded.f.sim, "");
  assert.deepEqual(loaded.f.atags, ["at1"]);
  assert.deepEqual(loaded.f.xtags, ["at2"]);
  assert.deepEqual(loaded.f.ranges, { height: [160, 180] });
  assert.equal(loaded.f.jst, "done");
  assert.equal(loaded.recentPages, 3);
  assert.deepEqual(loaded.expanded, ["f1"]);
  assert.deepEqual(loaded.chipQ, { cols: "col", tags: "ana" });
  assert.deepEqual(loaded.atOpen, ["body"]);
  assert.equal(loaded.scroll, 420);
  assert.equal(loaded.treeScroll, 85);

  VS.clearML(ls);
  assert.equal(VS.loadML(ls, "date_desc"), null);
});

test("Media Library mlPruneStale drops missing cols/tags/folders and falls back to nearest parent rel", () => {
  const meta = {
    collections: [{ id: "c1", name: "Keep" }],
    tags: [{ tag: "keep_tag", n: 5 }, { tag: "Persona:Ana", n: 3 }],
    folders: [{
      id: "f1",
      tree: {
        rel: "",
        children: [
          { rel: "a", children: [{ rel: "a/b", children: [] }] },
        ],
      },
    }],
  };
  const st = VS.mlNormalize({
    f: {
      cols: ["c1", "c_deleted"],
      folders: ["f1", "f_deleted"],
      tags: ["keep_tag", "persona:ana", "deleted_tag"],
      node: { fid: "f1", rel: "a/b/c_deleted" },
    },
    expanded: ["f1", "f_deleted"],
  });
  const res = VS.mlPruneStale(st, meta);
  assert.equal(res.changed, true);
  assert.deepEqual(res.state.f.cols, ["c1"]);
  assert.deepEqual(res.state.f.folders, ["f1"]);
  assert.deepEqual(res.state.f.tags, ["keep_tag", "persona:ana"]);
  assert.deepEqual(res.state.f.node, { fid: "f1", rel: "a/b" });
  assert.deepEqual(res.state.expanded, ["f1"]);

  // Deleted folder entirely -> node becomes null
  const st2 = VS.mlNormalize({ f: { node: { fid: "gone", rel: "x" } } });
  const res2 = VS.mlPruneStale(st2, meta);
  assert.equal(res2.changed, true);
  assert.equal(res2.state.f.node, null);
});

test("mlHasActiveFilters detects filters, chipQ, and non-default sort", () => {
  const def = VS.mlDefaultFilter("date_desc");
  assert.equal(VS.mlHasActiveFilters(def, {}, "date_desc"), false);
  assert.equal(VS.mlHasActiveFilters({ ...def, q: "hola" }, {}, "date_desc"), true);
  assert.equal(VS.mlHasActiveFilters({ ...def, fav: true }, {}, "date_desc"), true);
  assert.equal(VS.mlHasActiveFilters(def, {}, "name_asc", "date_desc"), true);
  assert.equal(VS.mlHasActiveFilters(def, { tags: "ana" }, "date_desc"), true);
});

test("Galería resolveStartupRoute, save/load, and stale pruning", () => {
  const ls = memStorage();
  assert.equal(VS.resolveStartupRoute("", "#/coleccion/c1", true), "#/coleccion/c1");
  assert.equal(VS.resolveStartupRoute("#/", "#/carpeta/f1/sub", true), "#/carpeta/f1/sub");
  assert.equal(VS.resolveStartupRoute("#/favoritas", "#/coleccion/c1", true), "#/favoritas");
  assert.equal(VS.resolveStartupRoute("#/", "#/coleccion/c1", false), "#/");
  assert.equal(VS.resolveStartupRoute("#/", "#/similares", true), "#/");

  VS.saveGal(ls, {
    route: "#/buscar",
    text: "estudio",
    chips: [{ k: "tag", v: "luz", label: "luz" }],
    kinds: ["image"],
    origins: ["real"],
    sort: "name_asc",
    extraTags: ["persona:Ana"],
    chipQ: { gtags: "ana" },
    af: { atags: ["at1"], xtags: [], ranges: { height: [160, null] }, jst: "" },
    afOpen: ["pose"],
    fpanel: true,
    fopen: false,
    manage: true,
    size: 280,
    scroll: 750,
  }, "date_desc");

  const loaded = VS.loadGal(ls, "date_desc");
  assert.equal(loaded.route, "#/buscar");
  assert.equal(loaded.text, "estudio");
  assert.equal(loaded.chips.length, 1);
  assert.deepEqual(loaded.kinds, ["image"]);
  assert.deepEqual(loaded.origins, ["real"]);
  assert.equal(loaded.sort, "name_asc");
  assert.deepEqual(loaded.extraTags, ["persona:Ana"]);
  assert.deepEqual(loaded.chipQ, { gtags: "ana" });
  assert.deepEqual(loaded.af.atags, ["at1"]);
  assert.deepEqual(loaded.afOpen, ["pose"]);
  assert.equal(loaded.fpanel, true);
  assert.equal(loaded.fopen, false);
  assert.equal(loaded.manage, true);
  assert.equal(loaded.size, 280);
  assert.equal(loaded.scroll, 750);

  const meta = {
    collections: [{ id: "c1" }],
    tags: [{ tag: "persona:Ana" }],
    folders: [{ id: "f1", tree: { rel: "", children: [{ rel: "a", children: [] }] } }],
  };
  const pr = VS.galPruneStale({
    route: "#/coleccion/deleted",
    chips: [{ k: "col", v: "deleted", label: "deleted" }, { k: "tag", v: "persona:Ana", label: "Ana" }],
    extraTags: ["persona:Ana", "gone_tag"],
  }, meta, false);
  assert.equal(pr.changed, true);
  assert.equal(pr.state.route, "#/");
  assert.deepEqual(pr.state.chips, [{ k: "tag", v: "persona:Ana", label: "Ana" }]);
  assert.deepEqual(pr.state.extraTags, ["persona:Ana"]);

  // Active filter detection
  assert.equal(VS.galHasActiveFilters({ route: "#/", text: "", chips: [], kinds: [], origins: [], sort: "date_desc", extraTags: [], chipQ: {}, af: {} }, "date_desc"), false);
  assert.equal(VS.galHasActiveFilters({ route: "#/favoritas", text: "", chips: [], kinds: [], origins: [], sort: "date_desc", extraTags: [], chipQ: {}, af: {} }, "date_desc"), true);
});

test("Wiring check: plugin.py, reference_library.js, gallery/src/App.tsx", () => {
  const py = fs.readFileSync(path.join(root, "plugin.py"), "utf8");
  const ml = fs.readFileSync(path.join(root, "reference_library.js"), "utf8");
  const app = fs.readFileSync(path.join(root, "gallery/src/App.tsx"), "utf8");
  assert.match(py, /"view_state_rules\.js"/);
  assert.match(py, /browser_remember_state/);
  assert.match(ml, /ReflibViewState/);
  assert.match(ml, /resetAllFilters/);
  assert.match(app, /view_state_rules\.js/);
  assert.match(app, /ReflibViewState/);
  assert.match(app, /Restablecer filtros/);
});

// node tests/test_stale_bar.mjs — 1.12.14: Galería stale-tab bar rule + EN/ES texts (real module gallery/src/stale.ts).
import assert from "node:assert/strict";
import path from "node:path";
import { fileURLToPath } from "node:url";
const root = path.join(path.dirname(fileURLToPath(import.meta.url)), "..");
const S = await import(path.join(root, "gallery/src/stale.ts"));
assert.equal(S.staleShow("1.12.14", "1.12.13", null), true);
assert.equal(S.staleShow("1.12.14", "1.12.14", null), false, "same build");
assert.equal(S.staleShow("1.12.14", "1.12.13", "1.12.14"), false, "closed once for this server version");
assert.equal(S.staleShow("1.12.15", "1.12.13", "1.12.14"), true, "a newer server version shows again");
assert.equal(S.staleShow(undefined, "1.12.13", null), false);
const es = S.staleText("es-ES", "1.12.13", "1.12.14"), en = S.staleText("en-US", "1.12.13", "1.12.14");
assert.match(es.msg, /servidor ya usa la 1\.12\.14/); assert.equal(es.reload, "Recargar"); assert.equal(es.close, "Cerrar");
assert.match(en.msg, /server already runs 1\.12\.14/); assert.equal(en.reload, "Reload"); assert.equal(en.close, "Close");
console.log("test_stale_bar: ok");

// node tests/test_standalone_rules.mjs
import assert from "node:assert/strict";
import path from "node:path";
import fs from "node:fs";
import { fileURLToPath } from "node:url";
const root = path.join(path.dirname(fileURLToPath(import.meta.url)), "..");
await import(path.join(root, "standalone_rules.js"));
const S = globalThis.ReflibStandalone;
assert.equal(S.version, 1);
assert.equal(S.isStandalone(true), true);
assert.equal(S.isStandalone(false), false);
assert.equal(S.showWanBridgeActions(true), false);
assert.equal(S.showWanBridgeActions(false), true);
assert.match(S.bridgeMissingMessage("es"), /WanGP/);
assert.match(S.bridgeMissingMessage("en"), /WanGP/);
assert.match(S.bridgeMissingMessage("es"), /necesita/);
assert.match(S.bridgeMissingMessage("en"), /needs/);
S.resetNotices();
const a = S.takeBridgeNotice("es");
const b = S.takeBridgeNotice("es");
assert.ok(a && /WanGP/.test(a));
assert.equal(b, null);

// Source contracts: Viewer must not hardcode offerLabels(..., "es")
const viewer = fs.readFileSync(path.join(root, "gallery/src/Viewer.tsx"), "utf8");
assert.ok(!/offerLabels\([^)]*,\s*["']es["']\s*\)/.test(viewer), "Viewer must not hardcode offerLabels lang es");
assert.ok(/uiLang|document\.documentElement\.lang|navigator\.language/.test(viewer), "Viewer must use UI lang");

// FEATURES Open Media Library bullet: the Reference Library *top link* target is media-library
const feat = fs.readFileSync(path.join(root, "docs/FEATURES.md"), "utf8");
const openMl = feat.split("\n").find((l) => /\*\*Open Media Library:\*\*/i.test(l));
assert.ok(openMl, "FEATURES must mention Open Media Library");
const top = openMl.match(/top link[^→\n]*→\s*`(\/reflib\/[^`]+)`/);
assert.ok(top, "FEATURES Open Media Library must name the top-link URL");
assert.equal(top[1], "/reflib/media-library/", "Open Media Library top link → /reflib/media-library/");

// Standalone must hide torefs when showWanBridgeActions is false (mediaActions wiring)
const js = fs.readFileSync(path.join(root, "reference_library.js"), "utf8");
assert.match(js, /ReflibStandalone|showWanBridgeActions/);
assert.match(js, /takeBridgeNotice|bridgeMissingMessage/);
// 1.12.10 BUG-3b: apply/vadd/vapply catches must not re-toast wan_bridge_unavailable
assert.match(js, /bridgeFailToast/);
assert.match(js, /wan_bridge_unavailable/);
const catches = [...js.matchAll(/bridgeFailToast\("[^"]+",\s*err\)/g)];
assert.ok(catches.length >= 3, "expected bridgeFailToast on apply/vadd/vapply paths, got " + catches.length);

assert.ok(js.includes("showWanBridgeActions") && js.includes("torefs"), "torefs gated by standalone rules");

console.log("test_standalone_rules: ok");

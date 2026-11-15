// node tests/test_browser_indexing.mjs — 1.12.16: while a folder is being indexed, both UIs refresh counts / the changed
// page only: loaded pages and cards stay (no "Cargando…" wipe, no body rebuild), shared ReflibNet.scanRefresh.
// REAL code in headless Chrome (built Galería + standalone Media Library) against tests/browser/server.mjs.
// Synthetic only. Skips (exit 0) when google-chrome / ffmpeg / gallery/dist are missing.
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawn, spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
const root = path.join(path.dirname(fileURLToPath(import.meta.url)), "..");
const has = (cmd) => spawnSync("sh", ["-c", "command -v " + cmd]).status === 0;
const DIST = path.join(root, "gallery/dist");
if (!has("google-chrome") || !has("ffmpeg") || !fs.existsSync(path.join(DIST, "index.html"))) { console.log("test_browser_indexing: SKIP"); process.exit(0); }
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "reflib-idx-"));
const MEDIA = path.join(tmp, "media"); fs.mkdirSync(MEDIA);
spawnSync("ffmpeg", ["-v", "error", "-f", "lavfi", "-i", "testsrc=duration=4:size=160x90:rate=10", "-c:v", "libvpx", "-b:v", "100k", path.join(MEDIA, "clip.webm")]);
spawnSync("ffmpeg", ["-v", "error", "-f", "lavfi", "-i", "color=c=red:s=64x64", "-frames:v", "1", path.join(MEDIA, "img.png")]);
const VERSION = JSON.parse(fs.readFileSync(path.join(root, "plugin_info.json"), "utf8")).version;
const { freePort } = await import(path.join(root, "tests/browser/ports.mjs"));
const PORT = await freePort(); let CDP = await freePort(); while (CDP === PORT) CDP = await freePort();
const BASE = `http://127.0.0.1:${PORT}`;
const srv = spawn(process.execPath, [path.join(root, "tests/browser/server.mjs")], { env: { ...process.env, DIST, PLUGIN: root, VERSION, PORT: String(PORT), MEDIA, QDELAY: "60" }, stdio: ["ignore", "pipe", "inherit"] });
process.on("exit", () => { try { srv.kill(); } catch {} });   // 1.12.18: never leave the mock running (it holds the runner's stderr)
await new Promise((r) => srv.stdout.once("data", r));
process.env.CHROME_PROFILE = path.join(tmp, "chrome");
const { launch } = await import(path.join(root, "tests/browser/cdp.mjs"));
const c = await launch(CDP); const ev = c.ev;
const done = (code) => { try { c.close(); } catch {} srv.kill(); try { fs.rmSync(tmp, { recursive: true, force: true }); } catch {} process.exit(code); };
const post = async (p, b = {}) => (await fetch(BASE + p, { method: "POST", body: JSON.stringify(b) })).json();
async function waitFor(expr, ms = 8000) { const t0 = Date.now(); while (Date.now() - t0 < ms) { try { if (await ev(expr)) return true; } catch {} await sleep(50); } return false; }
const fails = [];
async function check(name, fn) { try { await fn(); console.log("  ok  " + name); } catch (e) { fails.push(name); console.log("  FAIL " + name + ": " + (e && e.message)); } }
const queries = async () => (await post("/test/log")).log.filter((a) => a === "query").length;

// watch for a wipe: any moment with a loading message, skeleton-only grid or no cards
const ML_WATCH = `(() => { window.__wipe = 0; const chk = () => { const g = document.querySelector('.reflib-ib-vgrid');
  if (!g || document.querySelector('.reflib-ib-loading') || !g.querySelector('.reflib-ib-card')) window.__wipe++; };
  window.__wipeT = setInterval(chk, 20); new MutationObserver(chk).observe(document.body, { childList: true, subtree: true }); return true; })()`;

console.log("Media Library (standalone)");
async function mBoot(scan) {
  await post("/test/reset"); if (scan) await post("/test/scan", { running: true });
  await c.send("Page.navigate", { url: BASE + "/reflib/media-library/" });
  if (!await waitFor(`document.querySelectorAll('.reflib-ib-card').length > 5`, 10000)) throw new Error("no cards");
  await sleep(800);
  await ev(`(() => { document.querySelectorAll('.reflib-ib-card').forEach((e) => e._mark = 1); document.querySelector('.reflib-ib-body')._mark = 1; return true; })()`);
  await ev(ML_WATCH);
}
const mState = () => ev(`(() => { const cards = [...document.querySelectorAll('.reflib-ib-card')]; return { cards: cards.length, kept: cards.filter((e) => e._mark).length,
  body: !!document.querySelector('.reflib-ib-body')._mark, wipe: window.__wipe, dec: window.__mlDec || null, footer: document.querySelector('.reflib-ib-foot, .reflib-ib-footer')?.textContent || '' }; })()`);
await check("indexing, nothing new on screen (old-dated file): counts only — same body, same cards, no wipe", async () => {
  await mBoot(true);
  const q0 = await queries();
  await post("/test/add", { old: true }); await sleep(4500);
  const s = await mState();
  assert.equal(s.wipe, 0, "no loading / empty grid moment");
  assert.equal(s.body, true, "body not rebuilt");
  assert.equal(s.kept, s.cards, "every card is the same DOM node: " + JSON.stringify(s));
  assert.ok(s.cards > 5);
  assert.ok((await queries()) - q0 <= 2, "only the refresh query (no re-fetch of every loaded page)");
});
await check("indexing, new file at the top: page applied in place, no wipe, body kept", async () => {
  await mBoot(true);
  const h = (await post("/test/add", { old: false })).hash; await sleep(4500);
  const s = await mState();
  assert.equal(s.wipe, 0); assert.equal(s.body, true);
  assert.equal(await ev(`document.querySelector('.reflib-ib-card[data-idx="0"]')?.dataset.hash || document.querySelector('.reflib-ib-card[data-idx="0"] [data-hash]')?.dataset.hash || ''`), h);
});
await check("indexing finished: one normal refresh afterwards (as before)", async () => {
  await mBoot(true); await post("/test/scan", { running: false }); await post("/test/add", { old: false }); await sleep(2500);
  assert.ok((await mState()).cards > 5);
});

console.log("Galería");
async function gBoot(scan) {
  await post("/test/reset"); if (scan) await post("/test/scan", { running: true });
  await c.send("Page.navigate", { url: BASE + "/reflib/gallery/#/" }); await sleep(300);
  await ev(`localStorage.setItem('gal.sort','date_desc'); localStorage.setItem('gal.kinds','[]'); true`);
  await c.send("Page.reload", { ignoreCache: true });
  if (!await waitFor(`document.querySelectorAll('figure.tile').length > 5`, 10000)) throw new Error("no tiles");
  await ev(`(() => { window.scrollTo(0, 99999); return true; })()`); await sleep(1200);   // load more pages
  await ev(`(() => { window.scrollTo(0, 0); window.__gw = 0; const chk = () => { if (!document.querySelector('figure.tile') || [...document.querySelectorAll('.loading')].some((e) => /Cargando/.test(e.textContent))) window.__gw++; };
    window.__gwT = setInterval(chk, 20); return true; })()`);
}
await check("indexing, rev changed but page 0 unchanged: counts only, no other page re-fetched", async () => {
  await gBoot(true);
  const q0 = await queries();
  await post("/test/touch"); await sleep(6500);
  assert.equal((await queries()) - q0, 1, "only page 0 (+counts), no re-fetch of the other loaded pages");
  const dec = await ev(`window.__galScanRefresh || null`);
  assert.ok(dec && dec.countsOnly, "countsOnly: " + JSON.stringify(dec));
  assert.equal(await ev(`window.__gw`), 0, "no wipe");
});
await check("indexing, new file at the top: applied in place, no wipe", async () => {
  await gBoot(true);
  await post("/test/add", { old: false }); await sleep(6500);
  const dec = await ev(`window.__galScanRefresh || null`);
  assert.ok(dec && dec.applyPage && dec.refetchOthers, JSON.stringify(dec));
  assert.equal(await ev(`window.__gw`), 0, "no wipe");
  assert.match(await ev(`document.querySelector('figure.tile')?.textContent || document.querySelector('figure.tile img')?.alt || ''`) + "", /new_|/);
});
// 1.12.17 (retest repro gal_deep_stale): an item replaced deep in the list while indexing (total and page 0 unchanged
// -> countsOnly), then the scan ends: the indexing->idle transition must re-fetch every loaded page.
const gNames = async () => { const out = new Set(); for (let y = 0; y <= 30; y++) { const r = await ev(`(() => { window.scrollTo(0, ${y} * document.body.scrollHeight / 30); return [...document.querySelectorAll('figure.tile figcaption span')].map(e => e.textContent); })()`); await sleep(100); (r || []).forEach((n) => out.add(n)); } return out; };
await check("indexing ends: deep tiles changed during the scan are refreshed (full refresh on indexing -> idle)", async () => {
  await gBoot(true);
  for (let k = 0; k < 6; k++) { await ev(`window.scrollTo(0, 999999), true`); await sleep(500); }
  const before = await gNames();
  assert.ok(before.has("img_251.png"), "deep tile loaded before: " + before.size);
  await post("/test/remove", { hash: "p251" }); const add = await post("/test/add", { old: true });
  const nm = "new_" + Number(add.hash.slice(1)) + ".png";
  await waitFor(`!!window.__galScanRefresh`, 9000);
  await post("/test/scan", { running: false });
  await waitFor(`window.__galIndexMode === "full"`, 9000); await sleep(1500);
  assert.equal(await ev(`window.__galIndexMode || null`), "full", "full refresh on indexing -> idle");
  const after = await gNames();
  assert.equal(after.has("img_251.png"), false, "the removed deep tile is gone");
  assert.equal(after.has(nm), true, "the new old-dated tile is shown: " + nm);
});
console.log("Media Library: end of indexing");
await check("ML: indexing ends -> shared indexRefresh 'full', removed deep card gone", async () => {
  await post("/test/reset"); await post("/test/scan", { running: true });
  await c.send("Page.navigate", { url: BASE + "/reflib/media-library/" });
  if (!await waitFor(`document.querySelectorAll('.reflib-ib-card').length > 5`, 10000)) throw new Error("no cards");
  const mHashes = async () => { const out = new Set(); for (let y = 0; y <= 40; y++) { const r = await ev(`(() => { const m = document.querySelector('.reflib-ib-main'); m.scrollTop = ${y} * m.scrollHeight / 40; return [...document.querySelectorAll('.reflib-ib-card')].map(e => e.dataset.hash || e.querySelector('[data-hash]')?.dataset.hash); })()`); await sleep(120); (r || []).forEach((n) => n && out.add(n)); } return out; };
  const before = await mHashes();
  assert.ok(before.has("p251"), "deep card seen before: " + before.size);
  await post("/test/remove", { hash: "p251" }); await post("/test/add", { old: true });
  await sleep(2500);
  await post("/test/scan", { running: false });
  await waitFor(`window.__mlIndexMode === "full"`, 9000); await sleep(1500);
  assert.equal((await mHashes()).has("p251"), false, "the removed deep card is gone");
  assert.equal(await ev(`window.__mlIndexMode || null`), "full", "ML full refresh on indexing -> idle");
});
const ex = c.logs.filter((l) => l.startsWith("EXC ")); if (ex.length) { console.log(ex.slice(0, 5)); fails.push("exceptions"); }
console.log(fails.length ? `test_browser_indexing: ${fails.length} FAILED` : "test_browser_indexing: all OK");
done(fails.length ? 1 : 0);

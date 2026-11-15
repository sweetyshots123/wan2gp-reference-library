// node tests/test_browser_favorites.mjs — 1.12.18: favourites filter in both UIs, one shared rule (filter_rules.js
// ReflibFilters + the core's `fav` filter): the Galería's ♥ Favoritas view and the Media Library Explorador's ♥ Favoritas
// toggle both send f.fav and show exactly the favourites. Real code in headless Chrome against tests/browser/server.mjs,
// synthetic items (MOCK_FAV). Skips without google-chrome / ffmpeg / dist.
import assert from "node:assert/strict";
import fs from "node:fs"; import os from "node:os"; import path from "node:path"; import { spawn, spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
const root = path.join(path.dirname(fileURLToPath(import.meta.url)), "..");
const has = (cmd) => spawnSync("sh", ["-c", "command -v " + cmd]).status === 0;
const DIST = path.join(root, "gallery/dist");
if (!has("google-chrome") || !has("ffmpeg") || !fs.existsSync(path.join(DIST, "index.html"))) { console.log("test_browser_favorites: SKIP"); process.exit(0); }
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "reflib-fav-")); const MEDIA = path.join(tmp, "media"); fs.mkdirSync(MEDIA);
spawnSync("ffmpeg", ["-v", "error", "-f", "lavfi", "-i", "testsrc=duration=2:size=160x90:rate=10", "-c:v", "libvpx", "-b:v", "100k", path.join(MEDIA, "clip.webm")]);
spawnSync("ffmpeg", ["-v", "error", "-f", "lavfi", "-i", "color=c=red:s=64x64", "-frames:v", "1", path.join(MEDIA, "img.png")]);
const VERSION = JSON.parse(fs.readFileSync(path.join(root, "plugin_info.json"), "utf8")).version;
const { freePort } = await import(path.join(root, "tests/browser/ports.mjs"));
const PORT = await freePort(); let CDP = await freePort(); while (CDP === PORT) CDP = await freePort();
const BASE = `http://127.0.0.1:${PORT}`;
const FAVS = ["p001", "p002", "p003", "v005", "p007"];
const srv = spawn(process.execPath, [path.join(root, "tests/browser/server.mjs")], { env: { ...process.env, DIST, PLUGIN: root, VERSION, PORT: String(PORT), MEDIA, QDELAY: "40", MOCK_FAV: FAVS.join(",") }, stdio: ["ignore", "pipe", "inherit"] });
process.on("exit", () => { try { srv.kill(); } catch {} });
await new Promise((r) => srv.stdout.once("data", r));
process.env.CHROME_PROFILE = path.join(tmp, "chrome");
const { launch } = await import(path.join(root, "tests/browser/cdp.mjs"));
const c = await launch(CDP); const ev = c.ev;
const done = (code) => { try { c.close(); } catch {} srv.kill(); try { fs.rmSync(tmp, { recursive: true, force: true }); } catch {} process.exit(code); };
const post = async (p, b = {}) => (await fetch(BASE + p, { method: "POST", body: JSON.stringify(b) })).json();
async function waitFor(expr, ms = 10000) { const t0 = Date.now(); while (Date.now() - t0 < ms) { try { if (await ev(expr)) return true; } catch {} await sleep(50); } return false; }
const fails = [];
async function check(name, fn) { try { await fn(); console.log("  ok  " + name); } catch (e) { fails.push(name); console.log("  FAIL " + name + ": " + (e && e.message)); } }
const lastF = async () => (await post("/test/qlog")).f.at(-1) || {};

console.log("Galería");
await check("♥ Favoritas view sends the shared fav filter and shows exactly the favourites", async () => {
  await post("/test/reset");
  await c.send("Page.navigate", { url: BASE + "/reflib/gallery/#/favoritas" }); await sleep(300);
  await ev(`localStorage.setItem('gal.sort','date_desc'); localStorage.setItem('gal.kinds','[]'); true`);
  await c.send("Page.reload", { ignoreCache: true });
  assert.ok(await waitFor(`document.querySelectorAll('figure.tile').length === ${FAVS.length}`), "tiles: " + await ev(`document.querySelectorAll('figure.tile').length`));
  const f = await lastF();
  assert.equal(f.fav, true, JSON.stringify(f)); assert.ok(!(f.tags || []).length, "no client-side tag filter: " + JSON.stringify(f));
  assert.equal(await ev(`[...document.querySelectorAll('figure.tile .hfav')].every(b => b.classList.contains('on'))`), true, "every tile shows ♥");
  assert.equal(await ev(`window.ReflibFilters && window.ReflibFilters.FAV_TAG`), "favorita");
});

console.log("Media Library");
await check("Explorador ♥ Favoritas toggle: shared fav filter, only favourites, chip, toggles off", async () => {
  await post("/test/reset");
  await c.send("Page.navigate", { url: BASE + "/reflib/media-library/" });
  assert.ok(await waitFor(`document.querySelectorAll('.reflib-ib-card').length > 20`, 15000), "cards");
  assert.ok(await waitFor(`!!document.querySelector('.reflib-ib-fav')`), "toggle present");
  assert.match(await ev(`document.querySelector('.reflib-ib-fav').textContent`), new RegExp("Favoritas\\s*" + FAVS.length));
  await ev(`document.querySelector('.reflib-ib-fav').click(), true`);
  assert.ok(await waitFor(`document.querySelectorAll('.reflib-ib-card').length === ${FAVS.length}`), "only favourites: " + await ev(`document.querySelectorAll('.reflib-ib-card').length`));
  const hs = await ev(`[...document.querySelectorAll('.reflib-ib-card')].map(e => e.dataset.hash).sort()`);
  assert.deepEqual(hs, FAVS.slice().sort());
  const f = await lastF(); assert.equal(f.fav, true, JSON.stringify(f));
  assert.equal(await ev(`document.querySelector('.reflib-ib-fav').getAttribute('aria-pressed')`), "true");
  assert.ok(await ev(`!!document.querySelector('.reflib-ib-fchips [data-kind="fav"]')`), "filter chip shown");
  await ev(`document.querySelector('.reflib-ib-fav').click(), true`);
  assert.ok(await waitFor(`document.querySelectorAll('.reflib-ib-card').length > 20`), "all again");
  assert.equal((await lastF()).fav, false);
});
const ex = c.logs.filter((l) => l.startsWith("EXC ")); if (ex.length) { console.log(ex.slice(0, 5)); fails.push("exceptions"); }
console.log(fails.length ? `test_browser_favorites: ${fails.length} FAILED` : "test_browser_favorites: all OK");
done(fails.length ? 1 : 0);

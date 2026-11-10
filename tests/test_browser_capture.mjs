// node tests/test_browser_capture.mjs — 1.12.14: REAL code in headless Chrome (built Galería dist + standalone Media
// Library composed like plugin.py build_js) against the synthetic mock backend tests/browser/server.mjs.
// Frame capture is simulated like Vidosser: pause() → the frame is inserted as newest (date_desc) → vidosser:frame-saved.
// Skips (exit 0) when google-chrome / ffmpeg / gallery/dist are missing. No real data anywhere.
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawn, spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
const root = path.join(path.dirname(fileURLToPath(import.meta.url)), "..");
const has = (cmd) => spawnSync("sh", ["-c", "command -v " + cmd]).status === 0;
const DIST = path.join(root, "gallery/dist");
if (!has("google-chrome") || !has("ffmpeg") || !fs.existsSync(path.join(DIST, "index.html"))) { console.log("test_browser_capture: SKIP (needs google-chrome, ffmpeg, gallery/dist)"); process.exit(0); }
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "reflib-btest-"));
const MEDIA = path.join(tmp, "media"); fs.mkdirSync(MEDIA);
spawnSync("ffmpeg", ["-v", "error", "-f", "lavfi", "-i", "testsrc=duration=30:size=320x180:rate=25", "-c:v", "libvpx", "-b:v", "300k", path.join(MEDIA, "clip.webm")]);
spawnSync("ffmpeg", ["-v", "error", "-f", "lavfi", "-i", "color=c=red:s=64x64", "-frames:v", "1", path.join(MEDIA, "img.png")]);
const VERSION = JSON.parse(fs.readFileSync(path.join(root, "plugin_info.json"), "utf8")).version;
const PORT = 18900 + Math.floor(Math.random() * 90), CDP = 9400 + Math.floor(Math.random() * 90), BASE = `http://127.0.0.1:${PORT}`;
const srv = spawn(process.execPath, [path.join(root, "tests/browser/server.mjs")], { env: { ...process.env, DIST, PLUGIN: root, VERSION, PORT: String(PORT), MEDIA }, stdio: ["ignore", "pipe", "inherit"] });
await new Promise((r) => srv.stdout.once("data", r));
process.env.CHROME_PROFILE = path.join(tmp, "chrome");
const { launch } = await import(path.join(root, "tests/browser/cdp.mjs"));
const c = await launch(CDP); const ev = c.ev;
const done = (code) => { try { c.close(); } catch {} srv.kill(); try { fs.rmSync(tmp, { recursive: true, force: true }); } catch {} process.exit(code); };
const post = async (p, b = {}) => (await fetch(BASE + p, { method: "POST", body: JSON.stringify(b) })).json();
async function waitFor(expr, ms = 8000) { const t0 = Date.now(); while (Date.now() - t0 < ms) { try { if (await ev(expr)) return true; } catch {} await sleep(50); } return false; }
const nameOf = (h) => h === "c010" ? "clip_10.webm" : h[0] === "v" ? `vid_${+h.slice(1)}.webm` : h[0] === "f" ? `frame_${+h.slice(1)}.png` : `img_${+h.slice(1)}.png`;
async function capture(V, n = 1, gap = 120) {
  for (let k = 0; k < n; k++) {
    await ev(`(() => { const v = ${V}; if (v) v.pause(); return true; })()`);
    const r = await post("/test/capture"); await sleep(30);
    await ev(`window.dispatchEvent(new CustomEvent('vidosser:frame-saved', { detail: { hash: ${JSON.stringify(r.hash)}, name: ${JSON.stringify(r.name)} } })); true`);
    await sleep(gap);
  }
}
const order = async () => (await post("/test/order", { f: { sort: "date_desc" } })).order;
const fails = [];
async function check(name, fn) { try { await fn(); console.log("  ok  " + name); } catch (e) { fails.push(name); console.log("  FAIL " + name + ": " + (e && e.message)); } }

// ---------------- Galería
const GV = `document.querySelector('.viewer .stage video')`;
const gState = () => ev(`(() => { const v = ${GV}; return { name: document.querySelector('.vname')?.textContent || null, count: document.querySelector('.vtop .count')?.textContent || null,
  mark: v ? (v._mark || null) : null, paused: v ? v.paused : null, fs: !!document.fullscreenElement }; })()`);
async function gOpen(idx, playing, fsOn) {
  await post("/test/reset");
  await c.send("Page.navigate", { url: BASE + "/reflib/gallery/#/" }); await sleep(300);
  await ev(`localStorage.setItem('gal.sort','date_desc'); localStorage.setItem('gal.kinds','[]'); true`);
  await c.send("Page.reload", { ignoreCache: true }); await sleep(300);
  if (!await waitFor(`document.querySelectorAll('figure.tile').length > 0`)) throw new Error("no tiles");
  await ev(`document.querySelectorAll('figure.tile')[0].click(); true`, true);
  await waitFor(`!!document.querySelector('.viewer .vname')`);
  for (let i = 0; i < idx; i++) { await ev(`document.body.dispatchEvent(new KeyboardEvent('keydown', {key:'ArrowRight', bubbles:true})); true`); await waitFor(`document.querySelector('.vtop .count')?.textContent.startsWith('${i + 2} /')`, 3000); }
  if (!await waitFor(`(() => { const v = ${GV}; return v && v.readyState >= 2; })()`)) throw new Error("video not ready");
  await ev(`(() => { const v = ${GV}; v.muted = true; v._mark = 'orig'; v.currentTime = 7; return true; })()`); await sleep(300);
  if (playing) await ev(`${GV}.play().then(() => true)`); else await ev(`(() => { ${GV}.pause(); return true; })()`);
  if (fsOn) { await ev(`(() => { [...document.querySelectorAll('.vbtns button')].find((x) => x.textContent.includes('⛶')).click(); return true; })()`, true); await waitFor(`!!document.fullscreenElement`, 3000); }
  await sleep(playing ? 400 : 2600);   // user pause older than the 2 s intent window
}
const gNext = async () => { await ev(`document.body.dispatchEvent(new KeyboardEvent('keydown', {key:'ArrowRight', bubbles:true})); true`); await sleep(900); return gState(); };
const exitFs = () => ev(`(document.fullscreenElement ? document.exitFullscreen() : Promise.resolve()).then(() => true)`);

console.log("Galería");
await check("paused video, not newest, fullscreen: stays, same <video>, stays PAUSED (BUG-1)", async () => {
  await gOpen(5, false, true); await capture(GV); await sleep(2000);
  const s = await gState(), o = await order();
  assert.equal(s.name, "vid_5.webm"); assert.equal(s.mark, "orig"); assert.equal(s.paused, true, "must not start playing"); assert.equal(s.fs, true);
  assert.equal(s.count, `${o.indexOf("v005") + 1} / ${o.length}`);
  assert.equal((await gNext()).name, nameOf(o[o.indexOf("v005") + 1]));
  await exitFs();
});
await check("playing newest, burst ×3: stays and keeps playing", async () => {
  await gOpen(0, true, false); await capture(GV, 3); await sleep(2000);
  const s = await gState();
  assert.equal(s.name, "vid_0.webm"); assert.equal(s.mark, "orig"); assert.equal(s.paused, false);
});
await check("open item removed elsewhere: pin released, no ghost, › goes to the right neighbour (BUG-4)", async () => {
  await gOpen(5, false, false); await post("/test/remove", { hash: "v005" }); await sleep(6800);
  const o = await order(), s = await gState();
  assert.notEqual(s.name, "vid_5.webm", "ghost of the removed item");
  assert.equal(s.name, nameOf(o[5]));
  assert.equal((await gNext()).name, nameOf(o[6]));
});

// ---------------- Media Library (standalone)
const LBV = `document.querySelector('.reflib-ib-lightbox video.reflib-ib-lbmedia')`, PVV = `document.querySelector('.reflib-ib-pvmedia')`;
const mState = (V) => ev(`(() => { const v = ${V}, box = document.querySelector('.reflib-ib-lightbox');
  return { idx: box ? box.dataset.idx : null, imgHash: box?.querySelector('img[data-hash]')?.dataset.hash || null, mark: v ? (v._mark || null) : null,
    paused: v ? v.paused : null, fs: !!document.fullscreenElement, pvHash: v?.dataset?.hash || null }; })()`);
async function mBoot() {
  await post("/test/reset");
  await c.send("Page.navigate", { url: BASE + "/reflib/media-library/" });
  if (!await waitFor(`document.querySelectorAll('.reflib-ib-card').length > 5`, 10000)) throw new Error("no cards");
}
async function mPrep(V, playing, fsOn, fsExpr) {
  if (!await waitFor(`(() => { const v = ${V}; return !!v && v.readyState >= 2; })()`)) throw new Error("video not ready");
  await ev(`(() => { const v = ${V}; v.muted = true; v._mark = 'orig'; v.currentTime = 7; return true; })()`); await sleep(300);
  if (playing) await ev(`${V}.play().then(() => true)`); else await ev(`(() => { ${V}.pause(); return true; })()`);
  if (fsOn) { await ev(fsExpr, true); await waitFor(`!!document.fullscreenElement`, 3000); }
  await sleep(playing ? 400 : 2600);
}
console.log("Media Library");
await check("details panel, playing, native fullscreen on its <video>, burst ×3: SAME <video>, still fullscreen (BUG-2)", async () => {
  await mBoot();
  await ev(`(() => { referenceLibrary.ilibShowPreview("c010"); return true; })()`);
  await mPrep(PVV, true, true, `${PVV}.requestFullscreen().then(() => true)`);
  await capture(PVV, 3); await sleep(2500);
  const s = await mState(PVV);
  assert.equal(s.pvHash, "c010"); assert.equal(s.mark, "orig", "preview <video> was replaced"); assert.equal(s.fs, true, "fullscreen lost"); assert.equal(s.paused, false);
  await exitFs();
});
await check("details panel, paused: same <video>, stays paused", async () => {
  await mBoot();
  await ev(`(() => { referenceLibrary.ilibShowPreview("v005"); return true; })()`);
  await mPrep(PVV, false, false);
  await capture(PVV); await sleep(2500);
  const s = await mState(PVV);
  assert.equal(s.mark, "orig"); assert.equal(s.paused, true);
});
await check("lightbox on an item outside the loaded grid pages (idx 125): › / ‹ after capture hit the right rows (BUG-3)", async () => {
  await mBoot();
  await ev(`(() => { document.querySelector('.reflib-ib-card[data-idx="20"]').dispatchEvent(new MouseEvent('dblclick', { bubbles: true })); return true; })()`);
  for (let i = 20; i < 125; i++) { await ev(`(() => { document.querySelector('.reflib-ib-lightbox [data-lb="next"]').click(); return true; })()`); await waitFor(`document.querySelector('.reflib-ib-lightbox').dataset.idx === '${i + 1}'`, 3000); }
  await mPrep(LBV, false, false);
  await capture(LBV); await sleep(2500);
  const o = await order(), s = await mState(LBV), at = o.indexOf("v125");
  assert.equal(s.imgHash, "v125"); assert.equal(s.mark, "orig"); assert.equal(+s.idx, at);
  await ev(`(() => { document.querySelector('.reflib-ib-lightbox [data-lb="next"]').click(); return true; })()`); await sleep(1200);
  assert.equal((await mState(LBV)).imgHash, o[at + 1], "› skipped one");
  await ev(`(() => { document.querySelector('.reflib-ib-lightbox [data-lb="prev"]').click(); return true; })()`); await sleep(1200);
  assert.equal((await mState(LBV)).imgHash, "v125", "‹ must return to the video");
  await ev(`(() => { document.querySelector('.reflib-ib-lightbox [data-lb="prev"]').click(); return true; })()`); await sleep(1200);
  assert.equal((await mState(LBV)).imgHash, o[at - 1]);
});
await check("lightbox newest, playing, fullscreen: same <video>, ‹› neighbours", async () => {
  await mBoot();
  await ev(`(() => { document.querySelector('.reflib-ib-card[data-idx="0"]').dispatchEvent(new MouseEvent('dblclick', { bubbles: true })); return true; })()`);
  await mPrep(LBV, true, true, `(() => { document.querySelector('.reflib-ib-lightbox [data-lb="fs"]').click(); return true; })()`);
  await capture(LBV); await sleep(2500);
  const s = await mState(LBV), o = await order();
  assert.equal(s.imgHash, "v000"); assert.equal(s.mark, "orig"); assert.equal(s.fs, true); assert.equal(s.paused, false); assert.equal(+s.idx, o.indexOf("v000"));
  await exitFs();
});
const ex = c.logs.filter((l) => l.startsWith("EXC"));
if (ex.length) { console.log("page exceptions:", ex.slice(0, 5)); fails.push("page exceptions"); }
console.log(fails.length ? "test_browser_capture: FAIL " + fails.join("; ") : "test_browser_capture: ok");
done(fails.length ? 1 : 0);

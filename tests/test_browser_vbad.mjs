// node tests/test_browser_vbad.mjs — 1.12.15: the "Este navegador no puede reproducir este vídeo" notice must match
// the video that is actually loaded. REAL built Galería in headless Chrome against tests/browser/server.mjs.
// Synthetic only: ffmpeg testsrc as VP8 webm (plays) and as mp4v / MPEG-4 Part 2 (Chrome can't decode).
// Skips (exit 0) when google-chrome / ffmpeg / gallery/dist are missing.
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawn, spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
const root = path.join(path.dirname(fileURLToPath(import.meta.url)), "..");
const has = (cmd) => spawnSync("sh", ["-c", "command -v " + cmd]).status === 0;
const DIST = path.join(root, "gallery/dist");
if (!has("google-chrome") || !has("ffmpeg") || !fs.existsSync(path.join(DIST, "index.html"))) { console.log("test_browser_vbad: SKIP"); process.exit(0); }
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "reflib-vbad-"));
const MEDIA = path.join(tmp, "media"); fs.mkdirSync(MEDIA);
spawnSync("ffmpeg", ["-v", "error", "-f", "lavfi", "-i", "testsrc=duration=30:size=320x180:rate=25", "-c:v", "libvpx", "-b:v", "300k", path.join(MEDIA, "clip.webm")]);
spawnSync("ffmpeg", ["-v", "error", "-f", "lavfi", "-i", "testsrc=duration=10:size=320x180:rate=25", "-c:v", "mpeg4", "-tag:v", "mp4v", path.join(MEDIA, "bad.mp4")]);
spawnSync("ffmpeg", ["-v", "error", "-f", "lavfi", "-i", "color=c=red:s=64x64", "-frames:v", "1", path.join(MEDIA, "img.png")]);
const VERSION = JSON.parse(fs.readFileSync(path.join(root, "plugin_info.json"), "utf8")).version;
const PORT = 18900 + Math.floor(Math.random() * 90), CDP = 9500 + Math.floor(Math.random() * 90), BASE = `http://127.0.0.1:${PORT}`;
// video-only order (date_desc): v000 v005 c010 v015 v020 v025 …  → v005 and v020 are undecodable
const srv = spawn(process.execPath, [path.join(root, "tests/browser/server.mjs")], { env: { ...process.env, DIST, PLUGIN: root, VERSION, PORT: String(PORT), MEDIA, BAD_HASHES: "v005,v020" }, stdio: ["ignore", "pipe", "inherit"] });
await new Promise((r) => srv.stdout.once("data", r));
process.env.CHROME_PROFILE = path.join(tmp, "chrome");
const { launch } = await import(path.join(root, "tests/browser/cdp.mjs"));
const c = await launch(CDP); const ev = c.ev;
const done = (code) => { try { c.close(); } catch {} srv.kill(); try { fs.rmSync(tmp, { recursive: true, force: true }); } catch {} process.exit(code); };
const post = async (p, b = {}) => (await fetch(BASE + p, { method: "POST", body: JSON.stringify(b) })).json();
async function waitFor(expr, ms = 8000) { const t0 = Date.now(); while (Date.now() - t0 < ms) { try { if (await ev(expr)) return true; } catch {} await sleep(50); } return false; }
const GV = `document.querySelector('.viewer .stage video')`;
const st = () => ev(`(() => { const v = ${GV}; return { name: document.querySelector('.vname')?.textContent || null, notice: !!document.querySelector('.viewer .vbad'),
  ready: v ? v.readyState : null, err: v && v.error ? v.error.code : null, t: v ? v.currentTime : null, w: v ? v.videoWidth : null }; })()`);
async function open(idx) {
  await post("/test/reset");
  await c.send("Page.navigate", { url: BASE + "/reflib/gallery/#/" }); await sleep(300);
  await ev(`localStorage.setItem('gal.sort','date_desc'); localStorage.setItem('gal.kinds','["video"]'); true`);
  await c.send("Page.reload", { ignoreCache: true }); await sleep(300);
  if (!await waitFor(`document.querySelectorAll('figure.tile').length > 0`)) throw new Error("no tiles");
  await ev(`document.querySelectorAll('figure.tile')[${idx}].click(); true`, true);
  await waitFor(`!!document.querySelector('.viewer .vname')`);
  await sleep(1500);
}
const key = async (k, wait = 1800) => { await ev(`document.body.dispatchEvent(new KeyboardEvent('keydown', {key:'${k}', bubbles:true})); true`); await sleep(wait); return st(); };
const playsWell = (s) => s.ready >= 2 && s.err == null && s.w > 0;
const fails = [];
async function check(name, fn) { try { await fn(); console.log("  ok  " + name); } catch (e) { fails.push(name); console.log("  FAIL " + name + ": " + (e && e.message)); } }

await check("playable video opened directly: no notice", async () => {
  await open(0); const s = await st();
  assert.equal(s.name, "vid_0.webm"); assert.ok(playsWell(s), JSON.stringify(s)); assert.equal(s.notice, false);
});
await check("mp4v video: notice shown", async () => {
  await open(1); const s = await st();
  assert.equal(s.name, "vid_5.webm"); assert.equal(s.notice, true, JSON.stringify(s));
});
await check("mp4v → › playable: notice cleared while the next video plays (Ramón's case)", async () => {
  await open(1); assert.equal((await st()).notice, true);
  const s = await key("ArrowRight");
  assert.ok(s.name.startsWith("clip_10.webm")); assert.ok(playsWell(s), "plays: " + JSON.stringify(s));
  assert.equal(s.notice, false, "stale notice over a playing video: " + JSON.stringify(s));
  await sleep(1200); assert.equal((await st()).notice, false, "still no notice after playing a while");
});
await check("mp4v → ‹ playable: notice cleared", async () => {
  await open(1); const s = await key("ArrowLeft");
  assert.equal(s.name, "vid_0.webm"); assert.ok(playsWell(s)); assert.equal(s.notice, false, JSON.stringify(s));
});
await check("playable → › mp4v: notice shown; › again playable: cleared", async () => {
  await open(3); assert.equal((await st()).notice, false);
  const s1 = await key("ArrowRight"); assert.equal(s1.name, "vid_20.webm"); assert.equal(s1.notice, true, JSON.stringify(s1));
  const s2 = await key("ArrowRight"); assert.equal(s2.name, "vid_25.webm"); assert.ok(playsWell(s2)); assert.equal(s2.notice, false, JSON.stringify(s2));
});
await check("fast stepping through mp4v (no settle): no notice left on the playable one", async () => {
  await open(0); await key("ArrowRight", 30); const s = await key("ArrowRight", 1800);
  assert.ok(s.name.startsWith("clip_10.webm")); assert.ok(playsWell(s)); assert.equal(s.notice, false, JSON.stringify(s));
});
const ex = c.logs.filter((l) => l.startsWith("EXC")); if (ex.length) { console.log(ex.slice(0, 5)); fails.push("exceptions"); }
console.log(fails.length ? `test_browser_vbad: ${fails.length} FAILED` : "test_browser_vbad: all OK");
done(fails.length ? 1 : 0);

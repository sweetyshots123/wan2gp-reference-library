// node tests/test_browser_viewer_prio.mjs — 1.12.18: in the Galería viewer the open item's original (media_url + the
// full image) goes before the neighbour preview preloads (ReflibNet.itemPrio + MediumCache.hold). Built Galería in
// headless Chrome against tests/browser/server.mjs with a slow synthetic "preview" (PREVIEW_DELAY). DIST=<dir> to
// measure another build; REPORT=1 only prints the timings. Skips without google-chrome / ffmpeg / dist.
import assert from "node:assert/strict";
import fs from "node:fs"; import os from "node:os"; import path from "node:path"; import { spawn, spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
const root = path.join(path.dirname(fileURLToPath(import.meta.url)), "..");
const has = (cmd) => spawnSync("sh", ["-c", "command -v " + cmd]).status === 0;
const DIST = process.env.DIST || path.join(root, "gallery/dist");
if (!has("google-chrome") || !has("ffmpeg") || !fs.existsSync(path.join(DIST, "index.html"))) { console.log("test_browser_viewer_prio: SKIP"); process.exit(0); }
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "reflib-vprio-")); const MEDIA = path.join(tmp, "media"); fs.mkdirSync(MEDIA);
spawnSync("ffmpeg", ["-v", "error", "-f", "lavfi", "-i", "testsrc=duration=2:size=160x90:rate=10", "-c:v", "libvpx", "-b:v", "100k", path.join(MEDIA, "clip.webm")]);
spawnSync("ffmpeg", ["-v", "error", "-f", "lavfi", "-i", "color=c=red:s=64x64", "-frames:v", "1", path.join(MEDIA, "img.png")]);
spawnSync("ffmpeg", ["-v", "error", "-f", "lavfi", "-i", "testsrc=size=1600x1000:rate=1", "-frames:v", "1", path.join(MEDIA, "full.png")]);
const VERSION = JSON.parse(fs.readFileSync(path.join(root, "plugin_info.json"), "utf8")).version;
const { freePort } = await import(path.join(root, "tests/browser/ports.mjs"));
const PORT = await freePort(); let CDP = await freePort(); while (CDP === PORT) CDP = await freePort();
const BASE = `http://127.0.0.1:${PORT}`;
const PD = +(process.env.PD || 250);
const srv = spawn(process.execPath, [path.join(root, "tests/browser/server.mjs")], { env: { ...process.env, DIST, PLUGIN: root, VERSION, PORT: String(PORT), MEDIA, QDELAY: "20", PREVIEW_DELAY: String(PD), FULL: "full.png" }, stdio: ["ignore", "pipe", "inherit"] });
process.on("exit", () => { try { srv.kill(); } catch {} });
await new Promise((r) => srv.stdout.once("data", r));
process.env.CHROME_PROFILE = path.join(tmp, "chrome");
const { launch } = await import(path.join(root, "tests/browser/cdp.mjs"));
const c = await launch(CDP); const ev = c.ev;
const done = (code) => { try { c.close(); } catch {} srv.kill(); try { fs.rmSync(tmp, { recursive: true, force: true }); } catch {} process.exit(code); };
async function waitFor(expr, ms = 10000) { const t0 = Date.now(); while (Date.now() - t0 < ms) { try { if (await ev(expr)) return true; } catch {} await sleep(50); } return false; }
const tl = async (clear) => (await (await fetch(BASE + "/test/tl" + (clear ? "?clear=1" : ""), { method: "POST", body: "{}" })).json()).tl;

await c.send("Page.navigate", { url: BASE + "/reflib/gallery/#/" }); await sleep(300);
await ev(`localStorage.setItem('gal.sort','date_desc'); localStorage.setItem('gal.kinds','["image"]'); true`);
await c.send("Page.reload", { ignoreCache: true });
if (!await waitFor(`document.querySelectorAll('figure.tile').length > 12`, 15000)) { console.log("no tiles"); done(1); }
await sleep(400);
const runs = [];
for (let r = 0; r < 3; r++) {
  await tl(true);
  await ev(`document.querySelectorAll('figure.tile')[${3 + r * 3}].click(); true`, true);
  // wait (polling, robust under load) until the open item's original was requested and the preloads ran
  let ev2 = [];
  for (const t1 = Date.now(); Date.now() - t1 < 20000;) {
    await sleep(200); ev2 = ev2.concat(await tl(true));
    const f = ev2.find((e) => e[1].startsWith("preview:")); if (!f) continue;
    const hh = f[1].slice(8);
    if (ev2.some((e) => e[1] === "get:full:" + hh) && ev2.filter((e) => e[1].startsWith("preview:")).length >= 8) break;
  }
  const first = ev2.find((e) => e[1].startsWith("preview:")); if (!first) { console.log("no preview", ev2); done(1); }
  const h = first[1].slice(8), base = first[0];
  const mu = ev2.find((e) => e[1] === "media_url:" + h), full = ev2.find((e) => e[1] === "get:full:" + h);
  const nbBefore = ev2.filter((e) => e[1].startsWith("preview:") && e[1] !== "preview:" + h && mu && e[0] < mu[0]).length;
  runs.push({ h, media_url_ms: mu ? mu[0] - base : null, full_ms: full ? full[0] - base : null, neighbour_previews_before: nbBefore });
  // fresh page per run (empty preview cache, nothing in flight)
  await c.send("Page.navigate", { url: BASE + "/reflib/gallery/#/" });
  await c.send("Page.reload", { ignoreCache: true });
  if (!await waitFor(`document.querySelectorAll('figure.tile').length > 12 && !document.querySelector('.viewer')`, 15000)) { console.log("no tiles"); done(1); }
  await sleep(400);
}
console.log("viewer priority (ms from the open item's first preview request; PREVIEW_DELAY " + PD + "):");
for (const x of runs) console.log("  ", JSON.stringify(x));
if (process.env.REPORT) done(0);
let bad = 0;
for (const x of runs) {
  try {
    assert.ok(x.media_url_ms != null && x.full_ms != null, "original requested");
    assert.ok(x.neighbour_previews_before <= 1, "at most the one neighbour preview already running: " + x.neighbour_previews_before);
  } catch (e) { bad++; console.log("  FAIL " + e.message); }
}
console.log(bad ? "test_browser_viewer_prio: FAILED" : "test_browser_viewer_prio: all OK");
done(bad ? 1 : 0);

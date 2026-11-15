// node tests/test_browser_tagcomplete.mjs — 1.12.17: tag autocomplete in the Galería "Etiquetas" field and the Media
// Library tag field (shared tag_complete.js): inline completion (case / accent-insensitive), Tab / Enter accept,
// Backspace never re-completes, suggestions ranked prefix → word start → contains, ↓ + Enter picks a suggestion.
// Real code in headless Chrome against tests/browser/server.mjs with synthetic tags. Skips without chrome / ffmpeg / dist.
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawn, spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
const root = path.join(path.dirname(fileURLToPath(import.meta.url)), "..");
const has = (cmd) => spawnSync("sh", ["-c", "command -v " + cmd]).status === 0;
const DIST = path.join(root, "gallery/dist");
if (!has("google-chrome") || !has("ffmpeg") || !fs.existsSync(path.join(DIST, "index.html"))) { console.log("test_browser_tagcomplete: SKIP"); process.exit(0); }
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "reflib-tc-"));
const MEDIA = path.join(tmp, "media"); fs.mkdirSync(MEDIA);
spawnSync("ffmpeg", ["-v", "error", "-f", "lavfi", "-i", "testsrc=duration=2:size=160x90:rate=10", "-c:v", "libvpx", "-b:v", "100k", path.join(MEDIA, "clip.webm")]);
spawnSync("ffmpeg", ["-v", "error", "-f", "lavfi", "-i", "color=c=red:s=64x64", "-frames:v", "1", path.join(MEDIA, "img.png")]);
const VERSION = JSON.parse(fs.readFileSync(path.join(root, "plugin_info.json"), "utf8")).version;
const { freePort } = await import(path.join(root, "tests/browser/ports.mjs"));
const PORT = await freePort(); let CDP = await freePort(); while (CDP === PORT) CDP = await freePort();
const BASE = `http://127.0.0.1:${PORT}`;
const TAGS = "fake company+,planta,animal,Antonio,big andamio,Ánimo feliz";
const srv = spawn(process.execPath, [path.join(root, "tests/browser/server.mjs")], { env: { ...process.env, DIST, PLUGIN: root, VERSION, PORT: String(PORT), MEDIA, QDELAY: "40", MOCK_TAGS: TAGS }, stdio: ["ignore", "pipe", "inherit"] });
await new Promise((r) => srv.stdout.once("data", r));
process.env.CHROME_PROFILE = path.join(tmp, "chrome");
const { launch } = await import(path.join(root, "tests/browser/cdp.mjs"));
const c = await launch(CDP); const ev = c.ev;
const done = (code) => { try { c.close(); } catch {} srv.kill(); try { fs.rmSync(tmp, { recursive: true, force: true }); } catch {} process.exit(code); };
const post = async (p, b = {}) => (await fetch(BASE + p, { method: "POST", body: JSON.stringify(b) })).json();
async function waitFor(expr, ms = 8000) { const t0 = Date.now(); while (Date.now() - t0 < ms) { try { if (await ev(expr)) return true; } catch {} await sleep(50); } return false; }
const fails = [];
async function check(name, fn) { try { await fn(); console.log("  ok  " + name); } catch (e) { fails.push(name); console.log("  FAIL " + name + ": " + (e && e.message)); } }

const type = async (s) => { for (const ch of s) { await c.send("Input.insertText", { text: ch }); await sleep(40); } };
const KEYS = { Backspace: [8, ""], Tab: [9, ""], Enter: [13, "\r"], ArrowDown: [40, ""], Escape: [27, ""] };
const key = async (k) => { const [vk, text] = KEYS[k];
  await c.send("Input.dispatchKeyEvent", { type: text ? "keyDown" : "rawKeyDown", key: k, code: k, windowsVirtualKeyCode: vk, nativeVirtualKeyCode: vk, text: text || undefined });
  await c.send("Input.dispatchKeyEvent", { type: "keyUp", key: k, code: k, windowsVirtualKeyCode: vk, nativeVirtualKeyCode: vk }); await sleep(60); };

async function scenario(SEL, KEY) {
  const st = () => ev(`(() => { const i = document.querySelector(${JSON.stringify(SEL)}); const l = document.querySelector('.reflib-tc-list[data-key="${KEY}"]');
    return { v: i.value, s: i.selectionStart, e: i.selectionEnd, list: l && l.style.display !== "none" ? [...l.children].map(d => d.textContent) : [] }; })()`);
  const focus = async () => { await ev(`(() => { const i = document.querySelector(${JSON.stringify(SEL)}); i.value = ""; i.focus(); return true; })()`); await sleep(50); };
  const adds = async () => (await post("/test/tags")).adds;
  await check("'an': inline 'animal' (completed part selected); list prefix → word start → contains", async () => {
    await focus(); await type("an");
    const s = await st();
    assert.deepEqual([s.v, s.s, s.e], ["animal", 2, 6], JSON.stringify(s));
    assert.deepEqual(s.list, ["animal", "Antonio", "Ánimo feliz", "big andamio", "fake company+", "planta"]);
  });
  await check("typing on continues; case-insensitive ('ant' → 'Antonio')", async () => {
    await type("t"); const s = await st();
    assert.deepEqual([s.v, s.s, s.e], ["Antonio", 3, 7], JSON.stringify(s));
  });
  await check("Backspace removes the completion and does not re-complete", async () => {
    await key("Backspace"); let s = await st();
    assert.deepEqual([s.v, s.s, s.e], ["Ant", 3, 3], JSON.stringify(s));
    await key("Backspace"); s = await st();
    assert.deepEqual([s.v, s.s, s.e], ["An", 2, 2], JSON.stringify(s));
  });
  await check("Tab accepts the completion, Enter adds it", async () => {
    await type("i"); let s = await st();
    assert.deepEqual([s.v, s.s, s.e], ["animal", 3, 6], JSON.stringify(s));
    await key("Tab"); s = await st();
    assert.deepEqual([s.v, s.s, s.e], ["animal", 6, 6], "Tab: caret at the end, focus stays: " + JSON.stringify(s));
    assert.equal(await ev(`document.activeElement === document.querySelector(${JSON.stringify(SEL)})`), true);
    const n0 = (await adds()).length; await key("Enter");
    assert.ok(await waitFor(`fetch("/test/tags", {method:"POST"}).then(r => r.json()).then(j => j.adds.length > ${n0})`, 4000), "tag sent");
    assert.deepEqual((await adds()).at(-1), ["animal"]);
  });
  await check("accent-insensitive: 'ANIMO' → 'Ánimo feliz'; Enter accepts + adds it", async () => {
    await focus(); await type("ANIMO"); const s = await st();
    assert.equal(s.v, "Ánimo feliz"); assert.equal(s.e, s.v.length); assert.ok(s.s < s.e);
    const n0 = (await adds()).length; await key("Enter");
    await waitFor(`fetch("/test/tags", {method:"POST"}).then(r => r.json()).then(j => j.adds.length > ${n0})`, 4000);
    assert.deepEqual((await adds()).at(-1), ["Ánimo feliz"]);
  });
  await check("↓ + Enter picks a suggestion (no add yet); next Enter adds", async () => {
    await focus(); await type("an");
    for (let k = 0; k < 4; k++) await key("ArrowDown");
    const n0 = (await adds()).length;
    await key("Enter"); await sleep(300);
    const s = await st();
    assert.equal(s.v, "big andamio"); assert.equal((await adds()).length, n0, "picking does not submit");
    await key("Enter");
    await waitFor(`fetch("/test/tags", {method:"POST"}).then(r => r.json()).then(j => j.adds.length > ${n0})`, 4000);
    assert.deepEqual((await adds()).at(-1), ["big andamio"]);
  });
  await check("second tag after a comma completes its own segment", async () => {
    await focus(); await type("planta, an"); const s = await st();
    assert.deepEqual([s.v, s.s, s.e], ["planta, animal", 10, 14], JSON.stringify(s));
  });
}

console.log("Galería");
await post("/test/reset");
await c.send("Page.navigate", { url: BASE + "/reflib/gallery/#/" }); await sleep(300);
await ev(`localStorage.setItem('gal.sort','date_desc'); localStorage.setItem('gal.kinds','[]'); true`);
await c.send("Page.reload", { ignoreCache: true });
if (!await waitFor(`document.querySelectorAll('figure.tile .cb').length > 5`, 15000)) { console.log("no tiles"); done(1); }
await ev(`document.querySelector('figure.tile .cb').click(), true`);
await waitFor(`!!document.querySelector('.selbar')`);
await ev(`[...document.querySelectorAll('.selbar button')].find(b => /Editar selección/.test(b.textContent)).click(), true`);
if (!await waitFor(`!!document.querySelector('.bulk input.tagin')`)) fails.push("galeria: no tag field");
else await scenario(".bulk input.tagin", "gal-tag");

console.log("Media Library");
await post("/test/reset");
await c.send("Page.navigate", { url: BASE + "/reflib/media-library/" });
if (!await waitFor(`document.querySelectorAll('.reflib-ib-card').length > 5`, 15000)) { console.log("no cards"); done(1); }
await ev(`document.querySelector('.reflib-ib-card .reflib-ib-cb input').click(), true`);
if (!await waitFor(`!!document.querySelector('.reflib-ib-tagin')`)) fails.push("ml: no tag field");
else await scenario(".reflib-ib-tagin", "ml-tag");

const ex = c.logs.filter((l) => l.startsWith("EXC ")); if (ex.length) { console.log(ex.slice(0, 5)); fails.push("exceptions"); }
console.log(fails.length ? `test_browser_tagcomplete: ${fails.length} FAILED` : "test_browser_tagcomplete: all OK");
done(fails.length ? 1 : 0);

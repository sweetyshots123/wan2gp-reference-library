// node tests/test_browser_playable.mjs — 1.12.19: an mp4v fixture is transcoded by
// reflib_core.playable (real Python module, libx264) and plays in headless Chrome.
// Synthetic only: ffmpeg testsrc as MPEG-4 Part 2 (800x600, 29.97, yuv420p).
// Skips (exit 0) when google-chrome / ffmpeg / python3 are missing.
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawn, spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { createHash } from "node:crypto";

const root = path.join(path.dirname(fileURLToPath(import.meta.url)), "..");
const has = (cmd) => spawnSync("sh", ["-c", "command -v " + cmd]).status === 0;
const py = ["/workspace/rl-1218-venv/bin/python", "python3"].find((c) => {
  try { return spawnSync(c, ["-c", "import sys"]).status === 0; } catch { return false; }
});
if (!has("google-chrome") || !has("ffmpeg") || !py) { console.log("test_browser_playable: SKIP"); process.exit(0); }

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "reflib-playable-"));
const MEDIA = path.join(tmp, "media");
const DATA = path.join(tmp, "data");
fs.mkdirSync(MEDIA);
fs.mkdirSync(DATA);
const SRC = path.join(MEDIA, "bad.mp4");
// Ramón's case: MPEG-4 Part 2 (mp4v), 800x600, 29.97 fps, yuv420p; a few seconds so transcode + seek stay quick.
const ff = spawnSync("ffmpeg", [
  "-v", "error", "-f", "lavfi",
  "-i", "testsrc=duration=4:size=800x600:rate=30000/1001",
  "-pix_fmt", "yuv420p", "-c:v", "mpeg4", "-tag:v", "mp4v",
  SRC,
], { encoding: "utf8" });
if (ff.status !== 0 || !fs.existsSync(SRC)) {
  console.log("test_browser_playable: SKIP (ffmpeg could not write the mp4v fixture)");
  process.exit(0);
}
const srcHash = createHash("sha256").update(fs.readFileSync(SRC)).digest("hex");
const srcStat = fs.statSync(SRC);

const { freePort } = await import(path.join(root, "tests/browser/ports.mjs"));
const PORT = await freePort(); let CDP = await freePort(); while (CDP === PORT) CDP = await freePort();
const BASE = `http://127.0.0.1:${PORT}`;
const env = {
  ...process.env,
  MEDIA,
  REFLIB_DATA_DIR: DATA,
  REFLIB_PLAY_ENCODER: "libx264",
  PLAY_HASH: "mp4vfixture",
  PORT: String(PORT),
  PYTHONPATH: root,
};
const srv = spawn(py, [path.join(root, "tests/browser/play_server.py")], { env, stdio: ["ignore", "pipe", "inherit"] });
process.on("exit", () => { try { srv.kill(); } catch {} });
await new Promise((r, j) => {
  const t = setTimeout(() => j(new Error("play_server did not start")), 15000);
  srv.stdout.once("data", (b) => { clearTimeout(t); r(b); });
  srv.on("exit", (c) => { clearTimeout(t); j(new Error("play_server exited " + c)); });
});

process.env.CHROME_PROFILE = path.join(tmp, "chrome");
const { launch } = await import(path.join(root, "tests/browser/cdp.mjs"));
const c = await launch(CDP);
const ev = c.ev;
const done = (code) => { try { c.close(); } catch {} try { srv.kill(); } catch {} try { fs.rmSync(tmp, { recursive: true, force: true }); } catch {} process.exit(code); };
const waitFor = async (expr, ms = 20000) => {
  const t0 = Date.now();
  while (Date.now() - t0 < ms) {
    try { if (await ev(expr)) return true; } catch {}
    await sleep(80);
  }
  return false;
};
const st = () => ev(`window.__play || null`);

const fails = [];
async function check(name, fn) {
  try { await fn(); console.log("  ok  " + name); }
  catch (e) { fails.push(name); console.log("  FAIL " + name + ": " + (e && e.message)); }
}

await check("mp4v fixture is transcoded and plays in the browser", async () => {
  await c.send("Page.navigate", { url: BASE + "/" });
  if (!await waitFor(`!!document.querySelector('video')`, 5000)) throw new Error("no video");
  // First we may see "preparing"; then the playable H.264 copy must actually play.
  if (!await waitFor(`(() => { const p = window.__play; return p && p.width > 0 && p.ready >= 2 && !p.err && !p.notice; })()`, 25000)) {
    throw new Error("did not play: " + JSON.stringify(await st()));
  }
  const s = await st();
  assert.ok(s.play === "ready" || s.play === "preparing" || s.play === "original", "play=" + s.play);
  assert.equal(s.notice, false, "unsupported notice shown over a playing video: " + JSON.stringify(s));
  assert.ok(!s.preparing, "preparing banner still up while playing: " + JSON.stringify(s));
});

await check("seeking works on the playable copy", async () => {
  const ok = await ev(`(() => { const v = document.getElementById('v'); try { v.currentTime = 2; return true; } catch (e) { return false; } })()`);
  assert.ok(ok, "currentTime rejected");
  if (!await waitFor(`(() => { const v = document.getElementById('v'); return v && Math.abs(v.currentTime - 2) < 0.75; })()`, 8000)) {
    const s = await st();
    throw new Error("seek did not land: " + JSON.stringify(s));
  }
});

await check("original fixture is untouched and the cache is under the plugin data dir", async () => {
  const after = fs.statSync(SRC);
  assert.equal(after.size, srcStat.size);
  assert.equal(after.mtimeMs, srcStat.mtimeMs);
  const h = createHash("sha256").update(fs.readFileSync(SRC)).digest("hex");
  assert.equal(h, srcHash, "original bytes changed");
  const beside = fs.readdirSync(MEDIA);
  assert.deepEqual(beside, ["bad.mp4"], "cache or sidecar written next to the fixture: " + beside.join(","));
  const cache = path.join(DATA, "cache", "play");
  assert.ok(fs.existsSync(cache), "plugin cache dir missing: " + cache);
  const files = fs.readdirSync(cache).filter((f) => f.endsWith(".mp4") && !f.includes(".part"));
  assert.ok(files.length >= 1, "no finished cache mp4 in " + cache + ": " + fs.readdirSync(cache).join(","));
});

const ex = c.logs.filter((l) => l.startsWith("EXC "));
if (ex.length) { console.log(ex.slice(0, 5)); fails.push("exceptions"); }
console.log(fails.length ? `test_browser_playable: ${fails.length} FAILED` : "test_browser_playable: all OK");
done(fails.length ? 1 : 0);

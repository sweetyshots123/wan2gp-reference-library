// node tests/test_browser_standalone_theme.mjs — standalone Media Library (/reflib/media-library/)
// must have readable text on its dark shell (1.12.26). Synthetic mock only; no real data.
// Skips (exit 0) without google-chrome / ffmpeg.
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawn, spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
const root = path.join(path.dirname(fileURLToPath(import.meta.url)), "..");
const has = (cmd) => spawnSync("sh", ["-c", "command -v " + cmd]).status === 0;
if (!has("google-chrome") || !has("ffmpeg")) { console.log("test_browser_standalone_theme: SKIP (needs google-chrome, ffmpeg)"); process.exit(0); }
const DIST = path.join(root, "gallery/dist");
const VERSION = JSON.parse(fs.readFileSync(path.join(root, "plugin_info.json"), "utf8")).version;
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "reflib-theme-"));
const MEDIA = path.join(tmp, "media"); fs.mkdirSync(MEDIA);
spawnSync("ffmpeg", ["-v", "error", "-f", "lavfi", "-i", "testsrc=size=160x120:rate=1", "-frames:v", "1", path.join(MEDIA, "img.png")]);
spawnSync("ffmpeg", ["-v", "error", "-f", "lavfi", "-i", "testsrc=duration=2:size=160x90:rate=10", "-c:v", "libvpx", path.join(MEDIA, "clip.webm")]);
const PORT = 18900 + Math.floor(Math.random() * 80), CDP = 9400 + Math.floor(Math.random() * 80), BASE = `http://127.0.0.1:${PORT}`;
const srv = spawn(process.execPath, [path.join(root, "tests/browser/server.mjs")], {
  env: { ...process.env, DIST, PLUGIN: root, VERSION, PORT: String(PORT), MEDIA, MOCK_CHIPS: "16", MOCK_COLS: "6", QDELAY: "20" },
  stdio: ["ignore", "pipe", "inherit"],
});
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
await new Promise((r) => srv.stdout.once("data", r));
process.env.CHROME_PROFILE = path.join(tmp, "chrome");
const { launch } = await import(path.join(root, "tests/browser/cdp.mjs"));
const c = await launch(CDP);
const ev = c.ev;
const done = (code) => { try { c.close(); } catch {} try { srv.kill(); } catch {} try { fs.rmSync(tmp, { recursive: true, force: true }); } catch {} process.exit(code); };
try {
  await c.send("Emulation.setDeviceMetricsOverride", { width: 1024, height: 480, deviceScaleFactor: 1, mobile: false });
  await c.send("Page.navigate", { url: BASE + "/reflib/media-library/" });
  const t0 = Date.now();
  let ok = false;
  while (Date.now() - t0 < 12000) {
    try { if (await ev(`!!(document.querySelector('.reflib-ib-modal') && document.querySelectorAll('.reflib-ib-card').length > 0)`)) { ok = true; break; } } catch {}
    await sleep(80);
  }
  assert.ok(ok, "standalone ML did not render");
  const report = await ev(`(() => {
    const rgb = (cs) => {
      const m = String(cs).match(/rgba?\\((\\d+),\\s*(\\d+),\\s*(\\d+)(?:,\\s*([0-9.]+))?\\)/);
      if (!m) return null;
      return { r:+m[1], g:+m[2], b:+m[3], a: m[4] === undefined ? 1 : +m[4] };
    };
    const lum = ({r,g,b}) => {
      const f = (v) => { v/=255; return v<=0.04045 ? v/12.92 : Math.pow((v+0.055)/1.055, 2.4); };
      return 0.2126*f(r)+0.7152*f(g)+0.0722*f(b);
    };
    const contrast = (fg, bg) => {
      if (!fg || !bg) return 0;
      const hi = Math.max(lum(fg), lum(bg)), lo = Math.min(lum(fg), lum(bg));
      return (hi+0.05)/(lo+0.05);
    };
    const solidBg = (el) => {
      for (let n = el; n; n = n.parentElement) {
        const bg = rgb(getComputedStyle(n).backgroundColor);
        if (bg && bg.a > 0) return bg;
      }
      return rgb(getComputedStyle(document.body).backgroundColor);
    };
    const info = (sel) => {
      const el = document.querySelector(sel);
      if (!el) return { sel, missing: true, contrast: 0 };
      const fg = rgb(getComputedStyle(el).color), bg = solidBg(el);
      return { sel, contrast: Math.round(contrast(fg, bg)*100)/100, color: getComputedStyle(el).color, bg: bg && 'rgb('+bg.r+', '+bg.g+', '+bg.b+')' };
    };
    return {
      htmlClass: document.documentElement.className,
      bodyClass: document.body.className,
      bodyText: getComputedStyle(document.documentElement).getPropertyValue('--body-text-color').trim(),
      text: [
        info('.reflib-ib-head h3'),
        info('input.reflib-ib-q, .reflib-ib-modal input[type=search], .reflib-ib-modal input[type=text]'),
        info('.reflib-ib-flabel'),
        info('.reflib-ib-chip:not(.on)'),
        info('.reflib-ib-tree'),
        info('.reflib-ib-name'),
        info('.reflib-ib-foot .reflib-ib-btn, .reflib-ib-modal .reflib-ib-btn'),
      ],
      selected: info('.reflib-ib-view button.on'),
    };
  })()`);
  assert.match(report.htmlClass, /\breflib-standalone\b/);
  assert.match(report.htmlClass, /\bdark\b/);
  assert.match(report.bodyClass, /\bdark\b/);
  assert.ok(report.bodyText, "dark --body-text-color must be set on standalone");
  for (const s of report.text) {
    assert.ok(!s.missing, "missing " + s.sel);
    assert.ok(s.contrast >= 4.5, `${s.sel} contrast ${s.contrast} < 4.5 (${s.color} on ${s.bg})`);
  }
  // Selected Todo/Detalles (or the icon view button) is explicit white on accent blue;
  // the shared .dark rule uses #3b82f6 (~3.7:1), which is WCAG AA for large/UI text.
  assert.ok(!report.selected.missing, "missing selected view button");
  assert.ok(report.selected.contrast >= 3, `selected view button contrast ${report.selected.contrast}`);
  console.log("standalone theme contrast ok", JSON.stringify({ bodyText: report.bodyText, text: report.text, selected: report.selected }));
  console.log("test_browser_standalone_theme: ok");
  done(0);
} catch (e) {
  console.error("test_browser_standalone_theme FAIL:", e && e.message);
  done(1);
}

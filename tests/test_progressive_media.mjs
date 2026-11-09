import { readFileSync } from "fs";
import vm from "vm";
import assert from "assert";
import { fileURLToPath } from "url";
import { dirname, join } from "path";

const __dirname = dirname(fileURLToPath(import.meta.url));
vm.runInNewContext(readFileSync(join(__dirname, "..", "progressive_media.js"), "utf8"), globalThis);
assert.strictEqual(ReflibProgressive.pick({ thumb: "t", medium: "m" }), "m");
assert.strictEqual(ReflibProgressive.pick({ thumb: "t", medium: "m", full: "f" }), "f");
assert.strictEqual(ReflibProgressive.pick({ thumb: "t" }), "t");
console.log("progressive_media ok");

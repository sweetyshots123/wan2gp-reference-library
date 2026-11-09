import { readFileSync } from "fs";
import vm from "vm";
import assert from "assert";
import { fileURLToPath } from "url";
import { dirname, join } from "path";

const __dirname = dirname(fileURLToPath(import.meta.url));
const src = readFileSync(join(__dirname, "..", "person_match.js"), "utf8");
const g = { console, setTimeout, clearTimeout };
vm.runInNewContext(src + "\nthis.ReflibPersonMatch = ReflibPersonMatch;", g);
const PM = g.ReflibPersonMatch;
assert.ok(PM);
assert.ok(PM.version >= 2);
const j = (x) => JSON.parse(JSON.stringify(x));

const names = ["María José", "Mario", "Ana", "maria jose"];
const mar = j(PM.match("mar", names, 10));
assert.ok(mar.includes(names[0]) && mar.includes("Mario") && !mar.includes("Ana"));
assert.deepStrictEqual(j(PM.match("jos", names, 5)), [names[0]]);
assert.strictEqual(PM.resolve("MARIA JOSE", names), names[0]);
assert.strictEqual(PM.resolve("Nuevo", names), "Nuevo");
assert.strictEqual(PM.fold("Café"), "cafe");

const down = PM.keyStep("ArrowDown", { hits: ["A", "B"], hi: 0, open: true, v: "a" });
assert.strictEqual(down.hi, 1);
const enter = PM.keyStep("Enter", { hits: ["A", "B"], hi: 1, open: true, v: "a" });
assert.strictEqual(enter.commit, "B");
const esc = PM.keyStep("Escape", { hits: ["A"], hi: 0, open: true, v: "a" });
assert.strictEqual(esc.close, true);
assert.strictEqual(typeof PM.attach, "function");

console.log("person_match ok");

// node tests/test_tag_complete.mjs — 1.12.17 shared tag autocomplete rules (tag_complete.js). Synthetic tags only.
import assert from "node:assert/strict";
import path from "node:path";
import { fileURLToPath } from "node:url";
const root = path.join(path.dirname(fileURLToPath(import.meta.url)), "..");
await import(path.join(root, "tag_complete.js"));
const T = globalThis.ReflibTagComplete;
assert.equal(T.version, 1);
const TAGS = ["fake company+", "planta", "animal", "Antonio", "big andamio", "Ánimo feliz", "x_anexo", "zz+an"];
// ranking: prefix → word start (space, -, _, +…) → contains; stable inside each group
assert.deepEqual(T.rank("an", TAGS), ["animal", "Antonio", "Ánimo feliz", "big andamio", "x_anexo", "zz+an", "fake company+", "planta"]);
assert.deepEqual(T.rank("AN", TAGS, 3), ["animal", "Antonio", "Ánimo feliz"]);
assert.deepEqual(T.rank("ánimo", TAGS), ["Ánimo feliz"]);
assert.deepEqual(T.rank("  ", TAGS), []);
assert.deepEqual(T.rank("an", TAGS, 0, ["ANIMAL"]).slice(0, 2), ["Antonio", "Ánimo feliz"], "already typed tags excluded");
assert.deepEqual(T.rank("a", ["Anna", "anna"]), ["Anna"], "duplicates (case) once");
// completion: first prefix match in the given order, case- and accent-insensitive, longer than typed
assert.equal(T.completion("an", TAGS), "animal");
assert.equal(T.completion("ANT", TAGS), "Antonio");
assert.equal(T.completion("animo", TAGS), "Ánimo feliz");
assert.equal(T.completion("animal", TAGS), null, "exact: nothing to complete");
assert.equal(T.completion("qq", TAGS), null);
// decomposed accents (NFD) keep the right prefix length
const nfd = "A\u0301nimo";
assert.equal(T.prefixLen(nfd, "an"), 3);
assert.equal(T.prefixLen("Ánimo", "an"), 2);
// segment
assert.deepEqual(T.segment("foo, ba", 7), { start: 5, end: 7, text: "ba" });
assert.deepEqual(T.segment("foo;bar", 2), { start: 0, end: 3, text: "fo" });
// inline: only insertions at the end; deletions never re-complete
assert.deepEqual(T.inline("an", 2, "insertText", TAGS), { value: "animal", selStart: 2, selEnd: 6, tag: "animal" });
assert.deepEqual(T.inline("foo, Ant", 8, "insertText", TAGS), { value: "foo, Antonio", selStart: 8, selEnd: 12, tag: "Antonio" });
assert.equal(T.inline("an", 2, "deleteContentBackward", TAGS), null);
assert.equal(T.inline("an", 2, "deleteContentForward", TAGS), null);
assert.equal(T.inline("an", 1, "insertText", TAGS), null, "caret not at the end");
assert.equal(T.inline("an", 2, "insertFromPaste", TAGS), null);
assert.equal(T.inline("animal, an", 10, "insertText", ["animal", "andar"]).tag, "andar", "a tag already in the field is skipped");
assert.equal(T.inline("x, ", 3, "insertText", TAGS), null);
// accept: replace the caret's segment
assert.deepEqual(T.accept("planta, an", 10, "animal"), { value: "planta, animal", caret: 14 });
assert.deepEqual(T.accept("an, planta", 2, "Antonio"), { value: "Antonio, planta", caret: 7 });
console.log("test_tag_complete: ok");

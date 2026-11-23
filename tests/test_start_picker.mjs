// Exercise the shipped functions in a VM: no browser/Gradio pixels simulated.
import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
const src = fs.readFileSync(new URL('../reference_library.js', import.meta.url), 'utf8');
// Isolate adjacent declarations from the real source, never a second implementation.
const section = src.slice(src.indexOf('    const PKT = {'), src.indexOf('    // ================================================================ 1.6.6 virtual copies'));
let requests = [], closes = 0, queries = 0, toasts = [], language = 'es';
const ilib = {f: {kind: 'all', tags: new Set(['old']), q: 'prior'}, sel: new Set(['stale']), anchorIdx: 4,
    open: true, q: {items: [{hash: 'i', kind: 'image', name: 'synthetic.png'}, {hash: 'v', kind: 'video'}]}};
const c = vm.createContext({ Set, Map, JSON, String, Object, Promise, console, ilib,
    lang: () => language, setInterval: () => {}, SV_AUDIO: /audio/,
    svField: () => ({field: 'video_guide', tab: 'generate'}), pkLabel: () => 'Control Video',
    newQuery: () => queries++, renderKindBar: () => {}, render: () => {}, openBrowser: () => {},
    sendBridge: async req => { requests.push(req); return {ok: true, restored: [req.to]}; },
    toast: (...args) => toasts.push(args), closeBrowser: () => closes++,
    GRID_SVG: '', esc: s => s, bridgeButton: () => true,
});
vm.runInContext(section + '\nglobalThis.api = {startPickField,imagePickField,pickOpen,pickLoad,pickEnd,pkt,mountStartPickButtons,mountGuidePickButtons};', c);
const api = c.api;
assert.equal(api.startPickField({className: 'reflib-start-add reflib-start-generate'}).field, 'image_start');
assert.equal(api.startPickField({className: 'reflib-si-video_guide-generate'}), null);
api.pickOpen({className: 'reflib-start-add reflib-start-edit'});
assert.equal(ilib.pick.kind, 'image'); assert.equal(ilib.pick.tab, 'edit');
assert.equal(ilib.f.kind, 'image'); assert.equal(ilib.sel.size, 0); assert.equal(ilib.f.tags.size, 0);
assert.equal(api.pkt('start_btn'), 'Elegir de la librería');
await api.pickLoad('v'); assert.equal(requests.length, 0); // wrong kind never goes to bridge
await api.pickLoad('i'); assert.equal(requests.length, 1);
assert.deepEqual(JSON.parse(JSON.stringify(requests[0])), {hash: 'i', to: 'image_start', target: 'edit:image_start'});
assert.equal(closes, 1);
api.pickEnd(); assert.equal(ilib.pick, null); assert.equal(ilib.f.q, 'prior'); assert(ilib.f.tags.has('old'));
language = 'en'; assert.equal(api.pkt('start_btn'), 'Choose from library');
// Existing video picker remains on history bridge.
api.pickOpen({className: '', querySelector: () => ({textContent: 'Control Video'})}); await api.pickLoad('v');
assert.equal(requests[1].target, 'generate:history'); assert.equal(requests[1].to, 'video_guide');
api.pickEnd();
// Mount is idempotent, creates a sibling in AMG controls, and updates live language.
let children = [], click;
const host = {querySelector: () => children[0], appendChild: b => children.push(b)};
const upload = {className: 'reflib-start-add reflib-start-generate', closest: () => host};
c.document = {querySelectorAll: () => [upload], createElement: () => ({
    addEventListener: (name, f) => { if (name === 'click') click = f; }, setAttribute: () => {}
})};
api.mountStartPickButtons(); api.mountStartPickButtons();
assert.equal(children.length, 1); assert.equal(children[0].type, 'button');
assert.equal(children[0].textContent, 'Choose from library');
language = 'es'; api.mountStartPickButtons(); assert.equal(children[0].textContent, 'Elegir de la librería');
let stopped = 0; click({preventDefault: () => stopped++, stopPropagation: () => stopped++}); assert.equal(stopped, 2);
assert.equal(ilib.pick.field, 'image_start');
api.pickEnd();

// Control Image (image_guide): same "Elegir de la librería" label, history bridge, replaces the current image.
assert.equal(api.imagePickField({className: 'block reflib-ipick reflib-ipick-image_guide-generate'}).field, 'image_guide');
assert.equal(api.imagePickField({className: 'reflib-start-add reflib-start-generate'}), null);
const guide = {className: 'block reflib-ipick reflib-ipick-image_guide-edit', querySelector: () => ({textContent: 'Control Image'})};
api.pickOpen(guide);
assert.equal(ilib.pick.kind, 'image');
assert.equal(ilib.pick.field, 'image_guide');
assert.equal(ilib.pick.tab, 'edit');
assert.equal(ilib.pick.label, 'Control Image');
await api.pickLoad('v'); // wrong kind
assert.equal(requests.length, 2); // start + video earlier, this one rejected
await api.pickLoad('i');
assert.equal(requests[2].to, 'image_guide');
assert.equal(requests[2].target, 'edit:history');
assert.equal(closes, 3);
language = 'es';
assert.equal(api.pkt('start_btn'), 'Elegir de la librería');
assert.match(api.pkt('tip_g', {label: 'Imagen de control'}), /Imagen de control/);
language = 'en';
assert.match(api.pkt('tip_g', {label: 'Control Image'}), /Control Image/);

let gchildren = [];
const glabel = { parentNode: null, after(b) { gchildren.push(b); } };
const gblock = {
    className: 'block reflib-ipick reflib-ipick-image_guide-generate',
    querySelector: (sel) => String(sel).includes('ipick-btn') ? gchildren[0] : (String(sel).includes('label') ? glabel : {textContent: 'Control Image'}),
    contains: (n) => gchildren.includes(n),
    insertBefore(b) { gchildren.push(b); },
    appendChild(b) { gchildren.push(b); },
};
glabel.parentNode = gblock;
const prevDoc = c.document;
c.document = { querySelectorAll: (sel) => String(sel).includes('reflib-ipick') ? [gblock] : [],
    createElement: () => ({ addEventListener() {}, setAttribute() {} }) };
api.mountGuidePickButtons(); api.mountGuidePickButtons();
assert.equal(gchildren.length, 1);
assert.equal(gchildren[0].textContent, 'Choose from library');
assert.equal(gchildren[0].type, 'button');
c.document = prevDoc;

console.log('start picker: routing, filtering, cancel/restore, EN/ES, mount idempotence and video regression OK');
console.log('control image picker: field, history bridge, EN/ES, mount idempotence OK');

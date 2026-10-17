// Tests for the pure logic block (<script id="ag-logic">) of web/index.html.
// Run: node --test tests/web/
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const html = readFileSync(new URL('../../web/index.html', import.meta.url), 'utf8');
const code = /<script id="ag-logic">([\s\S]*?)<\/script>/.exec(html)[1];
vm.runInThisContext(code);   // same realm, so deepEqual compares plain objects
const AG = globalThis.AG;

const SHA_A = 'a'.repeat(64), SHA_B = 'b'.repeat(64);
const check = (status, detail = '', values = { x: 1 }) => ({ status, detail, values });

function blenderReport(model = 'Shovel', pack = 'Kit', overrides = {}) {
  const checks = {};
  for (const id of AG.MODEL_IDS.filter(i => AG.SOURCE[i] === 'blender')) checks[id] = check('pass');
  Object.assign(checks, overrides);
  return { schema: 1, tool: 'blender', toolVersion: '0.1.0', scope: 'model', pack, model,
    checkedAt: '2026-10-14T00:00:00Z', source: { fbxPath: 'x.fbx', fbxSha256: SHA_A },
    stats: { tris: 1606, tex: 2048, mats: 1, objs: 1 }, checks };
}
function unityReport(model = 'Shovel', pack = 'Kit', sha = SHA_A, overrides = {}) {
  const checks = {};
  for (const id of AG.MODEL_IDS.filter(i => AG.SOURCE[i] === 'unity')) checks[id] = check('pass');
  Object.assign(checks, overrides);
  return { schema: 1, tool: 'unity', toolVersion: '0.1.0', scope: 'model', pack, model,
    checkedAt: '2026-10-14T00:00:00Z', source: { fbxPath: 'Assets/x.fbx', fbxSha256: sha }, checks };
}
function model(name = 'Shovel', pack = 'Kit') {
  const m = AG.blankModel('m1'); m.name = name; m.pack = pack; return m;
}
const files = (...reports) => reports.map(r => ({ pack: r.pack,
  name: r.scope === 'pack' ? '_pack.unity.json' : `${r.model}.${r.tool}.json`, data: r }));

const confirmsFile = (tool, model, confirms, pack = 'Kit') => ({ pack,
  name: model ? `${model}.${tool}.confirms.json` : '_pack.unity.confirms.json',
  data: model ? { schema: 1, tool, scope: 'model', pack, model, confirms } : { schema: 1, tool: 'unity', scope: 'pack', pack, confirms } });

test('catalog: 40 model + 25 pack ids — v2 ids unchanged, m1-16 added at the end of Gate 1 (SPEC D22)', () => {
  assert.equal(AG.MODEL_IDS.length, 40);
  assert.equal(AG.MODEL_IDS[AG.MODEL_IDS.indexOf('m1-15') + 1], 'm1-16');
  assert.equal(AG.SOURCE['m1-16'], 'blender');
  assert.equal(AG.PACK_IDS.length, 25);
  assert.deepEqual(AG.MODEL_IDS.slice(0, 3), ['m1-1', 'm1-2', 'm1-3']);
  assert.equal(AG.PACK_IDS.at(-1), 'k3-10');
});

test('catalog: manual items match SPEC §5', () => {
  const manual = [...AG.MODEL_IDS, ...AG.PACK_IDS].filter(AG.isManual);
  // M7 (SPEC D19): m1-13, m3-4, m4-* moved into Blender / Unity; only pack items are ticked here
  assert.deepEqual(manual, ['k1-5', 'k1-7', 'k1-10', 'k3-3', 'k3-4', 'k3-5', 'k3-8', 'k3-9', 'k3-10']);
});

test('migration: v2 state keeps every field and gains confirms/overrides', () => {
  const v2 = { v: 2, view: 'pack', currentId: 'mA', currentPack: 'Kit', lastExport: 5,
    models: { mA: { id: 'mA', name: 'Arrow', pack: 'Kit', mat: 'Texture (Meshy)', date: '2026-09-01', note: 'n',
      stats: { tris: '1200', tex: '1024', mats: '1', objs: '3' }, lic: { plan: 'Pro', genDate: '2026-08-01', manual: 'uv' },
      checks: { 'm1-1': true, 'm4-1': true, 'zz-9': true }, updated: 123 } },
    packs: { Kit: { checks: { 'k3-9': true }, budget: '2000', unityVer: '6000', note: 'p' } } };
  const s = AG.normalize(v2);
  assert.equal(s.v, 3);
  assert.equal(s.view, 'pack');
  const m = s.models.mA;
  assert.equal(m.name, 'Arrow');
  assert.deepEqual(m.stats, { tris: '1200', tex: '1024', mats: '1', objs: '3' });
  assert.deepEqual(m.lic, { plan: 'Pro', genDate: '2026-08-01', manual: 'uv' });
  assert.deepEqual(m.checks, { 'm1-1': true, 'm4-1': true }, 'unknown ids dropped');
  assert.deepEqual(m.confirms, {});
  assert.deepEqual(m.overrides, {});
  assert.deepEqual(s.packs.Kit.checks, { 'k3-9': true });
  assert.equal(s.packs.Kit.budget, '2000');
});

test('migration: rejects prototype keys and pack ids on models', () => {
  const s = AG.normalize(JSON.parse('{"models":{"__proto__":{"name":"x"},"m":{"checks":{"k1-1":true},"overrides":{"m1-6":"  "}}}}'));
  assert.deepEqual(Object.keys(s.models), ['m']);
  assert.deepEqual(s.models.m.checks, {});
  assert.deepEqual(s.models.m.overrides, {}, 'blank reasons are not overrides');
});

test('reports: indexed by pack + model, bad files listed as errors', () => {
  const idx = AG.indexReports([...files(blenderReport(), unityReport()),
    { pack: 'Kit', name: 'Broken.blender.json', data: null },
    { pack: 'Kit', name: 'Other.blender.json', data: { schema: 2 } }]);
  assert.ok(idx.blender['Kit\u0000Shovel']);
  assert.ok(idx.unity['Kit\u0000Shovel']);
  assert.equal(idx.errors.length, 2);
});

test('status: no reports -> every model item pending (all come from Blender / Unity)', () => {
  const s = AG.modelSummary(model(), AG.indexReports([]));
  for (const id of ['m1-1', 'm1-13', 'm2-5', 'm3-4', 'm4-4']) assert.equal(s.items[id].status, 'pending', id);
  assert.equal(s.gate1, false);
});

test('status: review counts only after confirm; fail only after override with reason', () => {
  const m = model();
  const idx = AG.indexReports(files(blenderReport('Shovel', 'Kit', {
    'm1-2': check('review', '694 faces'), 'm1-6': check('fail', '5 ngons'), 'm1-11': check('na', '', {}) })));
  let s = AG.modelSummary(m, idx);
  assert.equal(s.items['m1-2'].passed, false);
  assert.equal(s.items['m1-6'].passed, false);
  assert.equal(s.items['m1-11'].passed, true, 'na counts as passed');
  assert.equal(s.items['m1-6'].detail, '5 ngons');
  m.confirms['m1-2'] = true;
  m.overrides['m1-6'] = 'intentional';
  m.checks['m1-13'] = true;
  s = AG.modelSummary(m, idx);
  assert.equal(s.items['m1-2'].passed, true);
  assert.equal(s.items['m1-6'].passed, true);
  assert.equal(s.items['m1-6'].override, 'intentional');
  assert.equal(s.gate1, true);
  // confirming a check that passes on its own changes nothing
  m.confirms['m1-1'] = true;
  assert.equal(AG.modelSummary(m, idx).items['m1-1'].passed, true);
});

test('gates: gate 2 needs gate 1 and every unity item, review items confirmed in the tools', () => {
  const m = model();
  const at = '2026-10-16T00:00:00Z';
  const idx = AG.indexReports([...files(
    blenderReport('Shovel', 'Kit', { 'm1-13': check('review', 'look', { textures: ['A'] }) }),
    unityReport('Shovel', 'Kit', SHA_A, { 'm3-4': check('review', 'look', { fbxSha256: SHA_A }) }))]);
  let s = AG.modelSummary(m, idx);
  assert.equal(s.gate1, false, 'm1-13 waits for a confirmation in Blender');
  const confirmed = AG.indexReports([...files(
    blenderReport('Shovel', 'Kit', { 'm1-13': check('review', 'look', { textures: ['A'] }) }),
    unityReport('Shovel', 'Kit', SHA_A, { 'm3-4': check('review', 'look', { fbxSha256: SHA_A }) })),
    confirmsFile('blender', 'Shovel', { 'm1-13': { values: { textures: ['A'] }, confirmedAt: at } }),
    confirmsFile('unity', 'Shovel', { 'm3-4': { values: { fbxSha256: SHA_A }, confirmedAt: at } })]);
  s = AG.modelSummary(m, confirmed);
  assert.equal(s.gate1, true);
  assert.equal(s.gate2, true);
  assert.equal(s.done, s.total);
});

test('stale: unity results stop counting when the FBX hash differs', () => {
  const m = model();
  const s = AG.modelSummary(m, AG.indexReports(files(blenderReport(), unityReport('Shovel', 'Kit', SHA_B))));
  assert.equal(s.stale, true);
  assert.equal(s.items['m2-5'].status, 'stale');
  assert.equal(s.items['m2-5'].passed, false);
  assert.equal(s.items['m1-1'].passed, true, 'blender results are not affected');
  assert.equal(s.gate2, false);
});

test('orphans: reports for models not in the list are offered once', () => {
  const state = AG.blankState();
  state.models.m1 = model('Shovel', 'Kit');
  const idx = AG.indexReports(files(blenderReport('Shovel'), blenderReport('Axe'), unityReport('Axe', 'Kit')));
  assert.deepEqual(JSON.parse(JSON.stringify(AG.orphanReports(state, idx))), [{ pack: 'Kit', model: 'Axe' }]);
});

test('matching ignores surrounding spaces in names', () => {
  const m = model(' Shovel ', 'Kit ');
  assert.ok(AG.reportsFor(m, AG.indexReports(files(blenderReport()))).blender);
});

test('syncStats copies Blender stats into the model numbers', () => {
  const m = model();
  assert.equal(AG.syncStats(m, blenderReport()), true);
  assert.deepEqual(m.stats, { tris: '1606', tex: '2048', mats: '1', objs: '1' });
  assert.equal(AG.syncStats(m, blenderReport()), false, 'no change the second time');
});

test('pack: k3-1 / k3-2 from model results, unity pack items pending without a pack report', () => {
  const pack = AG.blankPack();
  const a = model('Shovel'), b = model('Axe'); b.id = 'm2';
  for (const m of [a, b]) { for (const id of ['m1-13', 'm3-4', 'm4-1', 'm4-2', 'm4-3']) m.checks[id] = true; m.lic.manual = 'x'; }
  const idx = AG.indexReports(files(blenderReport('Shovel'), unityReport('Shovel'), blenderReport('Axe'), unityReport('Axe', 'Kit', SHA_B)));
  const sums = { m1: AG.modelSummary(a, idx), m2: AG.modelSummary(b, idx) };
  const p = AG.packSummary(pack, [a, b], sums, null);
  assert.equal(p.items['k3-1'].status, 'fail');
  assert.match(p.items['k3-1'].detail, /Axe/);
  assert.equal(p.items['k3-2'].status, 'fail', 'Axe is stale');
  assert.equal(p.items['k1-2'].status, 'pending');
  assert.equal(p.items['k2-1'].status, 'pending', 'marketing images come in M4');
  assert.equal(p.items['k3-9'].status, 'manual');

  const packReport = { schema: 1, tool: 'unity', toolVersion: '0.1.0', scope: 'pack', pack: 'Kit', checkedAt: 'x',
    checks: { 'k1-2': check('pass', '', { longest: 90 }) } };
  assert.equal(AG.packSummary(pack, [a], { m1: sums.m1 }, packReport).items['k1-2'].status, 'pass');
  assert.equal(AG.packSummary(pack, [a], { m1: sums.m1 }, null).items['k3-1'].status, 'pass');
});

// ---------------- M4: marketing images and store-page drafts ----------------
const CFG = JSON.parse(readFileSync(new URL('../../config/default.config.json', import.meta.url), 'utf8'));
const png = (width, height, alpha = false) => ({ width, height, format: 'PNG', alpha });
const goodImages = () => ({
  'icon.png': png(160, 160), 'card.png': png(420, 280), 'cover.png': png(1950, 1300), 'social.png': png(1200, 630),
  ...Object.fromEntries([1, 2, 3, 4, 5].map(i => [`screenshot_0${i}.png`, png(2400, 1600)])),
});
const status = (id, images, cfg = CFG) => AG.marketingStatus(id, AG.blankPack(), images, cfg);

test('marketing: all key art at the right size passes', () => {
  for (const id of ['k2-1', 'k2-2', 'k2-3', 'k2-4', 'k2-5']) assert.equal(status(id, goodImages()).status, 'pass', id);
  assert.equal(status('k2-5', goodImages()).values.count, 5);
});

test('marketing: wrong size, missing file, optional social', () => {
  const imgs = goodImages();
  imgs['icon.png'] = png(128, 128);
  delete imgs['card.png'];
  delete imgs['social.png'];
  assert.equal(status('k2-1', imgs).status, 'fail');
  assert.match(status('k2-1', imgs).detail, /128×128/);
  assert.equal(status('k2-2', imgs).status, 'fail');
  assert.equal(status('k2-4', imgs).status, 'na', 'social is optional');
});

test('marketing: file names are matched case-insensitively', () => {
  const imgs = goodImages();
  imgs['ICON.PNG'] = imgs['icon.png']; delete imgs['icon.png'];
  assert.equal(status('k2-1', imgs).status, 'pass');
});

test('marketing: screenshots need count 5–10, 3:2, PNG without alpha', () => {
  const few = goodImages(); delete few['screenshot_05.png'];
  assert.match(status('k2-5', few).detail, /4 ภาพ/);
  const bad = goodImages();
  bad['screenshot_02.png'] = png(1920, 1080);
  bad['screenshot_03.png'] = png(2400, 1600, true);
  bad['screenshot_04.png'] = { width: 2400, height: 1600, format: 'JPG', alpha: false };
  const r = status('k2-5', bad);
  assert.equal(r.status, 'fail');
  assert.match(r.detail, /1920×1080 ไม่ใช่ 3:2/);
  assert.match(r.detail, /มี alpha/);
  assert.match(r.detail, /ไม่ใช่ PNG/);
});

test('marketing: pending without folder or config', () => {
  assert.equal(status('k2-1', null).status, 'pending');
  assert.equal(status('k2-1', goodImages(), null).status, 'pending');
});

test('pack summary uses marketing images; k1-8 asks for review once models exist', () => {
  const pack = AG.blankPack();
  const a = model('Shovel');
  const idx = AG.indexReports(files(blenderReport('Shovel'), unityReport('Shovel')));
  const sums = { m1: AG.modelSummary(a, idx) };
  const p = AG.packSummary(pack, [a], sums, null, { images: goodImages(), cfg: CFG });
  assert.equal(p.items['k2-3'].status, 'pass');
  assert.equal(p.items['k1-8'].status, 'review');
  assert.equal(AG.packSummary(pack, [], {}, null, { images: goodImages(), cfg: CFG }).items['k1-8'].status, 'pending');
});

test('drafts: technical details from real numbers, AI disclosure from manual notes', () => {
  const pack = AG.blankPack(); pack.unityVer = '6000.3.22f1';
  const a = model('Shovel'), b = model('Axe'); b.id = 'm2';
  a.stats = { tris: '1606', tex: '2048', mats: '1', objs: '1' };
  b.stats = { tris: '900', tex: '2048', mats: '1', objs: '2' };
  a.lic.manual = 'Cleaned mesh, fixed UVs';
  const ur = unityReport('Shovel');
  ur.checks['m2-6'] = check('pass', '', { slots: ['_BaseMap=Shovel_base_color', '_BumpMap=Shovel_normal'] });
  const idx = AG.indexReports(files(blenderReport('Shovel'), ur, blenderReport('Axe')));
  const sums = { m1: AG.modelSummary(a, idx), m2: AG.modelSummary(b, idx) };
  const tech = AG.technicalDraft('Kit', pack, [a, b], sums);
  assert.match(tech, /Models: 2 \(Shovel, Axe\)/);
  assert.match(tech, /900–1,606 triangles per model, 2,506 in total/);
  assert.match(tech, /2048×2048 PNG/);
  assert.match(tech, /Base Color, Normal/);
  assert.match(tech, /tested with Unity 6000\.3\.22f1/);
  assert.doesNotMatch(tech, /[฀-๿]/, 'technical draft is English');
  const ai = AG.aiDraft([a, b]);
  assert.match(ai, /Shovel: Cleaned mesh, fixed UVs/);
  assert.match(ai, /Axe: \(describe the manual work\)/);
  assert.equal(AG.technicalDraft('Kit', pack, [], {}), '');
});

// ---------------- confirmations made in Blender / Unity (SPEC D11) ----------------

test('tool confirmations: count while values match, ignored once the result changed', () => {
  const review = check('review', 'two materials', { materials: 2, textures: { A: ['a.png'] } });
  const at = '2026-10-16T00:00:00Z';
  const same = AG.indexReports([...files(blenderReport('Shovel', 'Kit', { 'm1-9': review })),
    confirmsFile('blender', 'Shovel', { 'm1-9': { values: { textures: { A: ['a.png'] }, materials: 2 }, confirmedAt: at } })]);
  assert.deepEqual(same.errors, []);
  const s = AG.modelSummary(model(), same).items['m1-9'];
  assert.equal(s.confirmed, true);
  assert.equal(s.confirmedBy, 'blender');
  assert.equal(s.passed, true);

  const changed = AG.indexReports([...files(blenderReport('Shovel', 'Kit', { 'm1-9': review })),
    confirmsFile('blender', 'Shovel', { 'm1-9': { values: { materials: 3, textures: { A: ['a.png'] } }, confirmedAt: at } })]);
  const c = AG.modelSummary(model(), changed).items['m1-9'];
  assert.equal(c.confirmed, false);
  assert.equal(c.passed, false);

  // a Unity confirmation does not confirm a Blender check, and a confirmed pass stays a plain pass
  const cross = AG.indexReports([...files(blenderReport('Shovel', 'Kit', { 'm1-9': review }), unityReport()),
    confirmsFile('unity', 'Shovel', { 'm3-5': { values: { x: 1 }, confirmedAt: at } })]);
  const x = AG.modelSummary(model(), cross).items;
  assert.equal(x['m1-9'].confirmed, false);
  assert.equal(x['m3-5'].confirmedBy, '', 'm3-5 passed, nothing to confirm');
});

test('tool confirmations: pack level from _pack.unity.confirms.json; bad files are errors', () => {
  const at = '2026-10-16T00:00:00Z';
  const packReport = { schema: 1, tool: 'unity', toolVersion: '0.1.0', scope: 'pack', pack: 'Kit', checkedAt: at,
    checks: { 'k1-6': check('review', 'no notices', { files: [] }) } };
  const idx = AG.indexReports([...files(packReport), confirmsFile('unity', null, { 'k1-6': { values: { files: [] }, confirmedAt: at } }),
    { pack: 'Kit', name: 'Shovel.blender.confirms.json', data: { schema: 1 } }]);
  assert.deepEqual(idx.errors, ['Kit/Shovel.blender.confirms.json']);
  const p = AG.packSummary(AG.blankPack(), [], {}, idx.packUnity.Kit, null, idx.confirms.packUnity.Kit);
  assert.equal(p.items['k1-6'].confirmedBy, 'unity');
  assert.equal(p.items['k1-6'].passed, true);
  assert.equal(AG.packSummary(AG.blankPack(), [], {}, idx.packUnity.Kit, null, null).items['k1-6'].passed, false);
});

// ---------------- M7: the page lists what Blender / Unity checked ----------------
test('packs and models come from the reports; old state.json data still applies', () => {
  const idx = AG.indexReports(files(blenderReport('Shovel', 'Kit'), unityReport('Axe', 'Kit'), blenderReport('Box', 'Other')));
  const state = AG.blankState();
  const old = AG.blankModel('m9'); old.name = 'Shovel'; old.pack = 'Kit'; old.lic.manual = 'typed before M7';
  state.models.m9 = old;
  state.packs.Gone = AG.blankPack();
  assert.deepEqual(AG.reportPackNames(state, idx), ['Kit', 'Other']);
  const withStore = AG.indexReports([...files(unityReport()), { pack: 'Kit', name: 'Shovel.unity.store.json', data: { schema: 1, tool: 'unity' } }]);
  assert.deepEqual(withStore.errors, [], 'Unity store notes are not reports');
  const ms = AG.packModels(state, idx, 'Kit');
  assert.deepEqual(ms.map(m => m.name), ['Axe', 'Shovel']);
  assert.equal(ms[1], old, 'the saved model is reused');
  assert.equal(ms[1].stats.tris, '1606', 'stats copied from the Blender report');
});

test('AI draft uses the notes typed in Unity (m4-4), else what was typed in the page', () => {
  const m = model();
  m.lic.manual = 'old page note';
  const plain = AG.indexReports(files(unityReport()));
  assert.equal(AG.manualNotes(m, { m1: AG.modelSummary(m, plain) }), 'old page note');
  const typed = AG.indexReports(files(unityReport('Shovel', 'Kit', SHA_A, { 'm4-4': check('pass', '', { manual: 'Retopology in Blender' }) })));
  const sums = { m1: AG.modelSummary(m, typed) };
  assert.equal(AG.manualNotes(m, sums), 'Retopology in Blender');
  assert.match(AG.aiDraft([m], sums), /Retopology in Blender/);
  assert.doesNotMatch(AG.aiDraft([m], sums), /DALL-E|Meshy/, 'no tool names of our own in the public draft');
  assert.match(AG.aiDraft([m], sums), /name the AI tools you used/);
  const withTool = AG.indexReports(files(unityReport('Shovel', 'Kit', SHA_A, {
    'm4-1': check('review', '', { plan: 'Meshy Pro' }), 'm4-4': check('pass', '', { manual: 'x' }) })));
  assert.match(AG.aiDraft([m], { m1: AG.modelSummary(m, withTool) }), /\(Meshy Pro\)/, 'tools come from Unity m4-1');
});

// ---------------- M8: page language ----------------
test('language: texts made by the page follow EN/TH; catalog has English for every pack item', () => {
  const pack = AG.blankPack();
  try {
    AG.setLang('en');
    assert.equal(AG.getLang(), 'en');
    assert.match(AG.marketingStatus('k2-1', pack, null, CFG).detail, /No marketing\/<pack>\/ folder/);
    assert.equal(AG.SOURCE_NAME.page, 'this page');
    for (const phase of AG.PACK_PHASES) {
      assert.ok(phase.en && phase.en.title, 'phase ' + phase.id + ' has an English title');
      for (const g of phase.groups) for (const it of g.items) {
        assert.ok(it.en && it.en.t, it.id + ' has an English title');
        assert.doesNotMatch(AG.loc(it, 't') + (AG.loc(it, 'd') || ''), /[\u0E00-\u0E7F]/, it.id + ' English text has no Thai');
      }
    }
    AG.setLang('th');
    assert.match(AG.marketingStatus('k2-1', pack, null, CFG).detail, /ยังไม่มีโฟลเดอร์/);
  } finally { AG.setLang('th'); }
});

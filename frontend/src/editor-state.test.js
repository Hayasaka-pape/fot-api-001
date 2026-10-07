import assert from 'node:assert/strict';
import test from 'node:test';
import { colorInputValue, queryKey, reconcileSavedScene, sceneKey } from './editor-state.js';

const day = '2026-10-07';
const query = { kind: 'match', id: '5315746', date: day, timezone: 'Asia/Tokyo', timeout: 15, mode: 'demo' };
const makeScene = () => ({ name: 'Match', query: { ...query }, sections: ['scoreboard'], canvas: { width: 1920, height: 1080, background: 'transparent' }, theme: { accent: '#b8ef55', background: '#15191d', text: '#f5f7f8', opacity: 0.94 }, widgets: [{ id: 'scoreboard', section: 'scoreboard', x: 110, y: 70, width: 1700, height: 240, fontSize: 32 }], pollInterval: 30 });

test('backend query defaults and legacy null dates do not create false unsaved changes', () => {
  const normalized = { sections: null, mode: 'demo', timeout: 15, timezone: 'Asia/Tokyo', date: null, id: 5315746, kind: 'match' };
  assert.equal(queryKey(query, day), queryKey(normalized, day));
  assert.notEqual(queryKey(query, day), queryKey({ ...query, id: '5181855' }, day));
});

test('save completion keeps a drag made after submission and attaches the generated scene ID', () => {
  const submitted = makeScene(), current = structuredClone(submitted), saved = { ...structuredClone(submitted), id: 'new-id' };
  current.widgets[0].x = 180;
  const result = reconcileSavedScene(submitted, current, saved, day);
  assert.equal(result.id, 'new-id'); assert.equal(result.widgets[0].x, 180); assert.equal(saved.widgets[0].x, 110);
  assert.notEqual(sceneKey(result, day), sceneKey(saved, day));
});

test('save completion retains a match selected during submission rather than restoring the prior match', () => {
  const submitted = makeScene(), current = { ...structuredClone(submitted), query: { ...query, id: '5181855' } }, saved = { ...structuredClone(submitted), id: 'new-id' };
  assert.equal(reconcileSavedScene(submitted, current, saved, day).query.id, '5181855');
});

test('unchanged save can adopt server normalization without becoming dirty', () => {
  const submitted = makeScene(), saved = { ...structuredClone(submitted), id: 'new-id', query: { ...query, sections: null } };
  const result = reconcileSavedScene(submitted, structuredClone(submitted), saved, day);
  assert.equal(result, saved); assert.equal(sceneKey(result, day), sceneKey(saved, day));
});

test('accepted API color formats produce native picker values without mutating saved alpha colors', () => {
  for (const [input, expected] of [['#abc', '#aabbcc'], ['#abcd', '#aabbcc'], ['#12345680', '#123456'], ['rgba(1, 2, 3, 0.4)', '#010203'], ['rgb(50%, 0%, 100%)', '#8000ff'], ['white', '#ffffff']]) assert.equal(colorInputValue(input), expected);
  const scene = makeScene(); scene.theme.background = 'rgba(1, 2, 3, 0.4)'; colorInputValue(scene.theme.background);
  assert.equal(scene.theme.background, 'rgba(1, 2, 3, 0.4)');
});

import assert from 'node:assert/strict';
import test from 'node:test';
import { pollDelayMs, startPolling } from './polling.js';

function fakeClock() {
  const queue = new Map(); let nextId = 0;
  return { queue, setTimeout: (callback, delay) => { const id = ++nextId; queue.set(id, { callback, delay }); return id; }, clearTimeout: id => queue.delete(id), next: () => { const [id, job] = queue.entries().next().value; queue.delete(id); return job.callback(); } };
}
const drain = async () => { await Promise.resolve(); await Promise.resolve(); };

test('slow requests do not overlap and old 15-second scenes still wait at least 30 seconds', async () => {
  const clock = fakeClock(), results = []; let resolve, calls = 0;
  const stop = startPolling({ clock, intervalSeconds: 15, load: () => { calls++; return new Promise(done => { resolve = done; }); }, onResult: result => results.push(result) });
  assert.equal(calls, 1); assert.equal(clock.queue.size, 0);
  resolve('first'); await drain();
  assert.deepEqual(results, ['first']); assert.equal(clock.queue.size, 1); assert.equal([...clock.queue.values()][0].delay, 30000);
  clock.next(); assert.equal(calls, 2); assert.equal(clock.queue.size, 0);
  stop(); resolve('after stop'); await drain();
  assert.deepEqual(results, ['first']); assert.equal(clock.queue.size, 0);
});

test('cleanup aborts an in-flight request and suppresses its late result', async () => {
  const clock = fakeClock(); let signal, resolve, applied = false;
  const stop = startPolling({ clock, load: value => { signal = value; return new Promise(done => { resolve = done; }); }, onResult: () => { applied = true; } });
  stop(); assert.equal(signal.aborted, true); resolve('late'); await drain();
  assert.equal(applied, false); assert.equal(clock.queue.size, 0);
});

test('a transient failure reports stale data and continues on the next successful poll', async () => {
  const clock = fakeClock(), errors = [], values = []; let calls = 0;
  const stop = startPolling({ clock, load: async () => { if (++calls === 1) throw new Error('offline'); return 'recovered'; }, onError: error => errors.push(error.message), onResult: value => values.push(value) });
  await drain(); assert.deepEqual(errors, ['offline']); assert.deepEqual(values, []);
  await clock.next(); assert.deepEqual(values, ['recovered']); stop(); assert.equal(clock.queue.size, 0);
});

test('draft guards skip fetching while preserving a future polling opportunity', async () => {
  const clock = fakeClock(); let allowed = false, calls = 0;
  const stop = startPolling({ clock, immediate: false, shouldPoll: () => allowed, load: async () => ++calls });
  await clock.next(); assert.equal(calls, 0); assert.equal(clock.queue.size, 1);
  allowed = true; await clock.next(); assert.equal(calls, 1); stop();
});

test('invalid intervals fall back safely and custom intervals are retained', () => {
  for (const value of [undefined, null, 0, -1, NaN, 'bad']) assert.equal(pollDelayMs(value), 30000);
  assert.equal(pollDelayMs(45), 45000);
});
